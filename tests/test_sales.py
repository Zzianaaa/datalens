import pytest
from fastapi.testclient import TestClient
from backend import sales, inventory, receivables
from backend.app import app

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):monkeypatch.setenv('DATALENS_DB',str(tmp_path/'sales.sqlite'))

def setup_order(quantity=2):
    item=inventory.create_item('SELL','商品','件',1)['id']
    inventory.move(item,5,'期初入库')
    order=sales.create('SO-001','客户',item,quantity,10001,'2026-10-10')['id']
    return item,order

def test_fulfillment_links_stock_receivable_and_payment():
    item,order=setup_order()
    assert inventory.listing()['items'][0]['quantity']==5 and receivables.listing()['invoices']==[]
    result=sales.fulfill(order)
    assert inventory.listing()['items'][0]['quantity']==3
    assert inventory.listing()['movements'][0]['delta']==-2
    invoice=receivables.listing()['invoices'][0]
    assert (invoice['reference'],invoice['amount'],invoice['customer'])==('销售:SO-001',20002,'客户')
    assert sales.fulfill(order)=={'duplicate':True,'invoice_id':result['invoice_id']}
    assert len(inventory.listing()['movements'])==2 and len(receivables.listing()['invoices'])==1
    receivables.receive(invoice['id'],10001,'部分回款','sales-payment')
    assert sales.listing()['orders'][0]['paid']==10001
    with pytest.raises(ValueError):sales.cancel(order)

def test_stock_failure_leaves_all_ledgers_unchanged():
    item,order=setup_order(6)
    with pytest.raises(ValueError,match='库存不足'):sales.fulfill(order)
    assert inventory.listing()['items'][0]['quantity']==5
    assert len(inventory.listing()['movements'])==1
    assert sales.listing()['orders'][0]['status']=='draft'
    assert receivables.listing()['invoices']==[]

def test_invoice_conflict_rolls_back_and_cancel_is_idempotent():
    item,order=setup_order()
    receivables.create('销售:SO-001','客户',1,'2026-10-10')
    with pytest.raises(ValueError,match='已被使用'):sales.fulfill(order)
    assert inventory.listing()['items'][0]['quantity']==5
    assert sales.listing()['orders'][0]['invoice_id'] is None
    sales.cancel(order);sales.cancel(order)
    with pytest.raises(ValueError):sales.fulfill(order)
    assert sales.listing()['orders'][0]['status']=='cancelled'

def test_api_amount_dates_quantity_and_missing_records():
    item,order=setup_order()
    body={'reference':'SO-002','customer':'客户','item_id':item,'quantity':1,'unit_price':99,'due':'2026-10-10'}
    with TestClient(app) as c:
        for change in [{'quantity':1.5},{'quantity':True},{'unit_price':'100'},{'unit_price':0},{'due':'2026-02-30'}]:
            assert c.post('/api/sales',json={**body,**change}).status_code==422
        assert c.post('/api/sales',json={**body,'quantity':1000000,'unit_price':100000000000}).status_code==400
        assert c.post('/api/sales',json={**body,'reference':'SO-001'}).status_code==400
        assert c.post('/api/sales/missing/fulfill').status_code==404
        assert c.post('/api/sales',json=body).status_code==200
        assert c.get('/api/sales').status_code==200
