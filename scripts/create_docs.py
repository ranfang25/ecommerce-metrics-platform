"""生成指标注册及交付文档。"""
from pathlib import Path
import csv
import yaml
from src.common import ROOT, write_json

if (ROOT/'docs/PRD.md').exists():
    raise SystemExit('交付文档已存在；初始化脚本不覆盖已发布的文档和结果。')


def write(path,text):
    target=ROOT/path
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(text,encoding='utf-8')


names=['观察用户数','有效会话数','商品浏览会话数','加购会话数','结账会话数','购买会话数','有效交易数','已记录购买金额（USD）','金额完整订单客单价','会话购买转化率','浏览到加购转化率','结账到购买转化率']
formula=['COUNT(DISTINCT user_id)','COUNT(*) fact_sessions','COUNT_IF(has_view)','COUNT_IF(has_cart)','COUNT_IF(has_checkout)','COUNT_IF(has_purchase)','COUNT(*) fact_orders','SUM(revenue_usd)','SUM(revenue_usd)/COUNT(revenue_usd)','M06/M02','COUNT(cart_ts)/COUNT(view_ts)','COUNT(purchase_ts)/COUNT(checkout_ts)']
rows=[]
for i,name in enumerate(names,1):
    grain='用户事件' if i==1 else ('交易' if i in [7,8,9] else '会话')
    time='event_date' if i==1 else ('purchase_date' if i in [7,8,9] else 'session_date')
    rows.append(dict(metric_id=f'M{i:02d}',name=name,business_definition=name+'；样本内观察口径',formula=formula[i-1],
        numerator= formula[i-1].split('/')[0],denominator= formula[i-1].split('/')[1] if '/' in formula[i-1] else '不适用',
        grain=grain,time_field=time,filters='选定日期、设备及首次获客来源；有效标识；交易冲突隔离',
        dimensions='device;first_source',source_table='fact_events' if i==1 else ('fact_orders' if i in [7,8,9] else 'fact_sessions'),
        sql_path='sql/marts/metrics.sql',exception_policy='零分母与缺失金额为空；金额保留两位小数；重复冲突交易隔离；同时间戳不判定顺序',
        owner_role='分析维护者（模拟角色）',version='1.0.0',effective_date='2026-11-11',acceptance_case='U01/U03/U09'))
(ROOT/'docs').mkdir(exist_ok=True)
with (ROOT/'docs/metric_dictionary.csv').open('w',encoding='utf-8',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]))
    writer.writeheader();writer.writerows(rows)
