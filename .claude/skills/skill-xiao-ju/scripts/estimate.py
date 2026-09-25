"""步驟 4 之前：估算影片生成費（fal.ai），並查 fal 餘額夠不夠
單價（2026-09-19 查 fal 官方定價）：Kling AI Avatar v2 $0.0562/秒、Hailuo-02 $0.045/秒（每支固定 6 秒）、OmniHuman 1.5 $0.16/秒"""
import requests
from common import EP, key
from timeline import build

KLING, HAILUO, OMNI, KLING_KF, USD_NTD = 0.0562, 0.045, 0.16, 0.098, 32   # KLING_KF：Kling v2.1 pro 首尾幀（5 秒約 US$0.49，以 fal 後台為準）
tl = build()
talk = sum(x["dur"] for x in tl if x["type"] == "talk")
anim = sum(1 for x in tl if x["type"] in ("anim", "card"))
kf = sum(5 if x["dur"] <= 5 else 10 for x in tl if x["type"] == "kf")
k, h = talk * KLING * 1.1 + kf * KLING_KF, anim * 6 * HAILUO   # Kling 實際輸出常比音檔長一點，抓 1.1 倍
print(f"對白 {talk:.1f} 秒＋首尾幀 {kf} 秒 → Kling 約 US${k:.2f}")
print(f"動作／片尾 {anim} 鏡 × 6 秒 → Hailuo 約 US${h:.2f}")
print(f"合計約 US${k + h:.2f}（約 NT${(k + h) * USD_NTD:.0f}），重生壞鏡另計；若全部改用 OmniHuman 對嘴約 US${talk * OMNI:.2f}")
try:
    bal = requests.get("https://rest.alpha.fal.ai/billing/user_balance",
                       headers={"Authorization": f"Key {key('FAL_KEY')}"}, timeout=20).text
    print(f"fal 餘額：US${float(bal):.2f}" + ("  ⚠️ 不夠，請先到 fal.ai 後台儲值（要本人操作）" if float(bal) < (k + h) * 1.3 else ""))
except Exception as e:
    print("查不到 fal 餘額：", str(e)[:100])
