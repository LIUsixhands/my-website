#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小運 · 上架文案包生成器
從 JSON 產出可直接複製貼上的 Markdown 文案包，並自動做「字數檢查 + 合規紅線掃描」。

用法：
    python3 gen_copy_pack.py input.json                # 印出 Markdown
    python3 gen_copy_pack.py input.json -o 文案包.md   # 存檔
    python3 gen_copy_pack.py --sample > input.json     # 產一份範例 JSON 當起手式
    python3 gen_copy_pack.py input.json --check-only   # 只跑字數與合規檢查

JSON 欄位見 --sample。缺欄位不會中斷，會在報告裡標成 ⚠️ 缺料。
"""

import argparse
import json
import unicodedata

# ---------------------------------------------------------------- 平台規格
# 註：平台規格會變動，重要投放前建議實測。
PLATFORM_LIMITS = {
    "youtube":   {"名稱": "YouTube Shorts", "標題": 100, "內文": 5000, "hashtag": 15},
    "instagram": {"名稱": "Instagram Reels", "標題": None, "內文": 2200, "hashtag": 30},
    "tiktok":    {"名稱": "TikTok",          "標題": None, "內文": 2200, "hashtag": None},
    "facebook":  {"名稱": "Facebook",        "標題": None, "內文": 63206, "hashtag": None},
    "threads":   {"名稱": "Threads",         "標題": None, "內文": 500,  "hashtag": None},
    "xiaohongshu": {"名稱": "小紅書",         "標題": 20,   "內文": 1000, "hashtag": None},
}

COVER_MAX_CHARS = 9  # 封面／首幀大字上限

# ------------------------------------------------------- 合規紅線關鍵字
# 依Sixhands Studio既有鐵律：不得宣稱療效、不得保證收益、不得個別化投資建議、避免絕對詞。
COMPLIANCE_RULES = [
    ("療效／醫療宣稱", [
        "療效", "治療", "治好", "根治", "痊癒", "抗癌", "防癌", "殺菌", "消炎",
        "降血壓", "降血糖", "改善體質", "排毒", "藥效", "醫治", "療程保證",
    ]),
    ("收益保證", [
        "保證賺", "穩賺", "穩賺不賠", "包賺", "月入", "被動收入保證",
        "零風險", "無風險", "躺著賺", "保證獲利",
        "收入翻倍", "業績翻倍", "獲利翻倍", "資產翻倍",
    ]),
    ("個別化投資建議", [
        "現在買進", "全押", "梭哈", "明牌", "必漲", "必跌", "報明牌",
    ]),
    ("誇大絕對詞（公平交易法風險）", [
        "最強", "最好", "第一名", "唯一", "百分百", "100%", "絕對", "永久有效",
    ]),
]


# ---------------------------------------------------------------- 工具
def visual_len(text: str) -> int:
    """全形字算 2、半形算 1 的視覺寬度（小紅書、封面大字用）。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def char_len(text: str) -> int:
    """平台實際計數用的字元數（codepoint）。"""
    return len(text)


def scan_compliance(texts):
    """回傳 [(類別, 命中詞, 出處), ...]"""
    hits = []
    for where, text in texts:
        if not text:
            continue
        for category, words in COMPLIANCE_RULES:
            for w in words:
                if w in text:
                    hits.append((category, w, where))
    return hits


def fmt_check(ok: bool) -> str:
    return "✅" if ok else "🔴"


