import json, math, re, time, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from data_sources import robust_kline, source_probe

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; STOCKS=DATA/'stocks'; STOCKS.mkdir(parents=True,exist_ok=True)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36'
LIST_URL='https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
QUOTE_URL='https://hq.sinajs.cn/list='; NEWS_URL='https://finance.sina.com.cn/7x24/notification.shtml'
RETRY=Retry(total=2,connect=2,read=2,status=2,backoff_factor=.35,status_forcelist=(429,500,502,503,504),allowed_methods=frozenset(['GET']))
S=requests.Session(); S.mount('https://',HTTPAdapter(max_retries=RETRY)); S.headers.update({'User-Agent':UA,'Referer':'https://finance.sina.com.cn/'})
STRATEGIES={'A':'低位启动','B':'主升突破','C':'回踩二波','D':'筹码结构穿透','E':'龙头强度','F':'超跌反转','G':'量价异动','H':'风险拦截'}

def num(x,default=None):
    try:
        v=float(x); return default if math.isnan(v) else v
    except Exception:return default

def write_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':')),encoding='utf-8'); tmp.replace(path)

def exchange(code): return 'sh' if str(code).startswith(('5','6','9')) else 'sz'
def full_code(code): return str(code)+('.SH' if exchange(code)=='sh' else '.SZ')

def fetch_market():
    raw=[]
    for node in ('sh_a','sz_a'):
        for page in range(1,101):
            try: rows=S.get(LIST_URL,params={'node':node,'page':page,'num':100,'sort':'symbol','asc':1},timeout=12).json() or []
            except Exception: break
            if not rows: break
            raw.extend(rows)
            if len(rows)<100: break
            time.sleep(.02)
    dedup={str(x.get('code')):x for x in raw if x.get('code')}; out=[]
    for code,x in dedup.items():
        name=str(x.get('name') or '')
        if not re.fullmatch(r'\d{6}',code) or not name or any(k in name.upper() for k in ('ST','退','停牌')) or code.startswith(('8','4','68')): continue
        mv=num(x.get('mktcap')); nmc=num(x.get('nmc'))
        out.append({'code':full_code(code),'symbol':code,'name':name,'price':num(x.get('trade')),'change_pct':num(x.get('changepercent'),0),'change':num(x.get('pricechange'),0),'volume':num(x.get('volume'),0),'amount':num(x.get('amount'),0),'turnover':num(x.get('turnoverratio'),0),'pe':num(x.get('per')),'pb':num(x.get('pb')),'high':num(x.get('high')),'low':num(x.get('low')),'open':num(x.get('open')),'prev_close':num(x.get('settlement')),'total_mv':mv*10000 if mv is not None else None,'float_mv':nmc*10000 if nmc is not None else None,'sector':'未分类'})
    return out

def fetch_indices():
    try:
        text=S.get(QUOTE_URL+'sh000001,sz399001,sz399006,sh000300',timeout=8).content.decode('gbk','ignore'); out=[]
        for line in text.splitlines():
            m=re.search(r'hq_str_([a-z0-9]+)=\"([^\"]*)\"',line,re.I)
            if not m: continue
            p=m.group(2).split(','); prev=num(p[2]) if len(p)>2 else None; ch=num(p[3],0) if len(p)>3 else 0
            out.append({'code':m.group(1),'name':p[0],'price':num(p[1]),'change':ch,'change_pct':ch/prev*100 if prev else None})
        return out
    except Exception:return []

def regime(indices,breadth):
    vals=[x['change_pct'] for x in indices if x.get('change_pct') is not None]; avg=sum(vals)/len(vals) if vals else 0
    adv=breadth.get('advancers',0); dec=breadth.get('decliners',0); breadth_score=adv/max(1,adv+dec)*100
    score=max(0,min(100,round(.55*(50+avg*12)+.45*breadth_score)))
    if score>=68:return {'regime':'强势上行','score':score,'position':'65%~85%','risk':'中低','directive':'主升突破优先；强势回踩优先；严禁无计划追高'}
    if score>=57:return {'regime':'震荡偏强','score':score,'position':'45%~65%','risk':'中','directive':'高共振优先；等待回踩确认；控制单票风险'}
    if score>=45:return {'regime':'中性震荡','score':score,'position':'25%~45%','risk':'中','directive':'降低频率；只做结构清晰的A/B/C信号'}
    return {'regime':'弱势防守','score':score,'position':'0%~25%','risk':'中高','directive':'减少交易；H风险拦截优先；等待市场修复'}

