"""幂等复跑、三项故障注入和恢复记录；仅修改专用测试副本。"""
import argparse
import json
import uuid
from pathlib import Path
import duckdb
import pandas as pd
import yaml
from src.common import ROOT,read_json,write_json,now
from src.pipeline import run
from src.metrics_service import query_metrics,published


def validate(config_path):
    config_path=Path(config_path)
    config=yaml.safe_load(config_path.read_text(encoding='utf-8'))
    source_manifest=read_json(ROOT/config['manifest'])
    frame=pd.read_parquet(ROOT/config['snapshot'])
    tag=uuid.uuid4().hex[:8]
    workspace=ROOT/'data/fault_runs'/tag
    workspace.mkdir(parents=True,exist_ok=True)
    snapshot=workspace/'events.parquet'
    manifest=workspace/'manifest.json'
    local_config=workspace/'settings.yml'
    c={**config,'snapshot':snapshot.relative_to(ROOT).as_posix(),'manifest':manifest.relative_to(ROOT).as_posix(),
       'output':(workspace/'build').relative_to(ROOT).as_posix()}
    local_config.write_text(yaml.safe_dump(c,allow_unicode=True),encoding='utf-8')
    def save(data):
        data.to_parquet(snapshot,index=False)
        write_json(manifest,{**source_manifest,'rows':len(data),'source_kind':'controlled','source':'故障验收专用副本；原来源 '+source_manifest['source']})
    def pointer(): return read_json(workspace/'build/published.json')
    def values():
        db,meta=published(workspace/'build')
        with duckdb.connect(str(db),read_only=True) as con:
            return query_metrics(con,str(c['expected_start']),str(c['expected_end'])),con.execute('SELECT user_id,session_id FROM fact_sessions ORDER BY 1,2').fetchall(),con.execute('SELECT transaction_id FROM fact_orders ORDER BY 1').fetchall()
    save(frame)
    first=run(local_config)
    baseline,session_keys,order_keys=values()
    second=run(local_config)
    rerun,s2,o2=values()
    def equal(a,b):
        return all((pd.isna(a[k]) and pd.isna(b[k])) or a[k]==b[k] for k in a)
    idempotent=equal(baseline,rerun) and session_keys==s2 and order_keys==o2
    if not idempotent: raise AssertionError('重复运行不一致')
    cases=[]
    # 案例一：同一交易增加冲突金额，整笔隔离后恢复
    purchase=frame[(frame.event_name=='purchase') & frame.transaction_id.notna() & frame.purchase_revenue_usd.notna()].iloc[0].copy()
    target=str(purchase.transaction_id)
    original=float(purchase.purchase_revenue_usd)
    purchase['purchase_revenue_usd']=original+7
    save(pd.concat([frame,pd.DataFrame([purchase])],ignore_index=True))
    conflict_run=run(local_config)
    db,_=published(workspace/'build')
    with duckdb.connect(str(db),read_only=True) as con:
        audit=con.execute('SELECT * FROM order_audit WHERE transaction_id=?',[target]).df().to_dict('records')
        isolated=con.execute('SELECT count(*) FROM quarantined_orders WHERE transaction_id=?',[target]).fetchall()[0][0]
        valid=con.execute('SELECT count(*) FROM fact_orders WHERE transaction_id=?',[target]).fetchall()[0][0]
    if isolated<2 or valid!=0: raise AssertionError('冲突未隔离')
    save(frame);fixed=run(local_config)
    fixed_values,_,_=values()
    if not equal(baseline,fixed_values): raise AssertionError('冲突恢复不一致')
    cases.append(dict(case='F01',phenomenon='交易ID相同但金额冲突',hit='Q07',target=target,before_amount=original,injected_amount=original+7,
        location='order_audit → quarantined_orders',audit=audit,isolated_rows=isolated,published_valid_rows=valid,
        decision='冲突交易整笔隔离；不随意取第一条',failure_run=conflict_run['run_id'],repaired_run=fixed['run_id'],verified='恢复所有核心指标',status='closed'))
    # 案例二：移除中间日期副本，分区覆盖检查阻断
    missing_day=sorted(frame.event_date.astype(str).unique())[len(frame.event_date.astype(str).unique())//2]
    save(frame[frame.event_date.astype(str)!=missing_day])
    old=pointer()
    try:
        run(local_config)
        raise AssertionError('缺失日期未阻断')
    except ValueError as error:
        text=str(error)
        if 'Q01' not in text: raise
    unchanged=pointer()==old
    save(frame);fixed=run(local_config)
    if not unchanged or not equal(baseline,values()[0]): raise AssertionError('断档恢复不一致')
    cases.append(dict(case='F02',phenomenon='日期分区断档',missing_day=missing_day,hit='Q01/Q18',error=text,
        decision='阻断发布并保留上次成功版本；补回测试副本',previous_run=old['run_id'],pointer_preserved=unchanged,repaired_run=fixed['run_id'],verified='补跑后所有指标一致',status='closed'))
    # 案例三：发布前模拟任务异常，旧库仍可查询
    old=pointer()
    try:
        run(local_config,simulate_failure=True)
        raise AssertionError('预期异常未出现')
    except RuntimeError as error:
        text=str(error)
    unchanged=pointer()==old and equal(baseline,values()[0])
    fixed=run(local_config)
    if not unchanged or not equal(baseline,values()[0]): raise AssertionError('刷新失败保留不正确')
    cases.append(dict(case='F03',phenomenon='刷新失败',hit='Q19',error=text,decision='不切换发布指针，保留上次成功库',
        previous_run=old['run_id'],pointer_preserved=unchanged,repaired_run=fixed['run_id'],verified='旧库可查且恢复后所有指标一致',status='closed'))
    report=ROOT/'reports'/('official' if source_manifest['source_kind']=='official' else 'controlled')
    report.mkdir(parents=True,exist_ok=True)
    write_json(report/'fault_cases.json',dict(executed_at=now(),workspace=str(workspace.relative_to(ROOT)),
       original_source_kind=source_manifest['source_kind'],idempotency={'first':first['run_id'],'second':second['run_id'],'metrics_equal':idempotent,'session_and_order_keys_equal':True},cases=cases))
    print(f'幂等及3项故障恢复通过，记录 {report}')
    return cases


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--config',default='config/settings.demo.yml')
    a=p.parse_args()
    validate(ROOT/a.config)
