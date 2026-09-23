@echo off
REM Pre-market screener: monitor the full candidate pool, push the top few.
REM Scheduled by Windows Task Scheduler on weekdays at 08:40.
REM To test by hand: just double-click this file.
cd /d "%~dp0"
python screener.py --push
