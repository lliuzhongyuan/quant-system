import json
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36'
SAMPLES = ('600519', '000001', '300750')
SOURCES = {
    'Yahoo Finance Spark': 'https://query1.finance.yahoo.com/v7/finance/spark',
    'Tencent QFQ': 'https://web.ifzq.gtimg.cn/appstock/fqkline/get',
    'Eastmoney QFQ': 'https://push2his.eastmoney.com/api/qt/stock/kline/get',
    'Sina KLine': 'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData/getKLineData',
}


def market(code):
    return 'sh' if str(code).startswith(('5', '6', '9')) else 'sz'


def test_http(name, code):
    s = requests.Session()
    s.headers.update({'User-Agent': UA, 'Accept': 'application/json,text/plain,*/*'})
    try:
        if name == 'Yahoo Finance Spark':
            sym = f'{code}.SS' if market(code) == 'sh' else f'{code}.SZ'
            r = s.get(SOURCES[name], params={'symbols': sym, 'range': '1y', 'interval': '1d'}, timeout=15)
            r.raise_for_status()
            obj = r.json()
            node = ((obj.get('spark') or {}).get('result') or [{}])[0]
            rows = ((node.get('response') or [{}])[0].get('timestamp') or [])
        elif name == 'Tencent QFQ':
            sym = market(code) + code
            r = s.get(SOURCES[name], params={'param': f'{sym},day,,,80,qfq', '_var': 'kline_dayqfq'}, timeout=15)
            r.raise_for_status()
            node = ((r.json().get('data') or {}).get(sym) or {})
            rows = node.get('qfqday') or node.get('day') or []
        elif name == 'Eastmoney QFQ':
            secid = ('1.' if market(code) == 'sh' else '0.') + code
            params = {
                'secid': secid, 'fields1': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13',
                'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
                'klt': 101, 'fqt': 1, 'beg': '0', 'end': '20500101', 'lmt': 80,
                'ut': 'fa5fd1943c7b386f172d6893dbbd1d0c', 'rtntype': 6,
            }
            r = s.get(SOURCES[name], params=params, headers={'Referer': 'https://quote.eastmoney.com/'}, timeout=15)
            r.raise_for_status()
            rows = ((r.json().get('data') or {}).get('klines') or [])
        else:
            r = s.get(SOURCES[name], params={'symbol': market(code) + code, 'scale': 240, 'ma': '5,10,20,60', 'datalen': 80}, timeout=15)
            r.raise_for_status()
            rows = r.json() or []
        return {'ok': len(rows) >= 80, 'rows': len(rows), 'http_status': r.status_code}
    except Exception as e:
        return {'ok': False, 'rows': 0, 'error': type(e).__name__, 'message': str(e)[:160]}


def test_baostock_all():
    try:
        import baostock as bs
        login = bs.login()
        if login.error_code != '0':
            return {c: {'ok': False, 'rows': 0, 'error': 'login', 'message': login.error_msg} for c in SAMPLES}
        out = {}
        try:
            for code in SAMPLES:
                rs = bs.query_history_k_data_plus(
                    f'{market(code)}.{code}',
                    'date,open,high,low,close,volume,amount',
                    start_date='2025-01-01', end_date='2099-12-31', frequency='d', adjustflag='2'
                )
                rows = 0
                last_date = None
                if rs.error_code != '0':
                    out[code] = {'ok': False, 'rows': 0, 'error': rs.error_code, 'message': rs.error_msg}
                    continue
                while rs.next():
                    rows += 1
                    try:
                        last_date = rs.get_row_data()[0]
                    except Exception:
                        pass
                out[code] = {'ok': rows >= 80, 'rows': rows, 'last_date': last_date}
        finally:
            try:
                bs.logout()
            except Exception:
                pass
        return out
    except Exception as e:
        return {c: {'ok': False, 'rows': 0, 'error': type(e).__name__, 'message': str(e)[:160]} for c in SAMPLES}


def main():
    out = {}
    for name in SOURCES:
        out[name] = {code: test_http(name, code) for code in SAMPLES}
        time.sleep(0.5)
    out['Baostock'] = test_baostock_all()

    summary = {}
    for name, items in out.items():
        passed = sum(1 for v in items.values() if v.get('ok'))
        summary[name] = {'passed': passed, 'total': len(SAMPLES), 'coverage': round(passed / len(SAMPLES) * 100, 1), 'production_candidate': passed == len(SAMPLES)}

    candidates = [name for name, s in summary.items() if s['production_candidate']]
    payload = {
        'status': 'PASS' if candidates else 'BLOCKED',
        'production_candidates': candidates,
        'sample_symbols': list(SAMPLES),
        'summary': summary,
        'sources': out,
        'generated_at': time.time(),
        'rule': 'A provider is production-candidate only when all 3 representative symbols return >=80 daily rows.',
    }
    p = ROOT / 'data' / 'free_source_probe.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(payload, ensure_ascii=False))
    if not candidates:
        raise SystemExit('No free provider passed the 3/3 production preflight')


if __name__ == '__main__':
    main()
