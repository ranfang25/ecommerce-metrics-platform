# 数据契约 v1.0

官方来源：bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*。官方标注区间2020-11-01至2021-01-31；实际范围、行数和覆盖以导出清单为准。当前官方快照待接入。

|字段|类型|约束|
|---|---|---|
|event_date|YYYYMMDD字符串|源站点日期；不从UTC时间戳推导日期|
|event_timestamp|int64|UTC微秒；仅用于事件先后|
|event_name|字符串|必须存在|
|user_pseudo_id|可空字符串|空值保留原始层，排除用户指标|
|ga_session_id|可空int64|与用户构成会话键；缺失排除会话指标|
|device / first_source|可空字符串|空值显示未知；来源仅首次获客|
|transaction_id|可空字符串|空、(not set)、<Other>为无效；冲突隔离|
|purchase_revenue_usd|可空数值|仅USD购买金额，转为DECIMAL(18,2)|
|currency|可空字符串|原币种仅供披露；不与USD指标混加|
|items_json|JSON数组字符串|商品数量与item_revenue_in_usd独立展开|

会话日期取全快照内最早可见event_date；数据两端会话可能截断。设备与来源取最早事件属性；同时间戳属性并列时按导出行号选取，仅用于属性归属，不用于漏斗顺序。

有效交易要求ID可识别且用户/会话/日期/USD金额完全一致；重复一致记录合并，任一冲突整笔隔离（包括金额空值与非空值不一致）。最早购买行商品作为代表，重复事件商品差异不作真实商品销售结论。缺失用户或会话的可识别交易保留金额指标，但归属覆盖单列披露。

M06为含purchase事件的会话数，包括缺失交易ID或之后被交易冲突隔离的事件，不等于合格交易数。严格漏斗使用purchase事件；每一步时间严格大于前一步；相等不推定顺序，存在并列阶段单列覆盖。

文件登记以文件名、字节数、行数、日期、字段和BigQuery job_id溯源；快照完整重建避免重复追加。数据目录使用项目相对路径。

历史字段实测：ecommerce.transaction_id在样本中为空，event_params.transaction_id的int_value有值；提取时优先非空ecommerce字段，否则读取参数的string_value/int_value。来源探查与修正记录位于reports/official_7day_probe.json及transaction_repair_*.json。初版提取被保留，修正前后除交易ID外所有购买字段按多重集合对齐。
