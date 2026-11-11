-- 参数依次为事件/会话/交易共用的起止日期、设备和首次获客来源
WITH params AS (SELECT ?::DATE AS start,?::DATE AS finish,?::VARCHAR AS device,?::VARCHAR AS source),
e AS (SELECT x.* FROM fact_events x,params p WHERE event_date BETWEEN p.start AND p.finish AND (p.device='全部' OR x.device=p.device) AND (p.source='全部' OR x.first_source=p.source)),
s AS (SELECT x.* FROM fact_sessions x,params p WHERE session_date BETWEEN p.start AND p.finish AND (p.device='全部' OR x.device=p.device) AND (p.source='全部' OR x.first_source=p.source)),
o AS (SELECT x.* FROM fact_orders x,params p WHERE purchase_date BETWEEN p.start AND p.finish AND (p.device='全部' OR x.device=p.device) AND (p.source='全部' OR x.first_source=p.source))
SELECT (SELECT count(DISTINCT user_id) FROM e) AS M01,
 count(*) AS M02,count(*) FILTER(WHERE has_view) AS M03,count(*) FILTER(WHERE has_cart) AS M04,
 count(*) FILTER(WHERE has_checkout) AS M05,count(*) FILTER(WHERE has_purchase) AS M06,
 (SELECT count(*) FROM o) AS M07,(SELECT sum(revenue_usd) FROM o) AS M08,(SELECT avg(revenue_usd) FROM o) AS M09,
 count(*) FILTER(WHERE has_purchase)::DOUBLE/nullif(count(*),0) AS M10,
 count(cart_ts)::DOUBLE/nullif(count(view_ts),0) AS M11,count(purchase_ts)::DOUBLE/nullif(count(checkout_ts),0) AS M12,
 (SELECT count(revenue_usd) FROM o) AS amount_orders,
 (SELECT count(revenue_usd)::DOUBLE/nullif(count(*),0) FROM o) AS amount_coverage,
 (SELECT count(*) FROM e WHERE event_name='purchase') AS purchase_events,
 (SELECT count(transaction_id)::DOUBLE/nullif(count(*),0) FROM e WHERE event_name='purchase') AS transaction_id_coverage,
 count(view_ts) AS funnel_view,count(cart_ts) AS funnel_cart,count(checkout_ts) AS funnel_checkout,count(purchase_ts) AS funnel_purchase,
 count(*) FILTER(WHERE order_uncertain) AS uncertain_sessions,
 count(*) FILTER(WHERE has_purchase AND purchase_ts IS NULL) AS unmatched_purchase_sessions
FROM s;
