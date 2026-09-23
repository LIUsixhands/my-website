#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小群 · FB／IG 社群經營工具
標準庫 + Pillow，零第三方相依（Pillow 僅 card 指令需要）。

安全設計（不可移除）：
  * publish / schedule 預設 dry-run，必須明確加 --confirm 才會真的打 Meta API。
  * Token 只從 config.json 讀，不從參數列傳（避免留在 shell history）。
  * config.json 權限 600。
"""
import argparse
import csv
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta

WORKROOT = os.path.expanduser("~/AI員工_小群")
DEFAULT_GRAPH_VERSION = "v21.0"   # ⚠️ 導入時先確認 Meta 目前支援的版本，改 config 的 graph_version
GRAPH = "https://graph.facebook.com"
GRAPH_VIDEO = "https://graph-video.facebook.com"


# ────────────────────────────── 共用 ──────────────────────────────
def die(msg, code=1):
    print("❌ " + msg)
    sys.exit(code)


def ok(msg):
    print("✅ " + msg)


def warn(msg):
    print("⚠️  " + msg)


def client_dir(code):
    return os.path.join(WORKROOT, code)


def load_config(code):
    p = os.path.join(client_dir(code), "config.json")
    if not os.path.exists(p):
        die("找不到 %s，先跑：python3 socialpost.py init %s" % (p, code))
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_config(code, cfg):
    p = os.path.join(client_dir(code), "config.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.chmod(p, 0o600)


def graph_url(cfg, path):
    ver = cfg.get("graph_version") or DEFAULT_GRAPH_VERSION
    return "%s/%s/%s" % (GRAPH, ver, path.lstrip("/"))


def need_token(cfg):
    tok = (cfg.get("page_access_token") or "").strip()
    if not tok:
        die("config.json 的 page_access_token 是空的。\n"
            "   Token 由客戶／學員自己在 Meta 開發者後台產生後貼進去，小群不代為申請。\n"
            "   步驟見 references/Meta_API_設定SOP.md")
    return tok


def api_get(cfg, path, params=None):
    params = dict(params or {})
    params["access_token"] = need_token(cfg)
    url = graph_url(cfg, path) + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise SystemExit("❌ Graph API GET %s 失敗（HTTP %s）：\n%s" % (path, e.code, body))


def api_post(cfg, path, fields):
    fields = dict(fields)
    fields["access_token"] = need_token(cfg)
    url = graph_url(cfg, path)
    data = urllib.parse.urlencode(fields).encode("utf-8")
    try:
        with urllib.request.urlopen(url, data=data, timeout=180) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise SystemExit("❌ Graph API POST %s 失敗（HTTP %s）：\n%s" % (path, e.code, body))


def api_post_file(cfg, path, fields, file_field, file_path, base=None):
    """multipart 上傳（FB 照片／影片走本機檔）"""
    fields = dict(fields)
    fields["access_token"] = need_token(cfg)
    boundary = "----xiaoqun%s" % uuid.uuid4().hex
    ctype = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    with open(file_path, "rb") as f:
        blob = f.read()
    lines = []
    for k, v in fields.items():
        lines.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                      % (boundary, k, v)).encode("utf-8"))
    lines.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                  "Content-Type: %s\r\n\r\n"
                  % (boundary, file_field, os.path.basename(file_path), ctype)).encode("utf-8"))
    lines.append(blob)
    lines.append(("\r\n--%s--\r\n" % boundary).encode("utf-8"))
    body = b"".join(lines)
    ver = cfg.get("graph_version") or DEFAULT_GRAPH_VERSION
    url = "%s/%s/%s" % (base or GRAPH, ver, path.lstrip("/"))
    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", "multipart/form-data; boundary=%s" % boundary)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise SystemExit("❌ Graph API 上傳 %s 失敗（HTTP %s）：\n%s" % (path, e.code, detail))


# ────────────────────────────── init ──────────────────────────────
CONFIG_TEMPLATE = {
    "client_code": "",
    "brand_name": "",
    "industry": "",
    "graph_version": DEFAULT_GRAPH_VERSION,
    "page_id": "",
    "page_access_token": "",
    "ig_user_id": "",
    "public_asset_base": "",
    "timezone": "Asia/Taipei",
    "post_times": {"fb": "12:30", "ig": "20:00"},
    "content_mix": {"日常人味": 30, "專業教育": 30, "顧客見證": 20, "促銷活動": 20},
    "banned_words": [],
    "approver": "",
    "notes": "Token 由客戶自行產生後貼上；本檔權限 600，不可進 git、不可放進交付文件。",
}


def cmd_init(args):
    d = client_dir(args.code)
    for sub in ("素材", "貼文", "報表", "封存"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    cfg_path = os.path.join(d, "config.json")
    if os.path.exists(cfg_path):
        warn("config.json 已存在，保留原檔不覆蓋：%s" % cfg_path)
    else:
        cfg = dict(CONFIG_TEMPLATE)
        cfg["client_code"] = args.code
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.chmod(cfg_path, 0o600)
    log = os.path.join(d, "發佈紀錄.csv")
    if not os.path.exists(log):
        with open(log, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(["日期", "平台", "類型", "主題", "貼文ID", "網址", "備註"])
    ok("工作區已建立：%s" % d)
    print("   下一步：把粉專 ID／IG 商業帳號 ID／Token 填進 config.json，再跑 auth 驗證。")
    print("   設定步驟：references/Meta_API_設定SOP.md")


# ────────────────────────────── auth ──────────────────────────────
def cmd_auth(args):
    cfg = load_config(args.code)
    me = api_get(cfg, "me", {"fields": "id,name"})
    ok("Token 有效，身分：%s（%s）" % (me.get("name", "?"), me.get("id", "?")))
    try:
        accts = api_get(cfg, "me/accounts", {"fields": "id,name,instagram_business_account"})
        rows = accts.get("data", [])
        if rows:
            print("\n可管理的粉專：")
            for r in rows:
                iga = (r.get("instagram_business_account") or {}).get("id", "—")
                print("  · %s  page_id=%s  ig_user_id=%s" % (r.get("name"), r.get("id"), iga))
            print("\n把要用的那一組填進 config.json 的 page_id / ig_user_id。")
        else:
            warn("這個 Token 沒有列出任何粉專。若用的是粉專 Token 屬正常，請直接確認 config 的 page_id。")
    except SystemExit as e:
        warn("列粉專失敗（用粉專 Token 時屬正常）：%s" % e)
    if cfg.get("page_id"):
        p = api_get(cfg, cfg["page_id"], {"fields": "id,name,fan_count"})
        ok("粉專：%s，粉絲 %s" % (p.get("name"), p.get("fan_count", "?")))
    if cfg.get("ig_user_id"):
        g = api_get(cfg, cfg["ig_user_id"], {"fields": "id,username,followers_count"})
        ok("IG：@%s，追蹤 %s" % (g.get("username"), g.get("followers_count", "?")))
    if not cfg.get("public_asset_base"):
        warn("public_asset_base 沒填 → IG 無法發圖影片（IG API 只吃公開網址）。")


# ────────────────────────────── plan ──────────────────────────────
def cmd_plan(args):
    cfg = load_config(args.code)
    y, m = [int(x) for x in args.month.split("-")]
    start = datetime(y, m, 1)
    nxt = datetime(y + (m == 12), 1 if m == 12 else m + 1, 1)
    days = (nxt - start).days
    mix = cfg.get("content_mix") or CONFIG_TEMPLATE["content_mix"]
    per_week = args.per_week
    types = []
    for t, pct in mix.items():
        types += [t] * max(1, round(pct / 10))
    out = os.path.join(client_dir(args.code), "報表", "內容日曆_%s.csv" % args.month)
    rows, i = [], 0
    for d in range(days):
        day = start + timedelta(days=d)
        if day.weekday() not in _weekdays_for(per_week):
            continue
        t = types[i % len(types)]
        i += 1
        rows.append([day.strftime("%Y-%m-%d"), day.strftime("%a"), "FB+IG", t,
                     "（待填主題）", "（待填素材需求）", "未開始"])
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["日期", "星期", "平台", "類型", "主題", "素材需求", "狀態"])
        w.writerows(rows)
    ok("內容日曆已產出：%s（共 %d 則）" % (out, len(rows)))
    print("   主題欄位刻意留空 —— 選題要看客戶的真實素材與檔期，不由腳本亂編。")
    print("   選題彈藥見 references/內容公式庫.md")


def _weekdays_for(n):
    table = {2: [1, 4], 3: [1, 3, 5], 4: [0, 2, 4, 6], 5: [0, 1, 2, 3, 4], 7: [0, 1, 2, 3, 4, 5, 6]}
    return table.get(n, [1, 3, 5])


# ────────────────────────────── check（合規稽核）──────────────────────────────
RED = {
    "絕對化用語（公平交易法§21 廣告不實）": [
        "最好", "最佳", "最便宜", "最有效", "最強", "第一品牌", "業界第一", "全台第一",
        "唯一", "頂級", "極致", "完美", "百分百", "100%有效", "絕對", "永久有效", "史上最",
    ],
    "療效／醫療宣稱（食安法§28、化粧品法§10、藥事法§66-69）": [
        "療效", "治療", "根治", "痊癒", "醫療級", "消炎", "殺菌", "抗癌", "排毒", "解毒",
        "降血糖", "降血壓", "增強免疫", "提升免疫力", "修復細胞", "活化細胞", "改善過敏",
    ],
    "收益／投資保證（銀行法§29-1、投信投顧法）": [
        "保證獲利", "保證賺", "穩賺不賠", "保本保息", "保證報酬", "保證收益",
        "躺著賺", "無風險", "零風險", "包賺", "保證回本",
    ],
    "傳銷用語（多層次傳銷管理法）": ["下線", "分潤", "組織獎金", "團隊分紅", "拉人頭"],
    "做不到的保證": ["保證有效", "保證錄取", "保證成交", "保證瘦", "保證不復胖", "永不漏水"],
    "Meta 廣告政策：個人特徵斷言（第一人稱指認對方屬性）": [
        "你是不是很胖", "你一定有病", "像你這種負債", "你有憂鬱症嗎", "你也離婚了嗎",
    ],
}
YELLOW = {
    "誘導互動（會被壓觸及）": ["留言抽獎", "按讚抽獎", "分享抽獎", "tag 三個朋友", "標記三位好友", "限時免費領"],
    "體重數字與前後對比（Meta 健康與美容政策高風險）": ["瘦下", "公斤", "before", "after", "前後對比"],
    "價格與時效寫死（改一次就要重做素材）": ["本週限定", "只到今天", "最後一天", "倒數"],
}
INDUSTRY = {
    "醫美": ["微整", "電波", "音波", "肉毒", "玻尿酸", "術後", "無恢復期", "免動刀"],
    "保健": ["保健功效", "改善體質", "調整體質", "增強體力", "抗氧化功效"],
    "餐飲": ["無添加", "零防腐劑", "純天然", "有機"],
    "房產": ["保證增值", "穩賺", "投資報酬率", "包租", "保證出租"],
    "金融": ["保證核貸", "免聯徵", "低利保證", "月配息保證"],
    "補教": ["保證上榜", "保證考取", "免費試聽保證"],
    "美業": ["永久除毛", "根除", "無痛保證"],
}


def cmd_check(args):
    text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
    red, yellow = [], []
    for cat, words in RED.items():
        for w in words:
            if w in text:
                red.append((cat, w))
    for cat, words in YELLOW.items():
        for w in words:
            if w in text:
                yellow.append((cat, w))
    if args.industry:
        for w in INDUSTRY.get(args.industry, []):
            if w in text:
                yellow.append(("產業特別注意：%s（需有依據或改寫）" % args.industry, w))
    tags = re.findall(r"#\S+", text)
    body = len(re.sub(r"\s", "", text))
    print("── 小群 · 合規稽核 ──")
    print("字數（不含空白）：%d　hashtag：%d 個" % (body, len(tags)))
    if len(tags) > 15:
        yellow.append(("hashtag 過多（IG 建議 8–15）", "共 %d 個" % len(tags)))
    if red:
        print("\n🔴 紅燈（必改，改完才可發）")
        for cat, w in red:
            print("   · [%s] %s" % (cat, w))
    if yellow:
        print("\n🟡 黃燈（要有依據或請客戶確認）")
        for cat, w in yellow:
            print("   · [%s] %s" % (cat, w))
    if not red and not yellow:
        ok("全綠，可以進下一關（預覽 → 客戶確認 → 發佈）")
    print("\n⚠️  稽核只擋已知字詞，擋不掉「內容本身不實」。事實與授權仍要人工確認。")
    sys.exit(1 if red else 0)


# ────────────────────────────── card（圖卡）──────────────────────────────
RATIOS = {"1:1": (1080, 1080), "4:5": (1080, 1350), "9:16": (1080, 1920), "16:9": (1920, 1080)}


def _font(size, heavy=True):
    import glob
    from PIL import ImageFont
    cands = glob.glob("/System/Library/AssetsV2/com_apple_MobileAsset_Font7/*/AssetData/PingFang.ttc") + [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
    ]
    want = "Semibold" if heavy else "Regular"
    for path in cands:
        for idx in range(12):
            try:
                f = ImageFont.truetype(path, size, index=idx)
            except Exception:
                break
            fam, sty = f.getname()
            if "PingFang TC" in fam and want in sty:
                return f
    for path in cands:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    die("找不到可用的中文字型（需要 PingFang TC 或 STHeiti）")


def cmd_card(args):
    from PIL import Image, ImageDraw
    W, H = RATIOS.get(args.ratio) or die("--ratio 只支援 %s" % "／".join(RATIOS))
    parts = [p.strip() for p in args.text.split("|") if p.strip()]
    if not parts:
        die("--text 不可為空。格式：\"主標|副標|補充\"")
    bg, fg, accent = args.bg, args.fg, args.accent
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    margin = int(W * 0.09)
    sizes = [int(W * 0.115), int(W * 0.058), int(W * 0.042)]
    maxw = W - margin * 2

    # 先排版算總高，再垂直置中（偏上 46%），避免長短文案都擠在頂端、下半大片留白
    blocks = []
    total = 0
    for i, line in enumerate(parts[:3]):
        size = sizes[min(i, 2)]
        f = _font(size, heavy=(i == 0))
        segs = _wrap(d, line, f, maxw)
        h = len(segs) * int(size * 1.35) + int(size * 0.45)
        blocks.append((segs, f, size, fg if i == 0 else accent if i == 1 else fg))
        total += h
    bar_h = max(10, int(H * 0.008))
    y = max(int(H * 0.12), int(H * 0.46) - total // 2)
    d.rectangle([margin, y - int(H * 0.055), margin + int(W * 0.13), y - int(H * 0.055) + bar_h], fill=accent)
    for segs, f, size, color in blocks:
        for seg in segs:
            d.text((margin, y), seg, font=f, fill=color)
            y += int(size * 1.35)
        y += int(size * 0.45)
    if args.logo and os.path.exists(args.logo):
        lg = Image.open(args.logo).convert("RGBA")
        lw = int(W * 0.16)
        lg = lg.resize((lw, int(lg.height * lw / lg.width)))
        img.paste(lg, (W - margin - lw, H - margin - lg.height), lg)
    out = args.out or os.path.join(os.getcwd(), "圖卡_%s.png" % args.ratio.replace(":", "x"))
    img.save(out, quality=95)
    ok("圖卡已產出：%s（%dx%d）" % (out, W, H))
    print("   🚨 交件前一定要打開來看過：字有沒有被切、有沒有壓到安全區、有沒有豆腐格。")


def _wrap(draw, text, font, maxw):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) > maxw and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


# ────────────────────────────── preview / publish / schedule ──────────────────────────────
def load_post(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _describe(cfg, post):
    print("── 送出內容預覽 ──")
    print("品牌：%s（%s）" % (cfg.get("brand_name") or "?", cfg.get("client_code")))
    print("平台：%s" % "、".join(post.get("platforms", [])))
    print("類型：%s　主題：%s" % (post.get("type", "?"), post.get("topic", "?")))
    for plat in post.get("platforms", []):
        blk = post.get(plat, {})
        print("\n【%s】" % plat.upper())
        body = blk.get("message") or blk.get("caption") or ""
        print(body if body else "（無文字）")
        for k in ("link", "image", "image_url", "video", "video_url", "media_type"):
            if blk.get(k):
                print("  %s: %s" % (k, blk[k]))
    print("\n── 送出前檢查清單（人工逐項確認）──")
    for item in ["文案跑過 check 且無紅燈", "圖／影片親眼看過，無他牌 logo、無路人臉、無個資",
                 "素材與音樂已取得授權", "沒有把日期燒死在圖上", "連結點得開、指向正確頁面",
                 "%s 已看過並同意發佈" % (cfg.get("approver") or "客戶方確認人（config 未填）")]:
        print("  [ ] %s" % item)


def cmd_preview(args):
    _describe(load_config(args.code), load_post(args.post))


def _fb_publish(cfg, blk, scheduled_ts=None):
    page = cfg.get("page_id") or die("config 的 page_id 沒填")
    msg = blk.get("message", "")
    if blk.get("video"):
        fields = {"description": msg}
        if scheduled_ts:
            fields.update({"published": "false", "scheduled_publish_time": str(scheduled_ts)})
        r = api_post_file(cfg, "%s/videos" % page, fields, "source", blk["video"], base=GRAPH_VIDEO)
    elif blk.get("image"):
        fields = {"caption": msg}
        if scheduled_ts:
            fields.update({"published": "false", "scheduled_publish_time": str(scheduled_ts)})
        r = api_post_file(cfg, "%s/photos" % page, fields, "source", blk["image"])
    else:
        fields = {"message": msg}
        if blk.get("link"):
            fields["link"] = blk["link"]
        if scheduled_ts:
            fields.update({"published": "false", "scheduled_publish_time": str(scheduled_ts)})
        r = api_post(cfg, "%s/feed" % page, fields)
    return r


def _ig_publish(cfg, blk):
    ig = cfg.get("ig_user_id") or die("config 的 ig_user_id 沒填")
    mtype = (blk.get("media_type") or "IMAGE").upper()
    fields = {"caption": blk.get("caption", "")}
    if mtype == "IMAGE":
        url = blk.get("image_url") or die("IG 發圖必須給 image_url（外網打得開的公開網址）。"
                                          "IG API 不接受本機檔案上傳。")
        fields["image_url"] = url
    else:
        url = blk.get("video_url") or die("IG 發影片必須給 video_url（外網打得開的公開網址）")
        fields.update({"video_url": url, "media_type": "REELS"})
        if blk.get("cover_url"):
            fields["cover_url"] = blk["cover_url"]
    cont = api_post(cfg, "%s/media" % ig, fields)
    cid = cont.get("id") or die("建立 IG 容器失敗：%s" % cont)
    for i in range(40):
        st = api_get(cfg, cid, {"fields": "status_code,status"})
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code == "ERROR":
            die("IG 素材處理失敗：%s" % st.get("status"))
        print("   IG 素材處理中（%s）… %d/40" % (code, i + 1))
        time.sleep(6)
    else:
        die("IG 素材等太久未完成，稍後用同一個 creation_id 重試：%s" % cid)
    return api_post(cfg, "%s/media_publish" % ig, {"creation_id": cid})


def _log(code, post, plat, result, note=""):
    p = os.path.join(client_dir(code), "發佈紀錄.csv")
    pid = result.get("id") or result.get("post_id") or ""
    url = ""
    if plat == "fb" and pid and "_" in pid:
        page_part, post_part = pid.split("_", 1)
        url = "https://www.facebook.com/%s/posts/%s" % (page_part, post_part)
    with open(p, "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), plat,
                                post.get("type", ""), post.get("topic", ""), pid, url, note])


def _do_send(args, scheduled_ts=None):
    cfg = load_config(args.code)
    post = load_post(args.post)
    _describe(cfg, post)
    when = "排程於 %s" % datetime.fromtimestamp(scheduled_ts).strftime("%Y-%m-%d %H:%M") if scheduled_ts else "立即發佈"
    print("\n動作：%s" % when)
    if not args.confirm:
        print("\n🟡 這是 dry-run，什麼都沒有送出。")
        print("   確認上面每一項無誤、且客戶已同意後，才加 --confirm 再跑一次。")
        return
    for plat in post.get("platforms", []):
        blk = post.get(plat) or {}
        if plat == "fb":
            r = _fb_publish(cfg, blk, scheduled_ts)
            ok("FB 已送出：%s" % r)
            _log(args.code, post, "fb", r, "排程" if scheduled_ts else "")
        elif plat == "ig":
            if scheduled_ts:
                warn("IG 沒有原生排程 API，本則 IG 未送出。到點再跑 publish，或改人工發。")
                continue
            r = _ig_publish(cfg, blk)
            ok("IG 已送出：%s" % r)
            _log(args.code, post, "ig", r)
        else:
            warn("未知平台：%s（略過）" % plat)


def cmd_publish(args):
    _do_send(args, None)


def cmd_schedule(args):
    try:
        dt = datetime.strptime(args.at, "%Y-%m-%d %H:%M")
    except ValueError:
        die("--at 格式要是 \"YYYY-MM-DD HH:MM\"")
    ts = int(dt.timestamp())
    now = int(time.time())
    if ts < now + 600:
        die("FB 排程至少要 10 分鐘之後")
    if ts > now + 180 * 86400:
        die("FB 排程最多只能排到約 6 個月後")
    _do_send(args, ts)


# ────────────────────────────── limit / insights / report ──────────────────────────────
def cmd_limit(args):
    cfg = load_config(args.code)
    ig = cfg.get("ig_user_id") or die("config 的 ig_user_id 沒填")
    r = api_get(cfg, "%s/content_publishing_limit" % ig, {"fields": "config,quota_usage"})
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print("\nIG 內容發佈 API 有 24 小時額度上限，快到頂就先停，別硬送。")


def cmd_insights(args):
    cfg = load_config(args.code)
    since = int((datetime.now() - timedelta(days=args.days)).timestamp())
    until = int(time.time())
    if cfg.get("page_id"):
        try:
            r = api_get(cfg, "%s/insights" % cfg["page_id"],
                        {"metric": "page_impressions,page_post_engagements,page_fans",
                         "period": "day", "since": since, "until": until})
            print("── 粉專 ──")
            for m in r.get("data", []):
                vals = [v.get("value", 0) for v in m.get("values", [])]
                total = sum(v for v in vals if isinstance(v, int))
                print("  %s：期間合計 %s（末日 %s）" % (m.get("name"), total, vals[-1] if vals else "—"))
        except SystemExit as e:
            warn("粉專洞察抓取失敗（多半是權限或指標已改版）：%s" % e)
    if cfg.get("ig_user_id"):
        try:
            r = api_get(cfg, "%s/insights" % cfg["ig_user_id"],
                        {"metric": "reach,profile_views", "period": "day",
                         "since": since, "until": until})
            print("── IG ──")
            for m in r.get("data", []):
                vals = [v.get("value", 0) for v in m.get("values", [])]
                print("  %s：期間合計 %s" % (m.get("name"), sum(vals)))
        except SystemExit as e:
            warn("IG 洞察抓取失敗（指標名稱各版本差異大，見踩雷速查）：%s" % e)
    print("\n⚠️  Meta 的洞察指標名稱每個 API 版本都在改。抓不到先查版本，不要改成猜的指標。")


def cmd_report(args):
    code = args.code
    d = client_dir(code)
    rows = []
    p = os.path.join(d, "發佈紀錄.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r.get("日期", "").startswith(args.month)]
    out = os.path.join(d, "報表", "社群月報_%s.md" % args.month)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    by_plat = {}
    by_type = {}
    for r in rows:
        by_plat[r["平台"]] = by_plat.get(r["平台"], 0) + 1
        by_type[r["類型"]] = by_type.get(r["類型"], 0) + 1
    cfg = load_config(code)
    lines = [
        "# %s ｜ 社群月報 %s" % (cfg.get("brand_name") or code, args.month), "",
        "## 這個月做了什麼", "",
        "| 項目 | 數量 |", "|:--|--:|",
        "| 總發佈則數 | %d |" % len(rows),
    ]
    for k, v in by_plat.items():
        lines.append("| %s | %d |" % (k.upper(), v))
    lines += ["", "## 內容配比", "", "| 類型 | 則數 |", "|:--|--:|"]
    for k, v in sorted(by_type.items(), key=lambda x: -x[1]):
        lines.append("| %s | %d |" % (k or "未分類", v))
    lines += ["", "## 表現最好的三則（人工填，附網址與一句原因）", "1. ", "2. ", "3. ", "",
              "## 表現最差的三則（人工填，附網址與一句原因）", "1. ", "2. ", "3. ", "",
              "## 下個月調整什麼（最多三條，每條要可執行）", "1. ", "2. ", "3. ", "",
              "---", "",
              "> 數字先跑 `socialpost.py insights %s --days 30` 取得，" % code,
              "> 只把會影響下一步決策的數字寫進來，不要倒整包後台資料給客戶。"]
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    ok("月報骨架已產出：%s（表現最好／最差與調整方向要人工判讀後補上）" % out)


# ────────────────────────────── CLI ──────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="小群 · FB／IG 社群經營工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="建立客戶工作區");            s.add_argument("code"); s.set_defaults(f=cmd_init)
    s = sub.add_parser("auth", help="驗證 Token 與帳號");         s.add_argument("code"); s.set_defaults(f=cmd_auth)
    s = sub.add_parser("plan", help="產內容日曆")
    s.add_argument("code"); s.add_argument("--month", required=True, help="YYYY-MM")
    s.add_argument("--per-week", type=int, default=3, choices=[2, 3, 4, 5, 7]); s.set_defaults(f=cmd_plan)
    s = sub.add_parser("check", help="文案合規稽核")
    s.add_argument("file"); s.add_argument("--industry", choices=sorted(INDUSTRY)); s.set_defaults(f=cmd_check)
    s = sub.add_parser("card", help="產貼文圖卡")
    s.add_argument("code"); s.add_argument("--text", required=True, help='"主標|副標|補充"')
    s.add_argument("--ratio", default="4:5"); s.add_argument("--out")
    s.add_argument("--bg", default="#101014"); s.add_argument("--fg", default="#FFFFFF")
    s.add_argument("--accent", default="#C30D23"); s.add_argument("--logo"); s.set_defaults(f=cmd_card)
    s = sub.add_parser("preview", help="送出前預覽（不發）")
    s.add_argument("code"); s.add_argument("post"); s.set_defaults(f=cmd_preview)
    s = sub.add_parser("publish", help="發佈（預設 dry-run）")
    s.add_argument("code"); s.add_argument("post")
    s.add_argument("--confirm", action="store_true", help="真的送出。沒帶這個旗標只會印出將送出的內容")
    s.set_defaults(f=cmd_publish)
    s = sub.add_parser("schedule", help="排程發佈（FB 限定，預設 dry-run）")
    s.add_argument("code"); s.add_argument("post"); s.add_argument("--at", required=True)
    s.add_argument("--confirm", action="store_true"); s.set_defaults(f=cmd_schedule)
    s = sub.add_parser("limit", help="查 IG 24 小時發佈額度"); s.add_argument("code"); s.set_defaults(f=cmd_limit)
    s = sub.add_parser("insights", help="抓成效數據")
    s.add_argument("code"); s.add_argument("--days", type=int, default=30); s.set_defaults(f=cmd_insights)
    s = sub.add_parser("report", help="產月報骨架")
    s.add_argument("code"); s.add_argument("--month", required=True); s.set_defaults(f=cmd_report)

    args = ap.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()
