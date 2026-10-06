"""聯聚保和大廈 實登清洗 — 走小登管線（.claude/skills/skill-xiao-deng/references/實登批次處理管線.py）。
口徑：扣車位重算淨單價（108 年後車位未揭露者以本棟坡道平面每席中位估算）、排除特殊關係與債務抵償、
分「建商首售／餘屋」與「轉售」兩組；對外行情只走 headline()：近三年、中位數、含車／不含車並列。"""
import sys, json, statistics as st, csv
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / '.claude/skills/skill-xiao-deng/references'))
import 實登批次處理管線 as P

_, raw = P.load(str(HERE / '實登_市政路25號.xls'))
keep, drop = P.clean(raw)
drop = [(w, x) for w, x in drop]
debt = [x for x in keep if '債務' in x['note']]
keep = [x for x in keep if '債務' not in x['note']]
drop += [('債務抵償', x) for x in debt]
rows, MA, MV = P.recompute(keep)

def unit(addr):
    return 'B' if ('之１' in addr or '之1' in addr) else 'A' if ('之２' in addr or '之2' in addr) else '整層'
for x in raw:
    x['unit'] = unit(x['addr'])
    x['gross'] = x['tot'] / x['area']
    x['wave'] = '建商' if '第一次登記' in x['note'] else '轉售'
    x['split'] = bool(x['pkv_row'])

def med(v): return round(st.median(v), 2) if v else None
out = dict(撈取日='2026-10-06', 查詢區間='101/01–115/10', 原始筆數=len(raw),
           排除=[dict(原因=w, 日期=x['date'], 樓層=x['fl']) for w, x in drop], 有效筆數=len(rows),
           車位=dict(每席面積=round(MA, 2), 每席價格中位=round(MV, 1)))
out['近三年'] = P.headline(rows, window=(113, 115), name='聯聚保和 近三年')
out['近四年'] = P.headline(rows, window=(112, 115), name='聯聚保和 112–115')
out['建商'] = P.headline([x for x in rows if x['wave'] == '建商'], allow_full=True, name='建商首售／餘屋')
out['轉售'] = P.headline([x for x in rows if x['wave'] == '轉售'], allow_full=True, name='轉售全期')
out['年度'] = [dict(年=y, n=len(g), 不含車中位=med([x['val'] for x in g]), 含車中位=med([x['gross'] for x in g]),
                  轉售n=sum(1 for x in g if x['wave'] == '轉售'))
              for y in sorted({x['yr'] for x in rows}) for g in [[x for x in rows if x['yr'] == y]]]
cuts = [(2, 9, '低樓層 2–9F'), (10, 17, '中樓層 10–17F'), (18, 25, '中高樓層 18–25F'), (26, 38, '高樓層 26F+')]
out['樓層帶'] = []
for lo, hi, nm in cuts:
    d = dict(帶=nm)
    for w in ('建商', '轉售'):
        g = [x for x in rows if lo <= x['fl'] <= hi and x['wave'] == w]
        d[w] = dict(n=len(g), 不含車中位=med([x['val'] for x in g]), 含車中位=med([x['gross'] for x in g]))
    g = [x for x in rows if lo <= x['fl'] <= hi]
    d['總價中位'] = round(st.median([x['tot'] for x in g]))
    out['樓層帶'].append(d)

with open(HERE / 'transactions.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['交易日期', '戶別', '樓層', '總價萬', '總面積坪', '車位數', '車位價萬', '車位價來源', '扣車位面積坪', '含車單價', '不含車單價', '期別', '有效', '備註'])
    ok = {id(x) for x in rows}
    for x in sorted(raw, key=lambda x: x['date'], reverse=True):
        pv = x['pkv_row'] or round(x['npark'] * MV)
        base = x['area'] - (x['pk_area'] or x['npark'] * MA)
        net = (x['tot'] - pv) / base
        w.writerow([x['date'], x['unit'], x['fl'], x['tot'], x['area'], x['npark'], pv,
                    '實登揭露' if x['split'] else '估算(坡道平面中位)', round(base, 2), round(x['gross'], 2), round(net, 2),
                    x['wave'], '是' if id(x) in ok else '否', x['note'].replace('\n', ' ')])
json.dump(out, open(HERE / 'summary.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps({k: out[k] for k in ('有效筆數', '近三年', '近四年', '建商', '轉售', '樓層帶')}, ensure_ascii=False, indent=1))
