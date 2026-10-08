from backend.core import parse_csv
from backend.profile import profile_dataset


def test_profile_missing_duplicates_and_numeric():
    ds = parse_csv(b'category,amount\na,10\na,10\nb,30\nb,\n')
    p = profile_dataset(ds)
    assert p['duplicate_rows'] == 1
    assert p['missing_cells'] == 1
    assert p['columns'][0]['distinct'] == 2
    assert p['columns'][1]['missing_percent'] == 25
    assert p['columns'][1]['numeric'] == {'min': 10, 'max': 30, 'mean': 50/3, 'median': 10}


def test_profile_endpoint():
    from fastapi.testclient import TestClient
    from backend.app import app, DATA
    DATA.clear()
    with TestClient(app) as c:
        d = c.post('/api/upload', files={'file': ('test.csv', b'x,y\na,1\na,1\n')}).json()
        r = c.get('/api/datasets/'+d['id']+'/profile')
        assert r.status_code == 200
        assert r.json()['duplicate_rows'] == 1
        assert c.get('/api/datasets/missing/profile').status_code == 404
    DATA.clear()
