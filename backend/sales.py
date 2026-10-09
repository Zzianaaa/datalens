"""Sales fulfillment atomically posts stock and receivables."""
import secrets
import time
from .library import connect
from . import inventory, receivables


def initialize(con):
    inventory.initialize(con)
    receivables.initialize(con)
    con.execute("CREATE TABLE IF NOT EXISTS sales_orders (id TEXT PRIMARY KEY,reference TEXT UNIQUE NOT NULL,customer TEXT NOT NULL,item_id TEXT NOT NULL REFERENCES inventory_items(id),quantity INTEGER NOT NULL,unit_price INTEGER NOT NULL,due TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',invoice_id TEXT REFERENCES receivables(id),created REAL NOT NULL)")


def listing():
    with connect() as con:
        initialize(con)
        return {'orders':[dict(r) for r in con.execute('SELECT s.*,i.sku,i.name,r.paid FROM sales_orders s JOIN inventory_items i ON i.id=s.item_id LEFT JOIN receivables r ON r.id=s.invoice_id ORDER BY s.created DESC')], 'items':[dict(r) for r in con.execute('SELECT * FROM inventory_items ORDER BY sku')]}


def create(reference,customer,item_id,quantity,unit_price,due):
    if quantity*unit_price>100000000000:raise ValueError('订单金额超过上限')
    with connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        if con.execute('SELECT COUNT(*) FROM sales_orders').fetchone()[0]>=500:raise ValueError('最多 500 张销售订单')
        if con.execute('SELECT 1 FROM sales_orders WHERE reference=?',(reference,)).fetchone():raise ValueError('销售订单编号已存在')
        if not con.execute('SELECT 1 FROM inventory_items WHERE id=?',(item_id,)).fetchone():raise KeyError(item_id)
        key=secrets.token_urlsafe(18)
        con.execute('INSERT INTO sales_orders(id,reference,customer,item_id,quantity,unit_price,due,created) VALUES (?,?,?,?,?,?,?,?)',(key,reference,customer,item_id,quantity,unit_price,due,time.time()))
        return {'id':key}


def fulfill(key):
    with connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        order=con.execute('SELECT * FROM sales_orders WHERE id=?',(key,)).fetchone()
        if order is None:raise KeyError(key)
        if order['status']=='fulfilled':return {'duplicate':True,'invoice_id':order['invoice_id']}
        if order['status']!='draft':raise ValueError('已取消订单不能发货')
        item=con.execute('SELECT quantity FROM inventory_items WHERE id=?',(order['item_id'],)).fetchone()
        if item['quantity']<order['quantity']:raise ValueError('库存不足，请先补货')
        if con.execute('SELECT COUNT(*) FROM receivables').fetchone()[0]>=500:raise ValueError('应收台账已达到 500 条上限')
        reference='销售:'+order['reference']
        if con.execute('SELECT 1 FROM receivables WHERE reference=?',(reference,)).fetchone():raise ValueError('对应应收单据编号已被使用')
        invoice=secrets.token_urlsafe(18)
        now=time.time()
        con.execute('UPDATE inventory_items SET quantity=quantity-? WHERE id=?',(order['quantity'],order['item_id']))
        con.execute('INSERT INTO inventory_moves VALUES (?,?,?,?,?)',(secrets.token_urlsafe(18),order['item_id'],-order['quantity'],'销售发货 '+order['reference'],now))
        con.execute('INSERT INTO receivables(id,reference,customer,amount,due,created) VALUES (?,?,?,?,?,?)',(invoice,reference,order['customer'],order['quantity']*order['unit_price'],order['due'],now))
        con.execute("UPDATE sales_orders SET status='fulfilled',invoice_id=? WHERE id=?",(invoice,key))
        return {'duplicate':False,'invoice_id':invoice}


def cancel(key):
    with connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        order=con.execute('SELECT status FROM sales_orders WHERE id=?',(key,)).fetchone()
        if order is None:raise KeyError(key)
        if order['status']=='fulfilled':raise ValueError('已发货订单不能取消')
        con.execute("UPDATE sales_orders SET status='cancelled' WHERE id=?",(key,))
        return {'cancelled':True}
