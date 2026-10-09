import pytest
from backend import receivables
from backend.app import app
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):monkeypatch.setenv('DATALENS_DB',str(tmp_path/'cash.sqlite'))

def test_partial_receipts_are_atomic_and_idempotent():
    key=receivables.create('INV-1','示例客户',10001,'2026-10-08')['id']
    receivables.receive(key,4000,'首款','receipt-1')
    assert receivables.receive(key,4000,'首款','receipt-1')['duplicate']
    with pytest.raises(ValueError):receivables.receive(key,6002,'超收','receipt-2')
    with pytest.raises(ValueError):receivables.receive(key,4001,'首款','receipt-1')
    assert receivables.listing()['invoices'][0]['paid']==4000
    assert len(receivables.listing()['receipts'])==1
    receivables.receive(key,6001,'尾款','receipt-3')
    assert receivables.listing()['invoices'][0]['paid']==10001
    with pytest.raises(ValueError):receivables.create('INV-1','客户',1,'2026-10-08')

def test_api_requires_cents_and_valid_date():
    with TestClient(app) as c:
        assert c.post('/api/receivables',json={'reference':'A','customer':'B','amount':1.5,'due':'2026-10-09'}).status_code==422
        assert c.post('/api/receivables',json={'reference':'A','customer':'B','amount':100,'due':'invalid'}).status_code==422
        assert c.post('/api/receivables/missing/receive',json={'amount':100,'note':'到账','receipt_id':'receipt-1'}).status_code==404


def test_cash_alert_clears_after_settlement():
    from backend import alerts
    from datetime import date
    key=receivables.create('OVERDUE','示例客户',10001,'2026-10-08')['id']
    data=alerts.listing(date(2026,10,9))['alerts']
    assert data[0]['category']=='回款' and '100.01 元' in data[0]['detail']
    assert alerts.listing(date(2026,10,8))['alerts']==[]
    receivables.receive(key,10001,'全款','receipt-1')
    assert alerts.listing(date(2026,10,9))['alerts']==[]
