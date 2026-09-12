#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""七期商辦網站產生器 — 小登
產出：qiqi-office.html（母頁）＋ office/<slug>.html（各案子頁）
口徑全部來自 七期商辦_九案數據.json（近三年中位、扣車位、含/不含車位並列）

⛔ 助哥指示 2026-09-12：頁面打「助哥」個人品牌，不掛經紀業名稱。
   前提：本頁維持「市場資訊／數據分析＋諮詢」定位，不銷售特定物件、不招攬委託，
   故非《不動產經紀業管理條例》第21條所稱之「不動產廣告」。
   ⚠️ 若日後在頁面刊登實際物件或招攬委託 → 該頁必須補上經紀業名稱與證號。
"""
import json, pathlib
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]                      # /home/user/my-website
D = json.load(open(HERE / "七期商辦_九案數據.json", encoding="utf-8"))
SITE = "https://sixhands-studio.netlify.app"
LINE = "https://line.me/R/ti/p/@080akczk"
TIER = {"入門": "#2F8F5B", "中階": "#C98A2E", "頂級": "#A8384F"}   # validate_palette PASS
SLUG = {"市政壹號廣場":"shizheng-yihao","聯聚中維大廈":"lianju-zhongwei","聯聚中雍大廈":"lianju-zhongyong",
        "鼎盛BHW":"dingsheng-bhw","NTC國家商貿中心":"ntc","CBD時代廣場":"cbd-times-square",
        "親家T-POWER":"qinjia-tpower","親家T3市政國際中心":"qinjia-t3","豐邑市政都心廣場":"fengyi-shizheng"}
LIVE = {"NTC國家商貿中心"}                   # 已上線之子頁（樣板）
def money(v): return f"{v/10000:.2f} 億" if v >= 10000 else f"{v:,.0f} 萬"
def dot(t):  return f'<span class="dot" style="background:{TIER[t]}"></span>{t}'

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--brown-dark:#182b21;--brown:#1F3A2E;--brown-mid:#2C4E3D;--gold:#B08D3F;--gold-light:#D8BC7E;
 --cream:#F3EEE2;--cream-dark:#F1E6CF;--line:#ddd3bf;--text:#22271F;--mute:#565c50;
 --t1:#2F8F5B;--t2:#C98A2E;--t3:#A8384F}
html{scroll-behavior:smooth}
body{font-family:'Noto Sans TC',-apple-system,'PingFang TC',sans-serif;color:var(--text);line-height:1.75;background:var(--cream)}
h1,h2,h3,h4{font-family:'Noto Serif TC','PingFang TC',serif;font-weight:700;line-height:1.35}
a{color:inherit}
.wrap{max-width:1060px;margin:0 auto;padding:0 20px}
nav{position:sticky;top:0;z-index:50;background:rgba(243,238,226,.94);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
nav .wrap{display:flex;align-items:center;gap:18px;height:58px}
nav .brand{font-family:'Noto Serif TC',serif;font-weight:700;font-size:17px;text-decoration:none;white-space:nowrap}
nav .sp{margin-left:auto}
nav a.lk{font-size:14px;color:var(--mute);text-decoration:none}
nav a.lk:hover{color:var(--brown)}
.btn{display:inline-block;padding:12px 26px;border-radius:999px;text-decoration:none;font-weight:500;font-size:15px}
.btn-primary{background:var(--gold);color:#fff}
.btn-ghost{border:1px solid var(--line);color:var(--brown)}
.btn-sm{padding:8px 18px;font-size:14px}
header.hero{background:linear-gradient(160deg,var(--brown) 0%,var(--brown-dark) 100%);color:#fff;padding:64px 0 56px}
.hero .tag{font-size:12px;letter-spacing:.32em;color:var(--gold-light)}
.hero h1{font-size:clamp(30px,5.4vw,46px);margin:16px 0 14px}
.hero .lead{font-size:clamp(15px,2.2vw,18px);color:#dcd6c6;max-width:640px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-top:34px}
.kpi{background:rgba(255,255,255,.07);border:1px solid rgba(216,188,126,.3);border-radius:12px;padding:18px 16px}
.kpi .v{font-family:'Noto Serif TC',serif;font-size:27px;color:var(--gold-light);font-weight:700;line-height:1.2}
.kpi .l{font-size:12.5px;color:#c3bdad;margin-top:6px}
section{padding:56px 0}
.sec-tag{font-size:11.5px;letter-spacing:.3em;color:var(--gold)}
.sec-title{font-size:clamp(22px,3.4vw,30px);margin:10px 0 8px}
.sec-lead{color:var(--mute);font-size:15px;max-width:680px;margin-bottom:26px}
.tblwrap{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:12px;background:#fff}
table{width:100%;border-collapse:collapse;font-size:14px;min-width:760px}
th{background:var(--brown);color:#f3eee2;font-weight:500;padding:11px 12px;text-align:left;font-size:13px;white-space:nowrap}
td{padding:11px 12px;border-bottom:1px solid #ece4d4;white-space:nowrap}
tr:last-child td{border-bottom:0}
tr:nth-child(even) td{background:#faf7ef}
.num{text-align:right;font-variant-numeric:tabular-nums}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:0}
.sub{display:block;font-size:11.5px;color:var(--mute);font-weight:400}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:16px}
.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:22px}
.card h3{font-size:17px;margin-bottom:8px}
.card p{font-size:14.5px;color:var(--mute)}
.card .big{font-family:'Noto Serif TC',serif;font-size:30px;color:var(--gold);font-weight:700;line-height:1.2;margin:4px 0 8px}
.bldg{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
.bcard{background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px 20px;text-decoration:none;display:block;transition:.15s}
.bcard:hover{border-color:var(--gold);transform:translateY(-2px)}
.bcard .nm{font-family:'Noto Serif TC',serif;font-weight:700;font-size:16.5px;margin-bottom:4px}
.bcard .mt{font-size:13px;color:var(--mute)}
.bcard .pr{font-family:'Noto Serif TC',serif;font-size:22px;color:var(--brown);font-weight:700;margin-top:8px}
.bcard .soon{font-size:12px;color:#9a9384}
.note{background:#fdf8ec;border-left:4px solid var(--gold);padding:16px 18px;border-radius:0 10px 10px 0;font-size:14.5px;line-height:1.85}
.warn{background:#fbf0ec;border-left:4px solid #A8384F;padding:16px 18px;border-radius:0 10px 10px 0;font-size:14.5px;line-height:1.85}
.cta{background:var(--brown);color:#fff;border-radius:16px;padding:40px 32px;text-align:center}
.cta h2{font-size:clamp(20px,3vw,27px);margin-bottom:10px}
.cta p{color:#cfc9b8;font-size:15px;margin-bottom:22px}
footer{background:var(--brown-dark);color:#a9a294;font-size:13px;padding:40px 0 34px}
footer .fx{display:flex;flex-wrap:wrap;gap:26px;justify-content:space-between}
footer b{color:#e6dfcd;font-family:'Noto Serif TC',serif;font-size:15px}
footer a{color:#c8c0ae}
.dis{margin-top:22px;padding-top:18px;border-top:1px solid #2a3d33;line-height:1.8;font-size:12px;color:#8d8677}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13.5px;margin:0 0 14px}
.bar{height:11px;border-radius:6px}
.yrow{display:grid;grid-template-columns:52px 1fr 62px;gap:10px;align-items:center;font-size:13.5px;margin-bottom:7px}
@media(max-width:640px){section{padding:42px 0}nav a.lk{display:none}}
"""

