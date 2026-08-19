@echo off
setlocal
set "PROJECT_KEI_ROOT=%~dp0.."
set "_PROJECT_KEI_CALLER_NO_PAUSE=%PROJECT_KEI_NO_PAUSE%"
set "PROJECT_KEI_NO_PAUSE=1"
call "%PROJECT_KEI_ROOT%\start.bat" --only asr --current-window %*
set "_PROJECT_KEI_EXIT=%ERRORLEVEL%"
set "PROJECT_KEI_NO_PAUSE=%_PROJECT_KEI_CALLER_NO_PAUSE%"
call "%PROJECT_KEI_ROOT%\scripts\project-kei.pause.cmd" %_PROJECT_KEI_EXIT% start_asr
exit /b %_PROJECT_KEI_EXIT%
