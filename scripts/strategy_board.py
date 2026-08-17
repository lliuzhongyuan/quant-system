import json, datetime as dt
from pathlib import Path
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'

def run():
    market=json.loads((DATA/'market.json').read_text(encoding='utf8')) if (DATA/'market.json').exists() else {}
    items=(json.loads((DATA/'signals.json').read_text(encoding='utf8')).get('items') or []) if (DATA/'signals.json').exists() else []
    groups=defaultdict(list)
    for x in items:
        for k in x.get('strategy_keys') or []:
            if k!='H': groups[k].append(x)
    ranked=[]
    for k,rows in groups.items():
        rows=sorted(rows,key=lambda x:(x.get('opportunity_score',0),x.get('quality_score',0)),reverse=True)
        ranked.append({'strategy':k,'name':{'A':'低位启动','B':'主升突破','C':'回踩二波','D':'筹码结构穿透','E':'龙头强度','F':'超跌反转','G':'量价异动'}.get(k,k),'count':len(rows),'top':[{'symbol':x.get('symbol'),'name':x.get('name'),'tier':x.get('tier'),'score':x.get('opportunity_score'),'reason':x.get('signal_reason')} for x in rows[:10]]})
    ranked.sort(key=lambda x:x['count'],reverse=True)
    out={'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'data_status':market.get('data_status','unknown'),'source':'derived only from verified market/signals data','market_regime':market.get('regime'),'strategy_rank':ranked,'leader_board':sorted([{'symbol':x.get('symbol'),'name':x.get('name'),'tier':x.get('tier'),'opportunity':x.get('opportunity_score'),'quality':x.get('quality_score'),'resonance':x.get('resonance_count')} for x in items if x.get('tier') in ('S','A')],key=lambda x:(x['opportunity'],x['quality']),reverse=True)[:30]}
    (DATA/'strategy_board.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'strategies':len(ranked),'leaders':len(out['leader_board'])},ensure_ascii=False))
if __name__=='__main__':run()
