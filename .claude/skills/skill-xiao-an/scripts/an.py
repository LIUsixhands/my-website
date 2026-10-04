#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小安（Xiao An）— 保險行銷專員　主程式
Sixhands Studio AI數字員工

子指令：
  check    合規禁語掃描（寫任何對外文字後必跑）
  remind   從客戶名單算出「本週該聯絡誰」（七大接觸節點）
  plan     產一個月的內容排程表（五大支柱輪播）
  init     在目前資料夾產出範本檔

鐵律：
  1. 小安的產出一律是「草稿」，須經所屬公司文宣審查核可後才可發布。
  2. 不產生費率、給付倍數、宣告利率等數字。
  3. 客戶名單含個資 —— 放本機碟、不放 iCloud／公開雲端。
"""
import argparse, csv, datetime as dt, json, os, re, shutil, sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL_DIR = os.path.join(SKILL_DIR, "templates")
BRAND = "Sixhands Studio AI數字員工　🦞　小安 Xiao An"

RED = "\033[91m"; YEL = "\033[93m"; GRN = "\033[92m"; DIM = "\033[2m"; OFF = "\033[0m"


# ============================================================ check：禁語掃描

# (正則, 風險等級, 為什麼不行, 改寫建議)
RULES = [
    # --- 保證與報酬 ---
    (r"保證(獲利|報酬|收益|領回|給付|賺)", "紅", "對商品報酬為誇大不實表示，屬明定懲處事由",
     "改為「依保單條款約定之給付項目」"),
    (r"穩賺|穩賺不賠|包賺|一定賺|絕對賺", "紅", "保證報酬類禁語", "刪除；改談保障功能"),
    (r"零風險|無風險|沒有風險", "紅", "風險揭露不實", "改為「風險與費用揭露請見商品說明書」"),
    (r"保本", "紅", "投資型商品不得表示保本", "刪除；並揭露「投資損益由要保人自行承擔」"),
    (r"一定(領得到|拿得到|給付)", "紅", "給付保證", "改為「符合條款約定條件時，依約定給付」"),
    (r"(年|投資|預期)?報酬率", "紅", "保單不得以報酬率行銷", "改為「宣告利率／預定利率」＋「不等於報酬率」"),
    (r"穩健增值|穩定增值|錢滾錢", "紅", "報酬暗示", "刪除"),
    # --- 存款代稱 ---
    (r"儲蓄險", "紅", "不得以易使人誤認為存款之名詞行銷保險",
     "正名為「人壽保險／年金保險／利率變動型壽險」"),
    (r"定存|定期存款|存款", "紅", "存款代稱／存款比較禁區", "整句刪除，不與存款比較"),
    (r"幫你存|幫您存|存錢|零存整付", "紅", "存款代稱", "改為「分期繳納保險費」"),
    (r"(複利|年利率|月利率)", "紅", "利率用語易誤導", "改為「宣告利率／預定利率」並註明不等於報酬率"),
    (r"利息", "紅", "存款代稱", "改為條款用語（增值回饋分享金／宣告利率）"),
    (r"比定存(好|高|划算)", "紅", "存款比較", "整句刪除"),
    # --- 最高級與比較 ---
    (r"最(好|強|便宜|優|划算|完整|推薦)", "紅", "最高級用語屬誇大宣傳",
     "改為具體功能描述，不做排名"),
    (r"第一名|業界第一|唯一一張|唯一的選擇", "紅", "最高級用語", "刪除"),
    (r"CP值最高|C/P值最高", "紅", "最高級用語", "改為「保費依年齡體況而異，以核保結果為準」"),
    (r"別家(都)?不賠|只有我們(才)?賠", "紅", "跨公司比較且屬理賠保證", "刪除"),
    # --- 急迫與停售 ---
    (r"停售|停賣|即將(下架|調整).{0,4}(快|趕快|把握)", "紅", "停售話術為主管機關列管之不當招攬",
     "中性告知：「〇年〇月起本類商品投保條件將調整，如需了解可與我聯繫」"),
    (r"最後(一張|機會|三天|倒數)|錯過不再|賣完就沒", "紅", "製造急迫性", "刪除急迫性用語"),
    (r"限時|名額有限|再不買就(漲|沒)", "紅", "製造急迫性", "刪除"),
    (r"先簽再說|先買再說", "紅", "未經需求分析之促成", "改為「建議先做需求分析再決定」"),
    # --- 理賠保證 ---
    (r"一定(賠|理賠)|全賠|都會賠|什麼都賠|有病(就|都)賠|住院就賠", "紅", "理賠保證",
     "改為「是否符合理賠要件，以保單條款及保險公司核定為準」"),
    (r"(一定|保證|絕對)(過|過得了)核保", "紅", "核保保證", "改為「核保結果由保險公司判斷」"),
    (r"幫你喬|我幫你橋|包在我身上", "紅", "暗示可影響核保理賠", "改為「協助準備文件與追蹤進度」"),
    # --- 稅務 ---
    (r"免(遺產)?稅|不用(繳|課)稅", "紅", "稅務保證；稽徵機關得依實質課稅原則個案認定",
     "改為「稅務效果因個案而異，以稽徵機關與稅務專業人員意見為準」"),
    (r"(合法)?節稅|避稅|不列入遺產|不算遺產", "紅", "稅務保證", "同上；結論交給會計師"),
    # --- 利誘 ---
    (r"(送|贈)(禮券|禮品|現金|紅包|好禮)|加LINE送|加賴送", "紅", "提供不當利益招攬",
     "改為知識型贈品（保單整理表／理賠文件清單）"),
    (r"退佣|折讓|回饋金|退佣金|抽成給你", "紅", "提供不當利益，屬明定違規", "整段刪除"),
    (r"抽獎|摸彩", "黃", "促銷型誘因，多數公司禁止", "改為知識型贈品"),
    # --- 告知義務 ---
    (r"不用寫|不用講|先不要講|不要告訴|隱瞞", "紅", "唆使不實告知／不告知，屬明定懲處事由",
     "改為「健康告知請照實填寫，這是保障您理賠權益最重要的一步」"),
    (r"代(你|您|客戶)?(簽|填)|我幫你簽|我幫你填", "紅", "代簽章、代填要保書屬明定懲處事由",
     "刪除；一律由客戶本人親填親簽"),
    # --- 轉保 ---
    (r"(解掉|解約)(舊|原)?(保單)?(再|改|換)?(買|保)|舊保單(很爛|過時|不好)", "紅",
     "不當勸誘轉保（churning）", "改為盤點缺口，並揭露解約可能損失"),
    # --- 其他 ---
    (r"月入(十|十萬|百萬|\d+萬)|年薪\d+|輕鬆賺|躺著賺", "紅", "增員不得承諾收入",
     "改為「收入依個人業績與公司制度而定，個別差異大」"),
    (r"包(治|好)|療效|根治|治癒", "紅", "療效宣稱（且與保險招攬無關）", "刪除"),
    (r"投資標的.{0,6}(保證|穩)", "紅", "投資型商品保證用語", "刪除並揭露損益自負"),
    # --- 提醒級 ---
    (r"家破人亡|等死|沒保險就完了", "黃", "恐懼行銷過當", "改為中性風險陳述"),
    (r"人人都(該|要)買|每個人都需要", "黃", "未經適合度評估之泛稱", "改為「是否適合須經需求分析評估」"),
]

# 必載事項
REQUIRED = [
    ("公司全名", r"(人壽|產物|保險經紀|保險代理|保經|保代|保險股份有限公司)"),
    ("登錄字號", r"登錄字號|登錄證字號|執業證字號"),
    ("免責尾註", r"(以保單條款|依保單條款|條款及保險公司核定|僅供參考|僅提供保險觀念參考)"),
]


def cmd_check(args):
    if os.path.exists(args.target):
        text = open(args.target, encoding="utf-8").read()
        src = args.target
    else:
        text = args.target
        src = "(命令列文字)"

    lines = text.splitlines() or [""]
    hits = []
    for i, line in enumerate(lines, 1):
        for pat, level, why, fix in RULES:
            for m in re.finditer(pat, line):
                hits.append((i, m.group(0), level, why, fix, line.strip()))

    red = [h for h in hits if h[2] == "紅"]
    yel = [h for h in hits if h[2] == "黃"]

    print(f"\n{'='*64}")
    print(f"🛡  小安・合規禁語掃描　來源：{src}")
    print(f"{'='*64}")

    if not hits:
        print(f"{GRN}✅ 禁語掃描：0 筆{OFF}")
    else:
        for i, word, level, why, fix, line in hits:
            c = RED if level == "紅" else YEL
            print(f"\n{c}[{level}] 第 {i} 行　「{word}」{OFF}")
            print(f"    原句：{DIM}{line[:70]}{OFF}")
            print(f"    為什麼：{why}")
            print(f"    ✅ 改寫：{fix}")

    # 必載檢查
    print(f"\n{'-'*64}\n必載事項：")
    missing = []
    for name, pat in REQUIRED:
        ok = re.search(pat, text)
        print(f"  {'✅' if ok else RED+'❌'+OFF} {name}")
        if not ok:
            missing.append(name)

    print(f"\n{'-'*64}")
    print(f"結果：禁語 紅 {len(red)} 筆 / 黃 {len(yel)} 筆　必載缺 {len(missing)} 項")
    if red or missing:
        print(f"{RED}⛔ 不可送審。請先修正紅字與必載事項。{OFF}")
    elif yel:
        print(f"{YEL}⚠️  可送審，但黃字建議調整。{OFF}")
    else:
        print(f"{GRN}✅ 可送審。{OFF}")
    print(f"\n{DIM}※ 通過本掃描 ≠ 可以發布。仍須經所屬公司文宣審查核可。{OFF}")
    print(f"{DIM}{BRAND}{OFF}\n")
    return 1 if (red or missing) else 0


# ============================================================ remind：接觸節點

FREQ_DAYS = {"A": 90, "B": 180, "C": 90, "D": 365}


def _md_next(md, today):
    """MM-DD → 下一次發生的日期"""
    try:
        m, d = [int(x) for x in md.split("-")]
    except Exception:
        return None
    for y in (today.year, today.year + 1):
        try:
            cand = dt.date(y, m, d)
        except ValueError:
            return None
        if cand >= today:
            return cand
    return None


def _date(s):
    try:
        return dt.datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def cmd_remind(args):
    today = dt.date.today()
    horizon = today + dt.timedelta(days=args.days)
    if not os.path.exists(args.csvfile):
        print(f"找不到 {args.csvfile}。先跑：python3 an.py init", file=sys.stderr)
        return 2

    tasks = []
    with open(args.csvfile, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            name = (r.get("稱呼") or r.get("客戶代號") or "").strip()
            if not name:
                continue
            if (r.get("停止聯絡") or "").strip() in ("是", "Y", "y", "TRUE", "true"):
                continue
            grp = (r.get("分群") or "C").strip().upper()[:1] or "C"

            # 1 生日
            d = _md_next((r.get("生日(MM-DD)") or "").strip(), today)
            if d and d <= horizon:
                tasks.append((d, name, grp, "生日", "純祝福一句話，不夾帶任何商品"))

            # 2 保單週年
            eff = _date(r.get("保單生效日(YYYY-MM-DD)") or "")
            if eff:
                d = _md_next(eff.strftime("%m-%d"), today)
                if d and d <= horizon:
                    yrs = d.year - eff.year
                    tasks.append((d, name, grp, f"保單週年（滿{yrs}年）",
                                  "「要不要看一眼受益人」；不推商品"))

            # 3 續期（提前 10 天）
            d = _md_next((r.get("續期扣款日(MM-DD)") or "").strip(), today)
            if d and (d - dt.timedelta(days=10)) <= horizon:
                tasks.append((d - dt.timedelta(days=10), name, grp, "續期提醒",
                              f"扣款日 {d}，提醒帳戶餘額，避免斷繳失效"))

            # 4 繳費期滿（提前 30 天）
            due = _date(r.get("繳費期滿(YYYY-MM-DD)") or "")
            if due:
                d = due - dt.timedelta(days=30)
                if today <= d <= horizon:
                    tasks.append((d, name, grp, "繳費期滿前",
                                  "說明後續權益；🚨 不趁機推轉保"))

            # 5 人生事件
            ev = (r.get("人生事件") or "").strip()
            if ev:
                tasks.append((today, name, grp, f"人生事件：{ev}",
                              "受益人與需求變化提醒"))

            # 6 逾期未聯絡
            last = _date(r.get("最近聯絡日(YYYY-MM-DD)") or "")
            lim = FREQ_DAYS.get(grp, 90)
            if last and (today - last).days > lim:
                tasks.append((today, name, grp,
                              f"逾期未聯絡（{(today-last).days}天／{grp}群上限{lim}天）",
                              "軟性問候，不談商品"))
            elif not last:
                tasks.append((today, name, grp, "從未記錄聯絡", "建立第一次接觸"))

    tasks.sort(key=lambda t: (t[0], t[2]))
    print(f"\n{'='*70}")
    print(f"🛡  小安・接觸節點清單　{today} ~ {horizon}（{args.days} 天）")
    print(f"{'='*70}")
    if not tasks:
        print("這段期間沒有到期節點。")
    cur = None
    for d, name, grp, kind, how in tasks:
        if d != cur:
            cur = d
            tag = "【今天】" if d == today else ""
            print(f"\n{GRN}▎{d}（{'一二三四五六日'[d.weekday()]}）{tag}{OFF}")
        print(f"   [{grp}] {name}　{kind}")
        print(f"        {DIM}→ {how}{OFF}")
    print(f"\n{'-'*70}")
    print(f"共 {len(tasks)} 件。理賠結案後 7 天的關懷，是轉介轉換率最高的時刻。")
    print(f"{DIM}{BRAND}{OFF}\n")
    return 0


# ============================================================ plan：內容排程

PILLARS = [
    ("理賠實務", ["出院前必問的三件事", "診斷證明書要寫什麼", "收據正本副本差在哪",
                  "理賠卡關的五個原因", "醫療費用明細去哪拿"]),
    ("除外陷阱", ["等待期是什麼", "「意外」不是你想的那個意外", "既往症與批註除外",
                  "除外責任怎麼看", "健康告知沒寫會怎樣"]),
    ("盤點工具", ["保單三個人搞不清楚", "受益人該更新的四個時機", "怎麼查自己有幾張保單",
                  "一張表看懂你的保障分類", "保單健檢五步驟"]),
    ("人生節點", ["第一份工作先看三件事", "結婚後受益人怎麼調", "第一個小孩出生的優先順序",
                  "房貸下來那天該想什麼", "父母年紀大了先確認三份文件"]),
    ("個人品牌", ["我為什麼做這一行", "我的三個原則", "這週我陪客戶做了什麼",
                  "我怎麼服務：從盤點到理賠", "被拒絕的那一天"]),
]
WD = "一二三四五六日"


def cmd_plan(args):
    y, m = [int(x) for x in args.month.split("-")]
    d = dt.date(y, m, 1)
    rows, idx = [], 0
    while d.month == m:
        if d.weekday() in (0, 2, 4, 6):  # 一三五日
            pillar, topics = PILLARS[idx % len(PILLARS)]
            topic = topics[(idx // len(PILLARS)) % len(topics)]
            plat = "FB+IG" if d.weekday() in (0, 4) else ("IG" if d.weekday() == 2 else "FB")
            fmt = "長文+圖卡" if "+" in plat else ("圖卡" if plat == "IG" else "長文")
            rows.append([d.strftime("%Y-%m-%d"), WD[d.weekday()], pillar, topic,
                         plat, fmt, "草稿", "", "", "", ""])
            idx += 1
        d += dt.timedelta(days=1)

    out = args.out or f"內容排程_{args.month}.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["日期", "星期", "支柱", "主題", "平台", "格式", "狀態",
                    "送審日", "核可日", "發布日", "備註"])
        w.writerows(rows)

    print(f"\n🛡  小安・{args.month} 內容排程（{len(rows)} 則）→ {out}\n")
    for r in rows:
        print(f"  {r[0]}（{r[1]}）{r[2]:<6}｜{r[3]:<22}｜{r[4]}")
    print(f"\n{DIM}狀態流程：草稿 → 送審 → 核可 → 發布。核可前不得發布。{OFF}")
    print(f"{DIM}{BRAND}{OFF}\n")
    return 0


# ============================================================ init

def cmd_init(args):
    n = 0
    for fn in sorted(os.listdir(TPL_DIR)):
        dst = os.path.join(os.getcwd(), fn)
        if os.path.exists(dst) and not args.force:
            print(f"  略過（已存在）：{fn}")
            continue
        shutil.copy(os.path.join(TPL_DIR, fn), dst)
        print(f"  ✅ {fn}")
        n += 1
    print(f"\n產出 {n} 個檔案。")
    print("下一步：填 業務員資料卡.json 的【必填】欄位（身分／公司全名／登錄字號／審查流程）。")
    print(f"{DIM}⚠️ 客戶名單含個資，請放本機碟，不要放 iCloud 桌面。{OFF}")
    print(f"{DIM}{BRAND}{OFF}\n")
    return 0


# ============================================================ main

def main():
    p = argparse.ArgumentParser(prog="an.py", description="小安 — 保險行銷專員")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="合規禁語掃描（檔案路徑或直接給文字）")
    c.add_argument("target")
    c.set_defaults(func=cmd_check)

    r = sub.add_parser("remind", help="從客戶名單算出該聯絡誰")
    r.add_argument("csvfile", nargs="?", default="客戶名單.csv")
    r.add_argument("--days", type=int, default=7)
    r.set_defaults(func=cmd_remind)

    pl = sub.add_parser("plan", help="產一個月內容排程表")
    pl.add_argument("--month", required=True, help="YYYY-MM")
    pl.add_argument("--out")
    pl.set_defaults(func=cmd_plan)

    i = sub.add_parser("init", help="在目前資料夾產出範本檔")
    i.add_argument("--force", action="store_true")
    i.set_defaults(func=cmd_init)

    a = p.parse_args()
    sys.exit(a.func(a))


if __name__ == "__main__":
    main()
