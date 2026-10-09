from datetime import date

import secrets
import threading
import time
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, UploadFile, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from .core import parse_csv, demo_sql, run_query, MAX_BYTES
from .model import generate_sql, model_config
from .profile import profile_dataset
from .browse import browse_dataset
from .operations import clean_dataset, business_dashboard
from . import library, tasks, inventory, alerts, metrics, receivables

app = FastAPI(title='DataLens API', version='0.12.0')
DATA = {}
LOCK = threading.Lock()
ROOT = Path(__file__).resolve().parents[1]
TTL = 3600

class Question(BaseModel):
    dataset_id: str
    question: str = Field(min_length=1, max_length=500)
    mode: Literal['demo', 'ai'] = 'demo'

class SQLQuery(BaseModel):
    dataset_id: str
    sql: str = Field(min_length=1, max_length=10000)

def describe(key, ds):
    return {
        'id': key, 'row_count': len(ds['rows']),
        'columns': [{'name': n, 'type': t, 'missing': sum(r[i] is None for r in ds['rows'])}
                    for i, (n, t) in enumerate(zip(ds['names'], ds['types']))],
        'preview': ds['rows'][:5], 'missing': ds['missing'], 'encoding': ds['encoding'],
    }

def get_dataset(key):
    with LOCK:
        entry = DATA.get(key)
        if entry and time.time() - entry[0] > TTL:
            del DATA[key]
            entry = None
    if not entry:
        raise HTTPException(404, '数据已过期，请重新上传')
    return entry[1]

def store(raw):
    return store_dataset(parse_csv(raw))

def store_dataset(ds, key=None):
    key = key or secrets.token_urlsafe(24)
    with LOCK:
        now = time.time()
        for k in list(DATA):
            if now - DATA[k][0] > TTL:
                del DATA[k]
        if len(DATA) >= 10 and key not in DATA:
            raise ValueError('已达到 10 份数据上限，请移除不用的数据或等待过期')
        DATA[key] = (now, ds)
    return describe(key, ds)

class CleanRequest(BaseModel):
    deduplicate: bool = False
    trim_text: bool = False
    drop_missing: bool = False
    preview: bool = True

class DashboardRequest(BaseModel):
    amount: str
    category: str
    date: str | None = None
    status: str | None = None
    status_value: str | None = None

@app.post('/api/datasets/{key}/clean')
def clean(key: str, body: CleanRequest):
    try:
        cleaned, report = clean_dataset(get_dataset(key), body.deduplicate, body.trim_text, body.drop_missing)
        return {'report':report,'preview':cleaned['rows'][:5]} if body.preview else {'report':report,'dataset':store_dataset(cleaned)}
    except ValueError as exc:
        raise HTTPException(400,str(exc))

@app.post('/api/datasets/{key}/dashboard')
def dashboard(key: str, body: DashboardRequest):
    try:
        return business_dashboard(get_dataset(key), **body.model_dump())
    except ValueError as exc:
        raise HTTPException(400,str(exc))

class ProjectRequest(BaseModel):
    name: str = Field(min_length=1,max_length=100,pattern=r'\S')
    description: str = Field(default='',max_length=1000)

class SaveRequest(BaseModel):
    name: str = Field(min_length=1,max_length=100,pattern=r'\S')
    project_id: str | None = None

class ArchiveRequest(BaseModel):
    archived: bool

@app.get('/api/library')
def list_library():
    return library.listing()

@app.post('/api/library/projects')
def add_project(body: ProjectRequest):
    try:
        return library.create_project(body.name.strip(),body.description)
    except ValueError as exc:
        raise HTTPException(400,str(exc))

@app.post('/api/library/datasets/{key}')
def save_to_library(key: str,body: SaveRequest):
    try:
        return library.save_dataset(body.name.strip(),body.project_id,get_dataset(key))
    except ValueError as exc:
        raise HTTPException(400,str(exc))

@app.post('/api/library/assets/{key}/open')
def open_saved(key: str):
    try:
        return store_dataset(library.get_asset(key),key='saved-'+key)
    except KeyError:
        raise HTTPException(404,'保存的数据不存在')
    except ValueError as exc:
        raise HTTPException(400,str(exc))

@app.patch('/api/library/assets/{key}')
def archive_saved(key: str,body: ArchiveRequest):
    try:
        library.archive(key,body.archived)
        return {'archived':body.archived}
    except KeyError:
        raise HTTPException(404,'保存的数据不存在')

class ReportRequest(BaseModel):
    title: str = Field(min_length=1,max_length=100,pattern=r'\S')
    project_id: str | None = None
    question: str = Field(max_length=10000)
    result: dict

@app.post('/api/library/reports')
def add_report(body: ReportRequest):
    try:
        return library.save_report(body.title.strip(),body.project_id,body.question,body.result)
    except (ValueError,TypeError) as exc:
        raise HTTPException(400,str(exc))

@app.get('/api/library/reports/{key}')
def read_report(key: str):
    try:
        return library.get_report(key)
    except KeyError:
        raise HTTPException(404,'报告不存在')

