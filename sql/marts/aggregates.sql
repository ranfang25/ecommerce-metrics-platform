-- 日汇总只供趋势，周期去重与比率由统一服务重新计算
CREATE TABLE mart_daily_metrics AS
SELECT session_date AS date,device,first_source,count(*) AS sessions,
 count(*) FILTER(WHERE has_purchase) AS purchasing_sessions
FROM fact_sessions GROUP BY 1,2,3;
CREATE TABLE mart_funnel AS
SELECT session_date AS date,device,first_source,
 count(view_ts) AS viewed,count(cart_ts) AS carted,count(checkout_ts) AS checked_out,count(purchase_ts) AS purchased
FROM fact_sessions GROUP BY 1,2,3;
CREATE TABLE mart_user_segments AS
SELECT u.user_id,(SELECT max(event_date) FROM fact_events) AS as_of,
 count(DISTINCT o.transaction_id) AS orders,sum(o.revenue_usd)::DECIMAL(18,2) AS revenue_usd,
 CASE WHEN count(o.transaction_id)=0 THEN '窗内无有效交易' WHEN count(o.transaction_id)=1 THEN '窗内单次有效交易' ELSE '窗内多次有效交易' END AS segment
FROM (SELECT DISTINCT user_id FROM fact_events WHERE user_id IS NOT NULL) u
LEFT JOIN fact_orders o USING(user_id) GROUP BY 1;
