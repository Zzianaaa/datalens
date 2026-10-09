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

def basket():
    a=inventory.create_item('A','商品甲','件',0)['id']
    b=inventory.create_item('B','商品乙','件',0)['id']
    inventory.move(a,5,'期初');inventory.move(b,1,'期初')
    key=sales.create_basket('BASKET','客户',[{'item_id':a,'quantity':3,'unit_price':10001},{'item_id':b,'quantity':2,'unit_price':5001}],'2026-10-10')['id']
    lines={l['sku']:l['id'] for l in sales.listing()['orders'][0]['lines']}
    return a,b,key,lines

def test_multi_item_partial_shipments_payments_and_cancel_remainder():
    from datetime import date
    from backend import overview
    a,b,key,lines=basket()
    payload=[{'line_id':lines['A'],'quantity':1},{'line_id':lines['B'],'quantity':1}]
    first=sales.ship(key,payload,'shipment-first')
    assert sales.ship(key,list(reversed(payload)),'shipment-first')['duplicate']
    order=sales.listing()['orders'][0]
    assert order['status']=='partial' and order['shipped_amount']==15002 and order['ordered_amount']==40005
    assert overview.listing(date(2026,10,9))['sales']=={'total':1,'pending':1,'fulfilled':0,'shipped_amount':15002}
    receivables.receive(first['invoice_id'],5001,'首款','basket-payment')
    assert sales.listing()['orders'][0]['paid']==5001
    second=sales.ship(key,[{'line_id':lines['A'],'quantity':1}],'shipment-second')
    assert second['invoice_id']!=first['invoice_id']
    assert len(receivables.listing()['invoices'])==2
    sales.cancel(key)
    assert sales.listing()['orders'][0]['shipped_amount']==25003
    assert sales.listing()['orders'][0]['status']=='cancelled'
    assert overview.listing(date(2026,10,9))['sales']['shipped_amount']==25003
    with pytest.raises(ValueError):sales.ship(key,[{'line_id':lines['A'],'quantity':1}],'after-cancel')

def test_basket_stock_failure_rolls_back_every_line_and_no_over_ship():
    a,b,key,lines=basket()
    before={i['id']:i['quantity'] for i in inventory.listing()['items']}
    with pytest.raises(ValueError,match='库存不足'):sales.fulfill(key)
    assert {i['id']:i['quantity'] for i in inventory.listing()['items']}==before
    assert receivables.listing()['invoices']==[] and sales.listing()['shipments']==[]
    assert all(l['shipped']==0 for l in sales.listing()['orders'][0]['lines'])
    with pytest.raises(ValueError):sales.ship(key,[{'line_id':lines['A'],'quantity':4}],'over-ship')
    with pytest.raises(ValueError):sales.ship(key,[{'line_id':lines['A'],'quantity':1}]*2,'duplicate-lines')
    sales.ship(key,[{'line_id':lines['A'],'quantity':1}],'token-conflict')
    with pytest.raises(ValueError):sales.ship(key,[{'line_id':lines['A'],'quantity':2}],'token-conflict')
    inventory.move(b,1,'补货')
    last=sales.fulfill(key)
    assert sales.fulfill(key)=={'duplicate':True,'invoice_id':last['invoice_id']}
    assert sales.listing()['orders'][0]['status']=='fulfilled'
    assert sales.listing()['orders'][0]['shipped_amount']==40005

def test_legacy_migration_preserves_stock_invoice_and_paid():
    from backend.library import connect
    item=inventory.create_item('LEGACY','旧商品','件',0)['id']
    inventory.move(item,5,'旧库存')
    invoice=receivables.create('销售:OLD','旧客户',20002,'2026-10-09')['id']
    receivables.receive(invoice,10001,'旧首款','legacy-payment')
    with connect() as con:
        sales.initialize(con)
        con.execute('INSERT INTO sales_orders VALUES (?,?,?,?,?,?,?,?,?,?)',('old-order','OLD','旧客户',item,2,10001,'2026-10-09','fulfilled',invoice,0))
    for _ in range(2):
        order=sales.listing()['orders'][0]
        assert order['lines'][0]['shipped']==2 and order['paid']==10001 and order['shipped_amount']==20002
    assert inventory.listing()['items'][0]['quantity']==5
    assert len(receivables.listing()['invoices'])==1 and sales.listing()['shipments']==[]

def test_basket_api_rejects_invalid_lines_and_foreign_order_lines():
    a,b,key,lines=basket()
    with TestClient(app) as c:
        body={'reference':'API-BASKET','customer':'客户','due':'2026-10-10','lines':[{'item_id':a,'quantity':1,'unit_price':1}]}
        assert c.post('/api/sales/basket',json={**body,'lines':[]}).status_code==422
        assert c.post('/api/sales/basket',json={**body,'lines':body['lines']*2}).status_code==400
        assert c.post('/api/sales/'+key+'/ship',json={'shipment_id':'invalid-lines','lines':[{'line_id':'foreign','quantity':1}]}).status_code==400
        assert c.post('/api/sales/'+key+'/ship',json={'shipment_id':'float-quantity','lines':[{'line_id':lines['A'],'quantity':1.5}]}).status_code==422
        assert c.post('/api/sales/basket',json=body).status_code==200

def test_concurrent_shipments_cannot_oversell_stock():
    from concurrent.futures import ThreadPoolExecutor
    import threading
    item=inventory.create_item('ONE','最后一件','件',0)['id']
    inventory.move(item,1,'期初')
    keys=[sales.create(f'C{n}','客户',item,1,100,'2026-10-10')['id'] for n in range(2)]
    lines={o['id']:o['lines'][0]['id'] for o in sales.listing()['orders']}
    barrier=threading.Barrier(2)
    def post(n):
        barrier.wait(timeout=5)
        try:sales.ship(keys[n],[{'line_id':lines[keys[n]],'quantity':1}],f'concurrent-{n}');return 'success'
        except ValueError as exc:return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(post,range(2)))
    assert results.count('success')==1 and results.count('库存不足，请先补货')==1
    assert inventory.listing()['items'][0]['quantity']==0 and len(receivables.listing()['invoices'])==1

def test_receivable_capacity_failure_keeps_shipment_atomic():
    from backend.library import connect
    item,key=setup_order()
    line=sales.listing()['orders'][0]['lines'][0]['id']
    with connect() as con:
        con.executemany('INSERT INTO receivables(id,reference,customer,amount,due,created) VALUES (?,?,?,?,?,?)',[(f'cap-{n}',f'CAP{n}','客户',1,'2026-10-10',0) for n in range(500)])
    with pytest.raises(ValueError,match='上限'):sales.ship(key,[{'line_id':line,'quantity':1}],'capacity-shipment')
    assert inventory.listing()['items'][0]['quantity']==5
    assert sales.listing()['orders'][0]['lines'][0]['shipped']==0
    assert sales.listing()['shipments']==[]
