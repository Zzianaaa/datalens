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
        assert c.get('/api/alerts?today=2026-10-09').json()=={'as_of':'2026-10-09','alerts':[]}
