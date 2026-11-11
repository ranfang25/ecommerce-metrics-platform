-- 同一交易的日期、用户、会话或金额存在差异时整笔隔离
CREATE TABLE order_audit AS
SELECT transaction_id, count(*) AS event_rows,
 count(DISTINCT struct_pack(u:=user_id,s:=session_id,d:=event_date,a:=revenue_usd)) AS variants
FROM fact_events WHERE event_name='purchase' AND transaction_id IS NOT NULL GROUP BY 1;
CREATE TABLE quarantined_orders AS
SELECT e.* FROM fact_events e JOIN order_audit a USING(transaction_id)
WHERE e.event_name='purchase' AND a.variants>1;
CREATE TABLE fact_orders AS
WITH one AS (
 SELECT e.*, row_number() OVER (PARTITION BY e.transaction_id ORDER BY e.event_timestamp,e.event_row_id) AS n
 FROM fact_events e JOIN order_audit a USING(transaction_id)
 WHERE e.event_name='purchase' AND a.variants=1
)
SELECT e.transaction_id,e.user_id,e.session_id,e.event_date AS purchase_date,e.revenue_usd,e.event_row_id,
 coalesce(s.device,e.device) AS device,coalesce(s.first_source,e.first_source) AS first_source,
 e.items_json
FROM one e LEFT JOIN fact_sessions s USING(user_id,session_id) WHERE n=1;
-- 商品行保留数组行号，订单金额始终只从订单事实表汇总
CREATE TABLE fact_order_items AS
SELECT o.transaction_id, CAST(j.key AS INTEGER) AS item_line,
 json_extract_string(j.value,'$.item_id') AS item_id,
 try_cast(json_extract_string(j.value,'$.quantity') AS BIGINT) AS quantity,
 try_cast(json_extract_string(j.value,'$.item_revenue_in_usd') AS DECIMAL(18,2)) AS item_revenue_usd
FROM fact_orders o, json_each(o.items_json) j;
