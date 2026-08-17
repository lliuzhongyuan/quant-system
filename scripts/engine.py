from __future__ import annotations
import json, math, re, time, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; DATA.mkdir(exist_ok=True); STOCKS=DATA/'stocks'; STOCKS.mkdir(exist_ok=True)
UT='bd1d9ddb04089700cf9c27f6f7426281'
SINA_LIST_URL='https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
SINA_KLINE_URL='https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'
STOCK_URL='https://push2.eastmoney.com/api/qt/stock/get'; NEWS_URL='https://np-listapi.eastmoney.com/nlist/api/list/get'
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36'
SESSION=requests.Session(); retry=Retry(total=4,connect=4,read=4,status=4,backoff_factor=1.0,status_forcelist=(429,500,502,503,504),allowed_methods=frozenset(['GET'])); adapter=HTTPAdapter(max_retries=retry,pool_connections=32,pool_maxsize=32); SESSION.mount('https://',adapter); SESSION.headers.update({'User-Agent':UA,'Referer':'https://finance.sina.com.cn/'})

def num(x,default=None):
    try:
        if x is None or x in ('-',''): return default
        v=float(x); return default if math.isnan(v) else v
    except Exception:return default

def atomic_write(path:Path,obj:Any):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':')),encoding='utf-8'); tmp.replace(path)
def market_of(code): return 1 if code.startswith(('6','9','5')) else 0
def full_code(code): return f'{code}.{"SH" if market_of(code)==1 else "SZ"}'
def secid(code): return f'{market_of(code)}.{code}'

def fetch_market(page_size=80,max_pages=100):
    rows=[]
    for node in ('sh_a','sz_a'):
        for pn in range(1,max_pages+1):
            try:
                r=SESSION.get(SINA_LIST_URL,params={'node':node,'page':pn,'num':page_size,'sort':'symbol','asc':1},timeout=15,headers={'Referer':'https://vip.stock.finance.sina.com.cn/'}); r.raise_for_status(); diff=r.json() or []
            except Exception as e: print('sina market page failed',node,pn,e); break
            if not diff: break
            rows.extend(diff)
            if len(diff)<page_size: break
            time.sleep(.05)
    out={str(x.get('code')):x for x in rows if x.get('code')}; result=[]
    for code,item in out.items():
        name=str(item.get('name') or '')
        if not re.fullmatch(r'\d{6}',code) or not name: continue
        if any(x in name.upper() for x in ['ST','退','停牌']) or code.startswith(('8','4','68')): continue
        if not code.startswith(('0','3','6','9')): continue
        mkt=num(item.get('mktcap')); nmc=num(item.get('nmc'))
        result.append({'code':full_code(code),'symbol':code,'name':name,'price':num(item.get('trade')),'change_pct':num(item.get('changepercent'),0),'change':num(item.get('pricechange'),0),'volume':num(item.get('volume'),0),'amount':num(item.get('amount'),0),'amplitude':0,'turnover':num(item.get('turnoverratio'),0),'pe':num(item.get('per')),'volume_ratio':None,'high':num(item.get('high')),'low':num(item.get('low')),'open':num(item.get('open')),'prev_close':num(item.get('settlement')),'total_mv':mkt*10000 if mkt is not None else None,'float_mv':nmc*10000 if nmc is not None else None,'pb':num(item.get('pb')),'sector':'未分类','market_ts':dt.datetime.now(dt.timezone.utc).isoformat()})
    return result

def fetch_kline(code,limit=130):
    prefix='sh' if market_of(code)==1 else 'sz'
    try:
        r=SESSION.get(SINA_KLINE_URL,params={'symbol':prefix+code,'scale':240,'ma':'5,10,20,60','datalen':limit},timeout=15,headers={'Referer':'https://finance.sina.com.cn/'}); r.raise_for_status(); arr=r.json() or []; out=[]
        for x in arr:
            out.append({'date':str(x.get('day',''))[:10],'open':num(x.get('open')),'close':num(x.get('close')),'high':num(x.get('high')),'low':num(x.get('low')),'volume':num(x.get('volume'),0),'amount':num(x.get('amount'),0)})
        return out
    except Exception:return []

def sma(v,n): return sum(v[-n:])/n if len(v)>=n else None
def rsi(v,n=14):
    if len(v)<n+1:return None
    g=[];l=[]
    for i in range(-n,0): d=v[i]-v[i-1];g.append(max(d,0));l.append(max(-d,0))
    ag=sum(g)/n;al=sum(l)/n;return 100 if al==0 else 100-100/(1+ag/al)
