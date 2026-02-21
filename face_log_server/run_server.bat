@echo off
REM Hikvision Face Log Server - Windows Server startup script
REM Runs Waitress on port 80 (requires Administrator for port 80)

cd /d "%~dp0"

REM Activate virtual environment if it exists
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Set port (default 80; use PORT=8080 for non-admin)
if "%PORT%"=="" set PORT=80

REM Start server
echo Starting Face Log Server on port %PORT%...
python app.py

pause
