import sys, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import engine
from data_sources import robust_kline
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

def production():
    # The workflow already builds the dynamic universe before entering the
    # production pipeline. Reuse that verified snapshot instead of querying
    # Sina a second time, which can hit a transient page/JSON failure.
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

    market=scan_all()
    market_path=Path('data/market.json')
    if market_path.exists():
        market_obj=json.loads(market_path.read_text(encoding='utf8'))
        market_obj.update({
            'universe_raw': universe.get('raw_count', 0),
            'universe_unique': universe.get('unique_count', 0),
            'universe_valid_codes': universe.get('valid_code_count', 0),
            'tradable_universe': universe.get('tradable_universe_count', 0),
            'universe_excluded': universe.get('excluded', {}),
            'coverage_denominator': universe.get('tradable_universe_count', 0),
            'coverage_definition': 'scanned / dynamic tradable universe'
        })
        market_path.write_text(json.dumps(market_obj,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    signals_path=Path('data/signals.json')
    if signals_path.exists():
        signals_obj=json.loads(signals_path.read_text(encoding='utf8'))
        signals_obj.update({
            'universe_raw': universe.get('raw_count', 0),
            'universe_unique': universe.get('unique_count', 0),
            'tradable_universe': universe.get('tradable_universe_count', 0),
            'coverage_denominator': universe.get('tradable_universe_count', 0)
        })
        signals_path.write_text(json.dumps(signals_obj,ensure_ascii=False,separators=(',',':')),encoding='utf8')

    validate(True)
    run_sector()
    update_news()
    run_news_aggregator()
    run_backtest()
    run_strategy_board()
    run_portfolio()
    run_archive()
    run_walkforward()

if mode=='news': run_news_aggregator()
elif mode=='scan': production()
elif mode=='backtest': run_backtest()
elif mode in ('all','daily'): production()
else: raise SystemExit(f'unknown mode: {mode}')
