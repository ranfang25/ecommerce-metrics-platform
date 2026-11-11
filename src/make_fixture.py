"""固定种子的受控测试数据，不能用作真实业务结论。"""
import json
import random
from datetime import datetime, timedelta, timezone
import pandas as pd
from src.common import ROOT, write_json, now


def generate():
    rng = random.Random(20261111)
    rows = []
    base = datetime(2020,11,1,tzinfo=timezone.utc)
    for day in range(28):
        for i in range(100 + day % 7 * 3):
            device = rng.choices(['desktop','mobile','tablet',None], [.48,.43,.07,.02])[0]
            user = f'u{rng.randrange(450):04d}'
            sid = 100000+day*1000+i
            t = base + timedelta(days=day, hours=9, seconds=i*90)
            stage = rng.choices([1,2,3,4], [.52,.20,.13,.15] if day<14 else [.56,.21,.12,.11])[0]
            for j,event in enumerate(['view_item','add_to_cart','begin_checkout','purchase'][:stage]):
                revenue = round(rng.uniform(15,180)*(1.12 if day>=14 else 1),2) if event=='purchase' else None
                rows.append(dict(event_date=t.strftime('%Y%m%d'), event_timestamp=int((t+timedelta(seconds=j*10)).timestamp()*1e6),
                    event_name=event,user_pseudo_id=user,ga_session_id=sid,device=device,first_source='google' if i%3 else '(direct)',
                    transaction_id=f't{sid}' if event=='purchase' else None,
                    purchase_revenue_usd=revenue if i%31 else None,currency='USD' if revenue is not None else None,
                    items_json=json.dumps([dict(item_id='SKU1',item_name='测试商品',quantity=1,item_revenue_in_usd=revenue)],ensure_ascii=False) if event=='purchase' else '[]'))
    # 加入可解释的缺失标识、同时间戳路径和开放购买
    example = rows[0].copy()
    rows.append({**example,'user_pseudo_id':None,'ga_session_id':None})
    rows.append({**example,'user_pseudo_id':'missing_session','ga_session_id':None})
    for event in ['view_item','add_to_cart','begin_checkout','purchase']:
        rows.append({**example,'user_pseudo_id':'tied_user','ga_session_id':999999,'event_name':event,
                     'transaction_id':'tied_order' if event=='purchase' else None,'purchase_revenue_usd':20 if event=='purchase' else None})
    rows.append({**example,'user_pseudo_id':'open_user','ga_session_id':888888,'event_name':'purchase','transaction_id':'open_order','purchase_revenue_usd':30})
    frame = pd.DataFrame(rows)
    out = ROOT/'tests/fixtures'
    out.mkdir(parents=True,exist_ok=True)
    frame.to_parquet(out/'events.parquet',index=False)
    write_json(out/'manifest.json', {'source_kind':'controlled','source':'固定种子生成，仅供技术测试', 'rows':len(frame),
        'start':'2020-11-01','end':'2020-11-28','exported_at':now(),'fields':list(frame.columns),'seed':20261111,'version':'1.0.0'})
    print(f'受控样本 {len(frame)} 条')


if __name__ == '__main__':
    generate()
