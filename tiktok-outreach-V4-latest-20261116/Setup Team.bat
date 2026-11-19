@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (python scripts\team_setup.py) else (py -3 scripts\team_setup.py)
pause
