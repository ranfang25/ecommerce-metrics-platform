"""依据实际产物填写验收、发布清单和README成果，不预填试用结论。"""
import io
import json
import platform
import xml.etree.ElementTree as ET
import duckdb
import numpy as np
import pandas as pd
from src.common import ROOT,read_json,write_json,now
from src.metrics_service import published,query_metrics


def write(path,text):
    path=ROOT/path;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')


def main():
    report=ROOT/'reports/official'
    db,meta=published(ROOT/'data/official_build')
    manifest=read_json(ROOT/'data/official/manifest.json')
    write_json(ROOT/'data/manifest.json',{**manifest,'local_snapshot':'data/official/events.parquet',
        'published_database':str(db.relative_to(ROOT)),'published_run':meta['run_id'],'note':'官方样本；初版快照保留在initial_extract_v1，修复证据见reports/transaction_repair_full.json'})
    with duckdb.connect(str(db),read_only=True) as con:
        m=query_metrics(con,meta['start'],meta['end'])
        checks=con.execute('SELECT * FROM ops_quality_results').df()
    xml=ET.parse(report/'pytest.xml').getroot()
    testcases=xml.findall('.//testcase')
    assert len(testcases)==15 and all(t.find('failure') is None and t.find('error') is None for t in testcases)
    fault=read_json(report/'fault_cases.json')
    assert len(fault['cases'])==3 and all(c['status']=='closed' for c in fault['cases'])
    filtered=pd.read_csv(report/'filtered_reconciliation.csv',encoding='utf-8')
    assert len(filtered)==192 and filtered.passed.all()
    browser=read_json(report/'browser_performance.json')
    browser_df=pd.DataFrame(browser['samples'])
    summaries=[]
    for page,group in browser_df.groupby('page'):
        assert len(group)==20
        p95=float(np.percentile(group.seconds,95))
        summaries.append(dict(page=page,n=20,p50_seconds=float(group.seconds.median()),p95_seconds=p95,target_seconds=3,meets_target=p95<=3))
    summary=pd.DataFrame(summaries)
    summary.to_csv(report/'browser_performance_summary.csv',index=False,encoding='utf-8')
    performance=(report/'performance.md').read_text(encoding='utf-8').split('\n## 浏览器页面测量')[0]
    performance+='\n## 浏览器页面测量\n\n实际浏览器逐页切换，每页预热20次，固定2021-01-18至2021-01-31、全部设备与来源。计时从点击侧栏标签到对应页面标题出现且Streamlit前端notRunning，包含自动化往返开销，无法等同纯渲染耗时。浏览器真正冷启动未独立计时；缓存优化前一次诊断页切换为4.099秒，不能据此给出改进百分比。\n\n```csv\n'+summary.to_csv(index=False)+'```\n\n四页在此测量方式下均未达到p95不高于3秒目标，列为性能迭代项。原始80条测量见browser_performance.json。\n'
    write('reports/official/performance.md',performance);write('reports/performance.md',performance)
    # 实际浏览器下载文件按其自身版本与筛选复算，避免用当前版本冒充旧导出
    exported=pd.read_csv(ROOT/'demo/exported_metrics.csv',encoding='utf-8-sig')
    export_run=exported.run_id.iloc[0]
    filters=json.loads(exported.filters.iloc[0])
    export_db=ROOT/'data/official_build'/f'{export_run}.duckdb'
    with duckdb.connect(str(export_db),read_only=True) as con:
        expected=query_metrics(con,filters['start'],filters['end'],filters['device'],filters['first_source'])
    comparisons=[]
    for key in [f'M{i:02d}' for i in range(1,13)]:
        value=exported.loc[exported.metric_id==key,'value'].iloc[0]
        ok=(pd.isna(value) and pd.isna(expected[key])) or abs(value-expected[key])<1e-8
        comparisons.append(dict(metric_id=key,browser_csv=value,sql_service=expected[key],passed=ok,run_id=export_run))
    assert all(r['passed'] for r in comparisons)
    pd.DataFrame(comparisons).to_csv(report/'browser_export_reconciliation.csv',index=False,encoding='utf-8')
    cases=[
      ('U01','完整周期与独立SQL一致','test_U01_period_independent_sql；reconciliation.csv'),
      ('U02','设备筛选同步四页','test_U02_filter_all_supported_pages'),
      ('U03','12项口径完整可查','test_U03_dictionary_cards；metric_dictionary.csv'),
      ('U04','漏斗样本量及最大损失','test_U04_largest_funnel_loss；funnel.csv'),
      ('U05','开放购买与闭合漏斗分开','test_U05_open_and_closed_are_distinct'),
      ('U06','无数据与零基期处理','test_U06_no_data_and_zero_base'),
      ('U07','用户分层互斥完整','test_U07_segments_reconcile；无有效交易不等于未购买专项测试'),
      ('U08','质量问题与运行状态可见','test_U08_quality_visible；fault_cases.json'),
      ('U09','导出元数据与数字一致','test_U09_export_with_metadata；实际浏览器导出12项复算'),
      ('U10','同快照重复执行一致','test_U10_repeatable_snapshot；全量故障工具核对会话及交易主键集合')]
    acceptance='# 技术验收记录\n\n状态：功能技术验收完成，用户验证待完成。实际外部试用人数为0，不报告人工任务成功率。\n\n'
    acceptance+='|编号|验收内容|结果|证据|\n|---|---|---|---|\n'
    acceptance+='\n'.join(f'|{i}|{task}|通过|{evidence}|' for i,task,evidence in cases)
    acceptance+='\n\n15项自动测试全部通过，含10项基本业务用例及5项人工可复算语义/故障测试。独立虚拟环境安装已完成，pip check通过；同机隔离环境完成官方全量处理与测试，未声称在另一台电脑或macOS复跑。\n\n浏览器80项页面切换测量已完成，但四页p95为3.249至3.993秒，均超过3秒；见performance.md。四页真实截图与CSV下载在demo/。实际浏览器导出保留其原发布版本标识，与对应版本12项指标一致。\n'
    write('reports/acceptance.md',acceptance)
    write('reports/environment.md',f'# 复现环境\n\n{platform.platform()}；Python {platform.python_version()}；{platform.processor()}。\n\n独立环境 .venv 从空目录创建，首次ensurepip失败后用宿主pip的--python安装到该环境。依赖锁定在requirements.txt，pip check通过。正式测试使用.venv解释器；TEMP/TMP指向项目内tests/runtime_tmp，避免系统沙盒临时目录访问限制。官方数据源与本地快照都可溯源，离线运行不依赖Google凭证。\n\nWindows已实跑；macOS命令已提供，尚未在macOS实际验证。视频构建脚本使用Windows中文字体，仅该辅助脚本要求Windows字体路径。\n')
    perf_rows='\n'.join(f'|{r["page"]}|{r["p95_seconds"]:.3f}秒|{"达标" if r["meets_target"] else "超过3秒目标"}|' for r in summaries)
    release=f'''# 发布清单 v1.0.0

本次已完成正式数据全量运行和功能技术验收；真实用户验证待完成，页面响应目标未全部达标。运行 {meta['run_id']}。

- [x] 官方来源、92天范围、4,295,584条事件及脱敏限制已披露。
- [x] PRD、优先级、页面原型、数据契约、权限设计与代码对应。
- [x] 12项指标可查看定义、SQL及复算；4页可操作并实际截图。
- [x] 20项质量规则执行：19通过、1警告、0失败；330个重复交易ID、15笔冲突交易、450条缺失ID购买事件如实保留。
- [x] 10条业务验收及5条语义/故障自动测试通过。
- [x] 12项全范围对账、192项筛选对账、12项实际浏览器CSV复算通过。
- [x] 3个故障案例均检测、处理、修复复跑并关闭；重复运行指标与主键集合一致。
- [x] 3项分析附SQL、CSV、图表、样本量和边界。
- [x] 同机隔离虚拟环境安装、pip check、官方全量处理及测试已完成。
- [x] 六分钟页面截图与实际结果回放视频已提供，明确非连续录屏、无旁白。
- [ ] 真实用户走查：尚无真实试用者，模板已备好。
- [ ] 四页浏览器预热p95全部≤3秒：实测四页均超过3秒，继续优化。
- [ ] 浏览器真正冷启动独立计时：未完成。
- [ ] 6—8分钟连续操作并讲解的录屏：目前提供的是六分钟截图回放。
- [ ] 跨机器/macOS复跑：尚未验证。

|页面|实测预热p95，每页20次|目标状态|
|---|---|---|
{perf_rows}

有效交易分层替代“未购”标签，是根据真实样本中ID缺失/冲突导致的归属不确定所作的口径澄清，保留三组互斥及总量对账。未实现D7、RFM、后端角色鉴权和口径变更回滚（P1）。未报告企业运营收益或因果效果。
'''
    write('docs/release_checklist.md',release)
    write('docs/issue_log.md',f'''# 问题及闭环记录

|编号|实际问题|状态|处理及证据|
|---|---|---|---|
|I01|目录只有README|已关闭|实现模型、四页、指标服务、质量、报告和验收|
|I02|最初未发现本机认证|已关闭|找到既有gcloud登录；启用BigQuery沙盒；按日下载92天官方数据|
|I03|真实用户走查尚未发生|待验证|不捏造访谈，见reports/user_feedback.md|
|I04|ensurepip及沙盒临时目录限制|已关闭|独立环境安装并pip check；测试临时目录放项目内，15项通过|
|I05|历史交易ID字段空值及占位值|已关闭|核查event_params，保留初版，修正字段且其他字段多重集合一致；transaction_repair_full.json|
|I06|无有效订单者被误称未购买|已关闭|按有效交易数命名，展示购买行为及未匹配覆盖；人工样本专项测试通过|
|I07|部分页面p95超过3秒|待迭代|加入按发布数据库与筛选条件缓存；实际80条浏览器计时全部保留，不以服务耗时替代|
|I08|原生窗口激活授权超时|已有替代交付|浏览器控制完成页面验收与导出；六分钟截图回放替代连续录屏，类型已注明|
|F01|冲突交易测试注入|已关闭|检测隔离、还原、副本全量复跑；reports/official/fault_cases.json|
|F02|缺失日期测试注入|已关闭|阻断发布、保留成功指针、补回复跑|
|F03|发布前刷新失败|已关闭|旧库可查，恢复复跑指标一致|

正式数据已知限制：330个重复交易ID，其中15笔有冲突；450条purchase缺失有效交易ID。此处不是把样本缺陷“修复”为真实业务数据，而是保留与披露，仅对冲突订单隔离。
''')
    change=(ROOT/'docs/change_log.md').read_text(encoding='utf-8')
    if '最终功能验收' not in change:
        change+='\n最终功能验收：官方92天快照、15项测试、192项筛选对账及三例全量故障恢复通过。增加发布版本感知的查询缓存；浏览器每页20次测量，性能目标仍有未达项。将无有效交易者与未购买行为区分，实际发现当前14天有228个未匹配有效订单的购买者。\n'
        write('docs/change_log.md',change)
    readme=(ROOT/'README.md').read_text(encoding='utf-8').split('\n## 本次实际交付结果')[0]
    readme+=f'''\n## 本次实际交付结果

官方GA4样本已下载并完整运行，范围2020-11-01至2021-01-31（92天）。原始事件4,295,584，观察用户270,154，有效会话360,129，有效交易4,888，已记录USD购买金额337,993。不是受控数据的业务结论。

15项自动测试通过；20项质量检查为19通过、1警告；192项筛选对账和实际浏览器CSV的12项指标复算一致；三类异常均完成修复复跑。正式报告在reports/official/，入口为reports/business_analysis.md。详细完成与未完成项目见docs/release_checklist.md。

已启动本机产品：http://127.0.0.1:8501 。重启只需执行 `.\\.venv\\Scripts\\python.exe -m streamlit run app.py`，读取现有正式发布结果，无需重新登录Google或下载数据。

六分钟演示为 `demo/platform_walkthrough.mp4`，使用真实页面截图与运行结果回放，无旁白，非连续录屏。真实用户走查、连续讲解录屏、浏览器冷启动计时待完成；浏览器页面p95为3.249至3.993秒，四页均超过3秒目标，未将其标成达标。

三项真实分析概况：当前14天较前14天有效交易金额增加9,580美元（交易ID覆盖同时下降）；会话购买转化增加0.587个百分点，组内变化贡献占主导；严格路径主要缺口在浏览到加购，且无有效交易组中有228名购买事件用户。各结论的分母、日期、覆盖限制与实验建议均已在报告中展开。
'''
    write('README.md',readme);write('README.runtime.md',readme)
    write('demo/video_link.md','# 演示视频\n\n文件：[platform_walkthrough.mp4](platform_walkthrough.mp4)，6分钟，1920×1080。实际页面截图与运行结果回放，非连续录屏，无旁白；帧与时长验证见video_metadata.json。\n\n包含目标、官方数据、总览、转化、分层、质量、故障修复及验收边界。6—8分钟连续操作讲解录屏尚未完成；可按demo_script.md另行录制。\n')
    write_json(ROOT/'reports/delivery_summary.json',dict(generated_at=now(),run_id=meta['run_id'],source_kind='official',event_rows=manifest['rows'],
      users=int(m['M01']),sessions=int(m['M02']),orders=int(m['M07']),recorded_purchase_usd=m['M08'],tests_passed=15,
      quality_passed=int((checks.status=='pass').sum()),quality_warnings=int((checks.status=='warning').sum()),filtered_reconciliations=192,
      browser_export_reconciliations=12,fault_cases_closed=3,browser_p95=summaries,user_validation='pending',continuous_narrated_recording='pending',
      video_type='实际页面截图与运行结果回放，非连续录屏、无旁白'))
    print(summary.to_string(index=False))
    print('交付记录、发布清单和README已按实际结果填写')


if __name__=='__main__':main()
