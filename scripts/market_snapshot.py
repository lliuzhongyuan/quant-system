import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from engine import fetch_market, atomic_write, DATA
import datetime as dt
stocks=fetch_market()
atomic_write(DATA/'market.json',{'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'count':len(stocks),'source':'Eastmoney clist/get','items':stocks})
print('snapshot',len(stocks))
