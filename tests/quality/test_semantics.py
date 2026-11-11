import json
from pathlib import Path
import duckdb
import pandas as pd
import pytest
import yaml
from src.common import ROOT,write_json,read_json
from src.pipeline import run
from src.metrics_service import published,query_metrics


@pytest.fixture
def oracle():
    import uuid
    tmp_path=ROOT/'tests/artifacts'/uuid.uuid4().hex[:8]
    tmp_path.mkdir(parents=True,exist_ok=True)
    # 人工可复算样本：跨午夜会话、缺金额、重复一致、冲突和并列时间
    rows=[]
    def event(user,sid,date,name,t,tx=None,amount=None,items='[]'):
        rows.append(dict(event_date=date,event_timestamp=t,event_name=name,user_pseudo_id=user,ga_session_id=sid,
          device='desktop',first_source='test',transaction_id=tx,purchase_revenue_usd=amount,currency='USD',items_json=items))
    for name,t in [('view_item',1),('add_to_cart',2),('begin_checkout',3)]:event('u1',1,'20201101',name,t)
    items=json.dumps([{'item_id':'a','quantity':1,'item_revenue_in_usd':40},{'item_id':'b','quantity':2,'item_revenue_in_usd':60}])
    event('u1',1,'20201102','purchase',4,'T1',100,items)
    event('u1',1,'20201102','purchase',4,'T1',100,items)
    event('u2',1,'20201102','purchase',5,'T2',None)
    event('u3',3,'20201102','purchase',6,'T3',10)
    event('u3',3,'20201102','purchase',7,'T3',20)
    for name in ['view_item','add_to_cart','begin_checkout','purchase']:event('tie',4,'20201102',name,8,'T4' if name=='purchase' else None,50 if name=='purchase' else None)
    event(None,None,'20201102','page_view',9)
    event('u5',5,'20201102','purchase',10,None,None)
    frame=pd.DataFrame(rows)
    frame.to_parquet(tmp_path/'events.parquet',index=False)
    write_json(tmp_path/'manifest.json',dict(source_kind='controlled',source='人工复算样本',rows=len(frame),start='2020-11-01',end='2020-11-02',version='1.0.0',exported_at='2026-11-11'))
    config=dict(snapshot=str(tmp_path/'events.parquet'),manifest=str(tmp_path/'manifest.json'),output=str(tmp_path/'build'),expected_start='2020-11-01',expected_end='2020-11-02')
    path=tmp_path/'config.yml';path.write_text(yaml.safe_dump(config),encoding='utf-8')
    meta=run(path)
    db,_=published(tmp_path/'build')
    return path,db,meta


def test_manual_oracle_12_metrics(oracle):
    _,db,_=oracle
    with duckdb.connect(str(db),read_only=True) as con:
        m=query_metrics(con,'2020-11-01','2020-11-02')
        expected={'M01':5,'M02':5,'M03':2,'M04':2,'M05':2,'M06':5,'M07':3,'M08':150,'M09':75,'M10':1,'M11':.5,'M12':1}
        for key,value in expected.items(): assert m[key]==value,(key,m[key],value)
        assert m['amount_coverage']==pytest.approx(2/3)
        assert con.execute("SELECT cart_ts,order_uncertain FROM fact_sessions WHERE user_id='tie'").fetchall()[0]==(None,True)
        assert con.execute('SELECT count(*) FROM quarantined_orders').fetchall()[0][0]==2
        assert con.execute("SELECT count(*) FROM fact_order_items WHERE transaction_id='T1'").fetchall()[0][0]==2


def test_midnight_and_session_key(oracle):
    _,db,_=oracle
    with duckdb.connect(str(db),read_only=True) as con:
        m=query_metrics(con,'2020-11-01','2020-11-01')
        assert m['M02']==1 and m['M06']==1 and m['M07']==0
        assert con.execute('SELECT count(*) FROM fact_sessions WHERE session_id=1').fetchall()[0][0]==2


def test_purchase_without_valid_order_is_not_called_nonbuyer(oracle):
    from src.metrics_service import user_segments
    _,db,_=oracle
    with duckdb.connect(str(db),read_only=True) as con:
        users=user_segments(con,'2020-11-01','2020-11-02')
        user=users[users.user_id=='u5'].iloc[0]
        assert user.segment=='窗内无有效交易' and user.purchase_events==1 and bool(user.unmatched_purchase)


def test_failure_preserves_success(oracle):
    path,db,meta=oracle
    output=db.parent
    before=read_json(output/'published.json')
    with pytest.raises(RuntimeError):run(path,simulate_failure=True)
    assert read_json(output/'published.json')==before
    assert read_json(output/'latest_status.json')['status']=='failed'
    with duckdb.connect(str(db),read_only=True) as con:assert con.execute('SELECT count(*) FROM fact_orders').fetchall()[0][0]==3


def test_missing_date_blocks_publication(oracle):
    path,db,_=oracle
    cfg=yaml.safe_load(path.read_text(encoding='utf-8'))
    frame=pd.read_parquet(cfg['snapshot']);frame=frame[frame.event_date=='20201102'];frame.to_parquet(cfg['snapshot'],index=False)
    manifest=read_json(cfg['manifest']);manifest['rows']=len(frame);write_json(cfg['manifest'],manifest)
    before=read_json(db.parent/'published.json')
    with pytest.raises(ValueError,match='Q01'):run(path)
    assert read_json(db.parent/'published.json')==before
