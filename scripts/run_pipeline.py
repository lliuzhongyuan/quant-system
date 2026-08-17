import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from engine import scan_all, update_news
mode=(sys.argv[1] if len(sys.argv)>1 else 'daily')
if mode=='news': update_news()
elif mode=='scan': scan_all()
elif mode=='all': scan_all(); update_news()
else: scan_all(); update_news()
