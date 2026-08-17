from pathlib import Path
import datetime as dt,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from engine import market,idx,regime,w,DATA
stocks=market();indices=idx();rg=regime(indices)
w(DATA/'market.json',{'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'count':len(stocks),'source':'Sina Finance A-share list','indices':indices,'regime':rg,'items':stocks})
print('snapshot',len(stocks),'indices',len(indices),'regime',rg.get('regime'))
