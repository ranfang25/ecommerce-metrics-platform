"""四页产品：只读取已发布版本。"""
import os
from datetime import timedelta
import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st
import yaml
from src.common import ROOT,read_json
from src.metrics_service import published,query_metrics,user_segments,export_metrics,compare,validate_period,funnel_groups


@st.cache_data(show_spinner=False)
def page_metrics(database,start,end,device='全部',source='全部'):
    # 数据库文件名带运行版本，发布切换后自然使用新的缓存键
    with duckdb.connect(database,read_only=True) as connection:
        return query_metrics(connection,start,end,device,source)


@st.cache_data(show_spinner=False)
def page_segments(database,start,end,device='全部',source='全部'):
    with duckdb.connect(database,read_only=True) as connection:
        return user_segments(connection,start,end,device,source)


@st.cache_data(show_spinner=False)
def page_funnel_groups(database,start,end,device='全部',source='全部'):
    with duckdb.connect(database,read_only=True) as connection:
        return funnel_groups(connection,start,end,device,source)


st.set_page_config(page_title='电商指标工作台',page_icon='📊',layout='wide')
st.markdown('''<style>.stApp{background:#f6f8fc}h1,h2,h3{color:#172b4d}[data-testid="stMetric"]{background:white;border:1px solid #e1e8f0;border-radius:12px;padding:18px}</style>''',unsafe_allow_html=True)
st.title('电商指标工作台')
st.caption('经营分析 / 转化诊断 / 指标治理 · v1.0.0')
output = ROOT/os.environ.get('ECOM_OUTPUT','data/official_build')
if not (output/'published.json').exists():
    st.info('尚无已发布数据。请先运行数据接入与处理；受控样本演示需显式设置 ECOM_OUTPUT=data/demo_build。')
    if (output/'latest_status.json').exists():
        st.error(read_json(output/'latest_status.json').get('error','处理未完成'))
    st.stop()
db,meta = published(output)
if meta['source_kind']!='official':
    st.warning('受控测试数据 · 以下数值仅用于技术验收，不代表 Google 商店的真实表现。')
else:
    st.info('官方 GA4 脱敏历史样本 · 观察差异不能证明因果。')
success_time=pd.Timestamp(meta['finished_at']).tz_convert('Asia/Shanghai').strftime('%Y-%m-%d %H:%M:%S 北京时间')
st.caption(f'样本 {meta["start"]} 至 {meta["end"]} ｜ 上次成功 {success_time} ｜ 运行 {meta["run_id"]}')
latest = read_json(output/'latest_status.json')
if latest['status']=='failed':
    st.error('刷新失败，当前保留上一成功版本：'+latest['error'])
con = duckdb.connect(str(db),read_only=True)
dictionary = pd.read_csv(ROOT/'docs/metric_dictionary.csv',encoding='utf-8')
start_all,end_all = pd.Timestamp(meta['start']).date(),pd.Timestamp(meta['end']).date()
with st.sidebar:
    st.header('分析范围')
    page = st.radio('功能页面',['经营总览','转化诊断','用户分层','指标与数据运营'])
    default_start = max(start_all,end_all-timedelta(days=13))
    start = st.date_input('开始日期',default_start,min_value=start_all,max_value=end_all)
    end = st.date_input('结束日期',end_all,min_value=start_all,max_value=end_all)
    device = st.selectbox('设备',['全部']+con.execute('SELECT DISTINCT device FROM fact_events ORDER BY 1').df().device.tolist())
    source = st.selectbox('首次获客来源',['全部']+con.execute('SELECT DISTINCT first_source FROM fact_events ORDER BY 1').df().first_source.tolist())
    st.caption('用户按事件日期；会话按最早可见日期；交易按购买日期。首次获客来源不是当前会话渠道。')
if not validate_period(start,end,start_all,end_all):
    st.warning('无数据：请选择样本范围内、起止有序的完整日期区间。')
    con.close()
    st.stop()
