@echo off
REM Double-click to run Drexya from source.
REM First run sets everything up automatically (a few minutes); after that it starts right away.
setlocal
cd /d "%~dp0.."

if not exist .venv\Scripts\python.exe (
    echo First run: setting up Drexya. This takes a few minutes...
    py -3.12 -m venv .venv 2>nul || python -m venv .venv || goto :nopython
    .venv\Scripts\python -m pip install --upgrade pip >nul
    .venv\Scripts\pip install -r requirements.txt || goto :fail
    echo.
    echo Setup complete.
)

REM Re-install if requirements.txt changed since the last setup
fc /b requirements.txt .venv\requirements.installed >nul 2>&1 || (
    echo Updating packages...
    .venv\Scripts\pip install -r requirements.txt || goto :fail
    copy /y requirements.txt .venv\requirements.installed >nul
)

echo Starting Drexya...
.venv\Scripts\python run_jarvis.py
if errorlevel 1 (
    echo.
    echo Drexya exited with an error. Copy the text above and send it over.
    pause
)
goto :eof

:nopython
echo Python wasn't found. Install Python 3.12 from python.org and check "Add python.exe to PATH".
pause
exit /b 1

:fail
echo.
echo Setup failed. Copy the text above and send it over.
pause
exit /b 1
