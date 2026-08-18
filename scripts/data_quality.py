import json, datetime as dt
from pathlib import Path
from data_sources import tencent_quote, source_probe
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'
MIN_TRADABLE_UNIVERSE=3000; MIN_SCANNED_RATIO=.90; MAX_FRESH_MINUTES=30; MIN_SECONDARY_CHECKS=10; MIN_SECONDARY_PASS=.90

def now(): return dt.datetime.now(dt.timezone.utc)
def parse_ts(x):
    try:return dt.datetime.fromisoformat(x.replace('Z','+00:00'))
    except:return None

def validate(strict=True):
    market=json.loads((DATA/'market.json').read_text(encoding='utf8')) if (DATA/'market.json').exists() else {}
    signals=json.loads((DATA/'signals.json').read_text(encoding='utf8')) if (DATA/'signals.json').exists() else {}
    universe_stats=json.loads((DATA/'universe_stats.json').read_text(encoding='utf8')) if (DATA/'universe_stats.json').exists() else {}
    report={'generated_at':now().isoformat(),'status':'fail','checks':{},'source_policy':{'universe_primary':'Sina Finance dynamic A-share list','realtime_secondary':'Tencent Finance','kline_fallback_chain':['Tencent Finance QFQ','Tencent Finance Legacy QFQ','Eastmoney QFQ','Sina Finance'],'rule':'no fabricated values; stale, incomplete or single-source-only production is blocked'},'errors':[]}
    try: report['checks']['provider_probe']=source_probe('600519')
    except Exception as e: report['checks']['provider_probe_error']=type(e).__name__

    raw=int(universe_stats.get('raw_count') or market.get('universe_raw') or 0)
    unique=int(universe_stats.get('unique_count') or market.get('universe_unique') or 0)
    tradable=int(universe_stats.get('tradable_universe_count') or market.get('tradable_universe') or market.get('universe') or 0)
    scanned=int(market.get('scanned') or market.get('scanned_count') or 0)
    report['checks']['universe_raw']=raw
    report['checks']['universe_unique']=unique
    report['checks']['tradable_universe']=tradable
    report['checks']['scanned']=scanned
    if tradable<MIN_TRADABLE_UNIVERSE: report['errors'].append(f'dynamic tradable universe too small: {tradable} < {MIN_TRADABLE_UNIVERSE}')
    coverage=scanned/tradable if tradable else 0
    report['checks']['coverage_pct']=round(coverage*100,2)
    if tradable and coverage<MIN_SCANNED_RATIO: report['errors'].append(f'scan coverage too low: {scanned}/{tradable} ({coverage*100:.2f}%)')

    ts=parse_ts(market.get('updated_at') or market.get('finished_at') or ''); age=(now()-ts).total_seconds()/60 if ts else None
    report['checks']['freshness_minutes']=round(age,2) if age is not None else None
    if strict and (age is None or age>MAX_FRESH_MINUTES): report['errors'].append('market snapshot missing or stale')
    items=signals.get('items') or []; bad=[x for x in items if not x.get('price') or not x.get('symbol') or x.get('data_quality') in ('synthetic','demo')]
    report['checks']['signal_items']=len(items); report['checks']['invalid_items']=len(bad)
    if bad: report['errors'].append(f'invalid signal items: {len(bad)}')
    sample=items[:20]; secondary=[]
    for x in sample:
        try:
            q=tencent_quote(x['symbol']); p=x.get('price'); tp=q.get('price') if q else None
            if p and tp: secondary.append(abs(tp-p)/p<=.01)
        except Exception: pass
    report['checks']['secondary_checked']=len(secondary); report['checks']['secondary_pass_rate']=round(sum(secondary)/len(secondary),3) if secondary else None
    if strict and len(secondary)<MIN_SECONDARY_CHECKS: report['errors'].append(f'secondary realtime checks insufficient: {len(secondary)} < {MIN_SECONDARY_CHECKS}')
    elif strict and sum(secondary)/len(secondary)<MIN_SECONDARY_PASS: report['errors'].append('secondary realtime cross-check below 90%')
    report['status']='pass' if not report['errors'] else 'fail'
    (DATA/'data_quality.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False))
    if strict and report['status']!='pass': raise SystemExit(2)
    return report
if __name__=='__main__': validate(True)