with st.spinner('正在读取已验证指标…'):
    m = page_metrics(str(db),start,end,device,source)
if m['M01']==0 and m['M02']==0 and m['M07']==0:
    st.info('当前筛选无数据，请调整日期、设备或首次获客来源。金额与比率空值不补零。')
    con.close()
    st.stop()
filters = dict(start=str(start),end=str(end),device=device,first_source=source)
st.download_button('导出当前指标 CSV',export_metrics(m,filters,meta),'metrics.csv','text/csv')


def value(v,kind='number'):
    if pd.isna(v): return '暂无'
    if kind=='rate': return f'{v:.2%}'
    if kind=='money': return f'${v:,.2f}'
    return f'{v:,.0f}'


def evidence():
    with st.expander('查看计算 SQL 与当前复算结果'):
        st.code((ROOT/'sql/marts/metrics.sql').read_text(encoding='utf-8'),language='sql')
        st.json(filters)
        st.dataframe(pd.DataFrame([m]),hide_index=True)


if page=='经营总览':
    st.header('经营总览')
    p_end = start-timedelta(days=1)
    p_start = p_end-timedelta(days=(end-start).days)
    previous = page_metrics(str(db),p_start,p_end,device,source) if p_start>=start_all else None
    diffs = compare(m,previous) if previous else None
    if previous:
        st.caption(f'完整等长基期：{p_start} 至 {p_end}；当前：{start} 至 {end}。节假日与周末可能影响可比性。')
    else:
        st.info('样本内没有足够的前置完整等长周期，暂不显示周期增长率。')
    keys = [('M01','观察用户数','number'),('M02','有效会话数','number'),('M07','有效交易数','number'),('M08','已记录购买金额 USD','money'),('M09','金额完整订单客单价','money'),('M10','会话购买转化率','rate')]
    cols = st.columns(3)
    for i,(key,label,kind) in enumerate(keys):
        d = diffs[key] if diffs else None
        delta = f'{d["relative"]:+.2%}' if d and d['relative'] is not None else None
        cols[i%3].metric(label,value(m[key],kind),delta)
    st.caption('有效交易金额覆盖率 '+value(m['amount_coverage'],'rate')+'；购买事件交易ID覆盖率 '+value(m['transaction_id_coverage'],'rate')+'；缺失金额不补零。')
    if diffs:
        st.dataframe(pd.DataFrame(diffs).T.loc[[k[0] for k in keys]],width='stretch')
    daily = con.execute('''SELECT date,sum(sessions) AS sessions,sum(purchasing_sessions) AS purchasing_sessions FROM mart_daily_metrics
      WHERE date BETWEEN ? AND ? AND (?='全部' OR device=?) AND (?='全部' OR first_source=?) GROUP BY 1 ORDER BY 1''',[start,end,device,device,source,source]).df()
    st.plotly_chart(px.line(daily,x='date',y=['sessions','purchasing_sessions'],title='会话与购买会话趋势'),width='stretch')
    with st.expander('点击查看指标定义与口径',expanded=False):
        key = st.selectbox('选择指标',dictionary.metric_id.tolist())
        st.dataframe(dictionary[dictionary.metric_id==key].T,width='stretch')
    evidence()
