"""Manual receivables ledger. All amounts are integer cents."""
import secrets
import time
from .library import connect


def initialize(con):
    con.execute('CREATE TABLE IF NOT EXISTS receivables (id TEXT PRIMARY KEY,reference TEXT UNIQUE NOT NULL,customer TEXT NOT NULL,amount INTEGER NOT NULL,paid INTEGER NOT NULL DEFAULT 0,due TEXT NOT NULL,created REAL NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY,receivable_id TEXT NOT NULL REFERENCES receivables(id),amount INTEGER NOT NULL,note TEXT NOT NULL,created REAL NOT NULL)')


def listing():
    with connect() as con:
        initialize(con)
        return {'invoices':[dict(r) for r in con.execute('SELECT * FROM receivables ORDER BY due,id')], 'receipts':[dict(r) for r in con.execute('SELECT r.*,i.reference,i.customer FROM receipts r JOIN receivables i ON i.id=r.receivable_id ORDER BY r.created DESC LIMIT 100')]}


def create(reference,customer,amount,due):
    with connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        if con.execute('SELECT COUNT(*) FROM receivables').fetchone()[0]>=500:raise ValueError('最多 500 条应收记录')
        if con.execute('SELECT 1 FROM receivables WHERE reference=?',(reference,)).fetchone():raise ValueError('单据编号已存在')
        key=secrets.token_urlsafe(18)
        con.execute('INSERT INTO receivables(id,reference,customer,amount,due,created) VALUES (?,?,?,?,?,?)',(key,reference,customer,amount,due,time.time()))
        return {'id':key}


def receive(key,amount,note,receipt_id):
    with connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        old=con.execute('SELECT * FROM receipts WHERE id=?',(receipt_id,)).fetchone()
        if old:
            if old['receivable_id']!=key or old['amount']!=amount or old['note']!=note:raise ValueError('回款标识已用于其他记录')
            return {'duplicate':True}
        invoice=con.execute('SELECT * FROM receivables WHERE id=?',(key,)).fetchone()
        if invoice is None:raise KeyError(key)
        if amount>invoice['amount']-invoice['paid']:raise ValueError('回款超过未收金额')
        con.execute('UPDATE receivables SET paid=paid+? WHERE id=?',(amount,key))
        con.execute('INSERT INTO receipts VALUES (?,?,?,?,?)',(receipt_id,key,amount,note,time.time()))
        return {'duplicate':False,'paid':invoice['paid']+amount}
