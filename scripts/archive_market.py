import json, datetime as dt
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; ARCH=DATA/'history'; ARCH.mkdir(parents=True,exist_ok=True)

def run():
    src=DATA/'market.json'
    if not src.exists(): raise SystemExit('market.json missing')
    obj=json.loads(src.read_text(encoding='utf8')); day=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d')
    items=obj.get('items') or []
    compact=[{'symbol':x.get('symbol'),'name':x.get('name'),'price':x.get('price'),'change_pct':x.get('change_pct')} for x in items if x.get('symbol')]
    out=ARCH/f'universe_{day}.json'; out.write_text(json.dumps({'date':day,'source':obj.get('source'),'data_status':obj.get('data_status','unknown'),'universe':len(compact),'items':compact},ensure_ascii=False,separators=(',',':')),encoding='utf8')
    index={'archived_at':dt.datetime.now(dt.timezone.utc).isoformat(),'file':out.name,'universe':len(compact),'source':obj.get('source'),'policy':'compact universe membership/quote snapshot; historical prices are fetched from real source during research'}
    (ARCH/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(index,ensure_ascii=False))
if __name__=='__main__':run()
