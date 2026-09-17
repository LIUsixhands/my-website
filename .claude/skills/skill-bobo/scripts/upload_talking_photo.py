#!/usr/bin/env python3
"""把一張人像照上傳到 HeyGen，建立 Photo Avatar（talking photo），取得 ID。

用途：讓虛擬人物用「自己的臉」講話，而不是跟其他 HeyGen 用戶共用現成主播。

用法：
    python3 upload_talking_photo.py 小路_基準臉.png

成功後會印出 talking_photo_id，把它設成環境變數 HEYGEN_TALKING_PHOTO_ID，
之後 heygen_generate.py 就會自動改用這張臉。

⚠️ 只能上傳你有權使用的臉：
   - AI 生成的虛擬人物（本工具的用途）✅
   - 你自己的臉 ✅
   - 別人的照片、名人、網路上抓的圖 ❌（HeyGen 條款禁止，也違法）
"""
import argparse
import json
import os
import sys

try:
    import requests
except ImportError:
    sys.exit("❌ 缺少套件 requests。請確認 setup script 已安裝。")

UPLOAD = "https://upload.heygen.com/v1/talking_photo"
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image", help="人像圖檔（jpg / png）")
    a = ap.parse_args()

    key = os.getenv("HEYGEN_API_KEY")
    if not key:
        sys.exit("❌ 找不到 HEYGEN_API_KEY，請在環境設定填入並存檔（新 session 才生效）。")

    if not os.path.exists(a.image):
        sys.exit(f"❌ 找不到檔案：{a.image}")

    ext = os.path.splitext(a.image)[1].lower()
    if ext not in MIME:
        sys.exit(f"❌ 只支援 jpg / png，這是 {ext}")

    size = os.path.getsize(a.image)
    print(f"⬆️ 上傳 {a.image}（{size // 1024} KB）…")

    with open(a.image, "rb") as f:
        r = requests.post(
            UPLOAD,
            headers={"X-Api-Key": key, "Content-Type": MIME[ext]},
            data=f.read(),
            timeout=180,
        )

    if r.status_code != 200:
        print(f"❌ 上傳失敗 HTTP {r.status_code}")
        print(f"   HeyGen 回應：{r.text[:800]}")
        print("\n把上面這段貼給我，我看是哪裡卡住。常見原因：")
        print("  - 方案不含 Photo Avatar（免費/低階方案可能沒有）")
        print("  - 圖片裡沒有偵測到清楚的人臉")
        print("  - 需要先在網頁後台完成一次 avatar 建立流程")
        sys.exit(1)

    try:
        payload = r.json()
    except ValueError:
        sys.exit(f"❌ 回應不是 JSON：{r.text[:500]}")

    tp_id = (payload.get("data") or {}).get("talking_photo_id")
    if not tp_id:
        print("⚠️ 上傳成功但沒看到 talking_photo_id，完整回應如下（貼給我我幫你看）：")
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:1500])
        sys.exit(1)

    print(f"\n✅ 建立成功！\n   talking_photo_id = {tp_id}\n")
    print("下一步：把這行加進環境設定")
    print(f"   HEYGEN_TALKING_PHOTO_ID={tp_id}")
    print("\n之後跑 heygen_generate.py 就會自動用這張臉，不用改指令。")


if __name__ == "__main__":
    main()
