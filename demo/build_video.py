"""将实际页面截图和已运行结果整理为六分钟无旁白演示回放。"""
import json
import subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import imageio_ffmpeg
from src.common import ROOT,read_json,write_json


def main():
    output=ROOT/'demo/video_frames';output.mkdir(parents=True,exist_ok=True)
    font_path='C:/Windows/Fonts/msyh.ttc'
    font=ImageFont.truetype(font_path,30)
    small=ImageFont.truetype(font_path,23)
    heading=ImageFont.truetype(font_path,44)
    chapter=ImageFont.truetype(font_path,34)
    scenes=[
      ('项目目标与实施流程','01_overview.png',[
       '模拟业务问题：当访问、转化和金额变化方向不一致，如何找到变化环节并排查数据问题。',
       '流程：PRD与范围 → 指标注册 → 官方快照 → SQL建模 → 质量校验 → 四页产品 → 分析、验收及故障复跑。',
       '12项核心指标，4个操作页面。平台使用历史脱敏样本，分析仅覆盖样本观察，不代表线上经营改善。']),
      ('真实数据与历史字段核验','01_overview.png',[
       'Google官方GA4电商脱敏样本：2020年11月1日至2021年1月31日，92天，4,295,584条事件。',
       '先跑7天，再扩展完整区间；清单记录日期、字段、行数、文件大小和BigQuery任务ID。',
       '交易ID从有效ecommerce字段或event_params提取；初版快照保留，修正前后其他字段和事件量核对一致。']),
      ('经营总览：完整两期比较','01_overview.png',[
       '比较2021年1月4日至17日，与1月18日至31日；各14天，不按差异挑选极端日期。',
       '有效交易记录金额：22,153美元 → 31,733美元；增加9,580美元。订单量贡献4,653.92美元，客单价贡献4,926.08美元。',
       '同期购买事件交易ID覆盖率93.40% → 63.41%。金额只覆盖合格交易，不能解释成所有成交或利润。']),
      ('转化诊断：有序路径与覆盖','02_funnel.png',[
       '当前严格漏斗：12,671个浏览会话 → 2,135个有序加购 → 859个有序结账 → 503个有序购买。',
       '每步时间必须严格晚于前一步。并列时间戳不猜测先后；普通购买会话685个，与闭合漏斗分别展示。',
       '设备结构贡献约负0.001个百分点，组内转化贡献约正0.588个百分点；这是观察拆解，不是因果。']),
      ('用户分层：不把未知当未购','03_segments.png',[
       '所选14天共43,047个观察用户；按有效交易次数分为无有效交易、单次有效交易和多次有效交易。',
       '三组人数分别42,614、421、12。无有效交易组里仍有228人存在purchase事件。',
       '缺失或冲突交易ID导致无法匹配，不代表未发生购买。窗口、设备和首次获客来源与导出保持一致。']),
      ('指标与数据运营','04_operations.png',[
       '20项质量检查：19项通过、1项警告，0项阻断失败。警告涉及330个重复交易ID、15笔冲突交易和450条缺失ID购买事件。',
       '一致重复合并；冲突交易整笔隔离；缺失ID不自动造订单。USD金额、覆盖率与客单价分母分别解释。',
       '运营页提供可搜索字典、异常样例、质量结果、运行日志、问题与版本记录。']),
      ('故障演示与修复复跑','04_operations.png',[
       'F01：测试副本增加同ID冲突金额，命中Q07，整笔隔离；还原后复跑，核心结果恢复。',
       'F02：测试副本缺一个日期，Q01阻断发布；成功版本保留，补回分区后恢复。',
       'F03：发布前模拟刷新失败，旧库继续可查；修复复跑。官方源快照不受故障注入影响，完整记录见fault_cases.json。']),
      ('验收、结果与交付边界','01_overview.png',[
       '全区间：270,154个观察用户，360,129个有效会话，4,888笔有效交易，已记录USD购买金额337,993。',
       '15项自动测试通过；12项全范围指标以及192项日期、设备、来源筛选对账一致。真实用户走查尚未完成。',
       '服务耗时与浏览器耗时分别记录；部分页面切换超过3秒目标。下一步是页面响应优化、真实试用及连续讲解录屏。'])
    ]
    def paragraph(draw,text,x,y,width):
        line=''
        for char in text:
            if char in '，。；：！？、）”' and line:
                line+=char
                continue
            if draw.textlength(line+char,font=font)>width:
                draw.text((x,y),line,font=font,fill='#253b54');y+=47;line=''
            line+=char
        if line:draw.text((x,y),line,font=font,fill='#253b54');y+=47
        return y+28
    frames=[]
    for i,(title,filename,paragraphs) in enumerate(scenes,1):
        canvas=Image.new('RGB',(1920,1080),'#eef3f9');draw=ImageDraw.Draw(canvas)
        draw.rectangle((0,0,1920,100),fill='#172b4d')
        draw.text((35,24),'电商用户转化分析与指标管理平台',font=heading,fill='white')
        draw.text((1530,34),f'流程 {i:02d} / 08',font=chapter,fill='#a6d5f7')
        screenshot=Image.open(ROOT/'demo/screenshots'/filename).convert('RGB')
        screenshot.thumbnail((1160,910))
        canvas.paste(screenshot,(25+(1160-screenshot.width)//2,120))
        draw.rounded_rectangle((1210,120,1890,1015),radius=20,fill='white')
        y=145
        # 标题按可见宽度换行，避免中文超出右栏
        for offset in range(0,len(title),16):
            draw.text((1240,y),title[offset:offset+16],font=chapter,fill='#1d6395');y+=52
        y+=12
        for text in paragraphs:y=paragraph(draw,text,1240,y,620)
        draw.text((35,1040),'真实页面截图与运行结果回放 · 非连续录屏 · 无旁白 · 官方脱敏历史样本',font=small,fill='#52667d')
        target=output/f'{i:02d}.png';canvas.save(target);frames.append(target)
    listing=ROOT/'demo/video_frames.txt'
    listing.write_text(''.join(f"file '{f.as_posix()}'\nduration 45\n" for f in frames)+f"file '{frames[-1].as_posix()}'\n",encoding='utf-8')
    video=ROOT/'demo/platform_walkthrough.mp4'
    command=[imageio_ffmpeg.get_ffmpeg_exe(),'-y','-f','concat','-safe','0','-i',str(listing),'-t','360','-r','2','-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(video)]
    result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
    if result.returncode:raise RuntimeError(result.stderr[-2000:])
    count,seconds=imageio_ffmpeg.count_frames_and_secs(str(video))
    write_json(ROOT/'demo/video_metadata.json',dict(kind='真实页面截图与结果回放，非连续录屏，无旁白',duration_seconds=seconds,frames=count,
       source_screenshots=[f'demo/screenshots/{s[1]}' for s in scenes],video_bytes=video.stat().st_size))
    print(f'演示视频 {seconds} 秒，{count} 帧，{video.stat().st_size} 字节')


if __name__=='__main__':main()
