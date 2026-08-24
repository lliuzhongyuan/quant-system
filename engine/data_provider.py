# -*- coding: utf-8 -*-
"""V3200 real-data provider: no synthetic market values."""
import os, re, time, logging
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import requests

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
if ROOT not in sys.path: sys.path.insert(0, ROOT)
from scripts.data_sources import robust_kline, tencent_quote, eastmoney_kline, baostock_kline

UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36'
SINA='https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
log=logging.getLogger(__name__)

@dataclass
class IndexQuote:
    secid:str; code:str; name:str; price:float; change_pct:float; change_val:float; turnover:float; update_time:str

@dataclass
class SectorQuote:
    code:str; name:str; pct_change_1d:float; pct_change_5d:float; net_flow_5d:float; net_flow_10d:float; turnover_rate:float; leading_stock:str; leading_stock_chg:float; is_main_theme:bool

class DataProvider:
    def __init__(self, cache_dir='data/cache'):
        os.makedirs(cache_dir,exist_ok=True)
        self.provider_health={'status':'REAL_DATA_ONLY','universe':'LIVE_SINA','kline':['Baostock','Eastmoney','Tencent','Sina','Yahoo'],'index_realtime':'Tencent+KlineFallback','fundamentals':'UNAVAILABLE_NOT_SYNTHETIC','sector':'Eastmoney_Best_Effort'}

    def _s(self):
        s=requests.Session(); s.headers.update({'User-Agent':UA,'Accept':'application/json,text/plain,*/*','Referer':'https://finance.sina.com.cn/'}); return s

    def _universe(self):
        s=self._s(); raw=[]
        for node in ('sh_a','sz_a'):
            for page in range(1,101):
                rows=[]
                for attempt in range(4):
                    try:
                        r=s.get(SINA,params={'node':node,'page':page,'num':100,'sort':'symbol','asc':1},timeout=15); r.raise_for_status(); rows=r.json() or []; break
                    except Exception:
                        if attempt==3: log.warning('universe page failed: %s %s',node,page)
                        time.sleep(.4*(attempt+1))
                if not rows: break
                raw.extend(rows)
                if len(rows)<100: break
        return [(str(x.get('code')),str(x.get('name') or ''),x) for x in {str(x.get('code')):x for x in raw if re.fullmatch(r'\d{6}',str(x.get('code','')))}.values() if not str(x.get('code')).startswith(('68','8','4')) and 'ST' not in str(x.get('name','')).upper() and '退' not in str(x.get('name','')) and '停牌' not in str(x.get('name',''))]

    def load_universe_snapshot(self):
        items=self._universe()
        def fetch(item):
            code,name,meta=item; rows=robust_kline(code,180)
            if len(rows)<60:return None
            d=pd.DataFrame(rows); d['code']=code; d['name']=name; d['board']='创业板' if code.startswith('30') else '主板'; d['sector']='未分类（实时数据层）'; d['bars_count']=len(d)
            d['turnover_rate']=pd.to_numeric(meta.get('turnover'),errors='coerce')
            d['volume_ratio']=(d['volume']/d['volume'].rolling(5).mean()).fillna(1.0)
            for c in ('float_mv','pe','pb','roe','profit_growth','eps','deduct_net_profit'): d[c]=pd.NA
            d['is_leader']=False; d['data_quality']='REAL_KLINE_NO_FUNDAMENTALS'; return d
        out=[]
        with ThreadPoolExecutor(max_workers=24) as ex:
            fs=[ex.submit(fetch,x) for x in items]
            for f in as_completed(fs):
                try:
                    v=f.result()
                    if v is not None: out.append(v)
                except Exception: pass
        if not out: raise RuntimeError('BLOCKED: no real K-line data returned')
        return pd.concat(out,ignore_index=True)

    def _idx(self,code,name,prefix):
        try:
            q=tencent_quote(code)
            if q and q.get('price') is not None:
                p=float(q['price']); prev=float(q.get('prev_close') or p)
                return IndexQuote(f'{prefix}.{code}',code,name,p,float(q.get('change_pct') or 0),p-prev,0.0,str(q.get('quote_time') or q.get('fetched_at') or ''))
        except Exception: pass
        rows=baostock_kline(code,5) or eastmoney_kline(code,5)
        if len(rows)>=2:
            p=float(rows[-1]['close']); prev=float(rows[-2]['close'])
            return IndexQuote(f'{prefix}.{code}',code,name,p,(p/prev-1)*100 if prev else 0,p-prev,float(rows[-1].get('amount') or 0)/1e8,str(rows[-1].get('date')))
        return None

    def fetch_market_indices(self):
        meta=[('000001','上证指数','1'),('399001','深证成指','0'),('399006','创业板指','0'),('000300','沪深300','1'),('000688','科创50','1')]
        out=[q for q in (self._idx(*m) for m in meta) if q]
        if len(out)<4: raise RuntimeError(f'BLOCKED: real indices only {len(out)}/5')
        return out

    def fetch_sector_hotspots(self):
        url='https://push2.eastmoney.com/api/qt/clist/get'; params={'pn':1,'pz':100,'po':1,'np':1,'fltt':2,'invt':2,'fid':'f62','fs':'m:90+t:2','fields':'f12,f14,f2,f3,f62,f184'}
        try:
            r=requests.get(url,params=params,headers={'User-Agent':UA,'Referer':'https://quote.eastmoney.com/'},timeout=15); r.raise_for_status(); rows=(r.json().get('data') or {}).get('diff') or []
            out=[]
            for x in rows:
                try:
                    pct=float(x.get('f3') or 0); flow=float(x.get('f62') or 0); out.append(SectorQuote(str(x.get('f12') or ''),str(x.get('f14') or ''),pct,pct,flow,flow,0.0,'',0.0,pct>0 and flow>0))
                except Exception: pass
            return out
        except Exception as e:
            log.warning('sector source unavailable: %s',type(e).__name__); return []
