# -*- coding: utf-8 -*-
"""V3200.3 production scanner.

Keeps the production entrypoint under scripts/ so it cannot be shadowed by
scripts/engine.py. Data acquisition is delegated to the bounded real-data
loader; factor calculation remains local and uses the legacy strategy engine.
"""
import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from scripts.data_sources import baostock_kline, eastmoney_kline, tencent_kline, sina_kline, yahoo_kline, load_cached
from scripts.engine import score_signal, STRATEGIES

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
MAX_BAOSTOCK_WORKERS = 4
BAOSTOCK_DEADLINE_SECONDS = 1200
FRESH_MAX_AGE_DAYS = 5


def _fresh(rows):
    if not rows:
        return False
    try:
        last = dt.date.fromisoformat(str(rows[-1].get('date'))[:10])
        return (dt.date.today() - last).days <= FRESH_MAX_AGE_DAYS
    except Exception:
        return False


def _controlled_baostock(codes):
    """Small, bounded Baostock fan-out. Never creates hundreds of logins."""
    out = {}
    codes = list(dict.fromkeys(str(c) for c in codes))
    with ThreadPoolExecutor(max_workers=MAX_BAOSTOCK_WORKERS) as ex:
        futures = {ex.submit(baostock_kline, code, 180): code for code in codes}
        for future in as_completed(futures, timeout=BAOSTOCK_DEADLINE_SECONDS):
            code = futures[future]
            try:
                rows = future.result()
                if len(rows) >= 80 and _fresh(rows):
                    out[code] = rows
            except Exception:
                continue
    return out


def _http_fallback(codes):
    """Use the existing HTTP providers only for the remaining gap."""
    providers = (eastmoney_kline, tencent_kline, sina_kline, yahoo_kline)
    result = {}
    for fn in providers:
        if not codes:
            break
        next_result = {}
        for code in codes:
            try:
                rows = fn(code, 180)
                if len(rows) >= 80 and _fresh(rows):
                    next_result[code] = rows
            except Exception:
                continue
        result.update(next_result)
        codes = [c for c in codes if c not in result]
    return result


def load_real_klines_v3200(codes):
    codes = list(dict.fromkeys(str(c) for c in codes))
    result = {}
    diag = {
        'universe': len(codes),
        'baostock_controlled': 0,
        'eastmoney': 0,
        'tencent': 0,
        'sina': 0,
        'yahoo': 0,
        'cache': 0,
        'missing': 0,
        'coverage': 0.0,
        'baostock_workers': MAX_BAOSTOCK_WORKERS,
        'baostock_deadline_seconds': BAOSTOCK_DEADLINE_SECONDS,
        'fresh_max_age_days': FRESH_MAX_AGE_DAYS,
    }
    got = _controlled_baostock(codes)
    result.update(got)
    diag['baostock_controlled'] = len(got)

    missing = [c for c in codes if c not in result]
    for name, fn in [('eastmoney', eastmoney_kline), ('tencent', tencent_kline), ('sina', sina_kline), ('yahoo', yahoo_kline)]:
        if not missing:
            break
        current = {}
        for code in missing:
            try:
                rows = fn(code, 180)
                if len(rows) >= 80 and _fresh(rows):
                    current[code] = rows
            except Exception:
                continue
        result.update(current)
        diag[name] = len(current)
        missing = [c for c in missing if c not in result]

    for code in list(missing):
        try:
            rows = load_cached(code, 180)
            if len(rows) >= 80 and _fresh(rows):
                result[code] = rows
                diag['cache'] += 1
        except Exception:
            continue

    diag['missing'] = len(codes) - len(result)
    diag['coverage'] = round(len(result) / len(codes), 4) if codes else 0.0
    return result, diag


def run(verified_market, verified_indices):
    codes = [str(x['symbol']) for x in verified_market]
    klines, diag = load_real_klines_v3200(codes)
    signals = []
    failed = []
    for item in verified_market:
        code = str(item['symbol'])
        rows = klines.get(code, [])
        if len(rows) < 80:
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
    data_coverage = len(klines) / total if total else 0.0
    signal_coverage = len(signals) / total if total else 0.0
    market = {
        'updated_at': now,
        'universe': total,
        'kline_real_scanned': len(klines),
        'scanned': len(signals),
        'failed': len(failed),
        'kline_coverage': round(data_coverage, 4),
        'signal_coverage': round(signal_coverage, 4),
        'indices': verified_indices,
        'data_quality': 'REAL_KLINE_BATCH_V3200_3',
        'batch_diagnostics': diag,
        'universe_snapshot_frozen': True,
    }
    payload = {
        'updated_at': now,
        'universe': total,
        'kline_real_scanned': len(klines),
        'scanned': len(signals),
        'failed': len(failed),
        'kline_coverage': round(data_coverage, 4),
        'signal_coverage': round(signal_coverage, 4),
        'items': sorted(signals, key=lambda x: (x.get('tier') == 'S', x.get('opportunity_score', 0), x.get('quality_score', 0)), reverse=True),
        'strategy_catalog': STRATEGIES,
        'methodology': 'A-H multi-factor technical engine; D is a cost/volume proxy, not true chip distribution.',
        'batch_diagnostics': diag,
        'data_quality': 'technical_real_batch_v3200_3',
    }
    (DATA / 'market.json').write_text(json.dumps(market, ensure_ascii=False, separators=(',', ':')), encoding='utf8')
    (DATA / 'signals.json').write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf8')
    if data_coverage < 0.90:
        raise SystemExit(f'BLOCKED: real K-line coverage {len(klines)}/{total} ({data_coverage:.2%}) below 90%')
    return payload
