@echo off
REM ============================================================
REM  Builds Jarvis into a Windows app.
REM  Needs: Python 3.11 or 3.12 (64-bit) from python.org, "Add to PATH" checked.
REM  Optional: Inno Setup 6 (jrsoftware.org) to also make JarvisSetup.exe
REM ============================================================
setlocal
cd /d "%~dp0"

echo [1/4] Creating virtual environment...
if not exist .venv (
    py -3.12 -m venv .venv 2>nul || python -m venv .venv
)
call .venv\Scripts\activate.bat || goto :fail

echo [2/4] Installing dependencies (first time takes a few minutes)...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller || goto :fail

echo [3/4] Building Jarvis.exe...
pyinstaller --noconfirm --clean --windowed ^
  --name Jarvis ^
  --icon assets\jarvis.ico ^
  --add-data "assets;assets" ^
  --collect-all faster_whisper ^
  --collect-all ctranslate2 ^
  --collect-all customtkinter ^
  --collect-all piper ^
  --collect-all onnxruntime ^
  --collect-all tokenizers ^
  --hidden-import pyttsx3.drivers ^
  --hidden-import pyttsx3.drivers.sapi5 ^
  --hidden-import comtypes.client ^
  run_jarvis.py || goto :fail

echo [4/4] Packaging...
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
    %ISCC% installer.iss || goto :fail
    echo.
    echo Done! Send him:  Output\JarvisSetup.exe
) else (
    powershell -NoProfile -Command "Compress-Archive -Force -Path dist\Jarvis\* -DestinationPath Jarvis-Windows.zip"
    echo.
    echo Done! Send him:  Jarvis-Windows.zip   ^(unzip, run Jarvis.exe^)
    echo Tip: install Inno Setup 6 and re-run to get a proper installer instead.
)
goto :eof

:fail
echo.
echo Build failed - scroll up for the error.
exit /b 1
