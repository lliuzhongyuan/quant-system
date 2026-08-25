# -*- coding: utf-8 -*-
"""V3200.2 bounded batch loader: real data only, no synthetic fallback."""
import json, logging, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from scripts.data_sources import eastmoney_kline, tencent_kline, sina_kline, load_cached, market
log=logging.getLogger(__name__)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36'
YAHOO='https://query1.finance.yahoo.com/v7/finance/spark'
MAX_WORKERS=32

def _yahoo_symbol(c): return str(c)+('.SS' if market(c)=='sh' else '.SZ')
def _yahoo_rows(node):
    try:
        if isinstance(node,dict) and 'response' in node:
            response=(node.get('response') or [{}])[0]; node=response
        ts=node.get('timestamp') or []; q=((node.get('indicators') or {}).get('quote') or [{}])[0]; out=[]
        for i,t in enumerate(ts):
            vals=[q.get(k,[None]*len(ts))[i] if i<len(q.get(k,[])) else None for k in ('open','close','high','low','volume')]
            if any(v is None for v in vals[:4]): continue
            out.append({'date':dt.datetime.fromtimestamp(t,dt.timezone.utc).date().isoformat(),'open':float(vals[0]),'close':float(vals[1]),'high':float(vals[2]),'low':float(vals[3]),'volume':float(vals[4] or 0),'amount':0.0,'source':'Yahoo Finance','fetched_at':dt.datetime.now(dt.timezone.utc).isoformat()})
        return out[-180:]
    except Exception:return []

def _yahoo_batch(codes):
    s=requests.Session(); s.headers.update({'User-Agent':UA,'Accept':'application/json,text/plain,*/*'})
    out={}
    for start in range(0,len(codes),40):
        part=codes[start:start+40]
        try:
            r=s.get(YAHOO,params={'symbols':','.join(_yahoo_symbol(c) for c in part),'range':'1y','interval':'1d'},timeout=20); r.raise_for_status(); obj=r.json()
            nodes=[]
            if isinstance(obj.get('spark'),dict): nodes=obj['spark'].get('result') or []
            elif isinstance(obj,dict): nodes=[v for v in obj.values() if isinstance(v,dict) and ('timestamp' in v or 'response' in v)]
            for node in nodes:
                sym=node.get('symbol') or ((node.get('response') or [{}])[0].get('meta') or {}).get('symbol')
                if not sym: continue
                code=sym.split('.')[0]; rows=_yahoo_rows(node)
                if len(rows)>=80: out[code]=rows
        except Exception as e: log.warning('Yahoo batch chunk %s failed: %s',start,type(e).__name__)
    return out

def _parallel(codes,fn):
    out={}; codes=list(dict.fromkeys(str(c) for c in codes))
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures={ex.submit(fn,c,180):c for c in codes}
        for f in as_completed(futures):
            code=futures[f]
            try:
                rows=f.result()
                if len(rows)>=80: out[str(code)]=rows
            except Exception: pass
    return out

def load_real_klines(codes):
    """Batch-first real data. Every network provider has its own request timeout.
    No random/synthetic data is ever generated. Cache is recovery only.
    """
    codes=list(dict.fromkeys(str(c) for c in codes)); result={}; diag={'universe':len(codes),'yahoo_batch':0,'eastmoney':0,'tencent':0,'sina':0,'baostock_preflight_only':True,'cache':0,'missing':0}
    got=_yahoo_batch(codes); result.update(got); diag['yahoo_batch']=len(got)
    missing=[c for c in codes if c not in result]
    if missing:
        got=_parallel(missing,eastmoney_kline); result.update(got); diag['eastmoney']=len(got)
    missing=[c for c in codes if c not in result]
    if missing:
        got=_parallel(missing,tencent_kline); result.update(got); diag['tencent']=len(got)
    missing=[c for c in codes if c not in result]
    if missing:
        got=_parallel(missing,sina_kline); result.update(got); diag['sina']=len(got)
    missing=[c for c in codes if c not in result]
    for c in missing:
        rows=load_cached(c,180)
        if rows:
            result[c]=rows; diag['cache']+=1
    diag['missing']=len(codes)-len(result); diag['coverage']=round(len(result)/len(codes),4) if codes else 0
    return result,diag
