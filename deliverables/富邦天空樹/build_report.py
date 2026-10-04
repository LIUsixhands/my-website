"""富邦天空樹 銷售報告書（給買方）：讀 transactions.csv → 產 HTML → Playwright 輸出 PDF。"""
import base64, json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
OUT_HTML = HERE / '富邦天空樹_銷售報告書.html'
OUT_PDF = HERE / '富邦天空樹_銷售報告書.pdf'

df = pd.read_csv(HERE / 'transactions.csv', dtype={'棟': str})
df['備註'] = df['備註'].fillna('')
S = json.load(open(HERE / 'summary.json'))
N3, N5, FS, SH, ALL = S['近三年'], S['近五年'], S['首售_105-106'], S['二手_107-115'], S['全期_參考']

def img(name):
    mime = 'image/png' if name.endswith('png') else 'image/jpeg'
    return f"data:{mime};base64,{base64.b64encode((HERE / name).read_bytes()).decode()}"

def f2(v):
    return '—' if pd.isna(v) else f'{v:.2f}'

def wan(v):
    return f'{v:,.0f}'

# ---------- 年度趨勢圖（實色、inline SVG） ----------
yr = pd.DataFrame(S['年度']).rename(columns={'不含車中位': '不含車', '含車中位': '含車', 'n': '筆數'})
W, H, L, R, T, B = 560, 236, 44, 16, 24, 34
xs = list(range(105, 116))
def X(y): return L + (y - 105) * (W - L - R) / 10
def Y(v): return T + (70 - v) * (H - T - B) / (70 - 38)
svg = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK TC" font-size="10">']
for v in range(40, 71, 5):
    svg.append(f'<line x1="{L}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#e6dcc6" stroke-width="1"/>'
               f'<text x="{L-6}" y="{Y(v)+3:.1f}" text-anchor="end" fill="#8a7d64">{v}</text>')
for y in xs:
    svg.append(f'<text x="{X(y):.1f}" y="{H-B+15}" text-anchor="middle" fill="#8a7d64">{y}</text>')
svg.append(f'<text x="{W-R}" y="{T-6}" text-anchor="end" fill="#8a7d64" font-size="9">X：民國年　Y：萬元/坪</text>')
# 首售期底色
svg.append(f'<rect x="{X(104.6):.1f}" y="{T}" width="{X(106.4)-X(104.6):.1f}" height="{H-T-B}" fill="#f3ead6"/>'
           f'<text x="{(X(104.6)+X(106.4))/2:.1f}" y="{T+12}" text-anchor="middle" fill="#9a7a3c" font-size="9">建商首售期</text>')
for col, color, dash in [('不含車', '#8B5E1A', ''), ('含車', '#C9A055', '5 3')]:
    pts = [(r['年'], r[col]) for _, r in yr.iterrows() if pd.notna(r[col])]
    path = ' '.join(f'{"M" if i == 0 else "L"}{X(y):.1f},{Y(v):.1f}' for i, (y, v) in enumerate(pts))
    svg.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.2" stroke-dasharray="{dash}"/>')
    for y, v in pts:
        svg.append(f'<circle cx="{X(y):.1f}" cy="{Y(v):.1f}" r="3.4" fill="{color}"/>'
                   f'<text x="{X(y):.1f}" y="{Y(v) - 7:.1f}" text-anchor="middle" fill="{color}" font-size="9" font-weight="700">{v:.1f}</text>')
for _, r in yr.iterrows():
    svg.append(f'<text x="{X(r["年"]):.1f}" y="{H-B+27}" text-anchor="middle" fill="#b0a184" font-size="8">n={int(r["筆數"])}</text>')
svg.append('</svg>')
chart = ''.join(svg)

# ---------- 樓層分區（中位數） ----------
tier_rows = ''
for t in S['樓層帶']:
    a, b = t['首售'], t['二手']
    tier_rows += (f'<tr><td>{t["帶"]}</td><td class="num">{a["n"]}</td><td class="num">{a["含車中位"]:.2f}</td>'
                  f'<td class="num b">{a["不含車中位"]:.2f}</td><td class="num">{b["n"]}</td>'
                  f'<td class="num">{b["含車中位"]:.2f}</td><td class="num b">{b["不含車中位"]:.2f}</td>'
                  f'<td class="num">{wan(t["總價中位"])}</td></tr>')

