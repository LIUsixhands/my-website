"""麗晨語山簷 FB 貼文圖（1080×1350，4:5）：社區歷年成交圖＋三個關鍵數字＋助哥聯絡。
不放建議成交價、不放本戶開價線（對象是社區屋主與買方）。"""
import json
from pathlib import Path

HERE = Path(__file__).parent
S = json.load(open(HERE / 'summary.json'))
TX, AF, PRE, PK = S['成交'], S['交屋後'], S['預售'], S['車位每席']
after = [r for r in TX if r['波段'] == '交屋後']
LO, HI = min(r['單價'] for r in after), max(r['單價'] for r in after)

W, H, Lm, R, T, B = 960, 560, 52, 170, 30, 58
X0, X1, YMIN, YMAX = 110.5, 115.9, 40, 82
def X(t): return Lm + (t - X0) * (W - Lm - R) / (X1 - X0)
def Y(v): return T + (YMAX - v) * (H - T - B) / (YMAX - YMIN)
def tt(d): y, m, _ = d.split('/'); return int(y) + (int(m) - .5) / 12
STY = {'A': ('#C8963E', 'A 戶 70 坪・4 房'), 'B': ('#9aa7b2', 'B 戶 63 坪・3 房'), 'C': ('#1F4E5F', 'C 戶 55 坪・3 房')}
svg = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK TC" font-size="17">']
for v in range(YMIN, YMAX + 1, 10):
    svg.append(f'<line x1="{Lm}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#e3e8ec"/>'
               f'<text x="{Lm-10}" y="{Y(v)+6:.1f}" text-anchor="end" fill="#7b8794">{v}</text>')
for y in range(111, 116):
    svg.append(f'<text x="{X(y):.1f}" y="{H-B+26}" text-anchor="middle" fill="#7b8794">{y} 年</text>')
xc = X(113 + 6.5 / 12)
svg.append(f'<line x1="{xc:.1f}" x2="{xc:.1f}" y1="{T}" y2="{H-B}" stroke="#9aa7b2" stroke-width="2"/>'
           f'<text x="{xc+8:.1f}" y="{T+16}" fill="#7b8794" font-size="15">113/07 使照・交屋</text>'
           f'<text x="{(Lm+xc)/2:.1f}" y="{T+16}" text-anchor="middle" fill="#7b8794" font-size="15">預售（建商首售）</text>')
y1, y2 = Y(HI), Y(LO)
svg.append(f'<rect x="{X(114.95):.1f}" y="{y1-8:.1f}" width="{X(115.65)-X(114.95):.1f}" height="{y2-y1+16:.1f}" rx="10" fill="#C0392B" opacity=".08"/>')
for r in TX:
    c, _ = STY[r['戶型']]
    svg.append(f'<circle cx="{X(tt(r["日期"])):.1f}" cy="{Y(r["單價"]):.1f}" r="7.5" fill="{c}" stroke="#fff" stroke-width="2"/>')
lab, last = [], None
for r in sorted(after, key=lambda r: -r['單價']):
    y = Y(r['單價']) + 6 if last is None else max(Y(r['單價']) + 6, last + 22)
    lab.append((r, y)); last = y
LX = W - R + 22
for r, y in lab:
    c, _ = STY[r['戶型']]
    svg.append(f'<line x1="{X(tt(r["日期"]))+8:.1f}" y1="{Y(r["單價"]):.1f}" x2="{LX-4}" y2="{y-6:.1f}" stroke="{c}" stroke-width="1.2"/>'
               f'<text x="{LX}" y="{y:.1f}" fill="{c}" font-weight="700">{r["戶型"]} {r["樓層"]}F {r["單價"]:.1f}</text>')
for i, k in enumerate('CAB'):
    c, name = STY[k]; lx = Lm + i * 240
    svg.append(f'<circle cx="{lx+9}" cy="{H-12}" r="8" fill="{c}"/><text x="{lx+24}" y="{H-6}" fill="#4a5560">{name}</text>')
svg.append('</svg>')
chart = ''.join(svg)

html = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ width: 1080px; height: 1350px; font-family: "Noto Sans CJK TC", sans-serif; background: #F7F9FA; color: #1e2a33; }}
.top {{ background: #163a47; color: #fff; padding: 46px 60px 38px; }}
.ey {{ font-size: 24px; letter-spacing: .3em; color: #E3B66A; }}
h1 {{ font-family: "Noto Serif CJK TC", serif; font-size: 62px; line-height: 1.25; margin-top: 14px; }}
h1 b {{ color: #F0D9A4; }}
.sub {{ font-size: 25px; color: #b9cad3; margin-top: 14px; line-height: 1.6; }}
.chart {{ padding: 26px 50px 0; }}
.unit {{ text-align: right; font-size: 17px; color: #7b8794; padding-right: 10px; }}
.kpi {{ display: flex; gap: 18px; padding: 18px 60px 0; }}
.kpi > div {{ flex: 1; background: #fff; border: 1px solid #dde4e9; border-top: 5px solid #C8963E; padding: 16px 8px; text-align: center; }}
.kpi .v {{ font-family: "Noto Serif CJK TC", serif; font-size: 44px; font-weight: 700; color: #163a47; line-height: 1.1; }}
.kpi .v small {{ font-size: 20px; color: #C8963E; margin-left: 4px; }}
.kpi .l {{ font-size: 19px; color: #5d6b76; margin-top: 6px; }}
.src {{ font-size: 15px; color: #8a96a0; padding: 14px 60px 0; line-height: 1.6; }}
.foot {{ position: absolute; left: 0; right: 0; bottom: 0; height: 140px; background: #163a47; display: flex; align-items: center; justify-content: space-between; padding: 0 60px; }}
.foot .n {{ font-family: "Noto Serif CJK TC", serif; font-size: 36px; font-weight: 700; color: #fff; }}
.foot .n span {{ color: #F0D9A4; }}
.foot .s {{ font-size: 18px; color: #b9cad3; margin-top: 4px; }}
.foot img {{ width: 96px; height: 96px; background: #fff; padding: 5px; border-radius: 4px; }}
</style></head><body>
<div class="top">
  <div class="ey">南七期・惠文學區｜麗晨語山簷</div>
  <h1>同一棟、同一年，<br>房屋單價差 <b>{HI - LO:.0f} 萬/坪</b></h1>
  <div class="sub">交屋後 {len(after)} 筆成交落在 {LO:.1f}–{HI:.1f} 萬/坪（已扣車位）。差在樓層、戶型、車位怎麼算。</div>
</div>
<div class="chart"><div class="unit">單位：萬元／坪（房屋單價，已扣車位）</div>{chart}</div>
<div class="kpi">
  <div><div class="v">{AF["net"]:.1f}<small>萬/坪</small></div><div class="l">交屋後中位（{AF["n"]} 筆）</div></div>
  <div><div class="v">{PRE["net"]:.1f}<small>萬/坪</small></div><div class="l">預售期中位（{PRE["n"]} 筆）</div></div>
  <div><div class="v">{PK["交屋後"][0]:.0f}–{PK["交屋後"][-1]:.0f}<small>萬</small></div><div class="l">交屋後車位每席</div></div>
</div>
<div class="src">資料：內政部實價登錄，社區「麗晨語山簷」101/01–115/10，住宅 {S["有效筆數"]} 筆（查詢 2026/10/16）。單價為中位數，僅供參考，不代表未來走勢。</div>
<div class="foot">
  <div><div class="n">助哥　<span>0925-313-570</span></div><div class="s">LINE @080akczk　｜　sixhands.tw</div><div class="s" style="font-size:16px">永慶不動產 七期河南市政店／百富國際開發有限公司</div></div>
  <img src="QR_LINE.png">
</div>
</body></html>'''
(HERE / 'FB_圖.html').write_text(html, encoding='utf-8')

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
    pg = b.new_page(viewport={'width': 1080, 'height': 1350})
    pg.goto((HERE / 'FB_圖.html').resolve().as_uri())
    pg.wait_for_timeout(500)
    pg.screenshot(path=str(HERE / 'FB_社區成交圖.png'))
    b.close()
print('→', HERE / 'FB_社區成交圖.png')
