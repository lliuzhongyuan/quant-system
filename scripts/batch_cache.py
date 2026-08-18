import json, time
from pathlib import Path
from data_sources import yahoo_batch
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; CACHE=DATA/'kline_cache'

def main():
    p=DATA/'universe_codes.json'
    if not p.exists(): raise SystemExit('universe_codes.json missing')
    symbols=json.loads(p.read_text(encoding='utf-8')).get('codes') or []
    if len(symbols)<3000: raise SystemExit(f'Universe too small for batch cache: {len(symbols)}')
    CACHE.mkdir(parents=True,exist_ok=True); success=0; failed=0
    for start in range(0,len(symbols),40):
        chunk=symbols[start:start+40]
        try:
            rows=yahoo_batch(chunk)
            for code,klines in rows.items():
                (CACHE/(code+'.json')).write_text(json.dumps({'symbol':code,'provider':'Yahoo Finance Batch','updated_at':time.time(),'klines':klines},ensure_ascii=False),encoding='utf-8'); success+=1
            failed+=len(chunk)-len(rows)
        except Exception as e:
            failed+=len(chunk); print(f'batch_error start={start} error={type(e).__name__}')
        print(f'batch_cache progress {min(start+40,len(symbols))}/{len(symbols)} success={success} failed={failed}')
        time.sleep(.5)
    meta={'status':'success' if success else 'blocked','provider':'Yahoo Finance Batch','requested':len(symbols),'success':success,'failed':failed,'coverage_pct':round(success/max(1,len(symbols))*100,2)}
    (DATA/'batch_cache_status.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(meta,ensure_ascii=False))
    if success==0: raise SystemExit('Batch cache warmup produced zero valid K-line datasets')

if __name__=='__main__': main()
