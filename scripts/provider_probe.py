import json
from pathlib import Path
from data_sources import tencent_kline, tencent_legacy_kline, eastmoney_kline, sina_kline

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ('600519', '000001', '300750')
PROVIDERS = (
    ('Tencent QFQ', tencent_kline),
    ('Tencent Legacy', tencent_legacy_kline),
    ('Eastmoney QFQ', eastmoney_kline),
    ('Sina', sina_kline),
)

out = {}
for name, fn in PROVIDERS:
    best = {'ok': False, 'rows': 0, 'working_symbol': None, 'samples': []}
    for symbol in SAMPLES:
        try:
            rows = fn(symbol, 80)
            item = {'symbol': symbol, 'ok': len(rows) >= 80, 'rows': len(rows)}
        except Exception as e:
            item = {'symbol': symbol, 'ok': False, 'rows': 0, 'error': type(e).__name__}
        best['samples'].append(item)
        if item['rows'] > best['rows']:
            best['rows'] = item['rows']
        if item['ok'] and not best['working_symbol']:
            best['ok'] = True
            best['working_symbol'] = symbol
    out[name] = best

healthy = sum(1 for x in out.values() if x.get('ok'))
payload = {
    'provider_health': out,
    'healthy_providers': healthy,
    'required_minimum': 1,
    'sample_symbols': list(SAMPLES),
    'status': 'PASS' if healthy >= 1 else 'BLOCKED',
    'data_quality': 'real_multi_symbol_preflight',
}
path = ROOT / 'data' / 'provider_health.json'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(payload, ensure_ascii=False))
if healthy < 1:
    raise SystemExit('No K-line provider available across preflight sample symbols')
