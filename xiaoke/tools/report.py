"""
report.py — 客服成效報表。

  python tools/report.py              全部租戶近 30 天
  python tools/report.py lobster 7    指定租戶近 7 天

要看三個數字：
  自動化率 < 50%  → 知識庫太薄，照「轉人工的原因」補
  擬稿失敗 > 0    → Gemini 金鑰或額度問題，查 logs/xiaoke.log
  疑似注入 > 0    → 有人在玩 AI，看 log 決定要不要封鎖
"""
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import engine  # noqa: E402


def summarize(t: engine.Tenant, days: int) -> dict:
    logs = t.read_log(time.time() - days * 86400)
    msgs = [e for e in logs if e.get("kind") == "in"]
    total = len(msgs)
    auto = sum(1 for e in msgs if e.get("sent") == "auto")
    ai_ok = sum(1 for e in msgs if e.get("action") == "reply")   # 含審核模式下 AI 有把握的
    reasons = Counter(e.get("reason", "") for e in msgs if e.get("action") != "reply")
    return {
        "total": total,
        "auto": auto,
        "ai_ok": ai_ok,
        "rate": (ai_ok / total * 100) if total else 0.0,
        "handoff": total - ai_ok,
        "draft_error": sum(1 for e in msgs if "draft_error" in e.get("flags", [])),
        "injection": sum(1 for e in msgs if "injection" in e.get("flags", [])),
        "push_error": sum(1 for e in logs if e.get("kind") == "push_error"),
        "admin_sent": sum(1 for e in logs if e.get("kind") == "sent"),
        "reasons": reasons.most_common(10),
        "pending": len(t.pending()),
    }


def render(code: str, name: str, days: int, s: dict) -> str:
    out = [f"=== {name or code}（{code}）近 {days} 天 ===",
           f"收到訊息　{s['total']} 則",
           f"AI 能答　 {s['ai_ok']} 則（自動化率 {s['rate']:.0f}%，其中直接自動發出 {s['auto']} 則）",
           f"轉真人　　{s['handoff']} 則；管理員已回 {s['admin_sent']} 則；還在等 {s['pending']} 則",
           f"擬稿失敗　{s['draft_error']}　疑似注入　{s['injection']}　推播失敗　{s['push_error']}"]
    if s["reasons"]:
        out.append("轉人工的原因（這就是該補的知識庫）：")
        out += [f"  {n:>3} 次  {r}" for r, n in s["reasons"]]
    rx = []
    if s["total"] and s["rate"] < 50:
        rx.append("自動化率低於 50%：照上面的原因補知識庫")
    if s["draft_error"]:
        rx.append("有擬稿失敗：檢查 .env 的 GEMINI_API_KEY 與額度，看 logs/xiaoke.log")
    if s["injection"]:
        rx.append("有疑似注入：看 log.jsonl 決定要不要封鎖該用戶")
    if s["push_error"]:
        rx.append("有推播失敗：多半是當月訊息額度用完，到 LINE 後台看用量")
    if rx:
        out.append("處方：")
        out += [f"  - {r}" for r in rx]
    return "\n".join(out)


def main() -> None:
    engine.safe_console()
    args = sys.argv[1:]
    codes = [args[0]] if args and not args[0].isdigit() else engine.list_tenants()
    days = int(next((a for a in args if a.isdigit()), 30))
    if not codes:
        print("還沒有租戶。先跑 python tools/new_tenant.py <代號> --name \"品牌名\"")
        return
    for code in codes:
        t = engine.Tenant(code)
        print(render(code, t.config.get("name", ""), days, summarize(t, days)))
        print()


if __name__ == "__main__":
    main()
