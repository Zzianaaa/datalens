import pytest
from backend import library
from backend.core import parse_csv

@pytest.fixture(autouse=True)
def isolated_db(tmp_path,monkeypatch):
    monkeypatch.setenv('DATALENS_DB',str(tmp_path/'vault.sqlite'))

def test_snapshot_persists_independently_and_archive_restores():
    project=library.create_project('销售分析','月报')
    ds=parse_csv(b'category,amount\na,10\n')
    asset=library.save_dataset('一月',project['id'],ds)
    ds['rows'][0][1]=999
    assert library.get_asset(asset['id'])['rows']==[['a',10]]
    library.archive(asset['id'],True)
    assert library.listing()['assets'][0]['archived']
    library.archive(asset['id'],False)
    assert not library.listing()['assets'][0]['archived']
    with pytest.raises(ValueError):library.save_dataset('x','nonexistent',ds)

def test_vault_api_restores_after_session_disappears():
    from fastapi.testclient import TestClient
    from backend.app import app,DATA
    DATA.clear()
    with TestClient(app) as c:
        p=c.post('/api/library/projects',json={'name':'项目','description':''}).json()
        d=c.post('/api/demo').json()
        a=c.post('/api/library/datasets/'+d['id'],json={'name':'订单','project_id':p['id']}).json()
        DATA.clear()
        restored=c.post('/api/library/assets/'+a['id']+'/open').json()
        assert restored['row_count']==10 and restored['id']!=d['id']
        assert c.get('/api/library').json()['assets'][0]['name']=='订单'
        assert c.post('/api/library/projects',json={'name':' ','description':''}).status_code==422
    DATA.clear()

def test_report_snapshot_validation():
    result={'columns':['类别','金额'],'rows':[['a',10]],'sql':'SELECT category,amount FROM data','mode':'sql','summary':'示例'}
    report=library.save_report('销售报告',None,'按类别分析',result)
    result['rows'][0][1]=999
    assert library.get_report(report['id'])['result']['rows'][0][1]==10
    assert library.listing()['reports'][0]['title']=='销售报告'
    with pytest.raises(ValueError):library.save_report('bad',None,'x',{'columns':['a'],'rows':[[1,2]]})
