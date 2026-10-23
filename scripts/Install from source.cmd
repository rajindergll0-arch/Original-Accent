@echo off
rem Double-click to install Original Accent for this Windows user.
rem Must be run from an extracted folder, not from inside the zip.
if not exist "%~dp0install-from-source.ps1" (
  echo.
  echo  Original Accent can't find its installer files.
  echo  Extract the whole download first, then run this file from the scripts folder.
  echo.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-from-source.ps1"
echo.
if %errorlevel% neq 0 (echo  Install stopped with an error - see the messages above.) else (echo  Install finished.)
pause
