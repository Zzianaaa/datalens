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

@pytest.mark.parametrize('kind,limit',[('task',500),('goal',100)])
def test_concurrent_work_creation_respects_capacity(kind,limit):
    from backend import tasks
    from concurrent.futures import ThreadPoolExecutor
    import threading
    with tasks.connect() as con:
        tasks.initialize(con)
        if kind=='task':con.executemany('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)',[(str(i),None,'任务','','','待处理','',0) for i in range(limit-1)])
        else:con.executemany('INSERT INTO goals VALUES (?,?,?,?,?,?,?,?)',[(str(i),None,'目标','件',1,0,'',0) for i in range(limit-1)])
    barrier=threading.Barrier(2)
    def save(_):
        barrier.wait()
        try:
            if kind=='task':tasks.save_task({'title':'并发','owner':'','due':'','status':'待处理','notes':''})
            else:tasks.save_goal({'title':'并发','unit':'件','target':1,'current':0,'due':''})
            return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(save,range(2)))==[False,True]
    assert len(tasks.listing()['tasks' if kind=='task' else 'goals'])==limit

@pytest.mark.parametrize('kind,limit',[('task',500),('goal',100)])
def test_work_updates_at_capacity_preserve_creation_time(kind,limit):
    from backend import tasks
    with tasks.connect() as con:
        tasks.initialize(con)
        if kind=='task':con.executemany('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)',[(str(i),None,'任务','','','待处理','',123) for i in range(limit)])
        else:con.executemany('INSERT INTO goals VALUES (?,?,?,?,?,?,?,?)',[(str(i),None,'目标','件',10,0,'',123) for i in range(limit)])
    data={'title':'更新','owner':'负责人','due':'','status':'已完成','notes':'说明'} if kind=='task' else {'title':'更新','unit':'件','target':10,'current':5,'due':''}
    save=tasks.save_task if kind=='task' else tasks.save_goal
    with pytest.raises(ValueError):save(data)
    save(data,'0')
    rows=tasks.listing()['tasks' if kind=='task' else 'goals']
    assert len(rows)==limit
    row=next(r for r in rows if r['id']=='0')
    assert row['title']=='更新' and row['created']==123
    assert row['status']=='已完成' if kind=='task' else row['current']==5
