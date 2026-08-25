import sys, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'scripts'
sys.path.insert(0,str(ROOT))
sys.path.insert(1,str(SCRIPTS))

import scripts.engine as legacy_engine
from data_sources import robust_kline
from index_sources import fetch_indices
from backtest import run as run_backtest
from data_quality import validate
from strategy_board import run as run_strategy_board
from portfolio_engine import run as run_portfolio
from archive_market import run as run_archive
from walkforward import run as run_walkforward
from sector_engine import run as run_sector
from news_aggregator import run as run_news_aggregator
from universe_snapshot import run as run_universe_snapshot
from engine.batch_scan import run as run_batch_scan

legacy_engine.fetch_kline=robust_kline
legacy_engine.fetch_indices=fetch_indices
update_news=legacy_engine.update_news
mode=sys.argv[1] if len(sys.argv)>1 else 'daily'
def read_json(path): return json.loads(Path(path).read_text(encoding='utf8'))
def build_universe_once():
 p=Path('data/universe_stats.json')
 if not p.exists() or not Path('data/universe_market.json').exists(): x=run_universe_snapshot()
 else:
  x=read_json(p); n=int(x.get('tradable_universe_count') or 0); items=read_json('data/universe_market.json').get('items',[])
  if n<3000 or len(items)<n*.95: x=run_universe_snapshot()
 n=int(x.get('tradable_universe_count') or 0); items=read_json('data/universe_market.json').get('items',[]) if Path('data/universe_market.json').exists() else []
 if n<3000 or len(items)<n*.95: raise SystemExit(f'BLOCKED: dynamic universe incomplete: stats={n}, market_items={len(items)}')
 return x
def load_verified_market():
 obj=read_json('data/universe_market.json'); items=obj.get('items') or []; n=int(obj.get('tradable_universe_count') or 0)
 if n<3000 or len(items)<n*.95: raise SystemExit(f'BLOCKED: verified universe incomplete: {len(items)}/{n}')
 def num(x,default=None):
  try:
   v=float(x); return default if math.isnan(v) else v
  except Exception:return default
 def exchange(code): return 'sh' if str(code).startswith(('5','6','9')) else 'sz'
 out=[]
 for x in items:
  code=str(x.get('code') or ''); name=str(x.get('name') or '')
  if not code or not name: continue
  mv=num(x.get('mktcap')); nmc=num(x.get('nmc'))
  out.append({'code':code+('.SH' if exchange(code)=='sh' else '.SZ'),'symbol':code,'name':name,'price':num(x.get('trade')),'change_pct':num(x.get('changepercent'),0),'change':num(x.get('pricechange'),0),'volume':num(x.get('volume'),0),'amount':num(x.get('amount'),0),'turnover':num(x.get('turnoverratio'),0),'pe':num(x.get('per')),'pb':num(x.get('pb')),'high':num(x.get('high')),'low':num(x.get('low')),'open':num(x.get('open')),'prev_close':num(x.get('settlement')),'total_mv':mv*10000 if mv is not None else None,'float_mv':nmc*10000 if nmc is not None else None,'sector':'未分类'})
 if len(out)<n*.95: raise SystemExit(f'BLOCKED: verified universe conversion incomplete: {len(out)}/{n}')
 return out
def production():
 universe=build_universe_once()
 payload=read_json('data/provider_health.json') if Path('data/provider_health.json').exists() else {}
 probe=payload.get('provider_health') or {}; healthy=int(payload.get('healthy_providers') or sum(1 for v in probe.values() if v.get('ok')))
 if payload.get('status')!='PASS' or healthy<1: raise SystemExit('BLOCKED: provider preflight did not pass')
 index_health=read_json('data/index_provider_health.json') if Path('data/index_provider_health.json').exists() else {}
 if index_health.get('status')!='PASS' or int(index_health.get('healthy') or 0)<4: raise SystemExit('BLOCKED: index provider preflight did not pass all 4 major indexes')
 verified_indices=fetch_indices(); expected={'sh000001','sz399001','sz399006','sh000300'}; actual={str(x.get('code')) for x in verified_indices if x.get('code')}
 if actual!=expected or len(verified_indices)!=4 or any(x.get('price') is None or x.get('change_pct') is None or x.get('kline_rows',0)<60 for x in verified_indices): raise SystemExit('BLOCKED: verified index snapshot incomplete')
 verified_market=load_verified_market()
 if len(verified_market)<int(universe.get('tradable_universe_count') or 0)*.9: raise SystemExit(f"BLOCKED: verified market snapshot coverage too low: {len(verified_market)}/{universe.get('tradable_universe_count')}")
 run_batch_scan(verified_market,verified_indices)
 mp=Path('data/market.json')
 if mp.exists():
  o=read_json(mp); o.update({'universe_raw':universe.get('raw_count',0),'universe_unique':universe.get('unique_count',0),'universe_valid_codes':universe.get('valid_code_count',0),'tradable_universe':universe.get('tradable_universe_count',0),'universe_excluded':universe.get('excluded',{}),'coverage_denominator':universe.get('tradable_universe_count',0),'coverage_definition':'scanned / dynamic tradable universe','verified_index_snapshot':verified_indices,'universe_snapshot_frozen':True,'universe_fallback_used':bool(universe.get('fallback_used',False))}); mp.write_text(json.dumps(o,ensure_ascii=False,separators=(',',':')),encoding='utf8')
 sp=Path('data/signals.json')
 if sp.exists():
  o=read_json(sp); o.update({'universe_raw':universe.get('raw_count',0),'universe_unique':universe.get('unique_count',0),'tradable_universe':universe.get('tradable_universe_count',0),'coverage_denominator':universe.get('tradable_universe_count',0),'universe_snapshot_frozen':True,'universe_fallback_used':bool(universe.get('fallback_used',False))}); sp.write_text(json.dumps(o,ensure_ascii=False,separators=(',',':')),encoding='utf8')
 validate(True); run_sector(); update_news(); run_news_aggregator(); run_backtest(); run_strategy_board(); run_portfolio(); run_archive(); run_walkforward()
if mode=='news': run_news_aggregator()
elif mode in ('scan','all','daily'): production()
else: raise SystemExit(f'unknown mode: {mode}')
