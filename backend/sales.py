"""Multi-item sales orders and atomic, idempotent shipment posting."""
import json
import secrets
import time
from .library import connect
from . import inventory, receivables


def initialize(con):
    inventory.initialize(con)
    receivables.initialize(con)
    con.execute("CREATE TABLE IF NOT EXISTS sales_orders (id TEXT PRIMARY KEY,reference TEXT UNIQUE NOT NULL,customer TEXT NOT NULL,item_id TEXT NOT NULL REFERENCES inventory_items(id),quantity INTEGER NOT NULL,unit_price INTEGER NOT NULL,due TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',invoice_id TEXT REFERENCES receivables(id),created REAL NOT NULL)")
    con.execute('CREATE TABLE IF NOT EXISTS sales_lines (id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES sales_orders(id),item_id TEXT NOT NULL REFERENCES inventory_items(id),quantity INTEGER NOT NULL,unit_price INTEGER NOT NULL,shipped INTEGER NOT NULL DEFAULT 0,UNIQUE(order_id,item_id))')
    con.execute('CREATE TABLE IF NOT EXISTS sales_shipments (id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES sales_orders(id),payload TEXT NOT NULL,invoice_id TEXT NOT NULL REFERENCES receivables(id),created REAL NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS sales_shipment_lines (shipment_id TEXT NOT NULL REFERENCES sales_shipments(id),line_id TEXT NOT NULL REFERENCES sales_lines(id),quantity INTEGER NOT NULL,PRIMARY KEY(shipment_id,line_id))')
    # Every caller initializes before its own transaction. Migrate old orders once,
    # preserving their original stock movements, invoices and payments.
    if con.execute('SELECT 1 FROM sales_orders s WHERE NOT EXISTS (SELECT 1 FROM sales_lines l WHERE l.order_id=s.id) LIMIT 1').fetchone():
        con.execute('BEGIN IMMEDIATE')
        con.execute("INSERT INTO sales_lines SELECT 'legacy:'||s.id,s.id,s.item_id,s.quantity,s.unit_price,CASE WHEN s.status='fulfilled' THEN s.quantity ELSE 0 END FROM sales_orders s WHERE NOT EXISTS (SELECT 1 FROM sales_lines l WHERE l.order_id=s.id)")
        con.commit()


def fulfillment_rows(con):
    rows=[]
    for r in con.execute("SELECT i.id AS item_id,i.sku,i.name,i.unit,i.quantity AS stock,SUM(l.quantity-l.shipped) AS demand,COUNT(DISTINCT s.id) AS orders FROM sales_lines l JOIN sales_orders s ON s.id=l.order_id JOIN inventory_items i ON i.id=l.item_id WHERE s.status IN ('draft','partial') AND l.shipped<l.quantity GROUP BY i.id ORDER BY i.sku"):
        row=dict(r)
        row['incoming']=con.execute("SELECT COALESCE(SUM(ordered-received),0) FROM purchase_orders WHERE item_id=? AND status='open'",(r['item_id'],)).fetchone()[0]
        row['shortage']=max(0,row['demand']-row['stock'])
        row['purchase_gap']=max(0,row['shortage']-row['incoming'])
        rows.append(row)
    return rows


