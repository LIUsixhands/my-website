"""
clients.py — 對外連線：LINE Messaging API 與 Gemini。只用標準庫，不必 pip install。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.request

from engine import build_prompt

LINE_API = "https://api.line.me/v2/bot"
TIMEOUT = 20
RETRY_WAIT = 2   # 秒；測試會把它調成 0
GEMINI_TRIES = 4


class ApiError(RuntimeError):
    def __init__(self, msg: str, status: int = 0):
        super().__init__(msg)
        self.status = status


def _request(method: str, url: str, token: str = "", body=None, timeout: int = TIMEOUT,
             headers: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise ApiError(f"HTTP {e.code} {url.split('?')[0]}: {detail}", e.code) from None
    except urllib.error.URLError as e:
        raise ApiError(f"連不上 {url.split('?')[0]}: {e.reason}") from None
    return json.loads(raw) if raw.strip() else {}


# ── LINE ──────────────────────────────────────────────
def verify_signature(channel_secret: str, body: bytes, signature: str) -> bool:
    """LINE 用 channel secret 對原始 body 做 HMAC-SHA256。驗不過就不是 LINE 送來的。"""
    if not channel_secret or not signature:
        return False
    mac = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(mac).decode("ascii"), signature)


def _text_messages(text: str) -> list[dict]:
    return [{"type": "text", "text": text[:5000]}]   # LINE 單則上限 5000 字


def line_reply(token: str, reply_token: str, text: str) -> None:
    """回覆：免費、不吃推播額度，但 reply token 只能用一次、很快就過期。"""
    _request("POST", f"{LINE_API}/message/reply", token,
             {"replyToken": reply_token, "messages": _text_messages(text)})


def line_push(token: str, to: str, text: str) -> None:
    """推播：隨時可發，但每則都吃當月額度。額度用完會回 HTTP 429。"""
    _request("POST", f"{LINE_API}/message/push", token,
             {"to": to, "messages": _text_messages(text)})


def line_set_webhook(token: str, endpoint: str) -> None:
    _request("PUT", f"{LINE_API}/channel/webhook/endpoint", token, {"endpoint": endpoint})


def line_get_webhook(token: str) -> dict:
    return _request("GET", f"{LINE_API}/channel/webhook/endpoint", token)


# ── Gemini ────────────────────────────────────────────
def gemini_json(prompt: str, temperature: float = 0.2) -> str:
    """送 prompt 給 Gemini，要求回 JSON，回傳原始文字（呼叫端自己解析）。"""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ApiError("沒有設定 GEMINI_API_KEY（寫在 .env）")
    # 實機紀錄（2026-09）：2.5-flash 不開放新帳號（404）；Google 推薦的 3.6-flash 免費方案
    # 連續 503 塞車；3.5-flash 可用、客服問答也夠。要換就改 .env 的 GEMINI_MODEL。
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    # 金鑰放標頭不放網址：網址會被印進錯誤訊息與 log
    # 503「模型忙碌」、429 限流通常幾秒就好（實機遇過 503），重試兩次再放棄
    # 免費方案尖峰常連續 503（實機遇過），等 3、6、12 秒共試 4 次
    for attempt in range(GEMINI_TRIES):
        try:
            out = _request("POST", url, body=body, timeout=30, headers={"x-goog-api-key": key})
            break
        except ApiError as e:
            # 429 多半是額度用完，一直重試只會更快用光：只再試一次
            if e.status not in (429, 500, 503) or attempt == GEMINI_TRIES - 1 \
                    or (e.status == 429 and attempt >= 1):
                raise
            time.sleep(RETRY_WAIT * 1.5 * 2 ** attempt)
    try:
        return out["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise ApiError(f"Gemini 沒有回內容：{str(out)[:200]}") from None


def gemini_draft(text: str, knowledge: str, brand: str) -> dict:
    return parse_draft(gemini_json(build_prompt(text, knowledge, brand)))


def parse_draft(raw: str) -> dict:
    """模型偶爾會把 JSON 包在 ```json 裡。解不開就當作沒把握。"""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"answerable": False, "reply": "", "reason": "擬稿格式錯誤"}
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return {"answerable": False, "reply": "", "reason": "擬稿格式錯誤"}
    return {"answerable": d.get("answerable") is True,
            "reply": str(d.get("reply") or ""),
            "reason": str(d.get("reason") or "")}
