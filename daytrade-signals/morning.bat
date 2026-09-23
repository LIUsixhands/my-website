@echo off
REM Pre-market screener: keep top 5 by volume ratio, push to Telegram.
REM Scheduled by Windows Task Scheduler on weekdays at 08:40.
REM To test by hand: just double-click this file.
cd /d "%~dp0"
python screener.py --top 5 --push
