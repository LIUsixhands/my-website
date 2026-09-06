#!/usr/bin/env python3
"""角色一致性與合規檢查。

用法：
    python3 check_consistency.py characters/xiaoyou
    python3 check_consistency.py characters/xiaoyou --strict   # TODO 未填也算錯

檢查項目：
  1. 四份文件是否齊全
  2. 必要區塊是否存在且已填寫
  3. AI 揭露聲明是否填好（未填直接 fail，不受 --strict 影響）
  4. flux.md Identity Lock 特徵數是否足夠
  5. drafts/ 內的文案是否命中 voice.md 禁用詞
  6. brain.md 與 memory/ 是否存了敏感個資
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charlib import FILES, block, lines_of, read, strip_todo  # noqa: E402

REQUIRED_BLOCKS = {
    "persona.md": ["TAGLINE", "IDENTITY", "DISCLOSURE"],
    "voice.md": ["VOICE_RULES", "BANNED", "FEWSHOT"],
    "flux.md": ["LOCK", "STYLE", "WARDROBE", "SCENES", "NEGATIVE"],
    "brain.md": ["MEMORY_SCHEMA"],
}

SENSITIVE = [
    (r"[A-Z][12]\d{8}", "疑似身分證字號"),
    (r"\b(?:\d[ -]?){15,16}\b", "疑似信用卡號"),
    (r"\b09\d{2}[- ]?\d{3}[- ]?\d{3}\b", "疑似手機號碼"),
    (r"[\w.+-]+@[\w-]+\.[\w.]+", "疑似 Email"),
    (r"\d+\s*(?:號|樓)\s*(?:之\d+)?\s*$", "疑似完整地址"),
    (r"(憂鬱症|躁鬱|癌症|愛滋|HIV|懷孕)", "疑似健康狀況"),
]
SENSITIVE_ALLOW = ("example_user", "@handle", "example.com", "0912-345-678")


class Report:
    def __init__(self):
        self.errors, self.warns = [], []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warns.append(msg)


def check_files(d, r):
    texts = {}
    for f in FILES:
        t = read(d, f)
        if t is None:
            r.err(f"缺少 {f}")
        texts[f] = t
    return texts


def check_blocks(texts, r, strict):
    for fname, names in REQUIRED_BLOCKS.items():
        t = texts.get(fname)
        if t is None:
            continue
        for b in names:
            content = block(t, b)
            if content is None:
                r.err(f"{fname}：找不到區塊 BLOCK:{b}（標記被刪掉了？）")
                continue
            if not strip_todo(content):
                msg = f"{fname}：區塊 {b} 還沒填內容"
                (r.err if (strict or b == "DISCLOSURE") else r.warn)(msg)


def check_disclosure(texts, r):
    t = texts.get("persona.md")
    if not t:
        return
    d = strip_todo(block(t, "DISCLOSURE") or "")
    if d and not re.search(r"(AI|人工智慧|虛擬)", d):
        r.err("persona.md：揭露聲明沒有明確寫出 AI／虛擬字樣")


def check_lock(texts, r):
    t = texts.get("flux.md")
    if not t:
        return
    lock = strip_todo(block(t, "LOCK") or "")
    if not lock:
        return
    feats = [x for x in lock.replace("\n", ",").split(",") if x.strip()]
    if len(feats) < 6:
        r.err(f"flux.md：Identity Lock 只有 {len(feats)} 項特徵，至少要 8 項才鎖得住臉")
    elif len(feats) < 8:
        r.warn(f"flux.md：Identity Lock 只有 {len(feats)} 項，建議補到 8–12 項")


def check_banned(d, texts, r):
    t = texts.get("voice.md")
    if not t:
        return
    banned = [w for w in lines_of(block(t, "BANNED") or "") if not w.startswith("[TODO")]
    drafts = sorted(Path(d, "drafts").glob("**/*")) if Path(d, "drafts").is_dir() else []
    for p in drafts:
        if not p.is_file() or p.suffix.lower() not in (".md", ".txt"):
            continue
        body = p.read_text(encoding="utf-8", errors="ignore")
        for w in banned:
            if w in body:
                r.err(f"{p}：命中禁用詞「{w}」")


def check_sensitive(d, texts, r):
    targets = []
    if texts.get("brain.md"):
        targets.append(("brain.md", texts["brain.md"]))
    mem = Path(d, "memory")
    if mem.is_dir():
        for p in sorted(mem.glob("**/*")):
            if p.is_file() and p.suffix.lower() in (".md", ".txt", ".json"):
                targets.append((str(p), p.read_text(encoding="utf-8", errors="ignore")))

    for label, body in targets:
        for ln_no, line in enumerate(body.splitlines(), 1):
            if any(a in line for a in SENSITIVE_ALLOW):
                continue
            for pat, why in SENSITIVE:
                if re.search(pat, line):
                    r.err(f"{label}:{ln_no}：{why} → 依 brain.md §4 不得留存")
                    break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("char_dir")
    ap.add_argument("--strict", action="store_true", help="未填的 TODO 也視為錯誤")
    a = ap.parse_args()

    d = Path(a.char_dir)
    if not d.is_dir():
        sys.exit(f"✗ 找不到角色資料夾：{d}")

    r = Report()
    texts = check_files(d, r)
    check_blocks(texts, r, a.strict)
    check_disclosure(texts, r)
    check_lock(texts, r)
    check_banned(d, texts, r)
    check_sensitive(d, texts, r)

    todo_total = sum((t or "").count("[TODO") for t in texts.values())

    print(f"角色：{d}")
    print(f"未填 TODO：{todo_total} 處")
    for w in r.warns:
        print(f"  ⚠ {w}")
    for e in r.errors:
        print(f"  ✗ {e}")

    if r.errors:
        print(f"\n不通過（{len(r.errors)} 個錯誤）")
        return 1
    if todo_total:
        print("\n通過，但還有 TODO 未填 —— 上線前請跑 --strict")
        return 0
    print("\n✓ 全部通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