def head(title, desc, url, keywords, ld=""):
    return f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="keywords" content="{keywords}">
<meta name="author" content="助哥｜七期商辦"><meta name="robots" content="index,follow">
<link rel="canonical" href="{url}">
<meta name="theme-color" content="#1F3A2E">
<meta property="og:type" content="website"><meta property="og:site_name" content="助哥｜七期商辦">
<meta property="og:title" content="{title}"><meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE}/deliverables/FB_%E4%B8%83%E6%9C%9F%E5%95%86%E8%BE%A6%E4%BD%8D%E7%BD%AE%E5%88%86%E4%BD%88%E5%9C%96.png">
<meta name="twitter:card" content="summary_large_image">
{ld}
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;700&family=Noto+Serif+TC:wght@500;700;900&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>"""

def nav(depth=0):
    up = "../" * depth
    return f"""<nav><div class="wrap">
<a class="brand" href="{up}qiqi-office.html">助哥<span style="color:var(--gold)">｜</span>七期商辦</a>
<span class="sp"></span>
<a class="lk" href="{up}qiqi-office.html#table">九案速查</a>
<a class="lk" href="{up}qiqi-office.html#map">位置分佈</a>
<a class="lk" href="{up}qiqi-office.html#buildings">逐案</a>
<a class="lk" href="{up}qiqi-realestate.html">住宅／土地</a>
<a class="btn btn-primary btn-sm" href="{LINE}" target="_blank" rel="noopener">聊聊</a>
</div></nav>"""

def footer(depth=0):
    up = "../" * depth
    return f"""<footer><div class="wrap"><div class="fx">
