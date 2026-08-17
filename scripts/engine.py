import json,math,re,time,datetime as dt
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data';STOCKS=DATA/'stocks';STOCKS.mkdir(parents=True,exist_ok=True)
UA='Mozilla/5.0';L='https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData';K='https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData';Q='https://hq.sinajs.cn/list=';NEWS='https://finance.sina.com.cn/7x24/notification.shtml';EM='https://push2.eastmoney.com/api/qt/stock/get';UT='bd1d9ddb04089700cf9c27f6f7426281'
S=requests.Session();S.mount('https://',HTTPAdapter(max_retries=Retry(total=3,backoff_factor=.5,status_forcelist=(429,500,502,503,504),allowed_methods=['GET'])));S.headers.update({'User-Agent':UA,'Referer':'https://finance.sina.com.cn/'})
STR={'A':'低位启动','B':'主升突破','C':'回踩二波','D':'筹码结构穿透','E':'龙头强度','F':'超跌反转','G':'量价异动','H':'风险拦截'}
def n(x,d=None):
 try:v=float(x);return d if math.isnan(v) else v
 except:return d
def w(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix('.tmp');t.write_text(json.dumps(x,ensure_ascii=False,separators=(',',':')),encoding='utf8');t.replace(p)
def mo(c):return 1 if c.startswith(('6','9','5')) else 0
def fc(c):return c+('.SH' if mo(c) else '.SZ')
def kl(code,lim=180):
 try:
  a=S.get(K,params={'symbol':('sh' if mo(code) else 'sz')+code,'scale':240,'ma':'5,10,20,60','datalen':lim},timeout=15).json() or []
  return [{'date':str(x.get('day',''))[:10],'open':n(x.get('open')),'close':n(x.get('close')),'high':n(x.get('high')),'low':n(x.get('low')),'volume':n(x.get('volume'),0),'amount':n(x.get('amount'),0)} for x in a]
 except:return []
def market():
 a=[]
 for node in ('sh_a','sz_a'):
  for page in range(1,101):
   try:r=S.get(L,params={'node':node,'page':page,'num':100,'sort':'symbol','asc':1},timeout=15).json() or []
   except:break
   if not r:break
   a+=r
   if len(r)<100:break
   time.sleep(.03)
 out={x.get('code'):x for x in a if x.get('code')};z=[]
 for c,x in out.items():
  name=str(x.get('name') or '')
  if not re.fullmatch(r'\d{6}',str(c)) or not name or any(q in name.upper() for q in ('ST','退','停牌')) or str(c).startswith(('8','4','68')):continue
  z.append({'code':fc(c),'symbol':c,'name':name,'price':n(x.get('trade')),'change_pct':n(x.get('changepercent'),0),'change':n(x.get('pricechange'),0),'volume':n(x.get('volume'),0),'amount':n(x.get('amount'),0),'turnover':n(x.get('turnoverratio'),0),'pe':n(x.get('per')),'pb':n(x.get('pb')),'high':n(x.get('high')),'low':n(x.get('low')),'open':n(x.get('open')),'prev_close':n(x.get('settlement')),'total_mv':n(x.get('mktcap'))*10000 if n(x.get('mktcap')) is not None else None,'float_mv':n(x.get('nmc'))*10000 if n(x.get('nmc')) is not None else None,'sector':'未分类'})
 return z
def idx():
 try:
  t=S.get(Q+'sh000001,sz399001,sz399006,sh000300',timeout=10).content.decode('gbk','ignore');o=[]
  for line in t.splitlines():
   m=re.search(r'hq_str_([a-z0-9]+)="([^"]*)"',line,re.I)
   if m:
    p=m.group(2).split(',');pc=n(p[2]) if len(p)>2 else None;ch=n(p[3],0) if len(p)>3 else 0;o.append({'code':m.group(1),'name':p[0],'price':n(p[1]),'change':ch,'change_pct':ch/pc*100 if pc else None})
  return o
 except:return []
def regime(a):
 if not a:return {'regime':'数据不足','score':None,'position':'—','risk':'未知','directive':'等待指数数据'}
 avg=sum(x['change_pct'] for x in a if x.get('change_pct') is not None)/max(1,len([x for x in a if x.get('change_pct') is not None]));score=max(0,min(100,round(50+avg*12)))
 if score>=65:return {'regime':'偏强上行','score':score,'position':'60%~80%','risk':'中低','directive':'优先主升突破与强势回踩，控制追高','avg_change_pct':round(avg,2)}
 if score>=55:return {'regime':'震荡偏强','score':score,'position':'40%~60%','risk':'中','directive':'高共振优先，回踩确认后参与','avg_change_pct':round(avg,2)}
 if score>=45:return {'regime':'震荡','score':score,'position':'30%~50%','risk':'中','directive':'降低频率，等待结构确认','avg_change_pct':round(avg,2)}
 return {'regime':'偏弱防守','score':score,'position':'10%~30%','risk':'中高','directive':'冻结追涨，优先风险拦截','avg_change_pct':round(avg,2)}
def sma(a,k):return sum(a[-k:])/k if len(a)>=k else None
def rsi(a,k=14):
 if len(a)<k+1:return None
 g=[max(a[i]-a[i-1],0) for i in range(-k,0)];l=[max(a[i-1]-a[i],0) for i in range(-k,0)];ag=sum(g)/k;al=sum(l)/k;return 100 if al==0 else 100-100/(1+ag/al)
def atr(a,k=14):
 if len(a)<k+1:return None
 t=[max(a[i]['high']-a[i]['low'],abs(a[i]['high']-a[i-1]['close']),abs(a[i]['low']-a[i-1]['close'])) for i in range(1,len(a))];return sum(t[-k:])/k
def macd(a):
 if len(a)<35:return None,None,None
 e12=sum(a[:12])/12;e26=sum(a[:26])/26;d=[]
 for i,x in enumerate(a):
  if i>=12:e12=2*x/13+11*e12/13
  if i>=26:e26=2*x/27+25*e26/27;d.append(e12-e26)
 if len(d)<9:return None,None,None
 dea=sum(d[:9])/9
 for x in d[9:]:dea=x/5+4*dea/5
 return d[-1],dea,2*(d[-1]-dea)
def kdj(r):
 k=d=50
 for i in range(8,len(r)):
  hi=max(x['high'] for x in r[i-8:i+1]);lo=min(x['low'] for x in r[i-8:i+1]);v=50 if hi==lo else (r[i]['close']-lo)/(hi-lo)*100;k=(2*k+v)/3;d=(2*d+k)/3
 return k,d,3*k-2*d
def sig(s,r):
 if len(r)<80 or not s.get('price'):return None
 c=[x['close'] for x in r];v=[x['volume'] for x in r];p=c[-1];m5,m10,m20,m60=[sma(c,k) for k in (5,10,20,60)];a=atr(r);rs=rsi(c);dif,dea,mh=macd(c);k,d,j=kdj(r);vr=v[-1]/(sma(v,20) or 1);low=min(c[-60:]);hi=max(c[-60:]);pos=(p-low)/(hi-low) if hi>low else .5;ret5=p/c[-6]-1;ret20=p/c[-21]-1;dd=p/max(c[-20:])-1;vc=(sum(v[-5:])/5)/(sum(v[-20:])/20 or 1)
 trend=(18 if m5>m10>m20 else 10 if m5>m10 else 0)+(12 if p>m60 else 0)+(8 if m20>m60 else 0);position=(20 if pos<=.35 else 15 if pos<=.6 else 8 if pos<=.8 else 0)+(8 if p<m20*1.25 else 0);momentum=(12 if dif is not None and dea is not None and dif>dea else 0)+(8 if mh and mh>0 else 0)+(8 if rs and 45<=rs<=72 else 0)+(6 if k>d else 0);funds=(10 if vr>=1.3 else 0)+(8 if vr>=1.8 else 0)+(6 if (s.get('turnover') or 0)>=2 else 0);basic=(8 if s.get('pe') is not None and 0<s['pe']<=35 else 0)+(4 if s.get('pb') is not None and 0<s['pb']<=5 else 0)+(4 if (s.get('total_mv') or 0)>=30e8 else 0);risk=(15 if s.get('change_pct',0)<=-4 else 0)+(15 if p<m20*.95 else 0)+(10 if m60 and p>m60*1.45 and ret5>.08 else 0)+(15 if (s.get('turnover') or 0)>20 else 0);quality=max(0,min(100,round(35+trend+.7*position+.7*momentum+.5*basic-risk)));opp=max(0,min(100,round(25+.9*trend+.5*position+.8*momentum+.9*funds-risk)));mf=max(0,min(100,round(35+min(25,max(0,(vr-1)*15))+((r[-1]['close']-r[-1]['low'])/max(r[-1]['high']-r[-1]['low'],1e-6))*20+max(-10,min(10,ret5*100))+(5 if (s.get('turnover') or 0)>=2 else 0)+(5 if (s.get('turnover') or 0)>=5 else 0))))
 st=[];nm=[];why=[]
 def add(k,nm0,why0):st.append(k);nm.append(nm0);why.append(why0)
 if low and p/low<=1.35 and p<m20*1.25 and m5>=m10 and vr>=1.15 and ret20>-.05 and risk<20:add('A','低位启动','60日低位+均线修复+量能启动')
 if max(c[-21:-1]) and p>=max(c[-21:-1])*.995 and p>m20 and m5>m10 and vr>=1.3 and (mh is None or mh>0):add('B','主升突破','20日平台突破+趋势量能+MACD确认')
 if m5>m10>m20 and -.12<=dd<=-.025 and p>=m10*.985 and vc<.9 and (rs is None or rs>45):add('C','回踩二波','主升趋势回踩+缩量+均线承接')
 if p>m20 and ret5>-.06 and vr>=1.1 and (s.get('turnover') or 0)>.5 and mf>=55:add('D','筹码结构穿透','量价成本代理+趋势承接（非真实筹码分布）')
 if (s.get('total_mv') or 0)>=100e8 and p>m20 and trend>=20 and (s.get('pe') is None or 0<s['pe']<=60):add('E','龙头强度','大市值+趋势质量+估值约束')
 if rs is not None and rs<40 and p>m5 and ret5>-.08 and ((mh is not None and mh>0) or k>d):add('F','超跌反转','RSI超跌+站回MA5+动能转强')
 if vr>=1.8 and (s.get('turnover') or 0)>=3 and ret5>0 and mf>=60:add('G','量价异动','量比+换手+上涨+动能同步')
 blocked=risk>=25 or s.get('change_pct',0)<=-6 or (s.get('turnover') or 0)>20
 if blocked:add('H','风险拦截','硬风险条件触发')
 pos=len([x for x in st if x!='H']);tier='D' if blocked else 'S' if pos>=3 and quality>=70 and opp>=70 else 'A' if pos>=2 and quality>=58 else 'B' if pos else 'C';action='🔴 风险拦截' if blocked else '🟢 当前可买' if tier=='S' and s.get('change_pct',0)<=3.5 else '🟡 等待回踩' if tier=='S' else '🟡 等待确认' if tier=='A' else '👀 观察' if tier=='B' else '—';stop=max(0,p-1.5*a);target=p+2.5*a
 return {**s,'ma5':round(m5,3),'ma10':round(m10,3),'ma20':round(m20,3),'ma60':round(m60,3),'rsi14':round(rs,2) if rs is not None else None,'macd_dif':round(dif,4) if dif is not None else None,'macd_dea':round(dea,4) if dea is not None else None,'macd_hist':round(mh,4) if mh is not None else None,'kdj_k':round(k,2),'kdj_d':round(d,2),'kdj_j':round(j,2),'atr14':round(a,3),'volume_ratio_calc':round(vr,2),'main_force_proxy':mf,'position60':round(pos,3),'return5d':round(ret5*100,2),'return20d':round(ret20*100,2),'drawdown20':round(dd*100,2),'volume_contraction':round(vc,3),'trend_score':trend,'position_score':position,'momentum_score':momentum,'funds_score':funds,'basic_score':basic,'risk_deduction':risk,'quality_score':quality,'opportunity_score':opp,'strategy_keys':st,'strategy_names':nm,'resonance_count':pos,'tier':tier,'action_status':action,'signal_reason':'；'.join(why[:4]) or '暂无有效策略信号','target_price':round(target,2),'stop_loss':round(stop,2),'risk_reward':round((target-p)/max(.01,p-stop),2),'signal_time':dt.datetime.now(dt.timezone.utc).isoformat(),'data_quality':'technical_real'}
def fund(code):
 try:
  d=S.get(EM,params={'secid':f'{mo(code)}.{code}','ut':UT,'fields':'f12,f162,f164,f167,f116,f117'},timeout=10).json().get('data') or {};return {'roe':n(d.get('f164')),'pe_real':n(d.get('f162')),'pb_real':n(d.get('f167')),'total_mv_real':n(d.get('f116')),'float_mv_real':n(d.get('f117'))}
 except:return {}
def scan_all(workers=12,kline_limit=180):
 stocks=market();ix=idx();rg=regime(ix);w(DATA/'market.json',{'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'count':len(stocks),'source':'Sina Finance A-share list','indices':ix,'regime':rg,'items':stocks});out=[]
 with ThreadPoolExecutor(max_workers=workers) as ex:
  fs={ex.submit(kl,s['symbol'],kline_limit):s for s in stocks if s.get('price') and s.get('volume',0)>0}
  for f in as_completed(fs):
   s=fs[f];r=f.result();q=sig(s,r)
   if q:
    out.append(q)
    if q['tier'] in ('S','A'):w(STOCKS/(s['symbol']+'.json'),{'stock':q,'klines':r[-180:],'source':'Sina Finance daily K-line','note':'D为成交成本代理，不代表真实筹码分布'})
 top=sorted(out,key=lambda x:(x['tier']=='S',x['resonance_count'],x['opportunity_score'],x['quality_score']),reverse=True)[:500]
 with ThreadPoolExecutor(max_workers=10) as ex:
  fs={ex.submit(fund,x['symbol']):x for x in top}
  for f in as_completed(fs):fs[f].update(f.result())
 for x in top:x['fundamental_status']='真实财务摘要' if x.get('roe') is not None else '待财报数据'
 out.sort(key=lambda x:(x['tier']=='S',x['resonance_count'],x['opportunity_score'],x['quality_score']),reverse=True)
 p={'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'universe_count':len(stocks),'scanned_count':len(out),'source':'Sina realtime list + daily K-line','market_regime':rg,'strategies':STR,'items':out[:300]};w(DATA/'signals.json',p);return p
def news(limit=50):
 try:
  t=S.get(NEWS,timeout=15).text;p=re.findall(r'(20\d{2}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2}).{0,800}?>([^<>]{8,180})<',t,re.S);o=[];seen=set()
  for ts,title in p:
   title=re.sub(r'\s+',' ',title).strip()
   if title in seen or any(x in title for x in ('新浪财经','刷新','更多')):continue
   seen.add(title);o.append({'id':f'sina-{len(o)}','source':'新浪财经7×24','title':title,'time':ts,'url':NEWS})
   if len(o)>=limit:break
  return o
 except:return []
def update_news():
 a=news();w(DATA/'news.json',{'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':'Sina Finance 7x24','count':len(a),'items':a,'status':'ok' if a else 'unavailable'});return a
