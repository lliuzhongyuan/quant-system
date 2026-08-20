import sys, json, math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import engine
from data_sources import robust_kline
from index_sources import fetch_indices
from engine import scan_all, update_news
from backtest import run as run_backtest
from data_quality import validate
from strategy_board import run as run_strategy_board
from portfolio_engine import run as run_portfolio
from archive_market import run as run_archive
from walkforward import run as run_walkforward
from sector_engine import run as run_sector
from news_aggregator import run as run_news_aggregator
from universe_snapshot import run as run_universe_snapshot

engine.fetch_kline = robust_kline
engine.fetch_indices = fetch_indices
mode=sys.argv[1] if len(sys.argv)>1 else 'daily'

def load_valid_universe_snapshot():
    p=Path('data/universe_stats.json')
    if p.exists():
        try:
            x=json.loads(p.read_text(encoding='utf8'))
            n=int(x.get('tradable_universe_count') or 0)
            if n>=3000:
                return x
        except Exception:
            pass
    return run_universe_snapshot()

def load_verified_market():
    """Use the exact market snapshot produced by the preflight universe step."""
    p=Path('data/universe_market.json')
    if not p.exists():
        raise SystemExit('BLOCKED: verified universe market snapshot is missing')
    try:
        obj=json.loads(p.read_text(encoding='utf8'))
        items=obj.get('items') or []
        if int(obj.get('tradable_universe_count') or 0) < 3000 or len(items) < 3000:
            raise ValueError('verified universe market snapshot is incomplete')
    except Exception as e:
        raise SystemExit(f'BLOCKED: invalid verified universe market snapshot: {type(e).__name__}')

    def num(x, default=None):
        try:
            v=float(x)
            return default if math.isnan(v) else v
        except Exception:
            return default
    def exchange(code):
        return 'sh' if str(code).startswith(('5','6','9')) else 'sz'

    out=[]
    for x in items:
        code=str(x.get('code') or ''); name=str(x.get('name') or '')
        if not code or not name: continue
        mv=num(x.get('mktcap')); nmc=num(x.get('nmc'))
        out.append({'code':code+('.SH' if exchange(code)=='sh' else '.SZ'),'symbol':code,'name':name,
                    'price':num(x.get('trade')),'change_pct':num(x.get('changepercent'),0),
                    'change':num(x.get('pricechange'),0),'volume':num(x.get('volume'),0),
                    'amount':num(x.get('amount'),0),'turnover':num(x.get('turnoverratio'),0),
                    'pe':num(x.get('per')),'pb':num(x.get('pb')),'high':num(x.get('high')),
                    'low':num(x.get('low')),'open':num(x.get('open')),
                    'prev_close':num(x.get('settlement')),
                    'total_mv':mv*10000 if mv is not None else None,
                    'float_mv':nmc*10000 if nmc is not None else None,'sector':'未分类'})
    if len(out) < 3000:
        raise SystemExit(f'BLOCKED: verified market snapshot converted to only {len(out)} stocks')
    return out

def production():
    universe = load_valid_universe_snapshot()
    probe_path = Path('data/provider_health.json')
    if not probe_path.exists():
        raise SystemExit('BLOCKED: provider preflight result is missing')
    try:
        payload = json.loads(probe_path.read_text(encoding='utf8'))
        probe = payload.get('provider_health') or {}
        healthy = int(payload.get('healthy_providers') or sum(1 for v in probe.values() if v.get('ok')))
    except Exception as e:
        raise SystemExit(f'BLOCKED: invalid provider preflight result: {type(e).__name__}')
    if payload.get('status') != 'PASS' or healthy < 1:
        raise SystemExit('BLOCKED: provider preflight did not pass')

    index_health_path=Path('data/index_provider_health.json')
    if not index_health_path.exists():
        raise SystemExit('BLOCKED: index provider preflight result is missing')
    try:
        index_health=json.loads(index_health_path.read_text(encoding='utf8'))
    except Exception as e:
        raise SystemExit(f'BLOCKED: invalid index provider preflight result: {type(e).__name__}')
    if index_health.get('status') != 'PASS' or int(index_health.get('healthy') or 0) < 4:
        raise SystemExit('BLOCKED: index provider preflight did not pass all 4 major indexes')

    verified_market=load_verified_market()
    if len(verified_market) < int(universe.get('tradable_universe_count') or 0) * .9:
        raise SystemExit(f"BLOCKED: verified market snapshot coverage too low: {len(verified_market)}/{universe.get('tradable_universe_count')}")
    engine.fetch_market=lambda: verified_market

    market=scan_all()
    market_path=Path('data/market.json')
    if market_path.exists():
        market_obj=json.loads(market_path.read_text(encoding='utf8'))
        market_obj.update({'universe_raw': universe.get('raw_count', 0),'universe_unique': universe.get('unique_count', 0),'universe_valid_codes': universe.get('valid_code_count', 0),'tradable_universe': universe.get('tradable_universe_count', 0),'universe_excluded': universe.get('excluded', {}),'coverage_denominator': universe.get('tradable_universe_count', 0),'coverage_definition': 'scanned / dynamic tradable universe'})
        market_path.write_text(json.dumps(market_obj,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    signals_path=Path('data/signals.json')
    if signals_path.exists():
        signals_obj=json.loads(signals_path.read_text(encoding='utf8'))
        signals_obj.update({'universe_raw': universe.get('raw_count', 0),'universe_unique': universe.get('unique_count', 0),'tradable_universe': universe.get('tradable_universe_count', 0),'coverage_denominator': universe.get('tradable_universe_count', 0)})
        signals_path.write_text(json.dumps(signals_obj,ensure_ascii=False,separators=(',',':')),encoding='utf8')

    validate(True)
    run_sector(); update_news(); run_news_aggregator(); run_backtest(); run_strategy_board(); run_portfolio(); run_archive(); run_walkforward()

if mode=='news': run_news_aggregator()
elif mode=='scan': production()
elif mode in ('all','daily'): production()
else: raise SystemExit(f'unknown mode: {mode}')