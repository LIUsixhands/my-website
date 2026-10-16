"""麗晨語山簷 實登清洗 — 走小登管線（.claude/skills/skill-xiao-deng/references/實登批次處理管線.py）。
口徑：扣車位重算房屋單價（車位價、車位坪數逐案由車位分頁取）、排除特殊關係；排除 1F 店面（河南路四段門牌）。
戶型：之1＝A（4房，房屋 70.82 坪）｜之2＝B（3房，63.37 坪）｜之3＝C（3房，55.96 坪，本戶同型）。
波段：預售（建商首售，110/08–113/05，使照 113/07 前）｜交屋後（115 起）。對外行情只走 headline()。"""
import sys, json, statistics as st, csv
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / '.claude/skills/skill-xiao-deng/references'))
import 實登批次處理管線 as P

_, raw = P.load(str(HERE / '實登_大業路556號.xls'))
keep, drop = P.clean(raw)
shop = [x for x in keep if '河南路' in x['addr'] or not x['fl']]
keep = [x for x in keep if x not in shop]
drop += [('1F 店面（非住宅）', x) for x in shop]
rows, MA, MV = P.recompute(keep)

def unit(a):
    return 'A' if a.endswith(('之１', '之1')) else 'B' if a.endswith(('之２', '之2')) else 'C' if a.endswith(('之３', '之3')) else '?'
for x in rows:
    x['unit'] = unit(x['addr'])
    x['gross'] = x['tot'] / x['area']
    x['wave'] = '預售' if (x['yr'] <= 113) else '交屋後'
    x['pv'] = x['pk_val'] or x['pkv_row'] or 0

def med(v): return round(st.median(v), 2) if v else None
out = dict(撈取日='2026-10-16', 查詢區間='101/01–115/10', 原始筆數=len(raw), 有效筆數=len(rows),
           排除=[dict(原因=w, 日期=x['date'], 門牌=x['addr'][-12:]) for w, x in drop])
out['近三年'] = P.headline(rows, window=(113, 115), name='麗晨語山簷 近三年')
out['交屋後'] = P.headline([x for x in rows if x['wave'] == '交屋後'], window=(115, 115), name='115 年交屋後')
out['預售'] = P.headline([x for x in rows if x['wave'] == '預售'], allow_full=True, name='預售全期')
out['戶型'] = {}
for u in 'ABC':
    g = [x for x in rows if x['unit'] == u]
    out['戶型'][u] = dict(n=len(g), 房屋坪=med([x['base'] for x in g]),
                         預售中位=med([x['val'] for x in g if x['wave'] == '預售']),
                         交屋後中位=med([x['val'] for x in g if x['wave'] == '交屋後']),
                         交屋後n=sum(1 for x in g if x['wave'] == '交屋後'))
pk = lambda g: [x['pv'] / x['npark'] for x in g if x['npark'] and x['pv']]
out['車位每席'] = dict(預售中位=med(pk([x for x in rows if x['wave'] == '預售'])),
                    交屋後中位=med(pk([x for x in rows if x['wave'] == '交屋後'])),
                    交屋後=sorted(pk([x for x in rows if x['wave'] == '交屋後'])))
out['年度'] = [dict(年=y, n=len(g), 不含車中位=med([x['val'] for x in g]), 含車中位=med([x['gross'] for x in g]))
              for y in sorted({x['yr'] for x in rows}) for g in [[x for x in rows if x['yr'] == y]]]
out['成交'] = [dict(日期=x['date'], 戶型=x['unit'], 樓層=x['fl'], 總價=x['tot'], 坪數=x['area'], 車位=x['npark'],
                  車位價=x['pv'], 房屋坪=round(x['base'], 2), 單價=round(x['val'], 2), 含車單價=round(x['gross'], 2),
                  波段=x['wave'], 備註=('紅單轉讓' if '轉讓' in x['note'] else '') + ('門牌與樓別不一致' if x['fl'] == 4 and '十樓' in x['addr'] else ''))
             for x in sorted(rows, key=lambda x: x['date'])]

# 本戶：7F之3（C），開價 4,580 萬，78.27 坪，2 坡道平面（22.31 坪）
L = dict(門牌='大業路556號7樓之3', 戶型='C', 樓層=7, 總價=4580, 坪數=78.27, 車位=2, 車位坪=22.31,
         主建物=32.98, 附屬=4.07, 公設=18.91, 地坪=10.56)
L['房屋坪'] = round(L['坪數'] - L['車位坪'], 2)
L['車位估'] = round(2 * out['車位每席']['交屋後中位'])
L['單價'] = round((L['總價'] - L['車位估']) / L['房屋坪'], 2)
L['含車單價'] = round(L['總價'] / L['坪數'], 2)
out['本戶'] = L

with open(HERE / 'transactions.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['交易日期', '戶型', '樓層', '總價萬', '總面積坪', '車位數', '車位價萬', '房屋坪', '房屋單價(已扣車位)', '總價÷總坪數', '波段', '備註'])
    for r in reversed(out['成交']):
        w.writerow([r['日期'], r['戶型'], r['樓層'], r['總價'], r['坪數'], r['車位'], r['車位價'], r['房屋坪'], r['單價'], r['含車單價'], r['波段'], r['備註']])
json.dump(out, open(HERE / 'summary.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps({k: out[k] for k in ('有效筆數', '排除', '近三年', '交屋後', '預售', '戶型', '車位每席', '年度', '本戶')}, ensure_ascii=False, indent=1))