write('config/metrics.yml',yaml.safe_dump({'version':'1.0.0','metrics':rows},allow_unicode=True,sort_keys=False))
rules=['日期覆盖','字段类型','空用户','空会话','重复导入','事件保留','交易冲突','交易归属','会话唯一','漏斗顺序','漏斗单调','比率分母','金额覆盖','商品粒度','金额对账','分层完整','筛选对账','观察窗口','失败保留','版本对应']
write('config/quality_rules.yml',yaml.safe_dump({'rules':[{'id':f'Q{i:02d}','name':name,'severity':'warning' if i in [3,4,7,8,13] else 'error','implementation':'src/quality.py','policy':'警告保留披露；错误阻断发布'} for i,name in enumerate(rules,1)]},allow_unicode=True,sort_keys=False))
docs={
'docs/PRD.md':'''# PRD v1.0

目标：业务使用者独立完成查指标、看口径、找异常、看证据、导出结果。模拟角色：经营负责人、运营、分析、维护。真实试用待招募，不把模拟角色当成访谈。

核心问题：访问、转化与金额变化出现差异时，在哪个阶段或设备上定位可复算的变化，并先排查数据问题。

|需求|优先级及理由|交互与验收|
|---|---|---|
|12项统一口径|P0，防止多页数字冲突|字典、SQL、页面、导出对应；U01/03/09|
|经营总览|P0，支持周期判断|完整等长周期；零基期不显示增长率；U01/02|
|转化诊断|P0，定位阶段损失|严格时间递增，开放购买独立显示；U04/05|
|用户分层|P0，定位用户集合|窗内未购、单购、多购互斥；U07|
|质量与日志|P0，可现场处理失败|20项检查、3个异常；U08|
|导出与复现|P0，可交接|版本/筛选/日期/时间；U09/10|
|D7、RFM、真实权限|P1，观察期及鉴权成本较高|未实现，不展示成品声明|
|实时、投放、推荐|P2，超出历史样本分析边界|不在发布范围|

加载态用spinner；无数据给出筛选说明；缺失金额显示覆盖率且不补零；处理失败展示错误及上一成功版本。应用不触发全库刷新。

金额精度：USD两位小数，明细与汇总容差小于0.005美元。常用数据服务预热20次p95目标3秒；浏览器交互单独验收，不能用查询耗时替代页面耗时。

M1=模型与复算；M2=四页筛选及导出；M3=技术验收及故障演示。官方数据、真实试用和录像的完成状态以 release_checklist 为准。
''',
'docs/research_assumptions.md':'''# 研究假设与需求记录

业务痛点和角色来自项目设计假设，未进行真实访谈。假设H1：统一口径能减少解释成本；H2：阶段漏斗能帮助定位问题；H3：质量异常需要与业务变化同屏核查。

验证：邀请使用者完成10个验收任务，记录成功率、耗时和意见；不能从受控样本推断业务效果。Google官方样本有脱敏占位值，不能与在线演示账户对账。

需求池：D7、RFM、口径版本回滚、后端权限、第二轮试用均延后；优先解决数据接入、完整日期与金额覆盖。
''',
'docs/data_contract.md':'''# 数据契约 v1.0

官方来源：bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*。官方标注区间2020-11-01至2021-01-31；实际范围、行数和覆盖以导出清单为准。当前官方快照待接入。

|字段|类型|约束|
|---|---|---|
|event_date|YYYYMMDD字符串|源站点日期；不从UTC时间戳推导日期|
|event_timestamp|int64|UTC微秒；仅用于事件先后|
|event_name|字符串|必须存在|
|user_pseudo_id|可空字符串|空值保留原始层，排除用户指标|
|ga_session_id|可空int64|与用户构成会话键；缺失排除会话指标|
|device / first_source|可空字符串|空值显示未知；来源仅首次获客|
|transaction_id|可空字符串|空、(not set)、<Other>为无效；冲突隔离|
|purchase_revenue_usd|可空数值|仅USD购买金额，转为DECIMAL(18,2)|
|currency|可空字符串|原币种仅供披露；不与USD指标混加|
|items_json|JSON数组字符串|商品数量与item_revenue_in_usd独立展开|

会话日期取全快照内最早可见event_date；数据两端会话可能截断。设备与来源取最早事件属性；同时间戳属性并列时按导出行号选取，仅用于属性归属，不用于漏斗顺序。

有效交易要求ID可识别且用户/会话/日期/USD金额完全一致；重复一致记录合并，任一冲突整笔隔离（包括金额空值与非空值不一致）。最早购买行商品作为代表，重复事件商品差异不作真实商品销售结论。缺失用户或会话的可识别交易保留金额指标，但归属覆盖单列披露。

M06为含可识别交易ID购买事件的会话数，包括之后被交易冲突隔离的事件，不等于合格交易数。严格漏斗purchase也要求交易ID可识别；每一步时间严格大于前一步；相等不推定顺序，存在并列阶段单列覆盖。

文件登记以文件名、字节数、行数、日期、字段和BigQuery job_id溯源；快照完整重建避免重复追加。数据目录使用项目相对路径。
''',
'docs/data_model.md':'''# 模型与关联

```mermaid
flowchart LR
 A[官方导出 raw_events] --> B[fact_events 一行一事件]
 B --> C[fact_sessions 用户×会话]
 B --> D[order_audit 交易冲突检查]
 D --> E[fact_orders 一行一有效交易]
 D --> Q[quarantined_orders 冲突隔离]
 E --> F[fact_order_items 交易×商品行]
 C --> G[mart_daily_metrics / mart_funnel]
 B --> H[mart_user_segments 全窗口用户]
 E --> H
 G --> I[统一指标服务]
 C --> I
 E --> I
 I --> J[四页产品 / 导出 / 报告]
```

主键：事件event_row_id仅表示本次导入位置；会话(user_id,session_id)；交易transaction_id；商品(transaction_id,item_line)。事件关联会话为多对一；交易关联会话为多对一；商品关联交易为多对一。金额始终在订单粒度计算，不能先连接商品后相加。

mart日表支持趋势；周期用户与比率必须由原粒度重算。ops_quality_results记录本次20项结果；每个发布数据库含本次ops_pipeline_runs；跨运行日志在runs.jsonl。发布指针只在全部阻断规则通过后切换。
''',
'docs/permission_matrix.md':'''# 权限策略（设计产物）

|模拟角色|查看|汇总导出|刷新与维护|
|---|---|---|---|
|业务查看|是|否|否|
|分析人员|是|是|否|
|数据维护|是|是|是|

P0为本机单用户应用，无真实登录鉴权。页面未用角色下拉框假装鉴权；角色后端检查及越权测试属P1，未完成。
''',
'docs/wireframes/interaction.md':'''# 页面原型与交互

共同结构：顶部来源/样本区间/成功时间 → 左侧页面、起止日期、设备、首次来源 → 当前指标CSV导出 → 页面主体。

总览：6张主卡 → 完整等长基期差异 → 日会话趋势 → 可展开12项字典 → 参数和SQL。

诊断：严格漏斗 → 前阶段转化率 → 顺序不确定与未匹配覆盖 → 两期设备比较 → 窗内用户分组路径 → SQL证据。

分层：窗口和截至日 → 三组人数柱图 → 人数、占比、交易、金额 → 解释分组定义及多设备重叠。

运营：可搜索字典 → 20项校验 → 空会话/重复/冲突样例 → 跨运行日志 → 问题与版本。

空态：筛选没有事件或交易时提示调整；加载态spinner；不完整：日期越界拒绝查询、缺失金额显示覆盖；失败态：保留旧版并显示错误。截图由demo/capture.py运行后生成。
''',
'docs/change_log.md':'''# 版本记录

2026-11-11 v1.0.0：从仅有实施方案构建数据接入、SQL模型、统一指标服务、四页Streamlit、质量检查和验收工具。原计划保存在README.plan.v1.md。

真实反馈尚未发生，不记录虚构的用户建议。后续接入官方数据须重新生成profile、报告、质量与验收记录。
''',
'docs/issue_log.md':'''# 问题记录

|编号|问题|状态|处置与复验|
|---|---|---|---|
|I01|仅README，无平台代码|实现完成，验收状态见报告|新增全链路代码与四页产品|
|I02|官方数据缺少项目与ADC认证|待用户配置|提供登录步骤；不以受控数据替代正式业务发现|
|I03|真实试用未邀请|用户验证待完成|任务模板见reports/user_feedback.md|
|I04|虚拟环境ensurepip初始化失败|已提供替代安装路径|python -m pip --python .venv install -r requirements.txt|
|F01|受控交易金额冲突|执行状态见fault_cases.json|检测隔离、还原测试副本、复跑对账|
|F02|受控日期分区断档|执行状态见fault_cases.json|Q01阻断、保留成功指针、补回副本复跑|
|F03|受控刷新中断|执行状态见fault_cases.json|发布前异常、旧版可查、修复复跑|
''',
'reports/business_analysis.md':'''# 正式业务分析：等待官方数据

用户明确要求真实数据。当前未取得BigQuery项目ID与本机授权，不能填写官方样本行数或真实业务结论。

登录后按docs/real_data_setup.md下载7天验证，再下载2020-11-01至2021-01-31完整区间。执行pipeline、validation、reporting，自动生成三项有SQL及图表支持的发现：金额对称分解、设备流量构成与组内转化拆解、严格漏斗损失与用户分层。

受控技术运行报告位于reports/controlled/，不作为正式业务成果。独立试用与真实干预实验仍需要实际参与者。
''',
'reports/data_profile.md':'# 官方数据 Profile\n\n待本机Google授权及官方快照下载后生成。不得以测试行数替代。\n',
'reports/quality_report.md':'# 正式数据质量\n\n官方数据未接入，尚无正式质量结果。受控测试见reports/controlled/。\n',
'reports/user_feedback.md':'''# 真实用户走查

状态：用户验证待完成。当前没有真实试用者，不报告试用人数、成功率或反馈改进。

请邀请至少1位使用者，在不代替其操作的前提下完成：查两期指标→看一个比率口径→定位漏斗损失→筛选设备→查看异常→导出复算。

|匿名角色|实际日期|任务|是否独立成功|耗时秒|原话或操作问题|修改|复验|
|---|---|---|---|---|---|---|---|
|待填写||||||||

技术自动验收与用户验证分开记录；录像中的操作演示也不代表真实用户反馈。
''',
'demo/demo_script.md':'''# 6—8分钟现场演示脚本

1. 1分钟：业务问题、模拟角色、P0取舍；明确数据来源。
2. 1分钟：经营总览选两个完整周期，展开M10分母；金额覆盖单独说明。
3. 2分钟：切转化诊断，比较设备、漏斗损失、顺序不确定；只陈述关联。
4. 1分钟：运营页查看Q07与Q01，打开fault_cases.json说明发现、定位、恢复；故障仅影响测试副本。
5. 1分钟：用户分层、导出，按相同筛选复算；真实反馈未完成时据实说明。
6. 1分钟：版本、复现命令、未完成事项与P1优先级。

现场执行完整故障演示：python -m src.validation --config config/settings.demo.yml。正式样本原文件不会被改写。
''',
'demo/video_link.md':'''# 演示录像状态

尚未录制6—8分钟讲解录像。自动页面交互录像与截图（如已生成）在demo/screenshots/，用于技术走查，不替代讲解或真实试用。

正式数据接入并确认结论后，按demo_script.md录制讲解，填写实际文件路径或可访问链接。
''',
}
for path,body in docs.items(): write(path,body)
write_json(ROOT/'data/manifest.json',{'official_status':'pending_authentication','official_source':'bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*','controlled_fixture':'tests/fixtures/manifest.json','note':'受控样本仅用于技术验收，正式数据禁止静默回退'})
print('文档与12项指标注册已生成')
