-- 原始行不按相似字段去重；快照整体重建保证幂等
CREATE TABLE fact_events AS
SELECT row_number() OVER () AS event_row_id,
 try_strptime(CAST(event_date AS VARCHAR),'%Y%m%d')::DATE AS event_date,
 CAST(event_timestamp AS BIGINT) AS event_timestamp, CAST(event_name AS VARCHAR) AS event_name,
 NULLIF(trim(CAST(user_pseudo_id AS VARCHAR)),'') AS user_id,
 CAST(ga_session_id AS BIGINT) AS session_id,
 coalesce(nullif(trim(device),''),'未知') AS device,
 coalesce(nullif(trim(first_source),''),'未知') AS first_source,
 CASE WHEN transaction_id IN ('','(not set)','<Other>') THEN NULL ELSE transaction_id END AS transaction_id,
 CAST(purchase_revenue_usd AS DECIMAL(18,2)) AS revenue_usd,
 currency, items_json
FROM raw_events;
