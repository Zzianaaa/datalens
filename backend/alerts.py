"""Deterministic, read-only cross-module business alerts."""
from datetime import date
from .library import connect
from . import inventory, tasks, receivables, payables, expenses, sales


def cash_checks(con):
    rows=[]
    for table,flows,reversals,foreign,reverse_key,target,label in [
        ('receivables','receipts','receipt_reversals','receivable_id','receipt_id','cash','回款'),
        ('payables','payments','payment_reversals','payable_id','payment_id','payables','付款')]:
        query=f"SELECT d.id,d.amount,d.paid,COALESCE(SUM(CASE WHEN v.{reverse_key} IS NULL THEN r.amount ELSE 0 END),0) AS effective FROM {table} d LEFT JOIN {flows} r ON r.{foreign}=d.id LEFT JOIN {reversals} v ON v.{reverse_key}=r.id GROUP BY d.id ORDER BY d.id"
        for record in con.execute(query):
            row=dict(record)
            row.update(target=target,label=label,difference=row['paid']-row['effective'])
            row['valid']=row['difference']==0 and 0<=row['paid']<=row['amount'] and 0<=row['effective']<=row['amount']
            rows.append(row)
    return rows


def listing(today: date):
    alerts=[]
    with connect() as con:
        sales.initialize(con)
        tasks.initialize(con)
        receivables.initialize(con)
        payables.initialize(con)
        expenses.initialize(con)
        con.execute('BEGIN')
        checks=cash_checks(con)
        for row in checks:
            if not row['valid']:
                alerts.append({'id':'cash-ledger:'+row['target']+':'+row['id'],'category':'对账','severity':'高','title':row['label']+'单据与有效流水不一致','detail':f"单据 {row['id']}，总额 {row['amount']/100:.2f} 元，已收/已付余额 {row['paid']/100:.2f} 元，有效流水 {row['effective']/100:.2f} 元，差异 {row['difference']/100:.2f} 元。已冲销流水剔除；同时检查金额是否超出单据总额。请核查原记录，系统不自动调整余额。",'target':row['target']})
        for item in con.execute('SELECT * FROM inventory_items ORDER BY sku'):
            pending=con.execute("SELECT COALESCE(SUM(ordered-received),0) FROM purchase_orders WHERE item_id=? AND status='open'",(item['id'],)).fetchone()[0]
            if item['quantity']<=item['reorder_level']:
                short=max(0,item['reorder_level']-item['quantity'])
                alerts.append({'id':'stock:'+item['id'],'category':'库存','severity':'高' if item['quantity']==0 else '中','title':item['name']+'库存达到补货阈值','detail':f"现有 {item['quantity']} {item['unit']}，阈值 {item['reorder_level']}，待到货 {pending}；考虑待到货后的缺口 {max(0,short-pending)}。",'target':'inventory'})
        for row in inventory.ledger_rows(con):
            if row['difference']:
                alerts.append({'id':'stock-ledger:'+row['id'],'category':'对账','severity':'高','title':row['sku']+'库存与流水不一致','detail':f"库存现量 {row['quantity']} {row['unit']}，全部流水净额 {row['ledger_quantity']}，差异 {row['difference']}。请核查原始记录；系统不会自动改写库存。",'target':'inventory'})
        for row in sales.fulfillment_rows(con):
            if row['shortage']:
                alerts.append({'id':'fulfillment:'+row['item_id'],'category':'履约','severity':'高','title':row['sku']+'待履约订单缺货','detail':f"{row['orders']} 张未完成订单需发 {row['demand']} {row['unit']}，现有 {row['stock']}，当前缺货 {row['shortage']}；采购待到货 {row['incoming']}，考虑待到货后的采购缺口 {row['purchase_gap']}。库存未预占，待到货不能立即发货。",'target':'inventory','secondary_target':'sales'})
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
    return {'as_of':today.isoformat(),'alerts':alerts,'cash_audit':{'checked':len(checks),'inconsistent':sum(not r['valid'] for r in checks)}}
