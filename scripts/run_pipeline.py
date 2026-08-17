import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from engine import scan_all, update_news
from backtest import run as run_backtest
mode=sys.argv[1] if len(sys.argv)>1 else 'daily'
if mode=='news': update_news()
elif mode=='scan': scan_all()
elif mode=='backtest': run_backtest()
elif mode=='all':
    scan_all(); update_news(); run_backtest()
else:
    scan_all(); update_news(); run_backtest()