# ---------------------------------------------------------------- 產出
def build_markdown(d: dict) -> str:
    g = d.get
    platforms = g("平台", []) or []
    titles = g("標題", []) or []
    cover = g("封面大字", "") or ""
    desc = g("描述", "") or ""
    tags = g("hashtag", {}) or {}
    pinned = g("置頂留言", "") or ""
    cta = g("CTA", "") or ""

    L = []
    A = L.append

    A(f"# 📦 上架文案包｜{g('主題', '（未填主題）')}")
    A("")
    A("> 出品：Sixhands Studio AI數字員工 · 內容部小運  ")
    A(f"> 日期：{g('日期', '（未填）')}｜平台：{'、'.join(platforms) or '（未填）'}"
      f"｜目的：{g('目的', '（未填）')}｜受眾：{g('受眾', '（未填）')}")
    A("")
    A("---")
    A("")

    # 1. 標題
    A("## 1. 標題 ×3（A/B/C 測試用）")
    A("")
    if not titles:
        A("⚠️ **缺料**：沒有提供標題。")
    else:
        A("| 版本 | 標題 | 字數 | 公式 | 抓的心理 |")
        A("|:---|:---|:---:|:---|:---|")
        for t in titles:
            text = t.get("文字", "")
            A(f"| **{t.get('版本','?')}** | {text} | {char_len(text)} |"
              f" {t.get('公式','—')} | {t.get('心理','—')} |")
        A("")
        if g("推薦"):
            A(f"**小運推薦先發**：{g('推薦')} — 理由：{g('推薦理由','（未填）')}")
    A("")

    # 2. 封面
    A("## 2. 封面／首幀大字")
    A("")
    A("```")
    A(cover if cover else "（未填）")
    A("```")
    if cover:
        n = len(cover.replace("\n", ""))
        A(f"- 字數：{n}（上限 {COVER_MAX_CHARS}）{'' if n <= COVER_MAX_CHARS else ' 🔴 超標，請刪字'}")
    A("- 繁體字體務必用 **Songti TC**（SC 缺繁體字會渲染成空白，產出後必抽幀目視）")
    A("")

    # 3. 描述
    A("## 3. 描述文案（可直接複製）")
    A("")
    A("```")
    A(desc if desc else "（未填）")
    A("```")
    A("")

    # 4. hashtag
    A("## 4. Hashtag 組合")
    A("")
    all_tags = []
    if tags:
        A("| 層級 | 標籤 |")
        A("|:---|:---|")
        for level in ("小", "中", "大", "系列"):
            items = tags.get(level, []) or []
            all_tags += items
            if items:
                A(f"| {level} | {' '.join(items)} |")
        A("")
        A(f"**純文字版**：`{' '.join(all_tags)}`")
    else:
        A("⚠️ **缺料**：沒有提供 hashtag。")
    A("")

    # 5-6
    A("## 5. 置頂留言")
    A("")
    A("```")
    A(pinned if pinned else "（未填）")
    A("```")
    A("")
    A("## 6. CTA（只給一個動作）")
    A("")
    A(f"> {cta if cta else '（未填）'}")
    A("")
    A(f"導流終點：{g('導流終點', '（未填）')}")
    A("")

    # 7. 平台改寫
    if g("多平台改寫"):
        A("## 7. 多平台改寫")
        A("")
        for plat, content in g("多平台改寫").items():
            name = PLATFORM_LIMITS.get(plat, {}).get("名稱", plat)
            A(f"### ▸ {name}")
            A("```")
            A(content)
            A("```")
            A("")

    # 8. 檢查報告
    A("## 8. ✅ 自動檢查報告")
    A("")
    A(build_report(d))

    return "\n".join(L)


def build_report(d: dict) -> str:
    L = []
    A = L.append
    titles = d.get("標題", []) or []
    cover = d.get("封面大字", "") or ""
    desc = d.get("描述", "") or ""
    platforms = d.get("平台", []) or []
    tags = d.get("hashtag", {}) or {}

    # 字數
    A("### 字數")
    A("")
    A("| 項目 | 內容 | 長度 | 上限 | 結果 |")
    A("|:---|:---|:---:|:---:|:---:|")

    plat_keys = [p for p in platforms if p in PLATFORM_LIMITS] or list(PLATFORM_LIMITS)
    for t in titles:
        text = t.get("文字", "")
        for pk in plat_keys:
            lim = PLATFORM_LIMITS[pk]["標題"]
            if lim is None:
                continue
            n = visual_len(text) if pk == "xiaohongshu" else char_len(text)
            shown = text if len(text) <= 24 else text[:24] + "…"
            A(f"| 標題 {t.get('版本','?')} @ {PLATFORM_LIMITS[pk]['名稱']} | {shown} "
              f"| {n} | {lim} | {fmt_check(n <= lim)} |")

    if cover:
        n = len(cover.replace("\n", ""))
        A(f"| 封面大字 | {cover.replace(chr(10), '／')} | {n} | {COVER_MAX_CHARS} | {fmt_check(n <= COVER_MAX_CHARS)} |")

    if desc:
        for pk in plat_keys:
            lim = PLATFORM_LIMITS[pk]["內文"]
            n = char_len(desc)
            A(f"| 描述 @ {PLATFORM_LIMITS[pk]['名稱']} | — | {n} | {lim} | {fmt_check(n <= lim)} |")

    n_tags = sum(len(v or []) for v in tags.values())
    if n_tags:
        for pk in plat_keys:
            lim = PLATFORM_LIMITS[pk]["hashtag"]
            if lim is None:
                continue
            A(f"| Hashtag 數 @ {PLATFORM_LIMITS[pk]['名稱']} | {n_tags} 個 | {n_tags} | {lim} | {fmt_check(n_tags <= lim)} |")
    A("")

    # 合規
    A("### 合規紅線掃描")
    A("")
    texts = [("標題", " ".join(t.get("文字", "") for t in titles)),
             ("封面大字", cover),
             ("描述", desc),
             ("置頂留言", d.get("置頂留言", "") or ""),
             ("CTA", d.get("CTA", "") or "")]
    hits = scan_compliance(texts)
    if hits:
        A("🔴 **有紅燈，交件前必須改**：")
        A("")
        A("| 類別 | 命中詞 | 出處 |")
        A("|:---|:---|:---|")
        for cat, w, where in hits:
            A(f"| {cat} | `{w}` | {where} |")
    else:
        A("✅ 關鍵字掃描未命中紅線詞。")
    A("")
    A("> ⚠️ 關鍵字掃描只擋得住明著寫的違規詞，**擋不住語意上的暗示**。")
    A("> 下列項目仍須人工確認：貨對板（標題承諾片中真的有）、"
      "YouTube AI 內容營利新規（非套版幻燈片／非情緒操弄／AI 人格不談健康金融法律政治）、"
      "對外交付物已掛「Sixhands Studio AI數字員工」品牌 + logo。")
    return "\n".join(L)


