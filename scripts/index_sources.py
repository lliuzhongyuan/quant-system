import datetime as dt
import json
from pathlib import Path
import requests

UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36'
EAST_K='https://push2his.eastmoney.com/api/qt/stock/kline/get'
EAST_Q='https://push2.eastmoney.com/api/qt/stock/get'
TENCENT_Q='https://qt.gtimg.cn/q='
ROOT=Path(__file__).resolve().parents[1]
INDEXES={
    'sh000001':{'name':'上证指数','secid':'1.000001','bs':'sh.000001','tencent':'sh000001'},
    'sz399001':{'name':'深证成指','secid':'0.399001','bs':'sz.399001','tencent':'sz399001'},
    'sz399006':{'name':'创业板指','secid':'0.399006','bs':'sz.399006','tencent':'sz399006'},
    'sh000300':{'name':'沪深300','secid':'1.000300','bs':'sh.000300','tencent':'sh000300'},
}

def _session():
    s=requests.Session(); s.headers.update({'User-Agent':UA,'Accept':'application/json,text/plain,*/*','Referer':'https://quote.eastmoney.com/'}); return s

def _rows(klines,source):
    out=[]
    for x in klines or []:
        try:
            p=x.split(',')
            if len(p)<7: continue
            out.append({'date':p[0][:10],'open':float(p[1]),'close':float(p[2]),'high':float(p[3]),'low':float(p[4]),'volume':float(p[5] or 0),'amount':float(p[6] or 0),'source':source})
        except Exception: pass
    return out

def eastmoney_index(code,limit=260):
    meta=INDEXES[code]; s=_session()
    params={'secid':meta['secid'],'fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61','klt':101,'fqt':0,'beg':'0','end':'20500101','lmt':limit,'ut':'fa5fd1943c7b386f172d6893dbbd1d0c','rtntype':6}
    r=s.get(EAST_K,params=params,timeout=12); r.raise_for_status(); obj=r.json(); data=obj.get('data') or {}
    rows=_rows(data.get('klines') or [],'Eastmoney Index')
    return rows[-limit:] if len(rows)>=60 else []

def eastmoney_quote(code):
    meta=INDEXES[code]; s=_session()
    r=s.get(EAST_Q,params={'secid':meta['secid'],'fields':'f43,f44,f45,f46,f47,f48,f57,f58,f60,f169,f170'},timeout=8); r.raise_for_status(); d=(r.json().get('data') or {})
    price=d.get('f43'); prev=d.get('f60'); change=d.get('f169'); pct=d.get('f170')
    def n(v):
        try:return float(v)
        except Exception:return None
    return {'code':code,'name':meta['name'],'price':n(price),'prev_close':n(prev),'change':n(change),'change_pct':n(pct),'source':'Eastmoney Index Quote','fetched_at':dt.datetime.now(dt.timezone.utc).isoformat()}

def tencent_index_quote(code):
    meta=INDEXES[code]; s=_session(); r=s.get(TENCENT_Q+meta['tencent'],timeout=8); r.raise_for_status(); text=r.content.decode('gbk','ignore')
    if '=\"' not in text:return None
    body=text.split('=\"',1)[1].rsplit('\"',1)[0]; f=body.split('~')
    if len(f)<35:return None
    def n(i):
        try:return float(f[i])
        except Exception:return None
    price=n(3); prev=n(4)
    if price is None:return None
    return {'code':code,'name':f[1] or meta['name'],'price':price,'prev_close':prev,'change':price-prev if prev is not None else None,'change_pct':((price-prev)/prev*100 if prev else None),'high':n(33),'low':n(34),'quote_time':f[30] if len(f)>30 else None,'source':'Tencent Index Quote','fetched_at':dt.datetime.now(dt.timezone.utc).isoformat()}