<div><b>助哥｜七期商辦</b><div style="margin-top:6px">不賣房子，賣判斷。<br>七期九棟商辦，實登逐筆重算。</div></div>
<div><b>導覽</b><div style="margin-top:6px">
<a href="{up}qiqi-office.html">商辦首頁</a>　<a href="{up}qiqi-office.html#buildings">逐案分析</a><br>
<a href="{up}qiqi-realestate.html">住宅・土地・廠房</a>　<a href="{up}blog/index.html">文章</a></div></div>
<div><b>聯絡</b><div style="margin-top:6px"><a href="{LINE}" target="_blank" rel="noopener">LINE 諮詢</a></div></div>
</div>
<div class="dis">
資料來源：內政部不動產交易實價查詢服務網（撈取日 2026-09-11）。單價一律取民國 113–115 年（近三年）成交中位數，
已扣除車位、排除特殊關係交易與建商交屋期成交。<br>
本頁為市場資訊整理與分析，僅供參考，<b style="font-size:12px">不構成價格保證、投資建議或要約</b>，
亦非特定物件之銷售廣告。毛投報率未扣除管理費、稅賦、空置與裝修攤提，實際淨報酬將低於本頁數字。
個案成交條件差異極大，實際價格應以現場查看與個案評估為準。不動產價格受政策、利率與景氣影響，過去成交不代表未來表現。
</div></div></footer></body></html>"""

# ───────────────────────── 母頁 ─────────────────────────
rows = "".join(
 f'<tr><td><b>{d["n"]}</b><span class="sub">{d["addr"]}</span></td>'
 f'<td>{dot(d["tier"])}</td>'
 f'<td class="num"><b>{d["p"]:.1f}</b><span class="sub">含車位 {d["gross"]:.1f}</span></td>'
 f'<td class="num">{d["ping"]:.0f}<span class="sub">可用約 {round(d["ping"]*0.58)}–{round(d["ping"]*0.64)}</span></td>'
 f'<td class="num"><b>{money(d["tot"])}</b></td>'
 f'<td class="num">{(f"{d[chr(121)]:.2f}%" if d["y"] else "—")}</td>'
 f'<td class="num">{d["age"] if isinstance(d["age"],str) else str(d["age"])+" 年"}</td>'
 f'<td class="num">{d["fl"]}／{d["hh"]}</td></tr>' for d in D)

bcards = "".join(
 (f'<a class="bcard" href="office/{SLUG[d["n"]]}.html">' if d["n"] in LIVE else '<div class="bcard">')
 + f'<div class="nm"><span style="font-size:12px;color:var(--mute);font-family:\'Noto Sans TC\';font-weight:400;display:block;margin-bottom:3px">{dot(d["tier"])}</span>{d["n"]}</div>'
   f'<div class="mt">{d["addr"]}｜{d["ping"]:.0f} 坪｜{d["fl"]} 樓</div>'
   f'<div class="pr">{d["p"]:.1f} <span style="font-size:13px;color:var(--mute);font-family:\'Noto Sans TC\'">萬/坪</span></div>'
 + (f'<div class="mt" style="color:var(--gold);margin-top:6px">看完整分析 →</div></a>'
    if d["n"] in LIVE else '<div class="soon" style="margin-top:6px">完整分析即將上線</div></div>')
 for d in D)

# 位置分佈圖（沿用報告產生器的座標）
gsrc = open(HERE / "七期商辦整體分析報告產生器.py", encoding="utf-8").read()
geo = gsrc[gsrc.index("# ── 地理示意"):gsrc.index('p2=f"""')]
ns = {"D": D, "TIER": {"入門": TIER["入門"], "中階": TIER["中階"], "頂級": TIER["頂級"]}}
exec(geo, ns); GY = ns["gy"]

