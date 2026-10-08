"""Bounded in-memory browsing with literal search and stable sorting."""
def browse_dataset(ds, page=1, page_size=20, search='', sort_by=None, descending=False):
    rows = ds['rows']
    if search:
        needle = search.casefold()
        rows = [r for r in rows if any(v is not None and needle in str(v).casefold() for v in r)]
    if sort_by is not None:
        if sort_by >= len(ds['names']):
            raise ValueError('排序字段不存在')
        present = [r for r in rows if r[sort_by] is not None]
        absent = [r for r in rows if r[sort_by] is None]
        rows = sorted(present, key=lambda r: r[sort_by], reverse=descending) + absent
    total = len(rows)
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    offset = (page - 1) * page_size
    return {'columns': ds['names'], 'rows': rows[offset:offset+page_size],
            'total': total, 'page': page, 'pages': pages, 'page_size': page_size}
