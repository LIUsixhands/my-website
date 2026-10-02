@echo off
REM Pre-market screener: monitor the full candidate pool, push the top few.
REM Scheduled by Windows Task Scheduler on weekdays at 08:40.
REM To test by hand: just double-click this file.
REM Everything the run prints is appended to logs\morning.log, so a silent
REM 08:40 can still be diagnosed hours later.
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
REM A scheduled run pops a console window the user did not ask for, and
REM everything below is redirected to the log, so that window stays BLANK
REM for the whole run. On 2026-10-01 it looked frozen and was closed by hand
REM (exit 0xC000013A = CTRL+C) -- the whole pre-market watchlist was lost.
REM So say, on screen, what it is and that a blank screen is normal.
echo.
echo ==========================================================
echo   PRE-MARKET SCREENER IS RUNNING  --  DO NOT CLOSE
echo.
echo   Takes about 1-2 minutes.
echo   The screen stays BLANK until it finishes. That is normal,
echo   it is NOT frozen. This window closes by itself.
echo.
echo   The watchlist is pushed to Telegram when it is done.
echo ==========================================================
echo.
echo ================ %DATE% %TIME% ================>>"logs\morning.log"
python screener.py --push >>"logs\morning.log" 2>&1
set RC=%ERRORLEVEL%
echo [exit %RC%]>>"logs\morning.log"
REM Show the tail on screen for a hand-run; harmless under the scheduler.
powershell -NoProfile -Command "Get-Content 'logs\morning.log' -Tail 25"
if not "%RC%"=="0" echo *** FAILED with exit %RC% -- full log in logs\morning.log
