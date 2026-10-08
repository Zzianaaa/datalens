# DataLens 数据分析助手

上传 CSV，用中文问题生成只读 SQL，并展示可核对的表格、图表和实际执行查询。

## 启动
需要 pnpm 11.25.0、Python 3.11+、Node.js 20.19+ 或 22.12+。

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend
pnpm install --frozen-lockfile
pnpm run build
cd ..
uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

浏览器打开 http://127.0.0.1:8000 。点击「加载示例数据」，再点击「开始分析」。开发时可分别运行 uvicorn 和 frontend 下的 pnpm run dev。

## 两种模式
- 规则演示：无需密钥，仅支持界面列出的四个问题，要求相应的示例字段。不是模型推理。
- AI 自由提问：服务启动前设置 LLM_API_KEY、LLM_MODEL，可选 LLM_BASE_URL。使用兼容 Chat Completions 的服务。未配置时禁用。字段名称、类型和问题发送给模型，原始行数据不发送。真实模型集成尚未进行在线验收。

金额字段 amount 代表每条记录的总金额。销售额演示排除 returned 和 cancelled，仅统计 completed。演示数据是虚构订单，每行代表一个订单。

## 架构与边界
Vue 3 + ECharts → FastAPI → 规则解析 / 模型生成 SQL → SQLGlot 语法树校验 → 子进程中的 DuckDB → 表格与图表。

单进程服务为本地演示设计，无登录、多租户隔离或持久化。数据使用随机标识，在内存中最多保存一小时；服务重启丢失。最多 10 份数据、每份 5 MB、20000 行、50 列。仅允许当前 data 表、单条 SELECT、白名单函数；第一版不支持连接、子查询、CTE 和窗口函数。子进程设置查询超时，DuckDB 限制 128MB 数据库内存与单线程，禁用外部访问。128MB 不是整个进程的操作系统内存限制。结果最多 200 行。

SQL 通过校验不代表统计语义正确。请核对筛选条件、字段和金额含义。数值直接来自数据库，不由模型自由生成。

## 测试
```sh
python -m pytest -q
```
覆盖无效 CSV、编码、缺失值、非法 SQL、外部读取、结果上限、查询超时和示例标准答案。规则测试成绩不能作为真实模型准确率。GitHub Actions 执行后端测试与前端构建。

## 面试讲解
1. 为什么不用模型直接算数字？数据库可提供确定性计算，SQL 也便于复核。
2. 为什么既校验 SQL 又关闭外部访问？语法校验与数据库能力限制形成两层防护。
3. 为什么保留规则模式？降低首次演示门槛，明确功能边界，并提供稳定回归用例。
4. 下一步：真实模型评测、查询修复、字段映射、测试更多 CSV 边界、用户身份与持久化。

项目处于第一版。简历中只写实际实现与验证的功能，不写尚未测得的准确率或生产规模。
