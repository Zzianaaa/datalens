import secrets
import threading
import time
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, UploadFile, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .core import parse_csv, demo_sql, run_query, MAX_BYTES
from .model import generate_sql, model_config
from .profile import profile_dataset
from .browse import browse_dataset
from .operations import clean_dataset, business_dashboard
from . import library

app = FastAPI(title='DataLens API', version='0.6.0')
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
