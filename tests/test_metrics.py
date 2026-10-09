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
