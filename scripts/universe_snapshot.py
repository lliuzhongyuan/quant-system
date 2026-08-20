import datetime as dt
import json
import re
import time
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'
LIST_URL='https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36'
MIN_TRADABLE=3000


def _session():
    s=requests.Session()
    s.headers.update({'User-Agent':UA,'Referer':'https://finance.sina.com.cn/','Accept':'application/json,text/plain,*/*'})
    return s


def _fetch_node(s,node):
    rows=[]
    errors=[]
    for page in range(1,101):
        page_rows=None
        last_error=None
        for attempt in range(5):
            try:
                r=s.get(LIST_URL,params={'node':node,'page':page,'num':100,'sort':'symbol','asc':1},timeout=12)
                r.raise_for_status()
                page_rows=r.json() or []
                last_error=None
                break
            except Exception as e:
                last_error=type(e).__name__
                if attempt<4:
                    time.sleep(0.6*(attempt+1))
        if last_error:
            errors.append({'node':node,'page':page,'error':last_error,'attempts':5})
            break
        if not page_rows:
            break
        rows.extend(page_rows)
        if len(page_rows)<100:
            break
        time.sleep(.03)
    return rows,errors


def _normalize(raw,source='Sina Finance Market_Center.getHQNodeData'):
    dedup={str(x.get('code')):x for x in raw if x.get('code')}
    valid=[]
    tradable=[]
    tradable_items=[]
    excluded={'ST_or退':0,'停牌':0,'非目标板块':0,'代码无效':0}
    for code,item in dedup.items():
        name=str(item.get('name') or '')
        if not re.fullmatch(r'\d{6}',code) or not name:
            excluded['代码无效']+=1
            continue
        valid.append(code)
        if code.startswith(('8','4','68')):
            excluded['非目标板块']+=1
            continue
        if 'ST' in name.upper() or '退' in name:
            excluded['ST_or退']+=1
            continue
        if '停牌' in name:
            excluded['停牌']+=1
            continue
        tradable.append(code)
        tradable_items.append(item)
    return dedup,valid,tradable,tradable_items,excluded


def _load_previous():
    try:
        stats=json.loads((DATA/'universe_stats.json').read_text(encoding='utf-8'))
        codes=json.loads((DATA/'universe_codes.json').read_text(encoding='utf-8'))
        market=json.loads((DATA/'universe_market.json').read_text(encoding='utf-8'))
        n=int(stats.get('tradable_universe_count') or 0)
        items=market.get('items') or []
        if n>=MIN_TRADABLE and len(codes.get('codes') or [])>=MIN_TRADABLE and len(items)>=MIN_TRADABLE:
            return stats,codes,market
    except Exception:
        pass
    return None


def run():
    DATA.mkdir(parents=True,exist_ok=True)
    s=_session()
    raw=[]
    source_errors=[]
    for node in ('sh_a','sz_a'):
        node_rows,node_errors=_fetch_node(s,node)
        raw.extend(node_rows)
        source_errors.extend(node_errors)

    dedup,valid,tradable,tradable_items,excluded=_normalize(raw)
    updated=dt.datetime.now(dt.timezone.utc).isoformat()

    # Do not destroy a previously verified full universe because one transient
    # page/API failure returned only a partial market list. Reuse it only when
    # the fresh acquisition falls below the hard minimum and the old snapshot
    # itself is complete.
    if len(tradable)<MIN_TRADABLE:
        previous=_load_previous()
        if previous is not None:
            stats,codes,market=previous
            stats['fallback_used']=True
            stats['fallback_reason']='fresh market-list acquisition below minimum'
            stats['fresh_attempt_at']=updated
            stats['fresh_attempt_tradable']=len(tradable)
            stats['source_errors']=source_errors
            stats['data_quality']='real_dynamic_universe_fallback_verified_snapshot'
            DATA.joinpath('universe_stats.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
            DATA.joinpath('universe_codes.json').write_text(json.dumps(codes,ensure_ascii=False,indent=2),encoding='utf-8')
            DATA.joinpath('universe_market.json').write_text(json.dumps(market,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
            print(json.dumps({'status':'FALLBACK','fresh_tradable':len(tradable),'verified_tradable':len(codes.get('codes') or []),'source_errors':source_errors},ensure_ascii=False))
            return stats
        raise SystemExit(f'BLOCKED: dynamic tradable universe too small: {len(tradable)}; no verified previous snapshot available')

    payload={
        'updated_at':updated,
        'source':'Sina Finance Market_Center.getHQNodeData',
        'raw_count':len(raw),
        'unique_count':len(dedup),
        'valid_code_count':len(valid),
        'tradable_universe_count':len(tradable),
        'excluded':excluded,
        'source_errors':source_errors,
        'fallback_used':False,
        'definition':'动态获取沪深A股列表；排除ST/退、停牌及8/4/68代码板块。',
        'data_quality':'real_dynamic_universe'
    }
    DATA.joinpath('universe_stats.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    DATA.joinpath('universe_codes.json').write_text(json.dumps({'updated_at':updated,'source':payload['source'],'codes':tradable},ensure_ascii=False,indent=2),encoding='utf-8')
    DATA.joinpath('universe_market.json').write_text(json.dumps({'updated_at':updated,'source':payload['source'],'tradable_universe_count':len(tradable),'items':tradable_items},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps(payload,ensure_ascii=False))
    return payload


if __name__=='__main__':
    run()
