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
_thread=threading.local()

def session():
    s=getattr(_thread,'s',None)
    if s is None:
        s=requests.Session()
        s.headers.update({'User-Agent':UA,'Accept':'application/json,text/plain,*/*','Connection':'keep-alive'})
        _thread.s=s
    return s

def market(code): return 'sh' if str(code).startswith(('5','6','9')) else 'sz'
def east_secid(code): return ('1.' if market(code)=='sh' else '0.')+str(code)
def stamp(): return dt.datetime.now(dt.timezone.utc).isoformat()

def _rows(arr,source):
    out=[]
    for x in arr or []:
        try:
            if isinstance(x,str):
                p=x.split(',')
                if len(p)<6: continue
            else:
                p=list(x)
                if len(p)<6: continue
            out.append({'date':str(p[0])[:10],'open':float(p[1]),'close':float(p[2]),'high':float(p[3]),'low':float(p[4]),'volume':float(p[5]),'amount':float(p[6]) if len(p)>6 else 0.0,'source':source,'fetched_at':stamp()})
        except Exception: pass
    return out

def tencent_quote(code):
    s=session(); sym=market(code)+str(code)
    r=s.get(TENCENT_Q+sym,timeout=8); r.raise_for_status(); txt=r.content.decode('gbk','ignore')
    if '=\"' not in txt:return None
    f=txt.split('=\"',1)[1].rsplit('\"',1)[0].split('~')
    if len(f)<35:return None
    def n(i):
        try:return float(f[i])
        except:return None
    return {'symbol':str(code),'name':f[1],'price':n(3),'prev_close':n(4),'open':n(5),'volume':n(6),'change':n(31),'change_pct':n(32),'high':n(33),'low':n(34),'quote_time':f[30] if len(f)>30 else None,'source':'Tencent Finance','fetched_at':stamp()}

def tencent_kline(code,limit=180):
    s=session(); sym=market(code)+str(code)
    r=s.get(TENCENT_K,params={'param':f'{sym},day,,,{limit},qfq','_var':'kline_dayqfq'},timeout=8); r.raise_for_status()
    obj=r.json(); node=(obj.get('data') or {}).get(sym) or {}
    rows=node.get('qfqday') or node.get('day') or []
    return _rows(rows,'Tencent Finance QFQ')

def tencent_legacy_kline(code,limit=180):
    s=session(); sym=market(code)+str(code)
    r=s.get(TENCENT_K2,params={'param':f'{sym},day,1,0,{limit},640,qfq'},timeout=8); r.raise_for_status()
    obj=r.json(); node=(obj.get('data') or {}).get(sym) or {}
    rows=node.get('qfqday') or node.get('day') or []
    return _rows(rows,'Tencent Finance Legacy QFQ')

def eastmoney_kline(code,limit=180):
    s=session()
    params={'secid':east_secid(code),'fields1':'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61','klt':101,'fqt':1,'beg':'0','end':'20500101','lmt':limit,'ut':'fa5fd1943c7b386f172d6893dbbd1d0c','rtntype':6}
    r=s.get(EAST_K,params=params,headers={'Referer':'https://quote.eastmoney.com/','Origin':'https://quote.eastmoney.com'},timeout=8); r.raise_for_status()
    obj=r.json(); data=(obj.get('data') or {})
    return _rows(data.get('klines') or [],'Eastmoney QFQ')

def sina_kline(code,limit=180):
    s=session(); r=s.get(SINA_K,params={'symbol':market(code)+str(code),'scale':240,'ma':'5,10,20,60','datalen':limit},headers={'Referer':'https://finance.sina.com.cn/'},timeout=8); r.raise_for_status()
    return _rows(r.json() or [],'Sina Finance')

def robust_kline(code,limit=180):
    providers=[tencent_kline,tencent_legacy_kline,eastmoney_kline,sina_kline]
    for fn in providers:
        try:
            rows=fn(code,limit)
            if len(rows)>=80:
                return rows
        except Exception:
            continue
    return []

def source_probe(code='600519'):
    # Reuse the same-run provider preflight result to avoid duplicate requests and throttling.
    cache=Path(__file__).resolve().parents[1]/'data'/'provider_health.json'
    try:
        payload=json.loads(cache.read_text(encoding='utf-8'))
        cached=payload.get('provider_health') or payload.get('providers')
        if isinstance(cached,dict) and cached:
            return cached
    except Exception:
        pass
    out={}
    for name,fn in [('Tencent QFQ',tencent_kline),('Tencent Legacy',tencent_legacy_kline),('Eastmoney QFQ',eastmoney_kline),('Sina',sina_kline)]:
        try:
            rows=fn(code,80); out[name]={'ok':len(rows)>=80,'rows':len(rows)}
        except Exception as e: out[name]={'ok':False,'rows':0,'error':type(e).__name__}
    return out

def crosscheck(code,sina=None):
    try:
        t=tencent_quote(code)
        if not t or t.get('price') is None:return {'status':'unavailable','source':'Tencent Finance'}
        if sina is None:return {'status':'verified_secondary','tencent':t}
        p=sina.get('price'); tp=t.get('price')
        if not p or not tp:return {'status':'unavailable','tencent':t}
        diff=abs(tp-p)/max(abs(p),1e-9)
        return {'status':'pass' if diff<=.01 else 'mismatch','price_diff_pct':round(diff*100,4),'tencent':t}
    except Exception as e:return {'status':'error','error':type(e).__name__}