def listing():
    with connect() as con:
        initialize(con)
        con.execute('BEGIN')
        orders=[]
        for row in con.execute('SELECT * FROM sales_orders ORDER BY created DESC'):
            order=dict(row)
            order['lines']=[dict(r) for r in con.execute('SELECT l.*,i.sku,i.name,i.unit FROM sales_lines l JOIN inventory_items i ON i.id=l.item_id WHERE l.order_id=? ORDER BY l.id',(row['id'],))]
            order['ordered_amount']=sum(l['quantity']*l['unit_price'] for l in order['lines'])
            order['shipped_amount']=sum(l['shipped']*l['unit_price'] for l in order['lines'])
            order['paid']=con.execute('SELECT COALESCE(SUM(paid),0) FROM receivables WHERE id IN (SELECT invoice_id FROM sales_shipments WHERE order_id=? UNION SELECT invoice_id FROM sales_orders WHERE id=?)',(row['id'],row['id'])).fetchone()[0]
            orders.append(order)
        shipments=[dict(r) for r in con.execute('SELECT b.*,s.reference,s.customer,r.reference AS invoice_reference,r.amount,r.paid FROM sales_shipments b JOIN sales_orders s ON s.id=b.order_id JOIN receivables r ON r.id=b.invoice_id ORDER BY b.created DESC LIMIT 100')]
        return {'orders':orders,'shipments':shipments,'fulfillment':fulfillment_rows(con),'items':[dict(r) for r in con.execute('SELECT * FROM inventory_items ORDER BY sku')]}


def create(reference,customer,item_id,quantity,unit_price,due):
    return create_basket(reference,customer,[{'item_id':item_id,'quantity':quantity,'unit_price':unit_price}],due)


def create_basket(reference,customer,lines,due):
    if not 1<=len(lines)<=20:raise ValueError('每单需包含 1 至 20 种商品')
    if len({l['item_id'] for l in lines})!=len(lines):raise ValueError('同一商品请合并为一行')
    if any(type(l['quantity']) is not int or not 1<=l['quantity']<=1000000 or type(l['unit_price']) is not int or l['unit_price']<1 for l in lines):raise ValueError('数量和单价必须是正整数')
    if sum(l['quantity']*l['unit_price'] for l in lines)>100000000000:raise ValueError('订单金额超过上限')
    with connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        if con.execute('SELECT COUNT(*) FROM sales_orders').fetchone()[0]>=500:raise ValueError('最多 500 张销售订单')
        if con.execute('SELECT 1 FROM sales_orders WHERE reference=?',(reference,)).fetchone():raise ValueError('销售订单编号已存在')
        for line in lines:
            if not con.execute('SELECT 1 FROM inventory_items WHERE id=?',(line['item_id'],)).fetchone():raise KeyError(line['item_id'])
        key=secrets.token_urlsafe(18)
        first=lines[0]
        con.execute('INSERT INTO sales_orders(id,reference,customer,item_id,quantity,unit_price,due,created) VALUES (?,?,?,?,?,?,?,?)',(key,reference,customer,first['item_id'],first['quantity'],first['unit_price'],due,time.time()))
        con.executemany('INSERT INTO sales_lines VALUES (?,?,?,?,?,0)',[(secrets.token_urlsafe(18),key,l['item_id'],l['quantity'],l['unit_price']) for l in lines])
        return {'id':key}


