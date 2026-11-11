import io
import pandas as pd
from src.common import ROOT
from src.metrics_service import query_metrics,user_segments,export_metrics,compare,validate_period


def test_U01_period_independent_sql(con):
    m=query_metrics(con,'2020-11-15','2020-11-28')
    s=con.execute("SELECT count(*),sum(has_purchase::INT) FROM fact_sessions WHERE session_date BETWEEN '2020-11-15' AND '2020-11-28'").fetchall()[0]
    assert (m['M02'],m['M06'])==s
    assert m['M10']==s[1]/s[0]


def test_U02_filter_all_supported_pages(app,con):
    next(x for x in app.selectbox if x.label=='设备').select('mobile').run()
    assert not app.exception
    start=next(x for x in app.date_input if x.label=='开始日期').value
    end=next(x for x in app.date_input if x.label=='结束日期').value
    expected=query_metrics(con,start,end,'mobile')
    assert next(x for x in app.metric if x.label=='有效会话数').value==f'{expected["M02"]:,.0f}'
    for page in ['转化诊断','用户分层','指标与数据运营']:
        app.radio[0].set_value(page).run()
        assert not app.exception
        assert next(x for x in app.selectbox if x.label=='设备').value=='mobile'


def test_U03_dictionary_cards(app):
    dictionary=pd.read_csv(ROOT/'docs/metric_dictionary.csv',encoding='utf-8')
    assert len(dictionary)==12
    assert dictionary[['numerator','denominator','time_field','version','source_table','sql_path']].notna().all().all()
    assert any('口径' in expander.label for expander in app.expander)
    for path in dictionary.sql_path: assert (ROOT/path).exists()


def test_U04_largest_funnel_loss(app,con):
    app.radio[0].set_value('转化诊断').run()
    assert not app.exception
    table=app.dataframe[0].value
    assert table['会话数'].is_monotonic_decreasing
    counts=table['会话数'].tolist()
    assert max(counts[i-1]-counts[i] for i in range(1,4))>=0


def test_U05_open_and_closed_are_distinct(con):
    m=query_metrics(con,'2020-11-01','2021-01-31')
    independent=con.execute('SELECT count(*) FILTER(WHERE has_purchase),count(purchase_ts),count(checkout_ts) FROM fact_sessions').fetchall()[0]
    assert m['M06']==independent[0] and m['funnel_purchase']==independent[1]
    assert m['M06']>=m['funnel_purchase']
    if independent[2]:assert m['M12']==independent[1]/independent[2]
    else:assert pd.isna(m['M12'])


def test_U06_no_data_and_zero_base(app,con):
    m=query_metrics(con,'1900-01-01','1900-01-02')
    assert m['M02']==0 and pd.isna(m['M10']) and pd.isna(m['M08'])
    assert compare({'a':2},{'a':0})['a']['relative'] is None
    next(x for x in app.date_input if x.label=='开始日期').set_value(pd.Timestamp('2020-11-28').date()).run()
    next(x for x in app.date_input if x.label=='结束日期').set_value(pd.Timestamp('2020-11-01').date()).run()
    assert not app.exception
    assert any('无数据' in w.value for w in app.warning)


def test_U07_segments_reconcile(con):
    for device in ['全部','desktop','mobile','未知']:
        users=user_segments(con,'2020-11-01','2020-11-28',device)
        m=query_metrics(con,'2020-11-01','2020-11-28',device)
        assert len(users)==m['M01'] and users.user_id.is_unique
        assert users.segment.isin(['窗内无有效交易','窗内单次有效交易','窗内多次有效交易']).all()


def test_U08_quality_visible(app,con):
    app.radio[0].set_value('指标与数据运营').run()
    assert not app.exception
    checks=con.execute('SELECT * FROM ops_quality_results').df()
    assert len(checks)==20 and not (checks.status=='fail').any()
    assert len(app.dataframe)>=4
    assert any('运行日志' in e.label for e in app.expander)


def test_U09_export_with_metadata(con,build):
    m=query_metrics(con,'2020-11-15','2020-11-28','mobile')
    df=pd.read_csv(io.BytesIO(export_metrics(m,dict(start='2020-11-15',end='2020-11-28',device='mobile'),build[1])))
    assert set(['filters','metric_version','run_id','source_kind','snapshot_start','snapshot_end','generated_at'])<=set(df.columns)
    assert df.loc[df.metric_id=='M02','value'].iloc[0]==m['M02']
    assert df.filters.str.contains('mobile').all()


def test_U10_repeatable_snapshot(build,con):
    import os
    from src.pipeline import run
    meta=run(ROOT/os.environ.get('ECOM_TEST_CONFIG','config/settings.demo.yml'))
    assert build[1]['model_rows']==meta['model_rows']
    assert meta['source_rows']==con.execute('SELECT count(*) FROM raw_events').fetchall()[0][0]
    assert validate_period(pd.Timestamp('2020-11-01').date(),pd.Timestamp('2020-11-28').date(),pd.Timestamp('2020-11-01').date(),pd.Timestamp('2020-11-28').date())
