"""赫里翁 網站行情分析頁：讀 summary.json / transactions.csv → blog/heliweng.html。
市場資訊頁，不放特定物件開價；版型沿用 office/*.html。"""
import json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
OUT = ROOT / 'blog' / 'heliweng.html'
S = json.load(open(HERE / 'summary.json'))
df = pd.read_csv(HERE / 'transactions.csv').fillna({'備註': '', '格局': ''})
df['yr'] = df['交易日期'].str[:3].astype(int)
R3, SAME5, CMP = S['近三年'], S['同型_近五年'], S['比較組']
CB = CMP['同級距']
HI = S['樓層帶_110後'][2]
URL = 'https://sixhands-studio.netlify.app/blog/heliweng.html'
TITLE = '赫里翁 實價登錄分析｜西屯青海路二段188號 興富發 25 層雙塔｜行情・戶型・樓層・西屯比較'
DESC = (f'赫里翁（台中西屯青海路二段188號）實登 {S["有效筆數"]} 筆逐筆扣車位重算：三房中坪近五年 {SAME5["net"]:.1f} 萬/坪、'
        f'高樓層 {HI["不含車中位"]:.1f}、西屯同坪數大樓 {CB["net"]:.1f} 萬/坪。')
PK1 = S['車位']['每席價格中位_全期']

# 全社區年度中位長條
yrs = df.groupby('yr')['不含車單價'].agg(['median', 'count'])
mx = yrs['median'].max()
bars = ''.join(f'<div class="yrow"><span>{y} 年</span><span class="bar" style="width:{v/mx*100:.0f}%;background:#B08D3F;opacity:{.45+.04*i:.2f}"></span>'
               f'<span class="num"><b>{v:.1f}</b> <span style="font-size:11px;color:var(--mute)">n={int(n)}</span></span></div>'
               for i, (y, (v, n)) in enumerate(yrs.iterrows()))

def f2(v): return '—' if v is None else f'{v:.2f}'
prod = ''.join(f'<tr><td>{p["型"]}</td><td class="num">{p["總面積中位"]:.2f}</td><td class="num">{p["扣車位面積中位"]:.2f}</td>'
               f'<td class="num">{p["全期n"]}</td><td class="num">{p["近五年n"]}</td><td class="num"><b>{f2(p["近五年不含車中位"])}</b></td>'
               f'<td class="num">{f2(p["近五年含車中位"])}</td></tr>' for p in S['產品'])
floors = ''.join(f'<tr><td>{b["帶"]}</td><td class="num">{b["n"]} 筆</td><td class="num"><b>{b["不含車中位"]:.2f}</b></td><td class="num">{b["含車中位"]:.2f}</td></tr>'
                 for b in S['樓層帶_110後'])
recent = ''
for r in df[df['yr'] >= 110].itertuples():
    est = '*' if r.車位價來源.startswith('估算') else ''
    recent += (f'<tr><td>{r.交易日期}</td><td>{r.戶別}・{r.樓層}F</td><td>{r.產品[:4]}</td><td>{r.格局}</td><td class="num">{r.總價萬:,.0f}</td>'
               f'<td class="num">{r.總面積坪:.2f}</td><td class="num">{r.車位數}</td><td class="num"><b>{r.不含車單價:.2f}{est}</b></td>'
               f'<td class="num">{r.含車單價:.2f}</td><td>{r.備註.replace(";", " ").strip()[:10]}</td></tr>')
cmp_rows = ''.join(f'<tr><td>{r["日期"]}</td><td>{r["社區"]}</td><td class="num">{r["屋齡"]}</td><td class="num">{r["樓層"]}F</td><td class="num">{r["總價"]:,.0f}</td>'
                   f'<td class="num">{r["扣車位"]:.2f}</td><td class="num"><b>{r["不含車"]:.2f}{"" if r["車位價"] else "*"}</b></td><td class="num">{r["含車"]:.2f}</td></tr>'
                   for r in CMP['明細'] if r['同級距'])
