@echo off
cd /d "%~dp0"
call .\.venv\Scripts\activate.bat
title Build MaoZhiQin
echo Building and trimming PySide6...
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*
pause