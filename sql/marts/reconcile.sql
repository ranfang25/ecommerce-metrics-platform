-- 独立复算：不读取mart表，直接按三个事实粒度分别聚合
WITH p AS (SELECT ?::DATE AS start,?::DATE AS finish,?::VARCHAR AS device,?::VARCHAR AS source),
e AS (SELECT x.* FROM fact_events x,p WHERE event_date BETWEEN start AND finish AND (p.device='全部' OR x.device=p.device) AND (p.source='全部' OR x.first_source=p.source)),
s AS (SELECT x.* FROM fact_sessions x,p WHERE session_date BETWEEN start AND finish AND (p.device='全部' OR x.device=p.device) AND (p.source='全部' OR x.first_source=p.source)),
o AS (SELECT x.* FROM fact_orders x,p WHERE purchase_date BETWEEN start AND finish AND (p.device='全部' OR x.device=p.device) AND (p.source='全部' OR x.first_source=p.source)),
session_totals AS (SELECT count(*) AS n,coalesce(sum(CASE WHEN has_view THEN 1 ELSE 0 END),0) AS views,
 coalesce(sum(CASE WHEN has_cart THEN 1 ELSE 0 END),0) AS carts,
 coalesce(sum(CASE WHEN has_checkout THEN 1 ELSE 0 END),0) AS checkouts,
 coalesce(sum(CASE WHEN has_purchase THEN 1 ELSE 0 END),0) AS buyers,
 coalesce(sum(CASE WHEN view_ts IS NOT NULL THEN 1 ELSE 0 END),0) AS f1,
 coalesce(sum(CASE WHEN cart_ts IS NOT NULL THEN 1 ELSE 0 END),0) AS f2,
 coalesce(sum(CASE WHEN checkout_ts IS NOT NULL THEN 1 ELSE 0 END),0) AS f3,
 coalesce(sum(CASE WHEN purchase_ts IS NOT NULL THEN 1 ELSE 0 END),0) AS f4 FROM s)
SELECT (SELECT count(*) FROM (SELECT user_id FROM e WHERE user_id IS NOT NULL GROUP BY user_id)) AS M01,
 n AS M02,views AS M03,carts AS M04,checkouts AS M05,buyers AS M06,
 (SELECT count(DISTINCT transaction_id) FROM o) AS M07,(SELECT sum(revenue_usd) FROM o) AS M08,
 (SELECT sum(revenue_usd)*1.0/nullif(count(revenue_usd),0) FROM o) AS M09,
 buyers*1.0/nullif(n,0) AS M10,f2*1.0/nullif(f1,0) AS M11,f4*1.0/nullif(f3,0) AS M12 FROM session_totals;
