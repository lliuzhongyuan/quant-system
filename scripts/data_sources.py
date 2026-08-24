import datetime as dt
import threading
import json
from pathlib import Path
import requests

UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36'
SINA_K='https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData/getKLineData'
TENCENT_Q='https://qt.gtimg.cn/q='
TENCENT_K='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
TENCENT_K2='http://web.ifzq.gtimg.cn/app/kline/kline'
EAST_K='https://push2his.eastmoney.com/api/qt/stock/kline/get'
YAHOO_SPARK='https://query1.finance.yahoo.com/v7/finance/spark'
_thread=threading.local(); ROOT=Path(__file__).resolve().parents[1]; CACHE=ROOT/'data'/'kline_cache'

def session():
    s=getattr(_thread,'s',None)
    if s is None:
        s=requests.Session(); s.headers.update({'User-Agent':UA,'Accept':'application/json,text/plain,*/*','Connection':'keep-alive'}); _thread.s=s
    return s

def market(code): return 'sh' if str(code).startswith(('5','6','9')) else 'sz'
def east_secid(code): return ('1.' if market(code)=='sh' else '0.')+str(code)
def yahoo_symbol(code): return str(code)+('.SS' if market(code)=='sh' else '.SZ')
def stamp(): return dt.datetime.now(dt.timezone.utc).isoformat()

def _rows(arr,source):
    out=[]
    for x in arr or []:
        try:
            p=x.split(',') if isinstance(x,str) else list(x)
            if len(p)<6: continue
            out.append({'date':str(p[0])[:10],'open':float(p[1]),'close':float(p[2]),'high':float(p[3]),'low':float(p[4]),'volume':float(p[5]),'amount':float(p[6]) if len(p)>6 else 0.0,'source':source,'fetched_at':stamp()})
        except Exception: pass
    return out

def _yahoo_rows(node):
    try:
        ts=node.get('timestamp') or []; q=((node.get('indicators') or {}).get('quote') or [{}])[0]; out=[]
        for i,t in enumerate(ts):
            vals=[q.get(k,[None]*len(ts))[i] if i<len(q.get(k,[])) else None for k in ('open','close','high','low','volume')]
            if any(v is None for v in vals[:4]): continue
            out.append({'date':dt.datetime.fromtimestamp(t,dt.timezone.utc).date().isoformat(),'open':float(vals[0]),'close':float(vals[1]),'high':float(vals[2]),'low':float(vals[3]),'volume':float(vals[4] or 0),'amount':0.0,'source':'Yahoo Finance','fetched_at':stamp()})
        return out
    except Exception:return []

def yahoo_batch(codes,range_='1y',interval='1d',chunk=40):
    result={}; codes=list(dict.fromkeys(str(c) for c in codes)); s=session()
    for i in range(0,len(codes),chunk):
        part=codes[i:i+chunk]; r=s.get(YAHOO_SPARK,params={'symbols':','.join(yahoo_symbol(c) for c in part),'range':range_,'interval':interval},timeout=20); r.raise_for_status(); obj=r.json()
        for ys,node in (obj or {}).items():
            code=ys.split('.')[0]; rows=_yahoo_rows(node)
            if len(rows)>=80:result[code]=rows[-180:]
    return result

def load_cached(code,limit=180):
    p=CACHE/(str(code)+'.json')
    try:
        obj=json.loads(p.read_text(encoding='utf-8')); rows=obj.get('klines') if isinstance(obj,dict) else obj
        if isinstance(rows,list) and len(rows)>=80:return rows[-limit:]
    except Exception:pass
    return []

def _baostock_session():
    bs=getattr(_thread,'bs',None)
    if bs is None:
        try:
            import baostock as bs_mod; lg=bs_mod.login()
            if lg.error_code!='0':return None
            _thread.bs=bs_mod; bs=bs_mod
        except Exception:return None
    return bs

def baostock_kline(code,limit=180):
    try:
        bs=_baostock_session()
        if bs is None:return []
        end=dt.date.today().isoformat(); start=(dt.date.today()-dt.timedelta(days=420)).isoformat(); rs=bs.query_history_k_data_plus(f'{market(code)}.{code}','date,open,high,low,close,volume,amount',start_date=start,end_date=end,frequency='d',adjustflag='2'); out=[]
        if getattr(rs,'error_code','0')!='0':return []
        while rs.next():
            row=rs.get_row_data()
            if len(row)>=7 and row[0]:
                try:out.append({'date':row[0],'open':float(row[1]),'high':float(row[2]),'low':float(row[3]),'close':float(row[4]),'volume':float(row[5] or 0),'amount':float(row[6] or 0),'source':'Baostock','fetched_at':stamp()})
                except Exception:pass
        return out[-limit:] if len(out)>=80 else []
    except Exception:return []

