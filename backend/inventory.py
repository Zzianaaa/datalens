"""Transactional inventory ledger, quantities measured in whole units."""
import secrets
import time
from .library import connect


def initialize(con):
    con.execute('CREATE TABLE IF NOT EXISTS inventory_items (id TEXT PRIMARY KEY,sku TEXT UNIQUE NOT NULL,name TEXT NOT NULL,unit TEXT NOT NULL,reorder_level INTEGER NOT NULL,quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0))')
    con.execute('CREATE TABLE IF NOT EXISTS inventory_moves (id TEXT PRIMARY KEY,item_id TEXT NOT NULL REFERENCES inventory_items(id),delta INTEGER NOT NULL,reason TEXT NOT NULL,created REAL NOT NULL)')


def listing():
    with connect() as con:
        initialize(con)
        return {'items':[dict(r) for r in con.execute('SELECT * FROM inventory_items ORDER BY sku')],
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
