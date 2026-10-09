"""Deterministic, read-only cross-module business alerts."""
from datetime import date
from .library import connect
from . import inventory, tasks


def listing(today: date):
    alerts=[]
    with connect() as con:
        inventory.initialize(con)
        tasks.initialize(con)
        con.execute('BEGIN')
        for item in con.execute('SELECT * FROM inventory_items ORDER BY sku'):
            pending=con.execute("SELECT COALESCE(SUM(ordered-received),0) FROM purchase_orders WHERE item_id=? AND status='open'",(item['id'],)).fetchone()[0]
            if item['quantity']<=item['reorder_level']:
                short=max(0,item['reorder_level']-item['quantity'])
                alerts.append({'id':'stock:'+item['id'],'category':'库存','severity':'高' if item['quantity']==0 else '中','title':item['name']+'库存达到补货阈值','detail':f"现有 {item['quantity']} {item['unit']}，阈值 {item['reorder_level']}，待到货 {pending}；考虑待到货后的缺口 {max(0,short-pending)}。",'target':'inventory'})
        for order in con.execute("SELECT p.*,i.sku FROM purchase_orders p JOIN inventory_items i ON i.id=p.item_id WHERE p.status='open' ORDER BY p.created"):
            alerts.append({'id':'purchase:'+order['id'],'category':'采购','severity':'提示','title':order['sku']+'有待到货采购','detail':f"供应商 {order['supplier']}，剩余 {order['ordered']-order['received']}；请核对实际交付安排。",'target':'inventory'})
        for task in con.execute("SELECT * FROM tasks WHERE due<>'' AND status NOT IN ('已完成','已归档') ORDER BY due"):
            if task['due']<today.isoformat():
                alerts.append({'id':'task:'+task['id'],'category':'任务','severity':'高','title':task['title']+'已逾期','detail':f"截止 {task['due']}，负责人 {task['owner'] or '未指定'}，状态 {task['status']}。",'target':'work'})
        for goal in con.execute("SELECT * FROM goals WHERE due<>'' AND current<target ORDER BY due"):
            if goal['due']<today.isoformat():
                alerts.append({'id':'goal:'+goal['id'],'category':'目标','severity':'中','title':goal['title']+'到期未达标','detail':f"截止 {goal['due']}，当前 {goal['current']:g} / {goal['target']:g} {goal['unit']}；目标数据由用户手工维护。",'target':'work'})
    rank={'高':0,'中':1,'提示':2}
    alerts.sort(key=lambda a:rank[a['severity']])
    return {'as_of':today.isoformat(),'alerts':alerts}
