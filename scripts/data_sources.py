import json, math, random, time, datetime as dt
from pathlib import Path
import requests

UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36'
SINA_LIST='https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
SINA_K='https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'
TENCENT_Q='https://qt.gtimg.cn/q='
TENCENT_K='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'

session=requests.Session(); session.headers.update({'User-Agent':UA,'Referer':'https://finance.sina.com.cn/'})

def market(code): return 'sh' if str(code).startswith(('5','6','9')) else 'sz'
def stamp(): return dt.datetime.now(dt.timezone.utc).isoformat()

def tencent_quote(code):
    sym=market(code)+str(code)
    r=session.get(TENCENT_Q+sym,timeout=8); r.raise_for_status(); txt=r.content.decode('gbk','ignore')
    if '="' not in txt: return None
    fields=txt.split('="',1)[1].rsplit('"',1)[0].split('~')
    if len(fields)<35: return None
    def f(i):
        try:return float(fields[i])
        except:return None
    return {'symbol':str(code),'name':fields[1],'price':f(3),'prev_close':f(4),'open':f(5),'volume':f(6),'change':f(31),'change_pct':f(32),'high':f(33),'low':f(34),'quote_time':fields[30] if len(fields)>30 else None,'source':'Tencent Finance','fetched_at':stamp()}

def tencent_kline(code,limit=180):
    sym=market(code)+str(code)
    params={'param':f'{sym},day,,,{limit},qfq','_var':'kline_dayqfq','r':str(random.random())}
    r=session.get(TENCENT_K,params=params,timeout=12); r.raise_for_status(); obj=r.json()
    node=(obj.get('data') or {}).get(sym) or {}
    arr=node.get('qfqday') or node.get('day') or []
    out=[]
    for x in arr:
        if len(x)<6: continue
        try: out.append({'date':str(x[0])[:10],'open':float(x[1]),'close':float(x[2]),'high':float(x[3]),'low':float(x[4]),'volume':float(x[5]),'amount':0.0})
        except: pass
    return out

def sina_kline(code,limit=180):
    r=session.get(SINA_K,params={'symbol':market(code)+str(code),'scale':240,'ma':'5,10,20,60','datalen':limit},timeout=12); r.raise_for_status(); arr=r.json() or []
    out=[]
    for x in arr:
        try: out.append({'date':str(x.get('day',''))[:10],'open':float(x['open']),'close':float(x['close']),'high':float(x['high']),'low':float(x['low']),'volume':float(x.get('volume') or 0),'amount':float(x.get('amount') or 0)})
        except: pass
    return out

def robust_kline(code,limit=180):
    errors=[]
    for name,fn in [('Tencent Finance QFQ',tencent_kline),('Sina Finance',sina_kline)]:
        try:
            rows=fn(code,limit)
            if len(rows)>=80:
                rows=[dict(x,source=name,fetched_at=stamp()) for x in rows]
                return rows
            errors.append(f'{name}:only {len(rows)} bars')
        except Exception as e: errors.append(f'{name}:{type(e).__name__}')
    return []

def crosscheck(code,sina=None):
    try:
        t=tencent_quote(code)
        if not t or t.get('price') is None: return {'status':'unavailable','source':'Tencent Finance'}
        if sina is None: return {'status':'verified_secondary','tencent':t}
        p=sina.get('price'); tp=t.get('price')
        if not p or not tp: return {'status':'unavailable','tencent':t}
        diff=abs(tp-p)/max(abs(p),1e-9)
        return {'status':'pass' if diff<=0.01 else 'mismatch','price_diff_pct':round(diff*100,4),'tencent':t}
    except Exception as e:return {'status':'error','error':type(e).__name__}
