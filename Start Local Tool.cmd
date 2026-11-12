@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local-tool.ps1" %*
if errorlevel 1 (
    echo.
    echo The local tool could not start. See the message above.
    pause
    exit /b 1
)
