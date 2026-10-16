"""麗晨語山簷 行情分析頁 → blog/qiqi-lichen-yushanyan.html
版型沿用 blog/qiqi-price-2026.html（head 樣式、nav、footer 原樣取用），內容讀 summary.json。"""
import json, re
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
TPL = (ROOT / 'blog/qiqi-price-2026.html').read_text(encoding='utf-8')
OUT = ROOT / 'blog/qiqi-lichen-yushanyan.html'
S = json.load(open(HERE / 'summary.json'))
L, TX, AF, PRE, H3, TY, PK = S['本戶'], S['成交'], S['交屋後'], S['預售'], S['近三年'], S['戶型'], S['車位每席']
SLUG = 'qiqi-lichen-yushanyan.html'
URL = f'https://sixhands-studio.netlify.app/blog/{SLUG}'
DATE = '2026-10-16'
TITLE = f'麗晨語山簷行情分析：交屋後房屋單價 {AF["net"]:.1f} 萬、三種戶型怎麼比'
DESC = (f'南七期惠文學區「麗晨語山簷」實價登錄全解析：35 筆住宅成交，預售中位 {PRE["net"]:.1f}、115 年交屋後中位 {AF["net"]:.1f} 萬/坪（已扣車位），'
        f'車位每席約 {PK["交屋後中位"]:.0f} 萬，A／B／C 三種戶型與空中三合院建築一次看。')
IMG = 'https://sixhands-studio.netlify.app/photos/lichen-exterior.jpg'

def wan(v): return f'{v:,.0f}'

