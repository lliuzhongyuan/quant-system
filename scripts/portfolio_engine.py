import json, datetime as dt
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'

def run():
    sig=json.loads((DATA/'signals.json').read_text(encoding='utf8')).get('items',[]) if (DATA/'signals.json').exists() else []
    selected=[x for x in sig if x.get('tier') in ('S','A') and 'H' not in (x.get('strategy_keys') or [])]
    selected=sorted(selected,key=lambda x:(x.get('opportunity_score',0),x.get('quality_score',0),x.get('resonance_count',0)),reverse=True)
    out=[]
    for x in selected[:20]:
        stop=x.get('stop_loss'); price=x.get('price'); rr=x.get('risk_reward')
        out.append({'symbol':x.get('symbol'),'name':x.get('name'),'tier':x.get('tier'),'price':price,'opportunity':x.get('opportunity_score'),'quality':x.get('quality_score'),'resonance':x.get('resonance_count'),'stop_loss':stop,'target_price':x.get('target_price'),'risk_reward':rr,'risk_note':'研究仓位，不连接券商；实际成交需人工确认'})
    result={'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'research_only','account_assumption':'not hard-coded; UI local account is user input','max_candidates':20,'candidates':out,'position_formula':'risk_budget = NAV * risk_pct; shares = floor(risk_budget / (entry-stop)) rounded to 100 shares; apply max position and liquidity caps before any order','broker_connected':False}
    (DATA/'portfolio_plan.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'status':result['status'],'candidates':len(out)},ensure_ascii=False))
if __name__=='__main__':run()
