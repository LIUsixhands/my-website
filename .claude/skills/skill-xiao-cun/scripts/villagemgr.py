#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
villagemgr.py — AI 員工「小村」的養生村行銷管線工具
Sixhands Studio AI數字員工 🦞

零安裝、不連網、不用裝任何套件。所有資料都是你電腦裡的 CSV。

    python3 villagemgr.py init    --dir "./養生村資料"
    python3 villagemgr.py check   --dir "./養生村資料"
    python3 villagemgr.py funnel  --dir "./養生村資料"
    python3 villagemgr.py content --dir "./養生村資料"
    python3 villagemgr.py report  --dir "./養生村資料" --period "2026年9月"
    python3 villagemgr.py scan    --file "貼文草稿.txt"
"""
import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

ENC = "utf-8-sig"

# ─────────────────────────────────────────── 表格定義

TABLES = {
    "1_潛在名單.csv": [
        "編號", "建檔日期", "家屬稱呼", "聯絡方式", "長輩稱呼", "長輩狀況",
        "觸發事件", "急迫性", "決策者人數", "來源", "目前階段",
        "最後聯繫日", "下次聯繫日", "最不放心的事", "備註",
    ],
    "2_參訪試住紀錄.csv": [
        "編號", "名單編號", "類型", "日期", "參與人", "最不放心的事",
        "我們的回應", "試住天數", "結果", "下一步", "下一步日期", "負責人",
    ],
    "3_內容排程.csv": [
        "編號", "預計發布日", "類型", "主題", "平台", "狀態",
        "素材需求", "是否需同意書", "同意書是否取得", "實際發布日", "備註",
    ],
    "4_通路成效.csv": [
        "月份", "來源", "諮詢數", "參訪數", "試住數", "簽約數", "備註",
    ],
}

SAMPLES = {
    "1_潛在名單.csv": [{
        "編號": "L-001", "建檔日期": "2026-09-01", "家屬稱呼": "★範例｜王小姐（女兒）",
        "聯絡方式": "LINE: wang123", "長輩稱呼": "王媽媽", "長輩狀況": "可自行走動、輕度失智",
        "觸發事件": "上週跌倒送急診", "急迫性": "一個月內", "決策者人數": "3",
        "來源": "Google搜尋", "目前階段": "已參訪", "最後聯繫日": "2026-09-05",
        "下次聯繫日": "2026-09-08", "最不放心的事": "怕媽媽不適應、晚上沒人顧",
        "備註": "★這是範例列，請刪掉再填自己的",
    }],
    "2_參訪試住紀錄.csv": [{
        "編號": "V-001", "名單編號": "L-001", "類型": "參訪", "日期": "2026-09-05",
        "參與人": "王小姐＋弟弟", "最不放心的事": "夜間人力", "我們的回應": "已提供夜班配置與送醫流程",
        "試住天數": "", "結果": "有意願", "下一步": "提試住3天", "下一步日期": "2026-09-08",
        "負責人": "★範例列，請刪除",
    }],
    "3_內容排程.csv": [{
        "編號": "C-001", "預計發布日": "2026-09-02", "類型": "A", "主題": "這禮拜的菜",
        "平台": "FB/Google商家", "狀態": "待製作", "素材需求": "五道菜實拍",
        "是否需同意書": "否", "同意書是否取得": "-", "實際發布日": "",
        "備註": "★範例列，請刪除",
    }],
    "4_通路成效.csv": [{
        "月份": "2026-09", "來源": "★範例｜Google搜尋", "諮詢數": "12",
        "參訪數": "5", "試住數": "2", "簽約數": "1", "備註": "請刪除範例列",
    }],
}

STAGES = ["諮詢", "已參訪", "試住中", "家庭會議", "已簽約", "已入住"]
CLOSED = ["冷卻", "婉拒"]
ACTIVE = STAGES  # 需要有下次聯繫日的階段

DEFAULT_CONFIG = {
    "提醒天數": {
        "諮詢後未邀約參訪_天": 2,
        "長期名單再接觸_天": 30,
        "名單視為冷卻_天": 90,
    },
    "漏斗健康值": {
        "諮詢轉參訪率_下限": 0.40,
        "參訪轉試住率_下限": 0.30,
        "試住轉簽約率_下限": 0.60,
    },
    "內容配方": {"A": 8, "B": 5, "C": 4, "D": 2, "E": 1},
    "紅線關鍵字": [
        "治療", "療效", "改善失智", "延緩退化", "根治", "醫療級", "24小時醫護",
        "保證入住", "保證有床", "保證不跌倒", "零意外", "絕對安全",
        "保證返還", "保證獲利", "年化報酬", "可轉售", "可增值",
        "全台最大", "五星級", "業界第一", "唯一", "頂級",
        "倒數", "限時", "今天簽約",
    ],
}

DATA_CARD = {
    "_說明": "機構資料卡。所有文案的事實來源，沒填完的欄位小村不會替你猜。",
    "立案名稱": "", "對外品牌名": "", "立案字號": "", "主管機關": "",
    "服務類型": "", "核定床位數": 0, "目前入住數": 0,
    "地址": "", "電話": "", "LINE": "", "官網": "", "FB": "", "Google商家": "",
    "周邊": {"最近醫院": "", "車程分鐘": 0, "交通": ""},
    "房型": [{"名稱": "", "坪數": "", "床數": "", "月費": "", "目前空床": 0}],
    "費用": {
        "月費區間": "", "含": [], "不含": [],
        "保證金": "", "退費條件": "", "退費時程": "",
    },
    "人力": {"白班照顧比": "", "夜班照顧比": "", "護理配置": ""},
    "醫療": {"特約院所": "", "巡診頻率": "", "緊急送醫流程": "", "家屬通知機制": ""},
    "收案": {"收": [], "不收": []},
    "參訪": {"是否需預約": "", "帶看人": "", "時長": ""},
    "試住": {"是否提供": "", "天數": "", "費用": "", "是否折抵": ""},
    "評鑑": {"年度": "", "結果": "", "評鑑名稱": ""},
    "靈魂人物": "", "創辦故事": "",
}


# ─────────────────────────────────────────── 工具

def die(msg):
    print(f"❌ {msg}")
    sys.exit(1)


def load_config(d):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    for p in (os.path.join(d, "config.json"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "references", "config.json")):
        if os.path.exists(p):
            try:
                with open(p, encoding=ENC) as f:
                    user = json.load(f)
            except Exception:
                continue
            for k, v in user.items():
                if k.startswith("_"):
                    continue
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update({kk: vv for kk, vv in v.items() if not kk.startswith("_")})
                else:
                    cfg[k] = v
            break
    return cfg


def read_table(d, name):
    p = os.path.join(d, name)
    if not os.path.exists(p):
        die(f"找不到 {p}　→ 請先跑：python3 villagemgr.py init --dir \"{d}\"")
    with open(p, encoding=ENC, newline="") as f:
        rows = list(csv.DictReader(f))
    # 濾掉範例列
    return [r for r in rows if "★" not in "".join(str(v) for v in r.values())]


def pdate(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def pad(s, n):
    """以全形空白補齊，讓中文欄位對得齊。"""
    s = str(s)
    return s + "　" * max(0, n - len(s))


def bar(n, total, width=20):
    if total <= 0:
        return "░" * width
    filled = int(round(width * n / total))
    return "█" * filled + "░" * (width - filled)


# ─────────────────────────────────────────── init

def cmd_init(args):
    d = args.dir
    os.makedirs(d, exist_ok=True)
    made = []
    for name, cols in TABLES.items():
        p = os.path.join(d, name)
        if os.path.exists(p):
            print(f"⏭  已存在，跳過：{name}")
            continue
        with open(p, "w", encoding=ENC, newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for row in SAMPLES.get(name, []):
                w.writerow({c: row.get(c, "") for c in cols})
        made.append(name)

    card = os.path.join(d, "0_機構資料卡.json")
    if not os.path.exists(card):
        with open(card, "w", encoding="utf-8") as f:
            json.dump(DATA_CARD, f, ensure_ascii=False, indent=2)
        made.append("0_機構資料卡.json")

    print(f"\n✅ 建好了：{d}\n")
    for m in made:
        print(f"   ＋ {m}")
    print("""
