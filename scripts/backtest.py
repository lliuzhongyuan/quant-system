import json,statistics
from pathlib import Path
from engine import sig
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data';STOCKS=DATA/'stocks'
def run():
 trades=[]
 for p in STOCKS.glob('*.json'):
  try:d=json.loads(p.read_text(encoding='utf8'));stock=d['stock'];rows=d['klines']
  except:continue
  for i in range(80,len(rows)-10,5):
   hist=rows[:i+1];snap=dict(stock,price=hist[-1]['close'],change_pct=0,volume=hist[-1]['volume']);q=sig(snap,hist)
   if not q or q['tier'] not in ('S','A'):continue
   entry=hist[-1]['close'];future=rows[i+1:i+11];stop=q['stop_loss'];target=q['target_price'];exitp=future[-1]['close'];out='time_exit';ret=exitp/entry-1
   for b in future:
    if b['low']<=stop:out='stop';ret=stop/entry-1;break
    if b['high']>=target:out='target';ret=target/entry-1;break
   trades.append({'symbol':stock['symbol'],'date':hist[-1]['date'],'tier':q['tier'],'return':ret,'outcome':out})
 if not trades:r={'status':'not_generated','reason':'历史样本不足'}
 else:
  rs=[x['return'] for x in trades];win=sum(x>0 for x in rs);eq=peak=1;mdd=0
  for x in rs:eq*=1+x;peak=max(peak,eq);mdd=min(mdd,eq/peak-1)
  avg=statistics.mean(rs);sd=statistics.stdev(rs) if len(rs)>1 else 0
  r={'status':'ok','trades':len(rs),'win_rate':round(win/len(rs),4),'avg_return':round(avg,5),'total_compounded_return':round(eq-1,4),'max_drawdown':round(mdd,4),'sharpe_proxy':round(avg/sd*(len(rs)**.5),2) if sd else None,'note':'walk-forward研究样本；未计手续费、滑点、涨跌停成交限制','sample_file_count':len(list(STOCKS.glob('*.json')))}
 (DATA/'backtest.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(r,ensure_ascii=False))
if __name__=='__main__':run()
