"""Read-only operational overview from a single database snapshot."""
from datetime import date, datetime, timezone, timedelta
from .library import connect
from . import sales, tasks, payables, expenses


def monthly_rows(con,today):
    index=today.year*12+today.month-1
    months=[f'{n//12:04d}-{n%12+1:02d}' for n in range(index-11,index+1)]
    totals={m:{'month':m,'received':0,'supplier_paid':0,'expenses':0} for m in months}
    cutoff=datetime.combine(today+timedelta(days=1),datetime.min.time(),timezone.utc).timestamp()
    start=datetime.strptime(months[0],'%Y-%m').replace(tzinfo=timezone.utc).timestamp()
    for table,reversal,key,field in [('receipts','receipt_reversals','receipt_id','received'),('payments','payment_reversals','payment_id','supplier_paid')]:
        for r in con.execute(f"SELECT strftime('%Y-%m',r.created,'unixepoch') AS month,SUM(r.amount) AS amount FROM {table} r LEFT JOIN {reversal} v ON v.{key}=r.id WHERE v.{key} IS NULL AND r.created>=? AND r.created<? GROUP BY month",(start,cutoff)):
            if r['month'] in totals:totals[r['month']][field]=r['amount']
    for r in con.execute('SELECT substr(e.occurred,1,7) AS month,SUM(e.amount) AS amount FROM expenses e LEFT JOIN expense_voids v ON v.expense_id=e.id WHERE v.expense_id IS NULL AND e.occurred>=? AND e.occurred<=? GROUP BY month',(months[0]+'-01',today.isoformat())):
        if r['month'] in totals:totals[r['month']]['expenses']=r['amount']
    for row in totals.values():row['net']=row['received']-row['supplier_paid']-row['expenses']
    return list(totals.values())


def due_rows(con,today):
    rows=[{'period':label,'receivable_count':0,'receivable':0,'payable_count':0,'payable':0} for label in ['已逾期','今天到期','未来 1–7 天','未来 8–30 天','30 天以后']]
    for table,count,amount in [('receivables','receivable_count','receivable'),('payables','payable_count','payable')]:
        for record in con.execute(f'SELECT due,amount-paid AS remaining FROM {table} WHERE amount>paid'):
            days=(date.fromisoformat(record['due'])-today).days
            index=0 if days<0 else 1 if days==0 else 2 if days<=7 else 3 if days<=30 else 4
            rows[index][count]+=1;rows[index][amount]+=record['remaining']
    return rows


def listing(today):
    day=today.isoformat()
    with connect() as con:
        sales.initialize(con)
        tasks.initialize(con)
        payables.initialize(con)
        expenses.initialize(con)
        con.execute('BEGIN')
        scalar=lambda sql,args=():con.execute(sql,args).fetchone()[0]
        orders=dict(con.execute("SELECT COUNT(*) AS total,COALESCE(SUM(status IN ('draft','partial')),0) AS pending,COALESCE(SUM(status='fulfilled'),0) AS fulfilled,(SELECT COALESCE(SUM(shipped*unit_price),0) FROM sales_lines) AS shipped_amount FROM sales_orders").fetchone())
        cash=dict(con.execute("SELECT COUNT(*) AS invoices,COALESCE(SUM(amount),0) AS amount,COALESCE(SUM(paid),0) AS paid,COALESCE(SUM(amount-paid),0) AS unpaid,COALESCE(SUM(CASE WHEN due<? THEN amount-paid ELSE 0 END),0) AS overdue FROM receivables",(day,)).fetchone())
        payable=dict(con.execute("SELECT COUNT(*) AS bills,COALESCE(SUM(amount),0) AS amount,COALESCE(SUM(paid),0) AS paid,COALESCE(SUM(amount-paid),0) AS unpaid,COALESCE(SUM(CASE WHEN due<? THEN amount-paid ELSE 0 END),0) AS overdue FROM payables",(day,)).fetchone())
        expense=dict(con.execute('SELECT COUNT(*) AS records,COALESCE(SUM(e.amount),0) AS amount FROM expenses e LEFT JOIN expense_voids v ON v.expense_id=e.id WHERE v.expense_id IS NULL').fetchone())
        stock=dict(con.execute("SELECT COUNT(*) AS items,COALESCE(SUM(quantity<=reorder_level),0) AS low,COALESCE(SUM(quantity=0),0) AS empty FROM inventory_items").fetchone())
        procurement=dict(con.execute("SELECT COUNT(*) AS pending,COALESCE(SUM(due<>'' AND due<?),0) AS overdue FROM purchase_orders WHERE status='open'",(day,)).fetchone())
        work=dict(con.execute("SELECT COUNT(*) AS pending,COALESCE(SUM(due<>'' AND due<?),0) AS overdue FROM tasks WHERE status NOT IN ('已完成','已归档')",(day,)).fetchone())
        customers=[dict(r) for r in con.execute('SELECT customer,COUNT(*) AS invoices,SUM(amount-paid) AS unpaid,SUM(CASE WHEN due<? THEN amount-paid ELSE 0 END) AS overdue FROM receivables WHERE amount>paid GROUP BY customer ORDER BY overdue DESC,unpaid DESC,customer LIMIT 5',(day,))]
        return {'due_schedule':due_rows(con,today),'monthly':monthly_rows(con,today),'as_of':day,'sales':orders,'cash':cash,'payables':payable,'expenses':expense,'stock':stock,'procurement':procurement,'work':work,'library':{'projects':scalar('SELECT COUNT(*) FROM projects'),'datasets':scalar('SELECT COUNT(*) FROM assets WHERE archived=0'),'reports':scalar('SELECT COUNT(*) FROM reports')},'customers':customers}