def tencent_quote(code):
    s=session(); r=s.get(TENCENT_Q+market(code)+str(code),timeout=8); r.raise_for_status(); txt=r.content.decode('gbk','ignore')
    if '=\"' not in txt:return None
    f=txt.split('=\"',1)[1].rsplit('\"',1)[0].split('~')
    if len(f)<35:return None
    def n(i):
        try:return float(f[i])
        except:return None
    return {'symbol':str(code),'name':f[1],'price':n(3),'prev_close':n(4),'open':n(5),'volume':n(6),'change':n(31),'change_pct':n(32),'high':n(33),'low':n(34),'quote_time':f[30] if len(f)>30 else None,'source':'Tencent Finance','fetched_at':stamp()}

def tencent_kline(code,limit=180):
    s=session(); sym=market(code)+str(code); r=s.get(TENCENT_K,params={'param':f'{sym},day,,,{limit},qfq','_var':'kline_dayqfq'},timeout=8); r.raise_for_status(); obj=r.json(); node=(obj.get('data') or {}).get(sym) or {}; return _rows(node.get('qfqday') or node.get('day') or [],'Tencent Finance QFQ')

def tencent_legacy_kline(code,limit=180):
    s=session(); sym=market(code)+str(code); r=s.get(TENCENT_K2,params={'param':f'{sym},day,1,0,{limit},640,qfq'},timeout=8); r.raise_for_status(); obj=r.json(); node=(obj.get('data') or {}).get(sym) or {}; return _rows(node.get('qfqday') or node.get('day') or [],'Tencent Finance Legacy QFQ')

def eastmoney_kline(code,limit=180):
    s=session(); params={'secid':east_secid(code),'fields1':'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61','klt':101,'fqt':1,'beg':'0','end':'20500101','lmt':limit,'ut':'fa5fd1943c7b386f172d6893dbbd1d0c','rtntype':6}; r=s.get(EAST_K,params=params,headers={'Referer':'https://quote.eastmoney.com/','Origin':'https://quote.eastmoney.com'},timeout=8); r.raise_for_status(); data=(r.json().get('data') or {}); return _rows(data.get('klines') or [],'Eastmoney QFQ')

def sina_kline(code,limit=180):
    s=session(); r=s.get(SINA_K,params={'symbol':market(code)+str(code),'scale':240,'ma':'5,10,20,60','datalen':limit},headers={'Referer':'https://finance.sina.com.cn/'},timeout=8); r.raise_for_status(); return _rows(r.json() or [],'Sina Finance')
def yahoo_kline(code,limit=180):return yahoo_batch([code],range_='1y',interval='1d',chunk=1).get(str(code),[])[-limit:]

def _fresh(rows,max_age_days=5):
    if not rows:return False
    try:
        last=dt.date.fromisoformat(str(rows[-1].get('date'))[:10]); today=dt.date.today(); age=(today-last).days
        return age<=max_age_days
    except Exception:return False

def _save_cache(code,rows):
    try:
        CACHE.mkdir(parents=True,exist_ok=True); p=CACHE/(str(code)+'.json'); p.write_text(json.dumps({'updated_at':stamp(),'klines':rows},ensure_ascii=False),encoding='utf8')
    except Exception:pass

def robust_kline(code,limit=180):
    # V3200: network-first. Cache is recovery only, never the first production source.
    providers=(baostock_kline,eastmoney_kline,tencent_kline,tencent_legacy_kline,sina_kline,yahoo_kline)
    for fn in providers:
        try:
            rows=fn(code,limit)
            if len(rows)>=80 and _fresh(rows):
                _save_cache(code,rows); return rows
        except Exception:continue
    cached=load_cached(code,limit)
    return cached if _fresh(cached) else []

def source_probe(code='600519',force=True):
    out={}
    for name,fn in [('Baostock',baostock_kline),('Eastmoney QFQ',eastmoney_kline),('Tencent QFQ',tencent_kline),('Tencent Legacy',tencent_legacy_kline),('Sina',sina_kline),('Yahoo Finance',yahoo_kline)]:
        try:
            rows=fn(code,80); out[name]={'ok':len(rows)>=80,'rows':len(rows),'fresh':_fresh(rows),'last_date':rows[-1].get('date') if rows else None}
        except Exception as e:out[name]={'ok':False,'rows':0,'fresh':False,'error':type(e).__name__}
    return out

def crosscheck(code,sina=None):
    try:
        t=tencent_quote(code)
        if not t or t.get('price') is None:return {'status':'unavailable','source':'Tencent Finance'}
        if sina is None:return {'status':'verified_secondary','tencent':t}
        p=sina.get('price'); tp=t.get('price')
        if not p or not tp:return {'status':'unavailable','tencent':t}
        diff=abs(tp-p)/max(abs(p),1e-9);return {'status':'pass' if diff<=.01 else 'mismatch','price_diff_pct':round(diff*100,4),'tencent':t}
    except Exception as e:return {'status':'error','error':type(e).__name__}
