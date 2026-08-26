# -*- coding: utf-8 -*-
"""V3200.4 production scanner: bounded real-data acquisition + quality gate.

Production never creates synthetic K-lines. Providers are isolated so a slow or
broken source cannot hold the whole market scan indefinitely.
"""
import datetime as dt
import json
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path

from scripts.data_sources import baostock_kline, eastmoney_kline, tencent_kline, sina_kline, yahoo_kline, load_cached
from scripts.engine import score_signal, STRATEGIES

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'

# Baostock is the only source that passed the recent production preflight.
# Keep its concurrency deliberately low because each worker owns one login session.
BAOSTOCK_WORKERS = 4
BAOSTOCK_DEADLINE_SECONDS = 600
HTTP_WORKERS = 8
HTTP_DEADLINE_SECONDS = 180
FRESH_MAX_AGE_DAYS = 5
MIN_ROWS = 80
MIN_COVERAGE = 0.90


def _fresh(rows):
    if not rows:
        return False
    try:
        last = dt.date.fromisoformat(str(rows[-1].get('date'))[:10])
        return (dt.date.today() - last).days <= FRESH_MAX_AGE_DAYS
    except Exception:
        return False


def _bounded_fetch(codes, fn, workers, deadline):
    """Bounded fan-out. Returns whatever completed before the provider deadline."""
    codes = list(dict.fromkeys(str(c) for c in codes))
    if not codes:
        return {}
    out = {}
    executor = ThreadPoolExecutor(max_workers=workers)
    futures = {executor.submit(fn, code, 180): code for code in codes}
    pending = set(futures)
    end_at = time.monotonic() + deadline
    try:
        while pending:
            remaining = end_at - time.monotonic()
            if remaining <= 0:
                break
            done, pending = wait(
                pending,
                timeout=min(5.0, remaining),
                return_when=FIRST_COMPLETED,
            )
            for future in done:
                code = futures[future]
                try:
                    rows = future.result()
                    if len(rows) >= MIN_ROWS and _fresh(rows):
                        out[code] = rows[-180:]
                except Exception:
                    continue
    finally:
        for future in pending:
            future.cancel()
        # Do not wait for a hung provider during shutdown.
        executor.shutdown(wait=False, cancel_futures=True)
    return out


def _provider_round(codes, name, fn, workers, deadline):
    started = time.monotonic()
    rows = _bounded_fetch(codes, fn, workers, deadline)
    return rows, {
        'provider': name,
        'requested': len(codes),
        'success': len(rows),
        'elapsed_seconds': round(time.monotonic() - started, 2),
        'fresh_max_age_days': FRESH_MAX_AGE_DAYS,
    }


def load_real_klines_v3200(codes):
    """Acquire fresh real K-lines with bounded provider isolation.

    Order is based on verified availability, not on a claim that every provider
    is currently reachable from GitHub Actions. Failed providers are recorded and
    skipped; no synthetic values are inserted.
    """
    codes = list(dict.fromkeys(str(c) for c in codes))
    result = {}
    diagnostics = {
        'universe': len(codes),
        'min_rows': MIN_ROWS,
        'fresh_max_age_days': FRESH_MAX_AGE_DAYS,
        'min_coverage': MIN_COVERAGE,
        'providers': [],
        'cache': 0,
        'missing': 0,
    }

    # Verified primary: Baostock, tightly bounded.
    missing = [c for c in codes if c not in result]
    got, info = _provider_round(missing, 'Baostock', baostock_kline, BAOSTOCK_WORKERS, BAOSTOCK_DEADLINE_SECONDS)
    result.update(got)
    diagnostics['providers'].append({**info, 'workers': BAOSTOCK_WORKERS, 'deadline_seconds': BAOSTOCK_DEADLINE_SECONDS})

    # HTTP sources are independent bounded fallback rounds. They are deliberately
    # not run as an unbounded 4400-request waterfall.
    for name, fn in (
        ('Eastmoney', eastmoney_kline),
        ('Tencent', tencent_kline),
        ('Sina', sina_kline),
        ('Yahoo', yahoo_kline),
    ):
        missing = [c for c in codes if c not in result]
        if not missing:
            break
        got, info = _provider_round(missing, name, fn, HTTP_WORKERS, HTTP_DEADLINE_SECONDS)
        result.update(got)
        diagnostics['providers'].append({**info, 'workers': HTTP_WORKERS, 'deadline_seconds': HTTP_DEADLINE_SECONDS})

    # Cache is recovery only. It must contain a fresh series; stale cache is a miss.
    missing = [c for c in codes if c not in result]
    for code in missing:
        try:
            rows = load_cached(code, 180)
            if len(rows) >= MIN_ROWS and _fresh(rows):
                result[code] = rows[-180:]
                diagnostics['cache'] += 1
        except Exception:
            continue

    diagnostics['missing'] = len(codes) - len(result)
    diagnostics['coverage'] = round(len(result) / len(codes), 4) if codes else 0.0
    return result, diagnostics