LD_HOME = """<script type="application/ld+json">
{"@context":"https://schema.org","@type":"RealEstateAgent","name":"助哥｜七期商辦",
"description":"台中七期九大商辦完整實價登錄分析：單價、坪數、總價、投報率、位置分佈。近三年成交中位、扣除車位重算。",
"url":"%s/qiqi-office.html","slogan":"不賣房子，賣判斷",
"areaServed":[{"@type":"Place","name":"台中七期重劃區"},{"@type":"Place","name":"台中市西屯區"}],
"knowsAbout":["七期商辦","商辦實價登錄","商辦投報率","企業總部","辦公室買賣","商辦估價"],
"sameAs":["%s"]}</script>""" % (SITE, LINE)

home = head("台中七期商辦全解析｜九大建案實登比較・投報率・位置分佈｜助哥",
 "台中七期九棟商辦完整實價登錄分析：單價（含／不含車位）、坪數、典型總價、毛投報率與位置分佈。近三年成交中位數，逐筆扣車位重算。",
 f"{SITE}/qiqi-office.html",
 "七期商辦,台中商辦,七期商辦實價登錄,商辦投報率,聯聚中雍,聯聚中維,市政壹號廣場,NTC國家商貿中心,CBD時代廣場,鼎盛BHW,親家T-POWER,親家T3,豐邑市政都心,台中辦公室買賣,企業總部",
 LD_HOME) + nav() + f"""
<header class="hero"><div class="wrap">
 <div class="tag">TAICHUNG 7TH DISTRICT ／ OFFICE</div>
 <h1>台中七期商辦<br>九棟，我全部重算過</h1>
 <p class="lead">不是抓網路上的均價。九案 2,700+ 筆實價登錄逐筆重算——
 扣掉車位、排除建商交屋期那批低價、只取近三年成交。<br>你看到的是現在真正成交得到的價格。</p>
 <div class="kpis">
  <div class="kpi"><div class="v">9 棟</div><div class="l">七期主要商辦全建檔</div></div>
  <div class="kpi"><div class="v">2,700<span style="font-size:17px">+</span></div><div class="l">實價登錄筆數</div></div>
  <div class="kpi"><div class="v">113–115</div><div class="l">行情基準年（近三年）</div></div>
  <div class="kpi"><div class="v">2.93<span style="font-size:17px">%</span></div><div class="l">毛投報中位數</div></div>
 </div>
</div></header>

<section id="table"><div class="wrap">
 <div class="sec-tag">QUICK TABLE</div><h2 class="sec-title">九案速查</h2>
 <p class="sec-lead">單價上排為<b>不含車位</b>（估價與議價用），下排為<b>含車位</b>（總價÷總面積，多數公開查詢平台採此口徑）。
 兩者差 +0.8%～+10.4%，比價前先確認對方用哪一種。</p>
 <div class="legend"><span>{dot("入門")}　總價 2,500 萬以下</span><span>{dot("中階")}　2,900–4,400 萬</span><span>{dot("頂級")}　9,700 萬以上</span></div>
 <div class="tblwrap"><table>
  <tr><th>建案</th><th>級別</th><th class="num">單價 萬/坪</th><th class="num">坪數</th>
      <th class="num">典型總價</th><th class="num">毛投報</th><th class="num">屋齡</th><th class="num">樓/戶</th></tr>
  {rows}
 </table></div>
 <p style="font-size:12.5px;color:var(--mute);margin-top:10px">
 典型總價＝單價 × 坪數（房屋部分，車位另計）。坪數為扣車位後之權狀坪、含公設；「可用約」為扣除公設（約 36–42%）後之估算。
 聯聚中維與市政壹號為預售案，尚無租賃實績故無投報率。</p>
</div></section>

<section id="map" style="background:#faf7ef"><div class="wrap">
 <div class="sec-tag">LOCATION</div><h2 class="sec-title">九棟在哪裡</h2>
 <p class="sec-lead">南北向由西而東：朝富路 → 河南路 → 惠來路 → 惠中路 → 文心路。</p>
 <div class="legend"><span>{dot("入門")}入門</span><span>{dot("中階")}中階</span><span>{dot("頂級")}頂級總部</span>
  <span><span class="dot" style="background:#fff;border:2px solid #a9997a"></span>地標</span></div>
 <div style="background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px 10px;overflow-x:auto">
  <svg viewBox="0 0 600 322" style="width:100%;min-width:620px;height:auto">{GY}</svg></div>
 <p style="font-size:12.5px;color:var(--mute);margin-top:10px">示意圖，非按實際比例；各案定位經在地核對。為求清晰，市政北三／五／六路與惠民路、惠文路未繪。</p>
</div></section>
"""

