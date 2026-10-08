import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend.core import parse_csv,validate_sql,run_query
client=TestClient(app)
@pytest.mark.parametrize('raw',[b'',b'a,a\n1,2',b'a\n',b'a,b\n1,2,3',b' ,b\n1,2'])
def test_bad_csv(raw):
    with pytest.raises(ValueError):parse_csv(raw)
@pytest.mark.parametrize('sql',["DELETE FROM data","SELECT * FROM read_csv('/etc/passwd')","SELECT * FROM data; DROP TABLE data","SELECT * FROM other","SELECT * FROM data JOIN data d ON true","SELECT (SELECT 1) FROM data","SELECT getenv('HOME') FROM data"])
def test_blocked(sql):
    with pytest.raises(ValueError):validate_sql(sql)
def test_utf_and_missing():
    d=parse_csv('名称,金额\n测试,5\n其他,\n'.encode('gb18030'))
    assert d['encoding']=='gb18030' and d['missing']==1 and d['types']==['VARCHAR','DOUBLE']
def test_demo_results():
    d=client.post('/api/demo').json()
    r=client.post('/api/ask',json={'dataset_id':d['id'],'question':'每月销售额'})
    assert r.status_code==200,r.text
    assert r.json()['rows']==[['2026-01',160.0],['2026-02',335.0],['2026-03',310.0]]
    r=client.post('/api/ask',json={'dataset_id':d['id'],'question':'各类别销售额'})
    assert r.json()['rows']==[['Electronics',600.0],['Lifestyle',105.0],['Stationery',100.0]]
def test_unknown_and_missing():
    d=client.post('/api/upload',files={'file':('x.csv',b'a,b\n1,2','text/csv')}).json()
    assert client.post('/api/ask',json={'dataset_id':d['id'],'question':'每月销售额'}).status_code==400
    assert client.post('/api/ask',json={'dataset_id':'none','question':'x'}).status_code==404
    assert client.post('/api/upload',files={'file':('x.txt',b'x')}).status_code==400

def test_limit():
    ds=parse_csv(('a\n'+'1\n'*250).encode())
    assert len(run_query(ds,'SELECT * FROM data')['rows'])==200

def test_timeout():
    with pytest.raises(ValueError,match='超时'):run_query(parse_csv(b'a\n1'), 'SELECT * FROM data',timeout=.001)

def test_preserve_top_five_limit():
    ds=parse_csv(("a\n"+"1\n"*20).encode())
    assert len(run_query(ds,"SELECT * FROM data LIMIT 5")["rows"])==5

@pytest.fixture(autouse=True)
def clear_datasets():
    from backend.app import DATA
    DATA.clear()
    yield
    DATA.clear()

def test_dataset_lifecycle():
    d=client.post('/api/demo').json()
    assert client.get('/api/datasets/'+d['id']).json()['row_count']==10
    assert client.delete('/api/datasets/'+d['id']).json()['deleted']
    assert client.get('/api/datasets/'+d['id']).status_code==404

def test_capacity_and_expiry():
    from backend.app import DATA
    for _ in range(10): assert client.post('/api/demo').status_code==200
    assert client.post('/api/demo').status_code==400
    for k,(t,ds) in list(DATA.items()): DATA[k]=(t-4000,ds)
    assert client.post('/api/demo').status_code==200

def test_manual_sql():
    d=client.post('/api/demo').json()
    r=client.post('/api/query',json={'dataset_id':d['id'],'sql':'SELECT COUNT(*) AS count FROM data'})
    assert r.json()['rows']==[[10]]
    assert client.post('/api/query',json={'dataset_id':d['id'],'sql':'DELETE FROM data'}).status_code==400

def test_ai_integration(monkeypatch):
    import importlib
    module=importlib.import_module('backend.app')
    monkeypatch.setattr(module,'generate_sql',lambda q,ds:('SELECT COUNT(*) AS count FROM data',{'model':'mock'}))
    d=client.post('/api/demo').json()
    r=client.post('/api/ask',json={'dataset_id':d['id'],'question':'多少订单','mode':'ai'})
    assert r.json()['rows']==[[10]] and r.json()['model_info']['model']=='mock'

def test_ai_unsafe_output(monkeypatch):
    import importlib
    module=importlib.import_module('backend.app')
    monkeypatch.setattr(module,'generate_sql',lambda q,ds:('DROP TABLE data',{}))
    d=client.post('/api/demo').json()
    assert client.post('/api/ask',json={'dataset_id':d['id'],'question':'x','mode':'ai'}).status_code==400

def test_invalid_mode_and_whitespace():
    d=client.post('/api/demo').json()
    assert client.post('/api/ask',json={'dataset_id':d['id'],'question':'x','mode':'fake'}).status_code==422
