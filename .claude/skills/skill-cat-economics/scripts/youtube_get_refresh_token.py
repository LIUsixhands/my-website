#!/usr/bin/env python3
"""一次性取得 YouTube 上傳用的 refresh token（在「你自己的電腦」執行）。

雲端 session 沒有瀏覽器，無法做 OAuth 授權，所以這支要在本機跑一次：
會開瀏覽器讓你登入並同意，結束後印出 refresh token，
再把它貼到雲端環境變數 YOUTUBE_REFRESH_TOKEN。

前置：
    pip install google-auth-oauthlib
    準備好 client_secret.json（從 Google Cloud Console OAuth 用戶端下載，桌面應用程式類型）

用法：
    python youtube_get_refresh_token.py client_secret.json
"""
import sys

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("請先安裝：pip install google-auth-oauthlib")
    sys.exit(1)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main():
    if len(sys.argv) < 2:
        print("用法：python youtube_get_refresh_token.py client_secret.json")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
    # 開瀏覽器授權（本機才有瀏覽器）
    creds = flow.run_local_server(port=0, prompt="consent")

    print("\n================ 複製以下三個值到雲端環境變數 ================")
    print(f"YOUTUBE_CLIENT_ID={creds.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={creds.client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")
    print("============================================================")
    print("（refresh token 只在第一次授權時出現，請務必複製保存）")


if __name__ == "__main__":
    main()
