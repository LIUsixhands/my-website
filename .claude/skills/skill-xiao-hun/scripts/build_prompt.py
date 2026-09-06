#!/usr/bin/env python3
"""把四文件組裝成可直接使用的 prompt。

聊天 / 文案用（組 persona + voice + brain）：
    python3 build_prompt.py characters/xiaoyou --mode chat
    python3 build_prompt.py characters/xiaoyou --mode chat --user @example_user

生圖用（組 flux.md 的 Lock + 風格 + 衣櫃 + 場景）：
    python3 build_prompt.py characters/xiaoyou --mode image --outfit W01 --scene S02
    python3 build_prompt.py characters/xiaoyou --mode image --outfit W01 --scene S02 --extra "holding a paper cup"
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charlib import block, lookup, read, strip_todo  # noqa: E402


def memory_of(brain, handle):
    """從 brain.md §3 撈出某個 handle 的記憶檔。"""
    if not brain or not handle:
        return None
    h = handle if handle.startswith("@") else "@" + handle
    m = re.search(r"^###\s*%s\s*$(.*?)(?=^#{1,3}\s|\Z)" % re.escape(h), brain, re.S | re.M)
    return m.group(1).strip() if m else None


def build_chat(d, user):
    persona = read(d, "persona.md")
    voice = read(d, "voice.md")
    brain = read(d, "brain.md")
    if not (persona and voice):
        sys.exit("✗ 缺少 persona.md 或 voice.md")

    parts = ["你要扮演以下這個虛擬人物。這不是角色扮演遊戲，是內容生產 —— 語氣一致比創意重要。\n"]

    for title, content in (
        ("【定位】", strip_todo(block(persona, "TAGLINE") or "")),
        ("【身份】", strip_todo(block(persona, "IDENTITY") or "")),
        ("【說話規格】", strip_todo(block(voice, "VOICE_RULES") or "")),
        ("【語氣範例（照這個語感寫）】", strip_todo(block(voice, "FEWSHOT") or "")),
    ):
        if content:
            parts.append(f"{title}\n{content}\n")

    banned = strip_todo(block(voice, "BANNED") or "")
    if banned:
        words = "、".join(w.strip() for w in banned.splitlines() if w.strip())
        parts.append(f"【禁用詞（一個都不准出現）】\n{words}\n")

    if user:
        mem = memory_of(brain, user)
        if mem:
            parts.append(
                f"【關於 {user} 的記憶】\n{mem}\n"
                "使用規則：這次回覆最多帶入 1 條已知事實，不要一次全講出來。\n"
            )
        else:
            parts.append(f"【關於 {user}】\n沒有記憶檔。正常回覆，不要假裝認識對方。\n")

    disclosure = strip_todo(block(persona, "DISCLOSURE") or "")
    parts.append(
        "【不可違反的底線】\n"
        f"1. 被問是不是真人 → 誠實回答：{disclosure or '（尚未設定揭露聲明）'}\n"
        "2. 不談戀愛、不做曖昧承諾、不答應見面或視訊\n"
        "3. 不主動要錢、不收私下匯款\n"
        "4. 不給醫療／法律／投資建議\n"
        "5. 對方提及自傷 → 立即停止扮演，提供求助專線（台灣 1925）並轉真人處理\n"
    )
    return "\n".join(parts)


def build_image(d, outfit, scene, extra):
    flux = read(d, "flux.md")
    if not flux:
        sys.exit("✗ 缺少 flux.md")

    lock = strip_todo(block(flux, "LOCK") or "")
    if not lock:
        sys.exit("✗ flux.md 的 Identity Lock 還沒填 —— 沒有它每張圖都會是不同人")

    seg = [lock.replace("\n", " ")]

    style = block(flux, "STYLE") or ""
    style_bits = [
        cells[-1]
        for cells in (
            [c.strip() for c in ln.strip("|").split("|")]
            for ln in style.splitlines()
            if ln.strip().startswith("|")
        )
        if len(cells) >= 2 and cells[0] not in ("項目",) and set("".join(cells)) > set("-: ")
    ]
    style_bits = [s for s in style_bits if s and "[TODO" not in s and s != "設定"]

    if outfit:
        frag = lookup(block(flux, "WARDROBE"), outfit)
        if not frag or "[TODO" in frag:
            sys.exit(f"✗ 衣櫃裡沒有 {outfit}（或還沒填）")
        seg.append(frag)
    if scene:
        frag = lookup(block(flux, "SCENES"), scene)
        if not frag or "[TODO" in frag:
            sys.exit(f"✗ 場景庫裡沒有 {scene}（或還沒填）")
        seg.append(frag)
    if extra:
        seg.append(extra)
    seg.extend(style_bits)

    negative = " ".join((block(flux, "NEGATIVE") or "").split())

    out = ["POSITIVE:", ", ".join(s.strip().rstrip(",") for s in seg if s.strip())]
    if negative:
        out += ["", "NEGATIVE:", negative]
    out += [
        "",
        "# 生成後務必跑 flux.md §7 一致性檢查表；任一項不過就整批重生，不要挑圖。",
    ]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("char_dir")
    ap.add_argument("--mode", choices=("chat", "image"), required=True)
    ap.add_argument("--user", help="chat 模式：帶入這位互動者的記憶")
    ap.add_argument("--outfit", help="image 模式：衣櫃編號，例 W01")
    ap.add_argument("--scene", help="image 模式：場景編號，例 S02")
    ap.add_argument("--extra", help="image 模式：這張圖額外的動作或道具")
    a = ap.parse_args()

    d = Path(a.char_dir)
    if not d.is_dir():
        sys.exit(f"✗ 找不到角色資料夾：{d}")

    print(build_chat(d, a.user) if a.mode == "chat" else build_image(d, a.outfit, a.scene, a.extra))


if __name__ == "__main__":
    main()
