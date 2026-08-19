import datetime as dt
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from data_sources import robust_kline

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'
SAMPLE_SIZE=30
WORKERS=6
MIN_ROWS=80

def load_symbols():
    p=DATA/'universe_codes.json'
    try:
        obj=json.loads(p.read_text(encoding='utf-8'))
        codes=obj.get('codes') or []
        if len(codes)>=SAMPLE_SIZE:
            return codes[:SAMPLE_SIZE]
    except Exception:
        pass
    return ['600519','000001','300750','601318','000858','600036','002594','601012','300059','000333']

def one(code):
    t=time.perf_counter()
    try:
        rows=robust_kline(code,180)
        elapsed=round((time.perf_counter()-t)*1000,1)
        return {'symbol':code,'ok':len(rows)>=MIN_ROWS,'rows':len(rows),'elapsed_ms':elapsed,'source':rows[-1].get('source') if rows else None,'latest_date':rows[-1].get('date') if rows else None}
    except Exception as e:
        return {'symbol':code,'ok':False,'rows':0,'elapsed_ms':round((time.perf_counter()-t)*1000,1),'source':None,'latest_date':None,'error':type(e).__name__}

def run():
    codes=load_symbols()[:SAMPLE_SIZE]
    started=time.perf_counter()
    results=[]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs=[ex.submit(one,c) for c in codes]
        for f in as_completed(futs): results.append(f.result())
    elapsed=round(time.perf_counter()-started,2)
    ok=[x for x in results if x['ok']]
    by_source={}
    for x in ok: by_source[x['source']]=by_source.get(x['source'],0)+1
    times=[x['elapsed_ms'] for x in results]
    payload={
        'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'sample_size':len(codes),'workers':WORKERS,'success':len(ok),'failed':len(results)-len(ok),
        'success_pct':round(len(ok)/max(1,len(results))*100,1),'elapsed_seconds':elapsed,
        'avg_elapsed_ms':round(statistics.mean(times),1) if times else 0,
        'p95_elapsed_ms':round(sorted(times)[max(0,int(len(times)*.95)-1)],1) if times else 0,
        'sources':by_source,'results':sorted(results,key=lambda x:x['symbol']),
        'status':'PASS' if len(ok)>=max(25,int(len(results)*.8)) else 'BLOCKED',
        'definition':'30只代表性股票，6线程，使用生产robust_kline链路；仅验证性能与成功率，不产生选股结果。'
    }
    DATA.mkdir(parents=True,exist_ok=True)
    (DATA/'kline_performance_probe.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(payload,ensure_ascii=False))
    if payload['status']!='PASS': raise SystemExit('K-line performance probe failed')

if __name__=='__main__': run()
