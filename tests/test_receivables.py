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


def test_reversal_preserves_ledger_and_reopens_balance():
    key=receivables.create('FIX','客户',10000,'2026-10-08')['id']
    receivables.receive(key,10000,'误录','receipt-1')
    assert not receivables.reverse('receipt-1','金额错误')['duplicate']
    assert receivables.reverse('receipt-1','金额错误')['duplicate']
    with pytest.raises(ValueError):receivables.reverse('receipt-1','另一说明')
    state=receivables.listing()
    assert state['invoices'][0]['paid']==0
    assert state['receipts'][0]['amount']==10000
    assert state['receipts'][0]['reversal_reason']=='金额错误'
    receivables.receive(key,4000,'正确回款','receipt-2')
    assert receivables.listing()['invoices'][0]['paid']==4000
    with TestClient(app) as c:
        assert c.post('/api/receipts/missing/reverse',json={'reason':'错误'}).status_code==404
        assert c.post('/api/receipts/receipt-2/reverse',json={'reason':'   '}).status_code==422


def test_collection_task_link_and_duplicate_prevention():
    from backend import tasks
    key=receivables.create('TASK','客户',10000,'2026-10-08')['id']
    first=receivables.followup('客户','负责人','2026-10-10')
    assert not first['existing']
    assert receivables.followup('客户','其他人','2026-10-11')['id']==first['id']
    task=tasks.listing()['tasks'][0]
    assert task['owner']=='负责人' and '100.00 元' in task['notes']
    tasks.save_task({**task,'status':'已完成'},first['id'])
    assert receivables.followup('客户','','2026-10-12')['id']!=first['id']
    receivables.receive(key,10000,'结清','receipt-1')
    with pytest.raises(ValueError):receivables.followup('客户','','2026-10-12')
