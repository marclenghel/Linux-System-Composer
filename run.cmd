@echo off
REM Double-click launcher for Linux System Composer.
REM Hands off to run.ps1, which does the real work. The -NoExit keeps the
REM window open so you can read the error if something goes wrong.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
if errorlevel 1 pause
