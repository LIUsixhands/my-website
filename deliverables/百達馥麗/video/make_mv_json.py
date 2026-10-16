"""百達馥麗 16F 介紹影片：產生小曲 build_mv.py 用的 mv.json。
字幕放物件資訊（不放歌詞），時間軸依實際音檔長度等比縮放；尾卡從音樂結束前 7 秒開始。
用法：python3 make_mv_json.py audio/take1.mp3"""
import json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).parent
audio = sys.argv[1] if len(sys.argv) > 1 else 'audio/take1.mp3'
dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(HERE / audio)],
                           capture_output=True, text=True).stdout)
EC = 7.0                       # 尾卡秒數
# (秒數權重, 鏡頭, 字幕)
PLAN = [
    (3.0, dict(type='image', src='assets/外觀_雕塑仰視.jpg', mode='fill', cx=0.58, cy=0.45, zoom='in'), '台中西區・勤美草悟道生活圈'),
    (2.6, dict(type='image', src='assets/外觀_林蔭街景.jpg', mode='fill', cx=0.52, cy=0.5, zoom='out'), '興富發 百達馥麗・34 層'),
    (2.2, dict(type='card', big='16樓 邊間\n朝東南', sub='3+1房2廳3衛・93.16坪含車位'), ''),
    (2.6, dict(type='image', src='assets/室內_客廳.jpg', mode='fill', cx=0.45, cy=0.5, zoom='in'), '整戶精裝・空屋即可入住'),
    (2.3, dict(type='image', src='assets/室內_玄關客廳.jpg', mode='fill', cx=0.3, cy=0.5, zoom='in'), '玄關落塵區・整面收納'),
    (2.6, dict(type='image', src='assets/室內_中島客廳全景.jpg', mode='fill', cx=0.55, cy=0.5, zoom='out'), '客餐廚一字排開'),
    (2.0, dict(type='image', src='assets/室內_中島餐廳.jpg', mode='fill', cx=0.62, cy=0.55, zoom='in'), '大理石中島吧檯'),
    (2.0, dict(type='image', src='assets/室內_廚房.jpg', mode='fill', cx=0.55, cy=0.5, zoom='in'), '一字型廚具・嵌入式烤箱'),
    (2.6, dict(type='image', src='assets/室內_陽台景觀.jpg', mode='fill', cx=0.78, cy=0.5, zoom='in'), '16樓 遠眺市區天際線'),
    (2.2, dict(type='image', src='assets/室內_主臥.jpg', mode='fill', cx=0.6, cy=0.5, zoom='in'), '臥室大面景觀窗'),
    (2.0, dict(type='image', src='assets/室內_次臥.jpg', mode='fill', cx=0.35, cy=0.5, zoom='out'), '次臥雙面開窗'),
    (2.4, dict(type='image', src='assets/室內_主浴.jpg', mode='fill', cx=0.62, cy=0.5, zoom='in'), '主浴開窗・按摩浴缸'),
    (2.2, dict(type='image', src='assets/室內_書房.jpg', mode='fill', cx=0.55, cy=0.5, zoom='in'), '多功能空間 可作第四房'),
    (2.8, dict(type='image', src='assets/格局圖.jpg', mode='fit', zoom='in', zoom_amt=0.04), '三面採光・三套衛浴皆開窗'),
    (2.6, dict(type='image', src='assets/棟別圖.png', mode='band', cy=0.5, zoom='in', zoom_amt=0.04), 'B1 棟・位於基地內側'),
    (2.6, dict(type='image', src='assets/外觀_林蔭街景.jpg', mode='fill', cx=0.2, cy=0.6, zoom='in'), '步行到勤美・廣三SOGO'),
    (2.2, dict(type='card', big='坡道平面\n車位', sub='B4-146・物業管理'), ''),
    (2.6, dict(type='card', big='開價\n3,980萬', sub='含車位・管理費 8,500 元/月'), ''),
]
body = dur - EC
scale = body / sum(w for w, _, _ in PLAN)
t, shots, subs = 0.0, [], []
for i, (w, sh, sub) in enumerate(PLAN):
    t1 = round(t + w * scale, 2) if i < len(PLAN) - 1 else round(body, 2)
    shots.append(dict(id=f's{i+1:02d}', t0=round(t, 2), t1=t1, **sh))
    if sub:
        subs.append(dict(t0=round(t + 0.15, 2), t1=round(t1 - 0.1, 2), text=sub))
    t = t1

cfg = {
    'ratio': '9:16', 'fps': 30, 'audio': audio, 'total': None, 'out': '百達馥麗_16F_介紹.mp4',
    'brand': False,                         # 助哥自己的物件廣告：不掛 Sixhands logo，尾卡放經紀業名稱
    'accent': [200, 150, 62], 'card_bg': [22, 58, 71], 'sub_y': 0.70, 'sub_chars': 13, 'zoom_amt': 0.08, 'scrim': 0.35,
    'subs': subs, 'shots': shots,
    'endcard': {'t0': round(body, 2), 'title': '百達馥麗 16F',
                'lines': ['台中市西區中興街', '3+1房・93.16坪（含車位）', '助哥 0925-313-570', 'LINE @080akczk',
                          'sixhands.tw', '永慶不動產 七期河南市政店'],
                'cta': '預約看屋',
                'qrs': [{'src': 'assets/QR_LINE.png', 'label': '加 LINE'}, {'src': 'assets/QR_網站.png', 'label': 'sixhands.tw'}]},
}
(HERE / 'mv.json').write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding='utf-8')
print(f'音檔 {dur:.2f}s ／ 內容 {body:.2f}s ／ {len(shots)} 鏡 ／ 平均 {body/len(shots):.2f}s')
