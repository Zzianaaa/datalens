"""Read-only operational overview from a single database snapshot."""
from .library import connect
from . import sales, tasks, payables, expenses


def listing(today):
    day=today.isoformat()
    with connect() as con:
        sales.initialize(con)
        tasks.initialize(con)
        payables.initialize(con)
        expenses.initialize(con)
        con.execute('BEGIN')
        scalar=lambda sql,args=():con.execute(sql,args).fetchone()[0]
        orders=dict(con.execute("SELECT COUNT(*) AS total,COALESCE(SUM(status='draft'),0) AS pending,COALESCE(SUM(status='fulfilled'),0) AS fulfilled,COALESCE(SUM(CASE WHEN status='fulfilled' THEN quantity*unit_price ELSE 0 END),0) AS shipped_amount FROM sales_orders").fetchone())
        cash=dict(con.execute("SELECT COUNT(*) AS invoices,COALESCE(SUM(amount),0) AS amount,COALESCE(SUM(paid),0) AS paid,COALESCE(SUM(amount-paid),0) AS unpaid,COALESCE(SUM(CASE WHEN due<? THEN amount-paid ELSE 0 END),0) AS overdue FROM receivables",(day,)).fetchone())
        payable=dict(con.execute("SELECT COUNT(*) AS bills,COALESCE(SUM(amount),0) AS amount,COALESCE(SUM(paid),0) AS paid,COALESCE(SUM(amount-paid),0) AS unpaid,COALESCE(SUM(CASE WHEN due<? THEN amount-paid ELSE 0 END),0) AS overdue FROM payables",(day,)).fetchone())
        expense=dict(con.execute('SELECT COUNT(*) AS records,COALESCE(SUM(e.amount),0) AS amount FROM expenses e LEFT JOIN expense_voids v ON v.expense_id=e.id WHERE v.expense_id IS NULL').fetchone())
        stock=dict(con.execute("SELECT COUNT(*) AS items,COALESCE(SUM(quantity<=reorder_level),0) AS low,COALESCE(SUM(quantity=0),0) AS empty FROM inventory_items").fetchone())
        procurement=dict(con.execute("SELECT COUNT(*) AS pending,COALESCE(SUM(due<>'' AND due<?),0) AS overdue FROM purchase_orders WHERE status='open'",(day,)).fetchone())
        work=dict(con.execute("SELECT COUNT(*) AS pending,COALESCE(SUM(due<>'' AND due<?),0) AS overdue FROM tasks WHERE status NOT IN ('已完成','已归档')",(day,)).fetchone())
        customers=[dict(r) for r in con.execute('SELECT customer,COUNT(*) AS invoices,SUM(amount-paid) AS unpaid,SUM(CASE WHEN due<? THEN amount-paid ELSE 0 END) AS overdue FROM receivables WHERE amount>paid GROUP BY customer ORDER BY overdue DESC,unpaid DESC,customer LIMIT 5',(day,))]
        return {'as_of':day,'sales':orders,'cash':cash,'payables':payable,'expenses':expense,'stock':stock,'procurement':procurement,'work':work,'library':{'projects':scalar('SELECT COUNT(*) FROM projects'),'datasets':scalar('SELECT COUNT(*) FROM assets WHERE archived=0'),'reports':scalar('SELECT COUNT(*) FROM reports')},'customers':customers}