def sma(a,k): return sum(a[-k:])/k if len(a)>=k else None
def rsi(a,k=14):
    if len(a)<k+1:return None
    g=[max(a[i]-a[i-1],0) for i in range(-k,0)]; l=[max(a[i-1]-a[i],0) for i in range(-k,0)]; ag=sum(g)/k; al=sum(l)/k
    return 100 if al==0 else 100-100/(1+ag/al)
def atr(rows,k=14):
    if len(rows)<k+1:return None
    tr=[max(rows[i]['high']-rows[i]['low'],abs(rows[i]['high']-rows[i-1]['close']),abs(rows[i]['low']-rows[i-1]['close'])) for i in range(1,len(rows))]
    return sum(tr[-k:])/k

def ema_series(a,k):
    if len(a)<k:return []
    e=sum(a[:k])/k; out=[e]; alpha=2/(k+1)
    for x in a[k:]: e=alpha*x+(1-alpha)*e; out.append(e)
    return out

def macd(a):
    e12=ema_series(a,12); e26=ema_series(a,26)
    if not e12 or not e26:return None,None,None
    dif=[e12[i+14]-e26[i] for i in range(len(e26))]; dea=ema_series(dif,9)
    if not dea:return None,None,None
    return dif[-1],dea[-1],2*(dif[-1]-dea[-1])

def kdj(rows):
    if len(rows)<9:return 50,50,50
    k=d=50
    for i in range(8,len(rows)):
        hi=max(x['high'] for x in rows[i-8:i+1]); lo=min(x['low'] for x in rows[i-8:i+1]); rsv=50 if hi==lo else (rows[i]['close']-lo)/(hi-lo)*100
        k=(2*k+rsv)/3; d=(2*d+k)/3
    return k,d,3*k-2*d

