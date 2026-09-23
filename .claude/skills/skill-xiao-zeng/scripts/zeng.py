#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小增（Xiao Zeng）— 保險增員／人力招募專員　主程式
Sixhands Studio AI數字員工

子指令：
  funnel     增員漏斗表 CSV → 各段轉換率、瓶頸診斷、反推名單需求量
  score      面談評估表 JSON → 七維度加權評分＋硬性門檻＋報聘建議
  pipeline   增員名單表 CSV → 名單池體檢（階段分布／來源效率／該追誰）
  retention  增員名單表 CSV → 定著率、脫落月數分布、脫落原因統計
  disclose   招募主管資料卡 JSON → 誠實揭露包草稿（欄位沒填就標「待補」，不編數字）
  plan90     產出新人 90 天育成計畫（--name 代號 --start YYYY-MM-DD）
  check      合規禁語掃描（任何招募文案／貼文／簡報交出去前必跑）
  init       在目前資料夾產出所有範本

鐵律：
  1. 招募文案一律是「草稿」，須經所屬公司／保經代審查核可後才可對外。
  2. 不保證收入、不保證錄取、不保證考取、不寫平均收入以外的想像數字。
  3. 就業服務法：不得就業歧視、不得不實招募廣告、不得收保證金或扣留證件。
  4. 不唆使準增員對象帶走原公司客戶名單，不誘導其客戶解約轉單。
  5. 未登錄前不得招攬、不得掛件借牌。
  6. 應徵者履歷是個資 —— 放本機碟、限目的內使用、未錄取者定期銷毀。
