import json, datetime as dt
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; ARCH=DATA/'history'

def run():
    files=sorted(ARCH.glob('market_*.json')) if ARCH.exists() else []
    result={'status':'not_ready','generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'snapshots':len(files),'methodology':'样本外/滚动研究框架；只有从系统开始持续保存的全市场快照才进入正式无幸存者偏差研究，不回填伪历史','metrics':None}
    if len(files)>=30:
        result['status']='ready'; result['metrics']={'note':'快照级 walk-forward 框架已具备，正式收益统计需至少30个交易日且使用当日可见信息'}
    (DATA/'walkforward.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8'); print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':run()
