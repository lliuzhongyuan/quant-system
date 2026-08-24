# -*- coding: utf-8 -*-
import re,html,hashlib,requests,xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
FEEDS=[('Google News·A股','https://news.google.com/rss/search?q=A股%20股票%20中国%20股市&hl=zh-CN&gl=CN&ceid=CN:zh-Hans'),('Google News·政策','https://news.google.com/rss/search?q=中国%20证券%20政策%20金融监管&hl=zh-CN&gl=CN&ceid=CN:zh-Hans'),('Google News·科技','https://news.google.com/rss/search?q=中国%20AI%20算力%20新能源%20汽车&hl=zh-CN&gl=CN&ceid=CN:zh-Hans')]
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36'
def clean(x): return re.sub(r'\s+',' ',html.unescape(x or '')).strip()
def fetch_and_filter_eod_news():
 out=[]; seen=set()
 for source,url in FEEDS:
  try:
   r=requests.get(url,headers={'User-Agent':UA},timeout=15); r.raise_for_status(); root=ET.fromstring(r.content)
   for item in root.findall('.//item')[:20]:
    title=clean(item.findtext('title')); link=clean(item.findtext('link')); pub=clean(item.findtext('pubDate')); desc=clean(item.findtext('description')); key=hashlib.sha1(title.encode()).hexdigest()
    if not title or key in seen: continue
    seen.add(key); iso=pub
    try: iso=parsedate_to_datetime(pub).isoformat()
    except Exception: pass
    out.append({'id':'NEWS-'+key[:12],'source':source,'time':iso,'level':'NEWS','title':title,'summary':desc[:500],'url':link,'related_sector':'','related_codes':[],'quant_impact':'待量化引擎结合行情与板块数据判断'})
  except Exception: continue
 out.sort(key=lambda x:x.get('time',''),reverse=True); return out[:50]
