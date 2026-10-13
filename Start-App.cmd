@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_app.ps1" %*
if errorlevel 1 (
  echo.
  echo Startup failed. Read the error above and the runtime logs.
  pause
  exit /b 1
)
