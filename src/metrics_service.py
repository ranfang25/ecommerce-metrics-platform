"""页面、报告与导出共用口径，不平均每日比率。"""
import json
from pathlib import Path
import duckdb
import pandas as pd
from src.common import ROOT, VERSION, now, read_json

METRIC_SQL = (ROOT/'sql/marts/metrics.sql').read_text(encoding='utf-8')


def published(output):
    output = Path(output)
    meta = read_json(output/'published.json')
    return output/meta['database'], meta


def query_metrics(con,start,end,device='全部',source='全部'):
    return con.execute(METRIC_SQL,[str(start),str(end),device,source]).df().iloc[0].to_dict()


def user_segments(con,start,end,device='全部',source='全部'):
    # 用户集合按窗内筛选事件定义，订单使用同一维度与日期范围
    return con.execute('''WITH users AS (SELECT user_id,count(*) FILTER(WHERE event_name='purchase') AS purchase_events FROM fact_events
      WHERE user_id IS NOT NULL AND event_date BETWEEN ?::DATE AND ?::DATE
      AND (?='全部' OR device=?) AND (?='全部' OR first_source=?) GROUP BY user_id),
      orders AS (SELECT user_id,count(*) AS orders,sum(revenue_usd) AS revenue FROM fact_orders
      WHERE purchase_date BETWEEN ?::DATE AND ?::DATE AND (?='全部' OR device=?) AND (?='全部' OR first_source=?) GROUP BY 1)
      SELECT u.user_id,u.purchase_events,coalesce(o.orders,0) AS orders,o.revenue,
      coalesce(o.orders,0)=0 AND u.purchase_events>0 AS unmatched_purchase,
      CASE WHEN coalesce(o.orders,0)=0 THEN '窗内无有效交易' WHEN o.orders=1 THEN '窗内单次有效交易' ELSE '窗内多次有效交易' END AS segment
      FROM users u LEFT JOIN orders o USING(user_id)''',
      [str(start),str(end),device,device,source,source]*2).df()


def funnel_groups(con,start,end,device='全部',source='全部'):
    groups = user_segments(con,start,end,device,source)
    con.register('window_segments',groups[['user_id','segment']])
    return con.execute('''SELECT g.segment,count(*) AS sessions,count(view_ts) AS viewed,count(cart_ts) AS carted,
     count(checkout_ts) AS checked_out,count(purchase_ts) AS purchased
     FROM fact_sessions s JOIN window_segments g USING(user_id) WHERE session_date BETWEEN ?::DATE AND ?::DATE
     AND (?='全部' OR device=?) AND (?='全部' OR first_source=?) GROUP BY 1''',
     [str(start),str(end),device,device,source,source]).df()


def export_metrics(metrics,filters,metadata):
    rows = [{'metric_id':k,'value':v,'filters':json.dumps(filters,ensure_ascii=False),'metric_version':VERSION,
      'run_id':metadata['run_id'],'source_kind':metadata['source_kind'],'snapshot_start':metadata['start'],
      'snapshot_end':metadata['end'],'generated_at':now()} for k,v in metrics.items()]
    return pd.DataFrame(rows).to_csv(index=False).encode('utf-8-sig')


def compare(current,previous):
    return {k:{'current':current[k],'previous':previous[k],
       'absolute':current[k]-previous[k] if pd.notna(current[k]) and pd.notna(previous[k]) else None,
       'relative':current[k]/previous[k]-1 if pd.notna(current[k]) and pd.notna(previous[k]) and previous[k]!=0 else None}
       for k in current}


def validate_period(start,end,available_start,available_end):
    return start<=end and available_start<=start and end<=available_end
