import json, time
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36'
SAMPLES=('600519','000001','300750')

SOURCES={
    'Yahoo Finance Spark': 'https://query1.finance.yahoo.com/v7/finance/spark',
    'Tencent QFQ': 'https://web.ifzq.gtimg.cn/appstock/fqkline/get',
    'Eastmoney QFQ': 'https://push2his.eastmoney.com/api/qt/stock/kline/get',
    'Sina KLine': 'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData/getKLineData',
}

def test_http(name, code):
    s=requests.Session(); s.headers.update({'User-Agent':UA,'Accept':'application/json,text/plain,*/*'})
    try:
        if name=='Yahoo Finance Spark':
            sym=f'{code}.SS' if code.startswith(('5','6','9')) else f'{code}.SZ'
            r=s.get(SOURCES[name],params={'symbols':sym,'range':'1y','interval':'1d'},timeout=15)
            r.raise_for_status(); obj=r.json(); node=(obj.get('spark') or {}).get('result') or []
            rows=((node[0] if node else {}).get('response') or [{}])[0].get('timestamp') or []
        elif name=='Tencent QFQ':
            m='sh' if code.startswith(('5','6','9')) else 'sz'; sym=m+code
            r=s.get(SOURCES[name],params={'param':f'{sym},day,,,80,qfq','_var':'kline_dayqfq'},timeout=15); r.raise_for_status(); obj=r.json(); node=(obj.get('data') or {}).get(sym) or {}; rows=node.get('qfqday') or node.get('day') or []
        elif name=='Eastmoney QFQ':
            secid=('1.' if code.startswith(('5','6','9')) else '0.')+code
            r=s.get(SOURCES[name],params={'secid':secid,'fields1':'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61','klt':101,'fqt':1,'beg':'0','end':'20500101','lmt':80,'ut':'fa5fd1943c7b386f172d6893dbbd1d0c','rtntype':6},headers={'Referer':'https://quote.eastmoney.com/'},timeout=15); r.raise_for_status(); obj=r.json(); rows=((obj.get('data') or {}).get('klines') or [])
        else:
            m='sh' if code.startswith(('5','6','9')) else 'sz'
            r=s.get(SOURCES[name],params={'symbol':m+code,'scale':240,'ma':'5,10,20,60','datalen':80},timeout=15); r.raise_for_status(); rows=r.json() or []
        return {'ok':len(rows)>=20,'rows':len(rows),'http_status':r.status_code}
    except Exception as e:
        return {'ok':False,'rows':0,'error':type(e).__name__}

def test_baostock(code):
    try:
        import baostock as bs
        lg=bs.login();
        if lg.error_code!='0': return {'ok':False,'rows':0,'error':'login:'+lg.error_msg}
        rs=bs.query_history_k_data_plus(f"{'sh' if code.startswith(('5','6','9')) else 'sz'}.{code}",'date,open,high,low,close,volume,amount','start_date=2025-01-01&end_date=2026-08-18&frequency=d&adjustflag=2')
        rows=0
        while rs.next(): rows+=1
        bs.logout(); return {'ok':rows>=20,'rows':rows}
    except Exception as e:
        return {'ok':False,'rows':0,'error':type(e).__name__}

def main():
    out={}
    for name in SOURCES:
        out[name]={code:test_http(name,code) for code in SAMPLES}
        time.sleep(.5)
    out['Baostock']={code:test_baostock(code) for code in SAMPLES}
    healthy=sum(1 for name,items in out.items() if any(v.get('ok') for v in items.values()))
    payload={'status':'PASS' if healthy else 'BLOCKED','healthy_sources':healthy,'sample_symbols':list(SAMPLES),'sources':out,'generated_at':time.time()}
    p=ROOT/'data'/'free_source_probe.json'; p.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(payload,ensure_ascii=False))
    if healthy==0: raise SystemExit('No free source passed connectivity probe')

if __name__=='__main__': main()
