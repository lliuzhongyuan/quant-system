import json,sys,datetime as dt
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine.data_provider import DataProvider
from engine.news import fetch_and_filter_eod_news

def main():
 p=DataProvider(); report={'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'checks':{},'status':'FAIL'}
 df=p.load_universe_snapshot(); report['checks']['real_kline_stocks']=int(df.code.nunique()); report['checks']['real_kline_rows']=int(len(df)); report['checks']['latest_kline_date']=str(df.date.max())
 idx=p.fetch_market_indices(); report['checks']['indices']=len(idx); report['checks']['index_times']=[x.update_time for x in idx]
 sectors=p.fetch_sector_hotspots(); report['checks']['sectors']=len(sectors)
 news=fetch_and_filter_eod_news(); report['checks']['news']=len(news)
 report['provider_health']=p.provider_health
 report['status']='PASS' if report['checks']['real_kline_stocks']>=3000 and report['checks']['indices']>=4 else 'FAIL'
 Path('data/v3200_realdata_probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False))
 if report['status']!='PASS': raise SystemExit(2)
if __name__=='__main__': main()
