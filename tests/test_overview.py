from datetime import date
import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend import overview,inventory,sales,receivables,tasks,library

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):monkeypatch.setenv('DATALENS_DB',str(tmp_path/'overview.sqlite'))

def test_empty_overview_and_api_date():
    data=overview.listing(date(2026,10,9))
    assert data['sales']['shipped_amount']==0 and data['cash']['unpaid']==0
    assert data['stock']['items']==0 and data['customers']==[]
    with TestClient(app) as c:
        assert c.get('/api/overview?today=bad').status_code==422
        assert c.get('/api/overview?today=2026-10-09').json()==data

def test_cross_module_totals_and_date_boundaries():
    item=inventory.create_item('O','商品','件',5)['id']
    inventory.move(item,6,'期初')
    order=sales.create('O1','客户甲',item,2,10001,'2026-10-08')['id']
    sale=sales.fulfill(order)
    receivables.receive(sale['invoice_id'],10001,'首款','overview-pay')
    receivables.create('manual','客户乙',5000,'2026-10-09')
    inventory.create_order(item,'供应商',3,'2026-10-08')
    inventory.create_order(item,'供应商',3,'2026-10-09')
    tasks.save_task({'title':'逾期任务','owner':'','due':'2026-10-08','status':'待处理','notes':''})
    tasks.save_task({'title':'已完成','owner':'','due':'2026-10-08','status':'已完成','notes':''})
    library.create_project('项目','描述')
    data=overview.listing(date(2026,10,9))
    assert data['sales']=={'total':1,'pending':0,'fulfilled':1,'shipped_amount':20002}
    assert data['cash']=={'invoices':2,'amount':25002,'paid':10001,'unpaid':15001,'overdue':10001}
    assert data['stock']=={'items':1,'low':1,'empty':0}
    assert data['procurement']=={'pending':2,'overdue':1}
    assert data['work']=={'pending':1,'overdue':1}
    assert data['library']['projects']==1
    assert [c['customer'] for c in data['customers']]==['客户甲','客户乙']
    receivables.reverse('overview-pay','纠错')
    assert overview.listing(date(2026,10,9))['cash']['unpaid']==25002


def test_monthly_cash_utc_boundaries_reversals_and_zero_months():
    from backend.library import connect
    from backend import overview
    from datetime import date,datetime,timezone
    overview.listing(date(2026,1,1))
    stamp=lambda value:datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()
    with connect() as con:
        con.execute("INSERT INTO receivables VALUES ('i','monthly','客户',10000,0,'2026-02-01',0)")
        for key,amount,when in [('old',1,'2024-12-31'),('jan',1001,'2025-01-01'),('dec',2002,'2025-12-31T23:59:59'),('now',3003,'2026-01-01'),('future',4004,'2026-01-02')]:
            con.execute("INSERT INTO receipts VALUES (?,'i',?,'测试',?)",(key,amount,stamp(when)))
        con.execute("INSERT INTO receipt_reversals VALUES ('dec','误录',0)")
        con.execute("INSERT INTO expenses VALUES ('e','month-exp','软件',500,'2026-01-01','供应商',NULL,'说明',0)")
        rows=overview.monthly_rows(con,date(2026,1,1))
        assert len(rows)==12 and rows[0]['month']=='2025-02'
        assert rows[-2]['received']==0
        assert rows[-1]=={'month':'2026-01','received':3003,'supplier_paid':0,'expenses':500,'net':2503}
        assert all(r['net']==0 for r in rows[:-1])
        con.execute("INSERT INTO expense_voids VALUES ('e','误录',0)")
        assert overview.monthly_rows(con,date(2026,1,1))[-1]['net']==3003
