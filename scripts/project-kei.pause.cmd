@echo off
setlocal
set "_PROJECT_KEI_EXIT=%~1"
set "_PROJECT_KEI_LABEL=%~2"
if not defined _PROJECT_KEI_EXIT set "_PROJECT_KEI_EXIT=1"
if not defined _PROJECT_KEI_LABEL set "_PROJECT_KEI_LABEL=command"

if "%_PROJECT_KEI_EXIT%"=="0" (
    echo [Project Kei] %_PROJECT_KEI_LABEL% completed successfully.
) else (
    echo [Project Kei] %_PROJECT_KEI_LABEL% exited with code %_PROJECT_KEI_EXIT%.
)

if not "%PROJECT_KEI_NO_PAUSE%"=="1" (
    echo Press any key to close this window...
    pause >nul
)
exit /b %_PROJECT_KEI_EXIT%
