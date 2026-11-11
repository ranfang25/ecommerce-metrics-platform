-- 会话按样本内最早事件日期归属；相同时间戳不推定先后
CREATE TABLE fact_sessions AS
WITH base AS (
 SELECT user_id,session_id,min(event_date) AS session_date,
 arg_min(device,struct_pack(t:=event_timestamp,r:=event_row_id)) AS device,
 arg_min(first_source,struct_pack(t:=event_timestamp,r:=event_row_id)) AS first_source,
 bool_or(event_name='view_item') AS has_view,
 bool_or(event_name='add_to_cart') AS has_cart,
 bool_or(event_name='begin_checkout') AS has_checkout,
 bool_or(event_name='purchase') AS has_purchase,
 min(event_timestamp) FILTER (WHERE event_name='view_item') AS view_ts,
 count(DISTINCT device)>1 AS device_changed
 FROM fact_events WHERE user_id IS NOT NULL AND session_id IS NOT NULL GROUP BY 1,2
), cart AS (
 SELECT b.*, (SELECT min(event_timestamp) FROM fact_events e WHERE e.user_id=b.user_id AND e.session_id=b.session_id AND e.event_name='add_to_cart' AND e.event_timestamp>b.view_ts) AS cart_ts FROM base b
), checkout AS (
 SELECT b.*, (SELECT min(event_timestamp) FROM fact_events e WHERE e.user_id=b.user_id AND e.session_id=b.session_id AND e.event_name='begin_checkout' AND e.event_timestamp>b.cart_ts) AS checkout_ts FROM cart b
), purchase AS (
 SELECT b.*, (SELECT min(event_timestamp) FROM fact_events e WHERE e.user_id=b.user_id AND e.session_id=b.session_id AND e.event_name='purchase' AND e.event_timestamp>b.checkout_ts) AS purchase_ts FROM checkout b
)
SELECT b.*, EXISTS (
 SELECT 1 FROM fact_events x JOIN fact_events y ON x.user_id=y.user_id AND x.session_id=y.session_id AND x.event_timestamp=y.event_timestamp
 WHERE x.user_id=b.user_id AND x.session_id=b.session_id AND
 ((x.event_name='view_item' AND y.event_name='add_to_cart') OR (x.event_name='add_to_cart' AND y.event_name='begin_checkout') OR (x.event_name='begin_checkout' AND y.event_name='purchase'))
) AS order_uncertain FROM purchase b;
