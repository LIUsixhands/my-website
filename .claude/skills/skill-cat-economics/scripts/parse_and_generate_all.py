import os
import re
import sys
import time
from google import genai
from google.genai import types

# Using 'gemini-3-pro-image-preview' as requested
MODEL_NAME = "gemini-3-pro-image-preview"

# Define relative paths to style references (relative to this script)
STYLE_REF_REL_PATHS = [
    "../assets/frame_002_4.png",
    "../assets/frame_003_6.png",
    "../assets/frame_004_8.png",
    "../assets/frame_005_10.png",
    "../assets/frame_006_12.png"
]

def get_style_ref_paths():
    """Resolves relative paths to absolute paths based on the script location."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return [os.path.join(base_dir, p) for p in STYLE_REF_REL_PATHS]

# Input/Output Configuration
# Default to the example SRT in the skill folder if not provided
DEFAULT_SRT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../examples/demo_input.srt")
SRT_FILE = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRT_PATH
# Use a path relative to the script or the skill root, not cwd which varies
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "generated_frames_output")

def parse_time_str(time_str):
    # Format: 00:00:00,200
    try:
        h, m, s = time_str.split(':')
        s, ms = s.split(',')
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0
    except ValueError:
        return 0.0

def parse_srt(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Normalize newlines
    content = content.replace('\r\n', '\n')
    
    # Split by double newlines
    blocks = re.split(r'\n\s*\n', content.strip())
    
    segments = []
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            idx = lines[0].strip()
            time_line = lines[1].strip()
            text = " ".join([l.strip() for l in lines[2:]])
            
            if '-->' in time_line:
                start_str, end_str = time_line.split(' --> ')
                segments.append({
                    "index": idx,
                    "start": parse_time_str(start_str),
                    "end": parse_time_str(end_str),
                    "text": text
                })
    return segments

def generate_image(client, prompt, output_path):
    print(f"Generating image for prompt: {prompt[:50]}...")
    
    contents = [prompt]
    
    # Add style references
    style_ref_paths = get_style_ref_paths()
    for ref_path in style_ref_paths:
        if os.path.exists(ref_path):
            try:
                with open(ref_path, "rb") as f:
                    image_bytes = f.read()
                # Create a Part object for the image
                image_part = types.Part(
                    inline_data=types.Blob(
                        mime_type="image/png",
                        data=image_bytes
                    )
                )
                contents.append(image_part)
                print("Attached style reference image.")
            except Exception as e:
                print(f"Failed to load style reference: {e}")
            
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"]
            )
        )
        
        # Save image
        # Assuming single candidate, single part
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    with open(output_path, 'wb') as f:
                        f.write(part.inline_data.data)
                    print(f"Saved to {output_path}")
                    return True
        print("No image data found in response.")
        return False
    except Exception as e:
        print(f"Error generating image: {e}")
        return False

def main():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Please set GOOGLE_API_KEY environment variable.")
        return

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    client = genai.Client(api_key=api_key)
    segments = parse_srt(SRT_FILE)
    print(f"Parsed {len(segments)} segments.")
    
    # Generate images
    grouped_segments = []
    current_group = {"text": [], "start": None, "end": None, "first_segment_index": None}
    
    # Frequency Control: Average 3-5 seconds per image
    MIN_DURATION = 3.0
    MAX_DURATION = 5.0
    
    for i, seg in enumerate(segments):
        if current_group["start"] is None:
            current_group["start"] = seg["start"]
            current_group["first_segment_index"] = i
        
        current_group["end"] = seg["end"]
        current_group["text"].append(seg["text"])
        
        duration = current_group["end"] - current_group["start"]
        
        # Check if we should close the group
        if duration >= MIN_DURATION:
            grouped_segments.append({
                "start": current_group["start"],
                "end": current_group["end"],
                "text": " ".join(current_group["text"]),
                "original_index": current_group["first_segment_index"]
            })
            current_group = {"text": [], "start": None, "end": None, "first_segment_index": None}
            
    # Handle remainder
    if current_group["start"] is not None:
        grouped_segments.append({
            "start": current_group["start"],
            "end": current_group["end"],
            "text": " ".join(current_group["text"]),
            "original_index": current_group["first_segment_index"]
        })

    print(f"Grouped {len(segments)} segments into {len(grouped_segments)} visual scenes (Target: 3-5s).")

    # Quality Control Trackers
    accumulated_duration = 0.0
    first_checkpoint_passed = False
    generated_count = 0

    for i, scene in enumerate(grouped_segments):
        # Naming convention: frame_TIMESTAMP.png (using start timestamp in ms)
        timestamp_ms = int(scene['start'] * 1000)
        filename = f"frame_{timestamp_ms}.png"
        filepath = os.path.join(OUTPUT_DIR, filename)
        
        # --- Checkpoint 1: First 30 Seconds ---
        scene_duration = scene['end'] - scene['start']
        accumulated_duration += scene_duration
        
        if not first_checkpoint_passed and accumulated_duration >= 30.0:
            print(f"\n[CHECKPOINT] You have generated the first {accumulated_duration:.1f} seconds of content.")
            print("Please check the generated images in the output folder.")
            input("Press Enter to continue generation if quality is satisfactory...")
            first_checkpoint_passed = True
            
        # --- Checkpoint 2: Every 50 Images ---
        if generated_count > 0 and generated_count % 50 == 0:
            print(f"\n[CHECKPOINT] Generated {generated_count} images so far.")
            print("Please batch check the quality.")
            input("Press Enter to continue...")

        if os.path.exists(filepath):
            print(f"Skipping {filename} (exists)")
            continue
            
        # Construct Prompt with CONSTRAINT
        prompt = f"""
        Style: Follow the visual style of the provided reference images strictly.
        Subject: {scene['text']}
        Context: A visual explanation of economics using cats. 
        'Meow Country' cats are lazy, consumers. 'Can Republic' cats are industrious producers.
        Make it simple and iconic.
        CONSTRAINT: If there is text in the image, strictly limit it to under 40 Chinese characters.
        """
        
        success = generate_image(client, prompt, filepath)
        if success:
            generated_count += 1
            time.sleep(4) # Avoid rate limits
        else:
            print("Stopping due to error.")
            break

if __name__ == "__main__":
    main()