SAMPLE = {
    "主題": "為什麼你的短影音沒人看",
    "日期": "2026-08-11",
    "平台": ["youtube", "instagram", "tiktok"],
    "目的": "導流報名講座",
    "受眾": "40 歲想做自媒體但沒時間剪片的自營業者",
    "標題": [
        {"版本": "A｜懸念型", "文字": "3 個讓你影片沒人看的隱形錯誤",
         "公式": "A1 數字缺口", "心理": "害怕自己正在犯錯卻不知道"},
        {"版本": "B｜利益型", "文字": "60 秒學會讓完播率翻倍的剪法",
         "公式": "B1 時間承諾", "心理": "低成本高回報"},
        {"版本": "C｜衝突型", "文字": "「多發就會紅」是錯的",
         "公式": "C1 打臉常識", "心理": "挑釁既有認知，觸發辯論"},
    ],
    "推薦": "C",
    "推薦理由": "受眾多為已發過片但沒成效的人，打臉常識最能戳中",
    "封面大字": "多發\n不會紅",
    "描述": "你不是不夠努力，是每一支都在犯同一個錯。\n這 3 個錯誤，90% 的人自己看不出來。\n\n影片裡直接示範怎麼改。\n\n留言「剪法」我把檢查清單私訊你。",
    "hashtag": {
        "小": ["#自營業者行銷", "#四十歲創業", "#剪片新手"],
        "中": ["#短影音教學", "#自媒體經營"],
        "大": ["#行銷"],
        "系列": ["#Sixhands Studio"],
    },
    "置頂留言": "問一句：你覺得是「片子不好」還是「沒人看到」比較致命？我押後者，你呢？",
    "CTA": "留言「剪法」，我把檢查清單私訊給你。",
    "導流終點": "IG 私訊自動回覆 → 講座報名頁",
    "多平台改寫": {
        "tiktok": "多發就會紅？錯。90% 的人卡在這 3 個地方 👇\n#短影音教學 #自媒體經營 #剪片新手"
    },
}


def main():
    ap = argparse.ArgumentParser(description="小運 · 上架文案包生成器")
    ap.add_argument("input", nargs="?", help="輸入 JSON 檔路徑")
    ap.add_argument("-o", "--output", help="輸出 Markdown 檔路徑")
    ap.add_argument("--check-only", action="store_true", help="只印字數與合規檢查報告")
    ap.add_argument("--sample", action="store_true", help="輸出範例 JSON")
    args = ap.parse_args()

    if args.sample:
        print(json.dumps(SAMPLE, ensure_ascii=False, indent=2))
        return

    if not args.input:
        ap.error("需要輸入 JSON 檔（或用 --sample 產範例）")

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    out = build_report(data) if args.check_only else build_markdown(data)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out + "\n")
        print(f"✅ 已寫入 {args.output}")
    else:
        print(out)


if __name__ == "__main__":
    main()
