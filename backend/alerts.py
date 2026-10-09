"""Deterministic, read-only cross-module business alerts."""
from datetime import date
from .library import connect
from . import inventory, tasks, receivables, payables, expenses


def listing(today: date):
    alerts=[]
    with connect() as con:
        inventory.initialize(con)
        tasks.initialize(con)
        receivables.initialize(con)
        payables.initialize(con)
        expenses.initialize(con)
        con.execute('BEGIN')
        for item in con.execute('SELECT * FROM inventory_items ORDER BY sku'):
            pending=con.execute("SELECT COALESCE(SUM(ordered-received),0) FROM purchase_orders WHERE item_id=? AND status='open'",(item['id'],)).fetchone()[0]
            if item['quantity']<=item['reorder_level']:
                short=max(0,item['reorder_level']-item['quantity'])
                alerts.append({'id':'stock:'+item['id'],'category':'库存','severity':'高' if item['quantity']==0 else '中','title':item['name']+'库存达到补货阈值','detail':f"现有 {item['quantity']} {item['unit']}，阈值 {item['reorder_level']}，待到货 {pending}；考虑待到货后的缺口 {max(0,short-pending)}。",'target':'inventory'})
        for order in con.execute("SELECT p.*,i.sku FROM purchase_orders p JOIN inventory_items i ON i.id=p.item_id WHERE p.status='open' ORDER BY p.created"):
            overdue=bool(order['due'] and order['due']<today.isoformat())
            schedule=f"预计到货 {order['due']}" if order['due'] else '未设置预计到货日期'
            alerts.append({'id':'purchase:'+order['id'],'category':'采购','severity':'高' if overdue else '提示','title':order['sku']+('采购已逾期' if overdue else '有待到货采购'),'detail':f"供应商 {order['supplier']}，剩余 {order['ordered']-order['received']}；{schedule}。",'target':'inventory'})
        for task in con.execute("SELECT * FROM tasks WHERE due<>'' AND status NOT IN ('已完成','已归档') ORDER BY due"):
            if task['due']<today.isoformat():
                alerts.append({'id':'task:'+task['id'],'category':'任务','severity':'高','title':task['title']+'已逾期','detail':f"截止 {task['due']}，负责人 {task['owner'] or '未指定'}，状态 {task['status']}。",'target':'work'})
        for goal in con.execute("SELECT * FROM goals WHERE due<>'' AND current<target ORDER BY due"):
            if goal['due']<today.isoformat():
                alerts.append({'id':'goal:'+goal['id'],'category':'目标','severity':'中','title':goal['title']+'到期未达标','detail':f"截止 {goal['due']}，当前 {goal['current']:g} / {goal['target']:g} {goal['unit']}；目标数据由用户手工维护。",'target':'work'})
        for invoice in con.execute('SELECT * FROM receivables WHERE paid<amount ORDER BY due'):
            if invoice['due']<today.isoformat():
                alerts.append({'id':'cash:'+invoice['id'],'category':'回款','severity':'高','title':invoice['reference']+'回款逾期','detail':f"客户 {invoice['customer']}，截止 {invoice['due']}，未收 {(invoice['amount']-invoice['paid'])/100:.2f} 元。",'target':'cash'})
        for bill in con.execute('SELECT p.*,o.supplier,i.sku FROM payables p JOIN purchase_receipts r ON r.id=p.receipt_id JOIN purchase_orders o ON o.id=r.order_id JOIN inventory_items i ON i.id=o.item_id WHERE p.paid<p.amount AND p.due<? ORDER BY p.due',(today.isoformat(),)):
            alerts.append({'id':'payable:'+bill['id'],'category':'付款','severity':'高','title':bill['supplier']+'采购付款逾期','detail':f"商品 {bill['sku']}，截止 {bill['due']}，未付 {(bill['amount']-bill['paid'])/100:.2f} 元。",'target':'payables'})
        for budget in expenses.budget_rows(con):
            if budget['month']==today.isoformat()[:7] and budget['actual']>budget['amount']:
                alerts.append({'id':'budget:'+budget['month']+':'+budget['category'],'category':'费用','severity':'中','title':budget['category']+'费用超出本月预算','detail':f"月份 {budget['month']}，已登记 {budget['actual']/100:.2f} 元，预算 {budget['amount']/100:.2f} 元，超出 {(budget['actual']-budget['amount'])/100:.2f} 元。",'target':'expenses'})
    rank={'高':0,'中':1,'提示':2}
    alerts.sort(key=lambda a:rank[a['severity']])
    return {'as_of':today.isoformat(),'alerts':alerts}
