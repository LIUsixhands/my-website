"""
server.py — 小客主程式。Windows 雙擊或開機排程都是跑這支。

  python server.py            啟動（預設自己開 cloudflared 對外網址，並自動註冊 webhook）
  python server.py --check    只做體檢：金鑰、租戶設定、cloudflared 找不找得到

一支程式包三件事：
  1. 本機 HTTP 服務（埠 8788）：/webhook/<租戶代號> 收 LINE、/health 看狀態
  2. 對外網址：LINE 只能打公開的 https，家用電腦沒有 → 開 cloudflared 通道
  3. webhook 自動註冊：快速通道每次重開網址都會變，所以拿到新網址就重新告訴 LINE
     （Mac 版那套曾經因為網址過期、LINE 打不進來，服務看起來活著卻一個月沒回訊息）
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path

import clients
import engine
from engine import Tenant

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"

engine.load_env()
PORT = int(os.environ.get("XIAOKE_PORT", "8788"))
log = logging.getLogger("xiaoke")

HANDOFF_MSG = "收到！這個問題我幫你轉給專人，會盡快回覆你 🙏"


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    fh = RotatingFileHandler(LOG_DIR / "xiaoke.log", maxBytes=2_000_000, backupCount=5,
                             encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(fh)
    log.setLevel(logging.INFO)
    # pythonw（開機排程用的無視窗版）沒有主控台，sys.stdout 是 None
    if sys.stdout is not None:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
        log.addHandler(sh)


# ── 訊息處理 ──────────────────────────────────────────
class Bot:
    """一個租戶的 LINE 動作。測試時把 reply/push 換成假的。"""

    def __init__(self, t: Tenant, drafter=clients.gemini_draft, reply=None, push=None):
        self.t = t
        self.drafter = drafter
        self._reply = reply or (lambda rt, text: clients.line_reply(self.token, rt, text))
        self._push = push or (lambda to, text: clients.line_push(self.token, to, text))

    @property
    def token(self) -> str:
        return self.t.config.get("channel_access_token", "")

    def reply(self, reply_token: str, target: str, text: str) -> None:
        """優先用免費的 reply；token 過期（擬稿太久）就退回 push。"""
        try:
            self._reply(reply_token, text)
        except clients.ApiError as e:
            log.warning("[%s] reply 失敗改用 push：%s", self.t.code, e)
            self.push(target, text)

    def push(self, to: str, text: str) -> None:
        try:
            self._push(to, text)
        except clients.ApiError as e:
            self.t.log(kind="push_error", to=to, error=str(e))
            log.error("[%s] push 失敗（多半是當月推播額度用完）：%s", self.t.code, e)
            raise

    def notify_admins(self, text: str) -> None:
        admins = self.t.config.get("admins", [])
        if not admins:
            log.warning("[%s] 還沒有管理員配對，這則通知沒人收得到：%s", self.t.code, text[:60])
        for a in admins:
            try:
                self.push(a, text)
            except clients.ApiError:
                pass

    # ─────────────────────────────────────
    def handle(self, ev: dict) -> None:
        etype = ev.get("type")
        src = ev.get("source", {})
        user = src.get("userId", "")
        target = src.get("groupId") or src.get("roomId") or user
        in_group = src.get("type") in ("group", "room")
        rt = ev.get("replyToken", "")
        cfg = self.t.config

        if etype == "follow":
            if cfg.get("welcome_message"):
                self.reply(rt, target, cfg["welcome_message"])
            self.t.log(kind="follow", user=user)
            return
        if etype != "message":
            return

        msg = ev.get("message", {})
        mtype = msg.get("type")

        # 管理員（只認 1 對 1）：訊息一律是指令，不當客戶問題
        if not in_group and user in cfg.get("admins", []):
            if mtype == "text":
                try:
                    answer = engine.admin_command(self.t, msg.get("text", ""), self.push)
                except clients.ApiError as e:
                    answer = f"❌ 發送失敗，這則還留在清單裡：{e}"[:500]
                self.reply(rt, user, answer)
            return

        if mtype != "text":
            if in_group or mtype == "sticker":
                return                           # 貼圖與群組裡的圖片不處理
            # 1 對 1 傳圖片／檔案：可能是證件照或匯款單，一律真人看
            self._handoff(rt, target, user, f"[{mtype}]", "非文字訊息", in_group, log_it=True)
            return

        text = msg.get("text", "")

        # 配對碼：成為管理員，並立刻換一組新碼（舊碼外流也無法再用）
        code = str(cfg.get("pairing_code", ""))
        if not in_group and code and text.strip() == code:
            admins = cfg.get("admins", []) + [user]
            new_code = engine.new_pairing_code()
            self.t.update_config(admins=admins, pairing_code=new_code)
            self.t.log(kind="paired", user=user)
            self.reply(rt, user, "✅ 配對成功，你是這個帳號的客服管理員了。\n"
                                 f"要再加一位管理員，請他傳新配對碼：{new_code}\n\n" + engine.HELP)
            return

        if in_group and not engine.looks_like_question(text):
            return                               # 群組閒聊不插話

        d = engine.decide(text, self.t.knowledge, cfg, self.drafter)
        entry = dict(kind="in", user=user, group=in_group, text=text,
                     action=d.action, reason=d.reason, flags=d.flags)

        if d.action == "reply" and cfg.get("mode") == "auto":
            self.reply(rt, target, d.reply)
            self.t.log(**entry, sent="auto", reply=d.reply)
            return
        if d.action == "reply":                  # 審核模式：先給管理員看
            it = self.t.add_pending(dict(kind="review", target=target, user=user,
                                         text=text, draft=d.reply, reason="審核"))
            self.t.log(**entry, sent="pending", item=it["id"], reply=d.reply)
            self.notify_admins(engine.fmt_item(it))
            return

        self.t.log(**entry, sent="none")
        self._handoff(rt, target, user, text, d.reason, in_group,
                      draft=d.reply if "banned" in d.flags else "",
                      warn=d.action == "block")

    def _handoff(self, rt, target, user, text, reason, in_group, draft="", warn=False,
                 log_it=False):
        if not in_group:                         # 群組裡不發「已轉專人」，免得洗版
            self.reply(rt, target, self.t.config.get("handoff_message") or HANDOFF_MSG)
        it = self.t.add_pending(dict(kind="handoff", target=target, user=user,
                                     text=text, draft=draft, reason=reason))
        if log_it:                               # 非文字訊息在 handle() 裡沒有 log 過
            self.t.log(kind="in", user=user, group=in_group, text=text,
                       action="handoff", reason=reason, flags=[], sent="none")
        prefix = "⚠️ 疑似注入，已擋下自動回覆\n" if warn else ""
        self.notify_admins(prefix + engine.fmt_item(it))


# ── HTTP ──────────────────────────────────────────────
class Seen:
    """LINE 會重送 webhook。同一個 webhookEventId 只處理一次。"""

    def __init__(self, size: int = 2000):
        self.ids: OrderedDict[str, None] = OrderedDict()
        self.size = size
        self.lock = threading.Lock()

    def first_time(self, eid: str) -> bool:
        if not eid:
            return True
        with self.lock:
            if eid in self.ids:
                return False
            self.ids[eid] = None
            if len(self.ids) > self.size:
                self.ids.popitem(last=False)
            return True


SEEN = Seen()
STATE = {"public_url": "", "registered": {}, "started": time.time()}


def process(code: str, body: bytes) -> None:
    t = Tenant(code)
    bot = Bot(t)
    for ev in json.loads(body.decode("utf-8")).get("events", []):
        if not SEEN.first_time(ev.get("webhookEventId", "")):
            continue
        try:
            bot.handle(ev)
        except Exception:
            log.exception("[%s] 處理訊息失敗", code)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):          # 不要每個請求都洗一行
        pass

    def _send(self, status: int, obj) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        # 經過 cloudflared 進來的請求會帶 Cf-Connecting-Ip。/health 只給本機看，
        # 不讓網路上的人知道有哪些租戶、待處理幾則。
        if self.path.rstrip("/") == "/health" and not self.headers.get("Cf-Connecting-Ip"):
            self._send(200, health())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        m = re.fullmatch(r"/webhook/([A-Za-z0-9_-]+)/?", self.path)
        if not m or m.group(1) not in engine.list_tenants():
            self._send(404, {"error": "unknown tenant"})
            return
        code = m.group(1)
        body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        secret = Tenant(code).config.get("channel_secret", "")
        if not clients.verify_signature(secret, body, self.headers.get("X-Line-Signature", "")):
            log.warning("[%s] 簽章不符，丟掉（不是 LINE 送的，或 channel secret 填錯）", code)
            self._send(401, {"error": "bad signature"})
            return
        # 先回 200 再慢慢處理：Gemini 擬稿要幾秒，LINE 等太久會判定 webhook 失敗
        self._send(200, {"ok": True})
        threading.Thread(target=process, args=(code, body), daemon=True).start()


def health() -> dict:
    tenants = {}
    for code in engine.list_tenants():
        t = Tenant(code)
        cfg = t.config
        tenants[code] = {
            "name": cfg.get("name", ""),
            "mode": cfg.get("mode", "review"),
            "pending": len(t.pending()),
            "admins": len(cfg.get("admins", [])),
            "webhook": STATE["registered"].get(code, "未註冊"),
        }
    return {"ok": True, "public_url": STATE["public_url"],
            "uptime_min": int((time.time() - STATE["started"]) / 60), "tenants": tenants}


# ── 對外網址與 webhook 註冊 ───────────────────────────
def register_webhooks(public_url: str) -> None:
    STATE["public_url"] = public_url
    for code in engine.list_tenants():
        token = Tenant(code).config.get("channel_access_token", "")
        if not token:
            STATE["registered"][code] = "缺 channel_access_token"
            continue
        endpoint = f"{public_url.rstrip('/')}/webhook/{code}"
        try:
            clients.line_set_webhook(token, endpoint)
            STATE["registered"][code] = endpoint
            log.info("[%s] webhook 已註冊：%s", code, endpoint)
        except clients.ApiError as e:
            STATE["registered"][code] = f"註冊失敗：{e}"
            log.error("[%s] webhook 註冊失敗：%s", code, e)


def find_cloudflared() -> str:
    explicit = os.environ.get("CLOUDFLARED_PATH", "").strip()
    if explicit:
        return explicit
    found = shutil.which("cloudflared")
    if found:
        return found
    for p in (r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
              r"C:\Program Files\cloudflared\cloudflared.exe",
              str(BASE_DIR / "cloudflared.exe")):
        if Path(p).exists():
            return p
    return ""


TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def run_quick_tunnel(exe: str) -> None:
    """開 cloudflared 快速通道；它掛了就重開，並用新網址重新註冊 webhook。"""
    backoff = 5
    while True:
        log.info("啟動 cloudflared 通道…")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # Windows 不要跳黑視窗
        proc = subprocess.Popen(
            [exe, "tunnel", "--no-autoupdate", "--url", f"http://localhost:{PORT}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", creationflags=flags)
        started = time.time()
        for line in proc.stderr:                  # cloudflared 把網址印在 stderr
            m = TUNNEL_URL.search(line)
            if m and m.group(0) != STATE["public_url"]:
                register_webhooks(m.group(0))
        proc.wait()
        STATE["public_url"] = ""
        backoff = 5 if time.time() - started > 300 else min(backoff * 2, 300)
        log.error("cloudflared 結束（代碼 %s），%s 秒後重開", proc.returncode, backoff)
        time.sleep(backoff)


def start_public_url() -> None:
    fixed = os.environ.get("PUBLIC_URL", "").strip()
    if fixed:                                    # 自己的網域／固定通道：只註冊一次
        register_webhooks(fixed)
        return
    exe = find_cloudflared()
    if not exe:
        log.error("找不到 cloudflared，LINE 打不進來。請先安裝：winget install --id Cloudflare.cloudflared")
        return
    threading.Thread(target=run_quick_tunnel, args=(exe,), daemon=True).start()


# ── 體檢 ──────────────────────────────────────────────
def check() -> int:
    engine.safe_console()
    problems = 0

    def item(ok: bool, msg: str) -> None:
        nonlocal problems
        problems += 0 if ok else 1
        print(("[ OK ] " if ok else "[FAIL] ") + msg)

    item(bool(os.environ.get("GEMINI_API_KEY")), "GEMINI_API_KEY（.env）")
    cf = find_cloudflared()
    item(bool(cf or os.environ.get("PUBLIC_URL")),
         f"對外網址：{cf or os.environ.get('PUBLIC_URL') or '找不到 cloudflared'}")
    if "onedrive" in str(BASE_DIR).lower():
        item(False, f"程式放在 OneDrive 同步資料夾（{BASE_DIR}），請搬到 C:\\xiaoke")
    codes = engine.list_tenants()
    item(bool(codes), f"租戶：{', '.join(codes) or '還沒建，先跑 python tools/new_tenant.py'}")
    for code in codes:
        t = Tenant(code)
        cfg = t.config
        item(bool(cfg.get("channel_secret")), f"{code}：channel_secret")
        item(bool(cfg.get("channel_access_token")), f"{code}：channel_access_token")
        todo = t.knowledge.count(engine.PENDING_TAG)
        print(f"[INFO] {code}：模式 {cfg.get('mode')}、管理員 {len(cfg.get('admins', []))} 位、"
              f"知識庫【待補】{todo} 處、配對碼 {cfg.get('pairing_code')}")
    print("\n全部通過" if not problems else f"\n{problems} 項要處理")
    return 1 if problems else 0


def main() -> int:
    if "--check" in sys.argv:
        return check()
    setup_logging()
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        log.error("埠 %s 開不起來（小客是不是已經在跑了？）：%s", PORT, e)
        return 1
    log.info("小客啟動，埠 %s，租戶：%s", PORT, ", ".join(engine.list_tenants()) or "（無）")
    start_public_url()
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
