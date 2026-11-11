"""将Cloud Shell官方压缩包分批写成项目Parquet快照。"""
import argparse
import gzip
import json
import zipfile
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from src.common import ROOT,write_json

SCHEMA=pa.schema([(k,t) for k,t in [('event_date',pa.string()),('event_timestamp',pa.int64()),('event_name',pa.string()),
 ('user_pseudo_id',pa.string()),('ga_session_id',pa.int64()),('device',pa.string()),('first_source',pa.string()),
 ('transaction_id',pa.string()),('purchase_revenue_usd',pa.float64()),('currency',pa.string()),('items_json',pa.string())]])


def convert(archive_path,output):
    out=ROOT/output;out.mkdir(parents=True,exist_ok=True)
    count=0
    with zipfile.ZipFile(archive_path) as archive:
        manifest=json.loads(archive.read('manifest.json').decode('utf-8'))
        if manifest['source_kind']!='official':raise ValueError('必须提供官方导出清单')
        if set(manifest['fields'])!=set(SCHEMA.names):raise ValueError('字段不符合项目契约')
        with pq.ParquetWriter(out/'events.importing.parquet',SCHEMA,compression='snappy') as writer:
            for record in manifest['files']:
                part_count=0;batch=[]
                with archive.open(record['file']) as zipped,gzip.open(zipped,'rt',encoding='utf-8') as f:
                    for line in f:
                        batch.append(json.loads(line));part_count+=1
                        if len(batch)>=20000:
                            writer.write_table(pa.Table.from_pylist(batch,schema=SCHEMA));batch=[]
                    if batch:writer.write_table(pa.Table.from_pylist(batch,schema=SCHEMA))
                if part_count!=record['rows']:raise ValueError('导出清单与分区行数不一致')
                count+=part_count;print(f'{record["file"]}: {part_count} 行')
        if count!=manifest['rows']:raise ValueError('总行数与清单不一致')
        (out/'events.importing.parquet').replace(out/'events.parquet')
        write_json(out/'manifest.json',manifest)
    print(f'官方快照导入完成：{count} 行，{manifest["start"]}—{manifest["end"]}')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive');p.add_argument('--output',default='data/official');a=p.parse_args();convert(a.archive,a.output)
