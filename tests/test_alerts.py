from datetime import date
import pytest
from backend import alerts, inventory, tasks
from backend.app import app
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):monkeypatch.setenv('DATALENS_DB',str(tmp_path/'alerts.sqlite'))

def test_alerts_change_with_business_state():
    key=inventory.create_item('A','商品','件',5)['id']
    order=inventory.create_order(key,'供应商',8)['id']
    task={'title':'核对','owner':'','due':'2026-10-08','status':'进行中','notes':''}
    t=tasks.save_task(task)['id']
    tasks.save_task({**task,'title':'完成任务','status':'已完成'})
    tasks.save_task({**task,'title':'当天任务','due':'2026-10-09'})
    g=tasks.save_goal({**task,'title':'销售目标','unit':'元','target':100,'current':20})['id']
    data=alerts.listing(date(2026,10,9))['alerts']
    assert len(data)==4
    stock=next(a for a in data if a['category']=='库存')
    assert '待到货 8' in stock['detail'] and '缺口 0' in stock['detail']
    assert stock['severity']=='高'
    inventory.receive_order(order,8,'receipt-1')
    tasks.save_task({**task,'status':'已完成'},t)
    tasks.save_goal({**task,'title':'销售目标','unit':'元','target':100,'current':100},g)
    assert alerts.listing(date(2026,10,9))['alerts']==[]

def test_alerts_date_api_and_empty():
    with TestClient(app) as c:
        assert c.get('/api/alerts?today=bad').status_code==422
        assert c.get('/api/alerts?today=2026-10-09').json()=={'as_of':'2026-10-09','alerts':[],'cash_audit':{'checked':0,'inconsistent':0}}

def test_purchase_due_boundaries_and_receiving():
    item=inventory.create_item('DUE','交期商品','件',0)['id']
    keys=[inventory.create_order(item,'供应商',2,due)['id'] for due in ['2026-10-08','2026-10-09','2026-10-10','']]
    def purchases():return {a['id'].split(':',1)[1]:a for a in alerts.listing(date(2026,10,9))['alerts'] if a['category']=='采购'}
    assert [purchases()[k]['severity'] for k in keys]==['高','提示','提示','提示']
    inventory.receive_order(keys[0],1,'partial-due')
    assert '剩余 1' in purchases()[keys[0]]['detail']
    inventory.receive_order(keys[0],1,'final-due')
    inventory.cancel_order(keys[1])
    assert keys[0] not in purchases() and keys[1] not in purchases()

def test_purchase_due_api_validation():
    item=inventory.create_item('API-DUE','日期商品','件',0)['id']
    with TestClient(app) as c:
        body={'item_id':item,'supplier':'供应商','quantity':1}
        for due in ['2026-02-30','20261009','2026-1-01']:
            assert c.post('/api/inventory/orders',json={**body,'due':due}).status_code==422
        assert c.post('/api/inventory/orders',json={**body,'due':'2026-10-09'}).status_code==200
        assert inventory.listing()['orders'][0]['due']=='2026-10-09'

def test_legacy_purchase_schema_migration():
    from backend.library import connect
    with connect() as con:
        con.execute("CREATE TABLE purchase_orders (id TEXT PRIMARY KEY,item_id TEXT,supplier TEXT,ordered INTEGER,received INTEGER DEFAULT 0,status TEXT DEFAULT 'open',created REAL)")
        con.execute("INSERT INTO purchase_orders VALUES ('legacy','item','供应商',3,1,'open',0)")
    with connect() as con:
        inventory.initialize(con)
        inventory.initialize(con)
        row=con.execute("SELECT * FROM purchase_orders WHERE id='legacy'").fetchone()
        assert row['due']=='' and row['ordered']==3 and row['received']==1
        assert row['unit_cost']==0 and row['payment_due']==''


def test_cash_audit_effective_flows_reversals_and_corrupt_balances():
    from backend import receivables,payables
    from backend.library import connect
    day=date(2026,10,10)
    key=receivables.create('AUDIT','客户',1000,'2026-10-20')['id']
    receivables.receive(key,500,'回款','cash-audit')
    item=inventory.create_item('PAY','商品','件',0)['id']
    order=inventory.create_order(item,'供应商',1,'2026-10-10',1000,'2026-10-20')['id']
    inventory.receive_order(order,1,'pay-audit-receipt')
    bill=payables.listing()['bills'][0]['id']
    payables.pay(bill,300,'付款','pay-audit')
    assert alerts.listing(day)['cash_audit']=={'checked':2,'inconsistent':0}
    receivables.reverse('cash-audit','误录')
    payables.reverse('pay-audit','误录')
    assert alerts.listing(day)['cash_audit']['inconsistent']==0
    with connect() as con:
        con.execute('UPDATE receivables SET paid=1 WHERE id=?',(key,))
        con.execute('UPDATE payables SET paid=1001 WHERE id=?',(bill,))
    data=alerts.listing(day)
    assert data['cash_audit']=={'checked':2,'inconsistent':2}
    issues=[a for a in data['alerts'] if a['category']=='对账']
    assert {a['target'] for a in issues}=={'cash','payables'}
    with connect() as con:
        assert con.execute('SELECT paid FROM receivables WHERE id=?',(key,)).fetchone()[0]==1
        con.execute('UPDATE receivables SET paid=0 WHERE id=?',(key,))
        con.execute('UPDATE payables SET paid=0 WHERE id=?',(bill,))
    assert alerts.listing(day)['cash_audit']['inconsistent']==0


def test_upcoming_cash_deadline_boundaries_and_settlement():
    from backend import receivables,payables
    from datetime import timedelta
    today=date(2026,10,10)
    ids=[receivables.create('UP-'+str(n),'客户',1001,(today+timedelta(days=n)).isoformat())['id'] for n in [-1,0,1,7,8]]
    item=inventory.create_item('UP-PAY','商品','件',0)['id']
    for n in [0,7,8]:
        order=inventory.create_order(item,'供应商'+str(n),1,'',2001,(today+timedelta(days=n)).isoformat())['id']
        inventory.receive_order(order,1,'up-pay-'+str(n))
    data=alerts.listing(today)['alerts']
    cash={a['id']:a for a in data if a['category']=='回款'}
    assert [cash['cash:'+key]['severity'] for key in ids[:4]]==['高','中','提示','提示']
    assert 'cash:'+ids[4] not in cash
    payments=[a for a in data if a['category']=='付款']
    assert len(payments)==2 and {a['severity'] for a in payments}=={'中','提示'}
    receivables.receive(ids[1],1001,'结清','up-settle')
    assert not any(a['id']=='cash:'+ids[1] for a in alerts.listing(today)['alerts'])
    receivables.reverse('up-settle','误录')
    assert any(a['id']=='cash:'+ids[1] for a in alerts.listing(today)['alerts'])
