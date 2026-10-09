"""Paid operating expenses with immutable records and void audit trail."""
import time
from .library import connect

CATEGORIES=('租金','人员','营销','物流','软件','办公','其他')


def initialize(con):
    con.execute('CREATE TABLE IF NOT EXISTS expenses (id TEXT PRIMARY KEY,reference TEXT UNIQUE NOT NULL,category TEXT NOT NULL,amount INTEGER NOT NULL,occurred TEXT NOT NULL,counterparty TEXT NOT NULL,project_id TEXT REFERENCES projects(id),note TEXT NOT NULL,created REAL NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS expense_voids (expense_id TEXT PRIMARY KEY REFERENCES expenses(id),reason TEXT NOT NULL,created REAL NOT NULL)')


def listing():
    with connect() as con:
        initialize(con)
        return {'expenses':[dict(r) for r in con.execute('SELECT e.*,p.name AS project_name,v.reason AS void_reason FROM expenses e LEFT JOIN projects p ON p.id=e.project_id LEFT JOIN expense_voids v ON v.expense_id=e.id ORDER BY e.occurred DESC,e.created DESC')], 'categories':list(CATEGORIES)}


def create(key,reference,category,amount,occurred,counterparty,project_id,note):
    if category not in CATEGORIES:raise ValueError('费用类别无效')
    values=(reference,category,amount,occurred,counterparty,project_id or None,note)
    with connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        old=con.execute('SELECT * FROM expenses WHERE id=?',(key,)).fetchone()
        if old:
            if tuple(old[c] for c in ('reference','category','amount','occurred','counterparty','project_id','note'))!=values:raise ValueError('费用标识已用于其他记录')
            return {'id':key,'duplicate':True}
        if con.execute('SELECT COUNT(*) FROM expenses').fetchone()[0]>=500:raise ValueError('最多 500 条费用记录')
        if con.execute('SELECT 1 FROM expenses WHERE reference=?',(reference,)).fetchone():raise ValueError('费用编号已存在')
        if project_id and not con.execute('SELECT 1 FROM projects WHERE id=?',(project_id,)).fetchone():raise ValueError('项目不存在')
        con.execute('INSERT INTO expenses VALUES (?,?,?,?,?,?,?,?,?)',(key,*values,time.time()))
        return {'id':key,'duplicate':False}


def void(key,reason):
    with connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        if not con.execute('SELECT 1 FROM expenses WHERE id=?',(key,)).fetchone():raise KeyError(key)
        old=con.execute('SELECT reason FROM expense_voids WHERE expense_id=?',(key,)).fetchone()
        if old:
            if old['reason']!=reason:raise ValueError('费用已作废，请保留原说明')
            return {'duplicate':True}
        con.execute('INSERT INTO expense_voids VALUES (?,?,?)',(key,reason,time.time()))
        return {'duplicate':False}
