"""Reusable read-only SQL definitions; contains no dataset rows."""
import secrets
from .library import connect
from .core import validate_sql


def initialize(con):
    con.execute('CREATE TABLE IF NOT EXISTS metric_templates (id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,sql TEXT NOT NULL)')
    if 'archived' not in [r['name'] for r in con.execute('PRAGMA table_info(metric_templates)')]:
        con.execute('ALTER TABLE metric_templates ADD COLUMN archived INTEGER NOT NULL DEFAULT 0')


def listing():
    with connect() as con:
        initialize(con)
        return [dict(r) for r in con.execute('SELECT * FROM metric_templates ORDER BY name,id')]


def save(name,description,sql):
    safe=validate_sql(sql)
    with connect() as con:
        initialize(con)
        if con.execute('SELECT COUNT(*) FROM metric_templates').fetchone()[0]>=100:raise ValueError('最多保存 100 个指标模板')
        key=secrets.token_urlsafe(18)
        con.execute('INSERT INTO metric_templates(id,name,description,sql) VALUES (?,?,?,?)',(key,name.strip(),description,safe))
        return {'id':key}


def archive(key,archived):
    with connect() as con:
        initialize(con)
        if con.execute('UPDATE metric_templates SET archived=? WHERE id=?',(int(archived),key)).rowcount==0:raise KeyError(key)
        return {'archived':archived}
