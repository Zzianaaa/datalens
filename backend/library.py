"""Local SQLite project and dataset vault, separate from temporary sessions."""
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager


@contextmanager
def connect():
    path = Path(os.environ.get('DATALENS_DB', str(Path(__file__).resolve().parents[1] / 'storage/platform.sqlite')))
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,created REAL NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY,name TEXT NOT NULL,project_id TEXT REFERENCES projects(id),payload TEXT NOT NULL,created REAL NOT NULL,archived INTEGER NOT NULL DEFAULT 0)')
    con.execute('CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY,title TEXT NOT NULL,project_id TEXT REFERENCES projects(id),payload TEXT NOT NULL,created REAL NOT NULL)')
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def listing():
    with connect() as con:
        projects = [dict(r) for r in con.execute('SELECT * FROM projects ORDER BY created DESC')]
        assets = []
        for r in con.execute('SELECT * FROM assets ORDER BY created DESC'):
            ds = json.loads(r['payload'])
            assets.append({'id':r['id'],'name':r['name'],'project_id':r['project_id'],'created':r['created'],
                           'archived':bool(r['archived']),'row_count':len(ds['rows']),'column_count':len(ds['names'])})
        reports=[dict(r) for r in con.execute('SELECT id,title,project_id,created FROM reports ORDER BY created DESC')]
        return {'projects':projects,'assets':assets,'reports':reports}


def create_project(name, description):
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        if con.execute('SELECT COUNT(*) FROM projects').fetchone()[0] >= 50:
            raise ValueError('最多 50 个项目')
        key = secrets.token_urlsafe(18)
        con.execute('INSERT INTO projects VALUES (?,?,?,?)',(key,name,description,time.time()))
        return {'id':key,'name':name,'description':description}


def save_dataset(name, project_id, ds):
    payload = json.dumps(ds,ensure_ascii=False,allow_nan=False)
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        if project_id and not con.execute('SELECT 1 FROM projects WHERE id=?',(project_id,)).fetchone():
            raise ValueError('项目不存在')
        if con.execute('SELECT COUNT(*) FROM assets').fetchone()[0] >= 100:
            raise ValueError('最多保存 100 份数据快照')
        total = con.execute('SELECT COALESCE(SUM(LENGTH(CAST(payload AS BLOB))),0) FROM assets').fetchone()[0]
        if total+len(payload.encode()) > 100*1024*1024:
            raise ValueError('本地数据中心达到 100 MB 上限')
        key = secrets.token_urlsafe(18)
        con.execute('INSERT INTO assets VALUES (?,?,?,?,?,0)',(key,name,project_id or None,payload,time.time()))
        return {'id':key,'name':name}


def get_asset(key):
    with connect() as con:
        row = con.execute('SELECT * FROM assets WHERE id=?',(key,)).fetchone()
        if row is None: raise KeyError(key)
        return json.loads(row['payload'])


def archive(key, archived):
    with connect() as con:
        cur=con.execute('UPDATE assets SET archived=? WHERE id=?',(int(archived),key))
        if cur.rowcount == 0: raise KeyError(key)


def save_report(title,project_id,question,result):
    if not isinstance(result.get('columns'),list) or not isinstance(result.get('rows'),list) or len(result['rows'])>200:
        raise ValueError('报告结果格式无效，最多 200 行')
    if len(result['columns'])>50 or any(not isinstance(row,list) or len(row)!=len(result['columns']) for row in result['rows']):
        raise ValueError('报告列数无效')
    payload=json.dumps({'question':question,'result':result},ensure_ascii=False,allow_nan=False)
    if len(payload.encode())>2*1024*1024: raise ValueError('报告不能超过 2 MB')
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        if project_id and not con.execute('SELECT 1 FROM projects WHERE id=?',(project_id,)).fetchone(): raise ValueError('项目不存在')
        if con.execute('SELECT COUNT(*) FROM reports').fetchone()[0]>=100:raise ValueError('最多保存 100 份报告')
        key=secrets.token_urlsafe(18)
        con.execute('INSERT INTO reports VALUES (?,?,?,?,?)',(key,title,project_id or None,payload,time.time()))
        return {'id':key,'title':title}


def get_report(key):
    with connect() as con:
        row=con.execute('SELECT payload FROM reports WHERE id=?',(key,)).fetchone()
        if row is None:raise KeyError(key)
        return json.loads(row['payload'])
