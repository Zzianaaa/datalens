import json
import httpx
import pytest
from backend.model import extract_sql, generate_sql, ModelError
from backend.core import parse_csv

@pytest.fixture(autouse=True)
def fake_config(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'test-only-not-a-secret')
    monkeypatch.setenv('LLM_MODEL', 'test-model')
    monkeypatch.setenv('LLM_BASE_URL', 'https://test.invalid/v1')

@pytest.mark.parametrize('text', [None, '', '   '])
def test_no_sql(text):
    with pytest.raises(ModelError): extract_sql(text)

def test_fenced_sql():
    assert extract_sql('```sql\nSELECT * FROM data\n```') == 'SELECT * FROM data'

def test_request_schema_only():
    ds = parse_csv(b'amount\n123.456789')
    def handler(request):
        payload = json.loads(request.content)
        assert '123.456789' not in request.content.decode()
        assert 'amount' in payload['messages'][0]['content']
        assert request.url.path == '/v1/chat/completions'
        return httpx.Response(200, json={'choices': [{'message': {'content': 'SELECT SUM(amount) FROM data'}}], 'usage': {'total_tokens': 12}})
    sql, info = generate_sql('总金额', ds, transport=httpx.MockTransport(handler))
    assert sql == 'SELECT SUM(amount) FROM data'
    assert info['tokens']['total_tokens'] == 12

@pytest.mark.parametrize('status,message', [(401,'认证'), (429,'限流'), (500,'异常')])
def test_http_errors(status,message):
    with pytest.raises(ModelError, match=message):
        generate_sql('x', parse_csv(b'a\n1'), transport=httpx.MockTransport(lambda r: httpx.Response(status)))

@pytest.mark.parametrize('payload', [{}, {'choices': []}, {'choices':[{'message': {'content': None}}]}])
def test_malformed_response(payload):
    with pytest.raises(ModelError):
        generate_sql('x', parse_csv(b'a\n1'), transport=httpx.MockTransport(lambda r: httpx.Response(200,json=payload)))

def test_unsupported():
    with pytest.raises(ModelError, match='无法回答'):
        generate_sql('x', parse_csv(b'a\n1'), transport=httpx.MockTransport(lambda r: httpx.Response(200,json={'choices':[{'message':{'content':'UNSUPPORTED'}}]})))

def test_timeout():
    def handler(request): raise httpx.ReadTimeout('timeout')
    with pytest.raises(ModelError, match='超时'):
        generate_sql('x',parse_csv(b'a\n1'),transport=httpx.MockTransport(handler))

def test_config_missing(monkeypatch):
    monkeypatch.delenv('LLM_API_KEY')
    with pytest.raises(ModelError, match='尚未配置'):generate_sql('x',parse_csv(b'a\n1'))
