from backend.core import parse_csv
from backend.operations import clean_dataset,business_dashboard
import pytest


def test_clean_copy_does_not_change_source():
    ds=parse_csv(b'category,amount\n a ,10\na,10\nb,\n')
    cleaned,stats=clean_dataset(ds,True,True,True)
    assert cleaned['rows']==[['a',10]]
    assert len(ds['rows'])==3 and ds['rows'][0][0]==' a '
    assert stats['removed_rows']==2


def test_dashboard_explicit_status_and_invalid_dates():
    ds=parse_csv(b'date,category,amount,status\n2026-01-01,a,10,completed\nbad,b,20,completed\n2026-02-01,a,90,returned\n')
    r=business_dashboard(ds,'amount','category','date','status','completed')
    assert r['revenue']==30 and r['row_count']==2 and r['average_amount']==15
    assert r['invalid_date_rows']==1 and r['trend']['rows']==[('2026-01',10)]
    with pytest.raises(ValueError):business_dashboard(ds,'category','amount')


def test_clean_empty_rejected():
    ds=parse_csv(b'x,y\na,\n')
    with pytest.raises(ValueError):clean_dataset(ds,drop_missing=True)

def test_operations_api_preserves_original():
    from fastapi.testclient import TestClient
    from backend.app import app,DATA
    DATA.clear()
    with TestClient(app) as c:
        source=c.post('/api/upload',files={'file':('a.csv',b'category,amount\na,10\na,10\n')}).json()
        path='/api/datasets/'+source['id']
        assert c.post(path+'/clean',json={'deduplicate':True}).json()['report']['after_rows']==1
        cleaned=c.post(path+'/clean',json={'deduplicate':True,'preview':False}).json()['dataset']
        assert cleaned['id']!=source['id'] and c.get(path).json()['row_count']==2
        assert c.post(path+'/dashboard',json={'amount':'amount','category':'category'}).json()['revenue']==20
        assert c.post(path+'/dashboard',json={'amount':'bad','category':'category'}).status_code==400
    DATA.clear()