def score_signal(s,rows):
    if len(rows)<80 or not s.get('price'):return None
    c=[x['close'] for x in rows]; v=[x['volume'] for x in rows]; p=c[-1]; m5,m10,m20,m60=[sma(c,k) for k in (5,10,20,60)]; a=atr(rows); rs=rsi(c); dif,dea,mh=macd(c); k,d,j=kdj(rows)
    vr=v[-1]/max(sma(v,20) or 1,1); low60=min(c[-61:-1]); high60=max(c[-61:-1]); pos=(p-low60)/(high60-low60) if high60>low60 else .5
    ret5=p/c[-6]-1; ret20=p/c[-21]-1; dd20=p/max(c[-21:-1])-1; vc=(sum(v[-5:])/5)/max(sum(v[-20:])/20,1)
    trend=(18 if m5>m10>m20 else 10 if m5>m10 else 0)+(12 if p>m60 else 0)+(8 if m20>m60 else 0)
    position=(20 if pos<=.35 else 15 if pos<=.60 else 8 if pos<=.80 else 0)+(8 if p<m20*1.25 else 0)
    momentum=(12 if dif is not None and dea is not None and dif>dea else 0)+(8 if mh is not None and mh>0 else 0)+(8 if rs is not None and 45<=rs<=72 else 0)+(6 if k>d else 0)
    funds=(10 if vr>=1.3 else 0)+(8 if vr>=1.8 else 0)+(6 if (s.get('turnover') or 0)>=2 else 0)
    basic=(8 if s.get('pe') is not None and 0<s['pe']<=35 else 0)+(4 if s.get('pb') is not None and 0<s['pb']<=5 else 0)+(4 if (s.get('total_mv') or 0)>=30e8 else 0)
    risk=(15 if s.get('change_pct',0)<=-4 else 0)+(15 if p<m20*.95 else 0)+(10 if m60 and p>m60*1.45 and ret5>.08 else 0)+(15 if (s.get('turnover') or 0)>20 else 0)
    quality=max(0,min(100,round(35+trend+.7*position+.7*momentum+.5*basic-risk))); opportunity=max(0,min(100,round(25+.9*trend+.5*position+.8*momentum+.9*funds-risk)))
    force=max(0,min(100,round(35+min(25,max(0,(vr-1)*15))+((rows[-1]['close']-rows[-1]['low'])/max(rows[-1]['high']-rows[-1]['low'],1e-6))*20+max(-10,min(10,ret5*100))+(5 if (s.get('turnover') or 0)>=2 else 0)+(5 if (s.get('turnover') or 0)>=5 else 0))))
    st=[]; why=[]
    def add(key,reason): st.append(key); why.append(reason)
    if p/low60<=1.35 and p<m20*1.25 and m5>=m10 and vr>=1.15 and ret20>-.05 and risk<20:add('A','60日低位+均线修复+量能启动')
    if max(c[-21:-1]) and p>=max(c[-21:-1])*.995 and p>m20 and m5>m10 and vr>=1.3 and (mh is None or mh>0):add('B','20日平台突破+趋势量能+MACD确认')
    if m5>m10>m20 and -.12<=dd20<=-.025 and p>=m10*.985 and vc<.9 and (rs is None or rs>45):add('C','主升趋势回踩+缩量+均线承接')
    if p>m20 and ret5>-.06 and vr>=1.1 and (s.get('turnover') or 0)>.5 and force>=55:add('D','量价成本代理+趋势承接（非真实筹码分布）')
    if (s.get('total_mv') or 0)>=100e8 and p>m20 and trend>=20 and (s.get('pe') is None or 0<s['pe']<=60):add('E','大市值+趋势质量+估值约束')
    if rs is not None and rs<40 and p>m5 and ret5>-.08 and ((mh is not None and mh>0) or k>d):add('F','RSI超跌+站回MA5+动能转强')
    if vr>=1.8 and (s.get('turnover') or 0)>=3 and ret5>0 and force>=60:add('G','量比+换手+上涨+动能同步')
    blocked=risk>=25 or s.get('change_pct',0)<=-6 or (s.get('turnover') or 0)>20
    if blocked:add('H','硬风险条件触发')
    resonance=len([x for x in st if x!='H']); tier='D' if blocked else 'S' if resonance>=3 and quality>=70 and opportunity>=70 else 'A' if resonance>=2 and quality>=58 else 'B' if resonance else 'C'
    action='🔴 风险拦截' if blocked else '🟢 当前可买' if tier=='S' and s.get('change_pct',0)<=3.5 else '🟡 等待回踩' if tier=='S' else '🟡 等待确认' if tier=='A' else '👀 观察' if tier=='B' else '—'
    stop=max(0,p-1.5*(a or p*.03)); target=p+2.5*(a or p*.03); risk_per=max(.01,p-stop)
    provider=rows[-1].get('source','unknown') if rows else 'unknown'
    return {**s,'kline_source':provider,'kline_rows':len(rows),'ma5':round(m5,3),'ma10':round(m10,3),'ma20':round(m20,3),'ma60':round(m60,3),'rsi14':round(rs,2) if rs is not None else None,'macd_dif':round(dif,4) if dif is not None else None,'macd_dea':round(dea,4) if dea is not None else None,'macd_hist':round(mh,4) if mh is not None else None,'kdj_k':round(k,2),'kdj_d':round(d,2),'kdj_j':round(j,2),'atr14':round(a,3) if a else None,'volume_ratio_calc':round(vr,2),'main_force_proxy':force,'position60':round(pos,3),'return5d':round(ret5*100,2),'return20d':round(ret20*100,2),'drawdown20':round(dd20*100,2),'volume_contraction':round(vc,3),'trend_score':trend,'position_score':position,'momentum_score':momentum,'funds_score':funds,'basic_score':basic,'risk_deduction':risk,'quality_score':quality,'opportunity_score':opportunity,'strategy_keys':st,'strategy_names':[STRATEGIES[x] for x in st],'resonance_count':resonance,'tier':tier,'action_status':action,'signal_reason':'；'.join(why[:5]) or '暂无有效策略信号','target_price':round(target,2),'stop_loss':round(stop,2),'risk_reward':round((target-p)/risk_per,2),'signal_confidence':round(min(99,max(1,opportunity*.45+quality*.35+force*.20)),1),'signal_time':dt.datetime.now(dt.timezone.utc).isoformat(),'data_quality':'technical_real'}

