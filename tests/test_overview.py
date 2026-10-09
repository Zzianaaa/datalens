from datetime import date
import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend import overview,inventory,sales,receivables,tasks,library

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):monkeypatch.setenv('DATALENS_DB',str(tmp_path/'overview.sqlite'))

def test_empty_overview_and_api_date():
    data=overview.listing(date(2026,10,9))
    assert data['sales']['shipped_amount']==0 and data['cash']['unpaid']==0
    assert data['stock']['items']==0 and data['customers']==[]
    with TestClient(app) as c:
        assert c.get('/api/overview?today=bad').status_code==422
        assert c.get('/api/overview?today=2026-10-09').json()==data

def test_cross_module_totals_and_date_boundaries():
    item=inventory.create_item('O','商品','件',5)['id']
    inventory.move(item,6,'期初')
    order=sales.create('O1','客户甲',item,2,10001,'2026-10-08')['id']
    sale=sales.fulfill(order)
    receivables.receive(sale['invoice_id'],10001,'首款','overview-pay')
    receivables.create('manual','客户乙',5000,'2026-10-09')
    inventory.create_order(item,'供应商',3,'2026-10-08')
    inventory.create_order(item,'供应商',3,'2026-10-09')
    tasks.save_task({'title':'逾期任务','owner':'','due':'2026-10-08','status':'待处理','notes':''})
    tasks.save_task({'title':'已完成','owner':'','due':'2026-10-08','status':'已完成','notes':''})
    library.create_project('项目','描述')
    data=overview.listing(date(2026,10,9))
    assert data['sales']=={'total':1,'pending':0,'fulfilled':1,'shipped_amount':20002}
    assert data['cash']=={'invoices':2,'amount':25002,'paid':10001,'unpaid':15001,'overdue':10001}
    assert data['stock']=={'items':1,'low':1,'empty':0}
    assert data['procurement']=={'pending':2,'overdue':1}
    assert data['work']=={'pending':1,'overdue':1}
    assert data['library']['projects']==1
    assert [c['customer'] for c in data['customers']]==['客户甲','客户乙']
    receivables.reverse('overview-pay','纠错')
    assert overview.listing(date(2026,10,9))['cash']['unpaid']==25002
