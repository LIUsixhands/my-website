"""大師特別座（南屯區大通街）買方報告 實登整理 — 讀小登南屯透天管線（108/01–115/10）。
口徑：透天以「總價÷建物總面積」與「總價÷土地面積」比較；本戶另列「房屋單價（已扣車位）」。
比較組：七期重劃區透天、屋齡 18–35 年、建物總面積 60–100 坪、112–115 年有效成交，逐筆列出、逐年中位，不跨年合併。
B1 坡道平面車位價：南屯透天實登揭露僅 3 筆（150–200 萬），本戶車位 3.899 坪偏小，取 150 萬保守估算。"""
import io, json, contextlib, runpy, statistics as st
from pathlib import Path
HERE = Path(__file__).parent
REF = HERE.parents[1] / '.claude/skills/skill-xiao-deng/references'

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    G = runpy.run_path(str(REF / '南屯透天分區行情.py'))
df = G['df']
v = df[df.excl == ''].copy()

def med(x): return round(st.median(x), 2) if len(x) else None
def row(r, tag=''):
    return dict(日期=r.date, 門牌=r.addr.replace('南屯區', ''), 社區=r.comm if isinstance(r.comm, str) else '—', 屋齡=int(r.age), 樓層=r.floors.replace('全/', ''),
                總價=round(r.total), 建坪=round(r.barea, 2), 地坪=round(r.larea, 2), 格局=r.layout, 車位=int(r.cnt.split('車位:')[1]) if '車位:' in r.cnt else 0,
                建坪單價=round(r.bp, 2), 土地單價=round(r.lp, 2), 標記=tag)

ASK, BAREA, LAREA, PKA, PKV = 3980, 73.904, 33.801, 3.899, 150
L = dict(門牌='臺中市南屯區大通街（大師特別座）', 開價=ASK, 建坪=BAREA, 主建物=50.941, 附屬=0.239, 雨遮=0.239, 共同=22.724, 車位面積=PKA,
         土地=LAREA, 格局='6房2廳3衛', 樓層='1–4F（地上 4 層）', 朝向='東', 屋齡=28.2, 車位='B1 坡道平面 1 席（編號 B1-25）', 管理費月=4066,
         登記日期='88/02/23', 物件編號='1039804', 用途='住家用', 小學='市立惠文國小', 國中='市立惠文高中附設國中', 車位估價=PKV)
L['扣車位面積'] = round(BAREA - PKA, 3)
L['總價除總坪'] = round(ASK / BAREA, 2)
L['房屋單價_扣車位'] = round((ASK - PKV) / L['扣車位面積'], 2)
L['土地單價'] = round(ASK / LAREA, 2)

# 本社區（大通街 83 號一帶、社區簡稱「大師特別座」）
comm = df[df.comm.fillna('').str.contains('大師特別座') | df.addr.str.contains('大通街８３')]
COMM = [row(r) | dict(排除=r.excl) for r in comm.sort_values('date').itertuples()]

# 同街廓：大通街、大川街、大觀路（惠義段）
blk = v[v.road2.isin(['大通街', '大川街', '大觀路']) & ~v.index.isin(comm.index)]
BLOCK = [row(r) for r in blk.sort_values('date').itertuples()]

# 七期同齡同坪數比較組（112–115）
c = v[(v.zone == '七期重劃區') & (v.year >= 112) & v.age.between(18, 35) & v.barea.between(60, 100) & ~v.index.isin(comm.index)]
# 單價達同年中位 1.8 倍以上者列出但不計入中位（如臨大馬路店面型、土地型交易）
ym = c.groupby('year').bp.median()
c = c.assign(odd=[r.bp >= ym[r.year] * 1.8 for r in c.itertuples()])
CMP = [row(r, ('同街廓' if r.road2 in ('大通街', '大川街', '大觀路') else '') + ('・單價異常不計' if r.odd else '')) for r in c.sort_values('date').itertuples()]
cs = c[~c.odd]
CMP_YEAR = [dict(年=int(y), n=len(g), 建坪單價中位=med(list(g.bp)), 土地單價中位=med(list(g.lp)), 總價中位=round(st.median(g.total)),
                 建坪中位=med(list(g.barea)), 地坪中位=med(list(g.larea))) for y, g in cs.groupby('year')]

# 七期透天全體與 21–30 年屋齡帶，逐年（108–115）
z7 = v[v.zone == '七期重劃區']
Z7_YEAR = []
for y in range(108, 116):
    g, a = z7[z7.year == y], z7[(z7.year == y) & (z7.ageband == '21~30年')]
    Z7_YEAR.append(dict(年=y, n=len(g), 建坪單價中位=med(list(g.bp)), 土地單價中位=med(list(g.lp)),
                        屋齡21_30_n=len(a), 屋齡21_30_建坪=med(list(a.bp)), 屋齡21_30_土地=med(list(a.lp))))

out = dict(撈取日='2026-10-24', 資料='內政部實價登錄・臺中市南屯區透天厝買賣 108/01–115/10（115 年成交登錄至 8 月）',
           本戶=L, 本社區=COMM, 同街廓=BLOCK, 比較組條件='七期重劃區・透天・屋齡 18–35 年・建物總面積 60–100 坪・112/01–115/10',
           比較組=CMP, 比較組逐年=CMP_YEAR, 七期逐年=Z7_YEAR)
json.dump(out, open(HERE / 'summary.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps({k: out[k] for k in ('本戶', '本社區', '比較組逐年', '七期逐年')}, ensure_ascii=False, indent=1))
print('同街廓', len(BLOCK), '比較組', len(CMP))
