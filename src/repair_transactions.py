"""保留首次导出，按官方购买记录修正历史交易ID提取；非购买事件不重取。"""
import argparse
from pathlib import Path
import shutil
import duckdb
import pandas as pd
from google.cloud import bigquery
from src.auth import GcloudCredentials
from src.common import ROOT,read_json,write_json,now


def repair(project,gcloud,folder):
    out=ROOT/folder
    manifest=read_json(out/'manifest.json')
    sql=(ROOT/'sql/bigquery_extract/events.sql').read_text(encoding='utf-8').rstrip()+" AND event_name='purchase'"
    parameters=[bigquery.ScalarQueryParameter('start','STRING',manifest['start'].replace('-','')),bigquery.ScalarQueryParameter('end','STRING',manifest['end'].replace('-',''))]
    c=bigquery.Client(project=project,credentials=GcloudCredentials(gcloud))
    job=c.query(sql,job_config=bigquery.QueryJobConfig(query_parameters=parameters,maximum_bytes_billed=10_000_000_000))
    purchases=job.to_dataframe(create_bqstorage_client=False)
    backup=out/'initial_extract_v1';backup.mkdir(exist_ok=True)
    # 先保留可回溯的旧版与清单，不永久删除原始文件
    if not (backup/'manifest.json').exists():shutil.copy2(out/'manifest.json',backup/'manifest.json')
    if not (backup/'events.parquet').exists():shutil.copy2(out/'events.parquet',backup/'events.parquet')
    records=[];frames=[];old_missing=0;new_missing=0
    for record in manifest['files']:
        path=out/record['file']
        old=pd.read_parquet(path)
        old_purchase=old[old.event_name=='purchase']
        date=record['file'][7:15]
        correct=purchases[purchases.event_date==date]
        if len(old_purchase)!=len(correct):raise ValueError(f'{date}购买事件行数变化，停止自动修正')
        with duckdb.connect() as con:
            con.register('before_rows',old_purchase)
            con.register('after_rows',correct)
            differences=con.execute('''SELECT count(*) FROM (
              (SELECT * EXCLUDE(transaction_id) FROM before_rows EXCEPT ALL SELECT * EXCLUDE(transaction_id) FROM after_rows)
              UNION ALL (SELECT * EXCLUDE(transaction_id) FROM after_rows EXCEPT ALL SELECT * EXCLUDE(transaction_id) FROM before_rows))''').fetchall()[0][0]
        if differences:raise ValueError(f'{date}除交易ID外有字段变化，停止自动修正')
        fixed=pd.concat([old[old.event_name!='purchase'],correct],ignore_index=True)
        old_missing+=int((old_purchase.transaction_id.isna()|old_purchase.transaction_id.isin(['','(not set)','<Other>'])).sum())
        new_missing+=int((correct.transaction_id.isna()|correct.transaction_id.isin(['','(not set)','<Other>'])).sum())
        if not (backup/path.name).exists():shutil.copy2(path,backup/path.name)
        fixed.to_parquet(path,index=False)
        records.append({**record,'bytes':path.stat().st_size,'transaction_repair_job':job.job_id,'initial_sql':record.get('initial_sql',record.get('sql')),
            'sql':(ROOT/'sql/bigquery_extract/events.sql').read_text(encoding='utf-8')})
        frames.append(fixed)
        write_json(out/path.name.replace('.parquet','.meta.json'),records[-1])
    all_events=pd.concat(frames,ignore_index=True)
    all_events.to_parquet(out/'events.parquet',index=False)
    write_json(out/'manifest.json',{**manifest,'files':records,'extraction_revision':'transaction_params_valid_values_v3','repaired_at':now(),
       'purchase_repair_job':job.job_id,'initial_extract':'initial_extract_v1','sql':'sql/bigquery_extract/events.sql'})
    report={'source':'官方GA4购买事件','job_id':job.job_id,'sql':sql,'snapshot':folder,'purchase_events':len(purchases),
       'missing_transaction_before':old_missing,'missing_transaction_after':new_missing,'non_transaction_fields_equal':True,
       'event_rows_before':manifest['rows'],'event_rows_after':len(all_events),'backup':str(backup.relative_to(ROOT)),'repaired_at':now()}
    report_path=ROOT/'reports'/('transaction_repair_7day.json' if manifest['end']=='2020-11-07' else 'transaction_repair_full.json')
    if report_path.exists():shutil.copy2(report_path,report_path.with_stem(report_path.stem+'_'+now().replace(':','').replace('.','')))
    write_json(report_path,report)
    print(report)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--gcloud',required=True);p.add_argument('--folder',default='data/official');a=p.parse_args();repair(a.project,a.gcloud,a.folder)
