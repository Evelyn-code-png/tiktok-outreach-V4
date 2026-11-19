@echo off
rem Start the Outreach owl: it peeks out from the edge of the screen; click it to open the workspace.
cd /d "%~dp0"
set "PET=%~dp0scripts\owl_pet.py"

rem pyw / pythonw run the owl without a console window.
where pyw >nul 2>&1
if not errorlevel 1 (
  start "" pyw -3 "%PET%"
  exit /b 0
)
where pythonw >nul 2>&1
if not errorlevel 1 (
  start "" pythonw "%PET%"
  exit /b 0
)
where py >nul 2>&1
if not errorlevel 1 (
  start "" /min py -3 "%PET%"
  exit /b 0
)

echo.
echo Python 3.10 or newer was not found on this computer.
echo Install Python from https://www.python.org/downloads/windows/ and open this file again.
echo.
pause
exit /b 1