RT = S['租賃']
rent = ''.join(f'<tr><td>{r["日期"]}</td><td>{r["戶"]}・{r["樓層"]}F</td><td class="num">{r["面積坪"]:.2f}</td><td class="num">{r["車位"]}</td>'
               f'<td class="num"><b>{r["月租萬"]:.2f}</b></td><td class="num">{r["每坪元"]:,}</td><td>{"單價異常" if r["每坪元"] >= 2000 else ("含管理費" if "含管理費" in r["備註"] else "—")}</td></tr>'
               for r in RT['明細'])
mid = df[df['產品'].str.startswith('三房')].groupby('yr')['不含車單價'].median()

site = '''<svg viewBox="0 0 380 220" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans TC" font-size="10">
<rect x="20" y="8" width="320" height="16" fill="#e8edf0"/><text x="180" y="20" text-anchor="middle" fill="#5d6b76" font-size="9">西屯路二段 249-9 巷</text>
<rect x="20" y="194" width="340" height="18" fill="#e8edf0"/><text x="190" y="207" text-anchor="middle" fill="#5d6b76" font-size="9.5">青海路二段</text>
<rect x="346" y="8" width="16" height="186" fill="#e8edf0"/><text x="354" y="100" text-anchor="middle" fill="#5d6b76" font-size="9" writing-mode="tb">弘孝路</text>
''' + ''.join(f'<rect x="{x}" y="{y}" width="74" height="66" rx="3" fill="{c}" stroke="#9fb3bf"/><text x="{x+37}" y="{y+30}" text-anchor="middle" font-size="17" font-weight="700" fill="#1F4E5F">{k}</text>'
              f'<text x="{x+37}" y="{y+48}" text-anchor="middle" font-size="9" fill="#5d6b76">188號{no}</text>'
              for k, x, y, no, c in [('B2', 30, 40, '之6', '#f4ecdc'), ('B3', 108, 40, '之7', '#f4ecdc'), ('A3', 186, 40, '之3', '#f4ecdc'),
                                     ('A2', 264, 40, '之2', '#eef3f6'), ('B1', 30, 112, '之5', '#eef3f6'), ('A1', 264, 112, '之1', '#eef3f6')]) + '''
<rect x="108" y="112" width="24" height="66" fill="#d8e0e5"/><text x="120" y="150" text-anchor="middle" font-size="8.5" fill="#5d6b76" writing-mode="tb">梯間</text>
<rect x="186" y="112" width="24" height="66" fill="#d8e0e5"/><text x="198" y="150" text-anchor="middle" font-size="8.5" fill="#5d6b76" writing-mode="tb">梯間</text>
<text x="74" y="186" text-anchor="middle" font-size="8.5" fill="#7b8794">B 棟</text><text x="300" y="186" text-anchor="middle" font-size="8.5" fill="#7b8794">A 棟</text>
<text x="2" y="36" font-size="8.5" fill="#7b8794">↖北</text></svg>'''

css = (ROOT / 'office' / 'ntc.html').read_text(encoding='utf-8')
css = css[css.index('<style>'):css.index('</style>') + 8]