home += f"""
<section><div class="wrap">
 <div class="sec-tag">FINDINGS</div><h2 class="sec-title">三個跟你想的不一樣的發現</h2>
 <div class="cards">
  <div class="card"><h3>① 分級要看總價，不是單價</h3>
   <div class="big">80.6 萬 → 2,110 萬</div>
   <p>市政壹號單價全區最高，但一戶只有 26 坪，典型總價 2,110 萬，是九案門檻最低的。
   聯聚中雍單價 67.4 萬比它便宜，一戶 224 坪，總價 1.51 億。<br>
   <b>決定你進不進得來的是總價，單價只決定每坪成本。</b></p></div>
  <div class="card"><h3>② 十年前的價格，今天買不到</h3>
   <div class="big">1.76 倍</div>
   <p>鼎盛 BHW 建商交屋那幾年成交中位 28.51 萬，現在 50.31 萬。
   九案交屋潮到現行行情差 1.20～1.76 倍。<br>
   <b>聽到「某某商辦才 28 萬」，先問一句：那是哪一年的？</b></p></div>
  <div class="card"><h3>③ 投報率已經壓到 3% 以下</h3>
   <div class="big">2.93%</div>
   <p>用近三年成交價與租金重算，七棟毛投報 2.68–4.29%，中位僅 2.93%，<b>四棟低於 3%</b>。
   不是租金變差，是售價漲得比租金快太多。<br>
   <b>現在買七期商辦，買的是自用、門面與保值，不是租金收益。</b></p></div>
 </div>
 <div class="warn" style="margin-top:22px">
  <b>◆ 有人報你 3.5%、4% 的七期商辦投報率？先問他用的是哪一年的成交價。</b><br>
  用十年前交屋潮的價格當成本，投報率當然漂亮——但那個價格今天買不到。
 </div>
</div></section>

<section style="background:#faf7ef"><div class="wrap">
 <div class="sec-tag">HOW TO CHOOSE</div><h2 class="sec-title">先問坪數，比先問預算快</h2>
 <p class="sec-lead">客戶常低估「自己要的坪數在七期值多少」。先確定要幾坪，九案立刻刷掉一半。</p>
 <div class="tblwrap"><table style="min-width:560px">
  <tr><th>你需要的坪數</th><th>可選建案</th><th>備註</th></tr>
  <tr><td><b>25–35 坪</b><span class="sub">可用約 15–22 坪</span></td><td>市政壹號廣場</td><td>全區唯一小坪數新案（預售）</td></tr>
  <tr><td><b>60–75 坪</b><span class="sub">可用約 35–48 坪</span></td><td>親家 T3、親家 T-POWER、NTC 國家商貿中心</td><td>選擇最多的區間</td></tr>
  <tr><td><b>78–102 坪</b><span class="sub">可用約 45–65 坪</span></td><td>鼎盛 BHW、CBD 時代廣場、豐邑市政都心廣場</td><td>中大型辦公需求</td></tr>
  <tr><td><b>130–160 坪</b><span class="sub">可用約 75–102 坪</span></td><td>聯聚中維大廈</td><td>亦有 80 坪級小戶型</td></tr>
  <tr><td><b>220 坪以上／整層</b><span class="sub">可用約 128 坪以上</span></td><td>聯聚中雍大廈</td><td>可兩戶合併約 448 坪，全區唯一</td></tr>
 </table></div>
 <div class="note" style="margin-top:20px">
  <b>◆ 別忽略公設比。</b>七期商辦公設比約 <b>36%–42%</b>，每買一坪實際可用約 0.58–0.64 坪。
  大廳、電梯廳、機電都在公設裡，這是商辦常態，不是缺點——但算「實際每坪可用成本」時要納入。
  公設比最低的是 CBD 時代廣場（36.17%）。
 </div>
</div></section>

<section id="buildings"><div class="wrap">
 <div class="sec-tag">NINE BUILDINGS</div><h2 class="sec-title">逐案分析</h2>
 <p class="sec-lead">每一棟的完整實登明細、逐年行情、交屋潮對照、樓層溢價與優劣分析。</p>
 <div class="bldg">{bcards}</div>
</div></section>

<section><div class="wrap"><div class="cta">
 <h2>想知道你那棟現在實際成交多少？</h2>
 <p>不管你是要買、要賣，還是只是想知道手上這戶現在值多少——<br>我用實價登錄查給你看，不用先決定什麼。</p>
 <a class="btn btn-primary" href="{LINE}" target="_blank" rel="noopener">加 LINE 聊聊 →</a>
</div></div></section>
""" + footer()

