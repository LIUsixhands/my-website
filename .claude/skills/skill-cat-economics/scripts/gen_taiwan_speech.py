import os
import json
import urllib.request
import urllib.error
import sys

# ==========================================
# 配置信息
# ==========================================
# 從環境變量讀取 API Key 和 Group ID
API_KEY = os.getenv("MINIMAX_API_KEY")
GROUP_ID = os.getenv("MINIMAX_GROUP_ID")

API_BASE_URL = "https://api.minimax.chat/v1"
# 使用 speech-01 以匹配 female-shaonv 音色
MODEL_SPEECH = "speech-01" 

def make_request(endpoint, method="POST", data=None):
    if not API_KEY:
        print("❌ 錯誤: 未找到 MINIMAX_API_KEY 環境變量。")
        return None

    # 將 Group ID 添加到 URL 查詢參數中
    if "?" in endpoint:
        url = f"{API_BASE_URL}{endpoint}&GroupId={GROUP_ID}"
    else:
        url = f"{API_BASE_URL}{endpoint}?GroupId={GROUP_ID}"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    if data:
        json_data = json.dumps(data).encode('utf-8')
    else:
        json_data = None
        
    req = urllib.request.Request(url, data=json_data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"❌ API 請求失敗: {e.code} - {error_body}")
        return None
    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
        return None

def generate_speech(text, voice_id="female-shaonv"):
    print(f"🎙️ 正在生成語音...")
    print(f"📝 文本: {text[:50]}...")
    print(f"🗣️ 聲音 ID: {voice_id}")
    
    # 根據模型調整 payload
    payload = {
        "model": MODEL_SPEECH,
        "text": text,
        "voice_id": voice_id, # speech-01 使用 voice_id
        "speed": 1.0,
        "vol": 1.0,
        "pitch": 0
    }
    
    # 調用 T2A V1 (text_to_speech)
    response = make_request("/text_to_speech", data=payload)
    
    if not response:
        return

    # 檢查響應
    if "base_resp" in response and response["base_resp"]["status_code"] == 0:
        # T2A V1 通常在 content 或 audio_file 中返回
        # 注意：Minimax T2A V1 API 直接返回二進制流，但這裡 make_request 嘗試解析 JSON
        # 如果是 V1，make_request 的 json.loads 可能會失敗，因為它返回的是 audio/mpeg
        pass
    
    # 修正：make_request 假設是 JSON，但 speech-01 如果成功會直接返回音頻流
    # 我們需要重寫 make_request 來處理二進制響應，或者在此處使用 requests 庫更簡單
    # 為了保持依賴最少，我們修改上面的邏輯，但為了穩定性，這裡改用 requests (如果環境有) 或者 urllib 的正確處理
    
    # 由於 make_request 已經讀取了 body，如果它是二進制，decode('utf-8') 會失敗。
    # 讓我們重新實現一個簡單的 generate 函數，不使用上面的 make_request
    pass

# 重寫生成函數以支持二進制響應
def generate_speech_robust(text, voice_id="female-shaonv", output_file="voiceover.mp3"):
    if not API_KEY or not GROUP_ID:
        print("❌ 錯誤: 未設置 MINIMAX_API_KEY 或 MINIMAX_GROUP_ID。")
        return

    url = f"{API_BASE_URL}/text_to_speech?GroupId={GROUP_ID}"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    payload = {
        "model": MODEL_SPEECH,
        "text": text,
        "voice_id": voice_id,
        "speed": 1.0,
        "vol": 1.0,
        "pitch": 0
    }

    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        with urllib.request.urlopen(req) as response:
            if response.getheader("Content-Type") == "audio/mpeg":
                audio_content = response.read()
                with open(output_file, "wb") as f:
                    f.write(audio_content)
                print(f"✅ 語音生成成功！已保存為: {output_file}")
            else:
                print(f"⚠️ 收到非音頻響應: {response.read().decode('utf-8')}")
                
    except Exception as e:
        print(f"❌ 請求失敗: {e}")

if __name__ == "__main__":
    # 默認讀取同目錄下的腳本文件
    script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "貓咪經濟學腳本.txt")
    if os.path.exists(script_path):
        with open(script_path, "r", encoding="utf-8") as f:
            text = f.read()
        generate_speech_robust(text)
    else:
        print("未找到腳本文件，生成測試語音...")
        generate_speech_robust("這是一個測試語音，確認貓咪經濟學的音色。")

if __name__ == "__main__":
    text = "你好嗎？想你了"
    # 嘗試使用甜美女生聲音模擬台灣女生風格
    # 其他可選 ID: Lovely_Girl, Lively_Girl, Chinese (Mandarin)_HK_Flight_Attendant
    generate_speech(text, voice_id="Sweet_Girl_2")