# ---------- head：換標題、描述、網址、結構化資料 ----------
head = TPL.split('</style>')[0] + '''
.ph{margin:26px 0;border-radius:14px;overflow:hidden;border:1px solid rgba(216,188,126,.22)}
.ph img{width:100%;height:auto}
.ph figcaption{font-size:12.5px;color:#9fb09f;padding:8px 12px;background:rgba(255,255,255,.03)}
.ph2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:26px 0}
.ph2 .ph{margin:0}
@media(max-width:600px){.ph2{grid-template-columns:1fr}}
.tbl{width:100%;border-collapse:collapse;margin:18px 0 24px;font-size:14px;color:#D7E0D6}
.tbl th{background:rgba(216,188,126,.16);color:var(--brass-lite);font-weight:700;padding:9px 8px;text-align:left;font-size:13px}
.tbl td{padding:8px;border-bottom:1px solid rgba(216,188,126,.12)}
.tbl td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.tbl tr.hl td{background:rgba(192,57,43,.28);color:#fff}
.tblw{overflow-x:auto}
.chart{background:rgba(255,255,255,.03);border:1px solid rgba(216,188,126,.22);border-radius:14px;padding:12px;margin:22px 0}
.listing{background:linear-gradient(180deg,#24402f,#1b3125);border:1px solid var(--brass);border-radius:16px;padding:26px;margin:40px 0}
.listing .tag{display:inline-block;background:var(--brass);color:#fff;font-size:12px;font-weight:700;letter-spacing:.12em;padding:4px 12px;border-radius:99px;margin-bottom:12px}
.listing h3{font-size:22px;color:var(--cream);margin-bottom:10px}
.listing .lic{font-size:12px;color:#9fb09f;margin-top:14px}
.yt{position:relative;width:100%;max-width:340px;aspect-ratio:9/16;margin:20px auto;border-radius:14px;overflow:hidden;border:1px solid rgba(216,188,126,.3)}
.yt iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
</style>
</head>'''
head = head.replace(TPL[TPL.index('<title>'):TPL.index('</title>') + 8], f'<title>{TITLE}｜Sixhands Studio</title>')
head = re.sub(r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{DESC}">', head)
head = re.sub(r'<meta name="keywords" content="[^"]*">', '<meta name="keywords" content="麗晨語山簷,語山簷,麗晨建設,七期房價,南七期,惠文學區,大業路,實價登錄,南屯區新成屋">', head)
head = head.replace('https://sixhands-studio.netlify.app/blog/qiqi-price-2026.html', URL)
head = head.replace('2026-07-19', DATE).replace('https://sixhands-studio.netlify.app/photos/qiqi-view.jpg', IMG)
for old in re.findall(r'均價 65\.35 萬、新案天花板 85\.27 萬——七期房價現在該怎麼看？', head):
    head = head.replace(old, TITLE)
head = re.sub(r'<meta property="og:description" content="[^"]*">', f'<meta property="og:description" content="{DESC}">', head)
head = re.sub(r'"description":"[^"]*"', f'"description":"{DESC}"', head)
assert 'qiqi-price-2026' not in head and '65.35' not in head

nav = TPL[TPL.index('<body>'):TPL.index('<header class="art-head">')]
tail = TPL[TPL.index('<footer>'):]

# ---------- 圖：社區成交（房屋單價，已扣車位） ----------
W, H, Lm, R, T, B = 640, 300, 40, 120, 24, 44
X0, X1, YMIN, YMAX = 110.5, 115.9, 40, 82
def X(t): return Lm + (t - X0) * (W - Lm - R) / (X1 - X0)
def Y(v): return T + (YMAX - v) * (H - T - B) / (YMAX - YMIN)
def tt(d): y, m, _ = d.split('/'); return int(y) + (int(m) - .5) / 12
STY = {'A': ('#D8BC7E', 'A 戶 70 坪・4 房'), 'B': ('#8fa08f', 'B 戶 63 坪・3 房'), 'C': ('#E8735F', 'C 戶 55 坪・3 房')}
svg = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="麗晨語山簷歷年成交房屋單價" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans TC" font-size="11">']
for v in range(YMIN, YMAX + 1, 10):
    svg.append(f'<line x1="{Lm}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="rgba(216,188,126,.14)"/>'
               f'<text x="{Lm-6}" y="{Y(v)+4:.1f}" text-anchor="end" fill="#8fa08f">{v}</text>')
for y in range(111, 116):
    svg.append(f'<text x="{X(y):.1f}" y="{H-B+16}" text-anchor="middle" fill="#8fa08f">{y} 年</text>')
xc = X(113 + 6.5 / 12)
svg.append(f'<line x1="{xc:.1f}" x2="{xc:.1f}" y1="{T}" y2="{H-B}" stroke="#8fa08f" stroke-dasharray="3 3"/>'
           f'<text x="{xc+4:.1f}" y="{T+10}" fill="#8fa08f" font-size="10">113/07 使照・交屋</text>')
for r in TX:
    c, _ = STY[r['戶型']]
    svg.append(f'<circle cx="{X(tt(r["日期"])):.1f}" cy="{Y(r["單價"]):.1f}" r="4.4" fill="{c}" stroke="#182b21" stroke-width="1"/>')
lab, last = [], None
for r in sorted([r for r in TX if r['波段'] == '交屋後'], key=lambda r: -r['單價']):
    y = Y(r['單價']) + 4 if last is None else max(Y(r['單價']) + 4, last + 13)
    lab.append((r, y)); last = y
LX = W - R + 14
for r, y in lab:
    c, _ = STY[r['戶型']]
    svg.append(f'<line x1="{X(tt(r["日期"]))+5:.1f}" y1="{Y(r["單價"]):.1f}" x2="{LX-3}" y2="{y-4:.1f}" stroke="{c}" stroke-width=".7"/>'
               f'<text x="{LX}" y="{y:.1f}" fill="{c}" font-weight="700">{r["戶型"]} {r["樓層"]}F {r["單價"]:.1f}</text>')
for i, k in enumerate('CAB'):
    c, name = STY[k]; lx = Lm + i * 150
    svg.append(f'<circle cx="{lx+6}" cy="{H-10}" r="4.5" fill="{c}"/><text x="{lx+15}" y="{H-6}" fill="#C6D2C6">{name}</text>')
svg.append('</svg>')
chart = ''.join(svg)

after = [r for r in TX if r['波段'] == '交屋後']
after_rows = ''.join(f'<tr{" class=hl" if r["戶型"] == "C" else ""}><td>{r["日期"]}</td><td>{r["戶型"]} 戶</td><td class="n">{r["樓層"]}F</td>'
                     f'<td class="n">{wan(r["總價"])}</td><td class="n">{r["車位"] or "—"}</td><td class="n"><b>{r["單價"]:.2f}</b></td><td class="n">{r["含車單價"]:.2f}</td></tr>'
                     for r in reversed(after))
yr_rows = ''.join(f'<tr><td>{r["年"]} 年{"（至 10 月）" if r["年"] == 115 else ""}</td><td class="n">{r["n"]}</td>'
                  f'<td class="n"><b>{r["不含車中位"]:.2f}</b></td><td class="n">{r["含車中位"]:.2f}</td></tr>' for r in S['年度'])
def aft(t): return f'{t["交屋後中位"]:.2f}（{t["交屋後n"]} 筆）' if t['交屋後n'] else '尚無成交'
ty_rows = ''.join(f'<tr><td>{k} 戶</td><td>{d}</td><td class="n">{TY[k]["房屋坪"]:.2f}</td><td class="n">{TY[k]["預售中位"]:.2f}</td><td class="n"><b>{aft(TY[k])}</b></td></tr>'
                  for k, d in [('A', '4 房・南側臨大業路'), ('B', '3 房・北側'), ('C', '3 房・西側臨河南路')])
pre_c = [r for r in TX if r['戶型'] == 'C' and r['波段'] == '預售']
same_c = next(r for r in after if r['戶型'] == 'C')

body = f'''<header class="art-head">
  <div class="wrap">
    <a href="index.html" class="back">← 回文章列表</a>
    <div class="meta">社區行情 · 2026/10/16</div>
    <h1>麗晨語山簷行情分析<br>——交屋後房屋單價 {AF["net"]:.1f} 萬，三種戶型怎麼比</h1>
  </div>
</header>

<article class="art">
  <div class="wrap">
    <p>大業路與河南路四段口、惠文國小正對面的「麗晨語山簷」，是南七期少見的低密度新大樓：基地 495 坪只蓋 42 戶、每層 3 戶，外牆是一整片會長的植生牆。<strong>2024 年 7 月拿到使照、交屋滿一年後，開始有屋主轉手與建商保留戶釋出</strong>——這篇用實價登錄 35 筆住宅成交，拆給你看現在的行情落在哪裡。</p>

    <figure class="ph"><img src="../photos/lichen-exterior.jpg" alt="麗晨語山簷外觀，紅色格柵與複層植生牆" loading="lazy" width="900"><figcaption>麗晨語山簷外觀：傳統花窗、合院簷廊的意象，外層是植生牆與金屬擴張網。</figcaption></figure>

    <div class="data-grid">
      <div class="data-card"><div><span class="num">{AF["net"]:.1f}</span><span class="unit">萬/坪</span></div><div class="lb">115 年交屋後房屋單價中位（{AF["n"]} 筆，已扣車位）</div></div>
      <div class="data-card"><div><span class="num">{PRE["net"]:.1f}</span><span class="unit">萬/坪</span></div><div class="lb">預售期房屋單價中位（110–113 年，{PRE["n"]} 筆）</div></div>
      <div class="data-card"><div><span class="num">{PK["交屋後中位"]:.0f}</span><span class="unit">萬/席</span></div><div class="lb">交屋後坡道平面車位每席成交中位</div></div>
    </div>

    <h2>社區基本資料</h2>
    <div class="tblw"><table class="tbl">
      <tr><th style="width:28%">項目</th><th>內容</th></tr>
      <tr><td>地址</td><td>台中市南屯區大業路 556 號（河南路四段口）</td></tr>
      <tr><td>建設／設計／營造</td><td>麗晨建設／凡工建築師事務所／晨祥營造</td></tr>
      <tr><td>規模</td><td>基地 495 坪・地上 15 層・42 戶・每層 3 戶（A、B、C）</td></tr>
      <tr><td>使照</td><td>113 年 7 月・RC・土地分區第二種住宅區</td></tr>
      <tr><td>公設比／管理費</td><td>33.80%／140 元/坪/月</td></tr>
      <tr><td>車位</td><td>98 位，坡道平面，私有充電車位</td></tr>
      <tr><td>學區</td><td>惠文國小（雙語）・惠文高中國中部</td></tr>
    </table></div>

    <h2>空中三合院：把合院簷廊搬上 15 層樓</h2>
    <p>語山簷的設計構想是把傳統合院的「簷廊」立起來：住家外面先有一圈維護通道與複層植生牆（Double Skin），再進到室內。簷廊遮陽、避雨、隔熱，植栽沿著格柵往上長，從室內看出去是綠的，從街上看是一棟會換季的大樓。</p>
    <div class="ph2">
      <figure class="ph"><img src="../photos/lichen-corridor.jpg" alt="環繞住家的空中綠廊" loading="lazy" width="900"><figcaption>環繞住家的空中綠廊，望向惠文國小操場。</figcaption></figure>
      <figure class="ph"><img src="../photos/lichen-greenwall.jpg" alt="複層植生牆與入口庭園" loading="lazy" width="900"><figcaption>入口庭園與植生牆。</figcaption></figure>
    </div>
    <ul>
      <li><strong>一層三戶、零走廊：</strong>出電梯就入戶，戶戶三面採光。</li>
      <li><strong>零瓦斯全電：</strong>全社區不接瓦斯；德國鑄鐵排水管、全室隔音墊。</li>
      <li><strong>衛浴全開窗、全平面無障礙：</strong>每間衛浴都有窗，室內沒有高低差。</li>
      <li><strong>公設：</strong>1F 挑高圖書館（敦煌書店選書）與水景、琴房、交誼廳；頂樓空中花園、開心農場、健身房。</li>
    </ul>
    <figure class="ph"><img src="../photos/lichen-library.jpg" alt="一樓挑高圖書館" loading="lazy" width="900"><figcaption>1F 挑高圖書館。</figcaption></figure>

    <h2>行情一：交屋後成交集中在 67–78 萬/坪</h2>
    <p>下圖每一個點是一筆成交，單價一律是<strong>房屋單價（已扣車位）</strong>：（總價－車位價）÷（總坪數－車位坪數），車位價和車位坪數都取自實登揭露。這樣算，有車位、沒車位的成交才能放在一起比。</p>
    <div class="chart">{chart}</div>
    <div class="tblw"><table class="tbl">
      <tr><th>日期</th><th>戶型</th><th>樓層</th><th>總價（萬）</th><th>車位</th><th>房屋單價<br>（已扣車位）</th><th>總價÷總坪數<br>（車位一起算）</th></tr>
      {after_rows}
    </table></div>
    <p>115 年的 {AF["n"]} 筆裡，5 筆是 A 戶（70 坪 4 房），預售期實登沒看到這幾戶，研判多為建商保留戶交屋後才售出〔推估〕；另 1 筆是 C 戶 13 樓，112 年預售買進、115 年 1 月以 {wan(same_c["總價"])} 萬（不含車位）轉手，房屋單價 {same_c["單價"]:.1f}。</p>

    <h2>行情二：A、B、C 三種戶型怎麼選</h2>
    <div class="tblw"><table class="tbl">
      <tr><th>戶型</th><th>位置</th><th>房屋坪數</th><th>預售中位</th><th>交屋後中位</th></tr>
      {ty_rows}
    </table></div>
    <p>A 戶最大、4 房，交屋後總價多在 5,300–6,360 萬；C 戶 55 坪 3 房，是全社區總價門檻最低的產品，一般配 2 個平面車位。B 戶交屋後還沒有成交紀錄。</p>

    <h2>行情三：預售簽約價和交屋後成交價，差在哪</h2>
    <div class="tblw"><table class="tbl">
      <tr><th>年度</th><th>筆數</th><th>房屋單價（已扣車位）</th><th>總價÷總坪數（車位一起算）</th></tr>
      {yr_rows}
    </table></div>
    <p>預售期（110–113 年）房屋單價中位 {PRE["net"]:.1f}，和交屋後的 {AF["net"]:.1f} 差了一截。要注意兩件事：預售價是 3–5 年前簽約時的價格，不能直接拿來當現在的行情；交屋後的成交只有 {AF["n"]} 筆、而且多是 A 戶，<strong>樣本少，看單一戶時一定要回到同戶型、相近樓層比</strong>。車位也一樣：預售每席中位約 {PK["預售中位"]:.0f} 萬，交屋後成交 {PK["交屋後"][0]:.0f}–{PK["交屋後"][-1]:.0f} 萬。</p>

    <div class="cta-box">
      <h3>在看語山簷或南七期其他社區？</h3>
      <p>📱 加 LINE，助哥用逐戶實登幫你算同戶型、同樓層的合理價。</p>
      <a href="https://line.me/R/ti/p/@080akczk" class="btn">加 LINE →</a>
    </div>

    <div class="listing">
      <span class="tag">現正銷售</span>
      <h3>語山簷 7 樓 C 戶・三房雙平車</h3>
      <p>權狀 {L["坪數"]} 坪（含車位 {L["車位坪"]} 坪）・3房2廳2衛・朝西・坡道平面車位 ×2（B3 獨立、B4 柱邊）・空屋。開價 <strong>{wan(L["總價"])} 萬</strong>。</p>
      <p>扣掉兩個車位（以交屋後每席中位約 {wan(PK["交屋後中位"])} 萬計），房屋單價約 <strong>{L["單價"]:.1f} 萬/坪</strong>，低於社區交屋後中位 {AF["net"]:.1f}；同型 C 戶 13 樓 115/01 成交 {same_c["單價"]:.1f}。北、西、南三面環綠廊，窗外是惠文國小。</p>
      <figure class="ph" style="margin:18px 0"><img src="../photos/lichen-living.jpg" alt="7 樓 C 戶客廳" loading="lazy" width="900"><figcaption>本戶客廳：整面落地窗通陽台。</figcaption></figure>
      <div class="yt"><iframe src="https://www.youtube.com/embed/UrZ5fMJqZtA" title="麗晨語山簷 影片導覽" loading="lazy" allow="accelerometer; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>
      <div style="text-align:center"><a href="https://line.me/R/ti/p/@080akczk" class="btn">預約看屋・索取完整報告 →</a></div>
      <div class="lic">永慶不動產 七期河南市政店（百富國際開發有限公司）・中市地價二字第1070032073號・聯絡：助哥 0925-313-570。坪數與產權以權狀、謄本及不動產說明書為準。</div>
    </div>

    <div class="src">資料來源：內政部不動產交易實價查詢服務網，社區名稱「麗晨語山簷」，交易期間 101/01–115/10，查詢 2026/10/16；住宅有效 {S["有效筆數"]} 筆（排除 1F 店面 1 筆）。單價為中位數。建物資料參考樂居、591 新建案公開資料。本文僅供市場觀察參考，非估價報告，不代表未來價格走勢。</div>

    <nav aria-label="延伸閱讀" style="margin-top:36px">
      <div style="font-family:'Noto Serif TC',serif;font-size:13px;letter-spacing:.18em;color:#8fa08f;font-weight:700;margin-bottom:14px">延伸閱讀</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px">
        <a href="/blog/qiqi-neighborhoods.html" style="display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 18px;border:1px solid rgba(216,188,126,.28);border-radius:12px;background:rgba(255,255,255,.03);color:#D7E0D6;font-size:15px;font-weight:600"><span>七期三個次分區怎麼分</span><span aria-hidden="true" style="color:var(--brass-lite);flex-shrink:0">→</span></a>
        <a href="/blog/qiqi-presale-vs-resale.html" style="display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 18px;border:1px solid rgba(216,188,126,.28);border-radius:12px;background:rgba(255,255,255,.03);color:#D7E0D6;font-size:15px;font-weight:600"><span>七期預售 vs 中古怎麼選？</span><span aria-hidden="true" style="color:var(--brass-lite);flex-shrink:0">→</span></a>
        <a href="/blog/qiqi-offer-price.html" style="display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 18px;border:1px solid rgba(216,188,126,.28);border-radius:12px;background:rgba(255,255,255,.03);color:#D7E0D6;font-size:15px;font-weight:600"><span>出價前先算這幾件事</span><span aria-hidden="true" style="color:var(--brass-lite);flex-shrink:0">→</span></a>
      </div>
    </nav>
  </div>
</article>

'''
OUT.write_text(head + '\n' + nav + body + tail, encoding='utf-8')
print('→', OUT)
