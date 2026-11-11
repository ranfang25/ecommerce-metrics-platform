# 模型与关联

```mermaid
flowchart LR
 A[官方导出 raw_events] --> B[fact_events 一行一事件]
 B --> C[fact_sessions 用户×会话]
 B --> D[order_audit 交易冲突检查]
 D --> E[fact_orders 一行一有效交易]
 D --> Q[quarantined_orders 冲突隔离]
 E --> F[fact_order_items 交易×商品行]
 C --> G[mart_daily_metrics / mart_funnel]
 B --> H[mart_user_segments 全窗口用户]
 E --> H
 G --> I[统一指标服务]
 C --> I
 E --> I
 I --> J[四页产品 / 导出 / 报告]
```

主键：事件event_row_id仅表示本次导入位置；会话(user_id,session_id)；交易transaction_id；商品(transaction_id,item_line)。事件关联会话为多对一；交易关联会话为多对一；商品关联交易为多对一。金额始终在订单粒度计算，不能先连接商品后相加。

mart日表支持趋势；周期用户与比率必须由原粒度重算。ops_quality_results记录本次20项结果；每个发布数据库含本次ops_pipeline_runs；跨运行日志在runs.jsonl。发布指针只在全部阻断规则通过后切换。
