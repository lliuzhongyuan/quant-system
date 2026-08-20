import json
from pathlib import Path
from index_sources import probe

if __name__=='__main__':
    payload=probe()
    print(json.dumps(payload,ensure_ascii=False,indent=2))
    raise SystemExit(0 if payload.get('status')=='PASS' else 1)
