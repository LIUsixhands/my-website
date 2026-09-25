# -*- coding: utf-8 -*-
"""小美・字型解析與缺字檢查（繁體優先，永不落到 SC）"""
import glob, os
from PIL import ImageFont

# 候選字型檔（macOS）。順序即優先序。
_CANDIDATES = [
    "/System/Library/AssetsV2/com_apple_MobileAsset_Font7/*/AssetData/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/AssetsV2/com_apple_MobileAsset_Font7/*/AssetData/Hiragino_Sans_CNS.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/LucidaGrande.ttc",
    "/Library/Fonts/*.ttc", "/Library/Fonts/*.otf", "/Library/Fonts/*.ttf",
    os.path.expanduser("~/Library/Fonts/*.ttc"),
    os.path.expanduser("~/Library/Fonts/*.otf"),
    os.path.expanduser("~/Library/Fonts/*.ttf"),
]

# 角色 -> 想要的 (family 關鍵字, style 關鍵字) 由前往後找
_ROLES = {
    "heavy":   [("PingFang TC", "Semibold"), ("PingFang TC", "Medium"), ("Heiti TC", "Medium"), ("Noto Sans", "Bold")],
    "bold":    [("PingFang TC", "Medium"), ("Heiti TC", "Medium"), ("Noto Sans", "Bold")],
    "regular": [("PingFang TC", "Regular"), ("Heiti TC", "Light"), ("Noto Sans", "Regular")],
    "light":   [("PingFang TC", "Light"), ("Heiti TC", "Light")],
    "serif":   [("Songti TC", "Bold"), ("Songti TC", "Regular")],
    "serif_r": [("Songti TC", "Regular"), ("Songti TC", "Light")],
    # 族語羅馬字（含 ʉ ʼ ʔ）：⚠️ PingFang TC 缺 U+0289 ʉ，實測會變空白 → 一律走拉丁擴充完整的字型
    "latin":      [("Helvetica Neue", "Regular"), ("Noto Sans", "Regular"), ("Lucida Grande", "Regular")],
    "latin_bold": [("Helvetica Neue", "Bold"), ("Noto Sans", "Bold"), ("Lucida Grande", "Bold")],
}

_cache = {}


def _iter_faces():
    for pat in _CANDIDATES:
        for path in sorted(glob.glob(pat)):
            for idx in range(0, 12):
                try:
                    f = ImageFont.truetype(path, 20, index=idx)
                except Exception:
                    break
                fam, sty = f.getname()
                # 🚫 繁體專案一律不吃 SC（缺繁體字會渲染成空白）
                if "SC" in (fam or "").split():
                    continue
                yield path, idx, fam or "", sty or ""


def resolve(role="regular"):
    """回傳 (path, index)。找不到就退回第一個可用繁體字面。"""
    if role in _cache:
        return _cache[role]
    faces = list(_iter_faces())
    for want_fam, want_sty in _ROLES.get(role, _ROLES["regular"]):
        for path, idx, fam, sty in faces:
            if want_fam.lower() in fam.lower() and want_sty.lower() == sty.lower():
                _cache[role] = (path, idx)
                return _cache[role]
    for want_fam, _ in _ROLES.get(role, _ROLES["regular"]):
        for path, idx, fam, sty in faces:
            if want_fam.lower() in fam.lower():
                _cache[role] = (path, idx)
                return _cache[role]
    path, idx, fam, sty = faces[0]
    _cache[role] = (path, idx)
    return _cache[role]


def load(role="regular", size=48):
    path, idx = resolve(role)
    return ImageFont.truetype(path, size, index=idx)


def check_glyphs(text, role="regular"):
    """缺字檢查：回傳該字型畫不出來的字元清單（族語 ʉ、生僻字最常中）"""
    from fontTools.ttLib import TTFont, TTCollection
    path, idx = resolve(role)
    try:
        tt = TTCollection(path).fonts[idx] if path.lower().endswith(".ttc") else TTFont(path)
    except Exception:
        return []  # 無法解析就不誤報
    cmap = set()
    for t in tt["cmap"].tables:
        cmap |= set(t.cmap.keys())
    missing = []
    for ch in text:
        if ch in "\n\r\t ":
            continue
        if ord(ch) not in cmap and ch not in missing:
            missing.append(ch)
    return missing


if __name__ == "__main__":
    for r in _ROLES:
        p, i = resolve(r)
        print(f"{r:8s} -> {os.path.basename(p)}[{i}] {ImageFont.truetype(p,20,index=i).getname()}")
    print("缺字測試(族語 ʉ / 生僻字):", check_glyphs("Pangcah ilisin ʉ 'a 龘", "heavy"))
