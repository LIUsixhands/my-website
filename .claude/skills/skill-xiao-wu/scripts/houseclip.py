#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
houseclip.py — AI 員工「小屋」的 591 房屋影片上架工具
零第三方依賴（標準庫 + ffprobe/ffmpeg）

指令：
    init                       建工作區與空白設定檔
    spec                       印出 591 影片規格實測表 / 顯示目前 config
    check  <影片檔>             規格檢查（依 config，未實測的項目會標「未實測」不硬判）
    fix    <影片檔>             依 config 轉檔到符合規格（裁掉開頭黑幀、音量正規化）
    pack   <物件.json>          產出上架文案包
    precheck <物件代號>         送出前確認清單（禁字＋必載欄位稽核）
    log add <物件代號> <網址>    記一筆上架
    log verify [代號 ok|fail]   列出待驗證 / 記錄驗證結果
    report                     產出當月上架月報

設計原則：不猜、不編。config 沒有的規格一律標「未實測」，不用網路傳聞的數字硬判。
"""
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

WORK = os.path.expanduser("~/AI員工_小屋")
CONFIG = os.path.join(WORK, "config", "591_spec.json")
OBJECTS = os.path.join(WORK, "objects")
VIDEOS = os.path.join(WORK, "videos")
PACKS = os.path.join(WORK, "packs")
DATA = os.path.join(WORK, "data")
LOGCSV = os.path.join(DATA, "上架紀錄.csv")

EMPTY_SPEC = {
    "measured_at": None,
    "mode": None,
    "formats": [],
    "max_mb": None,
    "max_seconds": None,
    "min_seconds": None,
    "resolutions": [],
    "aspect": None,
    "max_videos_per_object": None,
    "publish_delay_note": "",
    "evidence": {},
}

BANNED = {
    "保證與絕對": ["保證", "絕對", "穩賺", "零風險", "無風險", "包漲", "必漲",
                   "百分百", "100%", "投報保證", "鐵定"],
    "最高級與排他": ["最便宜", "最低價", "全台最", "唯一", "第一名", "僅此一戶"],
    "預測與招攬投資": ["增值潛力", "翻倍", "暴漲", "穩定收益", "輕鬆月收", "以租養貸",
                       "投資報酬率"],
    "需證據才可寫": ["急售", "賠售", "法拍價", "可貸九成", "可改套房", "無漏水"],
    "居住歧視": ["限男", "限女", "不租外籍", "限本國人"],
}

REQUIRED_OBJECT_FIELDS = ["code", "agency", "agent", "video"]


# ---------- 共用 ----------
def die(msg, code=1):
    print(f"❌ {msg}")
    sys.exit(code)


def need(binname):
    if shutil.which(binname) is None:
        die(f"找不到 {binname}，請先安裝 ffmpeg（brew install ffmpeg）")


def load_spec():
    if not os.path.exists(CONFIG):
        return dict(EMPTY_SPEC), False
    with open(CONFIG, encoding="utf-8") as f:
        spec = json.load(f)
    measured = bool(spec.get("measured_at"))
    return spec, measured


def ffprobe(path):
    need("ffprobe")
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True)
    if out.returncode != 0:
        die(f"ffprobe 讀不到這個檔：{path}\n{out.stderr.strip()}")
    return json.loads(out.stdout)


def first_frame_luma(path):
    """回傳首幀平均亮度 0-255，抓不到回 None。"""
    need("ffmpeg")
    out = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", path, "-vf",
         "select=eq(n\\,0),signalstats,metadata=print", "-frames:v", "1",
         "-f", "null", "-"],
        capture_output=True, text=True)
    m = re.search(r"lavfi\.signalstats\.YAVG=([\d.]+)", out.stderr)
    return float(m.group(1)) if m else None


def mean_volume(path):
    need("ffmpeg")
    out = subprocess.run(
        ["ffmpeg", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", out.stderr)
    return float(m.group(1)) if m else None


# ---------- init / spec ----------
def cmd_init():
    for d in [os.path.join(WORK, "config"), OBJECTS, VIDEOS, PACKS, DATA]:
        os.makedirs(d, exist_ok=True)
    if not os.path.exists(CONFIG):
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(EMPTY_SPEC, f, ensure_ascii=False, indent=2)
    if not os.path.exists(LOGCSV):
        with open(LOGCSV, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(
                ["日期", "物件代號", "前台網址", "影片檔", "狀態", "驗證日", "備註"])
    print(f"✅ 工作區就緒：{WORK}")
    print(f"   設定檔（出廠空白，請先實測）：{CONFIG}")
    print("   下一步：python3 houseclip.py spec")


def cmd_spec():
    spec, measured = load_spec()
    if not os.path.exists(CONFIG):
        print("⚠️  還沒 init，先跑：python3 houseclip.py init")
        return
    print(f"設定檔：{CONFIG}\n")
    if measured:
        print(f"✅ 已實測（{spec['measured_at']}）目前規格：")
        print(json.dumps(spec, ensure_ascii=False, indent=2))
        print("\n建議每季複測一次，或一退件就複測。")
        return
    print("🚨 尚未實測。591 沒有公開的影片規格文件，我不編數字。")
    print("   請照 references/591影片規格實測法.md 實測七題，把結果填進上面這個檔。\n")
    print("實測七題：")
    for i, q in enumerate([
        "影片是上傳檔案還是貼 YouTube 連結？        → mode",
        "接受哪些檔案格式？                          → formats",
        "檔案大小上限幾 MB？                         → max_mb",
        "長度上下限幾秒？                            → max_seconds / min_seconds",
        "解析度或長寬比有沒有限制？直式吃不吃？      → resolutions / aspect",
        "一個物件能掛幾支影片？                      → max_videos_per_object",
        "上傳後多久前台看得到？要不要審核？          → publish_delay_note",
    ], 1):
        print(f"  {i}. {q}")
    print("\n🔎 被擋時跳出來的提示原文，照抄進 evidence 欄，將來有據可查。")


# ---------- check / fix ----------
def cmd_check(path):
    if not os.path.exists(path):
        die(f"檔案不存在：{path}")
    spec, measured = load_spec()
    info = ffprobe(path)
    fmt = info.get("format", {})
    vs = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    aus = [s for s in info["streams"] if s["codec_type"] == "audio"]
    if vs is None:
        die("這個檔沒有視訊軌，不是影片")

    dur = float(fmt.get("duration", 0))
    size_mb = int(fmt.get("size", 0)) / 1024 / 1024
    w, h = int(vs["width"]), int(vs["height"])
    ext = os.path.splitext(path)[1].lstrip(".").lower()

    rows, hard_fail = [], False

    def judge(item, value, ok, note=""):
        nonlocal hard_fail
        if ok is None:
            rows.append((item, value, "未實測", note))
        elif ok:
            rows.append((item, value, "通過", note))
        else:
            rows.append((item, value, "不符", note))
            hard_fail = True

    judge("容器格式", ext,
          (ext in [e.lower() for e in spec["formats"]]) if spec["formats"] else None,
          f"config 允許：{spec['formats'] or '（未實測）'}")
    judge("影片編碼", vs.get("codec_name", "?"), None, "591 未實測，h264 最保險")
    judge("長度", f"{dur:.1f} 秒",
          (dur <= spec["max_seconds"]) if spec["max_seconds"] else None,
          f"上限：{spec['max_seconds'] or '（未實測）'}")
    judge("檔案大小", f"{size_mb:.1f} MB",
          (size_mb <= spec["max_mb"]) if spec["max_mb"] else None,
          f"上限：{spec['max_mb'] or '（未實測）'}")
    judge("解析度", f"{w}×{h}", None, f"config：{spec['resolutions'] or '（未實測）'}")

    orient = "直式" if h > w else ("橫式" if w > h else "正方")
    judge("長寬比", f"{orient} {w}:{h}",
          (orient == spec["aspect"]) if spec["aspect"] else None,
          f"config 要求：{spec['aspect'] or '（未實測）'}")

    judge("音軌", "有" if aus else "無", bool(aus), "沒有音軌的帶看影片觀感差")

    luma = first_frame_luma(path)
    if luma is not None:
        # 限制範圍(TV range)的純黑 YAVG 正好是 16，所以門檻要拉到 20 以上
        judge("首幀亮度", f"{luma:.1f}/255", luma > 20,
              "20 以下等於開頭是黑畫面（純黑 = 16），封面會全黑")
    if aus:
        mv = mean_volume(path)
        if mv is not None:
            judge("平均音量", f"{mv:.1f} dB", mv >= -30,
                  "低於 -30dB 手機幾乎聽不到")

    print(f"\n📼 {os.path.basename(path)}")
    if not measured:
        print("🚨 config 尚未實測 → 平台限制類項目標「未實測」，只做得了通用品質檢查。")
    print(f"{'項目':<10}{'實際值':<18}{'判定':<8}說明")
    print("-" * 78)
    for item, val, verdict, note in rows:
        mark = {"通過": "✅", "不符": "❌", "未實測": "⚪️"}[verdict]
        print(f"{item:<10}{str(val):<18}{mark}{verdict:<6}{note}")
    print("-" * 78)
    if hard_fail:
        print("結論：❌ 有項目不符，先跑 fix 轉檔：")
        print(f"  python3 houseclip.py fix {path}")
        sys.exit(2)
    print("結論：✅ 通過（未實測項目不代表平台會收，第一次上架仍要人工盯）")


def cmd_fix(path):
    if not os.path.exists(path):
        die(f"檔案不存在：{path}")
    need("ffmpeg")
    spec, _ = load_spec()
    os.makedirs(VIDEOS, exist_ok=True)
    base = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(VIDEOS, f"{base}_591.mp4")

    # 抓開頭黑幀
    bd = subprocess.run(
        ["ffmpeg", "-i", path, "-vf", "blackdetect=d=0.1:pix_th=0.10",
         "-an", "-f", "null", "-"], capture_output=True, text=True)
    ss = 0.0
    for m in re.finditer(r"black_start:([\d.]+) black_end:([\d.]+)", bd.stderr):
        if float(m.group(1)) < 0.05:
            ss = float(m.group(2))
            break

    cmd = ["ffmpeg", "-y"]
    if ss > 0:
        cmd += ["-ss", f"{ss:.2f}"]
    cmd += ["-i", path]
    if spec.get("max_seconds"):
        cmd += ["-t", str(spec["max_seconds"])]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "21",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a", "aac", "-b:a", "192k", out]
    print(f"轉檔中…（裁掉開頭黑幀 {ss:.2f}s）")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        die("ffmpeg 轉檔失敗：\n" + r.stderr[-1200:])
    mb = os.path.getsize(out) / 1024 / 1024
    print(f"✅ 產出：{out}（{mb:.1f} MB）")
    if spec.get("max_mb") and mb > spec["max_mb"]:
        print(f"⚠️  仍超過 config 的 {spec['max_mb']} MB，請調高 crf 或縮短片長後重跑")
    print(f"複驗：python3 houseclip.py check {out}")


# ---------- pack ----------
def cmd_pack(objpath):
    if not os.path.exists(objpath):
        die(f"物件檔不存在：{objpath}")
    with open(objpath, encoding="utf-8") as f:
        o = json.load(f)
    missing = [k for k in REQUIRED_OBJECT_FIELDS if not o.get(k)]
    if missing:
        die("物件檔缺欄位，補齊再跑：" + "、".join(missing))
    if not o.get("owner_consent"):
        die("owner_consent 不是 true — 屋主書面同意刊登影片才可上架（合規紅線第三章）")

    os.makedirs(PACKS, exist_ok=True)
    title = f"【{o.get('title_area','')} {o.get('highlight','')}】" \
            f"{o.get('ping','')}坪｜一支影片看完"
    walk = o.get("walk") or []
    lines = [
        f"# 上架文案包｜{o['code']}",
        "",
        f"產出時間：{datetime.now():%Y-%m-%d %H:%M}",
        "",
        "## 標題",
        title,
        "",
        "## 說明",
        "這支影片從大門走到主臥，一鏡看完格局動線。",
        f"{o.get('ping','—')} 坪，{o.get('layout','—')}，"
        f"樓層 {o.get('floor','—')}，屋齡 {o.get('age','—')} 年。",
    ]
    if walk:
        lines.append("周邊：" + "、".join(walk) + "（步行距離為實測）。")
    lines += [
        "想看細節或約現場，直接私訊我。",
        "",
        "---",
        f"經紀業：{o['agency']}",
        f"經紀人：{o['agent']}" +
        (f"（不動產經紀人證書字號：{o['agent_license']}）"
         if o.get("agent_license") else "（⚠️ 證書字號待補）"),
        "本廣告內容與事實相符，物件資料以土地建物謄本及不動產說明書為準。",
        "",
        "## 標籤",
        "、".join(o.get("tags") or ["（待填：區域／格局／樓層／車位／電梯／屋齡帶）"]),
        "",
        "## 影片檔",
        o["video"],
    ]
    outp = os.path.join(PACKS, f"{o['code']}.md")
    with open(outp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"✅ 文案包：{outp}")
    print(f"下一步：python3 houseclip.py precheck {o['code']}")


# ---------- precheck ----------
def scan_banned(text):
    hits = []
    for cat, words in BANNED.items():
        for w in words:
            if w in text:
                hits.append((cat, w))
    return hits


def cmd_precheck(code):
    packp = os.path.join(PACKS, f"{code}.md")
    if not os.path.exists(packp):
        die(f"找不到文案包：{packp}（先跑 pack）")
    text = open(packp, encoding="utf-8").read()
    hits = scan_banned(text)

    print(f"\n📋 {code} 送出前確認清單")
    print("=" * 60)
    print("\n【自動稽核】")
    if hits:
        print(f"❌ 禁字 {len(hits)} 處：")
        for cat, w in hits:
            print(f"   - 「{w}」（{cat}）")
        print("   → 有證據支持的（急售、無漏水等）請房仲確認後再放行")
    else:
        print("✅ 禁字掃描：乾淨")
    for key, label in [("經紀業：", "經紀業名稱"), ("經紀人：", "經紀人姓名"),
                       ("與事實相符", "廣告與事實相符聲明")]:
        print(("✅ " if key in text else "❌ 缺少 ") + f"必載：{label}")
    if "待補" in text:
        print("⚠️  文案包內仍有「待補」字樣，補完再送")

    print("\n【人工逐項確認，全部打勾才送出】")
    for i, q in enumerate([
        "影片畫面確實是這個物件，不是別間房子",
        "坪數、格局、樓層、價格與謄本／委託書一致",
        "影片沒有拍到門牌、車牌、鄰居人臉、屋主私人物品",
        "背景音樂是自製或有授權",
        "屋主的書面同意刊登影片已取得",
        "591 後台頁面上顯示的地址與售價，與交辦單一致",
        "這個 591 帳號有權刊登這筆物件（公司政策已確認）",
    ], 1):
        print(f"  [ ] {i}. {q}")
    print("\n" + "=" * 60)
    print("🚨 以上確認完畢後，**由房仲本人按送出**。小屋不代按。")
    print(f"送出後：python3 houseclip.py log add {code} <前台網址>")
    if hits:
        sys.exit(2)


# ---------- log / report ----------
def read_log():
    if not os.path.exists(LOGCSV):
        return []
    with open(LOGCSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_log(rows):
    with open(LOGCSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["日期", "物件代號", "前台網址",
                                          "影片檔", "狀態", "驗證日", "備註"])
        w.writeheader()
        w.writerows(rows)


def cmd_log(args):
    if not args:
        die("用法：log add <代號> <網址> ｜ log verify [代號 ok|fail]")
    sub = args[0]
    rows = read_log()
    if sub == "add":
        if len(args) < 3:
            die("用法：log add <物件代號> <前台網址>")
        code, url = args[1], args[2]
        packp = os.path.join(PACKS, f"{code}.md")
        video = ""
        if os.path.exists(packp):
            m = re.search(r"## 影片檔\n(.+)", open(packp, encoding="utf-8").read())
            video = m.group(1).strip() if m else ""
        rows.append({"日期": f"{datetime.now():%Y-%m-%d}", "物件代號": code,
                     "前台網址": url, "影片檔": video, "狀態": "待驗證",
                     "驗證日": "", "備註": ""})
        write_log(rows)
        print(f"✅ 已記錄 {code}")
        print("🔎 30 分鐘後用**未登入的無痕視窗**開前台網址驗證，隔天再驗一次：")
        print("   python3 houseclip.py log verify")
    elif sub == "verify":
        if len(args) >= 3:
            code, res = args[1], args[2].lower()
            if res not in ("ok", "fail"):
                die("結果只能是 ok 或 fail")
            hit = False
            for r in rows:
                if r["物件代號"] == code and r["狀態"] == "待驗證":
                    r["狀態"] = "已上線" if res == "ok" else "驗證失敗"
                    r["驗證日"] = f"{datetime.now():%Y-%m-%d}"
                    hit = True
            if not hit:
                die(f"找不到待驗證的 {code}")
            write_log(rows)
            print(f"✅ {code} → {'已上線' if res=='ok' else '驗證失敗'}")
            return
        pend = [r for r in rows if r["狀態"] == "待驗證"]
        if not pend:
            print("✅ 沒有待驗證的項目")
            return
        print(f"待驗證 {len(pend)} 筆 — 用**未登入的無痕視窗**逐一開啟：\n")
        for r in pend:
            print(f"  {r['物件代號']}  {r['前台網址']}")
        print("\n確認影片有出現且能播，然後：")
        print("  python3 houseclip.py log verify <代號> ok|fail")
    else:
        die(f"不認得的 log 子指令：{sub}")


def cmd_report():
    rows = read_log()
    ym = f"{datetime.now():%Y-%m}"
    cur = [r for r in rows if r["日期"].startswith(ym)]
    print(f"\n📊 小屋 {ym} 上架月報")
    print("=" * 50)
    print(f"本月上架：{len(cur)} 支")
    for st in ["已上線", "待驗證", "驗證失敗"]:
        n = len([r for r in cur if r["狀態"] == st])
        if n:
            print(f"  {st}：{n} 支")
    fails = [r for r in cur if r["狀態"] == "驗證失敗"]
    if fails:
        print("\n❌ 驗證失敗，需要處理：")
        for r in fails:
            print(f"  {r['物件代號']}  {r['備註'] or '（未填原因，請補）'}")
    print(f"\n累計總上架：{len(rows)} 支")
    print("=" * 50)
    print("月報是續約憑據 — 交給房仲時附上「這個月替你省下的時間 = 支數 × 你原本一支的耗時」")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    c, rest = sys.argv[1], sys.argv[2:]
    if c == "init":
        cmd_init()
    elif c == "spec":
        cmd_spec()
    elif c == "check":
        cmd_check(rest[0]) if rest else die("用法：check <影片檔>")
    elif c == "fix":
        cmd_fix(rest[0]) if rest else die("用法：fix <影片檔>")
    elif c == "pack":
        cmd_pack(rest[0]) if rest else die("用法：pack <物件.json>")
    elif c == "precheck":
        cmd_precheck(rest[0]) if rest else die("用法：precheck <物件代號>")
    elif c == "log":
        cmd_log(rest)
    elif c == "report":
        cmd_report()
    else:
        print(__doc__)
        die(f"不認得的指令：{c}")


if __name__ == "__main__":
    main()
