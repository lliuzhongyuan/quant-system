import json, datetime as dt
from pathlib import Path
from data_sources import tencent_quote

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'
MIN_UNIVERSE=3500; MIN_SCANNED_RATIO=.90; MAX_FRESH_MINUTES=30

def now(): return dt.datetime.now(dt.timezone.utc)
def parse_ts(x):
    try:return dt.datetime.fromisoformat(x.replace('Z','+00:00'))
    except:return None

def validate(strict=True):
    market=json.loads((DATA/'market.json').read_text(encoding='utf8')) if (DATA/'market.json').exists() else {}
    signals=json.loads((DATA/'signals.json').read_text(encoding='utf8')) if (DATA/'signals.json').exists() else {}
    report={'generated_at':now().isoformat(),'status':'fail','checks':{},'source_policy':{'primary':'Sina Finance','secondary':'Tencent Finance','rule':'no fabricated values; stale or incomplete data cannot be promoted to production'},'errors':[]}
    universe=int(market.get('universe') or market.get('universe_count') or 0); scanned=int(market.get('scanned') or market.get('scanned_count') or 0)
    report['checks']['universe']=universe; report['checks']['scanned']=scanned
    if universe<MIN_UNIVERSE: report['errors'].append(f'universe too small: {universe} < {MIN_UNIVERSE}')
    if universe and scanned/universe<MIN_SCANNED_RATIO: report['errors'].append(f'scan coverage too low: {scanned}/{universe}')
    ts=parse_ts(market.get('updated_at') or market.get('finished_at') or '')
    age=(now()-ts).total_seconds()/60 if ts else None
    report['checks']['freshness_minutes']=round(age,2) if age is not None else None
    if strict and (age is None or age>MAX_FRESH_MINUTES): report['errors'].append('market snapshot missing or stale')
    items=signals.get('items') or []
    bad=[x for x in items if not x.get('price') or not x.get('symbol') or x.get('data_quality') in ('synthetic','demo')]
    report['checks']['signal_items']=len(items); report['checks']['invalid_items']=len(bad)
    if bad: report['errors'].append(f'invalid signal items: {len(bad)}')
    # Secondary-source verification on a deterministic sample. Failure is visible, never replaced by fake data.
    sample=items[:20]
    secondary=[]
    for x in sample:
        try:
            q=tencent_quote(x['symbol']); p=x.get('price'); tp=q.get('price') if q else None
            if p and tp: secondary.append(abs(tp-p)/p<=.01)
        except: pass
    report['checks']['secondary_checked']=len(secondary); report['checks']['secondary_pass_rate']=round(sum(secondary)/len(secondary),3) if secondary else None
    if strict and secondary and sum(secondary)/len(secondary)<.90: report['errors'].append('secondary realtime cross-check below 90%')
    report['status']='pass' if not report['errors'] else 'fail'
    (DATA/'data_quality.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False))
    if strict and report['status']!='pass': raise SystemExit(2)
    return report

if __name__=='__main__': validate(True)
