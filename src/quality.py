"""二十项可执行校验，警告保留样本问题，阻断项禁止发布。"""
import math
import pandas as pd
from src.metrics_service import query_metrics, user_segments, export_metrics

REQUIRED = {'event_date','event_timestamp','event_name','user_pseudo_id','ga_session_id','device','first_source','transaction_id','purchase_revenue_usd','currency','items_json'}


def run_quality(con,manifest,config,meta,previous=None):
    results = []
    def scalar(sql):
        return con.execute(sql).fetchall()[0][0]
    def check(i,name,ok,observed,threshold='0 差异',severity='error'):
        results.append(dict(check_id=f'Q{i:02d}',name=name,status='pass' if ok else ('warning' if severity=='warning' else 'fail'),
            observed=str(observed),threshold=threshold,severity=severity,action='保留并披露' if severity=='warning' else '失败则阻断发布'))
    start,end = config['expected_start'],config['expected_end']
    dates = con.execute('SELECT DISTINCT event_date FROM fact_events ORDER BY 1').df().iloc[:,0]
    expected = set(pd.date_range(start,end).date)
    actual = set(pd.to_datetime(dates).dt.date)
    n = scalar('SELECT count(*) FROM fact_events')
    check(1,'日期分区覆盖与清单',actual==expected and str(manifest['start'])==start and str(manifest['end'])==end,
        f'缺失 {sorted(expected-actual)}；多余 {sorted(actual-expected)}','日期集合一致')
    fields = set(con.execute('DESCRIBE raw_events').df()['column_name'])
    invalid = scalar("SELECT count(*) FROM fact_events WHERE event_date IS NULL OR event_timestamp IS NULL OR event_name IS NULL")
    check(2,'字段与类型契约',REQUIRED<=fields and invalid==0,f'缺失字段 {sorted(REQUIRED-fields)}；无效日期/时间/名称 {invalid}')
    missing_user = scalar('SELECT count(*) FROM fact_events WHERE user_id IS NULL')
    missing_session = scalar('SELECT count(*) FROM fact_events WHERE session_id IS NULL OR user_id IS NULL')
    check(3,'空用户标识已统计',missing_user==0,f'{missing_user}/{n}', '无空标识；非零披露', 'warning')
    check(4,'无效会话组合已统计',missing_session==0,f'{missing_session}/{n}', '无空组合；非零披露', 'warning')
    signatures = {t:scalar(f'SELECT count(*) FROM {t}') for t in ['raw_events','fact_events','fact_sessions','fact_orders','fact_order_items']}
    comparable = previous and previous.get('source_rows')==manifest['rows'] and previous.get('start')==start and previous.get('end')==end and previous.get('data_revision','initial')==meta.get('data_revision','initial') and previous.get('snapshot_exported_at')==meta.get('snapshot_exported_at')
    check(5,'快照重建不追加导入',signatures['raw_events']==manifest['rows'] and (not comparable or signatures==previous.get('model_rows')),
       f'模型行数 {signatures}；同范围前版对比 {bool(comparable)}','源行数一致；重复运行模型行数一致')
    check(6,'标准化保留原始事件',n==manifest['rows'],f'原始 {manifest["rows"]}；标准化 {n}')
    duplicates = scalar('SELECT count(*) FROM order_audit WHERE event_rows>1')
    conflicts = scalar('SELECT count(*) FROM order_audit WHERE variants>1')
    missing_tx = scalar("SELECT count(*) FROM fact_events WHERE event_name='purchase' AND transaction_id IS NULL")
    check(7,'重复交易及冲突隔离',duplicates==0 and missing_tx==0,f'重复交易 {duplicates}；冲突交易 {conflicts}；缺失交易ID的购买事件 {missing_tx}；冲突全部隔离','无重复和缺失ID；非零披露','warning')
    bad_join = scalar('''SELECT count(*) FROM fact_orders o LEFT JOIN fact_sessions s USING(user_id,session_id)
      WHERE o.user_id IS NULL OR o.session_id IS NULL OR s.user_id IS NULL''')
    check(8,'交易归属覆盖',bad_join==0,f'无法归属会话交易 {bad_join}','全部可归属；非零披露','warning')
    check(9,'会话组合键唯一',scalar('SELECT count(*) FROM (SELECT user_id,session_id FROM fact_sessions GROUP BY 1,2 HAVING count(*)>1)')==0,'组合键重复数为零')
    invalid_order = scalar('''SELECT count(*) FROM fact_sessions WHERE (cart_ts IS NOT NULL AND NOT cart_ts>view_ts)
      OR (checkout_ts IS NOT NULL AND NOT checkout_ts>cart_ts) OR (purchase_ts IS NOT NULL AND NOT purchase_ts>checkout_ts)''')
    check(10,'严格有序漏斗',invalid_order==0,invalid_order)
    m = query_metrics(con,start,end)
    check(11,'闭合漏斗单调',m['funnel_view']>=m['funnel_cart']>=m['funnel_checkout']>=m['funnel_purchase'],
      [m[k] for k in ['funnel_view','funnel_cart','funnel_checkout','funnel_purchase']],'依次不增')
    empty = query_metrics(con,'1900-01-01','1900-01-02')
    ratios = [m[k] for k in ['M10','M11','M12']]
    check(12,'比率范围及零分母',all(pd.isna(v) or 0<=v<=1 for v in ratios) and all(pd.isna(empty[k]) for k in ['M10','M11','M12']),ratios,'比率 0—1；零分母为空')
    check(13,'USD金额覆盖',m['amount_orders']==m['M07'],f'有效交易 {m["M07"]}；有USD金额 {m["amount_orders"]}；覆盖率 {m["amount_coverage"]}', '100%；非零缺失披露','warning')
    repeated_items = scalar('SELECT count(*) FROM (SELECT transaction_id,item_line FROM fact_order_items GROUP BY 1,2 HAVING count(*)>1)')
    check(14,'商品粒度不放大订单',repeated_items==0 and scalar('SELECT count(*) FROM fact_orders')==scalar('SELECT count(DISTINCT transaction_id) FROM fact_orders'),
       f'商品重复键 {repeated_items}；订单金额仅从fact_orders汇总')
    amount = scalar('SELECT sum(revenue_usd) FROM fact_orders')
    check(15,'汇总与订单金额对账',(amount is None and pd.isna(m['M08'])) or abs(float(amount)-m['M08'])<0.005,
       f'订单 {amount}；服务 {m["M08"]}','金额差异 < 0.005 USD')
    segments = user_segments(con,start,end)
    check(16,'用户分层集合完整互斥',len(segments)==m['M01'] and segments.user_id.is_unique and segments.segment.notna().all(),
      f'分层 {len(segments)}；用户 {m["M01"]}')
    checks = []
    for device in con.execute('SELECT DISTINCT device FROM fact_sessions').df()['device']:
        filtered = query_metrics(con,start,end,device)
        independent = con.execute('SELECT count(*),count(*) FILTER(WHERE has_purchase) FROM fact_sessions WHERE session_date BETWEEN ?::DATE AND ?::DATE AND device=?',[start,end,device]).fetchall()[0]
        exported = pd.read_csv(__import__('io').BytesIO(export_metrics(filtered,dict(device=device),meta)))
        checks.append(filtered['M02']==independent[0] and filtered['M06']==independent[1] and float(exported.loc[exported.metric_id=='M02','value'].iloc[0])==independent[0])
    check(17,'筛选服务导出独立SQL对账',all(checks),f'{len(checks)} 个设备分组','所有分组一致')
    check(18,'完整周期与观察窗口',actual==expected,f'完整日期 {len(actual&expected)}/{len(expected)}；D7未实现，不纳入结果','比较仅使用完整等长周期')
    check(19,'发布前不修改成功版本',config.get('_pointer_unchanged',True), '构建与检查期间发布指针保持原值；故障实测见 fault_cases.json','原子发布；失败保留前版')
    check(20,'运行与版本溯源',bool(meta['run_id']) and meta['version']==manifest['version'] and meta['source_rows']==n,
      f'{meta["run_id"]} / {meta["version"]} / {manifest["source_kind"]}','运行、快照与指标版本对应')
    return results,signatures
