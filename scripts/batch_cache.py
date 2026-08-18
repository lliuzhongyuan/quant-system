import json, time
from pathlib import Path
from data_sources import yahoo_batch

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'
CACHE=DATA/'kline_cache'


def main():
    universe=json.loads((DATA/'universe_stats.json').read_text(encoding='utf-8')) if (DATA/'universe_stats.json').exists() else {}
    symbols=[]
    # Prefer the persisted market universe when available; otherwise derive from signals/stocks.
    stocks_dir=DATA/'stocks'
    if stocks_dir.exists():
        symbols=[p.stem for p in stocks_dir.glob('*.json')]
    if not symbols and (DATA/'signals.json').exists():
        obj=json.loads((DATA/'signals.json').read_text(encoding='utf-8')); symbols=[str(x.get('symbol')) for x in obj.get('items',[]) if x.get('symbol')]
    if not symbols:
        raise SystemExit('No persisted symbols available for batch cache warmup')
    CACHE.mkdir(parents=True,exist_ok=True)
    success=0; failed=0
    for start in range(0,len(symbols),40):
        chunk=symbols[start:start+40]
        try:
            rows=yahoo_batch(chunk)
            for code,klines in rows.items():
                (CACHE/(code+'.json')).write_text(json.dumps({'symbol':code,'provider':'Yahoo Finance Batch','updated_at':time.time(),'klines':klines},ensure_ascii=False),encoding='utf-8')
                success+=1
            failed += len(chunk)-len(rows)
        except Exception:
            failed += len(chunk)
        print(f'batch_cache progress {min(start+40,len(symbols))}/{len(symbols)} success={success} failed={failed}')
        time.sleep(.5)
    meta={'status':'success' if success else 'blocked','provider':'Yahoo Finance Batch','requested':len(symbols),'success':success,'failed':failed,'coverage_pct':round(success/max(1,len(symbols))*100,2)}
    (DATA/'batch_cache_status.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(meta,ensure_ascii=False))
    if success==0: raise SystemExit('Batch cache warmup produced zero valid K-line datasets')

if __name__=='__main__': main()
