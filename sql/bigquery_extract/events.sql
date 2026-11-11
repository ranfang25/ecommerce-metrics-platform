-- 参数与商品分别读取，避免两个重复数组相乘
SELECT event_date, event_timestamp, event_name, user_pseudo_id,
  (SELECT value.int_value FROM UNNEST(event_params) WHERE key='ga_session_id' LIMIT 1) AS ga_session_id,
  device.category AS device,
  traffic_source.source AS first_source,
  COALESCE(CASE WHEN ecommerce.transaction_id NOT IN ('','(not set)','<Other>') THEN ecommerce.transaction_id END,
    (SELECT COALESCE(CASE WHEN value.string_value NOT IN ('','(not set)','<Other>') THEN value.string_value END,CAST(value.int_value AS STRING)) FROM UNNEST(event_params) WHERE key='transaction_id' LIMIT 1)) AS transaction_id,
  ecommerce.purchase_revenue_in_usd AS purchase_revenue_usd,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key='currency' LIMIT 1) AS currency,
  TO_JSON_STRING(ARRAY(SELECT AS STRUCT item_id, item_name, quantity, item_revenue_in_usd FROM UNNEST(items))) AS items_json
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN @start AND @end
