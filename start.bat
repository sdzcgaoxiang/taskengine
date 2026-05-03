@echo off
REM TaskEngine startup script - auto-start on boot + crash restart
REM Place this file in the Windows startup directory: shell:startup
REM Or create a Task Scheduler task to run this script on login

cd /d %~dp0

:restart
echo [%date% %time%] Starting TaskEngine...
python -m taskengine serve
echo [%date% %time%] TaskEngine exited (crash or stop), restarting in 5 seconds...
timeout /t 5 /nobreak >nul
goto restart
