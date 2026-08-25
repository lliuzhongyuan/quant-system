# -*- coding: utf-8 -*-
"""V3200.2 bounded batch loader: real data only, no synthetic fallback."""
import json, os, time, logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from scripts.data_sources import yahoo_batch, eastmoney_kline, tencent_kline, sina_kline, baostock_kline, load_cached
log=logging.getLogger(__name__)

MAX_WORKERS=24
PER_SYMBOL_TIMEOUT=12

def _one(code, fn):
    try:
        rows=fn(code,180)
        return str(code), rows if len(rows)>=80 else []
    except Exception:
        return str(code), []

def _parallel(codes, fn, workers=MAX_WORKERS):
    out={}
    codes=list(dict.fromkeys(str(c) for c in codes))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures={ex.submit(_one,c,fn):c for c in codes}
        for f in as_completed(futures):
            code=futures[f]
            try:
                k,rows=f.result(timeout=PER_SYMBOL_TIMEOUT)
                if rows: out[k]=rows
            except Exception:
                pass
    return out

def load_real_klines(codes):
    """Network-first, batch-first. Never creates fake rows.
    Returns {code: rows} and diagnostics. Cached rows are recovery only.
    """
    codes=list(dict.fromkeys(str(c) for c in codes)); result={}; diag={'universe':len(codes),'yahoo_batch':0,'eastmoney':0,'tencent':0,'sina':0,'baostock':0,'cache':0,'missing':0}
    # Yahoo Spark is genuinely batched; use it opportunistically so one HTTP call serves many symbols.
    for start in range(0,len(codes),40):
        part=codes[start:start+40]
        try:
            got=yahoo_batch(part)
            result.update(got); diag['yahoo_batch']+=len(got)
        except Exception as e:
            log.warning('Yahoo batch failed chunk %s: %s',start,type(e).__name__)
    missing=[c for c in codes if c not in result]
    if missing:
        got=_parallel(missing,eastmoney_kline); result.update(got); diag['eastmoney']+=len(got)
    missing=[c for c in codes if c not in result]
    if missing:
        got=_parallel(missing,tencent_kline); result.update(got); diag['tencent']+=len(got)
    missing=[c for c in codes if c not in result]
    if missing:
        got=_parallel(missing,sina_kline); result.update(got); diag['sina']+=len(got)
    # Baostock is fallback only; do not let it block the entire production run indefinitely.
    if missing:
        got=_parallel(missing,baostock_kline,workers=12); result.update(got); diag['baostock']+=len(got)
    missing=[c for c in codes if c not in result]
    for c in missing:
        rows=load_cached(c,180)
        if rows:
            result[c]=rows; diag['cache']+=1
    diag['missing']=len(codes)-len(result); diag['coverage']=round(len(result)/len(codes),4) if codes else 0
    return result,diag
