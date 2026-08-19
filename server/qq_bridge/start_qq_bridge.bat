@echo off
setlocal
set "PROJECT_KEI_ROOT=%~dp0..\.."
set "_PROJECT_KEI_CALLER_NO_PAUSE=%PROJECT_KEI_NO_PAUSE%"
set "PROJECT_KEI_NO_PAUSE=1"
echo [info] QQ Bridge now starts only after an explicit click in the local dashboard.
echo [info] Open http://127.0.0.1:8000/dashboard and click the QQ avatar or Start QQ Bridge.
call :manual_start_required %*
set "_PROJECT_KEI_EXIT=%ERRORLEVEL%"
set "PROJECT_KEI_NO_PAUSE=%_PROJECT_KEI_CALLER_NO_PAUSE%"
call "%PROJECT_KEI_ROOT%\scripts\project-kei.pause.cmd" %_PROJECT_KEI_EXIT% start_qq_bridge
exit /b %_PROJECT_KEI_EXIT%

:manual_start_required
exit /b 2
