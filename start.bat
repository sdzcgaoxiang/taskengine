@echo off
REM TaskEngine 启动脚本 - 开机自启 + 崩溃重启
REM 把此文件放到 Windows 启动目录: shell:startup
REM 或创建 Task Scheduler 任务: 登录时运行此脚本

cd /d %~dp0

:restart
echo [%date% %time%] Starting TaskEngine...
python -m taskengine serve
echo [%date% %time%] TaskEngine exited (crash or stop), restarting in 5 seconds...
timeout /t 5 /nobreak >nul
goto restart
