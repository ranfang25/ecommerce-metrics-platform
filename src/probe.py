"""核查历史样本实际参数字段，避免用当前文档替代实际结构。"""
import argparse
from google.cloud import bigquery
from src.auth import GcloudCredentials
from src.common import ROOT,write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--gcloud',required=True);a=p.parse_args()
    c=bigquery.Client(project=a.project,credentials=GcloudCredentials(a.gcloud))
    sql="""SELECT TO_JSON_STRING(event_params) AS params_json,TO_JSON_STRING(ecommerce) AS ecommerce_json
    FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
    WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20201107' AND event_name='purchase' LIMIT 8"""
    j=c.query(sql,job_config=bigquery.QueryJobConfig(maximum_bytes_billed=10_000_000_000))
    rows=[dict(r) for r in j.result()]
    write_json(ROOT/'reports/official_7day_probe.json',dict(sql=sql,job_id=j.job_id,rows=rows))
    print(__import__('json').dumps(rows,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
