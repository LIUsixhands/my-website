@echo off
REM Intraday monitor: watch the list, emit signals, track them to stop or target.
REM Scheduled by Windows Task Scheduler on weekdays at 08:50 (after the 08:40
REM screener has written today watchlist).
REM The program exits by itself at 13:30, so nothing has to stop it.
REM To test by hand: just double-click this file.
REM Everything the run prints is appended to logs\monitor.log.
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
REM This one matters most: the window stays open from 08:50 to 13:30 and
REM everything is redirected to the log, so it looks frozen for 4h40m.
REM Closing it kills every signal AND the live stop/target tracking for
REM the rest of the day, silently. Say so on screen.
echo.
echo ==========================================================
echo   INTRADAY MONITOR IS RUNNING  --  DO NOT CLOSE
echo.
echo   Runs until 13:30, then closes by itself.
echo   The screen stays BLANK all day. That is normal,
echo   it is NOT frozen.
echo.
echo   CLOSING THIS WINDOW STOPS TODAY'S SIGNALS AND STOPS
echo   TRACKING ANY POSITION YOU ALREADY HAVE. No warning.
echo.
echo   Signals arrive on Telegram, not here.
echo ==========================================================
echo.
echo ================ %DATE% %TIME% ================>>"logs\monitor.log"
python signals.py >>"logs\monitor.log" 2>&1
set RC=%ERRORLEVEL%
echo [exit %RC%]>>"logs\monitor.log"
REM Show the tail on screen for a hand-run; harmless under the scheduler.
powershell -NoProfile -Command "Get-Content 'logs\monitor.log' -Tail 25"
if not "%RC%"=="0" echo *** FAILED with exit %RC% -- full log in logs\monitor.log
