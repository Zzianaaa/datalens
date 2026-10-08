from backend.browse import browse_dataset
from backend.core import parse_csv
from fastapi.testclient import TestClient
from backend.app import app, DATA


def test_search_sort_and_pagination():
    ds = parse_csv(b'name,amount\nAlice,10\nbob,2\nALICE,\n')
    p = browse_dataset(ds, page=99, page_size=1, search='alice', sort_by=1, descending=True)
    assert p['total'] == 2 and p['page'] == 2
    assert p['rows'] == [['ALICE', None]]
    assert browse_dataset(ds, sort_by=1)['rows'][0] == ['bob', 2]
    assert browse_dataset(ds, search="%'")['total'] == 0


def test_browse_endpoint_bounds():
    DATA.clear()
    with TestClient(app) as c:
        d = c.post('/api/demo').json()['id']
        r = c.get(f'/api/datasets/{d}/rows?page_size=3&search=keyboard')
        assert r.status_code == 200 and r.json()['total'] == 3
        assert c.get(f'/api/datasets/{d}/rows?page_size=101').status_code == 422
        assert c.get(f'/api/datasets/{d}/rows?sort_by=99').status_code == 400
        assert c.get('/api/datasets/nope/rows').status_code == 404
    DATA.clear()
