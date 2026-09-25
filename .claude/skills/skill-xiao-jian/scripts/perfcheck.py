#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
perfcheck.py — AI 員工「小健」的電腦健檢工具（Sixhands Studio 資訊部）

零第三方依賴，只用 macOS 內建指令（df / sysctl / vm_stat / ps / uptime / launchctl）。

指令：
  scan                 全面健檢，出彩色報告（唯讀，永遠安全）
  disk                 磁碟容量與大戶排行
  mem                  記憶體 / swap / 行程普查
  reclaim [--path P]   列出可回收的中間檔（dry-run，**含成品守門驗證**）
  clean --confirm      真的刪除（沒有 --confirm 一律 dry-run）
  sched                launchd 排程健檢（RunAtLoad / 失效 plist / iCloud 陷阱）

🚨 硬規（寫死在程式裡，不是建議）：
  1. clean 沒有 --confirm 絕不刪任何東西
  2. 只刪白名單樣式的中間檔資料夾，永不碰單一檔案、永不碰非白名單路徑
  3. 刪任何專案的中間檔前，必須先確認該專案「tmp 以外」有成品 —— 驗不過就鎖住不刪
  4. 系統關鍵路徑（vm_bundles 等）列入永久黑名單，掃都不掃
"""
import argparse, os, re, shutil, subprocess, sys

HOME = os.path.expanduser("~")

# ── 只有這些名字的資料夾會被當成「可回收的中間檔」 ──────────────────
TMP_PATTERNS = re.compile(
    r"^(tmp|temp|tmp_v\d+|tmp_shorts\d*|tmp_thumb|.*_tmp|once\d*_tmp|nostatic_tmp)$"
)
# ── 永不觸碰（刪了會壞掉的東西）──────────────────────────────────
BLACKLIST = [
    "Library/Application Support/Claude/vm_bundles",   # Claude Code 沙箱 VM，13GB，刪了沙箱掛掉
    "Library/Application Support/Claude/claude-code",  # 執行檔本體
    "Library/Application Support/Claude/claude-code-sessions",  # 對話紀錄
    "Library/Keychains", "Library/CloudStorage", ".ssh", ".gnupg",
]
# 判定「這是成品」的副檔名
DELIVERABLE_EXT = (".mp4", ".mov", ".pdf", ".pptx", ".docx", ".png", ".jpg", ".mp3", ".wav")

C = {"r": "\033[91m", "y": "\033[93m", "g": "\033[92m", "b": "\033[1m", "d": "\033[2m", "x": "\033[0m"}
def c(s, k): return f"{C[k]}{s}{C['x']}" if sys.stdout.isatty() else str(s)

def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120).stdout.strip()
    except Exception:
        return ""

def human(kb):
    v = float(kb)
    for u in ("K", "M", "G", "T"):
        if v < 1024 or u == "T":
            return f"{v:.1f}{u}".replace(".0", "")
        v /= 1024

def light(val, warn, crit, reverse=False):
    """reverse=True 代表數字越小越糟（例如可用空間%）"""
    bad = val <= crit if reverse else val >= crit
    mid = val <= warn if reverse else val >= warn
    return ("🔴", "r") if bad else (("🟠", "y") if mid else ("🟢", "g"))


# ══════════════════════════════════════════════════════════════════
# 指標蒐集
# ══════════════════════════════════════════════════════════════════
def get_disk():
    out = sh("df -k /System/Volumes/Data | tail -1").split()
    if len(out) < 5:
        return None
    total, used, avail = int(out[1]), int(out[2]), int(out[3])
    pct = used / (used + avail) * 100
    return {"total": total, "used": used, "avail": avail, "pct": pct}

def get_swap():
    m = re.findall(r"([\d.]+)M", sh("sysctl -n vm.swapusage"))
    if len(m) < 3:
        return None
    total, used = float(m[0]), float(m[1])
    return {"total": total, "used": used, "pct": (used / total * 100) if total else 0}

def get_mem():
    free_pct = 0.0
    mp = sh("memory_pressure 2>/dev/null | grep -i 'free percentage'")
    m = re.search(r"(\d+)%", mp)
    if m:
        free_pct = float(m.group(1))
    comp = 0
    cm = re.search(r"Pages occupied by compressor:\s+(\d+)", sh("vm_stat"))
    if cm:
        comp = int(cm.group(1)) * 16384 / 1024 / 1024 / 1024  # GB (16K pages)
    total_gb = int(sh("sysctl -n hw.memsize") or 0) / 1073741824
    return {"free_pct": free_pct, "compressor_gb": comp, "total_gb": total_gb}

def get_load():
    ncpu = int(sh("sysctl -n hw.ncpu") or 1)
    m = re.search(r"load averages?:\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", sh("uptime"))
    if not m:
        return None
    l1 = float(m.group(1))
    return {"l1": l1, "l5": float(m.group(2)), "l15": float(m.group(3)),
            "ncpu": ncpu, "ratio": l1 / ncpu}

def get_procs():
    """行程普查 —— 🚨 看的是「活行程」，不是 App 裡的分頁清單。
    今日實證：封存 4 個舊 session，行程數 42→42 完全沒動。"""
    rows = [l.split(None, 1) for l in sh("ps -Aceo rss,comm").splitlines()[1:] if l.strip()]
    groups, n_claude = {}, 0
    for r in rows:
        if len(r) != 2:
            continue
        rss, name = int(r[0]), r[1]
        if name == "claude":
            n_claude += 1
        key = ("Claude" if "laude" in name else
               "Chrome" if "oogle" in name else
               "其他" if rss < 100_000 else name)
        groups[key] = groups.get(key, 0) + rss
    return {"claude_sessions": n_claude, "groups": groups}


# ══════════════════════════════════════════════════════════════════
# 可回收空間（含成品守門）
# ══════════════════════════════════════════════════════════════════
def is_blacklisted(path):
    rel = os.path.relpath(path, HOME) if path.startswith(HOME) else path
    return any(rel.startswith(b) for b in BLACKLIST)

def dir_kb(path):
    out = sh(f'du -sk "{path}" 2>/dev/null')
    try:
        return int(out.split()[0])
    except Exception:
        return 0

# 成品通常住在這些資料夾裡
FINAL_DIRS = {"final", "output", "outputs", "成品", "交付", "dist", "publish", "export", "release"}
BIG_DELIVERABLE_MB = 20   # 不在 final/ 裡的話，要夠大才算數

def has_deliverable_outside_tmp(project_root):
    """守門規則：這個專案在 tmp 之外是否存在**成品**？

    🚨 認定標準刻意收緊（2026-09-15 修）：
       早期版本把任何 >1MB 的媒體檔都當成品，結果 narration/ch3.mp3（旁白素材）
       也被當證據放行 —— 那是中間素材不是成品，守門等於形同虛設。
    現在只認兩種：
       (a) 位於 final/output/成品/… 這類交付資料夾內的檔案（>1MB）
       (b) 不在交付資料夾，但體積 ≥ 20MB 的影片／文件
    驗不過 ⇒ 該專案的中間檔一律鎖住不刪。
    """
    best = None
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if not TMP_PATTERNS.match(d) and not d.startswith(".")]
        if root[len(project_root):].count(os.sep) > 3:
            dirs[:] = []
            continue
        in_final = os.path.basename(root).lower() in FINAL_DIRS
        for f in files:
            if not f.lower().endswith(DELIVERABLE_EXT):
                continue
            fp = os.path.join(root, f)
            try:
                mb = os.path.getsize(fp) / 1_048_576
            except OSError:
                continue
            rel = os.path.relpath(fp, project_root)
            if in_final and mb >= 1:
                return True, f"{rel} ({mb:.0f}MB, 交付資料夾)"
            if mb >= BIG_DELIVERABLE_MB and (best is None or mb > best[1]):
                best = (rel, mb)
    if best:
        return True, f"{best[0]} ({best[1]:.0f}MB)"
    return False, None

def find_reclaimable(scan_root, min_mb=1):
    """回傳 [(tmp路徑, KB, 專案根, 是否放行, 成品證據)]"""
    found = []
    for root, dirs, _ in os.walk(scan_root):
        if is_blacklisted(root):
            dirs[:] = []
            continue
        if root[len(scan_root):].count(os.sep) > 4:
            dirs[:] = []
            continue
        for d in list(dirs):
            if TMP_PATTERNS.match(d):
                p = os.path.join(root, d)
                if is_blacklisted(p):
                    continue
                kb = dir_kb(p)
                if kb >= min_mb * 1024:
                    ok, ev = has_deliverable_outside_tmp(root)
                    found.append((p, kb, root, ok, ev))
                dirs.remove(d)   # 不要再往 tmp 裡面爬
    return sorted(found, key=lambda x: -x[1])

def find_caches():
    """可回收的快取（會自動重建，刪了只是下次慢一點）"""
    cands = [
        ("~/Library/Caches/com.anthropic.claudefordesktop.ShipIt", "Claude 舊安裝包殘檔"),
        ("~/.npm/_cacache", "npm 快取"),
        ("~/.cache/whisper", "Whisper 模型（會重新下載）"),
        ("~/.cache/huggingface", "HuggingFace 模型（會重新下載）"),
        ("~/.cache/uv", "uv 套件快取"),
        ("~/Library/Caches/node-gyp", "node-gyp 快取"),
        ("~/Library/Caches/Homebrew", "Homebrew 下載快取"),
    ]
    out = []
    for p, desc in cands:
        full = os.path.expanduser(p)
        if os.path.isdir(full):
            kb = dir_kb(full)
            if kb > 10 * 1024:
                out.append((full, kb, desc))
    return sorted(out, key=lambda x: -x[1])


# ══════════════════════════════════════════════════════════════════
# 報表
# ══════════════════════════════════════════════════════════════════
def cmd_scan(args):
    print(c("\n🦞 小健 — 電腦健檢報告", "b"))
    model = sh("sysctl -n hw.model")
    cpu = sh("sysctl -n machdep.cpu.brand_string")
    osv = sh("sw_vers -productVersion")
    up = sh("uptime").split(",")[0].split("up")[-1].strip()
    print(c(f"   {model} · {cpu} · macOS {osv} · 開機 {up}", "d"))
    print("=" * 62)
    reds = []

    d = get_disk()
    if d:
        free_pct = 100 - d["pct"]
        ic, col = light(free_pct, 15, 10, reverse=True)
        print(f"\n{ic} 磁碟    已用 {human(d['used'])} / 可用 {c(human(d['avail']), col)} "
              f"({d['pct']:.0f}% 滿)")
        if free_pct <= 10:
            reds.append("磁碟可用空間低於 10% — macOS 會全面變慢（swap 擠不出空間、Spotlight 反覆重建）")

    s = get_swap()
    if s:
        ic, col = light(s["pct"], 50, 80)
        used_s = c(f"{s['used']:.0f}MB", col)
        print(f"{ic} Swap    {used_s} / {s['total']:.0f}MB ({s['pct']:.0f}%)")
        if s["pct"] >= 80:
            reds.append("Swap 幾乎打滿 — 記憶體壓力會回頭吃 CPU")

    m = get_mem()
    ic, col = light(m["free_pct"], 40, 25, reverse=True)
    free_s = c(f"{m['free_pct']:.0f}%", col)
    print(f"{ic} 記憶體  可用 {free_s} / 共 {m['total_gb']:.0f}GB · 壓縮器佔 {m['compressor_gb']:.1f}GB")
    if m["free_pct"] <= 25:
        reds.append("可用記憶體低於 25%")

    l = get_load()
    if l:
        ic, col = light(l["ratio"], 0.7, 1.0)
        l1_s = c(f"{l['l1']:.2f}", col)
        print(f"{ic} CPU     load {l1_s} / {l['ncpu']} 核 "
              f"= {l['ratio']*100:.0f}% · 5分 {l['l5']:.2f} · 15分 {l['l15']:.2f}")
        if l["ratio"] >= 1.0:
            reds.append(f"CPU 超載（load {l['l1']:.2f} > {l['ncpu']} 核）")

    p = get_procs()
    print(f"\n{c('記憶體大戶', 'b')}")
    for k, v in sorted(p["groups"].items(), key=lambda x: -x[1])[:6]:
        if k != "其他":
            print(f"   {human(v):>8}  {k}")
    if p["claude_sessions"] > 8:
        msg = c(f"claude 活行程 {p['claude_sessions']} 個", "y")
        print(f"\n🟠 {msg} — 超過 8 個就該重開 App")
        reds.append(f"Claude 開了 {p['claude_sessions']} 個工作階段")
    else:
        print(f"\n🟢 claude 活行程 {p['claude_sessions']} 個")

    print("\n" + "=" * 62)
    if reds:
        print(c(f"⚠️  {len(reds)} 項需要處理：", "r"))
        for i, r in enumerate(reds, 1):
            print(f"   {i}. {r}")
        print(c("\n   下一步：perfcheck.py reclaim   （列出可回收空間，不會刪東西）", "d"))
    else:
        print(c("✅ 各項指標都在健康範圍", "g"))
    print()


def cmd_disk(args):
    d = get_disk()
    print(c("\n📀 磁碟", "b"))
    if d:
        print(f"   已用 {human(d['used'])} / 可用 {human(d['avail'])} ({d['pct']:.0f}% 滿)\n")
    print(c("家目錄大戶 Top 12", "b"))
    for line in sh(f'du -sk "{HOME}"/* 2>/dev/null | sort -rn | head -12').splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            print(f"   {human(parts[0]):>8}  {parts[1].replace(HOME + '/', '')}")
    print()


def cmd_mem(args):
    m, s, p = get_mem(), get_swap(), get_procs()
    print(c("\n🧠 記憶體", "b"))
    print(f"   實體 {m['total_gb']:.0f}GB · 可用 {m['free_pct']:.0f}% · 壓縮器 {m['compressor_gb']:.1f}GB")
    if s:
        print(f"   Swap {s['used']:.0f}MB / {s['total']:.0f}MB ({s['pct']:.0f}%)")
        print(c("   （swap 總量會隨壓力自動伸縮；壓力解除後 macOS 會自己把 swap 檔收掉，磁碟因此會多出空間）", "d"))
    print(f"\n{c('分組佔用', 'b')}")
    for k, v in sorted(p["groups"].items(), key=lambda x: -x[1])[:10]:
        print(f"   {human(v):>8}  {k}")
    print(f"\n   claude 活行程：{p['claude_sessions']} 個")
    print(c("   🚨 封存舊工作階段不等於釋放記憶體 —— 吃記憶體的是活行程。", "d"))
    print(c("      要一次拿回全部，唯一有效做法是 Cmd+Q 完全結束 Claude App 再重開。", "d"))
    print(c("      對話都存在硬碟上，重開後從側邊欄點回去即可，不會掉內容。\n", "d"))


def cmd_reclaim(args):
    root = os.path.expanduser(args.path) if args.path else os.path.join(HOME, "Desktop")
    print(c(f"\n♻️  可回收空間掃描：{root}", "b"))
    print(c("   （這是 dry-run，不會刪任何東西）", "d"))
    print("=" * 62)

    items = find_reclaimable(root, args.min_mb)
    ok_items = [i for i in items if i[3]]
    blocked = [i for i in items if not i[3]]

    if ok_items:
        total = sum(i[1] for i in ok_items)
        print(f"\n{c('✅ 可安全回收的中間檔', 'g')}（成品已驗證存在於 tmp 之外）")
        for p, kb, proj, _, ev in ok_items[:30]:
            print(f"   {human(kb):>8}  {p.replace(HOME + '/', '')}")
            print(c(f"            └ 成品證據：{ev}", "d"))
        print(f"\n   {c('小計 ' + human(total), 'g')}")

    if blocked:
        print(f"\n{c('🔒 鎖住不刪', 'y')}（在 tmp 之外找不到成品，刪了可能真的沒了）")
        for p, kb, proj, _, _ in blocked[:15]:
            print(f"   {human(kb):>8}  {p.replace(HOME + '/', '')}")
        print(c("            → 要刪必須人工確認成品位置，小健不自己解鎖", "d"))

    caches = find_caches()
    if caches:
        print(f"\n{c('🟡 快取（刪了會自動重建，只是下次慢一點）', 'y')}")
        for p, kb, desc in caches:
            print(f"   {human(kb):>8}  {desc}")
            print(c(f"            {p.replace(HOME + '/', '~/')}", "d"))

    if not ok_items and not caches:
        print(c("\n   沒有找到可回收的中間檔 —— 很乾淨。", "g"))
    else:
        print(c(f"\n   要真的刪除，跑：perfcheck.py clean --path {args.path or '~/Desktop'} --confirm", "d"))
    print()


def cmd_clean(args):
    root = os.path.expanduser(args.path) if args.path else os.path.join(HOME, "Desktop")
    items = [i for i in find_reclaimable(root, args.min_mb) if i[3]]

    if not items:
        print(c("\n沒有通過守門驗證的可刪項目。\n", "y"))
        return

    total = sum(i[1] for i in items)
    print(c(f"\n{'🗑  刪除' if args.confirm else '🔍 DRY-RUN（不會刪）'} — {len(items)} 個資料夾，共 {human(total)}", "b"))
    print("=" * 62)

    if not args.confirm:
        for p, kb, _, _, ev in items:
            print(f"   {human(kb):>8}  {p.replace(HOME + '/', '')}")
        print(c(f"\n   ⚠️  這是 dry-run。要真的刪，加 --confirm\n", "y"))
        return

    freed = 0
    for p, kb, proj, _, ev in items:
        ok, ev2 = has_deliverable_outside_tmp(proj)   # 刪之前再驗一次
        if not ok:
            print(f"   {c('🔒 跳過', 'y')}  {p.replace(HOME + '/', '')} — 複驗失敗")
            continue
        try:
            shutil.rmtree(p)
            freed += kb
            print(f"   {c('✔', 'g')} {human(kb):>8}  {p.replace(HOME + '/', '')}")
        except Exception as e:
            print(f"   {c('✘', 'r')} {p.replace(HOME + '/', '')} — {e}")
    d = get_disk()
    print(f"\n   {c('已釋放 ' + human(freed), 'g')}"
          + (f" · 目前可用 {human(d['avail'])}" if d else ""))
    print()


def cmd_sched(args):
    print(c("\n⏰ launchd 排程健檢", "b"))
    print("=" * 62)
    d = os.path.join(HOME, "Library/LaunchAgents")
    if not os.path.isdir(d):
        print("   找不到 LaunchAgents 資料夾\n")
        return
    plists = sorted(os.listdir(d))
    active = [f for f in plists if f.endswith(".plist")]
    off = [f for f in plists if not f.endswith(".plist")]
    print(f"\n   啟用中 {len(active)} 個 · 停用/備份 {len(off)} 個\n")

    warn = []
    for f in active:
        p = os.path.join(d, f)
        body = sh(f'plutil -p "{p}" 2>/dev/null')
        label = f.replace(".plist", "")
        issues = []
        if "StartCalendarInterval" in body and '"RunAtLoad" => 1' not in body:
            issues.append("定時排程缺 RunAtLoad（GUI 未登入那刻會整個不補跑）")
        prog = re.findall(r'"(?:Program|ProgramArguments)"[^\n]*\n?\s*(?:0 => )?"([^"]+)"', body)
        for x in prog:
            if x.startswith("/") and not os.path.exists(x):
                issues.append(f"指向的檔案不存在：{x}")
                break
        if "/Desktop/" in body or "/Documents/" in body:
            issues.append("路徑在 iCloud 同步區（可能噴 EDEADLK 間歇卡死）")
        if issues:
            warn.append((label, issues))
            print(f"   🟠 {label}")
            for i in issues:
                print(c(f"        └ {i}", "y"))
    if not warn:
        print(c("   🟢 啟用中的排程都沒有明顯問題", "g"))
    print()


def main():
    ap = argparse.ArgumentParser(prog="perfcheck.py", description="小健 — 電腦健檢工具")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("scan")
    sub.add_parser("disk")
    sub.add_parser("mem")
    sub.add_parser("sched")
    for name in ("reclaim", "clean"):
        sp = sub.add_parser(name)
        sp.add_argument("--path", default=None)
        sp.add_argument("--min-mb", type=int, default=1, dest="min_mb")
        if name == "clean":
            sp.add_argument("--confirm", action="store_true")
    a = ap.parse_args()
    fn = {"scan": cmd_scan, "disk": cmd_disk, "mem": cmd_mem,
          "reclaim": cmd_reclaim, "clean": cmd_clean, "sched": cmd_sched}.get(a.cmd or "scan")
    fn(a if a.cmd else ap.parse_args(["scan"]))

if __name__ == "__main__":
    main()
