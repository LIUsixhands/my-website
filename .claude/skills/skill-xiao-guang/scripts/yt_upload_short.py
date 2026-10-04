#!/usr/bin/env python3
import os, sys, json
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TOKEN = os.path.expanduser("~/貓咪經濟學/token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]

video = sys.argv[1]
title = sys.argv[2]
desc  = open(sys.argv[3], encoding="utf-8").read()
privacy = sys.argv[4] if len(sys.argv) > 4 else "public"

creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
if not creds.valid:
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            Path(TOKEN).write_text(creds.to_json())
            print("TOKEN_REFRESHED_OK")
        except Exception as e:
            print("AUTH_FAIL_REFRESH", type(e).__name__, e); sys.exit(2)
    else:
        print("AUTH_FAIL_NO_REFRESH"); sys.exit(2)

yt = build("youtube", "v3", credentials=creds)
body = {
    "snippet": {
        "title": title[:100],
        "description": desc[:5000],
        "tags": ["Sixhands Studio","助哥","AI行銷","免費講座","AI數字員工","台北講座","華人創業","Sixhands Studio經濟學"],
        "categoryId": "27",
        "defaultLanguage": "zh-TW",
    },
    "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
}
media = MediaFileUpload(video, chunksize=-1, resumable=True)
req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
resp = None
while resp is None:
    st, resp = req.next_chunk()
print("VIDEO_ID", resp["id"])
print("URL https://youtu.be/" + resp["id"])
