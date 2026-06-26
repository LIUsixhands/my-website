#!/usr/bin/env python3
"""自動上傳影片到 YouTube（YouTube Data API v3）。

用 OAuth refresh token 認證（無需執行時開瀏覽器），上傳 MP4 並設定
標題 / 簡介 / 標籤 / 隱私狀態。預設上傳為「私人(private)」較安全。

必填環境變數：
    YOUTUBE_CLIENT_ID
    YOUTUBE_CLIENT_SECRET
    YOUTUBE_REFRESH_TOKEN      （見 youtube_get_refresh_token.py / YOUTUBE_SETUP.md）

用法：
    python youtube_upload.py 影片.mp4 \
        --title "標題" \
        --description-file 簡介.txt \
        --tags "貓咪經濟學,關稅,經濟學" \
        --privacy private          # private / unlisted / public

也可只給影片，其餘用預設：
    python youtube_upload.py final_video_cat_economics.mp4
"""
import argparse
import os
import sys

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except ImportError:
    print("❌ 缺少套件。請確認 setup script 已安裝：")
    print("   pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2")
    sys.exit(1)

TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CATEGORY_EDUCATION = "27"  # YouTube 分類：教育


def build_service():
    cid = os.getenv("YOUTUBE_CLIENT_ID")
    secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh = os.getenv("YOUTUBE_REFRESH_TOKEN")
    missing = [n for n, v in [
        ("YOUTUBE_CLIENT_ID", cid),
        ("YOUTUBE_CLIENT_SECRET", secret),
        ("YOUTUBE_REFRESH_TOKEN", refresh),
    ] if not v]
    if missing:
        print(f"❌ 缺少環境變數：{', '.join(missing)}。請見 YOUTUBE_SETUP.md。")
        sys.exit(1)

    creds = Credentials(
        token=None,
        refresh_token=refresh,
        token_uri=TOKEN_URI,
        client_id=cid,
        client_secret=secret,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload(video_path, title, description, tags, privacy):
    if not os.path.exists(video_path):
        print(f"❌ 找不到影片檔：{video_path}")
        sys.exit(1)

    youtube = build_service()
    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags,
            "categoryId": CATEGORY_EDUCATION,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    print(f"⬆️ 開始上傳：{video_path}")
    print(f"   標題：{title}")
    print(f"   隱私：{privacy}")

    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"   進度 {int(status.progress() * 100)}%")

    vid = response.get("id")
    print(f"✅ 上傳完成！影片網址：https://youtu.be/{vid}")
    if privacy == "private":
        print("   （目前是「私人」，到 YouTube 後台確認無誤後再改公開）")
    return vid


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video", help="要上傳的 mp4 路徑")
    p.add_argument("--title", default="貓咪經濟學新影片")
    p.add_argument("--description", default="")
    p.add_argument("--description-file", help="從檔案讀取簡介（優先於 --description）")
    p.add_argument("--tags", default="貓咪經濟學,經濟學,科普", help="逗號分隔")
    p.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    args = p.parse_args()

    description = args.description
    if args.description_file and os.path.exists(args.description_file):
        with open(args.description_file, encoding="utf-8") as f:
            description = f.read()

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    upload(args.video, args.title, description, tags, args.privacy)


if __name__ == "__main__":
    main()
