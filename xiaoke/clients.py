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
import urllib.error
import urllib.request

from engine import build_prompt

LINE_API = "https://api.line.me/v2/bot"
TIMEOUT = 20


class ApiError(RuntimeError):
    pass


def _request(method: str, url: str, token: str = "", body=None, timeout: int = TIMEOUT) -> dict:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise ApiError(f"HTTP {e.code} {url.split('?')[0]}: {detail}") from None
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
def gemini_draft(text: str, knowledge: str, brand: str) -> dict:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ApiError("沒有設定 GEMINI_API_KEY（寫在 .env）")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
           f"?key={key}")
    body = {
        "contents": [{"role": "user", "parts": [{"text": build_prompt(text, knowledge, brand)}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    out = _request("POST", url, body=body, timeout=30)
    try:
        raw = out["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise ApiError(f"Gemini 沒有回內容：{str(out)[:200]}") from None
    return parse_draft(raw)


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
