"""Backtest guardrail.

No performance numbers are emitted until point-in-time historical data and the
same production signal logic can be replayed with T+1 execution, fees, slippage,
limit rules and position sizing.
"""
from pathlib import Path
import json
out=Path(__file__).resolve().parents[1]/'data'/'backtest.json'
out.write_text(json.dumps({'status':'not_generated','reason':'需要点时历史全市场数据与T+1执行模型；禁止使用旧版写死指标'},ensure_ascii=False),encoding='utf-8')
print(out)