def _validate_rows(rows):
    """Reject malformed/duplicate/future K-lines before factor calculation."""
    if len(rows) < MIN_ROWS:
        return False, 'too_few_rows'
    seen = set()
    today = dt.date.today()
    prev = None
    for row in rows:
        try:
            d = dt.date.fromisoformat(str(row.get('date'))[:10])
            o, h, l, c = (float(row[k]) for k in ('open', 'high', 'low', 'close'))
            v = float(row.get('volume', 0) or 0)
            if d in seen:
                return False, 'duplicate_date'
            if d > today:
                return False, 'future_date'
            if min(o, h, l, c) <= 0 or h < max(o, c) or l > min(o, c) or v < 0:
                return False, 'invalid_ohlcv'
            if prev and d <= prev:
                return False, 'unsorted_date'
            seen.add(d)
            prev = d
        except Exception:
            return False, 'malformed_row'
    if not _fresh(rows):
        return False, 'stale'
    return True, 'ok'


def run(verified_market, verified_indices):
    codes = [str(x['symbol']) for x in verified_market]
    started = time.monotonic()
    klines, diag = load_real_klines_v3200(codes)

    valid = {}
    invalid = {}
    for code, rows in klines.items():
        ok, reason = _validate_rows(rows)
        if ok:
            valid[code] = rows
        else:
            invalid[code] = reason

    signals = []
    failed = []
    for item in verified_market:
        code = str(item['symbol'])
        rows = valid.get(code, [])
        if len(rows) < MIN_ROWS:
            failed.append(code)
            continue
        try:
            signal = score_signal(item, rows)
            if signal:
                signals.append(signal)
            else:
                failed.append(code)
        except Exception:
            failed.append(code)

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    total = len(verified_market)
    data_coverage = len(valid) / total if total else 0.0
    signal_coverage = len(signals) / total if total else 0.0
    elapsed = round(time.monotonic() - started, 2)

    market = {
        'updated_at': now,
        'universe': total,
        'kline_real_scanned': len(valid),
        'kline_raw_received': len(klines),
        'scanned': len(signals),
        'failed': len(failed),
        'kline_coverage': round(data_coverage, 4),
        'signal_coverage': round(signal_coverage, 4),
        'indices': verified_indices,
        'data_quality': 'REAL_KLINE_BATCH_V3200_4',
        'batch_diagnostics': diag,
        'invalid_kline_rows': invalid,
        'elapsed_seconds': elapsed,
        'universe_snapshot_frozen': True,
    }
    payload = {
        'updated_at': now,
        'universe': total,
        'kline_real_scanned': len(valid),
        'kline_raw_received': len(klines),
        'scanned': len(signals),
        'failed': len(failed),
        'kline_coverage': round(data_coverage, 4),
        'signal_coverage': round(signal_coverage, 4),
        'items': sorted(signals, key=lambda x: (x.get('tier') == 'S', x.get('opportunity_score', 0), x.get('quality_score', 0)), reverse=True),
        'strategy_catalog': STRATEGIES,
        'methodology': 'A-H multi-factor technical engine; D is a cost/volume proxy, not true chip distribution.',
        'batch_diagnostics': diag,
        'invalid_kline_rows': invalid,
        'elapsed_seconds': elapsed,
        'data_quality': 'technical_real_batch_v3200_4',
    }
    (DATA / 'market.json').write_text(json.dumps(market, ensure_ascii=False, separators=(',', ':')), encoding='utf8')
    (DATA / 'signals.json').write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf8')

    if data_coverage < MIN_COVERAGE:
        raise SystemExit(
            f'BLOCKED: real K-line coverage {len(valid)}/{total} ({data_coverage:.2%}) below {MIN_COVERAGE:.0%}; '
            f'raw={len(klines)}, invalid={len(invalid)}, elapsed={elapsed}s'
        )
    return payload
