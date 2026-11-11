-- 在控制台先执行，确认旧样本的参数与日期覆盖
SELECT event_date, event_name, COUNT(*) AS event_rows,
 COUNT(DISTINCT user_pseudo_id) AS observed_user_ids,
 COUNTIF(user_pseudo_id IS NULL) AS missing_user_rows
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20201107'
GROUP BY 1,2 ORDER BY 1,3 DESC;
