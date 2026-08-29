#!/usr/bin/env python3
"""
把一筆預測追加到專案根目錄的 predictions.jsonl（每行一個 JSON）。

用法（用 --json 傳入完整物件字串最省事）：
  python log_prediction.py --json '{"date":"2026-07-23","ticker":"2330","name":"台積電",
    "market":"TW","direction":"看多","confidence":"中","horizon":"1-3個月",
    "thesis":"...","scenarios":{"bull":0.4,"base":0.45,"bear":0.15}}'

或用旗標逐欄帶入（未帶的欄位留空/預設）：
  python log_prediction.py --ticker 2330 --name 台積電 --direction 看多 \
    --confidence 中 --horizon 1-3個月 --thesis "外資轉買+CoWoS需求超預期"

欄位定義見 ../references/prediction-log.md。
檔案預設寫到「目前工作目錄往上找到的 git repo 根目錄」，找不到就寫到 cwd。
"""
import sys
import os
import json
import argparse
import datetime
import subprocess

FIELDS = ["date", "ticker", "name", "market", "direction", "confidence", "horizon",
          "thesis", "entry_ref", "stop_ref", "target_ref", "scenarios",
          "price_at_call", "outcome", "verified_date", "note"]


def repo_root():
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return os.getcwd()


def normalize(rec):
    rec.setdefault("date", datetime.date.today().isoformat())
    rec.setdefault("market", "TW")
    for f in FIELDS:
        rec.setdefault(f, None)
    if rec.get("outcome") is None:
        rec["outcome"] = None
    return {k: rec.get(k) for k in FIELDS}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--json")
    for f in ["ticker", "name", "direction", "confidence", "horizon", "thesis",
              "entry_ref", "stop_ref", "target_ref", "note"]:
        p.add_argument(f"--{f}")
    p.add_argument("--price_at_call", type=float)
    p.add_argument("--scenarios", help='如 \'{"bull":0.4,"base":0.45,"bear":0.15}\'')
    p.add_argument("--file", help="覆寫輸出檔路徑")
    args = p.parse_args()

    if args.json:
        rec = json.loads(args.json)
    else:
        rec = {}
        for f in ["ticker", "name", "direction", "confidence", "horizon", "thesis",
                  "entry_ref", "stop_ref", "target_ref", "note", "price_at_call"]:
            v = getattr(args, f)
            if v is not None:
                rec[f] = v
        if args.scenarios:
            rec["scenarios"] = json.loads(args.scenarios)

    rec = normalize(rec)
    if not rec.get("ticker") and not rec.get("name"):
        print("ERROR: 至少要有 ticker 或 name", file=sys.stderr)
        sys.exit(1)

    path = args.file or os.path.join(repo_root(), "predictions.jsonl")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"已寫入預測 → {path}")
    print(json.dumps(rec, ensure_ascii=False))


if __name__ == "__main__":
    main()
