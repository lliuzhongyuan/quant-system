import json, time
from pathlib import Path
from data_sources import yahoo_kline, baostock_kline, tencent_kline, tencent_legacy_kline, eastmoney_kline, sina_kline

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ('600519', '000001', '300750')
MIN_ROWS = 80
PROVIDERS = (
    ('Yahoo Finance', yahoo_kline),
    ('Baostock', baostock_kline),
    ('Tencent QFQ', tencent_kline),
    ('Tencent Legacy', tencent_legacy_kline),
    ('Eastmoney QFQ', eastmoney_kline),
    ('Sina', sina_kline),
)


def probe_provider(fn, samples):
    items = []
    for symbol in samples:
        last_error = None
        rows = []
        for attempt in range(2):
            try:
                rows = fn(symbol, MIN_ROWS)
                last_error = None
                break
            except Exception as e:
                last_error = type(e).__name__
                if attempt == 0:
                    time.sleep(2)
        item = {'symbol': symbol, 'ok': len(rows) >= MIN_ROWS, 'rows': len(rows)}
        if last_error and not item['ok']:
            item['error'] = last_error
        items.append(item)

    passed = sum(1 for x in items if x['ok'])
    return {
        'ok': passed == len(samples),
        'passed_symbols': passed,
        'total_symbols': len(samples),
        'coverage_pct': round(passed / len(samples) * 100, 1),
        'working_symbol': next((x['symbol'] for x in items if x['ok']), None),
        'rows': max((x['rows'] for x in items), default=0),
        'samples': items,
    }


def run():
    out = {}
    for name, fn in PROVIDERS:
        out[name] = probe_provider(fn, SAMPLES)
        time.sleep(0.5)

    healthy = sum(1 for x in out.values() if x.get('ok'))
    payload = {
        'provider_health': out,
        'healthy_providers': healthy,
        'required_minimum': 1,
        'required_symbol_coverage': '3/3',
        'min_rows_per_symbol': MIN_ROWS,
        'sample_symbols': list(SAMPLES),
        'status': 'PASS' if healthy >= 1 else 'BLOCKED',
        'data_quality': 'real_free_multi_symbol_preflight_3of3',
    }
    path = ROOT / 'data' / 'provider_health.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(payload, ensure_ascii=False))
    if healthy < 1:
        raise SystemExit('No free K-line provider passed 3/3 preflight')
    return payload


if __name__ == '__main__':
    run()
