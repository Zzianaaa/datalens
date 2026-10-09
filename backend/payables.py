"""Supplier payables generated from priced procurement receipts, integer cents."""
import secrets
import time
from .library import connect


def initialize(con):
    con.execute('CREATE TABLE IF NOT EXISTS payables (id TEXT PRIMARY KEY,receipt_id TEXT UNIQUE NOT NULL REFERENCES purchase_receipts(id),amount INTEGER NOT NULL,paid INTEGER NOT NULL DEFAULT 0,due TEXT NOT NULL,created REAL NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS payments (id TEXT PRIMARY KEY,payable_id TEXT NOT NULL REFERENCES payables(id),amount INTEGER NOT NULL,note TEXT NOT NULL,created REAL NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS payment_reversals (payment_id TEXT PRIMARY KEY REFERENCES payments(id),reason TEXT NOT NULL,created REAL NOT NULL)')


def listing():
    from . import inventory
    with connect() as con:
        inventory.initialize(con)
        initialize(con)
        bills=[dict(r) for r in con.execute('SELECT p.*,r.order_id,r.quantity,o.supplier,i.sku,i.name FROM payables p JOIN purchase_receipts r ON r.id=p.receipt_id JOIN purchase_orders o ON o.id=r.order_id JOIN inventory_items i ON i.id=o.item_id ORDER BY p.due,p.created')]
        payments=[dict(r) for r in con.execute('SELECT m.*,p.receipt_id,o.supplier,v.reason AS reversal_reason FROM payments m JOIN payables p ON p.id=m.payable_id JOIN purchase_receipts r ON r.id=p.receipt_id JOIN purchase_orders o ON o.id=r.order_id LEFT JOIN payment_reversals v ON v.payment_id=m.id ORDER BY m.created DESC LIMIT 100')]
        return {'bills':bills,'payments':payments}


def pay(key,amount,note,payment_id):
    from . import inventory
    with connect() as con:
        inventory.initialize(con)
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        old=con.execute('SELECT * FROM payments WHERE id=?',(payment_id,)).fetchone()
        if old:
            if old['payable_id']!=key or old['amount']!=amount or old['note']!=note:raise ValueError('付款标识已用于其他记录')
            return {'duplicate':True}
        bill=con.execute('SELECT * FROM payables WHERE id=?',(key,)).fetchone()
        if bill is None:raise KeyError(key)
        if amount>bill['amount']-bill['paid']:raise ValueError('付款超过未付金额')
        con.execute('UPDATE payables SET paid=paid+? WHERE id=?',(amount,key))
        con.execute('INSERT INTO payments VALUES (?,?,?,?,?)',(payment_id,key,amount,note,time.time()))
        return {'duplicate':False,'paid':bill['paid']+amount}


def reverse(payment_id,reason):
    from . import inventory
    with connect() as con:
        inventory.initialize(con)
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        payment=con.execute('SELECT * FROM payments WHERE id=?',(payment_id,)).fetchone()
        if payment is None:raise KeyError(payment_id)
        old=con.execute('SELECT reason FROM payment_reversals WHERE payment_id=?',(payment_id,)).fetchone()
        if old:
            if old['reason']!=reason:raise ValueError('该流水已冲销，请保留原说明')
            return {'duplicate':True}
        con.execute('UPDATE payables SET paid=paid-? WHERE id=?',(payment['amount'],payment['payable_id']))
        con.execute('INSERT INTO payment_reversals VALUES (?,?,?)',(payment_id,reason,time.time()))
        return {'duplicate':False}
