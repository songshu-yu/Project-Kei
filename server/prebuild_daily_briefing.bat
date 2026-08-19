@echo off
setlocal
chcp 65001 >nul
set "PROJECT_KEI_ROOT=%~dp0.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_KEI_ROOT%\scripts\run-server-tool.ps1" prebuild-daily-briefing %*
set "_PROJECT_KEI_EXIT=%ERRORLEVEL%"
call "%PROJECT_KEI_ROOT%\scripts\project-kei.pause.cmd" %_PROJECT_KEI_EXIT% prebuild_daily_briefing
exit /b %_PROJECT_KEI_EXIT%