class TaskRequest(BaseModel):
    project_id: str | None = None
    title: str = Field(min_length=1,max_length=120,pattern=r'\S')
    owner: str = Field(default='',max_length=80)
    due: str = ''
    status: Literal['待处理','进行中','已完成','已归档'] = '待处理'
    notes: str = Field(default='',max_length=2000)

    @field_validator('due')
    @classmethod
    def valid_due(cls,value):
        if value:
            from datetime import date
            if date.fromisoformat(value).isoformat()!=value:raise ValueError('日期无效')
        return value

class GoalRequest(TaskRequest):
    unit: str = Field(default='元',max_length=20)
    target: float = Field(gt=0,allow_inf_nan=False)
    current: float = Field(ge=0,allow_inf_nan=False)

@app.get('/api/work')
def list_work():
    return tasks.listing()

@app.post('/api/work/tasks')
def create_task(body: TaskRequest):
    try:return tasks.save_task(body.model_dump())
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.put('/api/work/tasks/{key}')
def update_task(key: str,body: TaskRequest):
    try:return tasks.save_task(body.model_dump(),key)
    except KeyError:raise HTTPException(404,'任务不存在')
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/work/goals')
def create_goal_record(body: GoalRequest):
    try:return tasks.save_goal(body.model_dump())
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.put('/api/work/goals/{key}')
def update_goal_record(key: str,body: GoalRequest):
    try:return tasks.save_goal(body.model_dump(),key)
    except KeyError:raise HTTPException(404,'目标不存在')
    except ValueError as exc:raise HTTPException(400,str(exc))

class ItemRequest(BaseModel):
    sku: str = Field(min_length=1,max_length=80,pattern=r'\S')
    name: str = Field(min_length=1,max_length=120,pattern=r'\S')
    unit: str = Field(default='件',max_length=20)
    reorder_level: int = Field(default=5,ge=0,le=1000000000)

class MovementRequest(BaseModel):
    item_id: str
    delta: int = Field(ge=-1000000,le=1000000)
    reason: str = Field(min_length=1,max_length=300,pattern=r'\S')

    @field_validator('delta')
    @classmethod
    def nonzero(cls,value):
        if value==0:raise ValueError('数量不能为零')
        return value

@app.get('/api/inventory')
def list_inventory():return inventory.listing()

@app.post('/api/inventory/items')
def add_item(body: ItemRequest):
    try:return inventory.create_item(body.sku.strip(),body.name.strip(),body.unit,body.reorder_level)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/inventory/movements')
def stock_movement(body: MovementRequest):
    try:return inventory.move(body.item_id,body.delta,body.reason.strip())
    except KeyError:raise HTTPException(404,'商品不存在')
    except ValueError as exc:raise HTTPException(400,str(exc))

class PurchaseRequest(BaseModel):
    item_id: str
    supplier: str = Field(min_length=1,max_length=120,pattern=r'\S')
    quantity: int = Field(ge=1,le=1000000)
    due: str = ''

    @field_validator('due')
    @classmethod
    def valid_due(cls,value):
        if value and (len(value)!=10 or date.fromisoformat(value).isoformat()!=value):
            raise ValueError('预计到货日期格式应为 YYYY-MM-DD')
        return value

class ReceiptRequest(BaseModel):
    quantity: int = Field(ge=1,le=1000000)
    receipt_id: str = Field(min_length=8,max_length=100)

@app.post('/api/inventory/orders')
def purchase_order(body: PurchaseRequest):
    try:return inventory.create_order(body.item_id,body.supplier.strip(),body.quantity,body.due)
    except KeyError:raise HTTPException(404,'商品不存在')
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/inventory/orders/{key}/receive')
def purchase_receive(key: str,body: ReceiptRequest):
    try:return inventory.receive_order(key,body.quantity,body.receipt_id)
    except KeyError:raise HTTPException(404,'采购单不存在')
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/inventory/orders/{key}/cancel')
def purchase_cancel(key: str):
    try:return inventory.cancel_order(key)
    except KeyError:raise HTTPException(404,'采购单不存在')
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/alerts')
def business_alerts(today: str):
    from datetime import date
    try:
        day=date.fromisoformat(today)
        if day.isoformat()!=today:raise ValueError('日期格式无效')
    except ValueError:raise HTTPException(422,'日期必须为 YYYY-MM-DD')
    return alerts.listing(day)

class MetricRequest(BaseModel):
    name: str = Field(min_length=1,max_length=120,pattern=r'\S')
    description: str = Field(default='',max_length=1000)
    sql: str = Field(min_length=1,max_length=10000)

@app.get('/api/metrics')
def metric_list():return {'templates':metrics.listing()}

@app.post('/api/metrics')
def metric_save(body: MetricRequest):
    try:return metrics.save(body.name,body.description,body.sql)
    except ValueError as exc:raise HTTPException(400,str(exc))