下一步（照順序做）：
  1. 打開 0_機構資料卡.json，把「立案字號／服務類型／費用」三塊填完
     → 沒填完，小村不會替你寫任何對外文字
  2. 打開 references/開工前必問15題.md，一題一題問老闆
  3. 把現有的諮詢名單補進 1_潛在名單.csv（重點是「下次聯繫日」一定要填）
  4. 每天早上跑一次：python3 villagemgr.py check --dir "%s"
""" % d)


# ─────────────────────────────────────────── check

def cmd_check(args):
    d = args.dir
    cfg = load_config(d)
    today = pdate(args.today) if args.today else date.today()
    cold_days = int(cfg["提醒天數"].get("名單視為冷卻_天", 90))

    leads = read_table(d, "1_潛在名單.csv")
    visits = read_table(d, "2_參訪試住紀錄.csv")
    contents = read_table(d, "3_內容排程.csv")

    red, orange, yellow = [], [], []

    # 1. 名單跟進
    for r in leads:
        stage = (r.get("目前階段") or "").strip()
        if stage in CLOSED:
            continue
        who = f"{r.get('編號','?')} {r.get('家屬稱呼','')}／{r.get('長輩稱呼','')}".strip()
        nxt = pdate(r.get("下次聯繫日"))
        last = pdate(r.get("最後聯繫日")) or pdate(r.get("建檔日期"))
        worry = (r.get("最不放心的事") or "").strip()
        tail = f"　※他最不放心：{worry}" if worry else ""

        if nxt is None:
            if stage in ACTIVE:
                yellow.append(f"{who}（{stage or '未填階段'}）：**沒有下次聯繫日** → 現在就決定一個日期")
            continue
        gap = (today - nxt).days
        if gap > 0:
            line = f"{who}（{stage}）：逾期 {gap} 天未跟進（原訂 {nxt}）{tail}"
            (red if gap >= 3 else orange).append(line)
        elif gap == 0:
            orange.append(f"{who}（{stage}）：**今天**要聯繫{tail}")
        elif -3 <= gap < 0:
            yellow.append(f"{who}（{stage}）：{-gap} 天後要聯繫（{nxt}）")

        if last and (today - last).days >= cold_days and stage in ACTIVE:
            yellow.append(f"{who}：已 {(today-last).days} 天沒有聯繫 → 轉「長期名單」每月一則日常內容，或標記冷卻")

    # 2. 參訪／試住後沒有下一步
    for v in visits:
        nd = pdate(v.get("下一步日期"))
        vd = pdate(v.get("日期"))
        tag = f"{v.get('編號','?')} {v.get('類型','')}（{v.get('日期','')}）名單 {v.get('名單編號','')}"
        if not (v.get("下一步") or "").strip():
            yellow.append(f"{tag}：**沒有填下一步** → 參訪後沒有下一步＝這個案子已經死了")
        elif nd and (today - nd).days > 0:
            red.append(f"{tag}：下一步「{v.get('下一步')}」逾期 {(today-nd).days} 天")
        elif vd and not nd and (today - vd).days >= 2:
            orange.append(f"{tag}：{(today-vd).days} 天前參訪，還沒排下一步日期")

    # 3. 內容排程
    for c in contents:
        st = (c.get("狀態") or "").strip()
        pd_ = pdate(c.get("預計發布日"))
        if st in ("已發布", "取消") or (c.get("實際發布日") or "").strip():
            continue
        if pd_ and (today - pd_).days > 0:
            orange.append(f"內容 {c.get('編號','')}「{c.get('主題','')}」：預計 {pd_} 發布，已逾期 {(today-pd_).days} 天")
        elif pd_ and 0 <= (pd_ - today).days <= 3:
            need = (c.get("是否需同意書") or "").strip()
            got = (c.get("同意書是否取得") or "").strip()
            if need in ("是", "Y", "y") and got not in ("是", "Y", "y"):
                red.append(f"內容 {c.get('編號','')}「{c.get('主題','')}」：{pd_} 要發，**肖像同意書還沒拿到** → 不准發")
            else:
                yellow.append(f"內容 {c.get('編號','')}「{c.get('主題','')}」：{pd_} 要發，狀態＝{st or '未填'}")

    print(f"\n**🔴 立即處理 {len(red)} 件　🟠 三天內 {len(orange)} 件　🟡 補資料 {len(yellow)} 件**"
          f"　（{today}）\n")
    for title, items, icon in (("立即處理", red, "🔴"), ("三天內", orange, "🟠"), ("補資料", yellow, "🟡")):
        if items:
            print(f"## {icon} {title}（{len(items)}）")
            for i in items:
                print(f"- {icon} {i}")
            print()
    if not (red or orange or yellow):
        print("今天沒有待辦。把時間拿去打電話給現住民家屬 —— 那是最便宜的行銷。\n")
    else:
        print("＿只看 🔴，五分鐘處理完就下班。＿\n")


# ─────────────────────────────────────────── funnel

def cmd_funnel(args):
    d = args.dir
    cfg = load_config(d)
    leads = read_table(d, "1_潛在名單.csv")
    visits = read_table(d, "2_參訪試住紀錄.csv")
    if not leads:
        die("1_潛在名單.csv 裡沒有資料（範例列不算）。先把名單補進去。")

    trial_ids = {(v.get("名單編號") or "").strip()
                 for v in visits if (v.get("類型") or "").strip() == "試住"}
    visit_ids = {(v.get("名單編號") or "").strip()
                 for v in visits if (v.get("類型") or "").strip() == "參訪"}

    def idx(stage):
        return STAGES.index(stage) if stage in STAGES else -1

    src_stat = defaultdict(lambda: Counter())
    for r in leads:
        src = (r.get("來源") or "未填").strip() or "未填"
        sid = (r.get("編號") or "").strip()
        stage = (r.get("目前階段") or "").strip()
        s = src_stat[src]
        s["諮詢"] += 1
        if idx(stage) >= idx("已參訪") or sid in visit_ids:
            s["參訪"] += 1
        if idx(stage) >= idx("試住中") or sid in trial_ids:
            s["試住"] += 1
        if idx(stage) >= idx("已簽約"):
            s["簽約"] += 1
        if stage in CLOSED:
            s["流失"] += 1

    tot = Counter()
    for s in src_stat.values():
        tot.update(s)

    print(f"\n# 漏斗總覽（名單 {tot['諮詢']} 筆）\n")
    prev = None
    for k in ("諮詢", "參訪", "試住", "簽約"):
        n = tot[k]
        rate = f"　轉換 {n/prev*100:.0f}%" if prev else ""
        print(f"  {pad(k, 4)}{n:>4}  {bar(n, tot['諮詢'])}{rate}")
        prev = n if n else None
    print()

    lim = cfg["漏斗健康值"]
    checks = [
        ("諮詢 → 參訪", tot["參訪"], tot["諮詢"], lim.get("諮詢轉參訪率_下限", 0.40),
         "邀約話術有問題 → 讀 參訪試住轉單SOP.md 第 1 關（用『吃飯』不用『參觀』）"),
        ("參訪 → 試住", tot["試住"], tot["參訪"], lim.get("參訪轉試住率_下限", 0.30),
         "沒有試住方案，或帶看時沒開口 → 讀 第 3 關"),
        ("試住 → 簽約", tot["簽約"], tot["試住"], lim.get("試住轉簽約率_下限", 0.60),
         "試住期間沒有主動溝通 → 第 1 晚／第 3 天／結束前各聯繫一次"),
    ]
    print("## 健康度\n")
    for name, n, base, floor, advice in checks:
        if not base:
            print(f"- ⚪️ {name}：資料不足")
            continue
        r = n / base
        icon = "✅" if r >= floor else "🔴"
        print(f"- {icon} {name}：{r*100:.0f}%（下限 {floor*100:.0f}%）")
        if r < floor:
            print(f"     → {advice}")
    print()

    print("## 來源別（成交數高的那一條，才是明年要加碼的）\n")
    print(f"| 來源 | 諮詢 | 參訪 | 試住 | 簽約 | 諮詢→簽約 |")
    print(f"|:---|---:|---:|---:|---:|---:|")
    for src, s in sorted(src_stat.items(), key=lambda kv: (-kv[1]["簽約"], -kv[1]["諮詢"])):
        cr = f"{s['簽約']/s['諮詢']*100:.0f}%" if s["諮詢"] else "-"
        print(f"| {src} | {s['諮詢']} | {s['參訪']} | {s['試住']} | {s['簽約']} | {cr} |")
    print()

    未填 = src_stat.get("未填", Counter())["諮詢"]
    if 未填:
        print(f"⚠️  有 {未填} 筆沒填來源。**每一通諮詢都要問「你從哪裡知道我們的」** —— "
              f"這一題決定明年的預算怎麼花。\n")


# ─────────────────────────────────────────── content

def cmd_content(args):
    d = args.dir
    cfg = load_config(d)
    today = pdate(args.today) if args.today else date.today()
    rows = read_table(d, "3_內容排程.csv")
    ym = today.strftime("%Y-%m")

    month = [r for r in rows if (pdate(r.get("預計發布日")) or date(1900, 1, 1)).strftime("%Y-%m") == ym]
    cnt = Counter((r.get("類型") or "?").strip().upper()[:1] for r in month)
    recipe = cfg["內容配方"]
    names = {"A": "日常生活", "B": "知識型", "C": "人的故事", "D": "透明資訊", "E": "行動邀請"}

    print(f"\n# {ym} 內容排程（已排 {len(month)} 則）\n")
    for k in "ABCDE":
        want = int(recipe.get(k, recipe.get(f"{k}_日常生活", 0)) or 0)
        if not want:
            want = {"A": 8, "B": 5, "C": 4, "D": 2, "E": 1}[k]
        have = cnt.get(k, 0)
        icon = "✅" if have >= want else "🔴"
        gap = f"　缺 {want-have} 則" if have < want else ""
        print(f"  {icon} {k} {pad(names[k], 5)} {have}/{want} {bar(have, want)}{gap}")
    if cnt.get("E", 0) > int(recipe.get("E", 1)) + 1:
        print("\n  ⚠️ E（行動邀請）超量了。滿版都在招住民的粉專，家屬看了會怕 —— 上限 5%。")

    print(f"\n## 未來 7 天要發的\n")
    up = sorted(
        [r for r in rows
         if pdate(r.get("預計發布日")) and 0 <= (pdate(r["預計發布日"]) - today).days <= 7
         and (r.get("狀態") or "").strip() not in ("已發布", "取消")],
        key=lambda r: pdate(r["預計發布日"]))
    if not up:
        print("  （空的）→ 現在就從 內容矩陣與貼文模板庫.md 抽 5 則排進去。\n")
    for r in up:
        need = (r.get("是否需同意書") or "").strip()
        got = (r.get("同意書是否取得") or "").strip()
        flag = ""
        if need in ("是", "Y", "y"):
            flag = "　📄同意書已取得" if got in ("是", "Y", "y") else "　🔴**同意書未取得，不准發**"
        print(f"- {r.get('預計發布日')}｜{r.get('類型','?')}｜{r.get('主題','')}｜{r.get('平台','')}"
              f"｜{r.get('狀態','未填')}{flag}")
    print()


# ─────────────────────────────────────────── report

def cmd_report(args):
    d = args.dir
    today = pdate(args.today) if args.today else date.today()
    period = args.period or today.strftime("%Y年%m月")
    leads = read_table(d, "1_潛在名單.csv")
    visits = read_table(d, "2_參訪試住紀錄.csv")
    contents = read_table(d, "3_內容排程.csv")

    ym = None
    for fmt in ("%Y年%m月", "%Y-%m"):
        try:
            ym = datetime.strptime(period, fmt).strftime("%Y-%m")
            break
        except ValueError:
            continue
    ym = ym or today.strftime("%Y-%m")

    def in_month(s):
        dd = pdate(s)
        return bool(dd) and dd.strftime("%Y-%m") == ym

    new_leads = [r for r in leads if in_month(r.get("建檔日期"))]
    v_month = [v for v in visits if in_month(v.get("日期"))]
    tours = [v for v in v_month if (v.get("類型") or "").strip() == "參訪"]
    trials = [v for v in v_month if (v.get("類型") or "").strip() == "試住"]
    signed = [r for r in leads if (r.get("目前階段") or "").strip() in ("已簽約", "已入住")]
    published = [c for c in contents if in_month(c.get("實際發布日"))]

    src = Counter((r.get("來源") or "未填").strip() or "未填" for r in new_leads)

    print(f"""