elif page=='转化诊断':
    st.header('转化诊断')
    counts = [m[k] for k in ['funnel_view','funnel_cart','funnel_checkout','funnel_purchase']]
    f = pd.DataFrame({'阶段':['商品浏览','有序加购','有序结账','有序购买'],'会话数':counts})
    f['较前阶段转化率'] = [None]+[counts[i]/counts[i-1] if counts[i-1] else None for i in range(1,4)]
    st.plotly_chart(px.funnel(f,x='会话数',y='阶段'),width='stretch')
    st.dataframe(f,hide_index=True)
    st.caption(f'顺序不确定会话 {m["uncertain_sessions"]:.0f} / {m["M02"]:.0f}；购买但未完成闭合路径 {m["unmatched_purchase_sessions"]:.0f} / {m["M06"]:.0f}。同时间戳不推断先后。')
    st.warning('这是样本记录中的路径覆盖，未匹配不等于真实用户流失。特别是加购埋点稀疏时，应先核查数据，再提出体验实验。')
    if m['M02']<100: st.warning('小样本：少于100个会话，差异不稳定。')
    comparison = []
    p_end = start-timedelta(days=1)
    p_start = p_end-timedelta(days=(end-start).days)
    for d in ([device] if device!='全部' else con.execute('SELECT DISTINCT device FROM fact_sessions ORDER BY 1').df().device):
        current = page_metrics(str(db),start,end,d,source)
        prior = page_metrics(str(db),p_start,p_end,d,source) if p_start>=start_all else None
        comparison.append(dict(设备=d,会话数=current['M02'],会话转化率=current['M10'],基期会话数=prior['M02'] if prior else None,基期转化率=prior['M10'] if prior else None,小样本=current['M02']<100))
    st.dataframe(pd.DataFrame(comparison),hide_index=True)
    st.subheader('窗内用户分组路径')
    st.dataframe(page_funnel_groups(str(db),start,end,device,source),hide_index=True)
    st.caption('分组使用所选窗口内行为，属于结果分组描述，不是购买前预测或因果解释。')
    st.info('已观察事实：上表给出损失环节及设备差异。待验证原因：先核查埋点完整性与结账体验，再设计真实实验。')
    evidence()
elif page=='用户分层':
    st.header('用户分层')
    users = page_segments(str(db),start,end,device,source)
    summary = users.groupby('segment').agg(用户数=('user_id','size'),记录金额_USD=('revenue',lambda x:x.sum(min_count=1)),有效交易数=('orders','sum'),购买事件用户数=('purchase_events',lambda x:(x>0).sum()),未匹配有效交易的购买用户=('unmatched_purchase','sum')).reset_index()
    summary['占比'] = summary['用户数']/len(users)
    summary['购买事件用户率'] = summary['购买事件用户数']/summary['用户数']
    st.caption(f'观察窗口 {start} 至 {end}，截至日期 {end}；用户总数 {len(users)}。窗内次数不代表生命周期购买次数。')
    st.plotly_chart(px.bar(summary,x='segment',y='用户数',color='segment'),width='stretch')
    st.dataframe(summary,hide_index=True)
    st.caption('按窗内有效交易数互斥分组。“无有效交易”可能含缺失或冲突交易ID的购买者，不代表未发生购买。购买事件用户率与有效交易分组分开展示。多设备用户可能重叠，不能直接相加。')
    evidence()
else:
    st.header('指标与数据运营')
    text = st.text_input('搜索指标名称、口径或编号')
    selected = dictionary[dictionary.astype(str).apply(lambda row:row.str.contains(text,regex=False).any(),axis=1)] if text else dictionary
    st.dataframe(selected,hide_index=True)
    st.subheader('本次发布质量结果')
    quality = con.execute('SELECT * FROM ops_quality_results ORDER BY check_id').df()
    st.dataframe(quality,hide_index=True)
    for label,sql in [('缺失会话样例','SELECT * FROM fact_events WHERE session_id IS NULL OR user_id IS NULL LIMIT 20'),('重复交易','SELECT * FROM order_audit WHERE event_rows>1 LIMIT 20'),('冲突隔离','SELECT * FROM quarantined_orders LIMIT 20')]:
        with st.expander(label): st.dataframe(con.execute(sql).df(),hide_index=True)
    with st.expander('运行日志与版本'):
        st.json(meta)
        st.code((output/'runs.jsonl').read_text(encoding='utf-8'),language='json')
    for name in ['issue_log.md','change_log.md']:
        with st.expander(name): st.markdown((ROOT/'docs'/name).read_text(encoding='utf-8'))
con.close()
