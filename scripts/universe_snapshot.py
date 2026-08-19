import datetime as dt
import json
import re
import time
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; LIST_URL='https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'; UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36'

def run():
    s=requests.Session(); s.headers.update({'User-Agent':UA,'Referer':'https://finance.sina.com.cn/'}); raw=[]; source_errors=[]
    for node in ('sh_a','sz_a'):
        for page in range(1,101):
            rows=None; last_error=None
            # Sina occasionally returns a transient non-JSON response on one
            # page. Retry that page instead of truncating the whole universe.
            for attempt in range(3):
                try:
                    rows=s.get(LIST_URL,params={'node':node,'page':page,'num':100,'sort':'symbol','asc':1},timeout=12).json() or []
                    last_error=None; break
                except Exception as e:
                    last_error=type(e).__name__
                    if attempt<2: time.sleep(.5*(attempt+1))
            if last_error:
                source_errors.append({'node':node,'page':page,'error':last_error,'attempts':3}); break
            if not rows: break
            raw.extend(rows)
            if len(rows)<100: break
            time.sleep(.02)
    dedup={str(x.get('code')):x for x in raw if x.get('code')}; valid=[]; tradable=[]; excluded={'ST_or退':0,'停牌':0,'非目标板块':0,'代码无效':0}
    for code,item in dedup.items():
        name=str(item.get('name') or '')
        if not re.fullmatch(r'\d{6}',code) or not name: excluded['代码无效']+=1; continue
        valid.append(code)
        if code.startswith(('8','4','68')): excluded['非目标板块']+=1; continue
        if 'ST' in name.upper() or '退' in name: excluded['ST_or退']+=1; continue
        if '停牌' in name: excluded['停牌']+=1; continue
        tradable.append(code)
    payload={'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':'Sina Finance Market_Center.getHQNodeData','raw_count':len(raw),'unique_count':len(dedup),'valid_code_count':len(valid),'tradable_universe_count':len(tradable),'excluded':excluded,'source_errors':source_errors,'definition':'动态获取沪深A股列表；排除ST/退、停牌及8/4/68代码板块。','data_quality':'real_dynamic_universe'}
    DATA.mkdir(parents=True,exist_ok=True); (DATA/'universe_stats.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8'); (DATA/'universe_codes.json').write_text(json.dumps({'updated_at':payload['updated_at'],'source':payload['source'],'codes':tradable},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(payload,ensure_ascii=False))
    if len(tradable)<3000: raise SystemExit(f'BLOCKED: dynamic tradable universe too small: {len(tradable)}')
    return payload

if __name__=='__main__': run()
