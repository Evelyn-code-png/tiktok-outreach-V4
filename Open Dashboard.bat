@echo off
setlocal

rem Launch the local creator workspace from the folder that contains this file.
cd /d "%~dp0"
set "DASHBOARD=%~dp0scripts\dashboard.py"

rem The standard Windows Python installer normally provides the "py" launcher.
where py >nul 2>&1
if not errorlevel 1 goto run_with_py

rem Some installations expose Python only through the "python" command.
where python >nul 2>&1
if not errorlevel 1 goto run_with_python

echo.
echo Python 3.10 or newer was not found on this computer.
echo Install Python from https://www.python.org/downloads/windows/
echo During installation, select "Add python.exe to PATH", then open this file again.
echo.
pause
exit /b 1

:run_with_py
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto python_too_old
py -3 "%DASHBOARD%" --reuse
goto finished

:run_with_python
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto python_too_old
python "%DASHBOARD%" --reuse
goto finished

:python_too_old
echo.
echo This workspace requires Python 3.10 or newer.
echo Update Python from https://www.python.org/downloads/windows/ and try again.
echo.
pause
exit /b 1

:finished
set "DASHBOARD_EXIT=%ERRORLEVEL%"
if "%DASHBOARD_EXIT%"=="0" exit /b 0
echo.
echo The workspace stopped with an error. Review the message above.
echo.
pause
exit /b %DASHBOARD_EXIT%