(ROOT / "qiqi-office.html").write_text(home, encoding="utf-8")
print("✅ qiqi-office.html")

# ───────────────────────── 子頁 ─────────────────────────
# 每案敘事（逐棟補；未填者子頁不產出）
NARR = {
"NTC國家商貿中心": dict(
 tagline="中階級距裡租金最強的一棟，但樓層完全不影響價格",
 wave=("≤107", 228, 32.40, 1.54),
 floor=[("低樓層 ≤9F", 17, 42.68), ("高樓層 26F↑", 9, 42.86)], floor_gap=0.4,
 zone="惠民段・第五種新市政中心專用區",
 pros=["中階級距中<b>租金最強</b>（1,297 元／坪），毛投報 3.12% 為中階最佳",
       "73 坪是市場最泛用的中型坪數，格局好配置",
       "另有大坪數戶，實登最大達 838 坪，<b>擴充彈性大</b>",
       "屋齡 8 年，設備仍新，近三年成交 24 筆、流通性佳"],
 cons=["<b>樓層溢價僅 +0.4%</b>——高樓層要溢價，實登上站不住腳",
       "交屋潮 32.40 → 現行 49.90，<b>達 1.54 倍</b>，看錯年份極易誤判行情",
       "243 戶，出入相對較雜",
       "單價 49.9 萬已接近中階天花板，議價空間相對有限"],
 who=[("30–50 人成長期企業", "73 坪、典型總價 3,664 萬，是中階最主流的配置"),
      ("想壓低持有成本的收租方", "中階裡投報最高的 3.12%，租金端最穩"),
      ("預期會擴編的公司", "同棟有大坪數戶可承接，不用搬離")],
 buyer="議價時把重點放在<b>坪數、格局、車位席數與總價</b>——這棟樓層幾乎不影響單價，"
       "屋主若用「我這戶樓層高」要溢價，實登數據不支持。",
 owner="這棟的優勢是<b>租金</b>，不是樓層。跟買方談，主打 1,297 元／坪的租金實績與 3.12% 投報，"
       "那是中階九棟裡最強的一組數字。"),
}

