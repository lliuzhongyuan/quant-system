import sys
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

engine.fetch_kline = robust_kline
mode=sys.argv[1] if len(sys.argv)>1 else 'daily'

def production():
    scan_all()
    validate(True)
    run_sector()
    update_news()
    run_backtest()
    run_strategy_board()
    run_portfolio()
    run_archive()
    run_walkforward()

if mode=='news': update_news()
elif mode=='scan': production()
elif mode=='backtest': run_backtest()
elif mode in ('all','daily'): production()
else: raise SystemExit(f'unknown mode: {mode}')
