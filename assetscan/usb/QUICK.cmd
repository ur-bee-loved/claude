@echo off
setlocal
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if exist "%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe" set "PS=%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0assetscan\Collect.ps1" -NoPrompt -NoResultDialog -SkipConsent %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (echo. & echo FAILED, see the run.log in assetscan-data\runs & pause & exit /b %RC%)
echo.
echo Done. You can remove the USB drive. This window closes in 5 seconds.
timeout /t 5 >nul
exit /b 0
