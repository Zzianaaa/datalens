from datetime import date
import pytest
from fastapi.testclient import TestClient
from backend import expenses,library,overview
from backend.app import app

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):monkeypatch.setenv('DATALENS_DB',str(tmp_path/'expense.sqlite'))

def test_project_link_amount_idempotency_and_void_audit():
    project=library.create_project('营销项目','')['id']
    args=('expense-001','E001','营销',10001,'2026-10-09','渠道方',project,'推广费用')
    assert not expenses.create(*args)['duplicate']
    assert expenses.create(*args)['duplicate']
    assert expenses.listing()['expenses'][0]['project_name']=='营销项目'
    assert overview.listing(date(2026,10,9))['expenses']=={'records':1,'amount':10001}
    with pytest.raises(ValueError):expenses.create('expense-001','E001','营销',20001,'2026-10-09','渠道方',project,'推广费用')
    with pytest.raises(ValueError):expenses.create('expense-002',*args[1:])
    expenses.void('expense-001','误录')
    assert expenses.void('expense-001','误录')['duplicate']
    with pytest.raises(ValueError):expenses.void('expense-001','其他原因')
    assert len(expenses.listing()['expenses'])==1
    assert expenses.listing()['expenses'][0]['void_reason']=='误录'
    assert overview.listing(date(2026,10,9))['expenses']=={'records':0,'amount':0}

def test_expense_api_validation_and_unknown_project():
    body={'expense_id':'api-expense','reference':'E1','category':'软件','amount':999,'occurred':'2026-10-09','note':'订阅费'}
    with TestClient(app) as c:
        for change in [{'amount':1.2},{'amount':True},{'amount':0},{'occurred':'2026-02-30'},{'category':'未知'},{'note':' '}]:
            assert c.post('/api/expenses',json={**body,**change}).status_code==422
        assert c.post('/api/expenses',json={**body,'project_id':'missing'}).status_code==400
        assert c.post('/api/expenses',json=body).status_code==200
        assert c.get('/api/expenses').json()['expenses'][0]['amount']==999
        assert c.post('/api/expenses/api-expense/void',json={'reason':'误录'}).status_code==200
        assert c.post('/api/expenses/missing/void',json={'reason':'误录'}).status_code==404
