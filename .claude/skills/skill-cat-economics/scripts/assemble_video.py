
import os
import re
import math
try:
    from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, ColorClip
except ImportError:
    from moviepy import AudioFileClip, concatenate_videoclips
    from moviepy.video.VideoClip import ColorClip, ImageClip
    try: from moviepy.video.io.ImageClip import ImageClip
    except ImportError: pass

# Config
# Assuming we run this from the 'scripts' directory or skill root? 
# Let's assume we run from skill root, so paths are relative to CWD.
# But better to use absolute paths based on __file__
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(BASE_DIR, "cat_economics.srt")
AUDIO_PATH = os.path.join(BASE_DIR, "voiceover.mp3")
FRAMES_DIR = os.path.join(BASE_DIR, "generated_frames_output")
OUTPUT_VIDEO = os.path.join(BASE_DIR, "final_video_cat_economics.mp4")

def parse_srt(file_path):
    with open(file_path, 'r', encoding='utf-8') as f: content = f.read()
    pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n((?:(?!\n\n).)*)', re.DOTALL)
    matches = pattern.findall(content)
    segments = []
    for match in matches:
        index, start_str, end_str, text = match
        h, m, s = start_str.split(':'); s, ms = s.split(',')
        start = int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0
        h, m, s = end_str.split(':'); s, ms = s.split(',')
        end = int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0
        segments.append({'start': start, 'end': end, 'text': text.strip()})
    return segments

def get_frame_path(timestamp):
    # Mapping logic from parse_and_generate_all.py: frame_{timestamp_ms}.png
    # But wait, parse_and_generate_all.py groups segments.
    # We need to find the frame that covers this timestamp.
    # The frames are named by their START time.
    # We need to find the frame with start_time <= timestamp.
    
    # Let's list all frames and sort them.
    if not os.path.exists(FRAMES_DIR):
        return None
        
    files = os.listdir(FRAMES_DIR)
    frame_files = [f for f in files if f.startswith("frame_") and f.endswith(".png")]
    
    # Parse timestamps from filenames
    frames = []
    for f in frame_files:
        # frame_12345.png
        try:
            ts_ms = int(f.split('_')[1].split('.')[0])
            frames.append({'ts': ts_ms / 1000.0, 'path': os.path.join(FRAMES_DIR, f)})
        except:
            continue
            
    frames.sort(key=lambda x: x['ts'])
    
    # Find the last frame that started before or at timestamp
    selected_frame = None
    for f in frames:
        if f['ts'] <= timestamp + 0.1: # Small buffer
            selected_frame = f['path']
        else:
            break
            
    return selected_frame

def assemble_video():
    print(f" assembling video from {SCRIPT_PATH} and {AUDIO_PATH}")
    if not os.path.exists(SCRIPT_PATH) or not os.path.exists(AUDIO_PATH):
        print("Error: Script or Audio file not found.")
        return

    segments = parse_srt(SCRIPT_PATH)
    try:
        audio = AudioFileClip(AUDIO_PATH)
    except Exception as e:
        print(f"Audio error: {e}"); return

    clips = []
    last_valid_image = None
    
    # We need to create a continuous video.
    # Strategy: iterate through time from 0 to audio duration?
    # Or iterate through SRT segments?
    # SRT segments cover the whole duration continuously (because we generated them linearly).
    
    for i, seg in enumerate(segments):
        start_time = seg['start']
        end_time = seg['end']
        duration = end_time - start_time
        
        frame_path = get_frame_path(start_time)
        
        if frame_path:
            img_clip = ImageClip(frame_path)
            last_valid_image = frame_path
            # print(f"Frame for {start_time:.2f}s: {os.path.basename(frame_path)}")
        elif last_valid_image:
            img_clip = ImageClip(last_valid_image)
        else:
            img_clip = ColorClip(size=(1920, 1080), color=(0,0,0))
            
        # Set duration
        if hasattr(img_clip, 'with_duration'): 
            img_clip = img_clip.with_duration(duration)
        else: 
            img_clip = img_clip.set_duration(duration)
            
        # Resize to 1080p if needed (Gemini images might not be 1920x1080)
        # img_clip = img_clip.resize(newsize=(1920, 1080)) # Might distort
        # Better to resize width to 1920 or height to 1080 and center?
        # Let's just assume they are reasonably sized or let moviepy handle it.
        # But to be safe for YouTube, let's resize to height 1080.
        # img_clip = img_clip.resize(height=1080) 
        # (Skip resize for now to avoid dependency issues if PIL missing etc, though PIL is there)
            
        clips.append(img_clip)

    print("Concatenating clips...")
    final_visual = concatenate_videoclips(clips, method="compose")
    
    # Trim to audio duration
    if final_visual.duration > audio.duration:
        final_visual = final_visual.subclip(0, audio.duration)
    else:
        # If visual is shorter, extend last frame? 
        # concatenate_videoclips should handle sum of durations.
        pass
        
    print("Setting audio...")
    if hasattr(final_visual, 'with_audio'): 
        final_video = final_visual.with_audio(audio)
    else: 
        final_video = final_visual.set_audio(audio)
    
    print(f"Writing video to {OUTPUT_VIDEO}...")
    final_video.write_videofile(OUTPUT_VIDEO, fps=24, codec='libx264', audio_codec='aac')
    print("Done!")

if __name__ == "__main__":
    assemble_video()