def scan_all(workers=6,kline_limit=180):
    stocks=fetch_market(); indices=fetch_indices(); total=len(stocks); now=dt.datetime.now(dt.timezone.utc).isoformat()
    probe=source_probe('600519')
    write_json(DATA/'provider_health.json',{'checked_at':now,'probe_symbol':'600519','providers':probe,'healthy_providers':sum(1 for x in probe.values() if x.get('ok')),'data_quality':'real_provider_probe'})
    if not any(x.get('ok') for x in probe.values()):
        write_json(DATA/'scan_status.json',{'status':'blocked','reason':'all_kline_providers_unavailable','universe':total,'scanned':0,'failed':total,'progress':0})
        raise RuntimeError('All K-line providers unavailable')
    breadth={'advancers':sum(x['change_pct']>0 for x in stocks),'decliners':sum(x['change_pct']<0 for x in stocks),'flat':sum(x['change_pct']==0 for x in stocks),'limit_up':sum(x['change_pct']>=9.5 for x in stocks),'limit_down':sum(x['change_pct']<=-9.5 for x in stocks)}
    write_json(DATA/'scan_status.json',{'status':'running','started_at':now,'universe':total,'scanned':0,'failed':0,'progress':0})
    results=[]; failed=0
    def one(s):
        rows=robust_kline(s['symbol'],kline_limit); return score_signal(s,rows),rows
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fs={ex.submit(one,s):s for s in stocks}
        for i,f in enumerate(as_completed(fs),1):
            try:
                q,rows=f.result()
                if q: results.append((q,rows))
                else: failed+=1
            except Exception: failed+=1
            if i%100==0 or i==total: write_json(DATA/'scan_status.json',{'status':'running','started_at':now,'universe':total,'scanned':i,'failed':failed,'progress':round(i/max(1,total)*100,1)})
    results.sort(key=lambda x:(x[0]['tier']=='D',-x[0]['resonance_count'],-x[0]['opportunity_score'],-x[0]['quality_score']))
    signals=[x[0] for x in results]; qualified=[x for x in results if x[0]['tier'] in ('S','A','B')]; keep=sorted(qualified,key=lambda x:(-x[0]['opportunity_score'],-x[0]['quality_score']))[:600]; keep_names={x[0]['symbol']+'.json' for x in keep}
    for p in STOCKS.glob('*.json'):
        if p.name not in keep_names: p.unlink(missing_ok=True)
    for q,rows in keep: write_json(STOCKS/(q['symbol']+'.json'),{'stock':q,'klines':rows})
    rg=regime(indices,breadth); source_counts={}
    for q in signals: source_counts[q.get('kline_source','unknown')]=source_counts.get(q.get('kline_source','unknown'),0)+1
    market_obj={'updated_at':now,'source':'Sina A-share list + multi-source daily K-line','universe':total,'scanned':len(signals),'failed':failed,'coverage_pct':round(len(signals)/max(1,total)*100,2),'kline_source_counts':source_counts,'indices':indices,'breadth':breadth,'regime':rg,'data_quality':'real_market_and_multi_source_daily_technical'}
    write_json(DATA/'market.json',market_obj); write_json(DATA/'signals.json',{'updated_at':now,'universe':total,'scanned':len(signals),'failed':failed,'coverage_pct':round(len(signals)/max(1,total)*100,2),'items':signals,'strategy_catalog':STRATEGIES,'methodology':'A-H multi-factor technical engine; D is a cost/volume proxy, not true chip distribution.'})
    write_json(DATA/'scan_status.json',{'status':'success','finished_at':dt.datetime.now(dt.timezone.utc).isoformat(),'universe':total,'scanned':len(signals),'failed':failed,'coverage_pct':round(len(signals)/max(1,total)*100,2),'progress':100})
    return market_obj

def update_news():
    items=[]; now=dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        html=S.get(NEWS_URL,timeout=8).text
        for m in re.finditer(r'<a[^>]+href=[\'\"]([^\'\"]+)[\'\"][^>]*>(.*?)</a>',html,re.I|re.S):
            title=re.sub(r'<[^>]+>','',m.group(2)); title=re.sub(r'\s+',' ',title).strip(); href=m.group(1)
            if 8<=len(title)<=120 and ('finance.sina.com.cn' in href or href.startswith('/')):
                if title not in {x['title'] for x in items}: items.append({'title':title,'url':href if href.startswith('http') else 'https://finance.sina.com.cn'+href,'source':'Sina Finance 7x24','time':now})
            if len(items)>=30: break
    except Exception: pass
    write_json(DATA/'news.json',{'updated_at':now,'source':'Sina Finance 7x24','items':items,'count':len(items),'data_quality':'verified_web_fetch_only'}); return items

if __name__=='__main__': scan_all(); update_news()