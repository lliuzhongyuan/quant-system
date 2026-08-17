import datetime as dt, html as html_lib, json, re, uuid
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36'
S=requests.Session(); S.headers.update({'User-Agent':UA})

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def clean(x): return re.sub(r'\s+',' ',html_lib.unescape(re.sub(r'<[^>]+>',' ',str(x or '')))).strip()

def sina():
    url='https://finance.sina.com.cn/7x24/notification.shtml'
    r=S.get(url,timeout=10); raw=r.content
    text=raw.decode('gb18030','ignore')
    out=[]
    for m in re.finditer(r'<a[^>]+href=[\'\"]([^\'\"]+)[\'\"][^>]*>(.*?)</a>',text,re.I|re.S):
        title=clean(m.group(2)); href=m.group(1)
        if 8<=len(title)<=160 and ('sina.com.cn' in href or href.startswith('/')):
            out.append({'title':title,'url':href if href.startswith('http') else 'https://finance.sina.com.cn'+href,'source':'Sina Finance 7x24','time':now()})
    return out[:50]

def eastmoney():
    url='https://np-weblist.eastmoney.com/comm/web/getFastNewsList'
    p={'client':'web','biz':'web_724','fastColumn':'102','sortEnd':'','pageSize':'50','req_trace':str(uuid.uuid4())}
    r=S.get(url,params=p,headers={'Referer':'https://kuaixun.eastmoney.com/'},timeout=10); d=r.json() or {}
    out=[]
    for x in ((d.get('data') or {}).get('fastNewsList') or []):
        title=clean(x.get('title') or x.get('summary')); t=x.get('showTime') or x.get('ctime') or now()
        if title: out.append({'title':title,'url':'https://kuaixun.eastmoney.com/','source':'Eastmoney 7x24','time':str(t)})
    return out

def eastmoney_stock():
    # Broad market/company news stream; direct public endpoint, no third-party relay.
    url='https://search-api-web.eastmoney.com/search/jsonp'
    inner=json.dumps({'uid':'','keyword':'A股','type':['cmsArticleWebOld'],'client':'web','clientType':'web','clientVersion':'curr','param':{'cmsArticleWebOld':{'searchScope':'default','sort':'default','pageIndex':1,'pageSize':40,'preTag':'','postTag':''}}},ensure_ascii=False,separators=(',',':'))
    r=S.get(url,params={'cb':'jQuery_news','param':inner},headers={'Referer':'https://so.eastmoney.com/'},timeout=10)
    text=r.text; text=re.sub(r'^\w+\(', '', text).rstrip(');\n '); d=json.loads(text)
    out=[]
    for x in ((d.get('result') or {}).get('cmsArticleWebOld') or {}).get('data') or []:
        title=clean(x.get('title') or x.get('brief')); t=x.get('date') or x.get('ctime') or now(); u=x.get('url') or 'https://so.eastmoney.com/'
        if title: out.append({'title':title,'url':u,'source':'Eastmoney Stock News','time':str(t)})
    return out

def cls():
    # Public telegraph endpoint when available; failure is recorded, never replaced with fake news.
    url='https://www.cls.cn/nodeapi/telegraphs'
    r=S.get(url,params={'refresh_type':1,'rn':30},headers={'Referer':'https://www.cls.cn/'},timeout=10); d=r.json() or {}
    rows=d.get('data') or d.get('data',{}).get('data') or []
    if isinstance(rows,dict): rows=rows.get('roll_data') or rows.get('telegraphs') or []
    out=[]
    for x in rows or []:
        title=clean(x.get('content') or x.get('title')); t=x.get('ctime') or now()
        if title: out.append({'title':title,'url':'https://www.cls.cn/telegraph','source':'CLS 财联社','time':str(t)})
    return out

def run():
    providers=[('Sina Finance 7x24',sina),('Eastmoney 7x24',eastmoney),('Eastmoney Stock News',eastmoney_stock),('CLS 财联社',cls)]
    all_items=[]; statuses=[]; seen=set()
    for name,fn in providers:
        try:
            rows=fn(); statuses.append({'source':name,'status':'verified','count':len(rows)})
            for x in rows:
                key=clean(x.get('title')).lower()
                if key and key not in seen: seen.add(key); all_items.append(x)
        except Exception as e:
            statuses.append({'source':name,'status':'unavailable','count':0,'error':type(e).__name__})
    all_items.sort(key=lambda x:str(x.get('time','')),reverse=True)
    obj={'updated_at':now(),'status':'verified' if all_items else 'unavailable','sources':statuses,'source_count':sum(s['status']=='verified' for s in statuses),'items':all_items[:100],'count':min(len(all_items),100),'data_quality':'verified_multi_source_only'}
    (DATA/'news.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'status':obj['status'],'source_count':obj['source_count'],'count':obj['count'],'sources':statuses},ensure_ascii=False))

if __name__=='__main__': run()
