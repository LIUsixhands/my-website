
import os
import math
try:
    from moviepy.editor import AudioFileClip
except ImportError:
    from moviepy import AudioFileClip

# Config
AUDIO_PATH = "../voiceover.mp3"
SCRIPT_PATH = "../cat_economics_script.txt"
OUTPUT_SRT = "../cat_economics.srt"

def format_timestamp(seconds):
    """Converts seconds to SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def generate_srt():
    # 1. Get Audio Duration
    base_dir = os.path.dirname(os.path.abspath(__file__))
    audio_full_path = os.path.join(base_dir, AUDIO_PATH)
    script_full_path = os.path.join(base_dir, SCRIPT_PATH)
    output_full_path = os.path.join(base_dir, OUTPUT_SRT)

    print(f"Loading audio: {audio_full_path}")
    try:
        audio = AudioFileClip(audio_full_path)
        total_duration = audio.duration
        print(f"Audio Duration: {total_duration:.2f}s")
    except Exception as e:
        print(f"Error loading audio: {e}")
        return

    # 2. Read Script
    with open(script_full_path, 'r', encoding='utf-8') as f:
        # Read lines and filter empty ones
        lines = [line.strip() for line in f.readlines() if line.strip()]

    # 3. Calculate Total Characters
    total_chars = sum(len(line) for line in lines)
    print(f"Total Characters: {total_chars}")

    # 4. Generate SRT segments
    srt_content = ""
    current_time = 0.0
    
    for i, line in enumerate(lines):
        # Calculate duration for this line based on character count
        # Adding a small buffer logic? No, simple linear distribution is safest for estimation.
        line_duration = (len(line) / total_chars) * total_duration
        
        start_time = current_time
        end_time = current_time + line_duration
        
        # Format SRT entry
        srt_entry = f"{i+1}\n"
        srt_entry += f"{format_timestamp(start_time)} --> {format_timestamp(end_time)}\n"
        srt_entry += f"{line}\n\n"
        
        srt_content += srt_entry
        current_time = end_time

    # 5. Write to file
    with open(output_full_path, 'w', encoding='utf-8') as f:
        f.write(srt_content)
    
    print(f"SRT generated at: {output_full_path}")

if __name__ == "__main__":
    generate_srt()
