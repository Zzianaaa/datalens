"""Deterministic data quality statistics; no model or external calls."""
import math
import statistics
from collections import Counter


def profile_dataset(ds):
    rows = ds['rows']
    columns = []
    for i, (name, kind) in enumerate(zip(ds['names'], ds['types'])):
        values = [r[i] for r in rows if r[i] is not None]
        counts = Counter(values)
        missing = len(rows) - len(values)
        item = {'name': name, 'type': kind, 'missing': missing,
                'missing_percent': round(missing / len(rows) * 100, 2) if rows else 0,
                'distinct': len(counts),
                'top_values': [{'value': v, 'count': n} for v, n in counts.most_common(5)]}
        if kind == 'DOUBLE':
            finite = [v for v in values if math.isfinite(v)]
            item['non_finite'] = len(values) - len(finite)
            item['numeric'] = {'min': min(finite), 'max': max(finite),
                               'mean': statistics.fmean(finite), 'median': statistics.median(finite)} if finite else None
        columns.append(item)
    return {'row_count': len(rows), 'duplicate_rows': len(rows) - len(set(map(tuple, rows))),
            'missing_cells': sum(c['missing'] for c in columns), 'columns': columns}
