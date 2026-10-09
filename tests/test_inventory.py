import pytest
from backend import inventory
from fastapi.testclient import TestClient
from backend.app import app

@pytest.fixture(autouse=True)
def db(tmp_path,monkeypatch):monkeypatch.setenv('DATALENS_DB',str(tmp_path/'stock.sqlite'))

def test_ledger_transaction_rollback_and_duplicate_sku():
    key=inventory.create_item('A','商品','件',5)['id']
    assert inventory.move(key,10,'采购入库')['quantity']==10
    with pytest.raises(ValueError):inventory.move(key,-11,'销售出库')
    assert inventory.listing()['items'][0]['quantity']==10
    assert len(inventory.listing()['movements'])==1
    assert inventory.move(key,-7,'销售出库')['quantity']==3
    with pytest.raises(ValueError):inventory.create_item('A','重复','件',1)

def test_inventory_api_validation():
    with TestClient(app) as c:
        key=c.post('/api/inventory/items',json={'sku':'B','name':'商品'}).json()['id']
        assert c.post('/api/inventory/movements',json={'item_id':key,'delta':0,'reason':'零数量'}).status_code==422
        assert c.post('/api/inventory/movements',json={'item_id':key,'delta':1.5,'reason':'小数'}).status_code==422
        assert c.post('/api/inventory/movements',json={'item_id':key,'delta':-1,'reason':'库存不足'}).status_code==400
        assert c.post('/api/inventory/movements',json={'item_id':'missing','delta':1,'reason':'入库'}).status_code==404
