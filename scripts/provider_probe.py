import json, time
from pathlib import Path
from data_sources import baostock_kline, yahoo_kline, tencent_kline, tencent_legacy_kline, eastmoney_kline, sina_kline
ROOT=Path(__file__).resolve().parents[1]
SAMPLES=('600519','000001','300750')
PROVIDERS=(('Baostock',baostock_kline),('Yahoo Finance Batch',yahoo_kline),('Tencent QFQ',tencent_kline),('Tencent Legacy',tencent_legacy_kline),('Eastmoney QFQ',eastmoney_kline),('Sina',sina_kline))

def probe_provider(fn,samples,attempts=2):
    best={'ok':False,'rows':0,'working_symbol':None,'samples':[]}
    for symbol in samples:
        last_error=None; rows=[]
        for attempt in range(attempts):
            try: rows=fn(symbol,80); last_error=None; break
            except Exception as e:
                last_error=type(e).__name__
                if attempt+1<attempts: time.sleep(2+attempt*2)
        item={'symbol':symbol,'ok':len(rows)>=80,'rows':len(rows)}
        if last_error and not item['ok']: item['error']=last_error
        best['samples'].append(item); best['rows']=max(best['rows'],len(rows))
        if item['ok'] and not best['working_symbol']: best['ok']=True; best['working_symbol']=symbol
    return best

def run():
    out={}
    for name,fn in PROVIDERS:
        out[name]=probe_provider(fn,SAMPLES); time.sleep(1)
    healthy=sum(1 for x in out.values() if x.get('ok'))
    payload={'provider_health':out,'healthy_providers':healthy,'required_minimum':1,'sample_symbols':list(SAMPLES),'status':'PASS' if healthy>=1 else 'BLOCKED','data_quality':'real_free_multi_symbol_preflight_retry'}
    path=ROOT/'data'/'provider_health.json'; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(payload,ensure_ascii=False))
    if healthy<1: raise SystemExit('No free K-line provider available across preflight after retries')
    return payload
if __name__=='__main__': run()
