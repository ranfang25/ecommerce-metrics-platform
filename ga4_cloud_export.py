"""在Google Cloud Shell执行的独立导出脚本，输出官方样本压缩包。"""
import argparse
from datetime import date,timedelta,datetime,timezone
import gzip
import json
from pathlib import Path
import zipfile
from google.cloud import bigquery

SQL="""SELECT event_date,event_timestamp,event_name,user_pseudo_id,
(SELECT value.int_value FROM UNNEST(event_params) WHERE key='ga_session_id' LIMIT 1) AS ga_session_id,
device.category AS device,traffic_source.source AS first_source,
COALESCE(CASE WHEN ecommerce.transaction_id NOT IN ('','(not set)','<Other>') THEN ecommerce.transaction_id END,(SELECT COALESCE(CASE WHEN value.string_value NOT IN ('','(not set)','<Other>') THEN value.string_value END,CAST(value.int_value AS STRING)) FROM UNNEST(event_params) WHERE key='transaction_id' LIMIT 1)) AS transaction_id,ecommerce.purchase_revenue_in_usd AS purchase_revenue_usd,
(SELECT value.string_value FROM UNNEST(event_params) WHERE key='currency' LIMIT 1) AS currency,
TO_JSON_STRING(ARRAY(SELECT AS STRUCT item_id,item_name,quantity,item_revenue_in_usd FROM UNNEST(items))) AS items_json
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN @start AND @end"""


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--project',required=True)
    p.add_argument('--start',default='2020-11-01')
    p.add_argument('--end',default='2021-01-31')
    p.add_argument('--execute',action='store_true')
    p.add_argument('--maximum-gb',type=float,default=100)
    a=p.parse_args()
    start,end=date.fromisoformat(a.start),date.fromisoformat(a.end)
    if end<start:raise ValueError('结束日期必须不早于开始日期')
    client=bigquery.Client(project=a.project)
    def params(x,y):return [bigquery.ScalarQueryParameter('start','STRING',x.strftime('%Y%m%d')),bigquery.ScalarQueryParameter('end','STRING',y.strftime('%Y%m%d'))]
    dry=client.query(SQL,job_config=bigquery.QueryJobConfig(dry_run=True,use_query_cache=False,query_parameters=params(start,end)))
    print(f'预估扫描 {dry.total_bytes_processed/1e9:.3f} GB，限制 {a.maximum_gb} GB',flush=True)
    if not a.execute:
        print('仅预估。确认后同一命令加 --execute 下载。');return
    if dry.total_bytes_processed>a.maximum_gb*1e9:raise ValueError('超过扫描限制，停止')
    out=Path('ga4_official_export');out.mkdir(exist_ok=True)
    files=[];fields=[]
    for i in range((end-start).days+1):
        day=start+timedelta(days=i);filename=f'events_{day:%Y%m%d}.jsonl.gz';path=out/filename
        record_path=out/f'{day:%Y%m%d}.meta.json'
        if path.exists() and record_path.exists():
            record=json.loads(record_path.read_text(encoding='utf-8'))
            if record.get('complete') and record.get('sql')==SQL:
                files.append(record);fields=record['fields'];print(f'{day} 使用已完成分区 {record["rows"]} 行',flush=True);continue
        job=client.query(SQL,job_config=bigquery.QueryJobConfig(query_parameters=params(day,day),maximum_bytes_billed=int(a.maximum_gb*1e9)))
        result=job.result(page_size=10000);fields=[s.name for s in result.schema];count=0
        with gzip.open(path,'wt',encoding='utf-8') as f:
            for row in result:
                f.write(json.dumps(dict(row),ensure_ascii=False)+'\n');count+=1
        record=dict(file=filename,rows=count,bytes=path.stat().st_size,job_id=job.job_id,processed_bytes=job.total_bytes_processed,
           fields=fields,complete=True,sql=SQL)
        record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        files.append(record);print(f'{day} {count} 行',flush=True)
    manifest=dict(source_kind='official',source='bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*',start=a.start,end=a.end,
        exported_at=datetime.now(timezone.utc).isoformat(),rows=sum(x['rows'] for x in files),fields=fields,files=files,version='1.0.0',sql=SQL)
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile('ga4_official_export.zip','w',compression=zipfile.ZIP_STORED) as archive:
        archive.write(out/'manifest.json','manifest.json')
        for record in files:archive.write(out/record['file'],record['file'])
    print('完成。执行 cloudshell download ga4_official_export.zip 下载真实数据包。',flush=True)


if __name__=='__main__':main()