def atr(rows,n=14):
    if len(rows)<n+1:return None
    tr=[]
    for i in range(1,len(rows)):
        h,l,pc=rows[i]['high'],rows[i]['low'],rows[i-1]['close'];tr.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(tr[-n:])/n
def max_prev(v,n): return max(v[-n-1:-1]) if len(v)>=n+1 else None
def min_prev(v,n): return min(v[-n:]) if len(v)>=n else None
def turnover_ok(s): return (s.get('turnover') or 0)>.5

def calc_signal(stock,rows):
    if len(rows)<65 or not stock.get('price'):return None
    closes=[x['close'] for x in rows];vols=[x['volume'] for x in rows];c=closes[-1];ma5=sma(closes,5);ma10=sma(closes,10);ma20=sma(closes,20);ma60=sma(closes,60);atr14=atr(rows,14);rsi14=rsi(closes,14)
    if atr14 is None or atr14<=0:return None
    avgv=sma(vols,20) or 0;vr=vols[-1]/avgv if avgv else None;prev20=max_prev(closes,20);low60=min_prev(closes,60);high60=max(closes[-60:]);pos60=(c-low60)/(high60-low60) if high60>low60 else .5;slope20=c/closes[-21]-1 if closes[-21] else 0;ret5=c/closes[-6]-1;draw=c/max(closes[-20:])-1;vc=(sum(vols[-5:])/5)/(sum(vols[-20:])/20) if sum(vols[-20:]) else 1
    strat=[];names=[];reasons=[]
    if low60 and c/low60<=1.35 and c<ma20*1.25 and ma5>=ma10 and (vr or 0)>=1.15 and slope20>-.05:strat+=['A'];names+=['低位启动'];reasons.append('60日低位+均线修复+量能启动')
    if prev20 and c>=prev20*.995 and c>ma20 and ma5>ma10 and (vr or 0)>=1.3:strat+=['B'];names+=['主升突破'];reasons.append('20日平台突破+量能确认')
    if ma5 and ma10 and ma20 and ma5>ma10>ma20 and -.12<=draw<=-.025 and c>=ma10*.985 and vc<.9:strat+=['C'];names+=['回踩二波'];reasons.append('主升趋势回踩+缩量+均线承接')
    if ma20 and c>ma20 and ret5>-.06 and (vr or 0)>=1.1 and turnover_ok(stock):strat+=['D'];names+=['筹码结构穿透'];reasons.append('成交成本结构代理+趋势承接')
    if (stock.get('total_mv') or 0)>=100e8 and (stock.get('pe') is None or 0<stock['pe']<=60) and c>ma20:strat+=['E'];names+=['龙头强度'];reasons.append('大市值+趋势质量')
    if rsi14 is not None and rsi14<38 and c>ma5 and ret5>-.08:strat+=['F'];names+=['超跌反转'];reasons.append('RSI超跌+价格重新站回MA5')
    if (vr or 0)>=1.8 and (stock.get('turnover') or 0)>=3 and ret5>0:strat+=['G'];names+=['量价异动'];reasons.append('量比+换手+上涨同步')
    blocked=stock.get('change_pct',0)<=-4 or (ma20 and c<ma20*.95) or (ma60 and c>ma60*1.45 and ret5>.08) or (stock.get('turnover') or 0)>20
    if blocked:strat+=['H'];names+=['风险拦截']
    q=30
    if ma5 and ma10 and ma20 and ma5>ma10>ma20:q+=15
    if ma60 and c>ma60:q+=8
    if .15<=pos60<=.65:q+=7
    if rsi14 is not None and 45<=rsi14<=70:q+=5
    if stock.get('pe') is not None and 0<stock['pe']<=35:q+=5
    if stock.get('pb') is not None and 0<stock['pb']<=5:q+=3
    quality=min(100,q);op=30+len([x for x in strat if x!='H'])*8
    if 'B' in strat:op+=15
    if 'G' in strat:op+=8
    if 'C' in strat:op+=5
    if vr and vr>=2:op+=5
    if ret5>0:op+=min(8,ret5*100)
    op=min(100,round(op))
    if blocked:tier='D';action='🔴 风险拦截';quality=min(quality,55);op=min(op,35)
    elif len([x for x in strat if x!='H'])>=3 and quality>=70 and op>=75:tier='S';action='🟢 当前可买' if stock.get('change_pct',0)<=3.5 else '🟡 等待回踩'
    elif len([x for x in strat if x!='H'])>=2 and quality>=60:tier='A';action='🟡 等待确认'
    elif strat:tier='B';action='👀 观察'
    else:tier='C';action='—'
    stop=max(0,c-1.5*atr14);target=c+2.5*atr14;rr=(target-c)/max(.01,c-stop)
    return {**stock,'ma5':round(ma5,3),'ma10':round(ma10,3),'ma20':round(ma20,3),'ma60':round(ma60,3),'rsi14':round(rsi14,2) if rsi14 is not None else None,'atr14':round(atr14,3),'volume_ratio_calc':round(vr,2) if vr else None,'position60':round(pos60,3),'return5d':round(ret5*100,2),'drawdown20':round(draw*100,2),'strategy_keys':strat,'strategy_names':names,'resonance_count':len([x for x in strat if x!='H']),'quality_score':round(quality),'opportunity_score':round(op),'tier':tier,'action_status':action,'signal_reason':'；'.join(reasons[:4]) or '暂无有效策略信号','target_price':round(target,2),'stop_loss':round(stop,2),'risk_reward':round(rr,2),'signal_time':dt.datetime.now(dt.timezone.utc).isoformat(),'data_quality':'technical_real'}

