#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
spacemgr.py — AI 員工「小空」的空間設計 × 客戶互動管線工具
Sixhands Studio AI數字員工 🦞

零安裝、不連網、不用裝任何套件（純 Python 標準函式庫）。
Mac / Windows 皆可執行。Windows 請把 python3 換成 python。

    python3 spacemgr.py init   --dir "./林宅_大安三房"
    python3 spacemgr.py brief  --dir "./林宅_大安三房"
    python3 spacemgr.py space  --area 32.5 --unit 坪 --people 4
    python3 spacemgr.py change --dir "./林宅_大安三房" --contract 1850000
    python3 spacemgr.py change --dir "./林宅_大安三房" --new
    python3 spacemgr.py report --dir "./林宅_大安三房" --week 6
    python3 spacemgr.py scan   --file "提案.txt"
"""
import argparse
import csv
import json
import os
import sys

ENC = "utf-8-sig"        # CSV：Excel 開得起來
ENC_TXT = "utf-8"        # 純文字 / Markdown

PING_TO_M2 = 3.305785
M2_TO_PING = 0.3025
TSAI_M2 = 0.303 * 0.303  # 才（玻璃石材）≈ 0.0918 ㎡

CARD = "客戶資料卡.json"

# ─────────────────────────────────────────── 表格定義

TABLES = {
    "1_客戶名單.csv": [
        "編號", "建檔日期", "案名", "屋主稱呼", "決策者", "聯絡方式",
        "行政區", "屋型", "屋齡", "室內坪數", "格局", "居住人數",
        "預算範圍", "期望完工", "來源", "目前階段", "下次聯繫日", "備註",
    ],
    "2_需求清單.csv": [
        "編號", "案名", "屋主原話", "真正的需求", "解法A", "解法B",
        "優先級", "空間", "預估費用", "狀態", "備註",
    ],
    "3_選材決策.csv": [
        "編號", "案名", "空間", "項目", "材料品名", "型號", "顏色編號",
        "單價", "供應商", "樣板是否給屋主看過", "屋主確認日", "狀態", "備註",
    ],
    "4_變更單.csv": [
        "編號", "日期", "案名", "提出方", "項目名稱", "規格說明", "單位",
        "單價", "數量", "小計", "追加或減帳", "工期影響天數",
        "屋主確認方式", "確認日期", "狀態", "備註",
    ],
    "5_工程進度.csv": [
        "週次", "日期", "案名", "本週完成", "下週預計", "需屋主決定",
        "決定截止日", "工期狀態", "順延天數", "順延原因", "照片張數", "備註",
    ],
}

SAMPLES = {
    "1_客戶名單.csv": [{
        "編號": "C-001", "建檔日期": "2026-09-01", "案名": "★範例｜林宅",
        "屋主稱呼": "林小姐", "決策者": "林小姐＋先生（兩人都要點頭）",
        "聯絡方式": "LINE: lin123", "行政區": "台北市大安區", "屋型": "電梯大樓",
        "屋齡": "28年", "室內坪數": "32.5", "格局": "3房2廳2衛", "居住人數": "4",
        "預算範圍": "180–220萬（不含家電家具窗簾）", "期望完工": "2027-01",
        "來源": "舊客轉介", "目前階段": "已訪談", "下次聯繫日": "2026-09-08",
        "備註": "★這是範例列，請刪掉再填自己的",
    }],
    "2_需求清單.csv": [{
        "編號": "R-001", "案名": "★範例｜林宅",
        "屋主原話": "我想要一個中島", "真正的需求": "煮飯時能看到客廳的小孩",
        "解法A": "半高吧台＋開放視線", "解法B": "廚房牆面開長條視線窗口",
        "優先級": "必須", "空間": "廚房", "預估費用": "6–12萬",
        "狀態": "待屋主排序", "備註": "★範例列請刪除",
    }],
    "3_選材決策.csv": [{
        "編號": "M-001", "案名": "★範例｜林宅", "空間": "全室", "項目": "地板",
        "材料品名": "超耐磨木地板", "型號": "XX-1234", "顏色編號": "淺橡",
        "單價": "4200", "供應商": "○○建材", "樣板是否給屋主看過": "是",
        "屋主確認日": "2026-09-20", "狀態": "已確認", "備註": "★範例列請刪除",
    }],
    "4_變更單.csv": [{
        "編號": "CO-001", "日期": "2026-10-05", "案名": "★範例｜林宅",
        "提出方": "屋主", "項目名稱": "主臥增設插座", "規格說明": "雙孔附接地 2 處",
        "單位": "式", "單價": "2800", "數量": "1", "小計": "2800",
        "追加或減帳": "追加", "工期影響天數": "0",
        "屋主確認方式": "LINE文字確認", "確認日期": "2026-10-05",
        "狀態": "已確認", "備註": "★範例列請刪除",
    }],
    "5_工程進度.csv": [{
        "週次": "1", "日期": "2026-10-03", "案名": "★範例｜林宅",
        "本週完成": "保護工程完成；拆除完成 80%",
        "下週預計": "拆除清運；泥作進場放樣",
        "需屋主決定": "衛浴磁磚色號（A/B 二選一）", "決定截止日": "2026-10-08",
        "工期狀態": "依原訂進度", "順延天數": "0", "順延原因": "",
        "照片張數": "5", "備註": "★範例列請刪除",
    }],
}

# ─────────────────────────────────────────── 紅線禁字（對應 references/空間設計法規紅線.md）

BANNED = [
    ("保證合法", "本案是否須辦理室內裝修審查，以主管建築機關認定為準"),
    ("免申請", "是否須申請以主管建築機關認定為準"),
    ("不用申請", "是否須申請以主管建築機關認定為準"),
    ("不用送審", "如需辦理，由具登記資格之單位及開業建築師辦理送審"),
    ("一定過", "審查結果由主管機關決定，補正作業由我方協助"),
    ("保證通過", "審查結果由主管機關決定"),
    ("保證過關", "審查結果由主管機關決定"),
    ("包過", "審查結果由主管機關決定"),
    ("可以拆", "此牆是否為結構牆須經結構／土木技師確認後始得評估"),
    ("直接打掉", "須經結構／土木技師確認後始得評估"),
    ("打掉沒問題", "須經結構／土木技師確認後始得評估"),
    ("保證不裂", "新舊介面可能產生細微裂縫屬正常現象，保固範圍見合約"),
    ("絕對不會裂", "新舊介面可能產生細微裂縫屬正常現象"),
    ("消防一定過", "依主管機關核准圖說施作，材料檢附合格證明"),
    ("零甲醛", "使用符合 CNS 2215 F☆☆☆☆ 等級板材（檢測報告可提供）"),
    ("無甲醛", "使用符合 CNS 2215 F☆☆☆☆ 等級板材"),
    ("無毒", "使用具檢測報告之低逸散建材"),
    ("絕對防水", "防水施作範圍為 XX，保固 X 年"),
    ("永不漏水", "防水保固 X 年，範圍為施作面之滲漏"),
    ("終身保固", "保固 X 年，範圍為本工程施作項目之施工瑕疵"),
    ("一勞永逸", "刪除，改寫具體保固年限與範圍"),
    ("保證如期", "預計工期 XX 個工作天，不含假日、天候、缺料及變更展延"),
    ("絕對準時", "預計工期 XX 個工作天，不含不可抗力因素"),
    ("完工就長這樣", "示意圖僅供空間感受參考，實際以合約圖說及建材樣板為準"),
    ("一模一樣", "示意圖僅供參考，材質色差以樣板為準"),
    ("業界最低", "刪除（比較性用語易涉不實廣告）"),
    ("最便宜", "刪除，改寫「本報價含 X、Y、Z，不含 A、B」"),
    ("第一品牌", "刪除（無客觀依據之最高級用語）"),
    ("唯一", "刪除或改為具體事實敘述"),
    ("漏財", "改為設計回應：可用半高櫃／玻璃隔屏處理，同時增加收納"),
    ("破財", "不做吉凶斷言，只做設計回應"),
    ("招財", "不做吉凶斷言，只做設計回應"),
    ("旺運", "不做吉凶斷言，只做設計回應"),
    ("化煞", "不做吉凶斷言，只做設計回應"),
]

# 「一坪X元起」型誘餌：出現「起」且同段沒有「不含」
PRICE_HINT = "起"

DISCLAIMERS = [
    "示意圖僅供空間感受參考。實際材質紋理、色差、五金樣式、燈光色溫、家具尺寸與比例，"
    "以合約圖說、建材樣板及實際到貨品項為準。",
    "本案是否須辦理室內裝修審查，以案場所在地主管建築機關認定為準；"
    "如需辦理，將由具室內裝修業登記資格之單位及開業建築師／專業技術人員辦理送審。",
    "涉及牆體、樑柱、樓板等主要構造之變動，須經結構／土木技師確認後始得施作。",
    "本報價依現況可見範圍估算；拆除後如發現壁癌、管線老化、結構異常等隱蔽狀況，"
    "將另開變更單經業主確認後施作。",
]

EXCLUDES = [
    "拆除清運", "公共區域保護工程", "大樓管理費與裝修押金", "電梯使用費",
    "冷氣主機與安裝", "家電", "活動家具", "窗簾", "燈具", "細清與垃圾清運",
    "假日／夜間施工加成", "室內裝修送審規費", "水電外線與管制申請",
]


# ─────────────────────────────────────────── 共用

def die(msg):
    print("✗ " + msg)
    sys.exit(1)


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding=ENC, newline="") as f:
        return [r for r in csv.DictReader(f)]


def live_rows(rows):
    """濾掉範例列（案名或備註帶 ★）"""
    out = []
    for r in rows:
        blob = (r.get("案名", "") or "") + (r.get("備註", "") or "")
        if "★" in blob:
            continue
        if not any((v or "").strip() for v in r.values()):
            continue
        out.append(r)
    return out


def num(v):
    try:
        return float(str(v).replace(",", "").replace("NT$", "").strip() or 0)
    except ValueError:
        return 0.0


def money(v):
    return "NT$ {:,.0f}".format(v)


def title(t):
    print("\n" + "─" * 60)
    print("  " + t)
    print("─" * 60)


# ─────────────────────────────────────────── init

def cmd_init(args):
    d = args.dir
    os.makedirs(d, exist_ok=True)
    for name, cols in TABLES.items():
        p = os.path.join(d, name)
        if os.path.exists(p):
            print("· 已存在，略過：" + name)
            continue
        with open(p, "w", encoding=ENC, newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for row in SAMPLES.get(name, []):
                w.writerow({c: row.get(c, "") for c in cols})
        print("✓ 建立 " + name)

    card = os.path.join(d, CARD)
    if not os.path.exists(card):
        here = os.path.dirname(os.path.abspath(__file__))
        src = os.path.join(here, "..", "templates", CARD)
        try:
            with open(src, "r", encoding=ENC_TXT) as f:
                data = f.read()
        except OSError:
            data = json.dumps({"_說明": "請參考 skill 的 templates/客戶資料卡.json"},
                              ensure_ascii=False, indent=2)
        with open(card, "w", encoding=ENC_TXT) as f:
            f.write(data)
        print("✓ 建立 " + CARD)

    for sub in ("01_現況照", "02_丈量", "03_提案", "04_施工紀錄"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    print("✓ 建立素材資料夾 01_現況照 / 02_丈量 / 03_提案 / 04_施工紀錄")

    title("下一步")
    print("1. 填 " + CARD + "（不會的看 references/待補15題.md）")
    print("2. 訪談用 templates/生活習慣訪談表.md，用屋主原話記")
    print("3. 需求填進 2_需求清單.csv，再跑：")
    print("   python3 spacemgr.py brief --dir \"%s\"" % d)
    print("\n⚠️ 這個資料夾請放本機碟，不要放 iCloud 桌面。")


# ─────────────────────────────────────────── brief

def cmd_brief(args):
    d = args.dir
    if not os.path.isdir(d):
        die("找不到資料夾：" + d + "（先跑 init）")

    info = {}
    card = os.path.join(d, CARD)
    if os.path.exists(card):
        try:
            with open(card, "r", encoding=ENC_TXT) as f:
                info = json.load(f)
        except (OSError, ValueError):
            info = {}
    case = info.get("本案", {}) if isinstance(info, dict) else {}

    reqs = live_rows(read_csv(os.path.join(d, "2_需求清單.csv")))
    if args.case:
        reqs = [r for r in reqs if args.case in (r.get("案名") or "")]

    order = {"必須": 0, "想要": 1, "加分": 2}
    reqs.sort(key=lambda r: order.get((r.get("優先級") or "").strip(), 3))
    must = [r for r in reqs if (r.get("優先級") or "").strip() == "必須"]

    name = args.case or case.get("案名") or "＿＿＿＿"
    L = []
    L.append("# 設計需求確認書")
    L.append("")
    L.append("**案名**：%s　　**版本**：v1" % name)
    L.append("")
    L.append("> 這份文件是我們對您需求的理解。")
    L.append("> **請您看過，有不對的地方直接改。** 您確認之後，我們就依這份開始規劃。")
    L.append("")
    L.append("## 一、案場基本資料")
    L.append("")
    L.append("| 項目 | 內容 |")
    L.append("|:---|:---|")
    for k in ("行政區", "屋型", "屋齡", "室內坪數", "格局"):
        L.append("| %s | %s |" % (k, case.get(k, "") or "（待補）"))
    mem = info.get("居住成員", {}) if isinstance(info, dict) else {}
    L.append("| 居住成員 | %s |" % (mem.get("人數", "") or "（待補）"))
    L.append("")

    L.append("## 二、本案要解決的三個核心問題")
    L.append("")
    if must:
        for i, r in enumerate(must[:3], 1):
            L.append("%d. 「%s」" % (i, r.get("屋主原話", "")))
    else:
        L.append("（2_需求清單.csv 尚無「必須」項目，請先完成需求轉譯）")
    L.append("")

    L.append("## 三、需求清單")
    L.append("")
    L.append("| 屋主的話 | 真正要解決的 | 規劃方向 | 優先級 |")
    L.append("|:---|:---|:---|:---|")
    for r in reqs:
        sol = " / ".join(x for x in (r.get("解法A"), r.get("解法B")) if x)
        L.append("| %s | %s | %s | %s |" % (
            r.get("屋主原話", ""), r.get("真正的需求", ""), sol, r.get("優先級", "")))
    if not reqs:
        L.append("| （待補） | | | |")
    L.append("")
    L.append("> 「必須」以 5 項為上限，優先級由屋主排定。")
    L.append("")

    L.append("## 四、明確排除項目")
    L.append("")
    L.append("- 不做：")
    L.append("- 不用的材質／顏色：")
    L.append("")

    bud = info.get("預算與時程", {}) if isinstance(info, dict) else {}
    L.append("## 五、預算與含項")
    L.append("")
    L.append("- 預算範圍：%s" % (bud.get("總預算", "") or "＿＿＿＿"))
    L.append("- **含**：%s" % ("、".join(bud.get("預算含項", [])) or "（待填）"))
    L.append("- **不含**：" + "、".join(EXCLUDES))
    L.append("- 超支處理原則：任何追加一律**開變更單經您確認後施作**")
    L.append("")

    L.append("## 六、時程與關鍵節點")
    L.append("")
    L.append("| 節點 | 預計日期 | 需要您做的事 |")
    L.append("|:---|:---|:---|")
    for n, todo in [
        ("初步平面提案", "出席並決定方向"),
        ("平面定案", "**簽名確認（定案基準）**"),
        ("建材選定", "到場看樣板"),
        ("開工進場", ""),
        ("水電配置確認", "**現場走一次，確認開關插座位置**"),
        ("天花封板前", "現場確認"),
        ("預驗收", "現場"),
        ("交屋", "驗收簽署"),
    ]:
        L.append("| %s | | %s |" % (n, todo))
    L.append("")

    L.append("## 七、待確認事項（風險揭露）")
    L.append("")
    for t in DISCLAIMERS[1:]:
        L.append("- [ ] " + t)
    L.append("- [ ] 管委會裝修規約（施工時段、押金、電梯保護）待取得")
    L.append("")

    L.append("## 八、雙方確認")
    L.append("")
    L.append("> 本確認書所載為需求方向之共識，具體施作範圍、材料規格、金額與權利義務，"
             "以雙方另行簽訂之設計／工程契約及核准圖說為準。")
    L.append("> " + DISCLAIMERS[0])
    L.append("")
    L.append("| | 簽名 | 日期 |")
    L.append("|:---|:---|:---|")
    L.append("| 業主 | | |")
    L.append("| 設計方 | | |")
    L.append("")
    L.append("---")
    L.append("**Sixhands Studio AI數字員工**　🦞　由小空 Xiao Kong 協助整理")

    out = os.path.join(d, "設計需求確認書.md")
    with open(out, "w", encoding=ENC_TXT) as f:
        f.write("\n".join(L) + "\n")
    print("✓ 已產出：" + out)

    title("交件前檢查")
    if len(must) > 5:
        print("⚠️ 「必須」有 %d 項（建議 ≤5）。請屋主自己排序，砍到 5 項以內。" % len(must))
    if not must:
        print("⚠️ 沒有任何「必須」項目 —— 這代表需求還沒排序，不要往下走。")
    print("· 每一句需求都要是屋主原話，不是你的詮釋")
    print("· 第七段「待確認事項」不可空白")
    print("· 寄出時附一句：「請您看一下我聽到的對不對，確認後我們就開始規劃。」")


# ─────────────────────────────────────────── space

def cmd_space(args):
    a = args.area
    unit = args.unit
    if unit in ("坪", "ping", "p"):
        ping, m2 = a, a * PING_TO_M2
    elif unit in ("㎡", "m2", "平方公尺"):
        m2, ping = a, a * M2_TO_PING
    else:
        die("--unit 只接受 坪 或 ㎡")
        return

    title("面積換算")
    print("  %.2f 坪  =  %.2f ㎡  =  %.1f 才(玻璃石材)" % (ping, m2, m2 / TSAI_M2))
    print("  1 台尺 = 30.3 cm　｜　1 坪 = 3.3058 ㎡")

    title("收納量體檢核")
    lo, hi = m2 * 0.10, m2 * 0.12
    print("  建議收納投影面積：%.2f – %.2f ㎡（%.2f – %.2f 坪）" %
          (lo, hi, lo * M2_TO_PING, hi * M2_TO_PING))
    print("  低於 8% 幾乎一定會亂；高於 15% 要檢查是不是犧牲了活動空間。")
    if args.people:
        n = args.people
        print("  %d 人的衣物吊掛需求：約 %d – %d cm 吊桿總寬" % (n, n * 90, n * 120))
    if args.shoes:
        s = args.shoes
        layers = -(-s // 5)  # 每 100cm 層板約 5 雙
        print("  %d 雙鞋：約需 %d 層 × 100 cm 層板（鞋櫃深 35–40 cm）" % (s, layers))

    title("動線淨寬（檢核用）")
    for k, v in [("主動線", "90–120 cm"), ("次動線", "70–80 cm"),
                 ("單排廚具前", "90–110 cm"), ("雙排／中島之間", "100–120 cm"),
                 ("餐椅拉開＋通行", "105–120 cm"), ("床邊", "60 cm 以上，舒適 70–90"),
                 ("輪椅通行", "直行 90 cm，迴轉直徑 150 cm")]:
        print("  %-14s %s" % (k, v))

    title("關鍵尺寸（最常出錯的幾個）")
    for k, v in [("廚具檯面高", "身高÷2+5，常見 85–90 cm"),
                 ("吊櫃下緣距檯面", "60–70 cm"),
                 ("衣櫃深（吊掛）", "60 cm"),
                 ("鞋櫃深", "35–40 cm"),
                 ("馬桶左右淨寬", "70–75 cm 以上，前方 60 cm"),
                 ("淋浴間", "最小 80×80，舒適 90×120"),
                 ("開關中心離地", "110–120 cm"),
                 ("一般插座離地", "30 cm；檯面上 105–115 cm"),
                 ("天花完成面淨高", "≥ 240 cm")]:
        print("  %-16s %s" % (k, v))

    print("\n⚠️ 以上為設計常用參考值，非法規值。")
    print("⚠️ 任何牆體、樑柱、樓板變動 → 須結構／土木技師確認（紅線 2）。")
    print("→ 完整清單見 references/空間規劃知識庫.md")


# ─────────────────────────────────────────── change

def cmd_change(args):
    if args.new:
        title("空白變更單（貼給屋主用）")
        print("""【工程變更單】編號 CO-___　日期 ____/__/__
