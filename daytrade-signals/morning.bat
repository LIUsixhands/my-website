@echo off
REM Pre-market screener: monitor the full candidate pool, push the top few.
REM Scheduled by Windows Task Scheduler on weekdays at 08:40.
REM To test by hand: just double-click this file.
REM Everything the run prints is appended to logs\morning.log, so a silent
REM 08:40 can still be diagnosed hours later.
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
echo ================ %DATE% %TIME% ================>>"logs\morning.log"
python screener.py --push >>"logs\morning.log" 2>&1
set RC=%ERRORLEVEL%
echo [exit %RC%]>>"logs\morning.log"
REM Show the tail on screen for a hand-run; harmless under the scheduler.
powershell -NoProfile -Command "Get-Content 'logs\morning.log' -Tail 25"
if not "%RC%"=="0" echo *** FAILED with exit %RC% -- full log in logs\morning.log