def baostock_index(code,limit=260):
    try:
        import baostock as bs
        lg=bs.login()
        if lg.error_code!='0': return []
        m=INDEXES[code]; end=dt.date.today().isoformat(); start=(dt.date.today()-dt.timedelta(days=520)).isoformat()
        rs=bs.query_history_k_data_plus(m['bs'],'date,open,high,low,close,volume,amount',start_date=start,end_date=end,frequency='d',adjustflag='3')
        out=[]
        while rs.next():
            x=rs.get_row_data()
            try: out.append({'date':x[0],'open':float(x[1]),'high':float(x[2]),'low':float(x[3]),'close':float(x[4]),'volume':float(x[5] or 0),'amount':float(x[6] or 0),'source':'Baostock Index'})
            except Exception: pass
        try: bs.logout()
        except Exception: pass
        return out[-limit:] if len(out)>=60 else []
    except Exception:return []

def get_index(code,limit=260):
    for fn in (eastmoney_index,baostock_index):
        try:
            rows=fn(code,limit)
            if len(rows)>=60:return rows
        except Exception: pass
    return []

def fetch_indices():
    out=[]
    for code in INDEXES:
        quote=None
        for qfn in (eastmoney_quote,tencent_index_quote):
            try:
                quote=qfn(code)
                if quote and quote.get('price') is not None:break
            except Exception: pass
        rows=get_index(code,260)
        if quote is None and rows:
            last=rows[-1]; prev=rows[-2]['close'] if len(rows)>1 else None; ch=(last['close']-prev) if prev else None
            quote={'code':code,'name':INDEXES[code]['name'],'price':last['close'],'prev_close':prev,'change':ch,'change_pct':ch/prev*100 if prev else None,'source':last['source']+' Latest Close','fetched_at':dt.datetime.now(dt.timezone.utc).isoformat()}
        if quote:
            quote['kline_rows']=len(rows); quote['kline_source']=rows[-1].get('source') if rows else None; quote['kline_latest']=rows[-1].get('date') if rows else None; quote['live_quote']=quote.get('source','').endswith('Quote'); out.append(quote)
    return out

def probe():
    result={}
    today=dt.date.today()
    for code,meta in INDEXES.items():
        item={'name':meta['name'],'eastmoney_kline':0,'baostock_kline':0,'quote_ok':False,'quote_source':None,'latest_date':None,'live_quote_available':False}
        try:
            er=eastmoney_index(code,80); item['eastmoney_kline']=len(er); item['latest_date']=er[-1]['date'] if er else None
        except Exception: pass
        if item['eastmoney_kline']<60:
            try:
                br=baostock_index(code,80); item['baostock_kline']=len(br); item['latest_date']=br[-1]['date'] if br else item['latest_date']
            except Exception: pass
        for qfn in (eastmoney_quote,tencent_index_quote):
            try:
                q=qfn(code)
                if q and q.get('price') is not None:
                    item['quote_ok']=True; item['live_quote_available']=True; item['quote_source']=q.get('source'); item['quote']=q; break
            except Exception: pass
        fresh=False
        if item['latest_date']:
            try:fresh=(today-dt.date.fromisoformat(item['latest_date'])).days<=7
            except Exception: pass
        item['fresh_enough']=fresh
        kline_ok=(item['eastmoney_kline']>=60 or item['baostock_kline']>=60)
        # EOD production depends on fresh daily index K-lines. Live quotes are reported separately
        # and must never be fabricated or silently relabeled as real-time.
        item['ok']=kline_ok and fresh
        item['acceptance_mode']='fresh_daily_kline' if item['ok'] and not item['live_quote_available'] else ('live_quote_plus_kline' if item['ok'] else 'failed')
        result[code]=item
    ok=sum(1 for x in result.values() if x['ok'])
    live=sum(1 for x in result.values() if x['live_quote_available'])
    payload={'status':'PASS' if ok==len(result) else 'FAIL','healthy':ok,'total':len(result),'live_quote_available':live,'indexes':result,'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),'policy':'EOD scan accepts fresh real daily index K-lines when live quote providers are unreachable; live status remains explicitly unavailable.'}
    (ROOT/'data'/'index_provider_health.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    return payload