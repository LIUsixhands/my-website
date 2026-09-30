# 範例成品

| 檔案 | 說明 |
|:---|:---|
| `示範成片_9x16.mp4` | 用 `templates/scenes_範例.json` + `templates/chart_範例.json` 直接跑出來的成片（系統語音版，29 秒）。接上 ElevenLabs 後聲音會好很多。 |
| `示範命盤圖.png` | `gen_chart.py` 的輸出，可單獨拿去做貼文、簡報、縮圖。 |

想自己重跑一次：

```bash
mkdir -p ~/Desktop/紫微影片 && cd ~/Desktop/紫微影片
cp ~/.claude/skills/skill-xiao-zi/templates/scenes_範例.json scenes.json
cp ~/.claude/skills/skill-xiao-zi/templates/chart_範例.json  chart.json
python3 ~/.claude/skills/skill-xiao-zi/scripts/make_ziwei_short.py scenes.json
```