def sub(d):
    N = NARR[d["n"]]; slug = SLUG[d["n"]]
    ymax = max(v[1] for v in d["yrs"].values()) if d["yrs"] else 1
    ybars = "".join(
     f'<div class="yrow"><span>{y} 年</span>'
     f'<span class="bar" style="width:{v[1]/ymax*100:.0f}%;background:{TIER[d["tier"]]};opacity:{.45+.55*(int(y)-107)/8:.2f}"></span>'
     f'<span class="num"><b>{v[1]:.1f}</b> <span style="font-size:11px;color:var(--mute)">n={v[0]}</span></span></div>'
     for y, v in sorted(d["yrs"].items()))
    pros = "".join(f"<li>{x}</li>" for x in N["pros"])
    cons = "".join(f"<li>{x}</li>" for x in N["cons"])
    who = "".join(f'<div class="card"><h3>{a}</h3><p>{b}</p></div>' for a, b in N["who"])
    fl = "".join(f'<tr><td>{a}</td><td class="num">{n} 筆</td><td class="num"><b>{v:.2f}</b></td></tr>'
                 for a, n, v in N["floor"])
    ld = """<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Article","headline":"%s 實價登錄分析",
"description":"%s 近三年實價登錄行情、坪數、總價、投報率與逐年走勢分析。",
"author":{"@type":"Person","name":"助哥"},"datePublished":"2026-09-12",
"mainEntityOfPage":"%s/office/%s.html"}</script>""" % (d["n"], d["n"], SITE, slug)
    html = head(f'{d["n"]} 實價登錄分析｜近三年行情・坪數・投報率｜助哥七期商辦',
      f'{d["n"]}（{d["addr"]}）近三年實登行情 {d["p"]:.1f} 萬/坪、主力 {d["ping"]:.0f} 坪、典型總價 {money(d["tot"])}、毛投報 {d["y"]:.2f}%。逐筆扣車位重算。',
      f"{SITE}/office/{slug}.html",
      f'{d["n"]},{d["n"]}實價登錄,{d["n"]}行情,{d["n"]}坪數,{d["n"]}投報率,七期商辦,台中商辦,{d["addr"]}',
      ld) + nav(1) + f"""
<header class="hero"><div class="wrap">
 <div class="tag">{dot(d["tier"])}　／　{N["zone"]}</div>
 <h1>{d["n"]}</h1>
 <p class="lead">{d["addr"]}｜{d["dev"]}｜屋齡 {d["age"]} 年｜{d["fl"]} 樓｜{d["hh"]} 戶<br>
 <b style="color:var(--gold-light)">{N["tagline"]}</b></p>
 <div class="kpis">
  <div class="kpi"><div class="v">{d["p"]:.1f}</div><div class="l">萬/坪（不含車位）<br>含車位 {d["gross"]:.1f}</div></div>
  <div class="kpi"><div class="v">{d["ping"]:.0f} 坪</div><div class="l">主力坪數<br>可用約 {round(d["ping"]*0.58)}–{round(d["ping"]*0.64)} 坪</div></div>
  <div class="kpi"><div class="v">{money(d["tot"])}</div><div class="l">典型總價<br>房屋，車位另計</div></div>
  <div class="kpi"><div class="v">{d["y"]:.2f}%</div><div class="l">毛投報<br>租金 {d["rent"]:,} 元/坪/月</div></div>
 </div>
</div></header>

<section><div class="wrap">
 <div class="sec-tag">PRICE TREND</div><h2 class="sec-title">逐年行情：這就是為什麼不能用「平均」</h2>
 <p class="sec-lead">屋主中古轉售的淨單價中位數（已扣車位、已排除建商交屋期）。
 行情逐年變動，把多年平均在一起會嚴重失真——本站一律只採近三年。</p>
 <div style="background:#fff;border:1px solid var(--line);border-radius:14px;padding:22px 24px">{ybars}</div>
 <div class="note" style="margin-top:20px">
  <b>◆ 交屋潮 ≠ 行情。</b>本案建商交屋期（民國 {N["wave"][0]} 年、{N["wave"][1]} 筆）成交中位僅
  <b>{N["wave"][2]:.2f} 萬/坪</b>，與現行行情 <b>{d["p"]:.1f} 萬/坪</b> 相差 <b>{N["wave"][3]:.2f} 倍</b>。
  查行情時看到偏低的數字，先確認是哪一年。
 </div>
</div></section>

<section style="background:#faf7ef"><div class="wrap">
 <div class="sec-tag">FLOOR PREMIUM</div><h2 class="sec-title">樓層值不值錢？</h2>
 <div class="tblwrap" style="max-width:520px"><table style="min-width:380px">
  <tr><th>樓層帶</th><th class="num">筆數</th><th class="num">淨單價中位</th></tr>{fl}
  <tr style="background:var(--cream-dark)"><td><b>高樓層溢價</b></td><td class="num">—</td>
      <td class="num"><b style="color:{TIER[d["tier"]]}">+{N["floor_gap"]}%</b></td></tr>
 </table></div>
 <p style="font-size:12.5px;color:var(--mute);margin-top:10px">
 採中古轉售全樣本計算（近三年分層樣本太少），會受「不同樓層在不同年份成交」影響，僅供議價定調。</p>
</div></section>

<section><div class="wrap">
 <div class="sec-tag">PROS &amp; CONS</div><h2 class="sec-title">優勢與要留意的地方</h2>
 <p class="sec-lead">「要留意」欄寫的是實登數據看得出來的事實，不是缺點評價。沒有完美的案子，只有適不適合你。</p>
 <div class="cards">
  <div class="card" style="border-top:3px solid var(--t1)"><h3 style="color:var(--t1)">優　勢</h3><ul style="margin-left:18px">{pros}</ul></div>
  <div class="card" style="border-top:3px solid var(--t3)"><h3 style="color:var(--t3)">要留意</h3><ul style="margin-left:18px">{cons}</ul></div>
 </div>
</div></section>

<section style="background:#faf7ef"><div class="wrap">
 <div class="sec-tag">WHO FITS</div><h2 class="sec-title">這棟適合誰</h2>
 <div class="cards">{who}</div>
 <div class="cards" style="margin-top:18px">
  <div class="note"><b>◆ 如果你是買方</b><br>{N["buyer"]}</div>
  <div class="note"><b>◆ 如果你是屋主</b><br>{N["owner"]}</div>
 </div>
</div></section>

<section><div class="wrap"><div class="cta">
 <h2>想知道你這戶現在實際值多少？</h2>
 <p>{d["n"]} 我手上有近三年 {d["nn"]} 筆買賣、{d["rn"]} 筆租賃的完整實登明細。<br>
 告訴我樓層跟坪數，我算給你看。</p>
 <a class="btn btn-primary" href="{LINE}" target="_blank" rel="noopener">加 LINE 聊聊 →</a>
 <div style="margin-top:18px"><a class="btn btn-ghost" style="color:#e6dfcd;border-color:#4a6255" href="../qiqi-office.html#buildings">← 回九案總覽</a></div>
</div></div></section>
""" + footer(1)
    (ROOT / "office").mkdir(exist_ok=True)
    (ROOT / "office" / f"{slug}.html").write_text(html, encoding="utf-8")
    return slug

for d in D:
    if d["n"] in NARR:
        print("✅ office/%s.html（%s）" % (sub(d), d["n"]))
