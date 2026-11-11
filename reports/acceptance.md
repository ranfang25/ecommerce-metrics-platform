# 技术验收记录

状态：功能技术验收完成，用户验证待完成。实际外部试用人数为0，不报告人工任务成功率。

|编号|验收内容|结果|证据|
|---|---|---|---|
|U01|完整周期与独立SQL一致|通过|test_U01_period_independent_sql；reconciliation.csv|
|U02|设备筛选同步四页|通过|test_U02_filter_all_supported_pages|
|U03|12项口径完整可查|通过|test_U03_dictionary_cards；metric_dictionary.csv|
|U04|漏斗样本量及最大损失|通过|test_U04_largest_funnel_loss；funnel.csv|
|U05|开放购买与闭合漏斗分开|通过|test_U05_open_and_closed_are_distinct|
|U06|无数据与零基期处理|通过|test_U06_no_data_and_zero_base|
|U07|用户分层互斥完整|通过|test_U07_segments_reconcile；无有效交易不等于未购买专项测试|
|U08|质量问题与运行状态可见|通过|test_U08_quality_visible；fault_cases.json|
|U09|导出元数据与数字一致|通过|test_U09_export_with_metadata；实际浏览器导出12项复算|
|U10|同快照重复执行一致|通过|test_U10_repeatable_snapshot；全量故障工具核对会话及交易主键集合|

15项自动测试全部通过，含10项基本业务用例及5项人工可复算语义/故障测试。独立虚拟环境安装已完成，pip check通过；同机隔离环境完成官方全量处理与测试，未声称在另一台电脑或macOS复跑。

浏览器80项页面切换测量已完成，但四页p95为3.249至3.993秒，均超过3秒；见performance.md。四页真实截图与CSV下载在demo/。实际浏览器导出保留其原发布版本标识，与对应版本12项指标一致。
