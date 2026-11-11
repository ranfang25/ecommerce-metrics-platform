"""由发布库生成数据探查、三项分析、复算明细和性能报告。"""
import argparse
import io
import platform
import time
from pathlib import Path
import duckdb
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from src.common import ROOT,now,write_json
from src.metrics_service import published,query_metrics,user_segments,export_metrics


def generate(output):
    db,meta=published(ROOT/output)
    report=ROOT/'reports'/('official' if meta['source_kind']=='official' else 'controlled')
    report.mkdir(parents=True,exist_ok=True)
    charts=report/'charts';charts.mkdir(exist_ok=True)
    start,end=pd.Timestamp(meta['start']),pd.Timestamp(meta['end'])
    total=(end-start).days+1
    period=min(14,total//2)
    if period<1: raise ValueError('至少需要两个完整日期进行比较')
    p1_end=end;p1_start=end-pd.Timedelta(days=period-1)
    p0_end=p1_start-pd.Timedelta(days=1);p0_start=p0_end-pd.Timedelta(days=period-1)
    con=duckdb.connect(str(db),read_only=True)
    m0=query_metrics(con,p0_start.date(),p0_end.date());m1=query_metrics(con,p1_start.date(),p1_end.date())
    all_m=query_metrics(con,start.date(),end.date())
    events=con.execute('SELECT event_name,count(*) AS rows FROM fact_events GROUP BY 1 ORDER BY 2 DESC').df()
    dates=con.execute('SELECT event_date,count(*) AS rows FROM fact_events GROUP BY 1 ORDER BY 1').df()
    issues=con.execute('''SELECT count(*) FILTER(WHERE user_id IS NULL) AS missing_user,
      count(*) FILTER(WHERE session_id IS NULL OR user_id IS NULL) AS excluded_session_events,
      count(*) FILTER(WHERE event_name='purchase' AND transaction_id IS NULL) AS missing_transaction,
      count(*) FILTER(WHERE event_name='purchase' AND revenue_usd IS NULL) AS missing_purchase_usd FROM fact_events''').df()
    currency=con.execute("SELECT coalesce(currency,'未知') AS currency,count(*) AS rows FROM fact_events WHERE event_name='purchase' GROUP BY 1").df()
    monthly_stages=con.execute("""SELECT strftime(event_date,'%Y-%m') AS month,
      count(*) FILTER(WHERE event_name='view_item') AS view_events,
      count(*) FILTER(WHERE event_name='add_to_cart') AS cart_events,
      count(*) FILTER(WHERE event_name='begin_checkout') AS checkout_events,
      count(*) FILTER(WHERE event_name='purchase') AS purchase_events
      FROM fact_events GROUP BY 1 ORDER BY 1""").df()
    item_reconciliation=con.execute('''WITH items AS (SELECT transaction_id,sum(item_revenue_usd) AS item_usd FROM fact_order_items GROUP BY 1)
      SELECT count(*) AS valid_orders,count(*) FILTER(WHERE i.transaction_id IS NULL) AS orders_without_items,
      count(*) FILTER(WHERE item_usd IS NOT NULL AND abs(item_usd-o.revenue_usd)>0.005) AS item_order_amount_differences
      FROM fact_orders o LEFT JOIN items i USING(transaction_id)''').df()
    quality=con.execute('SELECT * FROM ops_quality_results ORDER BY check_id').df()
    def write(name,text): (report/name).write_text(text,encoding='utf-8')
    def table(df): return df.to_csv(index=False)
    note='官方脱敏历史样本' if meta['source_kind']=='official' else '受控测试数据；下列数值仅验证分析程序，不是实际业务发现'
    write('data_profile.md',f'''# 数据探查

来源：{note}。运行 {meta['run_id']}，处理时间 {meta['finished_at']}。

范围 {meta['start']} 至 {meta['end']}；原始事件 {meta['source_rows']}，有效用户 {all_m['M01']:.0f}，会话 {all_m['M02']:.0f}，交易 {all_m['M07']:.0f}。原始事件未按相似字段删数。会话两端可能截断。

## 事件分布
```csv
{table(events)}```

## 标识与金额缺失
```csv
{table(issues)}```

## 购买事件原币种（购买USD字段单独汇总）
```csv
{table(currency)}```

## 按月的事件覆盖
```csv
{table(monthly_stages)}```

加购等阶段的可用性随历史月份变化；不将记录缺口直接解释为业务流失。正式两期比较固定为末尾两个完整14天周期。

## 商品与订单金额
```csv
{table(item_reconciliation)}```

商品金额与订单金额差异单独披露，不据此制造相等，也不通过商品连接重复汇总订单金额。

每日覆盖见date_coverage.csv，模型行数见run_manifest.json。日期使用源event_date，时间戳只用于排序。首次获客来源不代表当前会话渠道。
''')
    monthly_stages.to_csv(report/'monthly_stage_coverage.csv',index=False,encoding='utf-8')
    item_reconciliation.to_csv(report/'item_order_reconciliation.csv',index=False,encoding='utf-8')
    dates.to_csv(report/'date_coverage.csv',index=False,encoding='utf-8')
    write_json(report/'run_manifest.json',meta)
    quality.to_csv(report/'quality_results.csv',index=False,encoding='utf-8')
    write('quality_report.md',f'# 质量执行结果\n\n{note}。运行 {meta["run_id"]}。20项已执行；通过 {(quality.status=="pass").sum()}，警告 {(quality.status=="warning").sum()}，阻断失败 {(quality.status=="fail").sum()}。警告不通过删数消除。详细阈值、观测、级别及处理见quality_results.csv；故障闭环见fault_cases.json。\n\n```csv\n'+table(quality)+'```\n')
    # 金额分解严格使用金额完整订单数，不用总有效订单数
    n0,n1=m0['amount_orders'],m1['amount_orders']
    a0,a1=m0['M09'],m1['M09']
    amount_valid=all(pd.notna(x) for x in [a0,a1,m0['M08'],m1['M08']])
    quantity=(n1-n0)*(a0+a1)/2 if amount_valid else np.nan
    price=(a1-a0)*(n0+n1)/2 if amount_valid else np.nan
    delta=m1['M08']-m0['M08'] if amount_valid else np.nan
    decomposition=pd.DataFrame({'component':['Order count','Average order value','Recorded USD change'],'USD':[quantity,price,delta]})
    decomposition.to_csv(report/'amount_decomposition.csv',index=False,encoding='utf-8')
    fig,ax=plt.subplots(figsize=(8,4));ax.bar(decomposition.component,decomposition.USD,color=['#2878b5','#ef9b32','#1c9e87']);ax.axhline(0,color='#666',linewidth=.7);ax.set_ylabel('Recorded purchase USD');ax.set_title('Controlled test' if meta['source_kind']!='official' else 'Recorded purchase decomposition');fig.tight_layout();fig.savefig(charts/'amount.png',dpi=150);plt.close(fig)
    # 设备结构/组内贡献采用对称分解，空设备保留；缺任一期组则不强行解释组内变化
    devices=con.execute('SELECT DISTINCT device FROM fact_sessions ORDER BY 1').df().device
    device_rows=[]
    for d in devices:
        x=query_metrics(con,p0_start.date(),p0_end.date(),d);y=query_metrics(con,p1_start.date(),p1_end.date(),d)
        w0=x['M02']/m0['M02'] if m0['M02'] else np.nan;w1=y['M02']/m1['M02'] if m1['M02'] else np.nan
        r0,r1=x['M10'],y['M10']
        device_rows.append(dict(device=d,sessions0=x['M02'],sessions1=y['M02'],share0=w0,share1=w1,rate0=r0,rate1=r1,
          mix_contribution=(w1-w0)*(r0+r1)/2,within_contribution=(r1-r0)*(w0+w1)/2,small_sample=min(x['M02'],y['M02'])<100))
    dev=pd.DataFrame(device_rows)
    dev.to_csv(report/'device_decomposition.csv',index=False,encoding='utf-8')
    fig,ax=plt.subplots(figsize=(8,4));pos=np.arange(len(dev));ax.bar(pos-.18,dev.rate0*100,.36,label='Previous');ax.bar(pos+.18,dev.rate1*100,.36,label='Current');ax.set_xticks(pos,dev.device.replace('未知','Unknown'));ax.set_ylabel('Session purchase conversion %');ax.legend();fig.tight_layout();fig.savefig(charts/'device.png',dpi=150);plt.close(fig)
    counts=[m1[k] for k in ['funnel_view','funnel_cart','funnel_checkout','funnel_purchase']]
    funnel=pd.DataFrame({'stage':['View','Cart','Checkout','Purchase'],'sessions':counts})
    funnel['loss_from_previous']=[np.nan]+[counts[i-1]-counts[i] for i in range(1,4)]
    funnel.to_csv(report/'funnel.csv',index=False,encoding='utf-8')
    fig,ax=plt.subplots(figsize=(8,4));ax.barh(funnel.stage,funnel.sessions,color='#2878b5');ax.invert_yaxis();ax.set_xlabel('Strictly ordered sessions');fig.tight_layout();fig.savefig(charts/'funnel.png',dpi=150);plt.close(fig)
    users=user_segments(con,p1_start.date(),p1_end.date())
    segments=users.groupby('segment').agg(users=('user_id','size'),orders=('orders','sum'),recorded_usd=('revenue',lambda x:x.sum(min_count=1)),purchase_event_users=('purchase_events',lambda x:(x>0).sum()),unmatched_purchase_users=('unmatched_purchase','sum')).reset_index()
    segments.to_csv(report/'segments.csv',index=False,encoding='utf-8')
    group_coverage=not dev[['rate0','rate1']].isna().any().any()
    mix=dev.mix_contribution.sum() if group_coverage else np.nan
    within=dev.within_contribution.sum() if group_coverage else np.nan
    conversion_delta=m1['M10']-m0['M10']
    loss=funnel.loc[funnel.loss_from_previous.idxmax()]
    write('business_analysis.md',f'''# 三项可复算分析

**{note}**。运行 {meta['run_id']}。完整等长周期：{p0_start.date()}—{p0_end.date()} 对比 {p1_start.date()}—{p1_end.date()}（各{period}天）。采用末尾两个相邻完整周期，未按差异挑选极端日期；仍需注意节假日与样本边界。

## 1. 已记录金额变化

两期有金额交易 {n0:.0f} → {n1:.0f}；客单价 ${a0:.2f} → ${a1:.2f}；已记录金额 ${m0['M08']:.2f} → ${m1['M08']:.2f}，差额 ${delta:.2f}。订单量贡献 ${quantity:.2f}，客单价贡献 ${price:.2f}；对称分解加回误差 {quantity+price-delta:.8f} USD。

有效交易金额覆盖率 {m0['amount_coverage']:.2%} → {m1['amount_coverage']:.2%}；购买事件交易ID覆盖率 {m0['transaction_id_coverage']:.2%} → {m1['transaction_id_coverage']:.2%}。分解只用金额完整且未冲突的有效交易，不等于所有购买事件。证据：sql/marts/metrics.sql的M08、M09与amount_orders；amount_decomposition.csv；charts/amount.png。建议先检查缺失ID、冲突隔离与缺失金额是否系统性集中，再判断交易量与单价的运营含义。没有成本、退款验证或实验，不能称利润提升。

![金额分解](charts/amount.png)

## 2. 设备构成与会话转化

会话 {m0['M02']:.0f} → {m1['M02']:.0f}；购买会话转化率 {m0['M10']:.2%} → {m1['M10']:.2%}，变化 {conversion_delta*100:+.3f} 个百分点。设备结构贡献 {mix*100:+.3f} 个百分点，组内转化贡献 {within*100:+.3f} 个百分点；分组覆盖完整={group_coverage}。有任一期空组时不强行计算其组内转化。

证据：sql/marts/metrics.sql，以device参数逐组复算；device_decomposition.csv，保留未知与小样本标记；charts/device.png。建议先核验各设备购买埋点与流量结构，再对主要流量设备设计结账体验实验；观察差异不等于设备导致转化变化。

![设备转化](charts/device.png)

## 3. 路径损失与窗内用户

当前严格漏斗会话：{counts}。最大绝对损失出现在进入 {loss['stage']}，损失 {loss['loss_from_previous']:.0f} 个会话。顺序不确定 {m1['uncertain_sessions']:.0f}/{m1['M02']:.0f}；有purchase事件但未完成闭合路径 {m1['unmatched_purchase_sessions']:.0f}/{m1['M06']:.0f}。

当前窗内用户分组如下，合计{len(users)}人。“无有效交易”中仍可能有购买事件，不能称为确定未购买人群：
```csv
{segments.to_csv(index=False)}```

证据：sql/facts/sessions.sql（每步严格晚于前一步），sql/marts/metrics.sql（闭合阶段），funnel.csv与segments.csv；charts/funnel.png。用户分组按当前窗口重算且互斥；不称生命周期首购。这里的损失是样本记录中的路径缺口，不能直接解释为真实用户流失或体验问题；应先排查加购埋点稀疏、路径缺失和并列时间戳，再设计实验并记录样本、分流与核心转化率。

![严格漏斗](charts/funnel.png)

## 复算方法与边界

python -m src.reporting --output {output}。页面、导出、报告调用同一服务；reconciliation.csv附当前全区间12指标及独立SQL核验。报告生成时间 {now()}。脱敏数据有限一致性；真实干预、企业收益、用户试用改善均未验证。
''')
    # 独立SQL逐指标对账，包括严格漏斗和缺失金额分母
    independent=con.execute('''SELECT (SELECT count(DISTINCT user_id) FROM fact_events) AS M01,
     count(*) AS M02,sum(has_view::INT) AS M03,sum(has_cart::INT) AS M04,sum(has_checkout::INT) AS M05,sum(has_purchase::INT) AS M06,
     (SELECT count(*) FROM fact_orders) AS M07,(SELECT sum(revenue_usd) FROM fact_orders) AS M08,(SELECT avg(revenue_usd) FROM fact_orders) AS M09,
     avg(has_purchase::INT) AS M10,count(cart_ts)*1.0/nullif(count(view_ts),0) AS M11,count(purchase_ts)*1.0/nullif(count(checkout_ts),0) AS M12 FROM fact_sessions''').df().iloc[0].to_dict()
    exported=pd.read_csv(io.BytesIO(export_metrics(all_m,{'start':meta['start'],'end':meta['end'],'device':'全部','first_source':'全部'},meta))).set_index('metric_id').value
    reconcile=[]
    for key,sql_value in independent.items():
        v=all_m[key]
        ok=(pd.isna(v) and pd.isna(sql_value)) or abs(v-sql_value)<1e-8
        exp_ok=(pd.isna(v) and pd.isna(exported[key])) or abs(v-exported[key])<1e-8
        reconcile.append(dict(metric_id=key,service=v,independent_sql=sql_value,export_value=exported[key],passed=ok and exp_ok))
    pd.DataFrame(reconcile).to_csv(report/'reconciliation.csv',index=False,encoding='utf-8')
    if not all(x['passed'] for x in reconcile): raise AssertionError('12项指标复算失败')
    timings=[]
    for name,args in [('all',()),('desktop',('desktop',)),('mobile',('mobile',))]:
        t=time.perf_counter();query_metrics(con,start.date(),end.date(),*args);cold=time.perf_counter()-t
        warm=[]
        for i in range(20):
            t=time.perf_counter();query_metrics(con,start.date(),end.date(),*args);warm.append(time.perf_counter()-t)
        timings.append(dict(task=name,first_call_seconds=cold,warm_n=20,warm_p95_seconds=float(np.percentile(warm,95)),warm_seconds=warm))
    write_json(report/'performance.json',dict(hardware=platform.platform(),processor=platform.processor(),source_kind=meta['source_kind'],source_rows=meta['source_rows'],tasks=timings))
    write('performance.md',f'# 服务性能实测\n\n环境 {platform.platform()} / {platform.processor()}；数据 {meta["source_rows"]} 事件，来源 {meta["source_kind"]}。各查询预热20次。\n\n```json\n'+__import__('json').dumps(timings,ensure_ascii=False,indent=2)+'\n```\n\n此处仅测本地数据服务，不是浏览器页面p95，也不是人工取数效率提升。浏览器实际交互单独记录于browser_performance.json（如已运行）。\n')
    con.close()
    if meta['source_kind']=='official':
        for name in ['business_analysis.md','data_profile.md','quality_report.md','performance.md','reconciliation.csv']:
            text=(report/name).read_text(encoding='utf-8')
            if name=='business_analysis.md':text=text.replace('](charts/','](official/charts/')
            (ROOT/'reports'/name).write_text(text,encoding='utf-8')
    print(f'报告已生成：{report}')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='data/official_build');a=p.parse_args();generate(a.output)