# ---------- 二手成交明細 ----------
sec = df[df['期別'] == '二手'].sort_values('交易日期', ascending=False)
sec_rows = ''
for i, r in enumerate(sec.itertuples()):
    est = r.車位價來源 != '實登揭露'
    note = '；'.join(n for n in ['毛胚屋' if '毛胚' in r.備註 else '', '車位未拆價，以每席 150 萬估' if est else ''] if n)
    cls = ' class="hl"' if i < 2 else ''
    sec_rows += (f'<tr{cls}><td>{r.交易日期}</td><td>{r.棟}號 {r.樓層}F</td><td class="num">{wan(r.總價萬)}</td>'
                 f'<td class="num">{r.總面積坪:.2f}</td><td class="num">{r.車位數}</td>'
                 f'<td class="num">{wan(r.車位價萬)}{"*" if est else ""}</td>'
                 f'<td class="num b">{r.含車單價:.2f}</td><td class="num b">{r.不含車單價:.2f}{"*" if est else ""}</td><td>{note}</td></tr>')

# ---------- 同戶前後成交 ----------
rep_rows = ''
for (b, fl), g in df.groupby(['棟', '樓層']):
    if len(g) < 2: continue
    g = g.sort_values('交易日期')
    path = ' → '.join(f'{r.交易日期}　{wan(r.總價萬)}萬（含車 {r.含車單價:.1f}／不含車 {r.不含車單價:.1f}{"*" if r.車位價來源 != "實登揭露" else ""}）' for r in g.itertuples())
    chg = (g.總價萬.iloc[-1] / g.總價萬.iloc[0] - 1) * 100
    rep_rows += f'<tr><td>{b}號 {fl}F</td><td>{path}</td><td class="num b">{chg:+.1f}%</td></tr>'

DISC = '永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號'
def foot(n):
    return f'<div class="foot"><span>{DISC}</span><span>富邦天空樹 銷售報告書　{n}</span></div>'

# 試算：典型 240 坪、3 車位（約 33 坪、450 萬）
main_area = 240 - 33
lo, hi = main_area * 53 + 450, main_area * 57 + 450

html = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>富邦天空樹 銷售報告書</title><style>
@page {{ size: A4; margin: 0; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: "Noto Sans CJK TC", sans-serif; color: #2b2418; -webkit-print-color-adjust: exact; print-color-adjust: exact; background: #ddd; }}
.page {{ width: 210mm; height: 297mm; position: relative; overflow: hidden; page-break-after: always; background: #FBF7EE; margin: 0 auto; }}
.page:last-child {{ page-break-after: auto; }}
h1, h2, h3, .serif {{ font-family: "Noto Serif CJK TC", serif; }}
.pad {{ padding: 15mm 15mm 0 15mm; }}
.eyebrow {{ font-size: 7.6pt; letter-spacing: .45em; color: #A47A35; margin-bottom: 2mm; }}
.ttl {{ font-family: "Noto Serif CJK TC", serif; font-size: 19pt; color: #3a2c12; font-weight: 700; border-left: 5px solid #B8893E; padding-left: 9px; margin-bottom: 3mm; }}
.sub {{ font-size: 8.8pt; color: #75684f; margin-bottom: 5mm; line-height: 1.7; }}
table {{ width: 100%; border-collapse: collapse; font-size: 8.3pt; }}
th {{ background: #5A4318; color: #FBF7EE; padding: 4.5px 6px; text-align: left; font-weight: 500; font-size: 8pt; }}
td {{ padding: 4.5px 6px; border-bottom: 1px solid #e8dfcb; vertical-align: top; }}
tr:nth-child(even) td {{ background: #f5eedd; }}
tr.hl td {{ background: #B8893E !important; color: #fff; }}
tr.ex td {{ color: #a9a090; text-decoration: line-through; }}
.num {{ font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }}
.b {{ font-weight: 700; }}
.g {{ color: #A47A35; }}
.foot {{ position: absolute; bottom: 0; left: 0; right: 0; height: 11mm; background: #3a2c12; color: #d9c9a3; font-size: 6.6pt; display: flex; align-items: center; justify-content: space-between; padding: 0 15mm; }}
.kpi {{ display: flex; gap: 3.5mm; margin-bottom: 5mm; }}
.kpi > div {{ flex: 1; background: #fff; border: 1px solid #e6dcc6; border-top: 3px solid #B8893E; padding: 3.5mm 2mm; text-align: center; }}
.kpi .v {{ font-family: "Noto Serif CJK TC", serif; font-size: 19pt; color: #3a2c12; font-weight: 700; line-height: 1.1; }}
.kpi .u {{ font-size: 7.6pt; color: #A47A35; }}
.kpi .l {{ font-size: 7.2pt; color: #7d7058; margin-top: 1.5mm; }}
.note {{ background: #f7ecd4; border-left: 4px solid #B8893E; padding: 3.5mm 4.5mm; font-size: 8.3pt; line-height: 1.75; }}
.warn {{ background: #fbeceb; border-left: 4px solid #a8382e; padding: 3.5mm 4.5mm; font-size: 8.3pt; line-height: 1.75; }}
.feat {{ display: flex; gap: 4mm; margin-bottom: 4.5mm; }}
.feat .no {{ font-family: "Noto Serif CJK TC", serif; font-size: 24pt; color: #C9A055; line-height: 1; min-width: 12mm; }}
.feat h3 {{ font-size: 12pt; color: #3a2c12; margin-bottom: 1.5mm; }}
.feat p, .feat li {{ font-size: 8.7pt; line-height: 1.8; color: #3d3423; }}
ul {{ margin-left: 4.5mm; }} li {{ font-size: 8.5pt; line-height: 1.8; margin-bottom: .6mm; }}
.photo {{ background: #efe5cf; padding: 2mm; border-radius: 2px; }}
.photo img {{ display: block; width: 100%; object-fit: contain; }}
.cap {{ font-size: 7pt; color: #8a7d64; margin-top: 1.2mm; }}
.spec td:first-child {{ color: #8a6a2c; width: 26mm; white-space: nowrap; }}
.spec td {{ background: transparent !important; padding: 3.6px 4px; font-size: 8.4pt; }}
.chip {{ display: inline-block; border: 1px solid #C9A055; color: #8B5E1A; font-size: 7.4pt; padding: .5mm 2.2mm; border-radius: 10px; margin: 0 1.2mm 1.2mm 0; }}
</style></head><body>

<!-- P1 封面 -->
<div class="page" style="background:#2e2410">
  <img src="{img('外觀_全景.jpg')}" style="position:absolute;right:0;top:0;width:112mm;height:297mm;object-fit:cover;object-position:center">
  <div style="position:absolute;left:98mm;top:0;width:14mm;height:297mm;background:linear-gradient(90deg,#2e2410,rgba(46,36,16,0))"></div>
  <div style="position:absolute;left:14mm;top:30mm;width:80mm;color:#FBF7EE">
    <div style="font-size:8pt;letter-spacing:.5em;color:#D8B26A">PROPERTY SALES REPORT</div>
    <div style="width:46mm;height:2px;background:#D8B26A;margin:6mm 0 9mm"></div>
    <div style="font-size:11pt;color:#D8B26A;letter-spacing:.2em" class="serif">國美館特區 · 伊東豊雄有機建築</div>
    <h1 style="font-size:40pt;line-height:1.2;margin-top:3mm">富邦<br>天空樹</h1>
    <div style="font-size:15pt;margin-top:5mm" class="serif">買方銷售報告書</div>
    <div style="font-size:8.8pt;color:#cdbf9f;margin-top:5mm;line-height:1.9">臺中市西區五權西路一段 167／169 號<br>39 層 · 72 戶 · 2,755 坪基地 · 私人森林庭園</div>
    <div style="margin-top:16mm;border-top:1px solid #6b5a33;padding-top:6mm;width:80mm">
      <div style="font-size:7.6pt;color:#D8B26A;letter-spacing:.3em">核心結論</div>
      <div style="font-size:9.6pt;line-height:1.9;margin-top:2.5mm">
        近三年（113–115）成交中位：<b>不含車 {N3['net']:.1f}</b> 萬／坪、<b>含車 {N3['gross']:.1f}</b> 萬／坪（{N3['n']} 筆）。<br>
        首售期（105–106）中位為 不含車 {FS['net']:.1f}／含車 {FS['gross']:.1f} 萬。<br>
        <span style="color:#D8B26A">用比首購者更低的單價，買進同一座森林。</span>
      </div>
    </div>
  </div>
  <div style="position:absolute;left:14mm;bottom:9mm;font-size:6.2pt;color:#a8987a;width:80mm;line-height:1.7">資料基準：內政部實價登錄 101/01–115/10（查詢 2026-10-04）<br>{DISC}</div>
</div>

<!-- P2 建案檔案 -->
<div class="page"><div class="pad">
  <div class="eyebrow">01 · PROFILE</div>
  <div class="ttl">建案檔案</div>
  <div class="sub">由國際建築大師伊東豊雄操刀、日本竹中工務店擔任營造顧問的超高層住宅；72 戶、每層僅兩戶，以 2,755 坪基地換來低建蔽與大面積自然覆土。</div>
  <div style="display:flex;gap:6mm">
    <div style="flex:1.15">
      <table class="spec">
        <tr><td>地址</td><td>臺中市西區五權西路一段 167、169 號</td></tr>
        <tr><td>區位</td><td>國美館特區（西區，非七期）</td></tr>
        <tr><td>屋齡</td><td>約 10 年（105/08 建築完成）</td></tr>
        <tr><td>使用分區</td><td>商1、住2</td></tr>
        <tr><td>基地面積</td><td>9,108 ㎡ ≒ 2,755 坪</td></tr>
        <tr><td>建築面積</td><td>1,605 ㎡（約佔基地 17.6%）</td></tr>
        <tr><td>總樓地板</td><td>52,279 ㎡</td></tr>
        <tr><td>樓層</td><td>4B / 39F / 3PH，高 173.1 m</td></tr>
        <tr><td>總戶數</td><td>72 戶（每層 2 戶）</td></tr>
        <tr><td>公設比</td><td>33.01%</td></tr>
        <tr><td>結構</td><td>地下層 SRC、地上層 SS 鋼骨造</td></tr>
        <tr><td>格局坪數</td><td>4 房以上，約 200–290 坪（含車位）</td></tr>
        <tr><td>車位</td><td>坡道平面 236 位，多數戶配 3–5 位</td></tr>
        <tr><td>國小學區</td><td>大勇國小（雙語）</td></tr>
        <tr><td>國中學區</td><td>崇倫國中（雙語）、向上國中</td></tr>
        <tr><td>建設公司</td><td>富邦建設</td></tr>
        <tr><td>建築設計</td><td>伊東豊雄建築設計事務所</td></tr>
        <tr><td>建築師</td><td>薛昭信 HOY 建築師事務所、邱文傑建築師事務所</td></tr>
        <tr><td>營造</td><td>互助營造；營造顧問：日本竹中工務店</td></tr>
        <tr><td>景觀</td><td>木荷景觀工程有限公司</td></tr>
      </table>
      <div class="cap" style="margin-top:2mm">註：雙語學區依各縣市政府教育局處資料，入學資格請以當年度公告為準。</div>
    </div>
    <div style="flex:.85">
      <div class="photo"><img src="{img('外觀_仰視.jpg')}" style="height:150mm;object-fit:cover"></div>
      <div class="cap">曲面帷幕層層外展，下窄上寬的「大樹」量體</div>
    </div>
  </div>
  <div style="margin-top:5mm">
    <span class="chip">伊東豊雄 有機住宅首作</span><span class="chip">竹中工務店 營造顧問</span><span class="chip">鋼骨結構</span><span class="chip">近 300 棵大樹</span><span class="chip">400 坪生態水池</span><span class="chip">雙語學區</span>
  </div>
</div>{foot(2)}</div>

<!-- P3 建築特色 -->
<div class="page"><div class="pad">
  <div class="eyebrow">02 · ARCHITECTURE</div>
  <div class="ttl">有機建築・仿生之美</div>
  <div class="sub">在充斥水泥量體的都市叢林裡，種下一棵巍然聳立的樹——伊東豊雄將住宅與大自然結合的首次實踐。</div>
  <div style="display:flex;gap:6mm">
    <div style="flex:1">
      <div class="feat"><div class="no">01</div><div><h3>像大樹一樣向天空展開</h3>
        <p>建築外觀由連續性的曲面逐漸往上擴張延伸，以高聳入雲的大樹為靈感，呈現<b>下窄上寬</b>的造型。外觀以石材與玻璃帷幕鋪陳，呼應周圍環境。</p></div></div>
      <div class="feat"><div class="no">02</div><div><h3>每一層都在轉動</h3>
        <p>每個樓層都帶有巧妙的角度變化，以有節奏的曲面波浪般展開，躍動感隨高度延伸，如同枝葉在高空向外生展，也讓<b>每戶的光照面積達到最大化</b>。</p></div></div>
      <div class="feat"><div class="no">03</div><div><h3>枝幹般的不規則突出</h3>
        <p>建築整體刻意安排的不規則突出，象徵樹木分枝，讓整座量體更添有機仿生感，充滿生命能量。</p></div></div>
    </div>
    <div style="width:62mm"><div class="photo"><img src="{img('外觀_全景.jpg')}" style="height:76mm;object-fit:cover"></div>
      <div class="cap">基地前方即為社區森林與生態水池</div></div>
  </div>
  <div style="margin-top:4mm;background:#fff;border:1px solid #e6dcc6;border-top:3px solid #B8893E;padding:5mm 6mm">
    <h3 style="font-size:12.5pt;color:#3a2c12;margin-bottom:2.5mm">看不見的地方，才是品質的底氣</h3>
    <ul>
      <li><b>鋼骨結構</b>，採<b>雙順打工法</b>與 <b>ACEUP 鋼骨吊裝工法</b>，縮短工期同時提升精度。</li>
      <li>精準計算<b>內凹弧形帷幕曲線</b>，以外環樑與帷幕單元間的精工處理，展現自然曲面與向上的大樹姿態。</li>
      <li><b>42 個月如期如質完工</b>；BIM 技術運用是一大功臣。</li>
      <li>假設工程專業規劃：遮斷層減少危害因子、斷水層擴展工作面、無外鷹架樓板施工推架、DECK 樓板一次 3 層 RC 的下支撐 H 鋼墊樑、大型塔吊適時換小型吊車。</li>
      <li>因外牆線變化不一，<b>堅持施工電梯留設室內</b>，外牆方能完整閉合——對日後防水與帷幕完整性是加分。</li>
    </ul>
  </div>
  <div class="note" style="margin-top:4mm">買方觀點：曲面帷幕與鋼骨超高層的施工門檻很高，同區不易再出現同等級的作品。這類「建築師作品型」住宅，價值不只在坪數，也在<b>不可複製性</b>。</div>
</div>{foot(3)}</div>

<!-- P4 森林庭園 -->
<div class="page"><div class="pad">
  <div class="eyebrow">03 · LANDSCAPE</div>
  <div class="ttl">夢寐以求的森林庭園</div>
  <div class="sub">建築只佔基地約 17.6%，把其餘的土地留給樹。國美館特區裡的一座私人森林。</div>
  <div class="photo"><img src="{img('配置圖_森林庭園.jpg')}" style="height:66mm"></div>
  <div class="cap">全區配置：左側塔樓、右側 400 坪生態水池與環湖步道</div>
  <div class="kpi" style="margin-top:5mm">
    <div><div class="v">~300<span class="u"> 棵</span></div><div class="l">園內種植大樹</div></div>
    <div><div class="v">400<span class="u"> 坪</span></div><div class="l">生態水池＋環湖步道</div></div>
    <div><div class="v">~40<span class="u"> %</span></div><div class="l">地下室佔基地比例</div></div>
    <div><div class="v">17.6<span class="u"> %</span></div><div class="l">建築面積／基地面積</div></div>
  </div>
  <div style="display:flex;gap:5mm">
    <div style="flex:1">
      <div class="feat"><div class="no">04</div><div><h3>樹是真的種在土裡</h3>
        <p>景觀由木荷景觀工程有限公司操刀。與一般社區「挖樹穴植樹」不同，天空樹的<b>地下室只佔基地面積約四成</b>，其餘都是能讓樹木深深扎根的自然覆土——大樹不受人造空間限制，能自然生長，看得見歲月與四季的變化。</p></div></div>
      <div class="feat"><div class="no">05</div><div><h3>回家就是公園</h3>
        <p>住戶每日閒散小憩的獨家花園：微風吹拂、樹梢搖曳；大面積綠地與水池，更真正有調節社區<b>「微氣候」</b>的功能。</p></div></div>
    </div>
    <div style="flex:1">
      <div class="feat"><div class="no">06</div><div><h3>真正會呼吸的住宅</h3>
        <p>透過精密規劃的旋轉角度，各樓層外周都有<b>縱深足夠的大露台</b>與出挑陽台，有效遮陽、避免強烈直射，讓室內維持舒適溫度。</p>
        <p style="margin-top:1.5mm">建築體包覆的<b>格柵玻璃帷幕</b>，減緩高樓特有的強風侵入，創造能與室內結合、穩定的戶外場域。一吐一納，與自然環境緊密結合——這是富邦建設與伊東豊雄共同堅持的「與自然結合」。</p></div></div>
    </div>
  </div>
</div>{foot(4)}</div>

<!-- P5 行情 -->
<div class="page"><div class="pad">
  <div class="eyebrow">04 · MARKET</div>
  <div class="ttl">社區行情：含車 vs 不含車</div>
  <div class="sub">資料：內政部實價登錄，五權西路一段 167、169 號，101/01–115/10。兩門牌檔共 {S['原始筆數']} 筆，去除兩檔重複列出 {S['重複筆數']} 筆、排除親友／特殊關係交易 {len(S['排除'])} 筆，有效 <b>{S['有效筆數']}</b> 筆。以下單價一律為<b>中位數</b>。</div>
  <div class="kpi">
    <div><div class="v">{N3['net']:.1f}</div><div class="l">近三年 不含車中位<br>萬／坪（{N3['n']} 筆）</div></div>
    <div><div class="v">{N3['gross']:.1f}</div><div class="l">近三年 含車中位<br>萬／坪（{N3['n']} 筆）</div></div>
    <div style="border-top-color:#8B5E1A"><div class="v">{FS['net']:.1f}</div><div class="l">首售期 不含車中位<br>萬／坪（105–106，{FS['n']} 筆）</div></div>
    <div style="border-top-color:#8B5E1A"><div class="v">{FS['gross']:.1f}</div><div class="l">首售期 含車中位<br>萬／坪（105–106，{FS['n']} 筆）</div></div>
  </div>
  <div style="background:#fff;border:1px solid #e6dcc6;padding:3mm 3mm 1mm">
    <div style="font-size:9pt;font-weight:700;color:#3a2c12;margin:0 0 1mm 2mm">年度成交單價走勢（中位數）
      <span style="font-weight:400;font-size:7.6pt;color:#8B5E1A;margin-left:4mm">━ 不含車</span>
      <span style="font-weight:400;font-size:7.6pt;color:#C9A055;margin-left:3mm">╍ 含車</span></div>
    {chart}
  </div>
  <div class="cap">⚠ 近三年僅 {N3['n']} 筆成交，行情帶寬較寬，議價前請逐戶核對。112、113 年各 1 筆車位未拆價，不含車單價以坡道平面車位每席中位 150 萬估算；113 年該筆為毛胚屋、112 年該筆為 5 房 4 衛。年度筆數標於年份下方。</div>
  <div style="margin-top:4mm"><table>
    <tr><th>樓層區段</th><th class="num">首售筆數</th><th class="num">首售 含車中位</th><th class="num">首售 不含車中位</th><th class="num">二手筆數</th><th class="num">二手 含車中位</th><th class="num">二手 不含車中位</th><th class="num">總價中位(萬)</th></tr>
    {tier_rows}
  </table></div>
  <div class="note" style="margin-top:4mm">
    <b>單價怎麼看？</b>　<b>含車單價</b>＝總價 ÷ 總面積（車位坪數一起攤）；<b>不含車單價</b>＝(總價 − 車位價) ÷ (總面積 − 車位面積)，也就是實價登錄網站顯示的單價。本社區每戶多配 3 個坡道平面車位（實登揭露每席中位 {S['車位']['每席價格中位']:.0f} 萬），近三年兩種口徑差約 {N3['gross']:.1f} → {N3['net']:.1f}（{N3['gap_pct']:+.1f}%），比價時務必用同一口徑。車位未拆價者以每席中位估算，表中以 * 標示。
  </div>
</div>{foot(5)}</div>

<!-- P6 成交明細 -->
<div class="page"><div class="pad">
  <div class="eyebrow">05 · TRANSACTIONS</div>
  <div class="ttl">二手成交明細（107 年後）</div>
  <div class="sub">金色列為最新兩筆成交；* 為車位未拆價、以每席 150 萬估算。已排除特殊關係交易 1 筆（108/12）。單價單位：萬元／坪；總價、車位價單位：萬元。</div>
  <table>
    <tr><th>交易日</th><th>門牌樓層</th><th class="num">總價</th><th class="num">總面積(坪)</th><th class="num">車位數</th><th class="num">車位價</th><th class="num">含車單價</th><th class="num">不含車單價</th><th>註記</th></tr>
    {sec_rows}
  </table>
  <div class="ttl" style="font-size:13pt;margin-top:6mm">同一戶的前後成交</div>
  <table>
    <tr><th style="width:20mm">戶別</th><th>成交軌跡（總價｜單價 萬/坪）</th><th class="num">總價變動</th></tr>
    {rep_rows}
  </table>
  <div class="cap" style="margin-top:2mm">169 號 8F 112 年成交為 5 房 4 衛格局、車位未拆價，與 106 年首售條件不同，漲幅不宜直接類推。</div>
</div>{foot(6)}</div>

<!-- P7 價格解讀 -->
<div class="page"><div class="pad">
  <div class="eyebrow">06 · BUYER'S VIEW</div>
  <div class="ttl">給買方的價格解讀</div>
  <div class="sub">把行情轉成你出價時用得到的數字。</div>
  <div style="display:flex;gap:5mm">
    <div style="flex:1" class="note">
      <div class="b" style="font-size:10pt;margin-bottom:1.5mm">① 現在的價格，低於首購者</div>
      105–106 年建商首售 {FS['n']} 筆，不含車中位 <b>{FS['net']:.1f}</b> 萬（含車 {FS['gross']:.1f}）。最近兩筆成交（114/09、115/04）不含車 <b>52.97、53.40</b> 萬，含車 47.7、48.5 萬。169 號 30F 同一戶，從 106 年 14,318 萬到 114 年 11,800 萬，約 <b>−17.6%</b>。
    </div>
    <div style="flex:1" class="note">
      <div class="b" style="font-size:10pt;margin-bottom:1.5mm">② 樓層價差明顯</div>
      高樓層（26F 以上）不含車中位：首售 {S['樓層帶'][2]['首售']['不含車中位']:.1f} 萬、二手 {S['樓層帶'][2]['二手']['不含車中位']:.1f} 萬，高於中低樓層。看的是哪一層，比價時就要對照同一區段。
    </div>
  </div>
  <div class="ttl" style="font-size:13pt;margin-top:6mm">近期成交帶試算（以典型戶為例）</div>
  <table>
    <tr><th>假設條件</th><th class="num">不含車 53 萬</th><th class="num">不含車 57 萬</th></tr>
    <tr><td>總面積 240 坪，含 3 車位（約 33 坪、450 萬），主＋附＋公設 207 坪</td><td class="num b">{wan(lo)} 萬</td><td class="num b">{wan(hi)} 萬</td></tr>
    <tr><td>換算含車單價</td><td class="num">{lo/240:.1f} 萬／坪</td><td class="num">{hi/240:.1f} 萬／坪</td></tr>
  </table>
  <div class="cap" style="margin-top:1.5mm">53 萬≈近三年不含車中位（{N3['net']:.1f}）；57 萬≈107 年後二手全期中位（{SH['net']:.1f}）；實際應依樓層、座向、裝修、車位數個別調整。這是試算，不是估價。</div>

  <div class="ttl" style="font-size:13pt;margin-top:6mm">租金報酬率試算（情境）</div>
  <table>
    <tr><th>情境月租（假設值）</th><th class="num">年租金</th><th class="num">購入總價 12,000 萬的毛報酬率</th></tr>
    <tr><td>12 萬／月</td><td class="num">144 萬</td><td class="num">1.20%</td></tr>
    <tr><td>15 萬／月</td><td class="num">180 萬</td><td class="num">1.50%</td></tr>
    <tr><td>18 萬／月</td><td class="num">216 萬</td><td class="num">1.80%</td></tr>
  </table>
  <div class="cap" style="margin-top:1.5mm">月租金為假設情境，非本社區實際租金數據；未扣管理費、房屋稅、地價稅、保險與空置期。實際請以租賃實價登錄或現行租約確認。</div>
  <div class="note" style="margin-top:4mm">結論：天空樹是<b>自住型頂級產品</b>，租金收益率低，購買理由應是居住品質、建築稀缺性與森林環境，而不是收租。</div>
</div>{foot(7)}</div>

<!-- P8 誠實揭露 + 免責 -->
<div class="page"><div class="pad">
  <div class="eyebrow">07 · DISCLOSURE</div>
  <div class="ttl">誠實揭露：購買前請一併評估</div>
  <div class="warn">
    <ul>
      <li><b>價格曾經回檔：</b>近期成交單價低於 106 年首售，代表首購者多數帳面虧損。這對新買方是進場機會，但也說明此產品價格不是只漲不跌。</li>
      <li><b>流通量少：</b>110 年後每年僅約 1–2 筆成交，未來轉手可能需要較長時間，議價空間也較難從成交數據判斷。</li>
      <li><b>公設比 33.01%：</b>主建物佔比約六成；比價時請一併比較主建物坪數與陽台／露台面積。</li>
      <li><b>部分成交車位未拆價：</b>這些案件無法計算不含車單價，已在表中標註並排除於不含車平均。</li>
      <li><b>管理費與修繕：</b>大面積景觀、水池與帷幕維護成本較高，管理費標準、公基金與帷幕維修計畫請向管委會確認。</li>
      <li><b>學區：</b>雙語學區資訊依教育局處資料，學籍與入學資格以學校當年度公告為準。</li>
      <li><b>區位：</b>本案位於西區國美館特區，非七期重劃區，與七期行情不宜直接比較。</li>
    </ul>
  </div>
  <div class="ttl" style="font-size:13pt;margin-top:7mm">資料來源與方法</div>
  <ul>
    <li>成交資料：內政部不動產交易實價查詢服務網，五權西路一段 167 號、169 號，101 年 1 月至 115 年 10 月，查詢時間 2026-10-04。</li>
    <li>清洗規則：兩門牌檔同一筆交易重複列出者去重（{S['重複筆數']} 筆）；備註含親友、員工、共有人、特殊關係者排除（{len(S['排除'])} 筆）。</li>
    <li>統計：一律採<b>中位數</b>；行情以<b>近三年（113–115）</b>為準，首售期與全期僅作脈絡參考。車位未拆價者，以同類別（坡道平面）每席中位 {S['車位']['每席價格中位']:.0f} 萬、逐案件車位面積扣除。</li>
    <li>含車單價＝總價 ÷ 總面積；不含車單價＝(總價 − 車位價) ÷ (總面積 − 車位面積)。</li>
    <li>建案資料與特色說明：建設公司及設計團隊公開資料、經紀人整理；圖片為建案外觀與配置示意。</li>
  </ul>
  <div style="margin-top:10mm;position:relative;background:#fff;border:1px solid #e6dcc6;padding:6mm 38mm 6mm 7mm;font-size:8pt;line-height:1.85;color:#55493a">
    <div class="b" style="font-size:10pt;color:#3a2c12;margin-bottom:2mm">免責聲明</div>
    本報告書為不動產經紀業務之行銷參考資料，非不動產估價師出具之估價報告。報告中之行情統計、試算與情境分析，係依公開實價登錄資料整理，不構成任何價格保證、投資建議或獲利承諾。實際交易價格、面積、車位、產權及使用現況，以權狀、謄本、不動產說明書及買賣契約記載為準。建案特色說明引用公開資料，實際設施以現況為準。買方應自行或委託專業人士查證後再做決定。
    <div style="position:absolute;right:8mm;top:50%;margin-top:-12mm;width:24mm;height:24mm;border:2.5px solid #b3261e;border-radius:50%;color:#b3261e;display:flex;align-items:center;justify-content:center;text-align:center;font-family:'Noto Serif CJK TC',serif;font-size:8.4pt;font-weight:700;line-height:1.3;transform:rotate(-12deg)">僅供<br>參考</div>
  </div>
  <div style="margin-top:8mm;text-align:center;font-size:9pt;color:#3a2c12" class="serif">永慶不動產 七期河南市政店　｜　劉力助</div>
</div>{foot(8)}</div>

</body></html>'''

OUT_HTML.write_text(html, encoding='utf-8')
print('HTML →', OUT_HTML)

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
    pg = b.new_page()
    pg.goto(OUT_HTML.resolve().as_uri())
    pg.wait_for_timeout(500)
    pg.pdf(path=str(OUT_PDF), prefer_css_page_size=True, print_background=True)
    b.close()
print('PDF  →', OUT_PDF)