html = f'''<!DOCTYPE html><html lang="zh-Hant"><head>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-Z2BTZV5V2P"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-Z2BTZV5V2P');
</script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{TITLE}</title>
<meta name="description" content="{DESC}">
<meta name="keywords" content="赫里翁,赫里翁實價登錄,赫里翁行情,青海路二段188號,興富發,台中西屯大樓,逢甲 大樓 行情,西屯 三房 行情">
<meta name="author" content="助哥｜台中行情"><meta name="robots" content="index,follow">
<link rel="canonical" href="{URL}">
<meta name="theme-color" content="#1F3A2E">
<meta property="og:type" content="website"><meta property="og:site_name" content="助哥｜台中行情">
<meta property="og:title" content="{TITLE}"><meta property="og:description" content="{DESC}">
<meta property="og:url" content="{URL}">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"Article","headline":"赫里翁 實價登錄分析","description":"赫里翁 實價登錄行情、戶型分型、樓層與西屯同坪數大樓比較。","author":{{"@type":"Person","name":"助哥"}},"datePublished":"2026-10-23","mainEntityOfPage":"{URL}"}}</script>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;700&family=Noto+Serif+TC:wght@500;700;900&display=swap" rel="stylesheet">
{css}</head><body><nav><div class="wrap">
<a class="brand" href="../qiqi-realestate.html">助哥<span style="color:var(--gold)">｜</span>台中行情</a>
<span class="sp"></span>
<a class="lk" href="#trend">逐年行情</a>
<a class="lk" href="#products">戶型與樓層</a>
<a class="lk" href="#compare">西屯比較</a>
<a class="lk" href="../blog/index.html">文章</a>
<a class="btn btn-primary btn-sm" href="https://line.me/R/ti/p/@080akczk" target="_blank" rel="noopener">聊聊</a>
</div></nav>
<header class="hero"><div class="wrap">
 <div class="tag"><span class="dot" style="background:#B08D3F"></span>住宅大樓　／　台中西屯・青海路二段 × 弘孝路（非七期重劃區）</div>
 <h1>赫里翁</h1>
 <p class="lead">青海路二段188號｜興富發建設｜2011 年完工｜25 樓雙塔｜143 戶｜一層三戶兩梯｜RC<br>
 <b style="color:var(--gold-light)">戶型分兩種、樓層有差：看行情先分三房中坪與四房大坪，再看樓層</b></p>
 <div class="kpis">
  <div class="kpi"><div class="v">{SAME5["net"]:.1f}</div><div class="l">萬/坪・三房中坪近五年<br>房屋單價（已扣車位）・{SAME5["n"]} 筆</div></div>
  <div class="kpi"><div class="v">{R3["net"]:.1f}</div><div class="l">萬/坪・全社區近三年<br>{R3["n"]} 筆・車位一起算 {R3["gross"]:.1f}</div></div>
  <div class="kpi"><div class="v">{HI["不含車中位"]:.1f}</div><div class="l">萬/坪・高樓層 18–25F<br>110 年後 {HI["n"]} 筆</div></div>
  <div class="kpi"><div class="v">{CB["net"]:.1f}</div><div class="l">萬/坪・西屯同坪數大樓<br>屋齡 10–20 年・{CB["n"]} 筆</div></div>
 </div>
</div></header>

<section id="trend"><div class="wrap">
 <div class="sec-tag">PRICE TREND</div><h2 class="sec-title">全社區：逐年行情</h2>
 <p class="sec-lead">101–115 年買賣 {S["原始筆數"]} 筆，排除特殊關係、債務抵償與資料異常 {len(S["排除"])} 筆，有效 {S["有效筆數"]} 筆。以下為「房屋單價（已扣車位）」年度中位，n 為筆數。</p>
 <div style="background:#fff;border:1px solid var(--line);border-radius:14px;padding:22px 24px">{bars}
  <div style="border-top:1px solid #ece4d4;margin-top:14px;padding-top:12px;font-size:14px">三房中坪年度中位：110 年 {mid.get(110):.1f} → 112 年 {mid.get(112):.1f} → 114 年 <b>{mid.get(114):.1f}</b>。115 年至 10 月社區尚無成交，下一筆成交是重要的行情確認。</div></div>
 <p style="font-size:12.5px;color:var(--mute);margin-top:9px">長條自 0 起算。單價為（總價－車位價）÷（總坪數－車位坪數）；車位價未揭露者以社區坡道平面每席中位 {PK1:.0f} 萬估算。</p>
 <div class="note" style="margin-top:20px"><b>◆ 這個社區的兩種單價幾乎一樣。</b>坡道平面車位每席登記約 6 坪、實登揭露每席中位 {PK1:.0f} 萬，車位每坪價和房屋差不多。
 所以網路上常看到的「總價÷總坪數」跟「房屋單價（已扣車位）」差距在 1–2% 內，可以直接拿來比社區行情；跟別的社區比時，仍建議兩個數字一起看。</div>
</div></section>

<section id="products" style="background:#faf7ef"><div class="wrap">
 <div class="sec-tag">PRODUCT MIX</div><h2 class="sec-title">三房中坪與四房大坪</h2>
 <p class="sec-lead">A、B 兩棟各一層 3 戶：之3／之6／之7 為三房中坪（扣車位約 84 坪），之1／之2／之5 為四房大坪（約 109 坪）。兩種戶型單價差距不大，總價差在坪數。</p>
 <div class="tblwrap"><table><tr><th>產品</th><th class="num">總坪數中位</th><th class="num">扣車位中位</th><th class="num">全期筆數</th><th class="num">111–115 筆數</th><th class="num">房屋單價（已扣車位）</th><th class="num">總價÷總坪數（車位一起算）</th></tr>{prod}</table></div>
 <div class="two" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:22px;margin-top:26px">
  <div><h3 style="font-size:18px;margin-bottom:10px">樓層：18 樓以上有溢價</h3>
   <div class="tblwrap"><table style="min-width:360px"><tr><th>樓層帶（110 年後）</th><th class="num">筆數</th><th class="num">已扣車位</th><th class="num">車位一起算</th></tr>{floors}</table></div>
   <p style="font-size:13px;color:var(--mute);margin-top:8px">25 層的社區，18–25 樓中位比中低樓層高約一成；高樓層樣本 {HI["n"]} 筆，不分戶型。</p></div>
  <div><h3 style="font-size:18px;margin-bottom:10px">棟別配置</h3>
   <div style="background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px">{site}</div>
   <p style="font-size:13px;color:var(--mute);margin-top:8px">依樂居棟別圖重繪，非比例尺。淡金底為三房中坪。</p></div>
 </div>
</div></section>

<section><div class="wrap">
 <div class="sec-tag">RECENT DEALS</div><h2 class="sec-title">110 年後成交明細</h2>
 <div class="tblwrap"><table><tr><th>日期</th><th>戶別</th><th>產品</th><th>格局</th><th class="num">總價（萬）</th><th class="num">總坪數</th><th class="num">車位</th><th class="num">已扣車位</th><th class="num">車位一起算</th><th>備註</th></tr>{recent}</table></div>
 <p style="font-size:12.5px;color:var(--mute);margin-top:9px">* 車位價未揭露，以每席中位估算。格局為實登登載之現況格局。單位：萬元／坪。</p>
</div></section>

<section id="compare" style="background:#faf7ef"><div class="wrap">
 <div class="sec-tag">AREA COMPARISON</div><h2 class="sec-title">跟西屯同坪數大樓比</h2>
 <p class="sec-lead">比較組：西屯區、大樓／華廈、屋齡 10–20 年、總坪數 70–100 坪（113/01–115/10），再取扣車位 {CMP["級距"].split(" ")[1]} 坪、與三房中坪同級距的 {CB["n"]} 筆（不含本社區）。</p>
 <div class="cards">
  <div class="card"><h3>西屯同坪數 中位</h3><div class="big">{CB["net"]:.1f}</div><p>萬/坪（已扣車位）；車位一起算 {CB["gross"]:.1f}</p></div>
  <div class="card"><h3>赫里翁 三房中坪近五年</h3><div class="big">{SAME5["net"]:.1f}</div><p>萬/坪（已扣車位）；車位一起算 {SAME5["gross"]:.1f}</p></div>
  <div class="card"><h3>價差</h3><div class="big">{(SAME5["net"]/CB["net"]-1)*100:+.0f}%</div><p>西屯範圍大，同坪數大樓從 33 到 50 萬都有成交；赫里翁的成交落在中段偏低</p></div>
 </div>
 <div class="tblwrap" style="margin-top:22px"><table><tr><th>日期</th><th>社區</th><th class="num">屋齡</th><th class="num">樓層</th><th class="num">總價（萬）</th><th class="num">扣車位坪數</th><th class="num">已扣車位</th><th class="num">車位一起算</th></tr>{cmp_rows}</table></div>
 <p style="font-size:12.5px;color:var(--mute);margin-top:9px">「—」為實登未填社區名。* 車位價未揭露，以比較組同類別車位中位估算。屋齡為交易當時。</p>
</div></section>

<section><div class="wrap">
 <div class="sec-tag">RENT</div><h2 class="sec-title">出租行情</h2>
 <p class="sec-lead">101–115 年租賃實登 {RT["筆數"]} 筆，最新一筆在 {RT["最新"]}，近三年沒有租賃實登。103–110 年整戶月租多在 4.3–9.3 萬之間，以自住為主的社區。</p>
 <div class="tblwrap"><table style="min-width:560px"><tr><th>日期</th><th>戶別</th><th class="num">面積（坪）</th><th class="num">車位</th><th class="num">月租（萬）</th><th class="num">元／坪／月</th><th>說明</th></tr>{rent}</table></div>
 <p style="font-size:12.5px;color:var(--mute);margin-top:9px">面積依實登登記，部分未含車位，每坪租金僅供參考。106/11 一筆每坪逾 3,000 元，疑為登錄異常。</p>
</div></section>

<section style="background:#faf7ef"><div class="wrap">
 <div class="sec-tag">TWO SIDES</div><h2 class="sec-title">同一份數據，兩種用法</h2>
 <div class="cards">
  <div class="card" style="border-top:3px solid var(--t2)"><div class="sec-tag" style="color:var(--t2)">如果你是買方</div>
   <h3 style="margin:8px 0 10px">先分戶型，再看樓層與年度</h3>
   <p style="font-size:15px;line-height:1.85">三房中坪與四房大坪單價接近，但高樓層有一成左右溢價；114 年之後的成交比 111 年前高出一截，拿舊成交比要注意年份。毛胚屋與裝修屋的成交也要分開看。</p></div>
  <div class="card" style="border-top:3px solid var(--t3)"><div class="sec-tag" style="color:var(--t3)">如果你是屋主</div>
   <h3 style="margin:8px 0 10px">樓層、景觀與屋況是籌碼</h3>
   <p style="font-size:15px;line-height:1.85">社區近三年成交 {R3["n"]} 筆、樣本少，單筆影響大。高樓層、端戶採光、裝修內容寫清楚，買方才有比較基準。</p></div>
 </div>
</div></section>

<section><div class="wrap"><div class="cta">
 <h2>想知道赫里翁某一戶現在值多少？</h2>
 <p>我手上有 {S["有效筆數"]} 筆買賣、{RT["筆數"]} 筆租賃的逐筆明細，和西屯同坪數大樓的比較組。<br>告訴我戶別、樓層跟車位數，我算給你看。</p>
 <a class="btn btn-primary" href="https://line.me/R/ti/p/@080akczk" target="_blank" rel="noopener">加 LINE 聊聊 →</a>
 <div style="margin-top:18px"><a class="btn btn-ghost" style="color:#e6dfcd;border-color:#4a6255" href="../qiqi-realestate.html">← 回台中行情首頁</a></div>
</div></div></section>
<footer><div class="wrap"><div class="fx">
<div><b>助哥｜台中行情</b><div style="margin-top:6px">不賣房子，賣判斷。<br>實登逐筆重算，數字附來源。</div></div>
<div><b>導覽</b><div style="margin-top:6px"><a href="../qiqi-realestate.html">住宅・土地・廠房</a>　<a href="../qiqi-office.html">七期商辦</a><br><a href="../blog/index.html">文章</a></div></div>
<div><b>聯絡</b><div style="margin-top:6px"><a href="https://line.me/R/ti/p/@080akczk" target="_blank" rel="noopener">LINE 諮詢</a></div></div>
</div>
<div class="dis">
資料來源：內政部不動產交易實價查詢服務網，青海路二段188號買賣與租賃（101/01–115/10）；西屯區住宅大樓／華廈・屋齡10–20年・總面積70–100坪買賣（113/01–115/10）；撈取日 2026-10-23。社區資料整理自樂居等網路公開資訊。
單價一律用中位數，已扣除車位、排除特殊關係；樣本少的區間另有標註。<br>
本頁為市場資訊整理與分析，僅供參考，<b style="font-size:12px">不構成價格保證、投資建議或要約</b>，亦非特定物件之銷售廣告。
個案成交條件差異極大，實際價格應以現場查看與個案評估為準。過去成交不代表未來表現。<br>
永慶不動產 七期河南市政店 / 百富國際開發有限公司 / 中市地價二字第1070032073號
</div></div></footer></body></html>'''
OUT.write_text(html, encoding='utf-8')
print('→', OUT)
