#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
netlify_deploy.py — Netlify digest 部署（只上傳伺服器沒有的檔案）

為什麼不用整包 zip：每次改一個檔案就上傳 63MB 太脆弱，
2026-09-09 的排程就是在上傳途中 Broken pipe 失敗的。
digest 的做法是先送全站檔案的 sha1 清單，伺服器回覆它缺哪些，只補那幾個。
實測上傳量從 63MB 降到 1.64MB。

可以直接執行，也可以 import 用：
  python3 netlify_deploy.py --src <網站根> --site-id <id>
  from netlify_deploy import deploy_digest, find_token
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API = "https://api.netlify.com/api/v1"


def find_token():
    """讀 Netlify CLI 存的 token（Mac / Windows / Linux），或吃環境變數。"""
    env = os.environ.get("NETLIFY_AUTH_TOKEN")
    if env:
        return env
    for c in [Path.home() / "Library" / "Preferences" / "netlify" / "config.json",
              Path(os.environ.get("APPDATA", "")) / "netlify" / "Config" / "config.json",
              Path.home() / ".config" / "netlify" / "config.json"]:
        try:
            if c.is_file():
                cfg = json.loads(c.read_text(encoding="utf-8"))
                uid = cfg.get("userId")
                tok = cfg.get("users", {}).get(uid, {}).get("auth", {}).get("token")
                if tok:
                    return tok
        except Exception:
            continue
    raise SystemExit("✗ 找不到 Netlify 憑證，也沒有 NETLIFY_AUTH_TOKEN。")


def deploy_digest(root: Path, site_id: str, token: str, log=print):
    root = Path(root)
    files, by_sha = {}, {}
    for f in root.rglob("*"):
        if not f.is_file() or f.name.startswith("."):
            continue
        h = hashlib.sha1(f.read_bytes()).hexdigest()
        files["/" + f.relative_to(root).as_posix()] = h
        by_sha.setdefault(h, f)
    return _deploy_manifest(files, by_sha, site_id, token, log)


def live_files(site_id: str, token: str):
    """目前線上那一版的完整檔案清單 {路徑: sha1}。一頁最多 100 筆，要翻頁。"""
    out, page = {}, 1
    while True:
        r = urllib.request.Request(
            f"{API}/sites/{site_id}/files?page={page}&per_page=100",
            headers={"Authorization": "Bearer " + token})
        batch = json.load(urllib.request.urlopen(r, timeout=60))
        if not batch:
            return out
        for f in batch:
            out[f["path"]] = f["sha"]
        page += 1


def deploy_overlay(overlay: dict, site_id: str, token: str, log=print, drop=()):
    """只換掉 overlay 裡的檔案，線上其他檔案原封不動。

    overlay = {"/blog/x.html": Path(...)}；drop = 要從線上拿掉的路徑（例如沒打碼的舊照片）。
    為什麼不整站重打包：網站資料夾同時有好幾條產線在部署（改版、講座頁、結果頁），
    整站重打包等於用這台機器當下的資料夾狀態覆蓋掉別人剛上線的東西；
    make_deploy 的引用分析也漏過 /logo/... 這種根目錄路徑，會把 favicon 與 OG 圖刪掉。
    部落格排程只該碰它自己產出的檔案。
    """
    files = live_files(site_id, token)
    if not files:
        raise SystemExit("✗ 讀不到線上檔案清單，為了不把整站清空，中止部署")
    lower = {p.lower(): p for p in files}      # Netlify 路徑不分大小寫、清單回小寫
    for path in drop:
        if files.pop(lower.get(path.lower(), path), None) is not None:
            log(f"  從線上移除 {path}")
    by_sha = {}
    for path, f in overlay.items():
        h = hashlib.sha1(Path(f).read_bytes()).hexdigest()
        files.pop(lower.get(path.lower(), path), None)
        files[path] = h
        by_sha.setdefault(h, Path(f))
    return _deploy_manifest(files, by_sha, site_id, token, log)


def _deploy_manifest(files: dict, by_sha: dict, site_id: str, token: str, log=print):
    req = urllib.request.Request(
        f"{API}/sites/{site_id}/deploys",
        data=json.dumps({"files": files}).encode(), method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=300))
    need = [h for h in d.get("required", []) if h in by_sha]
    total = sum(by_sha[h].stat().st_size for h in need)
    log(f"全站 {len(files)} 檔，需上傳 {len(need)} 個（{total/1024/1024:.2f} MB）")

    path_of = {}
    for p, h in files.items():
        path_of.setdefault(h, p)
    for i, h in enumerate(need, 1):
        f = by_sha[h]
        path = path_of[h]
        # 檔名含中文時 URL 一定要編碼，HTTP 請求行只能是 ASCII
        url = f"{API}/deploys/{d['id']}/files{urllib.parse.quote(path)}"
        for attempt in range(3):
            try:
                r = urllib.request.Request(
                    url, data=f.read_bytes(), method="PUT",
                    headers={"Authorization": "Bearer " + token,
                             "Content-Type": "application/octet-stream"})
                urllib.request.urlopen(r, timeout=600)
                break
            except Exception as e:
                if attempt == 2:
                    log(f"✗ 上傳失敗 {path}：{type(e).__name__}")
                    raise
                time.sleep(3 * (attempt + 1))
        if len(need) > 10 and i % 10 == 0:
            log(f"  已上傳 {i}/{len(need)}")

    # 輪詢部署狀態。這裡一定要能容錯——上傳完成後 Netlify 端可能重置連線
    # （2026-09-10 實測 Errno 54），但部署其實已經成功。
    # 沒有重試的話會回報「失敗」而實際上線了，比真失敗更難查。
    fails = 0
    for _ in range(60):
        time.sleep(5)
        try:
            r = urllib.request.Request(f"{API}/deploys/{d['id']}",
                                       headers={"Authorization": "Bearer " + token})
            st = json.load(urllib.request.urlopen(r, timeout=60))
            fails = 0
            if st["state"] in ("ready", "error"):
                return st
        except Exception as e:
            fails += 1
            log(f"  查詢部署狀態失敗（第 {fails} 次）：{type(e).__name__}，稍後重試")
            if fails >= 8:
                return {"state": "unknown", "deploy_id": d["id"],
                        "error_message": "上傳已完成但無法取得部署狀態，"
                                         "請用 /deploys 清單確認是否已 ready"}
    return {"state": "timeout", "deploy_id": d["id"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="要部署的資料夾（部署包，不是網站原始碼）")
    ap.add_argument("--site-id", default="80025f46-1ffa-4669-b866-9187fdc3fb9a")
    a = ap.parse_args()
    res = deploy_digest(Path(a.src).expanduser(), a.site_id, find_token())
    print(f"部署狀態：{res['state']}　{res.get('published_at','')}")
    if res["state"] != "ready":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
