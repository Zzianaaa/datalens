import pytest
from backend import metrics
from fastapi.testclient import TestClient
from backend.app import app

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):monkeypatch.setenv('DATALENS_DB',str(tmp_path/'metrics.sqlite'))

def test_templates_persist_and_reject_unsafe_sql():
    key=metrics.save('记录数','每行作为一条记录','SELECT COUNT(*) AS 数量 FROM data')['id']
    assert metrics.listing()[0]['id']==key
    with pytest.raises(ValueError):metrics.save('删除','','DELETE FROM data')
    with pytest.raises(ValueError):metrics.save('外部','','SELECT * FROM read_csv_auto(\'secret.csv\')')
    assert len(metrics.listing())==1

def test_template_api():
    with TestClient(app) as c:
        assert c.post('/api/metrics',json={'name':'   ','sql':'SELECT * FROM data'}).status_code==422
        assert c.post('/api/metrics',json={'name':'预览','sql':'SELECT * FROM data LIMIT 5'}).status_code==200
        assert len(c.get('/api/metrics').json()['templates'])==1


def test_archive_restore_and_existing_schema_migration():
    from backend.library import connect
    with connect() as con:
        con.execute('CREATE TABLE metric_templates (id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,sql TEXT NOT NULL)')
        con.execute("INSERT INTO metric_templates VALUES ('old','旧口径','','SELECT COUNT(*) FROM data')")
    assert metrics.listing()[0]['archived']==0
    metrics.archive('old',True)
    assert metrics.listing()[0]['archived']==1
    metrics.archive('old',False)
    assert metrics.listing()[0]['sql']=='SELECT COUNT(*) FROM data'
    with TestClient(app) as c:
        assert c.put('/api/metrics/missing/archive',json={'archived':True}).status_code==404
        assert c.put('/api/metrics/old/archive',json={'archived':True}).status_code==200

def test_concurrent_template_saves_respect_capacity():
    from concurrent.futures import ThreadPoolExecutor
    import threading
    with metrics.connect() as con:
        metrics.initialize(con)
        con.executemany('INSERT INTO metric_templates VALUES (?,?,?,?,?)',[(str(i),'模板','','SELECT * FROM data',0) for i in range(99)])
    barrier=threading.Barrier(2)
    def save(_):
        barrier.wait()
        try:metrics.save('并发','','SELECT COUNT(*) FROM data');return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(save,range(2)))==[False,True]
    assert len(metrics.listing())==100
    metrics.archive('0',True);metrics.archive('0',False)
    assert next(r for r in metrics.listing() if r['id']=='0')['archived']==0