# {period}　行銷月報
＿Sixhands Studio AI數字員工 🦞 小村＿

## 一、數字
| 項目 | 本月 |
|:---|---:|
| 新增諮詢 | {len(new_leads)} |
| 參訪 | {len(tours)} |
| 試住 | {len(trials)} |
| 累計已簽約／已入住 | {len(signed)} |
| 內容發布 | {len(published)} 則 |

## 二、名單來源
""")
    if src:
        for k, v in src.most_common():
            print(f"- {k}：{v} 筆　{bar(v, max(src.values()), 12)}")
    else:
        print("- （本月沒有新增名單，或建檔日期沒填）")

    print("\n## 三、家屬最不放心的事（原話，這是下個月的內容題目）\n")
    worries = [(r.get("最不放心的事") or "").strip() for r in leads]
    worries += [(v.get("最不放心的事") or "").strip() for v in v_month]
    worries = [w for w in worries if w]
    if worries:
        for w, n in Counter(worries).most_common(8):
            print(f"- 「{w}」{'　×' + str(n) if n > 1 else ''}")
        print("\n→ 出現最多次的那一句，就是下個月**知識型內容（B 類）的標題**。")
    else:
        print("- （沒有紀錄）→ 帶看結束一定要問：「你今天回去，最不放心的是哪一件事？」")

    print("""