def _ship(con,key,lines,shipment_id):
    if not lines or len({l['line_id'] for l in lines})!=len(lines):raise ValueError('请指定发货商品，不能重复同一订单行')
    if any(type(l['quantity']) is not int or l['quantity']<1 for l in lines):raise ValueError('发货数量必须是正整数')
    payload=json.dumps(sorted((l['line_id'],l['quantity']) for l in lines),separators=(',',':'))
    old=con.execute('SELECT * FROM sales_shipments WHERE id=?',(shipment_id,)).fetchone()
    if old:
        if old['order_id']!=key or old['payload']!=payload:raise ValueError('发货标识已用于其他批次，请核对原请求')
        return {'duplicate':True,'invoice_id':old['invoice_id']}
    order=con.execute('SELECT * FROM sales_orders WHERE id=?',(key,)).fetchone()
    if order is None:raise KeyError(key)
    if order['status'] not in ('draft','partial'):raise ValueError('订单已发完或关闭，不能继续发货')
    amount=0
    selected=[]
    for request in lines:
        line=con.execute('SELECT l.*,i.quantity AS stock FROM sales_lines l JOIN inventory_items i ON i.id=l.item_id WHERE l.id=? AND l.order_id=?',(request['line_id'],key)).fetchone()
        if line is None:raise ValueError('商品行不属于该订单')
        if request['quantity']>line['quantity']-line['shipped']:raise ValueError('发货数量超过该商品未发数量')
        if request['quantity']>line['stock']:raise ValueError('库存不足，请先补货')
        amount+=request['quantity']*line['unit_price']
        selected.append((line,request['quantity']))
    if con.execute('SELECT COUNT(*) FROM sales_shipments').fetchone()[0]>=2000:raise ValueError('最多 2000 个发货批次')
    if con.execute('SELECT COUNT(*) FROM receivables').fetchone()[0]>=500:raise ValueError('应收台账已达到 500 条上限')
    batch=con.execute('SELECT COUNT(*) FROM sales_shipments WHERE order_id=?',(key,)).fetchone()[0]+1
    reference='销售:'+order['reference']+(f'/批次{batch}' if batch>1 else '')
    if con.execute('SELECT 1 FROM receivables WHERE reference=?',(reference,)).fetchone():raise ValueError('对应应收单据编号已被使用')
    invoice=secrets.token_urlsafe(18)
    now=time.time()
    con.execute('INSERT INTO receivables(id,reference,customer,amount,due,created) VALUES (?,?,?,?,?,?)',(invoice,reference,order['customer'],amount,order['due'],now))
    con.execute('INSERT INTO sales_shipments VALUES (?,?,?,?,?)',(shipment_id,key,payload,invoice,now))
    for line,quantity in selected:
        con.execute('UPDATE inventory_items SET quantity=quantity-? WHERE id=?',(quantity,line['item_id']))
        con.execute('UPDATE sales_lines SET shipped=shipped+? WHERE id=?',(quantity,line['id']))
        con.execute('INSERT INTO inventory_moves VALUES (?,?,?,?,?)',(secrets.token_urlsafe(18),line['item_id'],-quantity,'销售发货 '+order['reference']+f' 批次{batch}',now))
        con.execute('INSERT INTO sales_shipment_lines VALUES (?,?,?)',(shipment_id,line['id'],quantity))
    pending=con.execute('SELECT 1 FROM sales_lines WHERE order_id=? AND shipped<quantity LIMIT 1',(key,)).fetchone()
    con.execute('UPDATE sales_orders SET status=?,invoice_id=COALESCE(invoice_id,?) WHERE id=?',('partial' if pending else 'fulfilled',invoice,key))
    return {'duplicate':False,'invoice_id':invoice}


def ship(key,lines,shipment_id):
    if shipment_id.startswith('whole:'):raise ValueError('发货标识使用了保留前缀')
    with connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        return _ship(con,key,lines,shipment_id)


def fulfill(key):
    with connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        order=con.execute('SELECT * FROM sales_orders WHERE id=?',(key,)).fetchone()
        if order is None:raise KeyError(key)
        if order['status']=='fulfilled':
            previous=con.execute('SELECT invoice_id FROM sales_shipments WHERE id=?',('whole:'+key,)).fetchone()
            return {'duplicate':True,'invoice_id':previous['invoice_id'] if previous else order['invoice_id']}
        if order['status']=='cancelled':raise ValueError('订单已关闭，不能继续发货')
        lines=[{'line_id':r['id'],'quantity':r['quantity']-r['shipped']} for r in con.execute('SELECT * FROM sales_lines WHERE order_id=? AND shipped<quantity',(key,))]
        return _ship(con,key,lines,'whole:'+key)


def cancel(key):
    with connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        order=con.execute('SELECT status FROM sales_orders WHERE id=?',(key,)).fetchone()
        if order is None:raise KeyError(key)
        if order['status']=='fulfilled':raise ValueError('已全部发货订单不能取消')
        con.execute("UPDATE sales_orders SET status='cancelled' WHERE id=?",(key,))
        return {'cancelled':True}
