# -*- coding: utf-8 -*-
"""V3200.2 bounded batch loader: real data only, no synthetic fallback."""
import logging
import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import requests
from scripts.data_sources import eastmoney_kline, tencent_kline, sina_kline, load_cached, market

log = logging.getLogger(__name__)
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36'
YAHOO = 'https://query1.finance.yahoo.com/v7/finance/spark'
MAX_WORKERS = 24
PROVIDER_DEADLINE_SECONDS = 300
FRESH_MAX_AGE_DAYS = 5


def _yahoo_symbol(c):
    return str(c) + ('.SS' if market(c) == 'sh' else '.SZ')


def _fresh(rows, max_age_days=FRESH_MAX_AGE_DAYS):
    if not rows:
        return False
    try:
        last = dt.date.fromisoformat(str(rows[-1].get('date'))[:10])
        return (dt.date.today() - last).days <= max_age_days
    except Exception:
        return False


def _yahoo_rows(node):
    try:
        if isinstance(node, dict) and 'response' in node:
            node = (node.get('response') or [{}])[0]
        ts = node.get('timestamp') or []
        q = ((node.get('indicators') or {}).get('quote') or [{}])[0]
        out = []
        for i, t in enumerate(ts):
            vals = [q.get(k, [None] * len(ts))[i] if i < len(q.get(k, [])) else None
                    for k in ('open', 'close', 'high', 'low', 'volume')]
            if any(v is None for v in vals[:4]):
                continue
            out.append({
                'date': dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(),
                'open': float(vals[0]), 'close': float(vals[1]),
                'high': float(vals[2]), 'low': float(vals[3]),
                'volume': float(vals[4] or 0), 'amount': 0.0,
                'source': 'Yahoo Finance',
                'fetched_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            })
        return out[-180:]
    except Exception:
        return []


def _yahoo_batch(codes):
    session = requests.Session()
    session.headers.update({'User-Agent': UA, 'Accept': 'application/json,text/plain,*/*'})
    out = {}
    for start in range(0, len(codes), 40):
        part = codes[start:start + 40]
        try:
            r = session.get(
                YAHOO,
                params={'symbols': ','.join(_yahoo_symbol(c) for c in part), 'range': '1y', 'interval': '1d'},
                timeout=20,
            )
            r.raise_for_status()
            obj = r.json()
            nodes = obj.get('spark', {}).get('result', []) if isinstance(obj, dict) else []
            if not nodes and isinstance(obj, dict):
                nodes = [v for v in obj.values() if isinstance(v, dict) and ('timestamp' in v or 'response' in v)]
            for node in nodes or []:
                sym = node.get('symbol') or ((node.get('response') or [{}])[0].get('meta') or {}).get('symbol')
                if not sym:
                    continue
                code = sym.split('.')[0]
                rows = _yahoo_rows(node)
                if len(rows) >= 80 and _fresh(rows):
                    out[code] = rows
        except Exception as exc:
            log.warning('Yahoo batch chunk %s failed: %s', start, type(exc).__name__)
    return out


def _parallel(codes, fn, deadline=PROVIDER_DEADLINE_SECONDS):
    """Bounded provider fan-out; a broken provider cannot hold the pipeline forever."""
    codes = list(dict.fromkeys(str(c) for c in codes))
    if not codes:
        return {}
    out = {}
    ex = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    futures = {ex.submit(fn, c, 180): c for c in codes}
    deadline_at = time.monotonic() + deadline
    try:
        pending = set(futures)
        while pending and time.monotonic() < deadline_at:
            done, pending = wait(
                pending,
                timeout=min(5.0, max(0.1, deadline_at - time.monotonic())),
                return_when=FIRST_COMPLETED,
            )
            for future in done:
                code = futures[future]
                try:
                    rows = future.result()
                    if len(rows) >= 80 and _fresh(rows):
                        out[str(code)] = rows
                except Exception:
                    pass
    finally:
        for future in futures:
            if not future.done():
                future.cancel()
        ex.shutdown(wait=False, cancel_futures=True)
    return out


def load_real_klines(codes):
    """Batch-first real data. No random/synthetic data is ever generated.

    Baostock is deliberately excluded from the 4400+ production fan-out because
    the previous run demonstrated login/transport instability under mass access.
    It remains available for preflight and small-sample diagnostics elsewhere.
    """
    codes = list(dict.fromkeys(str(c) for c in codes))
    result = {}
    diag = {
        'universe': len(codes), 'yahoo_batch': 0, 'eastmoney': 0,
        'tencent': 0, 'sina': 0, 'baostock_production': False,
        'cache': 0, 'missing': 0, 'coverage': 0.0,
        'fresh_max_age_days': FRESH_MAX_AGE_DAYS,
    }

    got = _yahoo_batch(codes)
    result.update(got)
    diag['yahoo_batch'] = len(got)

    missing = [c for c in codes if c not in result]
    if missing:
        got = _parallel(missing, eastmoney_kline)
        result.update(got)
        diag['eastmoney'] = len(got)

    missing = [c for c in codes if c not in result]
    if missing:
        got = _parallel(missing, tencent_kline)
        result.update(got)
        diag['tencent'] = len(got)

    missing = [c for c in codes if c not in result]
    if missing:
        got = _parallel(missing, sina_kline)
        result.update(got)
        diag['sina'] = len(got)

    # Cache is recovery only and must still contain a fresh trading-day series.
    missing = [c for c in codes if c not in result]
    for c in missing:
        rows = load_cached(c, 180)
        if rows and _fresh(rows):
            result[c] = rows
            diag['cache'] += 1

    diag['missing'] = len(codes) - len(result)
    diag['coverage'] = round(len(result) / len(codes), 4) if codes else 0.0
    return result, diag