class MetricArchiveRequest(BaseModel):
    archived: bool

@app.put('/api/metrics/{key}/archive')
def metric_archive(key: str,body: MetricArchiveRequest):
    try:return metrics.archive(key,body.archived)
    except KeyError:raise HTTPException(404,'模板不存在')

class ReceivableRequest(BaseModel):
    reference: str = Field(min_length=1,max_length=80,pattern=r'\S')
    customer: str = Field(min_length=1,max_length=120,pattern=r'\S')
    amount: int = Field(ge=1,le=100000000000)
    due: str

    @field_validator('due')
    @classmethod
    def valid_date(cls,value):
        from datetime import date
        if date.fromisoformat(value).isoformat()!=value:raise ValueError('日期格式无效')
        return value

class CashReceiptRequest(BaseModel):
    amount: int = Field(ge=1,le=100000000000)
    note: str = Field(min_length=1,max_length=300,pattern=r'\S')
    receipt_id: str = Field(min_length=8,max_length=100)

@app.get('/api/receivables')
def receivable_list():return receivables.listing()

@app.post('/api/receivables')
def receivable_create(body: ReceivableRequest):
    try:return receivables.create(body.reference.strip(),body.customer.strip(),body.amount,body.due)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/receivables/{key}/receive')
def cash_receive(key: str,body: CashReceiptRequest):
    try:return receivables.receive(key,body.amount,body.note.strip(),body.receipt_id)
    except KeyError:raise HTTPException(404,'应收记录不存在')
    except ValueError as exc:raise HTTPException(400,str(exc))

class ReversalRequest(BaseModel):
    reason: str = Field(min_length=1,max_length=300,pattern=r'\S')

@app.post('/api/receipts/{key}/reverse')
def receipt_reverse(key: str,body: ReversalRequest):
    try:return receivables.reverse(key,body.reason.strip())
    except KeyError:raise HTTPException(404,'回款流水不存在')
    except ValueError as exc:raise HTTPException(400,str(exc))

class CollectionTaskRequest(BaseModel):
    customer: str = Field(min_length=1,max_length=120,pattern=r'\S')
    owner: str = Field(default='',max_length=80)
    due: str

    @field_validator('due')
    @classmethod
    def valid_date(cls,value):
        from datetime import date
        if date.fromisoformat(value).isoformat()!=value:raise ValueError('日期无效')
        return value

@app.post('/api/receivables/followup')
def collection_task(body: CollectionTaskRequest):
    try:return receivables.followup(body.customer,body.owner,body.due)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/config')
def config():
    cfg = model_config()
    return {'ai_available': cfg['available'], 'model': cfg['model'] if cfg['available'] else '',
            'max_bytes': MAX_BYTES, 'ttl_seconds': TTL}

@app.get('/api/datasets/{key}')
def dataset(key: str):
    return describe(key, get_dataset(key))

@app.get('/api/datasets/{key}/rows')
def rows(key: str, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
         search: str = Query('', max_length=200), sort_by: int | None = Query(None, ge=0), descending: bool = False):
    try:
        return browse_dataset(get_dataset(key), page, page_size, search, sort_by, descending)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.get('/api/datasets/{key}/profile')
def profile(key: str):
    return profile_dataset(get_dataset(key))

@app.delete('/api/datasets/{key}')
def remove_dataset(key: str):
    with LOCK:
        DATA.pop(key, None)
    return {'deleted': True}

@app.post('/api/demo')
def demo():
    try:
        return store((ROOT / 'data/orders.csv').read_bytes())
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post('/api/upload')
async def upload(file: UploadFile):
    try:
        if not (file.filename or '').lower().endswith('.csv'):
            raise ValueError('请上传 .csv 文件')
        return store(await file.read(MAX_BYTES + 1))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    finally:
        await file.close()

@app.post('/api/ask')
def ask(body: Question):
    ds = get_dataset(body.dataset_id)
    start = time.perf_counter()
    try:
        metadata = {}
        if body.mode == 'demo':
            sql = demo_sql(body.question, ds['names'])
        else:
            sql, metadata = generate_sql(body.question, ds)
        result = run_query(ds, sql)
        result.update({'mode': body.mode, 'elapsed_ms': round((time.perf_counter() - start) * 1000),
                       'summary': f"查询返回 {len(result['rows'])} 行，最多展示 200 行。请核对 SQL 中的筛选条件和金额口径。",
                       'model_info': metadata})
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post('/api/query')
def sql_query(body: SQLQuery):
    start = time.perf_counter()
    try:
        result = run_query(get_dataset(body.dataset_id), body.sql)
        result.update({'mode': 'sql', 'elapsed_ms': round((time.perf_counter() - start) * 1000),
                       'summary': f"查询返回 {len(result['rows'])} 行，最多展示 200 行。SQL 已通过只读校验。",
                       'model_info': {}})
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc))

if (ROOT / 'frontend/dist').exists():
    app.mount('/', StaticFiles(directory=ROOT / 'frontend/dist', html=True), name='frontend')
