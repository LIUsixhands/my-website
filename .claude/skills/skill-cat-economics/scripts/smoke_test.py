"""小路測試片 — 不打任何 API 的產線煙霧測試。

正式產線（步驟三～六）要燒 Minimax + Gemini 的額度才跑得完，改一行程式就重跑一次太貴。
這支只驗證「不用花錢的那半條路」：

    步驟四 SRT 解析 → 畫面對時間軸 → 步驟六 ffmpeg 合成 MP4

配音（步驟三）與 Gemini 生圖（步驟五）全部跳過，畫面改用 assets/ 既有的 5 張風格參考圖
輪播，所以產出的是一支「無聲、畫面是佔位圖，但時間軸與規格都跟正式片一模一樣」的測試片。
拿它來確認環境沒壞、SRT 格式沒錯、ffmpeg 出得了 1080x1920，再去燒 API 跑正式的。

用法：
    python scripts/smoke_test.py                          # 用 cat_economics.srt 跑 30 秒
    python scripts/smoke_test.py --srt examples/demo_input.srt --seconds 15
"""
import argparse
import os
import re
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

# 刻意與 assemble_video.py 用同一支 regex：測試要測的就是正式產線那套解析邏輯，
# 這裡若寬鬆一點，正式跑才爆的格式問題就會被這支測試漏掉。
SRT_PATTERN = re.compile(
    r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n((?:(?!\n\n).)*)',
    re.DOTALL)


def to_seconds(timestamp):
    hours, minutes, rest = timestamp.split(':')
    seconds, millis = rest.split(',')
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000.0


def parse_srt(path):
    with open(path, encoding='utf-8') as f:
        content = f.read()
    return [{'start': to_seconds(start), 'end': to_seconds(end), 'text': text.strip()}
            for _, start, end, text in SRT_PATTERN.findall(content)]


def find_ffmpeg():
    """優先用系統 ffmpeg，沒有就退回 imageio-ffmpeg 內附的那顆。"""
    from shutil import which
    exe = which('ffmpeg')
    if exe:
        return exe
    try:
        import imageio_ffmpeg
    except ImportError:
        sys.exit("找不到 ffmpeg。請安裝系統 ffmpeg，或 pip install imageio-ffmpeg")
    return imageio_ffmpeg.get_ffmpeg_exe()


def build_timeline(segments, total_seconds, frames, slot_seconds):
    """照「黃金 30 秒每 3 秒一張」的節奏規定切 slot，圖片輪播補位。"""
    slots = []
    elapsed = 0.0
    while elapsed < total_seconds:
        duration = min(slot_seconds, total_seconds - elapsed)
        seg = next((s for s in segments if s['start'] <= elapsed < s['end']), segments[0])
        slots.append({
            'image': frames[len(slots) % len(frames)],
            'duration': duration,
            'text': seg['text'],
        })
        elapsed += duration
    return slots


def main():
    parser = argparse.ArgumentParser(description="貓咪經濟學產線煙霧測試（不打 API）")
    parser.add_argument('--srt', default=os.path.join(BASE_DIR, 'cat_economics.srt'),
                        help="要驗證的 SRT（預設 cat_economics.srt）")
    parser.add_argument('--seconds', type=float, default=30.0, help="測試片長度，預設 30 秒")
    parser.add_argument('--slot', type=float, default=3.0, help="每張畫面秒數，預設 3 秒")
    parser.add_argument('--frames', default=ASSETS_DIR, help="佔位圖目錄，預設 assets/")
    parser.add_argument('--out', default=os.path.join(BASE_DIR, 'smoke_test_output.mp4'))
    args = parser.parse_args()

    segments = parse_srt(args.srt)
    if not segments:
        sys.exit(f"SRT 解析出 0 段：{args.srt}\n"
                 f"  常見兩個原因：時間碼不是 HH:MM:SS,mmm，或條目之間少了空行。")
    print(f"[1/4] SRT 解析：{os.path.basename(args.srt)} → {len(segments)} 段，"
          f"總長 {segments[-1]['end']:.1f}s")

    frames = sorted(os.path.join(args.frames, f)
                    for f in os.listdir(args.frames) if f.endswith('.png'))
    if not frames:
        sys.exit(f"{args.frames} 裡沒有 PNG 佔位圖")
    print(f"[2/4] 佔位圖：{len(frames)} 張")

    slots = build_timeline(segments, args.seconds, frames, args.slot)
    print(f"[3/4] 時間軸：{len(slots)} 個 slot / {args.seconds:.0f}s，每 {args.slot:.0f} 秒一張")
    for i, slot in enumerate(slots, 1):
        print(f"      {i:>2}. {slot['duration']:.1f}s  {os.path.basename(slot['image'])}  "
              f"「{slot['text'][:18]}…」")

    concat_path = args.out + '.concat.txt'
    with open(concat_path, 'w', encoding='utf-8') as f:
        for slot in slots:
            f.write(f"file '{slot['image']}'\nduration {slot['duration']}\n")
        # concat demuxer 會忽略最後一個 duration，要把最後一張再寫一次它才算得對
        f.write(f"file '{slots[-1]['image']}'\n")

    cmd = [find_ffmpeg(), '-y', '-f', 'concat', '-safe', '0', '-i', concat_path,
           '-vf', 'scale=1080:1920:force_original_aspect_ratio=decrease,'
                  'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=white,fps=24',
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', args.out]
    result = subprocess.run(cmd, capture_output=True, text=True)
    os.remove(concat_path)
    if result.returncode != 0:
        print(result.stderr[-2000:], file=sys.stderr)
        sys.exit("ffmpeg 合成失敗")

    print(f"[4/4] 合成完成：{args.out} ({os.path.getsize(args.out) / 1024:.0f} KB) "
          f"1080x1920 / 24fps / 無聲")


if __name__ == '__main__':
    main()
