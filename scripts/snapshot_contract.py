import json,datetime as dt
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'data'/'market.json'
if not p.exists(): raise SystemExit('market.json missing')
x=json.loads(p.read_text(encoding='utf8')); n=int(x.get('universe') or x.get('universe_count') or 0); s=int(x.get('scanned') or x.get('scanned_count') or 0)
if n<3500: raise SystemExit(f'real market snapshot blocked: universe={n}')
if not x.get('updated_at'): raise SystemExit('real market snapshot blocked: no timestamp')
print(json.dumps({'status':'pass','universe':n,'scanned':s,'source':x.get('source'),'updated_at':x.get('updated_at')},ensure_ascii=False))