def fetch_fundamental(code):
    try:
        r=SESSION.get(STOCK_URL,params={'secid':secid(code),'ut':UT,'fields':'f12,f14,f162,f164,f167,f170,f171,f173,f116,f117'},timeout=10);r.raise_for_status();d=r.json().get('data') or {};return {'roe':num(d.get('f164')),'pe':num(d.get('f162')),'pb':num(d.get('f167')),'total_mv':num(d.get('f116')),'float_mv':num(d.get('f117'))}
    except Exception:return {}

def enrich_fundamentals(signals,limit=500):
    top=sorted(signals,key=lambda x:(x.get('tier')=='S',x.get('opportunity_score',0),x.get('quality_score',0)),reverse=True)[:limit]
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs={ex.submit(fetch_fundamental,s['symbol']):s for s in top}
        for fut in as_completed(futs):
            s=futs[fut]
            try:s.update({k:v for k,v in fut.result().items() if v is not None})
            except Exception:pass
    for s in top:s['fundamental_status']='真实财务摘要' if s.get('roe') is not None else '待财报数据'
    return signals

def scan_all(workers=12,kline_limit=130):
    stocks=fetch_market();atomic_write(DATA/'market.json',{'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'count':len(stocks),'source':'Sina Finance A-share list','items':stocks});signals=[]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs={ex.submit(fetch_kline,s['symbol'],kline_limit):s for s in stocks if s.get('price') and s.get('volume',0)>0}
        for fut in as_completed(futs):
            s=futs[fut];rows=fut.result();sig=calc_signal(s,rows)
            if sig:
                signals.append(sig)
                if sig['tier'] in ('S','A'):atomic_write(STOCKS/f"{s['symbol']}.json",{'stock':sig,'klines':rows[-130:],'source':'Sina Finance daily K-line'})
    signals=enrich_fundamentals(signals);signals.sort(key=lambda x:(x.get('tier')=='S',x.get('resonance_count',0),x.get('opportunity_score',0),x.get('quality_score',0)),reverse=True)
    payload={'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'universe_count':len(stocks),'scanned_count':len(signals),'source':'Sina realtime list + daily K-line','strategies':{'A':'低位启动','B':'主升突破','C':'回踩二波','D':'筹码结构穿透','E':'龙头强度','F':'超跌反转','G':'量价异动','H':'风险拦截'},'items':signals[:300]};atomic_write(DATA/'signals.json',payload);return payload

def fetch_news(limit=50):
    try:
        r=SESSION.get(NEWS_URL,params={'client':'web','column_id':'102','limit':limit,'last_time':'0'},timeout=15);r.raise_for_status();obj=r.json();raw=obj.get('data') or obj.get('result') or obj
        if isinstance(raw,dict):raw=raw.get('list') or raw.get('items') or []
        out=[]
        for x in raw or []:
            title=x.get('title') or x.get('digest') or x.get('content') or ''
            if title:out.append({'id':str(x.get('id') or x.get('art_code') or hash(title)),'source':x.get('source') or '东方财富7×24','title':re.sub(r'<.*?>','',str(title)),'time':x.get('showTime') or x.get('ctime') or x.get('time') or '','url':x.get('url') or x.get('art_url') or '','raw':x})
        return out
    except Exception as e:print('news fetch failed',e);return []

def update_news():
    news=fetch_news();atomic_write(DATA/'news.json',{'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':'Eastmoney 7x24','count':len(news),'items':news});return news

if __name__=='__main__':print(json.dumps(scan_all(),ensure_ascii=False)[:2000])
