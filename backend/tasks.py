"""Persistent business goals and execution tasks."""
import secrets
import time
from .library import connect


def initialize(con):
    con.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),title TEXT NOT NULL,owner TEXT NOT NULL,due TEXT NOT NULL,status TEXT NOT NULL,notes TEXT NOT NULL,created REAL NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS goals (id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),title TEXT NOT NULL,unit TEXT NOT NULL,target REAL NOT NULL,current REAL NOT NULL,due TEXT NOT NULL,created REAL NOT NULL)')


def check_project(con,project):
    if project and not con.execute('SELECT 1 FROM projects WHERE id=?',(project,)).fetchone():raise ValueError('项目不存在')


def listing():
    with connect() as con:
        initialize(con)
        return {'tasks':[dict(r) for r in con.execute('SELECT * FROM tasks ORDER BY created DESC')],
                'goals':[dict(r) for r in con.execute('SELECT * FROM goals ORDER BY created DESC')]}


def save_task(data,key=None):
    with connect() as con:
        initialize(con);check_project(con,data.get('project_id'))
        if key and not con.execute('SELECT 1 FROM tasks WHERE id=?',(key,)).fetchone():raise KeyError(key)
        if not key and con.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]>=500:raise ValueError('最多 500 个任务')
        key=key or secrets.token_urlsafe(18)
        con.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET project_id=excluded.project_id,title=excluded.title,owner=excluded.owner,due=excluded.due,status=excluded.status,notes=excluded.notes',
                    (key,data.get('project_id') or None,data['title'].strip(),data['owner'],data['due'],data['status'],data['notes'],time.time()))
        return {'id':key}


def save_goal(data,key=None):
    with connect() as con:
        initialize(con);check_project(con,data.get('project_id'))
        if key and not con.execute('SELECT 1 FROM goals WHERE id=?',(key,)).fetchone():raise KeyError(key)
        if not key and con.execute('SELECT COUNT(*) FROM goals').fetchone()[0]>=100:raise ValueError('最多 100 个目标')
        key=key or secrets.token_urlsafe(18)
        con.execute('INSERT INTO goals VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET project_id=excluded.project_id,title=excluded.title,unit=excluded.unit,target=excluded.target,current=excluded.current,due=excluded.due',
                    (key,data.get('project_id') or None,data['title'].strip(),data['unit'],data['target'],data['current'],data['due'],time.time()))
        return {'id':key}
