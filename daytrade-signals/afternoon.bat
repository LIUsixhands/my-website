@echo off
REM Post-close review: resolve every signal, write the journal, push the daily report.
REM Scheduled by Windows Task Scheduler on weekdays at 14:00.
REM 14:00 rather than 13:31 because the broker needs a little time to finish
REM serving the last minute bars of the session.
REM To test by hand: just double-click this file.
REM Everything the run prints is appended to logs\afternoon.log, so a silent
REM 14:00 can still be diagnosed later.
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
REM Same blank-window problem as morning.bat; see the note there.
echo.
echo ==========================================================
echo   POST-CLOSE REVIEW IS RUNNING  --  DO NOT CLOSE
echo.
echo   Takes about a minute. The screen stays BLANK until it
echo   finishes. That is normal, it is NOT frozen.
echo.
echo   Closing it means today's results never reach
echo   outcomes.csv, and that day cannot be recovered.
echo ==========================================================
echo.
echo ================ %DATE% %TIME% ================>>"logs\afternoon.log"
python review.py >>"logs\afternoon.log" 2>&1
set RC=%ERRORLEVEL%
echo [exit %RC%]>>"logs\afternoon.log"
REM Show the tail on screen for a hand-run; harmless under the scheduler.
powershell -NoProfile -Command "Get-Content 'logs\afternoon.log' -Tail 25"
if not "%RC%"=="0" echo *** FAILED with exit %RC% -- full log in logs\afternoon.log
