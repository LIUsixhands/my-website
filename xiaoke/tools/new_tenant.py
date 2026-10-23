"""
new_tenant.py — 開一套新客服（一個 LINE 官方帳號 = 一個租戶）。

  python tools/new_tenant.py <代號> --name "品牌名"
  python tools/new_tenant.py <代號> --name "物件分析" --type listing   （群組貼物件 → 行情＋591 廣告詞）

代號只能用英文、數字、底線、減號（會變成 webhook 網址的一段）。
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import engine  # noqa: E402

TEMPLATE = engine.BASE_DIR / "templates" / "knowledge.md"


def create(code: str, name: str, root: Path = engine.TENANTS_DIR, kind: str = "service",
           city: str = "臺中市") -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", code):
        raise SystemExit(f"代號「{code}」不行：只能用英文、數字、底線、減號，且不能用 _ 開頭")
    d = root / code
    if (d / "config.json").exists():
        raise SystemExit(f"{code} 已經存在（{d}），不覆蓋。")
    d.mkdir(parents=True, exist_ok=True)
    cfg = {
        "name": name,
        "channel_secret": "",
        "channel_access_token": "",
        "mode": "review",
        "pairing_code": engine.new_pairing_code(),
        "admins": [],
        "handoff_message": "收到！這個問題我幫你轉給專人，會盡快回覆你 🙏",
        "welcome_message": "",
        "banned_words": list(engine.DEFAULT_BANNED),
        "force_handoff_words": [],
        "next_id": 1,
    }
    if kind == "listing":
        cfg.update(type="listing", default_city=city)
    engine.atomic_write_json(d / "config.json", cfg)
    kb = d / "knowledge.md"
    if not kb.exists():
        kb.write_text(TEMPLATE.read_text(encoding="utf-8").replace("{name}", name), encoding="utf-8")
    return d


def main() -> None:
    engine.safe_console()
    ap = argparse.ArgumentParser(description="開一套新客服")
    ap.add_argument("code", help="租戶代號，例：sixhands")
    ap.add_argument("--name", required=True, help="品牌名稱")
    ap.add_argument("--type", choices=["service", "listing"], default="service",
                    help="service＝客服（預設）；listing＝物件分析")
    ap.add_argument("--city", default="臺中市", help="物件分析模式：物件沒寫縣市時用哪個")
    a = ap.parse_args()
    d = create(a.code, a.name, kind=a.type, city=a.city)
    cfg = engine.Tenant(a.code).config
    print(f"[ OK ] 已建立 {d}")
    print("下一步：")
    print(f"  1. 把 Channel secret 與 Channel access token 填進 {d / 'config.json'}")
    if a.type == "listing":
        print("  2. （物件分析不用寫知識庫）")
    else:
        print(f"  2. 把客戶資料寫進 {d / 'knowledge.md'}（留著的【待補】AI 會轉真人）")
    print("  3. 重啟小客：powershell -ExecutionPolicy Bypass -File windows\\restart.ps1")
    print(f"  4. 負責人用 LINE 1 對 1 傳配對碼給官方帳號：{cfg['pairing_code']}")


if __name__ == "__main__":
    main()
