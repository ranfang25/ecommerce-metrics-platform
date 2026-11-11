"""官方 BigQuery 快照下载；先预估扫描量，再按日保存，可恢复。"""
import argparse
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
from google.cloud import bigquery
from src.common import ROOT, now, write_json, read_json


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--project', required=True)
    p.add_argument('--start', default='2020-11-01')
    p.add_argument('--end', default='2020-11-07')
    p.add_argument('--output', default='data/official')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--gcloud', help='复用已有登录的gcloud可执行文件路径；未指定则使用ADC')
    p.add_argument('--maximum-gb', type=float, default=10)
    a = p.parse_args()
    start, end = date.fromisoformat(a.start), date.fromisoformat(a.end)
    if end < start:
        raise ValueError('结束日期早于开始日期')
    if a.gcloud:
        from src.auth import GcloudCredentials
        client = bigquery.Client(project=a.project,credentials=GcloudCredentials(a.gcloud))
    else:
        client = bigquery.Client(project=a.project)
    sql = (ROOT / 'sql/bigquery_extract/events.sql').read_text(encoding='utf-8')
    params = [bigquery.ScalarQueryParameter('start', 'STRING', start.strftime('%Y%m%d')),
              bigquery.ScalarQueryParameter('end', 'STRING', end.strftime('%Y%m%d'))]
    dry = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False, query_parameters=params))
    print(f'预估扫描 {dry.total_bytes_processed / 1e9:.3f} GB；限制 {a.maximum_gb} GB')
    if not a.execute:
        print('仅预估；确认后加 --execute 下载。')
        return
    if dry.total_bytes_processed > a.maximum_gb * 1e9:
        raise ValueError('预估扫描量超过本次限制')
    out = ROOT / a.output
    out.mkdir(parents=True, exist_ok=True)
    records, frames = [], []
    for i in range((end-start).days+1):
        day = start + timedelta(days=i)
        token = day.strftime('%Y%m%d')
        parameters = [bigquery.ScalarQueryParameter(k, 'STRING', token) for k in ['start', 'end']]
        file = out / f'events_{token}.parquet'
        checkpoint = out / f'events_{token}.meta.json'
        if file.exists() and checkpoint.exists():
            saved=read_json(checkpoint)
            if saved.get('sql')==sql and saved['bytes']==file.stat().st_size:
                frame=pd.read_parquet(file)
                if len(frame)==saved['rows']:
                    frames.append(frame);records.append(saved)
                    print(f'{day}: {len(frame)} 条（复用已完成分区）',flush=True)
                    continue
        job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=parameters, maximum_bytes_billed=int(a.maximum_gb*1e9)))
        frame = job.to_dataframe(create_bqstorage_client=False)
        frame.to_parquet(file, index=False)
        record={'file': file.name, 'rows': len(frame), 'bytes': file.stat().st_size, 'job_id': job.job_id, 'processed_bytes': job.total_bytes_processed,'sql':sql}
        records.append(record)
        write_json(checkpoint,record)
        frames.append(frame)
        print(f'{day}: {len(frame)} 条',flush=True)
    all_events = pd.concat(frames, ignore_index=True)
    all_events.to_parquet(out/'events.parquet', index=False)
    write_json(out/'manifest.json', {'source_kind':'official', 'source':'bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*',
        'start':a.start,'end':a.end,'exported_at':now(),'rows':len(all_events),'fields':list(all_events.columns),
        'sql':'sql/bigquery_extract/events.sql','files':records,'version':'1.0.0'})


if __name__ == '__main__':
    main()
