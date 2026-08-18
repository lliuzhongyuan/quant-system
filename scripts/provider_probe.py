import json
from pathlib import Path
from data_sources import source_probe

ROOT = Path(__file__).resolve().parents[1]
out = source_probe()
healthy = sum(1 for x in out.values() if x.get('ok'))
payload = {
    'provider_health': out,
    'healthy_providers': healthy,
    'required_minimum': 1,
    'status': 'PASS' if healthy >= 1 else 'BLOCKED',
}
path = ROOT / 'data' / 'provider_health.json'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(payload, ensure_ascii=False))
if healthy < 1:
    raise SystemExit('No K-line provider available; production scan blocked')