"""
import argparse, csv, datetime as dt, json, os, re, sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL_DIR = os.path.join(SKILL_DIR, "templates")
BRAND = "Sixhands Studio AI數字員工　🦞　小增 Xiao Zeng"

RED = "\033[91m"; YEL = "\033[93m"; GRN = "\033[92m"; CYA = "\033[96m"; DIM = "\033[2m"; OFF = "\033[0m"


def w(s):
    """字串顯示寬度（CJK 全形算 2）"""
    return sum(2 if ord(c) > 0x2E7F else 1 for c in str(s))


def pad(s, width, align="left"):
    gap = " " * max(0, width - w(s))
    return (s + gap) if align == "left" else (gap + s)


def head(title):
    print(f"\n{CYA}{'─'*64}{OFF}\n{CYA}▍{title}{OFF}\n{CYA}{'─'*64}{OFF}")


def foot():
    print(f"\n{DIM}{BRAND}{OFF}")


def die(msg):
    print(f"{RED}✖ {msg}{OFF}")
    sys.exit(1)


def read_csv(path):
    if not os.path.exists(path):
        die(f"找不到檔案：{path}（先跑 `zeng.py init` 產範本）")
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]


def read_json(path):
    if not os.path.exists(path):
        die(f"找不到檔案：{path}（先跑 `zeng.py init` 產範本）")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def num(v, default=0.0):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


# ==================================================================== funnel

# 漏斗各段的欄位順序（名單表與漏斗表共用的語彙）
STAGES = [
    ("名單數", "建檔的名單"),
    ("接觸數", "真的講到話"),
    ("約談數", "願意坐下來談"),
    ("說明會出席", "來聽職涯說明會"),
    ("深度面談", "二／三次面談"),
    ("報聘", "決定加入、送件"),
    ("考取", "考到證照"),
    ("到職", "登錄完成、正式開始"),
    ("滿3月留存", "撐過前 90 天"),
    ("滿13月定著", "13 個月還在"),
]

# 參考區間僅供「相對比較、找瓶頸」用，不是業界統計、不對外引用
REF_BAND = {
    "接觸數": (0.55, 0.80), "約談數": (0.30, 0.55), "說明會出席": (0.45, 0.75),
    "深度面談": (0.50, 0.80), "報聘": (0.30, 0.55), "考取": (0.70, 0.90),
    "到職": (0.85, 1.00), "滿3月留存": (0.60, 0.85), "滿13月定著": (0.40, 0.70),
}


def cmd_funnel(args):
    rows = read_csv(args.csv)
    tot = {}
    for k, _ in STAGES:
        tot[k] = sum(num(r.get(k)) for r in rows)
    if tot["名單數"] <= 0:
        die("名單數是 0，漏斗算不出來。先把每個月的實際數字填進去。")

    head(f"增員漏斗診斷（{len(rows)} 個月合計）")
    print(f"{pad('階段',14)}{pad('人數',8,'right')}   {pad('段轉換',9,'right')}  {pad('累積存活',10,'right')}  說明")
    print(f"{DIM}{'-'*64}{OFF}")
    prev = tot["名單數"]
    weak = []
    for i, (k, desc) in enumerate(STAGES):
        n = tot[k]
        step = (n / prev) if prev > 0 else 0.0
        cum = (n / tot["名單數"]) if tot["名單數"] > 0 else 0.0
        if i == 0:
            line = f"{pad(k,14)}{pad(str(int(n)),8,'right')}   {pad('—',9,'right')}  {pad('100.0%',10,'right')}  {desc}"
            print(line)
        else:
            lo, hi = REF_BAND.get(k, (0, 1))
            mark, color = "", ""
            if step < lo:
                mark, color = " ◀ 瓶頸", RED
                weak.append((k, step, lo, hi, desc))
            elif step > hi:
                mark, color = " ▲ 偏高（確認數字是否灌水）", YEL
            print(f"{pad(k,14)}{pad(str(int(n)),8,'right')}   "
                  f"{color}{pad(f'{step*100:.1f}%',9,'right')}{OFF}  "
                  f"{pad(f'{cum*100:.1f}%',10,'right')}  {desc}{color}{mark}{OFF}")
        prev = n if n > 0 else prev

    head("反推：要多一個「13 個月還在的人」，前面要準備多少")
    final = tot["滿13月定著"]
    if final <= 0:
        print(f"{YEL}目前 13 個月定著數是 0 —— 還沒有人走完整段，先用「到職數」當替代指標。{OFF}")
        final = tot["到職"]
        label = "到職"
    else:
        label = "13 個月定著"
    if final <= 0:
        print(f"{RED}連到職都是 0，這條線還沒跑起來，先衝「接觸數」與「約談數」。{OFF}")
    else:
        for k, _ in STAGES:
            need = tot[k] / final
            print(f"  {pad(k,14)} {pad(f'{need:.1f}',7,'right')} 人／每 1 位{label}")

    head("小增的判讀")
    if weak:
        for k, step, lo, hi, desc in weak:
            print(f"{RED}▶ 卡在「{k}」（{step*100:.1f}%，相對偏低）{OFF}")
            print(f"  {ADVICE.get(k, '檢視這一段的流程與話術。')}")
    else:
        print(f"{GRN}▶ 各段沒有明顯塌陷。想放大結果，先放大最上面的「名單數」與「接觸數」。{OFF}")
    print(f"\n{DIM}※ 參考區間只用來「找相對最弱的一段」，不是業界統計數字，不得對外引用。{OFF}")
    foot()


ADVICE = {
    "接觸數": "名單建了但沒開口。問題通常不是話術，是「不敢講」。先改成「不談工作、只談近況」的低壓接觸，見 references/增員名單開發SOP.md。",
    "約談數": "接觸到了但約不出來。多半是第一句就講成「來做保險」。改成先講「想找你聊一個職涯的可能」，把決定權留給對方。",
    "說明會出席": "答應了卻沒來。缺的是「說明會前 24 小時的確認動作」與「場地／時間對他的成本」。見 references/招募說明會SOP.md。",
    "深度面談": "來了一次就沒下文。通常是第一次面談講太多制度、太少聽對方。改用三次面談法。",
    "報聘": "談到最後不敢跳。九成卡在「錢撐不撐得過」。把 `zeng.py disclose` 的誠實揭露包提早在第二次面談就攤開，反而成交率會回升。",
    "考取": "報聘後考照卡關。排考試時程、指定讀書進度、每週回報，見 references/考照與報聘輔導SOP.md。",
    "到職": "考到了卻沒登錄開始。中間空窗越久掉越多，考取到到職不要超過兩週。",
    "滿3月留存": "前 90 天陣亡。這段幾乎都是主管的責任 —— 陪訪次數不夠。見 references/新人90天育成與定著SOP.md。",
    "滿13月定著": "撐過三個月卻死在第一年。多半是「緣故名單燒完、沒學會開發陌生市場」。第 4-6 個月就要開始轉市場。",
}


# ===================================================================== score

DIMS = [
    ("motivation", "動機真實性", 20, "為什麼想換？是「逃離現在」還是「想要什麼」。只想逃的通常撐不久"),
    ("runway", "財務緩衝", 20, "沒收入還能活幾個月。這一項是現實，不是志氣"),
    ("network", "人際存量", 15, "願意接他電話的人有多少（不是好友數）"),
    ("resilience", "學習與抗壓", 15, "被拒絕後多久回得來、願不願意被指正"),
    ("family_support", "家庭支持", 10, "另一半知不知道、支不支持。反對的家庭是最大脫落主因之一"),
    ("time", "時間投入", 10, "每週真的拿得出多少小時"),
    ("integrity", "誠信紀錄", 10, "有無誠信疑慮。這一項不是加分項，是門檻"),
]


def cmd_score(args):
    d = read_json(args.json)
    sc = d.get("評分", {})
    missing = [k for k, *_ in DIMS if k not in sc]
    if missing:
        die("以下維度還沒評（1-5 分）：" + "、".join(
            f"{n}({k})" for k, n, *_ in DIMS if k in missing))

    head(f"增員對象評估：{d.get('代號','(未填代號)')}")
    total = 0.0
    for k, name, wt, desc in DIMS:
        v = num(sc.get(k))
        if not 1 <= v <= 5:
            die(f"{name} 的分數 {sc.get(k)} 不在 1-5 之間")
        got = v / 5 * wt
        total += got
        bar = "█" * int(v) + "·" * (5 - int(v))
        color = RED if v <= 2 else (YEL if v == 3 else GRN)
        print(f"{pad(name,12)} {color}{bar}{OFF} {int(v)}/5  權重{pad(str(wt),3,'right')}  "
              f"得分 {pad(f'{got:.1f}',5,'right')}   {DIM}{desc}{OFF}")
    print(f"{DIM}{'-'*64}{OFF}")
    print(f"{pad('加權總分',12)} {total:.1f} / 100")

    # 硬性門檻：不是分數高就可以，這幾條踩到就停
    gates = []
    if num(sc.get("integrity")) <= 2:
        gates.append("誠信面有疑慮 → 直接停止。這一行踩到誠信，是撤登錄等級的事，不是訓練得回來的。")
    if num(sc.get("runway")) <= 1:
        gates.append("財務緩衝不足（撐不到 3 個月）→ 現在不要報聘。先讓他存錢，或先做兼職型接觸。餓著的人會做出違規的事。")
    if num(sc.get("family_support")) <= 1:
        gates.append("家庭明確反對 → 先安排一次「家屬也在場」的說明，家人沒點頭前不報聘。")
    if num(sc.get("motivation")) <= 2:
        gates.append("動機只有「逃離現職」→ 再談一次，找出他真正想要的東西，否則第一次挫折就會走。")

    head("結論")
    if gates:
        print(f"{RED}▶ 觸發硬性門檻，暫不報聘：{OFF}")
        for g in gates:
            print(f"  • {g}")
    elif total >= 75:
        print(f"{GRN}▶ 建議進入第三次面談 → 攤開誠實揭露包 → 由他自己決定。{OFF}")
        print("  提醒：分數高不代表要用力推。越適合的人，越禁不起被推。")
    elif total >= 55:
        print(f"{YEL}▶ 有潛力但條件未齊。先補弱項（見上表最低的兩項），一個月後再評一次。{OFF}")
    else:
        print(f"{RED}▶ 現階段不適合。不要為了達成增員件數把人拉進來 —— 他會在半年內離開，"
              f"而且會帶著對這個行業的壞印象走。{OFF}")

    print(f"\n{DIM}※ 本評分是內部參考，不得作為錄取／不錄取的對外理由，"
          f"不得記載年齡、性別、婚姻、容貌、星座、血型等就業歧視項目。{OFF}")
    foot()


# ================================================================== pipeline

ACTIVE = ["名單", "已接觸", "已約談", "已參加說明會", "面談中", "決定報聘", "考照中"]


def cmd_pipeline(args):
    rows = read_csv(args.csv)
    head(f"增員名單池體檢（{len(rows)} 筆）")

    stage_cnt, src_cnt, src_hire = {}, {}, {}
    stale = []
    today = dt.date.today()
    for r in rows:
        st = (r.get("階段") or "未填").strip()
        stage_cnt[st] = stage_cnt.get(st, 0) + 1
        src = (r.get("來源") or "未填").strip()
        src_cnt[src] = src_cnt.get(src, 0) + 1
        if st in ("已到職", "定著中"):
            src_hire[src] = src_hire.get(src, 0) + 1
        # 超過 30 天沒動作的活躍名單
        last = (r.get("最近接觸日") or "").strip()
        if st in ACTIVE and last:
            try:
                d0 = dt.date.fromisoformat(last)
                gap = (today - d0).days
                if gap >= 30:
                    stale.append((r.get("代號", "?"), st, gap))
            except ValueError:
                pass

    print(f"{pad('階段',14)}{pad('人數',6,'right')}")
    for st in ["名單", "已接觸", "已約談", "已參加說明會", "面談中", "決定報聘",
               "考照中", "已到職", "定著中", "脫落", "婉拒", "未填"]:
        if st in stage_cnt:
            print(f"{pad(st,14)}{pad(str(stage_cnt[st]),6,'right')}")

    head("來源效率（哪一種名單真的變成人）")
    print(f"{pad('來源',16)}{pad('名單',6,'right')}{pad('到職',6,'right')}  轉換")
    for src, c in sorted(src_cnt.items(), key=lambda x: -x[1]):
        h = src_hire.get(src, 0)
        rate = f"{h/c*100:.0f}%" if c else "—"
        print(f"{pad(src,16)}{pad(str(c),6,'right')}{pad(str(h),6,'right')}  {rate}")

    head("該追誰（活躍名單超過 30 天沒動作）")
    if stale:
        for code, st, gap in sorted(stale, key=lambda x: -x[2]):
            color = RED if gap >= 60 else YEL
            print(f"  {color}{pad(code,10)} {pad(st,12)} 已 {gap} 天沒接觸{OFF}")
        print(f"\n{DIM}超過 60 天基本上等於重新開始。與其硬追，不如換一個「純問候、不談工作」的接觸。{OFF}")
    else:
        print(f"{GRN}  沒有停滯名單。{OFF}")
    foot()


# ================================================================= retention

def cmd_retention(args):
    rows = read_csv(args.csv)
    joined = [r for r in rows if (r.get("階段") or "").strip() in ("已到職", "定著中", "脫落")]
    if not joined:
        die("名單表裡沒有任何「已到職／定著中／脫落」的人，算不出定著率。")
    drop = [r for r in joined if (r.get("階段") or "").strip() == "脫落"]
    stay = len(joined) - len(drop)

    head(f"定著分析（到職過的共 {len(joined)} 人）")
    print(f"  仍在職：{stay} 人　脫落：{len(drop)} 人　"
          f"留存率：{stay/len(joined)*100:.1f}%")

    months = [num(r.get("脫落月數"), -1) for r in drop]
    months = [m for m in months if m >= 0]
    if months:
        b = {"0-3 個月": 0, "4-6 個月": 0, "7-12 個月": 0, "13 個月以上": 0}
        for m in months:
            if m <= 3: b["0-3 個月"] += 1
            elif m <= 6: b["4-6 個月"] += 1
            elif m <= 12: b["7-12 個月"] += 1
            else: b["13 個月以上"] += 1
        head("死在第幾個月")
        for k, v in b.items():
            print(f"  {pad(k,14)}{pad(str(v),4,'right')} 人  {'▇'*v}")
        top = max(b, key=lambda k: b[k])
        print(f"\n{YEL}▶ 最集中的是「{top}」。{OFF}")
        print("  " + {
            "0-3 個月": "前 90 天陣亡＝陪訪不夠、期待落差太大。治本在「面談時就把難的講完」與「主管陪訪次數」。",
            "4-6 個月": "緣故名單燒完、還沒學會陌生開發。第 4 個月就該啟動市場轉換訓練。",
            "7-12 個月": "撐得住活動量、撐不住收入曲線。檢查考核門檻與他的實際件數落差。",
            "13 個月以上": "老手流失，通常是組織關係或公司制度問題，不是技能問題。",
        }[top])

    reasons = {}
    for r in drop:
        k = (r.get("脫落原因") or "未填").strip()
        reasons[k] = reasons.get(k, 0) + 1
    if reasons:
        head("脫落原因")
        for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  {pad(k,20)}{pad(str(v),4,'right')} 人")
        print(f"\n{DIM}※ 原因要問離開的人本人，不要用主管的猜測填。猜出來的原因會讓你一直修錯的地方。{OFF}")
    foot()


# ================================================================== disclose

DISCLOSE_FIELDS = [
    ("公司全名", "公司全名"),
    ("契約性質", "契約性質（承攬／僱傭）"),
    ("報酬結構", "報酬結構（初年度佣金／續年度／獎金項目）"),
    ("底薪或津貼", "是否有底薪或新人津貼、發放條件與期間"),
    ("考核制度", "考核制度（週期、標準、未達成的後果）"),
    ("自付成本", "需自行負擔的成本（證照報名費、教育訓練、交通、通訊、名片、加保勞保管道等）"),
    ("勞健保安排", "勞健保／退休金如何處理"),
    ("新人存活實況", "本單位新人 3 個月／13 個月的實際留存概況"),
    ("前三個月典型收入", "本單位新人前三個月的實際收入區間（有多少人是 0）"),
]


def cmd_disclose(args):
    d = read_json(args.json)
    head("誠實揭露包（草稿）")
    print("這一份要在「第二次面談」就攤開，不是等他報聘之後才講。\n"
          "小增的立場：把難的話講在前面，留下來的人才會留得久。\n")

    todo = []
    for key, label in DISCLOSE_FIELDS:
        v = (str(d.get(key, "")) or "").strip()
        if not v or v in ("待補", "TBD", "?"):
            todo.append(label)
            print(f"{RED}【{label}】{OFF}\n  {RED}待補 —— 這一格沒答案之前，不要對外做招募說明。{OFF}\n")
        else:
            print(f"{GRN}【{label}】{OFF}\n  {v}\n")

    head("必附的四句話（逐字，不要改寫成比較好聽的版本）")
    print("  1. 這份工作的收入不是固定的，可能連續幾個月是零，實際收入依個人業績與公司制度而定。")
    print("  2. 是否錄取、是否登錄、是否通過考試，都不是我能保證的。")
    print("  3. 我不會向你收取任何保證金、報名費，也不會扣留你的證件。")
    print("  4. 你如果現在有工作，我建議你先不要離職，等考到證照、確認自己做得下去再說。")

    if todo:
        head("結論")
        print(f"{RED}▶ 有 {len(todo)} 項待補，這份揭露包還不能用。{OFF}")
        print("  請去問你的主管／教育訓練單位，把數字問到，不要自己估。")
    else:
        head("結論")
        print(f"{GRN}▶ 九項齊全，可送所屬公司審查後使用。{OFF}")
    print(f"\n{DIM}※ 本文件為草稿，須經所屬公司／保經代審查核可後始得對外使用。{OFF}")
    foot()


# ==================================================================== plan90

PLAN = [
    (1, "報到與心理契約", ["把誠實揭露包再走一次，確認他知道前三個月可能是零",
                          "一起寫下「什麼情況下我會選擇離開」——先講好，比事後吵好",
                          "建立每日回報格式（接觸數／約訪數／面談數，不看成交）"]),
    (2, "工具與制度", ["公司系統、報表、送件流程實際走一次",
                       "商品線熟悉（只熟到能解釋，不急著背費率）",
                       "合規訓練：招攬規範、不實告知的後果"]),
    (3, "名單盤點", ["列出 100 個名字（不篩選，先寫完再說）",
                     "分類：可直接談／需要暖／不碰",
                     "🚨 若他來自同業：明確講清楚不得攜帶原公司客戶名單、不得誘導客戶解約轉單"]),
    (4, "第一次陪訪", ["主管親自陪訪 ≥ 3 件，前 2 件主管講、他看",
                       "回程 15 分鐘覆盤：他觀察到什麼，不是主管講評"]),
    (5, "他主講", ["他主講、主管只補充，≥ 3 件",
                   "開始固定週檢視：活動量而不是業績"]),
    (6, "第一次挫折", ["這週通常會出現第一次連續被拒 —— 主管要主動找他，不要等他來說",
                       "回到動機：當初他說想要的是什麼"]),
    (8, "轉市場的預告", ["提早講：緣故會用完，第 4 個月開始要有新來源",
                         "開始練一種陌生／轉介的固定動作"]),
    (10, "獨立作業", ["主管退到後面，只做事前沙盤與事後覆盤",
                      "檢查活動量是否穩定（穩定比爆量重要）"]),
    (12, "90 天覆盤", ["三方對齊：他、主管、他的家人（若當初家人有疑慮）",
                       "誠實檢視：這三個月的實際收入 vs 當初講的",
                       "決定下一季的目標——由他自己講出來"]),
]


def cmd_plan90(args):
    name = args.name or "新人"
    start = dt.date.fromisoformat(args.start) if args.start else dt.date.today()
    head(f"{name}　90 天育成計畫（起始 {start.isoformat()}）")
    print(f"{DIM}原則：前 90 天只考核「活動量」，不考核業績。業績是結果，活動量才是能被教的東西。{OFF}\n")
    for wk, title, items in PLAN:
        d0 = start + dt.timedelta(days=(wk - 1) * 7)
        d1 = d0 + dt.timedelta(days=6)
        print(f"{CYA}第 {wk:>2} 週　{d0.strftime('%m/%d')}–{d1.strftime('%m/%d')}　{title}{OFF}")
        for it in items:
            print(f"    ☐ {it}")
        print()
    head("主管的三個不可外包")
    print("  1. 陪訪 —— 前 6 週不能只交給資深同事。")
    print("  2. 那通「他被拒絕之後」的電話 —— 主動打，不要等。")
    print("  3. 誠實 —— 收入不好就說不好。新人分辨得出來你在粉飾。")
    foot()


# ===================================================================== check

# (正則, 等級, 為什麼不行, 改寫建議)
# 費用／證件規則單獨命名：它是唯一要過「自付成本」白名單的規則（見 self_paid()）
FEE_PAT = (r"(繳|交|收取|收|付|匯|給)\s*[^，。！？\n]{0,6}?(保證金|押金|報名費|工本費|訓練費)"
           r"|(繳交|附上?|押|留)\s*(證件|身分證|身份證|存摺)\s*正本|押(證件|身分證)")

RULES = [
    # ── 收入與保證 ──
    (r"保證(收入|月入|年薪|底薪|薪資|獎金|錄取|上班|考取|考過|通過|過件)", "紅",
     "保證性用語；招募廣告不得為不實或誇大之表示",
     "改為「收入依個人業績與公司制度而定，可能為零」"),
    (r"月入(數十萬|十萬|廿萬|二十萬|\d+\s*萬)|年薪百萬|百萬年薪|輕鬆月入|躺著(領|賺)", "紅",
     "以特定收入數字招募，屬誇大不實招募廣告",
     "刪除數字；改揭露「本單位新人前三個月實際收入區間」並附出處"),
    (r"穩賺|包賺|一定賺|穩定收入|收入穩定|旱澇保收", "紅",
     "承攬制報酬不固定，此類表述與事實不符", "改為「收入不固定，依業績而定」"),
    (r"被動收入|睡後收入|續期收入養你|退休後照領|(組織|團隊)收入(無限|倍增)", "紅",
     "易與多層次傳銷／不勞而獲聯想，且與事實不符",
     "改談「續年度服務津貼須持續服務並符合公司制度」"),
    (r"下線|拉人頭|人頭|抽成分潤|人脈變現", "紅",
     "傳銷式話術，保險增員不是拉人頭", "整段刪除，改談職涯與訓練制度"),
    # ── 不實工作內容 ──
    (r"不用(業績|考核|拉保險|做業績|跑客戶)|沒有(業績|考核)壓力|零壓力|不用拜訪", "紅",
     "與事實不符之招募內容", "如實揭露考核制度與活動量要求"),
    (r"(工作|時間)自由|想上班就上班|在家(工作|就能|躺著)|(超級)?輕鬆", "黃",
     "易造成期待落差，是前 90 天脫落的主因之一",
     "改為「時間可自行安排，但要達成考核需要穩定的每週活動量」"),
    (r"包教包會|保證上手|免經驗也能做得好|人人都適合", "黃",
     "誇大訓練效果", "改為「有完整訓練制度，但成果因人而異」"),
    # ── 就業服務法：歧視 ──
    (r"限(男|女)性?|男性?佳|女性?佳|限未婚|限已婚|需未婚|限本國人", "紅",
     "就業服務法禁止以性別、婚姻、種族等為就業歧視", "刪除該條件"),
    (r"(年齡|年紀)\s*\d+\s*[-~至到]\s*\d+|限\s*\d+\s*歲|\d+\s*歲以下|需年輕", "紅",
     "年齡為就業服務法明定不得歧視之項目", "刪除年齡限制"),
    (r"星座|血型|生肖|面相|八字|外貌佳|형象|形象佳|身高|體重|需有車", "紅",
     "非工作必要條件，涉就業歧視", "刪除；改列真正的工作必要條件"),
    # ── 就業服務法：費用與證件 ──
    (FEE_PAT, "紅",
     "不得向求職人收取保證金或扣留證件財物",
     "刪除；並在文案中明寫「不收取任何費用、不扣留證件」"),
    # ── 挖角與轉單 ──
    (r"(把|帶)(你的|他的)?(客戶|保戶)?(客戶|名單|保戶)(一起)?(帶|轉|拉)(過來|走)|沿用原(公司)?名單", "紅",
     "原公司客戶名單屬其營業秘密，唆使攜出恐涉法律責任",
     "刪除；改為「到職後從自己的人際關係重新開始」"),
    (r"(解約|轉單)(重買|再買)|叫客戶解約|退佣|回佣|佣金(分你|退你)", "紅",
     "誘導解約轉保與退佣皆屬招攬重大違規", "整段刪除"),
    (r"先掛(我|在我)|借牌|掛件|掛我這邊|用我的登錄", "紅",
     "未登錄不得招攬；掛件借牌是撤登錄等級的違規", "整段刪除"),
    # ── 其他 ──
    (r"(直接|馬上|立刻|快速)(升|做|當)主管|\d+\s*個月(直接|就|即可)?(升|當|做)主管|快速升遷保證", "黃",
     "晉升有制度條件，不可承諾", "改為「晉升依公司制度之考核標準辦理」"),
    (r"我們公司(最|第一)|業界第一|最好的公司|唯一", "黃",
     "最高級與比較性用語", "改為具體制度描述，不做排名"),
    (r"(離職|辭職)(再說|來做就對了)|先辭再說", "紅",
     "勸人先離職風險極高，且與誠實揭露原則衝突",
     "改為「建議先不要離職，考到證照、確認做得下去再決定」"),
]

# 招募文件應具備的四段揭露
NEEDED = [
    ("契約性質揭露", r"承攬|僱傭|勞務契約|非僱傭"),
    ("收入不固定揭露", r"收入.{0,12}(不固定|不是固定|非固定|依.{0,6}業績|可能為零|可能是零|可能連續.{0,8}零)"),
    ("考核制度揭露", r"考核"),
    ("不收費用揭露", r"不(會)?(向你)?(收取|收)[^，。\n]{0,8}(費用|保證金|報名費)|不(會)?扣留"),
]


NEG_RE = re.compile(r"(不會|不得|不可|不能|不收|不向|不是|免收|無需|絕不|禁止|嚴禁|我不|絕對不)[^，。；！？\n]{0,8}$")


def negated(line, start):
    """命中詞前面 4 字內有否定語 → 這是在『宣告我不做這件事』，不算違規"""
    return bool(NEG_RE.search(line[:start]))


# 「自付成本」= 求職人自己要花的錢，不是本單位向他收費。
# 誠實揭露包第 6 欄本來就要求逐項揭露這些成本，掃描器不能罰它自己要求做的事。
# 注意：「自行」必須後面直接接負擔／支付類動詞才算，單獨一個「自行」不放行
#（例：「請自行於報到前繳交報名費」仍然是紅字）。
SELF_PAY_RE = re.compile(
    r"自付|自費|自行(負擔|支付|支出|吸收|繳納|繳交|繳|付)|自己(出|付|負擔|支付)|自備|"
    r"(本人|個人|學員|求職人)(自行)?(負擔|支付|支出)"
)

# 保證金、押金沒有「自付」的正當版本；扣證件更不用說 → 一律不放行
SELF_PAY_FEES = ("報名費", "工本費", "訓練費")


def self_paid(line, m):
    """命中的是『自付成本』式揭露 → 不算向求職人收費。

    只放行報名費／工本費／訓練費這類求職人本來就得自己出的錢；
    保證金、押金、扣留證件永遠是紅字，不受此守門影響。
    """
    if not m.group(0).endswith(SELF_PAY_FEES):
        return False
    clause = re.split(r"[，。；！？\n]", line[:m.end()])[-1]
    return bool(SELF_PAY_RE.search(clause))


def cmd_check(args):
    path = args.file
    if not os.path.exists(path):
        die(f"找不到檔案：{path}")
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    head(f"合規掃描：{os.path.basename(path)}")
    hits = []
    for i, line in enumerate(lines, 1):
        for pat, level, why, fix in RULES:
            for m in re.finditer(pat, line):
                if negated(line, m.start()):
                    continue
                if pat is FEE_PAT and self_paid(line, m):
                    continue
                hits.append((i, level, m.group(0), why, fix, line.strip()))

    red = [h for h in hits if h[1] == "紅"]
    yel = [h for h in hits if h[1] == "黃"]

    if not hits:
        print(f"{GRN}  禁語掃描：沒有命中。{OFF}")
    for i, level, word, why, fix, ctx in hits:
        color = RED if level == "紅" else YEL
        print(f"{color}  [{level}] 第 {i} 行　「{word}」{OFF}")
        print(f"        原因：{why}")
        print(f"        改法：{fix}")
        print(f"        {DIM}原句：{ctx[:70]}{OFF}")

    head("四段揭露檢查")
    text = "\n".join(lines)
    miss = []
    for name, pat in NEEDED:
        if re.search(pat, text):
            print(f"{GRN}  ✔ {name}{OFF}")
        else:
            print(f"{RED}  ✘ {name} —— 缺{OFF}")
            miss.append(name)

    head("結論")
    if red or miss:
        print(f"{RED}▶ 不准交件。紅字 {len(red)} 處、黃字 {len(yel)} 處、缺揭露 {len(miss)} 段。{OFF}")
        sys.exit(2)
    elif yel:
        print(f"{YEL}▶ 沒有紅字，但有 {len(yel)} 處黃字（期待落差風險）。建議改完再送審。{OFF}")
    else:
        print(f"{GRN}▶ 通過小增的掃描。{OFF}")
    print(f"\n{DIM}※ 通過本掃描 ≠ 合規。對外使用前仍須經所屬公司／保經代文宣審查核可。{OFF}")
    foot()


# ====================================================================== init

def cmd_init(args):
    import shutil
    if not os.path.isdir(TPL_DIR):
        die(f"找不到範本資料夾：{TPL_DIR}")
    n = 0
    for fn in sorted(os.listdir(TPL_DIR)):
        src = os.path.join(TPL_DIR, fn)
        dst = os.path.join(os.getcwd(), fn)
        if os.path.isfile(src):
            if os.path.exists(dst):
                print(f"{YEL}  略過（已存在）：{fn}{OFF}")
                continue
            shutil.copy2(src, dst)
            print(f"{GRN}  產出：{fn}{OFF}")
            n += 1
    head("下一步")
    print("  1. 填 招募主管資料卡.json（九項誠實揭露欄位，問到才填，不要估）")
    print("  2. 把名單填進 增員名單表.csv，跑 `zeng.py pipeline 增員名單表.csv`")
    print("  3. 每月把數字填進 增員漏斗表.csv，跑 `zeng.py funnel 增員漏斗表.csv`")
    print(f"\n{RED}  🚨 這些檔案含求職者個資，放本機碟，不要放 iCloud 桌面、不要進群組。{OFF}")
    foot()


def main():
    p = argparse.ArgumentParser(description="小增 — 保險增員／人力招募專員")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("funnel", help="漏斗轉換率與瓶頸診斷"); s.add_argument("csv"); s.set_defaults(fn=cmd_funnel)
    s = sub.add_parser("score", help="面談七維度評分"); s.add_argument("json"); s.set_defaults(fn=cmd_score)
    s = sub.add_parser("pipeline", help="名單池體檢"); s.add_argument("csv"); s.set_defaults(fn=cmd_pipeline)
    s = sub.add_parser("retention", help="定著率與脫落分析"); s.add_argument("csv"); s.set_defaults(fn=cmd_retention)
    s = sub.add_parser("disclose", help="誠實揭露包草稿"); s.add_argument("json"); s.set_defaults(fn=cmd_disclose)
    s = sub.add_parser("plan90", help="新人 90 天育成計畫")
    s.add_argument("--name"); s.add_argument("--start"); s.set_defaults(fn=cmd_plan90)
    s = sub.add_parser("check", help="合規禁語掃描"); s.add_argument("file"); s.set_defaults(fn=cmd_check)
    s = sub.add_parser("init", help="產出所有範本"); s.set_defaults(fn=cmd_init)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
