import json, statistics, datetime as dt
from pathlib import Path
from engine import score_signal
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; STOCKS=DATA/'stocks'
ROUND_TRIP_COST=0.0015
HOLD_BARS=10

def run():
    trades=[]
    files=list(STOCKS.glob('*.json'))
    for p in files:
        try:d=json.loads(p.read_text(encoding='utf8')); stock=d['stock']; rows=d['klines']
        except Exception: continue
        for i in range(80,len(rows)-HOLD_BARS,5):
            hist=rows[:i+1]; snap=dict(stock,price=hist[-1]['close'],change_pct=0,volume=hist[-1]['volume'])
            q=score_signal(snap,hist)
            if not q or q['tier'] not in ('S','A'): continue
            entry=hist[-1]['close']; future=rows[i+1:i+1+HOLD_BARS]; stop=q['stop_loss']; target=q['target_price']; exitp=future[-1]['close']; outcome='time_exit'; gross=exitp/entry-1
            for b in future:
                if b['low']<=stop: exitp=stop; gross=exitp/entry-1; outcome='stop'; break
                if b['high']>=target: exitp=target; gross=exitp/entry-1; outcome='target'; break
            net=gross-ROUND_TRIP_COST
            trades.append({'symbol':stock['symbol'],'date':hist[-1]['date'],'tier':q['tier'],'resonance':q['resonance_count'],'gross_return':gross,'net_return':net,'outcome':outcome})
    if not trades:
        result={'status':'not_generated','reason':'历史样本不足'}
    else:
        rs=[x['net_return'] for x in trades]; wins=sum(x>0 for x in rs); eq=peak=1.0; mdd=0
        for x in rs:
            eq*=1+x; peak=max(peak,eq); mdd=min(mdd,eq/peak-1)
        avg=statistics.mean(rs); sd=statistics.stdev(rs) if len(rs)>1 else 0
        result={'status':'ok','generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'trades':len(rs),'win_rate':round(wins/len(rs),4),'avg_return':round(avg,5),'total_compounded_return':round(eq-1,4),'max_drawdown':round(mdd,4),'sharpe_proxy':round(avg/sd*(len(rs)**.5),2) if sd else None,'target_hit_rate':round(sum(x['outcome']=='target' for x in trades)/len(trades),4),'stop_hit_rate':round(sum(x['outcome']=='stop' for x in trades)/len(trades),4),'round_trip_cost':ROUND_TRIP_COST,'hold_bars':HOLD_BARS,'sample_file_count':len(files),'methodology':'同一A-H引擎的历史滚动样本；逐笔信号后向前验证，含固定双边成本代理；未模拟涨跌停、盘口冲击、真实成交队列。当前样本来自保留的高质量候选历史文件，仍不等同于全历史无幸存者偏差回测。'}
    (DATA/'backtest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8'); print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__': run()
