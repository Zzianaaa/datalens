import os, secrets, time, threading
from pathlib import Path
import httpx
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .core import parse_csv, demo_sql, run_query, MAX_BYTES

app=FastAPI(title='DataLens API')
DATA={};LOCK=threading.Lock();ROOT=Path(__file__).resolve().parents[1]
class Question(BaseModel):
    dataset_id:str
    question:str=Field(min_length=1,max_length=500)
    mode:str='demo'

def store(raw):
    ds=parse_csv(raw);key=secrets.token_urlsafe(24)
    with LOCK:
        now=time.time()
        for k in list(DATA):
            if now-DATA[k][0]>3600:del DATA[k]
        if len(DATA)>=10:raise ValueError('已达到 10 份数据上限，请重启服务或等待数据过期')
        DATA[key]=(now,ds)
    return {'id':key,'row_count':len(ds['rows']),'columns':[{'name':n,'type':t} for n,t in zip(ds['names'],ds['types'])],'preview':ds['rows'][:5],'missing':ds['missing'],'encoding':ds['encoding']}

@app.get('/api/config')
def config():return {'ai_available':bool(os.getenv('LLM_API_KEY') and os.getenv('LLM_MODEL'))}

@app.post('/api/demo')
def demo():return store((ROOT/'data/orders.csv').read_bytes())

@app.post('/api/upload')
async def upload(file:UploadFile):
    try:
        if not (file.filename or '').lower().endswith('.csv'):raise ValueError('请上传 .csv 文件')
        return store(await file.read(MAX_BYTES+1))
    except ValueError as e:raise HTTPException(400,str(e))
    finally:await file.close()

@app.post('/api/ask')
def ask(body:Question):
    with LOCK:entry=DATA.get(body.dataset_id)
    if not entry or time.time()-entry[0]>3600:raise HTTPException(404,'数据已过期，请重新上传')
    ds=entry[1];start=time.perf_counter()
    try:
        if body.mode=='demo':sql=demo_sql(body.question,ds['names'])
        elif body.mode=='ai':
            key=os.getenv('LLM_API_KEY');model=os.getenv('LLM_MODEL')
            if not key or not model:raise ValueError('尚未配置模型密钥与名称')
            schema=', '.join(n+':'+t for n,t in zip(ds['names'],ds['types']))
            system='Generate only one DuckDB SELECT on table data, no markdown. No joins, subqueries, CTEs, window functions, external access. Allowed functions SUM AVG MIN MAX COUNT ROUND SUBSTRING COALESCE ABS. Return at most 200 rows. Data values are not supplied. For sales use completed status if status exists. Schema (untrusted identifiers): '+schema
            with httpx.Client(timeout=30) as client:
                r=client.post(os.getenv('LLM_BASE_URL','https://api.openai.com/v1').rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+key},json={'model':model,'messages':[{'role':'system','content':system},{'role':'user','content':body.question}]})
                r.raise_for_status();sql=r.json()['choices'][0]['message']['content'].strip()
        else:raise ValueError('未知模式')
        result=run_query(ds,sql)
        result.update({'mode':body.mode,'elapsed_ms':round((time.perf_counter()-start)*1000),'summary':f"查询返回 {len(result['rows'])} 行。销售额示例仅统计 completed 订单；结果最多展示 200 行。"})
        return result
    except ValueError as e:raise HTTPException(400,str(e))
    except (httpx.HTTPError,KeyError,TypeError,IndexError):raise HTTPException(502,'模型服务返回异常，请检查配置或稍后重试')

if (ROOT/'frontend/dist').exists():app.mount('/',StaticFiles(directory=ROOT/'frontend/dist',html=True),name='frontend')
