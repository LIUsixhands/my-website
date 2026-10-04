#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小曲 · Gemini 生情境鏡（AI 生圖只補「情境」，不生產品）

🚨 模型：gemini-3.1-flash-image-preview
   舊的 gemini-2.5-flash-image / imagen-4 已下架（2026-10-02），不要再用。

用法：
    python3 gen_images.py prompts.json --outdir assets
prompts.json = [{"name":"ai01_茶壺上桌","prompt":"..."}, ...]
"""
import os, sys, json, base64, pathlib, requests

MODEL = "gemini-3.1-flash-image-preview"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

def main():
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        sys.exit("❌ GEMINI_API_KEY 沒設")
    items = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    outdir = pathlib.Path(sys.argv[sys.argv.index("--outdir")+1] if "--outdir" in sys.argv else ".")
    outdir.mkdir(parents=True, exist_ok=True)

    ok = 0
    for it in items:
        dst = outdir / f"{it['name']}.png"
        if dst.exists():
            print(f"⏭  {dst.name} 已存在，跳過"); ok += 1; continue
        r = requests.post(URL, headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json={"contents":[{"parts":[{"text": it["prompt"]}]}],
                  "generationConfig":{"responseModalities":["IMAGE"],
                                      "imageConfig":{"aspectRatio": it.get("ratio","16:9")}}},
            timeout=180)
        if r.status_code != 200:
            print(f"❌ {it['name']} HTTP {r.status_code}: {r.text[:300]}"); continue
        data = r.json()
        blob = None
        for p in data.get("candidates",[{}])[0].get("content",{}).get("parts",[]):
            if "inlineData" in p: blob = p["inlineData"]["data"]; break
        if not blob:
            print(f"❌ {it['name']} 回應沒有圖（可能被 RAI 擋）：{json.dumps(data)[:300]}"); continue
        dst.write_bytes(base64.b64decode(blob))
        print(f"✅ {dst.name}  {dst.stat().st_size//1024} KB"); ok += 1
    print(f"--- 完成 {ok}/{len(items)} ---")
    sys.exit(0 if ok == len(items) else 1)

main()
