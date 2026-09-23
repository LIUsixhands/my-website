# 範例

`demo_9x16.mp4` — 用純程式生成的假素材跑完整條產線的驗證片
（8 秒 / 1080×1920 / 30fps，含 image-fill、band、card 三種鏡型 + 字幕 + 品牌尾卡）。

這支的用途是**確認你的環境裝好了**，不是作品範例。
跑得出一樣的東西，就代表 ffmpeg / PIL / 字型 / logo 都正常。

重跑方式：
```bash
cd ~/.claude/skills/skill-xiao-qu/examples/demo
python3 ../../scripts/build_mv.py mv.json
```