## 四、下個月動作
- [ ] 把上面出現最多次的擔憂，寫成一則 B 類知識型內容
- [ ] 來源第一名的通路，加碼；掛零的通路，檢討或收掉
- [ ] 現住民家屬本月回報是否都做了（這是成本最低的行銷）
- [ ] 跑一次 funnel，看哪一段轉換率跌破下限

＿本報表為內部管理用，對外引用任何數字前請自行複核。＿
""")


# ─────────────────────────────────────────── scan

def cmd_scan(args):
    cfg = load_config(args.dir or ".")
    words = cfg.get("紅線關鍵字", DEFAULT_CONFIG["紅線關鍵字"])
    if args.file:
        if not os.path.exists(args.file):
            die(f"找不到檔案：{args.file}")
        text = open(args.file, encoding="utf-8", errors="ignore").read()
    elif args.text:
        text = args.text
    else:
        text = sys.stdin.read()

    lines = text.splitlines()
    hits = []
    for i, ln in enumerate(lines, 1):
        for w in words:
            if w in ln:
                hits.append((i, w, ln.strip()))

    print()
    if not hits:
        print("✅ 沒有掃到紅線關鍵字。")
        print("   但機器只看得到字，還有四件事要你自己確認：")
    else:
        print(f"🔴 掃到 {len(hits)} 處紅線關鍵字：\n")
        for i, w, ln in hits:
            print(f"  第 {i} 行　【{w}】")
            print(f"      {ln}")
        print("\n→ 換句方式看 references/法規紅線與合規話術.md 第二節逐字對照表。\n")
        print("   另外這四件事機器看不出來，請自己確認：")
    print("""   1. 有臉的照片，同意書拿到了嗎？（紅線 5）
   2. 有沒有寫立案字號、費用含不含項、個資告知？
   3. 這一則是寫給「子女／長輩／旁人」哪一種人看的？語言有沒有混？
   4. 這句話會讓家屬更輕鬆，還是更愧疚？
""")


# ─────────────────────────────────────────── main

def main():
    ap = argparse.ArgumentParser(
        description="小村 — 養生村行銷管線工具（Sixhands Studio AI數字員工 🦞）")
    sub = ap.add_subparsers(dest="cmd")

    def add(name, fn, help_):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--dir", default="./養生村資料", help="資料夾路徑")
        p.add_argument("--today", help="模擬日期 YYYY-MM-DD（測試用）")
        p.set_defaults(func=fn)
        return p

    add("init", cmd_init, "建立四張表與機構資料卡（只做一次）")
    add("check", cmd_check, "每天早上：今天要跟進誰、哪則內容要發")
    add("funnel", cmd_funnel, "漏斗轉換率與來源別成效")
    add("content", cmd_content, "本月內容配方缺口與未來七天排程")
    p = add("report", cmd_report, "月報")
    p.add_argument("--period", help='例："2026年9月"')
    p = add("scan", cmd_scan, "紅線關鍵字掃描（貼文發布前跑）")
    p.add_argument("--file", help="要掃的文字檔")
    p.add_argument("--text", help="直接貼一段文字")

    args = ap.parse_args()
    if not getattr(args, "func", None):
        ap.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
