"""Explicit business calculations and reversible cleaning copies."""
import math
from collections import defaultdict
from copy import deepcopy


def clean_dataset(ds, deduplicate=False, trim_text=False, drop_missing=False):
    result = deepcopy(ds)
    rows = result['rows']
    if trim_text:
        rows = [[v.strip() if isinstance(v, str) else v for v in r] for r in rows]
        rows = [[None if v == '' else v for v in r] for r in rows]
    if drop_missing:
        rows = [r for r in rows if all(v is not None for v in r)]
    if deduplicate:
        rows = list(dict.fromkeys(map(tuple, rows)))
        rows = list(map(list, rows))
    if not rows:
        raise ValueError('清洗后没有数据，请调整规则')
    result['rows'] = rows
    result['missing'] = sum(v is None for r in rows for v in r)
    return result, {'before_rows': len(ds['rows']), 'after_rows': len(rows),
                    'removed_rows': len(ds['rows'])-len(rows), 'missing_after': result['missing']}


def business_dashboard(ds, amount, category, date=None, status=None, status_value=None):
    if amount not in ds['names'] or category not in ds['names']:
        raise ValueError('请正确选择金额和类别字段')
    ai, ci = ds['names'].index(amount), ds['names'].index(category)
    if ds['types'][ai] != 'DOUBLE':
        raise ValueError('金额字段必须是数值')
    for field in (date, status):
        if field and field not in ds['names']:
            raise ValueError('所选字段不存在')
    rows = ds['rows']
    if status and status_value is not None:
        si = ds['names'].index(status)
        rows = [r for r in rows if str(r[si]) == status_value]
    valid = [r for r in rows if r[ai] is not None]
    def total(values):
        try:
            result = math.fsum(values)
            if not math.isfinite(result): raise OverflowError
            return result
        except OverflowError:
            raise ValueError('金额数值过大，无法汇总')
    revenue = total(r[ai] for r in valid)
    groups = defaultdict(list)
    months = defaultdict(list)
    invalid_dates = 0
    for r in valid:
        groups[str(r[ci]) if r[ci] is not None else '缺失类别'].append(r[ai])
        if date:
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(str(r[ds['names'].index(date)]).replace('Z','+00:00'))
                months[dt.strftime('%Y-%m')].append(r[ai])
            except (ValueError, TypeError): invalid_dates += 1
    ranked = sorted(((k,total(v)) for k,v in groups.items()),key=lambda x:x[1],reverse=True)
    trend = sorted((k,total(v)) for k,v in months.items())
    return {'revenue': revenue, 'row_count': len(rows), 'valid_amount_rows': len(valid),
            'average_amount': revenue/len(valid) if valid else None,
            'missing_amount_rows': len(rows)-len(valid), 'invalid_date_rows': invalid_dates,
            'categories': {'columns':['类别','金额'], 'rows': ranked[:20]},
            'trend': {'columns':['月份','金额'], 'rows': trend},
            'scope': {'amount':amount,'category':category,'date':date,'status':status,'status_value':status_value},
            'note': '按每行金额求和，不自动乘数量；每行视为一条记录，平均值不是按唯一订单计算。'}
