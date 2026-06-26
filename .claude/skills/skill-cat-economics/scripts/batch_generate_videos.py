import re
import json
import time
import os
# from topview_client import TopviewClient # Assuming this library is available or needs to be installed

# Use environment variables for sensitive data
API_KEY = os.getenv("TOPVIEW_API_KEY")
UID = os.getenv("TOPVIEW_UID")

def parse_scripts(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        return []

    with open(file_path, "r") as f:
        content = f.read()

    scripts = []
    # Split by "### " to separate sections
    sections = content.split("### ")[1:] # Skip the preamble

    for section in sections:
        try:
            # Extract title (first line)
            lines = section.strip().split("\n")
            title_line = lines[0]
            # Remove number "1. "
            title = re.sub(r"^\d+\.\s*", "", title_line).strip()

            # Extract script content
            # Look for **Script:** and take everything after until end or next section
            script_start_index = -1
            for i, line in enumerate(lines):
                if "**Script:**" in line:
                    script_start_index = i
                    break
            
            if script_start_index != -1:
                script_lines = lines[script_start_index+1:]
                # Filter out empty lines or lines that look like headers/separators
                script_text = "\n".join([l.strip() for l in script_lines if l.strip() and not l.startswith("###") and not l.startswith("---")])
                
                if script_text:
                    scripts.append({
                        "title": title,
                        "script": script_text
                    })
        except Exception as e:
            print(f"Error parsing section: {e}")
            continue
            
    return scripts

def split_text(text, max_chars=400):
    """
    Splits text into chunks of max_chars, preserving sentence boundaries if possible.
    """
    if len(text) <= max_chars:
        return [text]
        
    chunks = []
    current_chunk = ""
    
    # Split by sentence endings to avoid cutting mid-sentence
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 <= max_chars:
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence
            
            # Handle case where a single sentence is longer than max_chars
            while len(current_chunk) > max_chars:
                chunks.append(current_chunk[:max_chars])
                current_chunk = current_chunk[max_chars:]
                
    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks

def main():
    # Use relative path
    script_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "generated_scripts.md")
    scripts = parse_scripts(script_file)
    print(f"Found {len(scripts)} scripts.")
    
    if not API_KEY or not UID:
        print("Please set TOPVIEW_API_KEY and TOPVIEW_UID environment variables.")
        return

    # client = TopviewClient(API_KEY, UID)
    print("TopviewClient not initialized (library dependency check needed).")
    
    # ... rest of the logic

            part_title = f"{title} (Part {part_idx+1}/{len(script_parts)})"
            print(f"  Submitting {part_title} ({len(script_text)} chars)...")
            
            resp = client.process_full_flow(script_text)
            
            if resp and resp.get("code") == "200":
                result = resp.get("result", {})
                task_id = result.get("taskId")
                print(f"    Success! Task ID: {task_id}")
                tasks.append({
                    "title": part_title,
                    "task_id": task_id,
                    "status": "submitted",
                    "timestamp": time.time()
                })
            else:
                print(f"    Failed to submit task for '{part_title}'.")
                print(f"    Response: {resp}")
                tasks.append({
                    "title": part_title,
                    "status": "failed",
                    "error": str(resp),
                    "timestamp": time.time()
                })
                
            # Sleep to avoid rate limits
            time.sleep(2)
        
    # Save tasks to file
    with open("/Users/ethan/Documents/trae_projects/generation_tasks.json", "w") as f:
        json.dump(tasks, f, indent=2)
    
    print("\nBatch processing complete. Results saved to generation_tasks.json")

if __name__ == "__main__":
    main()
