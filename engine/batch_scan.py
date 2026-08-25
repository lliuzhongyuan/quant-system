# -*- coding: utf-8 -*-
"""V3200.2 production scanner: batch real K-lines, then pure local factor calculation."""
import json, datetime as dt
from pathlib import Path
from engine.batch_data import load_real_klines
from scripts.engine import score_signal, STRATEGIES

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'

def run(verified_market, verified_indices):
    items=verified_market; codes=[str(x['symbol']) for x in items]
    klines,diag=load_real_klines(codes)
    signals=[]; failed=[]
    for s in items:
        code=str(s['symbol']); rows=klines.get(code,[])
        if len(rows)<80:
            failed.append(code); continue
        try:
            r=score_signal(s,rows)
            if r: signals.append(r)
            else: failed.append(code)
        except Exception:
            failed.append(code)
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    total=len(items); scanned=len(signals); coverage=scanned/total if total else 0
    market={'updated_at':now,'universe':total,'scanned':scanned,'failed':len(failed),'coverage':round(coverage,4),'indices':verified_indices,'data_quality':'REAL_KLINE_BATCH','batch_diagnostics':diag,'universe_snapshot_frozen':True}
    payload={'updated_at':now,'universe':total,'scanned':scanned,'failed':len(failed),'coverage':round(coverage,4),'items':sorted(signals,key=lambda x:(x.get('tier')=='S',x.get('opportunity_score',0),x.get('quality_score',0)),reverse=True),'strategy_catalog':STRATEGIES,'methodology':'A-H multi-factor technical engine; D is a cost/volume proxy, not true chip distribution.','batch_diagnostics':diag,'data_quality':'technical_real_batch'}
    (DATA/'market.json').write_text(json.dumps(market,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    (DATA/'signals.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    if coverage < .90:
        raise SystemExit(f'BLOCKED: real K-line scan coverage {scanned}/{total} ({coverage:.2%}) below 90%')
    return payload
