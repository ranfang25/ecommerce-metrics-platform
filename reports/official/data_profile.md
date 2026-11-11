# 数据探查

来源：官方脱敏历史样本。运行 2026-11-11T042024754230+0000_d282ec41，处理时间 2026-11-11T04:20:34.467496+00:00。

范围 2020-11-01 至 2021-01-31；原始事件 4295584，有效用户 270154，会话 360129，交易 4888。原始事件未按相似字段删数。会话两端可能截断。

## 事件分布
```csv
event_name,rows
page_view,1350428
user_engagement,1058721
scroll,493072
view_item,386068
session_start,354970
first_visit,257462
view_promotion,190104
add_to_cart,58543
begin_checkout,38757
select_item,31007
view_search_results,26172
add_shipping_info,19722
add_payment_info,13899
select_promotion,9450
purchase,5692
click,1446
view_item_list,71
```

## 标识与金额缺失
```csv
missing_user,excluded_session_events,missing_transaction,missing_purchase_usd
0,0,450,0
```

## 购买事件原币种（购买USD字段单独汇总）
```csv
currency,rows
USD,5692
```

## 按月的事件覆盖
```csv
month,view_events,cart_events,checkout_events,purchase_events
2020-11,148639,7674,9546,2054
2020-12,150458,35347,18177,2434
2021-01,86971,15522,11034,1204
```

加购等阶段的可用性随历史月份变化；不将记录缺口直接解释为业务流失。正式两期比较固定为末尾两个完整14天周期。

## 商品与订单金额
```csv
valid_orders,orders_without_items,item_order_amount_differences
4888,0,931
```

商品金额与订单金额差异单独披露，不据此制造相等，也不通过商品连接重复汇总订单金额。

每日覆盖见date_coverage.csv，模型行数见run_manifest.json。日期使用源event_date，时间戳只用于排序。首次获客来源不代表当前会话渠道。
