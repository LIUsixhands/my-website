"""小魂 — 四文件角色系統共用工具（純標準庫）。"""
import re
from pathlib import Path

FILES = ("persona.md", "voice.md", "flux.md", "brain.md")


def read(char_dir, name):
    p = Path(char_dir) / name
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def block(text, name):
    """取出 <!-- BLOCK:NAME --> ... <!-- /BLOCK:NAME --> 之間的內容。"""
    if not text:
        return None
    m = re.search(
        r"<!--\s*BLOCK:%s\s*-->(.*?)<!--\s*/BLOCK:%s\s*-->" % (name, name),
        text,
        re.S,
    )
    return m.group(1).strip() if m else None


def table_rows(md):
    """把 markdown 表格解析成 list[list[str]]（跳過表頭與分隔線）。"""
    rows = []
    for line in (md or "").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or set("".join(cells)) <= set("-: "):
            continue
        if cells[0] in ("ID", "項目", "欄位", "規格"):
            continue
        rows.append(cells)
    return rows


def lookup(md, ident):
    """在表格中用第一欄 ID 找到該列，回傳最後一欄（prompt 片段）。"""
    for cells in table_rows(md):
        if cells[0].upper() == ident.upper():
            return cells[-1]
    return None


def lines_of(md):
    """把區塊內容拆成非空、非註解的行。"""
    out = []
    for line in (md or "").splitlines():
        line = line.strip()
        if line and not line.startswith("<!--"):
            out.append(line)
    return out


def has_todo(s):
    return "[TODO" in (s or "")


def strip_todo(s):
    """移除 [TODO ...] 佔位與說明行，留下真正填好的內容。"""
    s = re.sub(r"\[TODO(?:[^\[\]]|\[[^\]]*\])*\]", "", s or "")
    keep = [ln for ln in s.splitlines() if ln.strip() and not ln.strip().startswith("範例格式")]
    return "\n".join(keep).strip()
