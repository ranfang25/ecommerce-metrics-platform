"""多维度、交叉筛选的12指标SQL与CSV复算。"""
import argparse
import io
from pathlib import Path
import duckdb
import pandas as pd
from src.common import ROOT
from src.metrics_service import published,query_metrics,export_metrics


def reconcile(output):
    db,meta=published(ROOT/output)
    report=ROOT/'reports'/('official' if meta['source_kind']=='official' else 'controlled')
    report.mkdir(parents=True,exist_ok=True)
    con=duckdb.connect(str(db),read_only=True)
    sql=(ROOT/'sql/marts/reconcile.sql').read_text(encoding='utf-8')
    devices=con.execute('SELECT DISTINCT device FROM fact_sessions ORDER BY 1').df().device.tolist()
    sources=con.execute('SELECT first_source FROM fact_sessions GROUP BY 1 ORDER BY count(*) DESC LIMIT 3').df().first_source.tolist()
    groups=[('全部','全部')]+[(d,'全部') for d in devices]+[('全部',s) for s in sources]+[('mobile',sources[0])]
    periods=[(meta['start'],meta['end']),(str((pd.Timestamp(meta['end'])-pd.Timedelta(days=13)).date()),meta['end'])]
    results=[]
    for start,end in periods:
        for device,source in groups:
            m=query_metrics(con,start,end,device,source)
            direct=con.execute(sql,[start,end,device,source]).df().iloc[0].to_dict()
            exported=pd.read_csv(io.BytesIO(export_metrics(m,dict(start=start,end=end,device=device,source=source),meta))).set_index('metric_id').value
            for key,value in direct.items():
                ok=((pd.isna(value) and pd.isna(m[key])) or abs(value-m[key])<1e-8)
                ex=((pd.isna(value) and pd.isna(exported[key])) or abs(value-exported[key])<1e-8)
                results.append(dict(start=start,end=end,device=device,first_source=source,metric_id=key,
                    service=m[key],independent_sql=value,export_value=exported[key],passed=ok and ex,run_id=meta['run_id']))
    con.close()
    pd.DataFrame(results).to_csv(report/'filtered_reconciliation.csv',index=False,encoding='utf-8')
    assert all(r['passed'] for r in results),'筛选对账失败'
    print(f'{len(results)} 项筛选对账全部通过')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='data/official_build');a=p.parse_args();reconcile(a.output)
