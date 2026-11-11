# 数据探查

来源：受控测试数据；下列数值仅验证分析程序，不是实际业务发现。运行 2026-11-11T032744977344+0000_93ca9c24，处理时间 2026-11-11T03:27:45.646720+00:00。

范围 2020-11-01 至 2020-11-28；原始事件 5607，有效用户 453，会话 3054，交易 386。原始事件未按相似字段删数。会话两端可能截断。

## 事件分布
```csv
event_name,rows
view_item,3055
add_to_cart,1417
begin_checkout,749
purchase,386
```

## 标识与金额缺失
```csv
missing_user,excluded_session_events,missing_transaction,missing_purchase_usd
1,2,0,9
```

## 购买事件原币种（购买USD字段单独汇总）
```csv
currency,rows
USD,384
未知,2
```

每日覆盖见date_coverage.csv，模型行数见run_manifest.json。日期使用源event_date，时间戳只用于排序。首次获客来源不代表当前会话渠道。
