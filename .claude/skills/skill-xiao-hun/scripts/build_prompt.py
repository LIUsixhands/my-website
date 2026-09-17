#!/usr/bin/env python3
"""把四文件組裝成可直接使用的 prompt。

聊天 / 文案用（組 persona + voice + brain）：
    python3 build_prompt.py characters/xiaoyou --mode chat
    python3 build_prompt.py characters/xiaoyou --mode chat --user @example_user

生圖用 — Midjourney 等英文標籤型工具：
    python3 build_prompt.py characters/xiaoyou --mode image --outfit W01 --scene S02
    python3 build_prompt.py characters/xiaoyou --mode image --outfit W01 --scene S02 --extra "holding a paper cup"

生圖用 — Gemini（中文白話指令，需一併上傳基準臉圖片）：
    python3 build_prompt.py characters/xiaolu --mode gemini --outfit W02 --scene S01
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charlib import block, lookup, read, strip_todo, table_rows  # noqa: E402


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

    style_bits = [c[-1] for c in table_rows(block(flux, "STYLE"))]
    style_bits = [s for s in style_bits if s and "[TODO" not in s]

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

    parts = [s.strip().rstrip(",") for s in seg if s.strip()]
    flags = [s for s in parts if s.startswith("--")]
    words = [s for s in parts if not s.startswith("--")]
    line = ", ".join(words)
    if flags:
        line += " " + " ".join(flags)
    out = ["POSITIVE:", line]
    if negative:
        out += ["", "NEGATIVE:", negative]
    out += [
        "",
        "# 生成後務必跑 flux.md §7 一致性檢查表；任一項不過就整批重生，不要挑圖。",
    ]
    return "\n".join(out)


def build_gemini(d, outfit, scene, extra):
    """Gemini 用：輸出中文白話指令，靠上傳基準臉維持一致性。"""
    flux = read(d, "flux.md")
    if not flux:
        sys.exit("✗ 缺少 flux.md")

    lock = strip_todo(block(flux, "LOCK") or "").replace("\n", "")
    if not lock:
        sys.exit("✗ flux.md 的 Identity Lock 還沒填")
    marks = strip_todo(block(flux, "KEYMARKS") or "").replace("\n", "")

    wear = lookup(block(flux, "WARDROBE"), outfit) if outfit else None
    where = lookup(block(flux, "SCENES"), scene) if scene else None
    if outfit and (not wear or "[TODO" in wear):
        sys.exit(f"✗ 衣櫃裡沒有 {outfit}（或還沒填）")
    if scene and (not where or "[TODO" in where):
        sys.exit(f"✗ 場景庫裡沒有 {scene}（或還沒填）")

    style = "，".join(c[-1] for c in table_rows(block(flux, "STYLE")) if "[TODO" not in c[-1])

    lines = [
        "【先把基準臉圖片一起上傳，再貼下面這段】",
        "",
        "請用我附上的這張照片裡的同一個人，她的臉必須完全一致。",
    ]
    if marks:
        lines.append(f"特別注意保留：{marks}。")
    lines += [
        "",
        f"人物特徵提醒：{lock}。",
        "",
        "幫我生成一張新的照片：",
    ]
    body = []
    if wear:
        body.append(f"她穿著{wear}")
    if where:
        body.append(f"場景是{where}")
    if extra:
        body.append(extra)
    lines.append("，".join(body) + "。" if body else "（請描述你要的畫面）")
    lines += [
        "",
        f"風格：{style}。",
        "",
        "重點：她的長相要是路上會遇到的普通女生，不是明星臉。"
        "保留真實的毛孔與皮膚紋理，包含左臉的痘疤。表情自然放鬆，不是擺拍。",
        "",
        "比例：直式 9:16。",
        "",
        "# 生成後務必比對基準臉，特別檢查右下巴的痣與左臉痘疤還在不在。",
        "# Gemini 常會自動美化把痘疤修掉 —— 修掉了就重生，不要將就。",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("char_dir")
    ap.add_argument("--mode", choices=("chat", "image", "gemini"), required=True)
    ap.add_argument("--user", help="chat 模式：帶入這位互動者的記憶")
    ap.add_argument("--outfit", help="image 模式：衣櫃編號，例 W01")
    ap.add_argument("--scene", help="image 模式：場景編號，例 S02")
    ap.add_argument("--extra", help="image 模式：這張圖額外的動作或道具")
    a = ap.parse_args()

    d = Path(a.char_dir)
    if not d.is_dir():
        sys.exit(f"✗ 找不到角色資料夾：{d}")

    if a.mode == "chat":
        print(build_chat(d, a.user))
    elif a.mode == "gemini":
        print(build_gemini(d, a.outfit, a.scene, a.extra))
    else:
        print(build_image(d, a.outfit, a.scene, a.extra))


if __name__ == "__main__":
    main()
