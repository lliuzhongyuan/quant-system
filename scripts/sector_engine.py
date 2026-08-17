import json, re, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'
NODES='https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodes'
LIST='https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
H={'User-Agent':'Mozilla/5.0','Referer':'https://vip.stock.finance.sina.com.cn/'}

def walk(x,out):
    if isinstance(x,list):
        if len(x)>=3 and all(isinstance(v,str) for v in x[:3]) and re.fullmatch(r'[A-Za-z0-9_]+',x[2] or ''): out.append((x[0],x[2]))
        for y in x: walk(y,out)
    elif isinstance(x,dict):
        for y in x.values(): walk(y,out)

def run():
    s=requests.Session(); s.headers.update(H)
    result={'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':'Sina Finance','status':'unavailable','sectors':[]}
    try:
        nodes=s.get(NODES,timeout=15).json(); pairs=[]; walk(nodes,pairs)
        pairs=[p for p in pairs if p[1].startswith('sw_')]
        pairs=list(dict.fromkeys(pairs))
        def one(pair):
            name,node=pair
            try:
                rows=s.get(LIST,params={'node':node,'page':1,'num':100,'sort':'changepercent','asc':0},timeout=12).json() or []
                vals=[]
                for x in rows:
                    try: vals.append(float(x.get('changepercent'))) 
                    except: pass
                return {'name':name,'node':node,'count':len(rows),'avg_change_pct':round(sum(vals)/len(vals),2) if vals else None,'top':sorted([{'symbol':x.get('code'),'name':x.get('name'),'change_pct':x.get('changepercent')} for x in rows if x.get('code')],key=lambda z:z.get('change_pct') or -999,reverse=True)[:5]}
            except:return None
        with ThreadPoolExecutor(max_workers=8) as ex:
            for f in as_completed([ex.submit(one,p) for p in pairs]):
                v=f.result()
                if v: result['sectors'].append(v)
        result['sectors'].sort(key=lambda x:x.get('avg_change_pct') if x.get('avg_change_pct') is not None else -999,reverse=True)
        result['status']='verified' if result['sectors'] else 'unavailable'
    except Exception as e: result['error']=type(e).__name__
    (DATA/'sector_board.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8'); print(json.dumps({'status':result['status'],'sectors':len(result['sectors'])},ensure_ascii=False))
if __name__=='__main__':run()
