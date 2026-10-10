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

@pytest.mark.parametrize('kind',['project','asset','report'])
def test_concurrent_vault_saves_cannot_exceed_capacity(kind):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    with library.connect() as con:
        if kind=='project':
            con.executemany('INSERT INTO projects VALUES (?,?,?,?)',[(str(i),'项目','',0) for i in range(49)])
        elif kind=='asset':
            con.executemany('INSERT INTO assets VALUES (?,?,?,?,?,?)',[(str(i),'快照',None,'{}',0,0) for i in range(99)])
        else:
            con.executemany('INSERT INTO reports VALUES (?,?,?,?,?)',[(str(i),'报告',None,'{}',0) for i in range(99)])
    barrier=threading.Barrier(2)
    def save():
        barrier.wait()
        try:
            if kind=='project':library.create_project('并发项目','')
            elif kind=='asset':library.save_dataset('并发快照',None,parse_csv(b'a\n1\n'))
            else:library.save_report('并发报告',None,'问题',{'columns':['a'],'rows':[[1]]})
            return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:save(),range(2)))
    assert sorted(results)==[False,True]
    table={'project':'projects','asset':'assets','report':'reports'}[kind]
    with library.connect() as con:assert con.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==(50 if kind=='project' else 100)

@pytest.mark.parametrize('result',[None,[],{'columns':[],'rows':[]},{'columns':[1],'rows':[[1]]},{'columns':[' '],'rows':[[1]]},{'columns':['a'],'rows':[[{'nested':1}]]},{'columns':['a'],'rows':[[[1]]]}])
def test_report_invalid_shapes_are_rejected_without_saving(result):
    with pytest.raises(ValueError):library.save_report('无效报告',None,'问题',result)
    assert library.listing()['reports']==[]

def test_report_scalar_cells_round_trip():
    result={'columns':['文本','数字','布尔','空值'],'rows':[['示例',10.01,True,None]]}
    key=library.save_report('合法报告',None,'问题',result)['id']
    assert library.get_report(key)['result']==result
