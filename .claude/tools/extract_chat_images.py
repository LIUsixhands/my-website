#!/usr/bin/env python3
"""
extract_chat_images.py — 從 Claude Code session log 救出 chat 內嵌圖片
用法：python3 .claude/tools/extract_chat_images.py [N] [outdir]
  N      : 取最後 N 張（預設 5）
  outdir : 輸出目錄（預設 /tmp/chat_imgs）
背景：Claude Code on web 環境，「貼圖到對話」的照片不會落地成檔案，
      但會 base64 嵌在 session log 裡。本工具直接從 log 救出來。
作者：助哥團隊 · Sixhands Studio（2026-06-09 首次解鎖）
"""
import json, base64, os, sys, glob

def find_session_log():
    sid = os.environ.get('CLAUDE_CODE_SESSION_ID')
    base = '/root/.claude/projects'
    # 優先用環境變數對應檔
    if sid:
        for d in glob.glob(f'{base}/*'):
            p = f'{d}/{sid}.jsonl'
            if os.path.exists(p): return p
    # 退而求其次：找最新的 jsonl
    cands = sorted(glob.glob(f'{base}/*/*.jsonl'), key=os.path.getmtime, reverse=True)
    return cands[0] if cands else None

def extract(n=5, outdir='/tmp/chat_imgs'):
    log = find_session_log()
    if not log:
        print("[!] 找不到 session log。檢查 /root/.claude/projects/")
        return []
    print(f"[+] 來源：{log}")
    imgs = []
    with open(log, encoding='utf-8', errors='ignore') as f:
        for li, line in enumerate(f):
            try:
                d = json.loads(line)
                if d.get('type') != 'user': continue
                content = d.get('message', {}).get('content', [])
                if not isinstance(content, list): continue
                for ci, item in enumerate(content):
                    if isinstance(item, dict) and item.get('type') == 'image':
                        src = item.get('source', {})
                        if src.get('type') == 'base64':
                            imgs.append((d.get('timestamp', ''), li, ci,
                                         src.get('media_type', ''),
                                         src.get('data', '')))
            except Exception:
                pass
    print(f"[+] log 內共找到 {len(imgs)} 張 user 上傳圖片")
    os.makedirs(outdir, exist_ok=True)
    saved = []
    for i, (ts, li, ci, mime, data) in enumerate(imgs[-n:]):
        ext = 'jpg' if 'jpeg' in mime else ('png' if 'png' in mime else 'bin')
        out = f'{outdir}/photo_{i+1}.{ext}'
        with open(out, 'wb') as fo:
            fo.write(base64.b64decode(data))
        kb = os.path.getsize(out) // 1024
        print(f"  → {out}  ({kb} KB, ts={ts[:19]}, line {li})")
        saved.append(out)
    return saved

if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    outdir = sys.argv[2] if len(sys.argv) > 2 else '/tmp/chat_imgs'
    extract(n, outdir)
