#!/usr/bin/env python3
"""建立一個新的虛擬人物角色資料夾（四文件 + 工作區）。

用法：
    python3 init_character.py "小柚" --slug xiaoyou --out characters/
"""
import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charlib import FILES  # noqa: E402

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

README = """# {name}（{slug}）

AI 生成虛擬人物 — 建立於 {today}

## 四文件

| 文件 | 管什麼 | 崩壞時的症狀 |
|------|-------|------------|
| persona.md | 她是誰 | 講出不符合背景的話 |
| voice.md | 她怎麼講話 | 觀眾覺得「今天怪怪的」 |
| flux.md | 她長什麼樣 | 兩張圖看起來不同人 |
| brain.md | 她記得誰 | 忘記聊過的事、或記太多變恐怖 |

## 上線前檢查

- [ ] 四份文件的 `[TODO]` 全部填完
- [ ] `python3 ../../scripts/check_consistency.py .` 全綠
- [ ] flux.md 產 10 張測試圖，過一致性檢查表
- [ ] AI 揭露聲明已放上所有平台 bio
- [ ] voice.md §7 互動邊界的固定說法背熟（含「你是真人嗎」的回答）
- [ ] brain.md §6 關係深度上限已設定，團隊知道誰負責處理紅線事件

## 工作區

- `drafts/` — 產出的文案草稿，check_consistency.py 會掃這裡的禁用詞
- `memory/` — 互動者記憶檔（若量大，從 brain.md §3 拆出來）
- `images/` — 生成圖與一致性檢查紀錄
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="角色中文名")
    ap.add_argument("--slug", required=True, help="英文代號，用作資料夾名")
    ap.add_argument("--out", default="characters", help="輸出根目錄")
    ap.add_argument("--force", action="store_true", help="覆蓋既有資料夾")
    a = ap.parse_args()

    dest = Path(a.out) / a.slug
    if dest.exists() and not a.force:
        sys.exit(f"✗ {dest} 已存在。加 --force 才會覆蓋。")

    for sub in ("drafts", "memory", "images"):
        (dest / sub).mkdir(parents=True, exist_ok=True)

    for f in FILES:
        shutil.copy(TEMPLATES / f, dest / f)

    (dest / "README.md").write_text(
        README.format(name=a.name, slug=a.slug, today=date.today().isoformat()),
        encoding="utf-8",
    )

    print(f"✓ 已建立角色：{a.name}")
    print(f"  {dest}/")
    for f in ("README.md",) + FILES:
        print(f"    {f}")
    print("\n下一步：先填 persona.md（身份憲法），再填 voice.md（語言指紋）。")
    print("順序不能反 —— 語氣要從身份長出來。")


if __name__ == "__main__":
    main()
