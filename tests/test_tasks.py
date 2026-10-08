import pytest
from fastapi.testclient import TestClient
from backend.app import app

@pytest.fixture(autouse=True)
def isolate(tmp_path,monkeypatch):monkeypatch.setenv('DATALENS_DB',str(tmp_path/'tasks.sqlite'))

def test_task_lifecycle_and_validation():
    with TestClient(app) as c:
        data={'title':'复核销售口径','due':'2026-12-01','status':'待处理','owner':'分析负责人','notes':''}
        key=c.post('/api/work/tasks',json=data).json()['id']
        assert c.put('/api/work/tasks/'+key,json={**data,'status':'已完成'}).status_code==200
        assert c.get('/api/work').json()['tasks'][0]['status']=='已完成'
        assert c.post('/api/work/tasks',json={**data,'due':'2026-02-31'}).status_code==422
        assert c.put('/api/work/tasks/missing',json=data).status_code==404
        assert c.post('/api/work/tasks',json={**data,'project_id':'missing'}).status_code==400

def test_goal_persists_progress():
    with TestClient(app) as c:
        data={'title':'季度销售目标','target':100000,'current':25000,'unit':'元','due':''}
        key=c.post('/api/work/goals',json=data).json()['id']
        assert c.put('/api/work/goals/'+key,json={**data,'current':50000}).status_code==200
        assert c.get('/api/work').json()['goals'][0]['current']==50000
        assert c.post('/api/work/goals',json={**data,'target':0}).status_code==422
