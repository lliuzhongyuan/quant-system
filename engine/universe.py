# -*- coding: utf-8 -*-
import re, logging, pandas as pd
from engine.config import MIN_PRICE,MAX_PRICE,MIN_FLOAT_MV,MAX_FLOAT_MV,MIN_LISTED_DAYS,EXCLUDE_BOARDS,EXCLUDE_ST_KEYWORDS
log=logging.getLogger(__name__)

def filter_universe_pipeline(df):
    total=len(df['code'].unique()); stats={'total_initial_stocks':total}
    pat='|'.join(re.escape(k) for k in EXCLUDE_ST_KEYWORDS)
    x=df[~df['name'].str.contains(pat,na=False,regex=True)].copy(); stats['after_st_filter']=len(x.code.unique()); stats['st_filtered_out']=total-stats['after_st_filter']
    x=x[~(x.code.str.startswith(('688','83','87','88','43'))|x.board.isin(EXCLUDE_BOARDS))].copy(); stats['after_board_filter']=len(x.code.unique()); stats['board_filtered_out']=stats['after_st_filter']-stats['after_board_filter']
    x=x[(x.close>=MIN_PRICE)&(x.close<=MAX_PRICE)].copy(); stats['after_price_filter']=len(x.code.unique()); stats['price_filtered_out']=stats['after_board_filter']-stats['after_price_filter']
    if 'float_mv' in x and x.float_mv.notna().any(): x=x[x.float_mv.isna()|((x.float_mv>=MIN_FLOAT_MV)&(x.float_mv<=MAX_FLOAT_MV))].copy()
    stats['after_mv_filter']=len(x.code.unique()); stats['mv_filtered_out']=stats['after_price_filter']-stats['after_mv_filter']
    x=x[x.bars_count>=MIN_LISTED_DAYS].copy(); stats['after_subnew_filter']=len(x.code.unique()); stats['subnew_filtered_out']=stats['after_mv_filter']-stats['after_subnew_filter']
    eps=(x.eps.isna())|(x.eps>0); profit=(x.deduct_net_profit.isna())|(x.deduct_net_profit>0); x=x[eps&profit].copy(); stats['after_financial_filter']=len(x.code.unique()); stats['financial_filtered_out']=stats['after_subnew_filter']-stats['after_financial_filter']
    stats['final_tradeable_universe']=len(x.code.unique()); stats['pass_rate_pct']=round(stats['final_tradeable_universe']/max(1,total)*100,2); stats['fundamental_status']='UNAVAILABLE_FIELDS_PASSED_THROUGH_WITHOUT_SYNTHESIS'
    return x,stats
