"""Transactional inventory ledger, quantities measured in whole units."""
import secrets
import time
from .library import connect


def initialize(con):
    con.execute('CREATE TABLE IF NOT EXISTS inventory_items (id TEXT PRIMARY KEY,sku TEXT UNIQUE NOT NULL,name TEXT NOT NULL,unit TEXT NOT NULL,reorder_level INTEGER NOT NULL,quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0))')
    con.execute('CREATE TABLE IF NOT EXISTS inventory_moves (id TEXT PRIMARY KEY,item_id TEXT NOT NULL REFERENCES inventory_items(id),delta INTEGER NOT NULL,reason TEXT NOT NULL,created REAL NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS purchase_orders (id TEXT PRIMARY KEY,item_id TEXT NOT NULL REFERENCES inventory_items(id),supplier TEXT NOT NULL,ordered INTEGER NOT NULL,received INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT \'open\',created REAL NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS purchase_receipts (id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES purchase_orders(id),quantity INTEGER NOT NULL)')


def listing():
    with connect() as con:
        initialize(con)
        return {'orders':[dict(r) for r in con.execute('SELECT p.*,i.sku,i.name,i.unit FROM purchase_orders p JOIN inventory_items i ON i.id=p.item_id ORDER BY p.created DESC LIMIT 500')], 'items':[dict(r) for r in con.execute('SELECT * FROM inventory_items ORDER BY sku')],
                'movements':[dict(r) for r in con.execute('SELECT m.*,i.sku,i.name FROM inventory_moves m JOIN inventory_items i ON i.id=m.item_id ORDER BY m.created DESC LIMIT 100')]}


def create_item(sku,name,unit,reorder_level):
    with connect() as con:
        initialize(con)
        if con.execute('SELECT COUNT(*) FROM inventory_items').fetchone()[0]>=500:raise ValueError('最多 500 个商品')
        if con.execute('SELECT 1 FROM inventory_items WHERE sku=?',(sku,)).fetchone():raise ValueError('SKU 已存在')
        key=secrets.token_urlsafe(18)
        con.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,0)',(key,sku,name,unit,reorder_level))
        return {'id':key}


def move(item_id,delta,reason):
    with connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        item=con.execute('SELECT quantity FROM inventory_items WHERE id=?',(item_id,)).fetchone()
        if item is None:raise KeyError(item_id)
        if item['quantity']+delta<0:raise ValueError('库存不足，不能产生负库存')
        if item['quantity']+delta>1000000000:raise ValueError('库存数量超过上限')
        con.execute('UPDATE inventory_items SET quantity=quantity+? WHERE id=?',(delta,item_id))
        con.execute('INSERT INTO inventory_moves VALUES (?,?,?,?,?)',(secrets.token_urlsafe(18),item_id,delta,reason,time.time()))
        return {'quantity':item['quantity']+delta}


def create_order(item_id,supplier,quantity):
    with connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        if not con.execute('SELECT 1 FROM inventory_items WHERE id=?',(item_id,)).fetchone():raise KeyError(item_id)
        if con.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0]>=500:raise ValueError('最多 500 张采购单')
        key=secrets.token_urlsafe(18)
        con.execute('INSERT INTO purchase_orders(id,item_id,supplier,ordered,created) VALUES (?,?,?,?,?)',(key,item_id,supplier,quantity,time.time()))
        return {'id':key}


def receive_order(key,quantity,receipt_id):
    with connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        old=con.execute('SELECT * FROM purchase_receipts WHERE id=?',(receipt_id,)).fetchone()
        if old:
            if old['order_id']!=key or old['quantity']!=quantity:raise ValueError('到货标识已用于其他记录')
            return {'duplicate':True}
        order=con.execute('SELECT * FROM purchase_orders WHERE id=?',(key,)).fetchone()
        if order is None:raise KeyError(key)
        if order['status']!='open':raise ValueError('采购单已完成或取消')
        if quantity>order['ordered']-order['received']:raise ValueError('到货数量超过未到货数量')
        stock=con.execute('SELECT quantity FROM inventory_items WHERE id=?',(order['item_id'],)).fetchone()[0]
        if stock+quantity>1000000000:raise ValueError('库存数量超过上限')
        received=order['received']+quantity
        con.execute('UPDATE purchase_orders SET received=?,status=? WHERE id=?',(received,'complete' if received==order['ordered'] else 'open',key))
        con.execute('UPDATE inventory_items SET quantity=quantity+? WHERE id=?',(quantity,order['item_id']))
        con.execute('INSERT INTO inventory_moves VALUES (?,?,?,?,?)',(secrets.token_urlsafe(18),order['item_id'],quantity,'采购到货 '+key,time.time()))
        con.execute('INSERT INTO purchase_receipts VALUES (?,?,?)',(receipt_id,key,quantity))
        return {'received':received,'duplicate':False}


def cancel_order(key):
    with connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        order=con.execute('SELECT status FROM purchase_orders WHERE id=?',(key,)).fetchone()
        if order is None:raise KeyError(key)
        if order['status']!='open':raise ValueError('只能取消待到货的采购单')
        con.execute("UPDATE purchase_orders SET status='cancelled' WHERE id=?",(key,))
        return {'status':'cancelled'}
