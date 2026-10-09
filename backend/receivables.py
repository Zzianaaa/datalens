"""Manual receivables ledger. All amounts are integer cents."""
import secrets
import time
from .library import connect


def initialize(con):
    con.execute('CREATE TABLE IF NOT EXISTS receivables (id TEXT PRIMARY KEY,reference TEXT UNIQUE NOT NULL,customer TEXT NOT NULL,amount INTEGER NOT NULL,paid INTEGER NOT NULL DEFAULT 0,due TEXT NOT NULL,created REAL NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY,receivable_id TEXT NOT NULL REFERENCES receivables(id),amount INTEGER NOT NULL,note TEXT NOT NULL,created REAL NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS receipt_reversals (receipt_id TEXT PRIMARY KEY REFERENCES receipts(id),reason TEXT NOT NULL,created REAL NOT NULL)')


def listing():
    with connect() as con:
        initialize(con)
        return {'invoices':[dict(r) for r in con.execute('SELECT * FROM receivables ORDER BY due,id')], 'receipts':[dict(r) for r in con.execute('SELECT r.*,i.reference,i.customer,v.reason AS reversal_reason,v.created AS reversed_at FROM receipts r JOIN receivables i ON i.id=r.receivable_id LEFT JOIN receipt_reversals v ON v.receipt_id=r.id ORDER BY r.created DESC LIMIT 100')]}


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


def reverse(receipt_id,reason):
    with connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        receipt=con.execute('SELECT * FROM receipts WHERE id=?',(receipt_id,)).fetchone()
        if receipt is None:raise KeyError(receipt_id)
        old=con.execute('SELECT reason FROM receipt_reversals WHERE receipt_id=?',(receipt_id,)).fetchone()
        if old:
            if old['reason']!=reason:raise ValueError('该流水已冲销，请保留原冲销说明')
            return {'duplicate':True}
        con.execute('UPDATE receivables SET paid=paid-? WHERE id=?',(receipt['amount'],receipt['receivable_id']))
        con.execute('INSERT INTO receipt_reversals VALUES (?,?,?)',(receipt_id,reason,time.time()))
        return {'duplicate':False}


def followup(customer,owner,due):
    from . import tasks
    with connect() as con:
        initialize(con)
        tasks.initialize(con)
        con.execute('CREATE TABLE IF NOT EXISTS collection_tasks (customer TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES tasks(id))')
        con.execute('BEGIN IMMEDIATE')
        invoices=list(con.execute('SELECT * FROM receivables WHERE customer=? AND paid<amount',(customer,)))
        if not invoices:raise ValueError('该客户没有未收款项')
        existing=con.execute("SELECT t.id FROM collection_tasks c JOIN tasks t ON t.id=c.task_id WHERE c.customer=? AND t.status NOT IN ('已完成','已归档')",(customer,)).fetchone()
        if existing:return {'id':existing['id'],'existing':True}
        if con.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]>=500:raise ValueError('最多 500 个任务')
        key=secrets.token_urlsafe(18)
        balance=sum(i['amount']-i['paid'] for i in invoices)
        notes=f'回款跟进快照：客户 {customer}，未收 {balance/100:.2f} 元，{len(invoices)} 张单据。余额变化请回到回款中心核对；任务不会自动完成。'
        con.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)',(key,None,('跟进回款：'+customer)[:120],owner,due,'待处理',notes,time.time()))
        con.execute('INSERT INTO collection_tasks VALUES (?,?) ON CONFLICT(customer) DO UPDATE SET task_id=excluded.task_id',(customer,key))
        return {'id':key,'existing':False}