案名：
提出方：□屋主　□設計方（拆除後發現隱蔽狀況）
項目名稱：
規格說明：
單價：NT$ ____ × 數量 ____ = 小計 NT$ ____
性質：□追加　□減帳
工期影響：____ 天

【給屋主的話】
這張單不是跟您計較，是怕最後結算的時候您被嚇到，那個才傷感情。
您看過覺得 OK，回我一個「確認」我們就施作；沒有您的確認我們不會動工。

業主確認：□簽名　□LINE 文字回覆　　日期：____/__/__""")
        print("\n填完登錄進 4_變更單.csv。**收到確認才施作。**")
        return

    d = args.dir
    if not d or not os.path.isdir(d):
        die("找不到資料夾：%s（或用 --new 產空白單）" % d)
    rows = live_rows(read_csv(os.path.join(d, "4_變更單.csv")))
    if args.case:
        rows = [r for r in rows if args.case in (r.get("案名") or "")]

    add = sum(num(r.get("小計")) for r in rows if num(r.get("小計")) > 0)
    sub = sum(num(r.get("小計")) for r in rows if num(r.get("小計")) < 0)
    net = add + sub
    days = sum(num(r.get("工期影響天數")) for r in rows)
    unconf = [r for r in rows if (r.get("狀態") or "").strip() != "已確認"]

    title("追加減帳彙總（%d 張變更單）" % len(rows))
    print("  追加合計：%s" % money(add))
    print("  減帳合計：%s" % money(sub))
    print("  淨變動　：%s" % money(net))
    print("  工期影響：%+d 天" % int(days))
    if args.contract:
        pct = net / args.contract * 100 if args.contract else 0
        print("  占合約總價 %s 的 %.1f%%" % (money(args.contract), pct))
        if abs(pct) >= 10:
            print("  ⚠️ 已超過 10%%，強烈建議與屋主重新對一次總表，避免結算爭議。")

    if unconf:
        title("⚠️ 尚未取得屋主書面確認（%d 張）" % len(unconf))
        for r in unconf:
            print("  · %s %s（%s）狀態：%s" % (
                r.get("編號", ""), r.get("項目名稱", ""),
                money(num(r.get("小計"))), r.get("狀態", "") or "空白"))
        print("\n  **沒有確認就施作 = 你自己出錢做慈善。** 今天就補確認。")
    else:
        print("\n✓ 所有變更單皆已取得屋主確認。")


# ─────────────────────────────────────────── report

def cmd_report(args):
    d = args.dir
    if not os.path.isdir(d):
        die("找不到資料夾：" + d)
    rows = live_rows(read_csv(os.path.join(d, "5_工程進度.csv")))
    if args.case:
        rows = [r for r in rows if args.case in (r.get("案名") or "")]
    if not rows:
        die("5_工程進度.csv 沒有資料。請先填本週進度。")

    if args.week:
        pick = [r for r in rows if str(r.get("週次", "")).strip() == str(args.week)]
        if not pick:
            die("找不到第 %s 週的紀錄。" % args.week)
        r = pick[-1]
    else:
        r = rows[-1]

    ch = live_rows(read_csv(os.path.join(d, "4_變更單.csv")))
    if args.case:
        ch = [c for c in ch if args.case in (c.get("案名") or "")]
    net = sum(num(c.get("小計")) for c in ch)

    name = (r.get("案名") or "本案").replace("★", "")
    lines = []
    lines.append("【%s 裝修進度｜第 %s 週｜%s】" % (name, r.get("週次", ""), r.get("日期", "")))
    lines.append("")
    lines.append("■ 這週完成")
    for it in [x.strip() for x in (r.get("本週完成") or "").replace("、", ";").split(";") if x.strip()]:
        lines.append("・" + it)
    lines.append("")
    lines.append("■ 下週預計")
    for it in [x.strip() for x in (r.get("下週預計") or "").replace("、", ";").split(";") if x.strip()]:
        lines.append("・" + it)
    lines.append("")
    need = (r.get("需屋主決定") or "").strip()
    lines.append("■ 需要您決定" + ("（截止 %s）" % r.get("決定截止日") if r.get("決定截止日") else ""))
    lines.append("・" + (need if need else "本週沒有需要您決定的事項，請放心。"))
    lines.append("")
    lines.append("■ 目前狀況")
    st = r.get("工期狀態") or "依原訂進度"
    delay = num(r.get("順延天數"))
    if delay:
        st += "（順延 %d 天：%s）" % (int(delay), r.get("順延原因") or "原因待補")
    lines.append("工期：" + st)
    if net:
        lines.append("追加減帳累計：%s%s" % ("＋" if net > 0 else "－", money(abs(net))))
    else:
        lines.append("追加減帳累計：目前無變更")
    lines.append("")
    lines.append("（附現場照 %s 張）" % (r.get("照片張數") or "3–5"))

    text = "\n".join(lines)
    out = os.path.join(d, "進度回報_第%s週.txt" % (r.get("週次") or "X"))
    with open(out, "w", encoding=ENC_TXT) as f:
        f.write(text + "\n")

    title("可直接貼 LINE 的內容")
    print(text)
    print("\n✓ 已存檔：" + out)

    title("三個規則")
    print("1. 有變更、有延誤 → 第一時間主動講。被屋主發現 = 隱瞞。")
    if not need:
        print("2. ⚠️ 這週沒有「需要您決定」的事項 —— 確認一下是真的沒有，還是漏填了。")
    else:
        print("2. ✓ 有「需要您決定」，很好 —— 讓屋主知道他也有責任。")
    print("3. 照片要拍**同一個角度**，屋主才看得出進展。")


# ─────────────────────────────────────────── scan

def cmd_scan(args):
    p = args.file
    if not os.path.exists(p):
        die("找不到檔案：" + p)
    with open(p, "r", encoding=ENC_TXT, errors="replace") as f:
        lines = f.read().splitlines()

    hits = []
    for i, line in enumerate(lines, 1):
        for bad, fix in BANNED:
            if bad in line:
                hits.append((i, bad, fix, line.strip()))

    title("紅線禁字掃描：%s" % os.path.basename(p))
    if hits:
        for ln, bad, fix, ctx in hits:
            print("\n✗ 第 %d 行　禁字：「%s」" % (ln, bad))
            print("   原文：%s" % (ctx[:70] + ("…" if len(ctx) > 70 else "")))
            print("   改成：%s" % fix)
        print("\n共 %d 處。**全部改完才准交件。**" % len(hits))
    else:
        print("✓ 沒有掃到禁字。")

    text = "\n".join(lines)
    title("附加檢查")
    if PRICE_HINT in text and "不含" not in text:
        print("⚠️ 文中有「起」字價格但沒有「不含」說明 → 誘餌式廣告風險，請補含項／不含項。")
    else:
        print("· 價格含項：OK（或文中未提價）")

    for key, why in [
        ("示意", "3D／示意圖標註"),
        ("不含", "報價不含項"),
    ]:
        print("%s %s：%s" % ("·" if key in text else "⚠️", why,
                            "有" if key in text else "文中未見，若文件含圖或價格請補"))

    if any(w in text for w in ("拆", "打掉", "牆")):
        print("⚠️ 文中提到拆牆／牆面 → 確認是否已寫「須經結構技師確認」。")
    if any(w in text for w in ("店", "餐", "辦公", "補習", "診所", "營業")):
        print("⚠️ 疑似商業空間 → 確認是否已寫室內裝修審查與消防的保留語句（紅線 1、3）。")

    title("四道交件檢查（人工確認）")
    print("1. 合法檢查：紅線 1–8 全過？")
    print("2. 對齊檢查：每個需求都對得上訪談原話？")
    print("3. 金額檢查：含什麼、不含什麼都寫清楚？")
    print("4. 下一步檢查：屋主知道下一步做什麼、什麼時候？")
    print("\n→ 完整對照見 references/空間設計法規紅線.md")
    sys.exit(1 if hits else 0)


# ─────────────────────────────────────────── main

def main():
    ap = argparse.ArgumentParser(
        description="小空 spacemgr — 空間設計 × 客戶互動管線工具（Sixhands Studio AI數字員工 🦞）")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("init", help="建立專案資料夾與五張工作表")
    p.add_argument("--dir", required=True)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("brief", help="產出設計需求確認書")
    p.add_argument("--dir", required=True)
    p.add_argument("--case", default="")
    p.set_defaults(func=cmd_brief)

    p = sub.add_parser("space", help="面積換算與尺寸／收納檢核")
    p.add_argument("--area", type=float, required=True)
    p.add_argument("--unit", default="坪")
    p.add_argument("--people", type=int, default=0)
    p.add_argument("--shoes", type=int, default=0)
    p.set_defaults(func=cmd_space)

    p = sub.add_parser("change", help="追加減帳彙總／產空白變更單")
    p.add_argument("--dir", default="")
    p.add_argument("--case", default="")
    p.add_argument("--contract", type=float, default=0)
    p.add_argument("--new", action="store_true")
    p.set_defaults(func=cmd_change)

    p = sub.add_parser("report", help="產每週工程進度回報（可貼 LINE）")
    p.add_argument("--dir", required=True)
    p.add_argument("--case", default="")
    p.add_argument("--week", default="")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("scan", help="文案／提案紅線禁字稽核")
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_scan)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        ap.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
