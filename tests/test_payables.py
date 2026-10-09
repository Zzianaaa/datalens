from datetime import date
import pytest
from fastapi.testclient import TestClient
from backend import inventory,payables,overview,alerts
from backend.app import app

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):monkeypatch.setenv('DATALENS_DB',str(tmp_path/'payables.sqlite'))

def order():
    item=inventory.create_item('COST','成本商品','件',1)['id']
    return item,inventory.create_order(item,'供应商甲',3,'2026-10-10',10001,'2026-10-08')['id']

def test_partial_receipts_create_exact_payables_and_keep_cancelled_cost():
    item,key=order()
    assert payables.listing()['bills']==[]
    inventory.receive_order(key,1,'cost-first')
    inventory.receive_order(key,1,'cost-first')
    inventory.receive_order(key,1,'cost-second')
    inventory.cancel_order(key)
    bills=payables.listing()['bills']
    assert len(bills)==2 and sum(b['amount'] for b in bills)==20002
    assert inventory.listing()['items'][0]['quantity']==2
    assert all(b['due']=='2026-10-08' and b['supplier']=='供应商甲' for b in bills)
    assert overview.listing(date(2026,10,9))['payables']['unpaid']==20002
    assert len([a for a in alerts.listing(date(2026,10,9))['alerts'] if a['category']=='付款'])==2

def test_unknown_cost_does_not_create_zero_liability():
    item=inventory.create_item('OLD','历史商品','件',0)['id']
    key=inventory.create_order(item,'供应商',2)['id']
    inventory.receive_order(key,2,'no-cost-receipt')
    assert payables.listing()['bills']==[]
    assert inventory.listing()['orders'][0]['unit_cost']==0

def test_payment_idempotency_overpay_reversal_and_alert_clear():
    item,key=order();inventory.receive_order(key,1,'cost-payment')
    bill=payables.listing()['bills'][0]['id']
    assert payables.pay(bill,4000,'首款','payment-001')['paid']==4000
    assert payables.pay(bill,4000,'首款','payment-001')['duplicate']
    with pytest.raises(ValueError):payables.pay(bill,4001,'首款','payment-001')
    with pytest.raises(ValueError):payables.pay(bill,6002,'多付','payment-over')
    assert payables.listing()['bills'][0]['paid']==4000
    payables.pay(bill,6001,'尾款','payment-002')
    assert not [a for a in alerts.listing(date(2026,10,9))['alerts'] if a['category']=='付款']
    payables.reverse('payment-001','误录')
    assert payables.reverse('payment-001','误录')['duplicate']
    with pytest.raises(ValueError):payables.reverse('payment-001','改说明')
    assert payables.listing()['bills'][0]['paid']==6001
    assert len(payables.listing()['payments'])==2
    assert overview.listing(date(2026,10,9))['payables']['unpaid']==4000

def test_priced_purchase_validation_and_payment_api():
    item=inventory.create_item('API','商品','件',0)['id']
    body={'item_id':item,'supplier':'供应商','quantity':2,'unit_cost':1234,'payment_due':'2026-10-09'}
    with TestClient(app) as c:
        assert c.post('/api/inventory/orders',json={**body,'payment_due':''}).status_code==400
        assert c.post('/api/inventory/orders',json={**body,'unit_cost':True}).status_code==422
        assert c.post('/api/inventory/orders',json={**body,'payment_due':'2026-02-30'}).status_code==422
        assert c.post('/api/inventory/orders',json={**body,'unit_cost':100000000000}).status_code==400
        key=c.post('/api/inventory/orders',json=body).json()['id']
        inventory.receive_order(key,2,'api-cost-receipt')
        bill=payables.listing()['bills'][0]['id']
        pay={'amount':100,'note':'付款','payment_id':'api-payment'}
        assert c.post('/api/payables/'+bill+'/pay',json={**pay,'amount':1.2}).status_code==422
        assert c.post('/api/payables/'+bill+'/pay',json=pay).status_code==200
        assert c.post('/api/payments/api-payment/reverse',json={'reason':'误录'}).status_code==200
        assert c.post('/api/payables/missing/pay',json={**pay,'payment_id':'missing-payment'}).status_code==404
        assert c.get('/api/payables').status_code==200
    assert [a['severity'] for a in alerts.listing(date(2026,10,9))['alerts'] if a['category']=='付款']==['中']


def test_payable_capacity_failure_rolls_back_stock_and_receipt():
    from backend.library import connect
    item,key=order()
    with connect() as con:
        payables.initialize(con)
        con.executemany('INSERT INTO purchase_receipts VALUES (?,?,?)',[(f'limit-{n}',key,1) for n in range(500)])
        con.executemany('INSERT INTO payables(id,receipt_id,amount,due,created) VALUES (?,?,?,?,?)',[(f'bill-{n}',f'limit-{n}',1,'2026-10-09',0) for n in range(500)])
    with pytest.raises(ValueError,match='上限'):inventory.receive_order(key,1,'capacity-receipt')
    assert inventory.listing()['items'][0]['quantity']==0
    assert inventory.listing()['orders'][0]['received']==0
    with connect() as con:
        assert not con.execute("SELECT 1 FROM purchase_receipts WHERE id='capacity-receipt'").fetchone()


def test_concurrent_legacy_schema_migration():
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from backend.library import connect
    with connect() as con:
        con.execute("CREATE TABLE purchase_orders (id TEXT PRIMARY KEY,item_id TEXT,supplier TEXT,ordered INTEGER,received INTEGER DEFAULT 0,status TEXT DEFAULT 'open',created REAL,due TEXT DEFAULT '')")
        con.execute("INSERT INTO purchase_orders VALUES ('legacy','item','供应商',2,1,'open',0,'')")
    barrier=threading.Barrier(6)
    def migrate(n):
        barrier.wait(timeout=5)
        with connect() as con:
            inventory.initialize(con)
            row=con.execute("SELECT * FROM purchase_orders WHERE id='legacy'").fetchone()
            assert row['received']==1 and row['unit_cost']==0 and row['payment_due']==''
    with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(migrate,range(6)))
