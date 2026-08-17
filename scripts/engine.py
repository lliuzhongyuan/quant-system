from __future__ import annotations
import json, math, os, re, time, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
STOCKS = DATA / 'stocks'
STOCKS.mkdir(exist_ok=True)

UT = 'bd1d9ddb04089700cf9c27f6f7426281'
QUOTE_URL = 'https://push2.eastmoney.com/api/qt/clist/get'
KLINE_URL = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
STOCK_URL = 'https://push2.eastmoney.com/api/qt/stock/get'
NEWS_URL = 'https://np-listapi.eastmoney.com/nlist/api/list/get'
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36'

SESSION = requests.Session()
SESSION.headers.update({'User-Agent': UA, 'Referer': 'https://quote.eastmoney.com/'})

FIELDS = 'f12,f13,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10,f15,f16,f17,f18,f20,f21,f23,f100'
FS = 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23'

def num(x, default=None):
    try:
        if x is None or x == '-' or x == '': return default
        v = float(x)
        return default if math.isnan(v) else v
    except Exception:
        return default

def atomic_write(path: Path, obj: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(path)

def market_of(code: str) -> int:
    return 1 if code.startswith(('6','9','5')) else 0

def full_code(code: str) -> str:
    return f'{code}.{"SH" if market_of(code)==1 else "SZ"}'

def secid(code: str) -> str:
    return f'{market_of(code)}.{code}'

def is_valid_stock(item: dict) -> bool:
    code = str(item.get('f12') or '')
    name = str(item.get('f14') or '')
    if not re.fullmatch(r'\d{6}', code): return False
    if not name or any(x in name.upper() for x in ['ST','退','停牌']): return False
    if code.startswith(('8','4')): return False
    if code.startswith('68'): return True
    return code.startswith(('0','3','6','9'))

def fetch_market(page_size=100, max_pages=100):
    rows=[]
    for pn in range(1, max_pages+1):
        params={'pn':pn,'pz':page_size,'po':1,'np':1,'ut':UT,'fltt':2,'invt':2,'fid':'f3','fs':FS,'fields':FIELDS}
        try:
            r=SESSION.get(QUOTE_URL, params=params, timeout=15)
            r.raise_for_status(); data=r.json().get('data') or {}
            diff=data.get('diff') or []
        except Exception as e:
            print('market page failed',pn,e); break
        if not diff: break
        rows.extend([x for x in diff if is_valid_stock(x)])
        total=int(data.get('total') or 0)
        if total and len(rows)>=total: break
        if len(diff)<page_size: break
        time.sleep(0.08)
    out={str(x['f12']):x for x in rows}
    result=[]
    for code,item in out.items():
        result.append({'code':full_code(code),'symbol':code,'name':str(item.get('f14') or ''),'price':num(item.get('f2')), 'change_pct':num(item.get('f3'),0),'change':num(item.get('f4'),0),'volume':num(item.get('f5'),0),'amount':num(item.get('f6'),0),'amplitude':num(item.get('f7'),0),'turnover':num(item.get('f8'),0),'pe':num(item.get('f9')),'volume_ratio':num(item.get('f10')),'high':num(item.get('f15')),'low':num(item.get('f16')),'open':num(item.get('f17')),'prev_close':num(item.get('f18')),'total_mv':num(item.get('f20')),'float_mv':num(item.get('f21')),'pb':num(item.get('f23')),'sector':str(item.get('f100') or '未分类'),'market_ts':dt.datetime.now(dt.timezone.utc).isoformat()})
    return result

def fetch_kline(code: str, limit=130):
    params={'fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61','ut':'7eea3edcaed734bea9cbfc24409ed989','klt':101,'fqt':1,'secid':secid(code),'beg':'0','end':'20500101','lmt':limit}
    try:
        r=SESSION.get(KLINE_URL,params=params,timeout=15); r.raise_for_status(); data=r.json().get('data') or {}; arr=data.get('klines') or []
        out=[]
        for s in arr:
            p=s.split(',')
            if len(p)<7: continue
            out.append({'date':p[0],'open':num(p[1]),'close':num(p[2]),'high':num(p[3]),'low':num(p[4]),'volume':num(p[5],0),'amount':num(p[6],0)})
        return out
    except Exception:
        return []

def sma(vals,n):
    return sum(vals[-n:])/n if len(vals)>=n else None

def rsi(vals,n=14):
    if len(vals)<n+1:return None
    gains=[]; losses=[]
    for i in range(-n,0):
        d=vals[i]-vals[i-1]; gains.append(max(d,0)); losses.append(max(-d,0))
    ag=sum(gains)/n; al=sum(losses)/n
    return 100 if al==0 else 100-100/(1+ag/al)

def atr(rows,n=14):
    if len(rows)<n+1:return None
    trs=[]
    for i in range(1,len(rows)):
        h,l,pc=rows[i]['high'],rows[i]['low'],rows[i-1]['close']
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(trs[-n:])/n if len(trs)>=n else None

def max_prev(vals,n):
    return max(vals[-n-1:-1]) if len(vals)>=n+1 else None

def min_prev(vals,n):
    return min(vals[-n:]) if len(vals)>=n else None

def calc_signal(stock, rows):
    if len(rows)<65 or not stock.get('price'): return None
    closes=[x['close'] for x in rows]; vols=[x['volume'] for x in rows]
    c=closes[-1]; ma5=sma(closes,5); ma10=sma(closes,10); ma20=sma(closes,20); ma60=sma(closes,60)
    atr14=atr(rows,14) or c*0.03; rsi14=rsi(closes,14)
    avgv20=sma(vols,20) or 0; vr=(vols[-1]/avgv20) if avgv20 else None
    prev20=max_prev(closes,20); low60=min_prev(closes,60); high60=max(closes[-60:])
    pos60=(c-low60)/(high60-low60) if high60 and low60 is not None and high60>low60 else 0.5
    slope20=(c/closes[-21]-1) if len(closes)>=21 and closes[-21] else 0
    ret5=(c/closes[-6]-1) if len(closes)>=6 else 0
    draw_from_high=(c/max(closes[-20:])-1) if len(closes)>=20 else 0
    vol_contraction=(sum(vols[-5:])/5)/(sum(vols[-20:])/20) if len(vols)>=20 and sum(vols[-20:]) else 1
    strat=[]; names=[]; reasons=[]
    if low60 and c/low60<=1.35 and c<ma20*1.25 and ma5>=ma10 and (vr or 0)>=1.15 and slope20>-0.05:
        strat += ['A']; names += ['低位启动']; reasons.append('60日低位+均线修复+量能启动')
    if prev20 and c>=prev20*0.995 and c>ma20 and ma5>ma10 and (vr or 0)>=1.3:
        strat += ['B']; names += ['主升突破']; reasons.append('20日平台突破+量能确认')
    if ma5 and ma10 and ma20 and ma5>ma10>ma20 and -0.12<=draw_from_high<=-0.025 and c>=ma10*0.985 and vol_contraction<0.9:
        strat += ['C']; names += ['回踩二波']; reasons.append('主升趋势回踩+缩量+均线承接')
    if ma20 and c>ma20 and ret5>-0.06 and (vr or 0)>=1.1 and turnover_ok(stock):
        strat += ['D']; names += ['筹码结构穿透']; reasons.append('成交成本结构代理+趋势承接')
    if (stock.get('total_mv') or 0)>=100e8 and (stock.get('pe') is None or 0<stock.get('pe')<=60) and c>ma20:
        strat += ['E']; names += ['龙头强度']; reasons.append('大市值+趋势质量')
    if rsi14 is not None and rsi14<38 and c>ma5 and ret5>-0.08:
        strat += ['F']; names += ['超跌反转']; reasons.append('RSI超跌+价格重新站回MA5')
    if (vr or 0)>=1.8 and (stock.get('turnover') or 0)>=3 and ret5>0:
        strat += ['G']; names += ['量价异动']; reasons.append('量比+换手+上涨同步')
    blocked=False
    if stock.get('change_pct',0)<=-4 or (ma20 and c<ma20*0.95) or (ma60 and c>ma60*1.45 and ret5>0.08) or (stock.get('turnover') or 0)>20:
        strat += ['H']; names += ['风险拦截']; blocked=True
    q=30
    if ma5 and ma10 and ma20 and ma5>ma10>ma20:q+=15
    if ma60 and c>ma60:q+=8
    if 0.15<=pos60<=0.65:q+=7
    if rsi14 is not None and 45<=rsi14<=70:q+=5
    if stock.get('pe') is not None and 0<stock['pe']<=35:q+=5
    if stock.get('pb') is not None and 0<stock['pb']<=5:q+=3
    quality=min(100,q)
    opportunity=30+len([x for x in strat if x!='H'])*8
    if 'B' in strat: opportunity+=15
    if 'G' in strat: opportunity+=8
    if 'C' in strat: opportunity+=5
    if vr and vr>=2: opportunity+=5
    if ret5>0: opportunity+=min(8,ret5*100)
    opportunity=min(100,round(opportunity))
    if blocked:
        tier='D'; action='🔴 风险拦截'; quality=min(quality,55); opportunity=min(opportunity,35)
    elif len([x for x in strat if x!='H'])>=3 and quality>=70 and opportunity>=75:
        tier='S'; action='🟢 当前可买' if stock.get('change_pct',0)<=3.5 else '🟡 等待回踩'
    elif len([x for x in strat if x!='H'])>=2 and quality>=60:
        tier='A'; action='🟡 等待确认'
    elif strat:
        tier='B'; action='👀 观察'
    else:
        tier='C'; action='—'
    stop=max(0,c-1.5*atr14); target=c+2.5*atr14; rr=(target-c)/max(0.01,c-stop)
    risk_reason='；'.join(reasons[:4]) or '暂无有效策略信号'
    return {**stock,'ma5':round(ma5,3),'ma10':round(ma10,3),'ma20':round(ma20,3),'ma60':round(ma60,3),'rsi14':round(rsi14,2) if rsi14 is not None else None,'atr14':round(atr14,3),'volume_ratio_calc':round(vr,2) if vr else None,'position60':round(pos60,3),'return5d':round(ret5*100,2),'drawdown20':round(draw_from_high*100,2),'strategy_keys':strat,'strategy_names':names,'resonance_count':len([x for x in strat if x!='H']),'quality_score':round(quality),'opportunity_score':round(opportunity),'tier':tier,'action_status':action,'signal_reason':risk_reason,'target_price':round(target,2),'stop_loss':round(stop,2),'risk_reward':round(rr,2),'signal_time':dt.datetime.now(dt.timezone.utc).isoformat(),'data_quality':'technical_real'}

def turnover_ok(stock):
    return (stock.get('turnover') or 0) > 0.5

def fetch_fundamental(code):
    params={'secid':secid(code),'ut':UT,'fields':'f12,f14,f162,f164,f167,f170,f171,f173,f116,f117'}
    try:
        r=SESSION.get(STOCK_URL,params=params,timeout=10); r.raise_for_status(); d=(r.json().get('data') or {})
        return {'roe':num(d.get('f164')),'pe':num(d.get('f162')),'pb':num(d.get('f167')),'total_mv':num(d.get('f116')),'float_mv':num(d.get('f117'))}
    except Exception: return {}

def enrich_fundamentals(signals, limit=500):
    top=sorted(signals,key=lambda x:(x.get('tier')=='S',x.get('opportunity_score',0),x.get('quality_score',0)),reverse=True)[:limit]
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs={ex.submit(fetch_fundamental,s['symbol']):s for s in top}
        for fut in as_completed(futs):
            s=futs[fut]
            try: s.update({k:v for k,v in fut.result().items() if v is not None})
            except Exception: pass
    for s in top:
        if s.get('roe') is None: s['fundamental_status']='待财报数据'
        else: s['fundamental_status']='真实财务摘要'
    return signals

def scan_all(workers=12, kline_limit=130):
    stocks=fetch_market()
    atomic_write(DATA/'market.json',{'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'count':len(stocks),'source':'Eastmoney clist/get','items':stocks})
    signals=[]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs={ex.submit(fetch_kline,s['symbol'],kline_limit):s for s in stocks if s.get('price') and s.get('volume',0)>0}
        for fut in as_completed(futs):
            s=futs[fut]; rows=fut.result(); sig=calc_signal(s,rows)
            if sig:
                signals.append(sig)
                if sig['tier'] in ('S','A'):
                    atomic_write(STOCKS/f"{s['symbol']}.json",{'stock':sig,'klines':rows[-130:],'source':'Eastmoney K-line fqt=1'})
    signals=enrich_fundamentals(signals)
    signals.sort(key=lambda x:(x.get('tier')=='S',x.get('resonance_count',0),x.get('opportunity_score',0),x.get('quality_score',0)),reverse=True)
    payload={'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'universe_count':len(stocks),'scanned_count':len(signals),'source':'Eastmoney realtime + daily K-line','strategies':{'A':'低位启动','B':'主升突破','C':'回踩二波','D':'筹码结构穿透','E':'龙头强度','F':'超跌反转','G':'量价异动','H':'风险拦截'},'items':signals[:300]}
    atomic_write(DATA/'signals.json',payload)
    return payload

def fetch_news(limit=50):
    params={'client':'web','column_id':'102','limit':limit,'last_time':'0'}
    try:
        r=SESSION.get(NEWS_URL,params=params,timeout=15); r.raise_for_status(); obj=r.json()
        raw=(obj.get('data') or obj.get('result') or obj)
        if isinstance(raw,dict): raw=raw.get('list') or raw.get('items') or []
        out=[]
        for x in raw or []:
            title=x.get('title') or x.get('digest') or x.get('content') or ''
            if not title: continue
            out.append({'id':str(x.get('id') or x.get('art_code') or hash(title)),'source':x.get('source') or '东方财富7×24','title':re.sub(r'<.*?>','',str(title)),'time':x.get('showTime') or x.get('ctime') or x.get('time') or '', 'url':x.get('url') or x.get('art_url') or '', 'raw':x})
        return out
    except Exception as e:
        print('news fetch failed',e); return []

def update_news():
    news=fetch_news()
    atomic_write(DATA/'news.json',{'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':'Eastmoney 7x24','count':len(news),'items':news})
    return news

if __name__=='__main__':
    print(json.dumps(scan_all(),ensure_ascii=False)[:2000])
