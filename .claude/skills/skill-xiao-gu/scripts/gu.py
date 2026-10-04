#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小顧（Xiao Gu）— 保險顧問　主程式
Sixhands Studio AI數字員工

子指令：
  audit    保單盤點表 CSV → 六大類別彙總＋缺漏／重複／到期提醒
  gap      客戶資料卡 JSON → 保障缺口試算（責任法＋倍數法，假設全列）
  brief    面談前準備單（哪些欄位還沒問到）
  claim    理賠文件清單＋流程＋時效提醒
  review   年度檢視／人生事件觸發清單
  check    合規禁語掃描（任何對外文件交出去前必跑）
  init     在目前資料夾產出所有範本

鐵律：
  1. 產出一律是「草稿」，須經所屬公司／保經代審查核可後才可交付客戶。
  2. 不指名商品、不做費率試算、不做核保與理賠認定、不做稅務結論。
  3. 缺口試算是教育性試算，假設必須全部列出。
  4. 客戶保單含特種個資 —— 放本機碟、去識別化、不放公開雲端。
"""
import argparse, csv, datetime as dt, json, os, re, shutil, sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL_DIR = os.path.join(SKILL_DIR, "templates")
BRAND = "Sixhands Studio AI數字員工　🦞　小顧 Xiao Gu"

RED = "\033[91m"; YEL = "\033[93m"; GRN = "\033[92m"; CYA = "\033[96m"; DIM = "\033[2m"; OFF = "\033[0m"

CATS = ["身故", "失能", "醫療日額", "醫療實支", "重疾重傷", "長照", "意外"]

DISCLOSURES = [
    ("教育性分析", r"教育性|需求面分析|非投保建議"),
    ("核保揭露", r"核保結果為準"),
    ("理賠揭露", r"條款.{0,8}(約定)?.{0,8}(及|與).{0,8}(保險)?公司核定|以保單條款.{0,20}核定為準"),
    ("假設揭露", r"假設"),
]


def money(n):
    return f"{int(round(n)):,}"


def w(s):
    """字串顯示寬度（CJK 全形算 2）"""
    return sum(2 if ord(c) > 0x2E7F else 1 for c in str(s))


def pad(s, width, align="left"):
    gap = " " * max(0, width - w(s))
    return (s + gap) if align == "left" else (gap + s)


def head(title):
    print(f"\n{CYA}{'─'*60}{OFF}\n{CYA}▍{title}{OFF}\n{CYA}{'─'*60}{OFF}")


# ============================================================ check：合規禁語

# (正則, 等級, 為什麼不行, 改寫建議)
RULES = [
    # 保證與報酬
    (r"保證(獲利|報酬|收益|領回|給付|賺|理賠|承保|過件)", "紅", "保證性用語，屬誇大不實表示",
     "改為「依保單條款約定辦理」／「以核保結果為準」"),
    (r"穩賺|包賺|一定賺|絕對賺|穩健增值|錢滾錢", "紅", "報酬保證或暗示", "刪除；改談保障功能"),
    (r"保本|零風險|無風險|沒有風險", "紅", "風險揭露不實；投資型不得表示保本",
     "改為「投資標的損益由要保人自行承擔」"),
    (r"(預期|投資|年)?報酬率", "紅", "保險不得以報酬率行銷",
     "改為「宣告利率／預定利率」並註明不等於報酬率"),
    (r"一定(領得到|拿得到|給付|賠)", "紅", "給付保證", "改為「符合條款約定條件時依約給付」"),
    # 存款代稱
    (r"儲蓄險", "紅", "不得以易使人誤認為存款之名詞行銷保險",
     "正名為「人壽保險／年金保險／利率變動型保險」"),
    (r"定存|定期存款|存款|零存整付|幫你存|幫您存", "紅", "存款代稱／與存款比較",
     "整句刪除，不與存款比較"),
    (r"利息|複利|年利率|月利率", "紅", "利率用語易誤導",
     "改為「宣告利率／預定利率」並註明不等於報酬率"),
    # 最高級與比較
    (r"最(好|強|便宜|優|划算|完整|推薦|適合)", "紅", "最高級用語屬誇大宣傳", "改為具體功能描述，不做排名"),
    (r"第一名|業界第一|唯一(一張|的選擇)|CP值最高|C/P值最高", "紅", "最高級用語", "刪除"),
    (r"別家(都)?不賠|只有(我們|這張)(才)?賠|比[^。\n]{0,12}公司(好|強|划算)", "紅",
     "跨公司比較且屬理賠保證", "刪除"),
    # 急迫與停售
    (r"停售|停賣|最後(一張|機會|倒數)|錯過不再|賣完就沒|限時|名額有限|再不買", "紅",
     "停售與急迫性話術為列管之不當招攬", "中性告知商品條件將調整，不加催促語"),
    (r"先簽再說|先買再說", "紅", "未經需求分析之促成", "改為「建議先完成需求分析再決定」"),
    # 理賠與核保
    (r"什麼都賠|全部都賠|有病就賠|一定過|不會被拒保|包過", "紅", "理賠與核保認定屬公司權責",
     "改為「以保單條款約定及保險公司核定為準」"),
    # 稅務
    (r"(一定|保證|絕對)?免(稅|遺產稅)|不列入遺產|節稅效果|可以節稅|合法避稅", "紅",
     "稅務結論；稽徵機關得依實質課稅原則認定",
     "改為「稅務效果因個案而異，以稽徵機關及稅務專業人員意見為準」"),
    # 轉保與告知
    (r"解(掉|約)舊(的|保單)|舊的.{0,6}解掉|換成新的比較划算|解約再買", "紅",
     "勸誘轉保(churning)", "改為完整揭露解約損失，由客戶自行決定"),
    (r"(這個|先)?不用(告知|寫)|不要講|先不要說|沒寫沒關係", "紅", "唆使不實告知",
     "改為「請據實告知，由核保判斷」"),
    (r"我幫你簽|代簽|幫你填(要保書|告知)", "紅", "代填代簽", "要保書與健康告知須本人親簽"),
    # 顧問特有：指名商品與費率
    (r"建議(投保|購買)[^。\n]{0,10}(人壽|產險|保險公司)", "紅", "指名特定商品／公司",
     "改為「建議補強○○類保障，需求區間約○○」"),
    (r"年繳[^。\n]{0,6}元|保費[^。\n]{0,4}[0-9][0-9,]{2,}[^。\n]{0,2}元|費率表", "紅",
     "自製費率試算屬招攬廣告且易失準", "刪除數字，改為「保費以公司試算與核保結果為準」"),
    (r"給付[^。\n]{0,4}[0-9]+\s*倍", "紅", "商品給付倍數", "刪除；只寫需求端額度"),
    # 黃燈
    (r"投資|理財規劃", "黃", "與投資商品混淆風險", "確認語境；保險文件避免以投資訴求為主軸"),
    (r"終身", "黃", "常被誤解為「保費繳一輩子」或「什麼都保」", "確認有無說明保障期間與繳費年期"),
    (r"癌症|重大疾病", "黃", "涉及條款定義", "務必註明「以保單條款所定義者為準」"),
]


def cmd_check(args):
    path = args.file
    if not os.path.exists(path):
        print(f"{RED}找不到檔案：{path}{OFF}"); return 2
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    head(f"合規禁語掃描：{os.path.basename(path)}")
    red = yel = 0
    for i, line in enumerate(lines, 1):
        for pat, lvl, why, fix in RULES:
            m = re.search(pat, line)
            if not m:
                continue
            color = RED if lvl == "紅" else YEL
            print(f"{color}[{lvl}] L{i}　「{m.group(0)}」{OFF}")
            print(f"    原因：{why}")
            print(f"    改寫：{fix}")
            print(f"    {DIM}{line.strip()[:70]}{OFF}")
            if lvl == "紅":
                red += 1
            else:
                yel += 1

    head("必載揭露檢查（四段，缺一不可）")
    text = "\n".join(lines)
    missing = []
    for name, pat in DISCLOSURES:
        ok = re.search(pat, text) is not None
        print(f"  {(GRN + '✔' + OFF) if ok else (RED + '✘' + OFF)} {name}")
        if not ok:
            missing.append(name)

    head("結果")
    if red or missing:
        print(f"{RED}✘ 不合格 —— 紅字 {red} 處、缺必載揭露 {len(missing)} 項（{'、'.join(missing) or '無'}）{OFF}")
        print(f"{RED}  這份不准交件。改完再跑一次。{OFF}")
        print(f"{DIM}  黃燈 {yel} 處請人工判讀語境。{OFF}\n{DIM}{BRAND}{OFF}")
        return 1
    print(f"{GRN}✔ 未發現紅字，四段揭露齊全。{OFF}")
    print(f"{YEL}  仍有黃燈 {yel} 處，請人工判讀語境。{OFF}")
    print(f"{YEL}  ⚠️ 通過本檢查 ≠ 可以交付。仍須送所屬公司／保經代審查核可。{OFF}")
    print(f"\n{DIM}{BRAND}{OFF}")
    return 0


# ============================================================ audit：保單盤點

def _num(s, default=0.0):
    try:
        return float(str(s).replace(",", "").strip() or default)
    except ValueError:
        return default


def cmd_audit(args):
    path = args.file
    if not os.path.exists(path):
        print(f"{RED}找不到檔案：{path}{OFF}"); return 2
    with open(path, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]
    if not rows:
        print(f"{RED}盤點表沒有資料。先跑 gu.py init 產範本。{OFF}"); return 2

    head(f"保單盤點彙總（共 {len(rows)} 張／筆）")
    totals = {c: 0.0 for c in CATS}
    units = {}
    for r in rows:
        cat = (r.get("險種大類") or "").strip()
        if cat not in totals:
            print(f"{YEL}  ⚠ 未知險種大類「{cat}」（{r.get('商品名稱代號','')}），未計入彙總{OFF}")
            continue
        totals[cat] += _num(r.get("保額或日額"))
        units[cat] = (r.get("單位") or "元").strip()

    for c in CATS:
        u = units.get(c, "元")
        v = totals[c]
        mark = f"{RED}← 沒有{OFF}" if v == 0 else ""
        print("  " + pad(c, 12) + pad(money(v), 13, "r") + f" {u}　{mark}")

    head("① 缺漏類別（六大保障有沒有整塊是空的）")
    miss = [c for c in CATS if totals[c] == 0]
    print("  " + ("、".join(miss) + f"　{RED}← 這幾塊目前是 0{OFF}" if miss else f"{GRN}無，六大類別都有部位{OFF}"))

    head("② 疑似重複／同類多張（不一定是壞事，但要跟客戶說明）")
    bycat = {}
    for r in rows:
        bycat.setdefault((r.get("險種大類") or "").strip(), []).append(r)
    dup = False
    for c, rs in bycat.items():
        if c in CATS and len(rs) >= 3:
            dup = True
            names = "、".join((x.get("商品名稱代號") or "?") for x in rs)
            print(f"  {c}：{len(rs)} 張（{names}）")
    if not dup:
        print(f"{GRN}  無明顯堆疊{OFF}")

    head("③ 主約／附約結構（主約解約，附約會一起失效）")
    anyfx = False
    for r in rows:
        if (r.get("主約或附約") or "").strip() == "附約":
            anyfx = True
            print(f"  {r.get('商品名稱代號','?')}　依附主約：{r.get('依附主約') or RED+'未填 ← 一定要查'+OFF}")
    if not anyfx:
        print(f"{DIM}  盤點表未標註附約，請確認是否漏填{OFF}")

    head("④ 五年內到期／繳費屆滿（提前跟客戶講，不要等到斷了才知道）")
    thisyear = dt.date.today().year
    hit = False
    for r in rows:
        name = r.get("商品名稱代號", "?")
        pay_end = _num(r.get("繳費到期年"))
        if pay_end and 0 <= pay_end - thisyear <= 5:
            hit = True
            print(f"  {name}　{int(pay_end)} 年繳費期滿")
        cov_to = (r.get("保障到期年齡") or "").strip()
        if cov_to and cov_to not in ("終身", "終生", ""):
            hit = True
            print(f"  {name}　保障至 {cov_to} 歲{YEL}　← 定期型，到期即無保障{OFF}")
    if not hit:
        print(f"{GRN}  五年內無到期事件（仍請以保單條款為準）{OFF}")

    head("下一步")
    print("  1. 把上面的『現有』數字填進客戶資料卡的 existing 欄位")
    print("  2. 跑　python3 scripts/gu.py gap 客戶資料卡.json")
    print(f"  3. {YEL}若結論涉及調整既有保單 → 必附「解約損失揭露單」，缺這張不交件{OFF}")
    print(f"\n{DIM}{BRAND}{OFF}")
    return 0


# ============================================================ gap：缺口試算

def _g(d, *keys, default=0.0):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if isinstance(cur, (int, float)) else default


def cmd_gap(args):
    path = args.file
    if not os.path.exists(path):
        print(f"{RED}找不到檔案：{path}{OFF}"); return 2
    with open(path, encoding="utf-8") as f:
        d = json.load(f)

    cid = d.get("客戶代號", "客戶 A")
    age = _g(d, "年齡")
    a = d.get("假設", {})
    fin = d.get("財務", {})
    fam = d.get("家庭", {})
    ex = d.get("既有保障", {})
    soc = d.get("社會保險", {})

    years_support = _g(a, "生活費支應年數", default=20)
    infl = _g(a, "通膨率", default=0.02)
    final_cost = _g(a, "最終費用", default=800000)
    edu_year_cost = _g(a, "子女每人年教育費", default=200000)
    retire_age = _g(a, "退休年齡", default=65)
    life_end = _g(a, "餘命年齡", default=85)
    retire_spend = _g(a, "退休年支出", default=0)
    cure_months = _g(a, "重疾治療期月數", default=24)
    ltc_scenarios = a.get("長照年期情境", [5, 10, 20])

    income = _g(fin, "年收入")
    spend = _g(fin, "家庭年支出")
    cash = _g(fin, "可動用存款") + _g(fin, "其他可變現資產")
    debt = _g(fin, "房貸餘額") + _g(fin, "其他負債")

    # 教育費
    edu = 0.0
    for kid in fam.get("子女", []):
        k_age = kid.get("年齡", 0)
        k_until = kid.get("支應至年齡", 22)
        edu += max(0, k_until - k_age) * kid.get("年教育費", edu_year_cost)
    # 奉養
    support = _g(fam, "奉養父母年金") * _g(fam, "奉養年數")

    # 1. 身故／全失能
    living = spend * years_support * (1 + infl * years_support / 2)
    need_death = debt + edu + living + support + final_cost
    offset = cash + _g(ex, "身故") + _g(soc, "勞保等身故給付估")
    gap_death = max(0.0, need_death - offset)

    # 2. 重疾
    need_ci = income / 12 * cure_months + _g(a, "自費療程預備金", default=1000000)
    gap_ci = max(0.0, need_ci - _g(ex, "重疾重傷"))

    # 3. 長照（三情境）
    ltc_month_need = _g(a, "照顧月費用", default=40000) + spend / 12 * _g(a, "照顧期間家庭支出比例", default=0.7)
    ltc_month_have = _g(ex, "長照月給付")
    ltc_rows = []
    for y in ltc_scenarios:
        need = ltc_month_need * 12 * y
        have = ltc_month_have * 12 * y
        ltc_rows.append((y, need, have, max(0.0, need - have)))

    # 4. 意外（長期收入損失，兩情境並列）
    years_to_retire = max(0, retire_age - age)
    pa_ratio = _g(a, "部分失能收入損失比例", default=0.5)
    need_pa_full = income * years_to_retire
    need_pa_part = need_pa_full * pa_ratio
    have_pa = _g(ex, "意外")
    gap_pa = max(0.0, need_pa_full - have_pa)
    gap_pa_part = max(0.0, need_pa_part - have_pa)

    # 5. 醫療日額目標
    daily_target = (_g(a, "病房差額日費", default=3000)
                    + _g(a, "看護日費", default=2500)
                    + income / 365 * _g(a, "收入中斷比例", default=1.0))
    gap_daily = max(0.0, daily_target - _g(ex, "醫療日額"))

    # 6. 退休
    retire_years = max(0, life_end - retire_age)
    passive = _g(soc, "勞保年金月領估") * 12 + _g(fin, "其他年被動收入")
    yearly_gap = max(0.0, retire_spend - passive)
    gap_retire = yearly_gap * retire_years

    # 7. 倍數法檢核
    rule10 = income * 10
    prem_cap = income * 0.10

    head(f"保障缺口試算　—　{cid}（{int(age)} 歲）")
    print(f"{YEL}※ 教育性試算，非投保建議、非精算結果。所有數字建立在下列假設之上。{OFF}\n")

    rows = [
        ("身故／全失能", need_death, offset, gap_death, "元"),
        ("重大疾病／重傷", need_ci, _g(ex, "重疾重傷"), gap_ci, "元"),
        ("醫療日額", daily_target, _g(ex, "醫療日額"), gap_daily, "元／日"),
        ("退休現金流", yearly_gap * retire_years, 0, gap_retire, "元"),
    ]
    print("  " + pad("類別", 20) + pad("需求", 15, "r") + pad("現有", 15, "r") + pad("缺口", 15, "r"))
    print("  " + "─" * 65)
    for name, need, have, gap, unit in rows:
        flag = RED if gap > 0 else GRN
        print("  " + pad(name, 20) + pad(money(need), 15, "r") + pad(money(have), 15, "r")
              + flag + pad(money(gap), 15, "r") + OFF + "  " + unit)

    print(f"\n  {'意外／失能（兩情境並列，不與身故缺口相加）'}")
    for label, need, gap in [("全失能（收入全損）", need_pa_full, gap_pa),
                             (f"部分失能（{int(pa_ratio*100)}%）", need_pa_part, gap_pa_part)]:
        flag = RED if gap > 0 else GRN
        print("  　" + pad(label, 22) + "需求 " + pad(money(need), 13, "r")
              + "　現有 " + pad(money(have_pa), 13, "r") + "　" + flag + "缺口 " + pad(money(gap), 13, "r") + OFF)

    print(f"\n  {'長照（三情境並列）'}")
    for y, need, have, gap in ltc_rows:
        flag = RED if gap > 0 else GRN
        print("  　" + pad(f"需照顧 {int(y)} 年", 22) + "需求 " + pad(money(need), 13, "r")
              + "　現有 " + pad(money(have), 13, "r") + "　" + flag + "缺口 " + pad(money(gap), 13, "r") + OFF)

    print(f"\n{YEL}  ⚠ 各類缺口對應的是不同風險情境（身故／失能／重疾／長照不會同時發生），"
          f"\n    只能逐項討論，{RED}不可直接相加當成「總共要買多少」{OFF}{YEL}。{OFF}")

    head("倍數法檢核（僅供合理性對照，不是規劃結論）")
    print(f"  年收入 10 倍　＝ {money(rule10)} 元　vs 責任法需求 {money(need_death)} 元")
    print(f"  保費上限參考（年收入 10%）＝ {money(prem_cap)} 元／年")
    if need_death > rule10 * 1.5:
        print(f"{YEL}  ⚠ 責任法遠高於倍數法：家庭責任偏重（房貸／子女教育），以責任法為主並向客戶說明差異{OFF}")

    head("補強優先順序（依「風險發生後對家庭現金流的破壞力」排序）")
    order = sorted(
        [("身故／全失能", gap_death), ("長照（10 年情境）", ltc_rows[min(1, len(ltc_rows)-1)][3]),
         ("重大疾病", gap_ci), ("意外／失能（全失能情境）", gap_pa), ("退休現金流", gap_retire)],
        key=lambda x: -x[1])
    for i, (name, gap) in enumerate(order, 1):
        if gap <= 0:
            continue
        print(f"  {i}. {name}　缺口 {money(gap)} 元")
    print(f"  {DIM}（醫療日額缺口 {money(gap_daily)} 元／日、實支實付需求請依自費項目另行討論）{OFF}")
    print(f"{YEL}  ※ 只寫類別與額度區間。要用哪一張保單、保費多少，回到所屬公司商品系統與核保結果。{OFF}")

    head("本次試算使用的假設（交件必須整段附上）")
    assum = [
        f"生活費支應年數：{int(years_support)} 年",
        f"通膨率：{infl*100:.1f}%（採簡化近似，非現值精算）",
        f"最終費用（喪葬與稅費）：{money(final_cost)} 元",
        f"子女教育：每人每年 {money(edu_year_cost)} 元，支應至設定年齡",
        f"重疾治療期收入中斷：{int(cure_months)} 個月",
        f"長照月費用需求：{money(ltc_month_need)} 元；情境年期 {ltc_scenarios}",
        f"意外／失能：距退休 {int(years_to_retire)} 年，部分失能以收入損失 {int(pa_ratio*100)}% 估算",
        f"退休：{int(retire_age)} 歲退休、餘命 {int(life_end)} 歲、年支出 {money(retire_spend)} 元",
        f"社會保險給付均為概估，實際以勞保局／主管機關核算為準",
    ]
    for s in assum:
        print(f"  ・{s}")

    head("必載揭露（交件時原文照抄）")
    for s in [
        "1. 本報告為需求面之教育性分析，非投保建議，亦非精算或稅務意見。",
        "2. 所有金額均基於上列假設，假設變動結果即不同。",
        "3. 是否承保、加費或除外，以保險公司核保結果為準。",
        "4. 是否理賠及給付金額，以保單條款約定及保險公司核定為準。",
        "5. 涉及調整既有保單者，另附「解約損失揭露單」。",
    ]:
        print(f"  {s}")
    print(f"\n{YEL}⚠️ 這是草稿。送所屬公司／保經代審查核可後，才可交付客戶。{OFF}")
    print(f"\n{DIM}{BRAND}{OFF}")
    return 0


# ============================================================ brief：面談前準備

BRIEF_FIELDS = [
    ("年齡", ["年齡"]), ("職業", ["職業"]),
    ("年收入", ["財務", "年收入"]), ("家庭年支出", ["財務", "家庭年支出"]),
    ("房貸餘額", ["財務", "房貸餘額"]), ("可動用存款", ["財務", "可動用存款"]),
    ("子女資料", ["家庭", "子女"]), ("既有身故保障", ["既有保障", "身故"]),
    ("既有醫療日額", ["既有保障", "醫療日額"]), ("既有實支實付", ["既有保障", "醫療實支"]),
    ("既有重疾", ["既有保障", "重疾重傷"]), ("既有長照", ["既有保障", "長照月給付"]),
    ("既有意外", ["既有保障", "意外"]), ("退休年支出", ["假設", "退休年支出"]),
]


def cmd_brief(args):
    path = args.file
    d = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    else:
        print(f"{YEL}找不到 {path}，當作全新客戶處理。{OFF}")

    head(f"面談前準備單　—　{d.get('客戶代號', '新客戶')}")
    missing = []
    for label, keys in BRIEF_FIELDS:
        cur = d
        ok = True
        for k in keys:
            if not isinstance(cur, dict) or k not in cur or cur[k] in ("", None, [], 0):
                ok = False
                break
            cur = cur[k]
        print(f"  {(GRN+'✔'+OFF) if ok else (RED+'✘'+OFF)} {label}")
        if not ok:
            missing.append(label)

    head("這次面談要問到的（缺什麼問什麼）")
    if missing:
        for m in missing:
            print(f"  ・{m}")
    else:
        print(f"{GRN}  資料已齊，本次可直接進入缺口說明{OFF}")

    head("開場（照唸）")
    print("  「今天這一個小時，我不會推薦你任何一張保單。")
    print("　 我只做兩件事：把你現在有的講清楚，再一起看還缺什麼。")
    print("　 缺口出來之後，要不要補、什麼時候補，都是你決定。」")

    head("三個不要")
    print("  1. 客戶講他生病的親人時，不要打斷去接商品")
    print("  2. 不要用恐懼收尾")
    print("  3. 不要當場給結論 —— 回去算，留下第二次見面")
    print(f"\n  完整提問腳本：references/顧問面談與提問腳本.md")
    print(f"\n{DIM}{BRAND}{OFF}")
    return 0


# ============================================================ claim：理賠文件

CLAIM_COMMON = [
    "理賠申請書（保險公司制式，本人簽名）",
    "被保險人身分證影本",
    "受益人身分證影本",
    "受款帳戶存摺封面影本",
    "如由他人代辦：委任或授權文件",
]
CLAIM_BY_TYPE = {
    "住院": ["診斷證明書正本（載明病名、住院起訖日）",
             "醫療費用收據正本（副本申請須加蓋與正本相符章並註明正本去向）",
             "費用明細（自費項目需明細）"],
    "手術": ["診斷證明書正本（載明手術名稱與日期）", "醫療費用收據正本與明細",
             "手術紀錄或麻醉紀錄（部分公司要求）"],
    "意外": ["診斷證明書（載明受傷原因與部位）",
             "事故證明（交通事故初判表／警方資料／職災紀錄，視情況）",
             "醫療費用收據與明細"],
    "失能": ["失能診斷書（依保單失能程度表所需記載）", "相關影像與檢查報告",
             "治療過程之診斷證明"],
    "重疾": ["診斷證明書", "病理報告", "健保重大傷病證明（若條款以此為要件）"],
    "身故": ["死亡證明書正本", "除戶戶籍謄本", "受益人身分證明與關係證明"],
    "癌症": ["診斷證明書", "病理切片報告", "治療紀錄（門診／住院／放化療）"],
}


def cmd_claim(args):
    t = args.type
    head(f"理賠文件清單　—　{t}")
    if t not in CLAIM_BY_TYPE:
        print(f"{YEL}未收錄的事故類型。可用：{'、'.join(CLAIM_BY_TYPE)}{OFF}")
        return 2
    print(f"{DIM}  各公司要求略有差異，最終以保險公司公告之應備文件為準。{OFF}\n")
    print("  【共通】")
    for x in CLAIM_COMMON:
        print(f"    [ ] {x}")
    print(f"\n  【{t}】")
    for x in CLAIM_BY_TYPE[t]:
        print(f"    [ ] {x}")

    head("顧問要做的四件事（順序不要顛倒）")
    print("  1. 先確認人安全、先通知保險公司報案，文件之後補")
    print("  2. 告訴客戶：所有收據、明細、診斷書都先留著，不要丟")
    print("  3. 多家公司同時申請 → 正本給一家，其餘用加蓋『與正本相符』之副本並註明正本去向")
    print("  4. 建立送件追蹤表：哪家公司／送了什麼／何時送／承辦是誰／預計回覆日")

    head("時效")
    print("  ・保險金請求權有消滅時效之規定（依保險法為 2 年，自得請求之日起算）")
    print("  ・部分條款另定事故後通知期限 → 一發生就先通知，不要等文件齊")

    head("被拒賠時")
    print("  1. 要書面說明（載明依據條款與理由）")
    print("  2. 逐字對條款，確認爭點（除外／等待期／告知／定義）")
    print("  3. 先向保險公司申訴；仍不服可向金融消費評議中心申請評議")
    print("  4. 涉及訴訟或告知義務爭議 → 交小辯與律師")

    print(f"\n{RED}🚨 顧問不做理賠認定。全程只講：「是否符合理賠要件，以保單條款約定及保險公司核定為準。」{OFF}")
    print(f"\n{DIM}{BRAND}{OFF}")
    return 0


# ============================================================ review：年度檢視

LIFE_EVENTS = [
    ("結婚", "受益人、家庭責任額度"),
    ("生小孩", "壽險缺口大增、教育金、子女醫療"),
    ("買房／貸款", "房貸對應之身故與失能缺口"),
    ("換工作／創業", "團保消失、收入變動、職業等級改變（須通知保險公司）"),
    ("收入大幅變動", "保費可持續性、額度重算"),
    ("家人生病或身故", "家庭現金流結構、長照壓力"),
    ("離婚", "受益人、要保人、保單價值歸屬"),
    ("子女獨立", "壽險需求下降，轉向醫療與長照"),
    ("退休", "收入替代轉為醫療、長照、現金流"),
    ("搬遷／出國長住", "保障地域限制、海外就醫理賠條件、聯絡資料"),
]


def cmd_review(args):
    d = {}
    if args.file and os.path.exists(args.file):
        with open(args.file, encoding="utf-8") as f:
            d = json.load(f)
    head(f"年度檢視清單　—　{d.get('客戶代號', '客戶')}　{dt.date.today().isoformat()}")
    for x in [
        "六大保障類別有無整塊為 0（跑 gu.py audit）",
        "五年內到期或繳費屆滿的保單",
        "定期型保單的保障到期年齡",
        "附約所依附的主約是否仍有效",
        "受益人資料是否仍正確（離婚／再婚／子女出生後最常忘記改）",
        "要保人／被保險人聯絡資料、地址、扣款帳戶",
        "續期扣款帳戶餘額（避免停效；復效可能要重新審核健康狀況）",
        "職業有無變更（影響意外險費率與承保條件，須通知公司）",
        "收入與家庭支出有無明顯變化 → 缺口重算（跑 gu.py gap）",
    ]:
        print(f"  [ ] {x}")

    head("人生事件觸發（有發生就不必等週年，立刻檢視）")
    for ev, what in LIFE_EVENTS:
        print(f"  □ {ev:<12}→ {what}")

    head("年度檢視訊息範本（不推銷版）")
    print("  「○○ 你好，你的保單這個月滿 ○ 年了。")
    print("　 我幫你看過三件事：① 有沒有快到期的保障 ② 繳費年期還剩幾年 ③ 受益人資料是不是還正確。")
    print("　 目前狀況是 ______。沒有要你做任何事，如果要調整我們再約時間談。」")
    print(f"\n{DIM}{BRAND}{OFF}")
    return 0


# ============================================================ init

def cmd_init(args):
    if not os.path.isdir(TPL_DIR):
        print(f"{RED}找不到 templates 目錄：{TPL_DIR}{OFF}"); return 2
    n = 0
    for name in sorted(os.listdir(TPL_DIR)):
        src = os.path.join(TPL_DIR, name)
        dst = os.path.join(os.getcwd(), name)
        if os.path.isfile(src):
            if os.path.exists(dst):
                print(f"{YEL}  略過（已存在）：{name}{OFF}")
                continue
            shutil.copy2(src, dst)
            print(f"{GRN}  ✔ {name}{OFF}")
            n += 1
    print(f"\n產出 {n} 個範本於：{os.getcwd()}")
    print(f"{YEL}⚠️ 客戶資料含特種個資 —— 請放本機碟、不要放 iCloud 桌面或公開雲端，個案一律去識別化。{OFF}")
    print(f"\n{DIM}{BRAND}{OFF}")
    return 0


# ============================================================ main

def main():
    p = argparse.ArgumentParser(description="小顧 — 保險顧問工具")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("check", help="合規禁語掃描"); s.add_argument("file"); s.set_defaults(fn=cmd_check)
    s = sub.add_parser("audit", help="保單盤點彙總"); s.add_argument("file"); s.set_defaults(fn=cmd_audit)
    s = sub.add_parser("gap", help="保障缺口試算"); s.add_argument("file"); s.set_defaults(fn=cmd_gap)
    s = sub.add_parser("brief", help="面談前準備單"); s.add_argument("file"); s.set_defaults(fn=cmd_brief)
    s = sub.add_parser("claim", help="理賠文件清單")
    s.add_argument("--type", required=True, choices=list(CLAIM_BY_TYPE)); s.set_defaults(fn=cmd_claim)
    s = sub.add_parser("review", help="年度檢視清單")
    s.add_argument("file", nargs="?"); s.set_defaults(fn=cmd_review)
    s = sub.add_parser("init", help="產出範本"); s.set_defaults(fn=cmd_init)

    a = p.parse_args()
    if not getattr(a, "fn", None):
        p.print_help()
        print(f"\n{DIM}{BRAND}{OFF}")
        return 0
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
