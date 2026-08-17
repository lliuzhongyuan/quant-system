import datetime as dt
import requests

UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36'
SINA_K='https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData/getKLineData'
TENCENT_Q='https://qt.gtimg.cn/q='
TENCENT_K='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
EAST_K='https://push2his.eastmoney.com/api/qt/stock/kline/get'
session=requests.Session(); session.headers.update({'User-Agent':UA,'Referer':'https://finance.sina.com.cn/'})

def market(code): return 'sh' if str(code).startswith(('5','6','9')) else 'sz'
def east_secid(code): return ('1.' if market(code)=='sh' else '0.')+str(code)
def stamp(): return dt.datetime.now(dt.timezone.utc).isoformat()
def _rows(arr,source):
    out=[]
    for x in arr:
        try:
            if isinstance(x,str):
                p=x.split(',')
                if len(p)<6: continue
                out.append({'date':p[0][:10],'open':float(p[1]),'close':float(p[2]),'high':float(p[3]),'low':float(p[4]),'volume':float(p[5]),'amount':float(p[6]) if len(p)>6 else 0.0,'source':source,'fetched_at':stamp()})
            elif len(x)>=6:
                out.append({'date':str(x[0])[:10],'open':float(x[1]),'close':float(x[2]),'high':float(x[3]),'low':float(x[4]),'volume':float(x[5]),'amount':float(x[6]) if len(x)>6 else 0.0,'source':source,'fetched_at':stamp()})
        except Exception: pass
    return out

def tencent_quote(code):
    sym=market(code)+str(code); r=session.get(TENCENT_Q+sym,timeout=8); r.raise_for_status(); txt=r.content.decode('gbk','ignore')
    if '="' not in txt:return None
    f=txt.split('="',1)[1].rsplit('"',1)[0].split('~')
    if len(f)<35:return None
    def n(i):
        try:return float(f[i])
        except:return None
    return {'symbol':str(code),'name':f[1],'price':n(3),'prev_close':n(4),'open':n(5),'volume':n(6),'change':n(31),'change_pct':n(32),'high':n(33),'low':n(34),'quote_time':f[30] if len(f)>30 else None,'source':'Tencent Finance','fetched_at':stamp()}

def tencent_kline(code,limit=180):
    sym=market(code)+str(code); r=session.get(TENCENT_K,params={'param':f'{sym},day,,,{limit},qfq','_var':'kline_dayqfq'},timeout=12); r.raise_for_status(); obj=r.json(); node=(obj.get('data') or {}).get(sym) or {}; return _rows(node.get('qfqday') or node.get('day') or [],'Tencent Finance QFQ')

def eastmoney_kline(code,limit=180):
    r=session.get(EAST_K,params={'secid':east_secid(code),'fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57','klt':101,'fqt':1,'end':'20500101','lmt':limit},headers={'Referer':'https://quote.eastmoney.com/'},timeout=12); r.raise_for_status(); obj=r.json(); data=(obj.get('data') or {}); return _rows(data.get('klines') or [],'Eastmoney QFQ')

def sina_kline(code,limit=180):
    r=session.get(SINA_K,params={'symbol':market(code)+str(code),'scale':240,'ma':'5,10,20,60','datalen':limit},timeout=12); r.raise_for_status(); return _rows(r.json() or [],'Sina Finance')

def robust_kline(code,limit=180):
    for name,fn in [('Tencent Finance QFQ',tencent_kline),('Eastmoney QFQ',eastmoney_kline),('Sina Finance',sina_kline)]:
        try:
            rows=fn(code,limit)
            if len(rows)>=80:return rows
        except Exception: pass
    return []

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
