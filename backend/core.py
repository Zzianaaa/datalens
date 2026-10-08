import csv, io, math, re, multiprocessing, queue
import duckdb
import sqlglot
from sqlglot import exp

MAX_BYTES = 5 * 1024 * 1024

def parse_csv(raw):
    if not raw or len(raw) > MAX_BYTES: raise ValueError('文件不能为空，且不能超过 5 MB')
    text = None
    for encoding in ('utf-8-sig', 'gb18030'):
        try: text = raw.decode(encoding); break
        except UnicodeDecodeError: pass
    if text is None: raise ValueError('无法识别编码，请导出 UTF-8 CSV')
    reader = csv.reader(io.StringIO(text), strict=True)
    try:
        names = next(reader)
        if not names or len(names)>50 or any(not n.strip() or len(n)>80 for n in names): raise ValueError('列名不能为空，最多 50 列')
        if len(set(n.casefold() for n in names)) != len(names): raise ValueError('存在重复列名')
        rows = []
        for row in reader:
            if not row: continue
            if len(row)!=len(names): raise ValueError('数据行列数与表头不一致')
            rows.append([None if x.strip()=='' else x for x in row])
            if len(rows)>20000: raise ValueError('最多支持 20000 行')
    except (StopIteration,csv.Error) as e: raise ValueError('CSV 格式无效') from e
    if not rows: raise ValueError('CSV 没有数据行')
    types=[]
    for i in range(len(names)):
        values=[row[i] for row in rows if row[i] is not None]
        numeric=bool(values)
        try:
            numeric=numeric and all(math.isfinite(float(v)) for v in values)
        except ValueError: numeric=False
        types.append('DOUBLE' if numeric else 'VARCHAR')
        if numeric:
            for row in rows:
                if row[i] is not None:row[i]=float(row[i])
    return {'names':names,'types':types,'rows':rows,'encoding':encoding,'missing':sum(v is None for r in rows for v in r)}

def quote(s): return '"'+s.replace('"','""')+'"'

def validate_sql(sql):
    try: trees=sqlglot.parse(sql,read='duckdb')
    except sqlglot.errors.ParseError as e: raise ValueError('SQL 语法无效') from e
    if len(trees)!=1 or not isinstance(trees[0],exp.Select): raise ValueError('只允许单条 SELECT 查询')
    tree=trees[0]
    forbidden=(exp.Subquery, exp.With, exp.Join, exp.Union, exp.Window)
    if any(isinstance(n,forbidden) for n in tree.walk()): raise ValueError('第一版不支持子查询、连接、CTE 或窗口函数')
    tables=list(tree.find_all(exp.Table))
    if len(tables)!=1 or not isinstance(tables[0].this,exp.Identifier) or tables[0].name!='data' or tables[0].db or tables[0].catalog:raise ValueError('只能查询当前 data 表')
    allowed={'SUM','AVG','MIN','MAX','COUNT','ROUND','SUBSTRING','COALESCE','ABS'}
    for node in tree.find_all(exp.Func):
        if isinstance(node,exp.Anonymous) or node.sql_name() not in allowed:raise ValueError('包含未允许的函数')
    limit=tree.args.get('limit')
    count=200
    if limit is not None:
        value=limit.expression
        if not isinstance(value,exp.Literal) or not value.is_int:raise ValueError('LIMIT 必须是非负整数')
        count=min(200,int(value.this))
    tree.set('limit',exp.Limit(expression=exp.Literal.number(count)))
    return tree.sql(dialect='duckdb')

def _worker(dataset,sql,out):
    try:
        con=duckdb.connect(config={'enable_external_access':'false','threads':'1','memory_limit':'128MB'})
        defs=', '.join(quote(n)+' '+t for n,t in zip(dataset['names'],dataset['types']))
        con.execute('CREATE TABLE data ('+defs+')')
        con.executemany('INSERT INTO data VALUES ('+','.join('?' for _ in dataset['names'])+')',dataset['rows'])
        cur=con.execute(sql)
        out.put({'columns':[x[0] for x in cur.description],'rows':cur.fetchmany(201)})
        con.close()
    except Exception as e: out.put({'error':str(e)[:300]})

def run_query(dataset,sql,timeout=8):
    safe=validate_sql(sql)
    ctx=multiprocessing.get_context('spawn');out=ctx.Queue();proc=ctx.Process(target=_worker,args=(dataset,safe,out));proc.start()
    try:result=out.get(timeout=timeout)
    except queue.Empty:
        proc.terminate();raise ValueError('查询超时，请简化问题')
    finally:
        proc.join(timeout=1)
        if proc.is_alive():proc.terminate();proc.join()
        out.close()
    if 'error' in result:raise ValueError('查询失败：'+result['error'])
    result['sql']=safe;return result

def demo_sql(question,names):
    required={'日期':'order_date','类别':'category','商品':'product','金额':'amount','状态':'status'}
    q=question.strip()
    if q in ('每月销售额','每个月的销售额是多少？'):sql="SELECT SUBSTRING(order_date, 1, 7) AS 月份, ROUND(SUM(amount), 2) AS 销售额 FROM data WHERE status = 'completed' GROUP BY 月份 ORDER BY 月份";need=['日期','金额','状态']
    elif q in ('各类别销售额','哪个商品类别卖得最好？'):sql="SELECT category AS 类别, ROUND(SUM(amount), 2) AS 销售额 FROM data WHERE status = 'completed' GROUP BY category ORDER BY 销售额 DESC";need=['类别','金额','状态']
    elif q=='销售额最高的五个商品':sql="SELECT product AS 商品, ROUND(SUM(amount), 2) AS 销售额 FROM data WHERE status = 'completed' GROUP BY product ORDER BY 销售额 DESC LIMIT 5";need=['商品','金额','状态']
    elif q=='订单状态分布':sql='SELECT status AS 状态, COUNT(*) AS 订单数 FROM data GROUP BY status ORDER BY 订单数 DESC';need=['状态']
    else:raise ValueError('规则演示仅支持页面上的四个示例问题；自由提问请配置 AI 模式')
    missing=[required[k] for k in need if required[k] not in names]
    if missing:raise ValueError('当前数据缺少字段：'+', '.join(missing))
    return sql
