"""富邦天空樹 實登清洗 — 走小登管線（.claude/skills/skill-xiao-deng/references/實登批次處理管線.py）。
口徑：扣車位重算淨單價（未拆價車位以同類別中位估算）、排除特殊關係、兩門牌檔去重、
對外行情只走 headline()：近三年、中位數、含車／不含車並列。"""
import re, sys, json, statistics as st
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / '.claude/skills/skill-xiao-deng/references'))
import 實登批次處理管線 as P

CN = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
def addr_floor(addr):
    """樓別欄偶有全形數字（如「２８層」）管線解析不到，改由門牌取樓層。"""
    s = re.search(r'號(.+?)樓', addr.translate(str.maketrans('０１２３４５６７８９','0123456789'))).group(1)
    if s.isdigit(): return int(s)
    if '十' in s:
        a, b = s.split('十'); return (CN.get(a,1) if a else 1)*10 + CN.get(b,0)
    return CN[s]

FILES = [HERE/'實登_五權西路一段167號.xls', HERE/'實登_五權西路一段169號.xls']
raw = []
for f in FILES:
    _, r = P.load(str(f)); raw += r
# 167／169 兩檔會把同一筆交易各列一次 → 以（日期, 總價, 總面積）去重
seen, rows0 = set(), []
for x in raw:
    k = (x['date'], x['tot'], x['area'])
    if k in seen: continue
    seen.add(k); rows0.append(x)
keep, drop = P.clean(rows0)
rows, MA, MV = P.recompute(keep)
for x in rows:
    x['bldg'] = '167' if '167' in x['addr'].translate(str.maketrans('０１２３４５６７８９','0123456789')) else '169'
    x['fl'] = x['fl'] or addr_floor(x['addr'])
    x['gross'] = x['tot']/x['area']
    x['split'] = bool(x['pkv_row'])
    x['wave'] = '首售' if x['yr'] <= 106 else '二手'

def med(v): return round(st.median(v), 2) if v else None
out = dict(撈取日='2026-10-04', 查詢區間='101/01–115/10', 原始筆數=len(raw), 重複筆數=len(raw)-len(rows0),
           排除=[dict(原因=w, 日期=x['date'], 樓層=x['fl']) for w, x in drop], 有效筆數=len(rows),
           車位=dict(每席面積中位=round(MA,2), 每席價格中位=round(MV,1)))
out['近三年'] = P.headline(rows, window=(113,115), name='富邦天空樹 近三年')
out['近五年'] = P.headline(rows, window=(111,115), name='富邦天空樹 近五年')
out['全期_參考'] = P.headline(rows, allow_full=True, name='富邦天空樹 全期')
out['首售_105-106'] = P.headline(rows, window=(105,106), name='首售期')
out['二手_107-115'] = P.headline(rows, window=(107,115), name='二手')
out['年度'] = [dict(年=y, n=len(g), 不含車中位=med([x['val'] for x in g]), 含車中位=med([x['gross'] for x in g]))
              for y in sorted({x['yr'] for x in rows}) for g in [[x for x in rows if x['yr']==y]]]
cuts = [(2,12,'低樓層 2–12F'),(13,25,'中樓層 13–25F'),(26,99,'高樓層 26–37F')]
out['樓層帶'] = []
for lo, hi, nm in cuts:
    d = dict(帶=nm)
    for w in ('首售','二手'):
        g = [x for x in rows if lo <= x['fl'] <= hi and x['wave']==w]
        d[w] = dict(n=len(g), 不含車中位=med([x['val'] for x in g]), 含車中位=med([x['gross'] for x in g]))
    g = [x for x in rows if lo <= x['fl'] <= hi]
    d['總價中位'] = round(st.median([x['tot'] for x in g])); d['坪數中位'] = round(st.median([x['area'] for x in g]),1)
    out['樓層帶'].append(d)
out['坪數_全樣本'] = dict(總面積中位=round(st.median([x['area'] for x in rows]),1),
                       扣車位面積中位=round(st.median([x['base'] for x in rows]),1))

import csv
with open(HERE/'transactions.csv','w',newline='',encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['交易日期','棟','樓層','總價萬','總面積坪','車位數','車位價萬','車位價來源','扣車位面積坪','含車單價','不含車單價','期別','備註'])
    for x in sorted(rows, key=lambda x: x['date'], reverse=True):
        w.writerow([x['date'], x['bldg'], x['fl'], x['tot'], x['area'], x['npark'],
                    x['pkv_row'] or round(sum(1 for _ in x['kinds'])*MV), '實登揭露' if x['split'] else '估算(坡道平面中位)',
                    round(x['base'],2), round(x['gross'],2), round(x['val'],2), x['wave'], x['note']])
json.dump(out, open(HERE/'summary.json','w'), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
