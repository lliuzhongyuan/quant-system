import sys, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import engine
from data_sources import robust_kline, source_probe
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

# Production K-line policy: Tencent QFQ -> Tencent legacy QFQ -> Eastmoney QFQ -> Sina.
# No synthetic/demo/stale fallback is permitted.
engine.fetch_kline = robust_kline
mode=sys.argv[1] if len(sys.argv)>1 else 'daily'

def production():
    # Build the dynamic universe accounting first. This is diagnostic and does not replace engine's own market fetch.
    universe = run_universe_snapshot()

    # Reuse the same-run provider preflight when available; never probe the same single symbol twice.
    probe_path=Path('data/provider_health.json')
    if probe_path.exists():
        try:
            payload=json.loads(probe_path.read_text(encoding='utf8'))
            probe=payload.get('provider_health') or payload.get('providers') or {}
        except Exception:
            probe=source_probe('600519')
    else:
        probe=source_probe('600519')
        Path('data').mkdir(exist_ok=True)
        Path('data/provider_health.json').write_text(json.dumps({'generated_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'providers':probe},ensure_ascii=False,indent=2),encoding='utf8')
    available=[k for k,v in probe.items() if v.get('ok')]
    if not available:
        raise SystemExit('BLOCKED: no real K-line provider passed the preflight probe')

    market=scan_all()
    # Attach the dynamic universe layers to the production snapshot before the quality gate.
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
    update_news()          # legacy Sina fetch retained as a diagnostic source
    run_news_aggregator()  # overwrite with verified multi-source news set
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
