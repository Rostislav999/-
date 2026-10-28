@echo off
setlocal
cd /d "%~dp0"
set "PROTOCOL_WRAPPED=1"
call start.bat %*
set "RESULT=%ERRORLEVEL%"
if "%PROTOCOL_NO_PAUSE%"=="1" exit /b %RESULT%
echo.
echo Press any key to close this window.
pause >nul
exit /b %RESULT%
