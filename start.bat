@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
title Protocol to Excel - Startup

echo Protocol to Excel - starting...
echo Please wait. First-time setup may take a few minutes.
echo.
if not exist "logs" mkdir "logs"
echo Windows launcher diagnostics > "logs\launcher.log"

if not exist "bootstrap.py" goto :incomplete

call py -3.12 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >> "logs\launcher.log" 2>&1
if "%ERRORLEVEL%"=="0" goto :python312
call py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >> "logs\launcher.log" 2>&1
if "%ERRORLEVEL%"=="0" goto :pylauncher
call python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >> "logs\launcher.log" 2>&1
if "%ERRORLEVEL%"=="0" goto :python
call python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >> "logs\launcher.log" 2>&1
if "%ERRORLEVEL%"=="0" goto :python3

echo ERROR: Python 3.10 or newer could not be started.
echo Install Python 3.12 64-bit from https://www.python.org/downloads/
echo Enable Add Python to PATH and Tcl/Tk in the installer, then try again.
echo Details: logs\launcher.log
set "RESULT=1"
goto :done

:python312
call py -3.12 bootstrap.py %*
set "RESULT=%ERRORLEVEL%"
goto :done
:pylauncher
call py -3 bootstrap.py %*
set "RESULT=%ERRORLEVEL%"
goto :done
:python
call python bootstrap.py %*
set "RESULT=%ERRORLEVEL%"
goto :done
:python3
call python3 bootstrap.py %*
set "RESULT=%ERRORLEVEL%"
goto :done

:incomplete
echo ERROR: bootstrap.py is missing. Extract the COMPLETE new ZIP archive.
set "RESULT=1"

:done
echo.
echo Startup exit code: %RESULT%
echo If startup failed, send the error text or logs\startup.log.
if "%PROTOCOL_NO_PAUSE%"=="1" exit /b %RESULT%
if "%PROTOCOL_WRAPPED%"=="1" exit /b %RESULT%
echo Press any key to close this window.
pause >nul
exit /b %RESULT%
