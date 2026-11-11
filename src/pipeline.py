"""候选数据库建模、校验、原子发布，失败保留上一成功版本。"""
import argparse
import json
import uuid
from pathlib import Path
import duckdb
import pandas as pd
import yaml
from src.common import ROOT, VERSION, now, write_json, read_json
from src.quality import REQUIRED,run_quality


def run(config_path,simulate_failure=False):
    config = yaml.safe_load(Path(config_path).read_text(encoding='utf-8'))
    config['expected_start'],config['expected_end'] = str(config['expected_start']),str(config['expected_end'])
    output = ROOT/config['output']
    output.mkdir(parents=True,exist_ok=True)
    pointer = output/'published.json'
    old_text = pointer.read_text(encoding='utf-8') if pointer.exists() else None
    previous = json.loads(old_text) if old_text else None
    run_id = now().replace(':','').replace('.','')+'_'+uuid.uuid4().hex[:8]
    database = output/f'{run_id}.duckdb'
    meta = dict(run_id=run_id,version=VERSION,started_at=now(),status='running',database=database.name)
    con = None
    try:
        manifest = read_json(ROOT/config['manifest'])
        meta.update(source_kind=manifest['source_kind'],source=manifest['source'],source_rows=manifest['rows'],
                    start=config['expected_start'],end=config['expected_end'],snapshot_exported_at=manifest['exported_at'],
                    data_revision=manifest.get('extraction_revision','initial'))
        con = duckdb.connect(str(database))
        con.execute('CREATE TABLE raw_events AS SELECT * FROM read_parquet(?)',[str(ROOT/config['snapshot'])])
        fields = set(con.execute('DESCRIBE raw_events').df()['column_name'])
        if not REQUIRED<=fields:
            raise ValueError(f'Q02 必需字段缺失：{sorted(REQUIRED-fields)}')
        for script in ['sql/staging/events.sql','sql/facts/sessions.sql','sql/facts/orders.sql','sql/marts/aggregates.sql']:
            con.execute((ROOT/script).read_text(encoding='utf-8'))
        config['_pointer_unchanged'] = (pointer.read_text(encoding='utf-8') if pointer.exists() else None)==old_text
        results,counts = run_quality(con,manifest,config,meta,previous)
        meta['model_rows'] = counts
        checks = pd.DataFrame(results)
        con.register('quality_frame',checks)
        con.execute('CREATE TABLE ops_quality_results AS SELECT ? AS run_id,* FROM quality_frame',[run_id])
        write_json(output/f'{run_id}.quality.json',results)
        if any(r['status']=='fail' for r in results):
            raise ValueError('质量阻断：'+','.join(r['check_id'] for r in results if r['status']=='fail'))
        if simulate_failure:
            raise RuntimeError('受控刷新失败：建模完成后、发布前中断')
        meta.update(status='success',finished_at=now(),warnings=sum(r['status']=='warning' for r in results))
        run_frame = pd.DataFrame([meta]).drop(columns=['model_rows'])
        con.register('run_frame',run_frame)
        con.execute('CREATE TABLE ops_pipeline_runs AS SELECT * FROM run_frame')
        con.close()
        con = None
        # 只有完整数据库关闭且全部阻断检查通过后，才切换可用版本
        write_json(output/'published.next.json',meta)
        (output/'published.next.json').replace(pointer)
        write_json(output/'latest_status.json',meta)
        with (output/'runs.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(meta,ensure_ascii=False)+'\n')
        print(f'发布成功 {run_id}；警告 {meta["warnings"]}；{meta["source_kind"]}')
        return meta
    except Exception as error:
        meta.update(status='failed',finished_at=now(),error=str(error))
        write_json(output/'latest_status.json',meta)
        with (output/'runs.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(meta,ensure_ascii=False)+'\n')
        raise
    finally:
        if con is not None:
            con.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config',default='config/settings.local.yml')
    p.add_argument('--simulate-failure',action='store_true')
    a = p.parse_args()
    run(ROOT/a.config,a.simulate_failure)


if __name__=='__main__':
    main()
