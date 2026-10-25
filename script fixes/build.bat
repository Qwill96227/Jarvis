@echo off
REM ============================================================
REM  Builds Drexya into a Windows app.
REM  Needs: Python 3.11 or 3.12 (64-bit) from python.org, "Add to PATH" checked.
REM  Optional: Inno Setup 6 (jrsoftware.org) to also make DrexyaSetup.exe
REM ============================================================
setlocal
cd /d "%~dp0.."

echo [1/4] Creating virtual environment...
if not exist .venv (
    py -3.12 -m venv .venv 2>nul || python -m venv .venv
)
call .venv\Scripts\activate.bat || goto :fail

echo [2/4] Installing dependencies (first time takes a few minutes)...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller || goto :fail

echo [3/4] Building Drexya.exe...
pyinstaller --noconfirm --clean --windowed ^
  --name Drexya ^
  --icon assets\jarvis.ico ^
  --add-data "assets;assets" ^
  --collect-all faster_whisper ^
  --collect-all ctranslate2 ^
  --collect-all customtkinter ^
  --collect-all piper ^
  --collect-all onnxruntime ^
  --collect-all tokenizers ^
  --collect-data googleapiclient ^
  --hidden-import pyttsx3.drivers ^
  --hidden-import pyttsx3.drivers.sapi5 ^
  --hidden-import comtypes.client ^
  run_jarvis.py || goto :fail

REM PyInstaller can bundle an old Visual C++ runtime (14.31) that makes the newer DLLs in
REM numpy/onnxruntime/ctranslate2 crash on launch (0xC0000005 in MSVCP140.dll). Ship the
REM current Windows copies instead.
for %%D in (msvcp140.dll vcruntime140.dll vcruntime140_1.dll) do (
    copy /y "%SystemRoot%\System32\%%D" "dist\Drexya\_internal\%%D" >nul || goto :fail
)

echo [4/4] Packaging...
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
    %ISCC% installer.iss || goto :fail
    echo.
    echo Done! Send him:  Output\DrexyaSetup.exe
) else (
    REM Retry: antivirus often holds freshly built files open for a few seconds
    powershell -NoProfile -Command "for ($i = 1; $i -le 5; $i++) { try { Compress-Archive -Force -Path dist\Drexya\* -DestinationPath Drexya-Windows.zip -ErrorAction Stop; exit 0 } catch { Write-Host 'Zip attempt failed, retrying...'; Start-Sleep 5 } }; exit 1" || goto :fail
    echo.
    echo Done! Send him:  Drexya-Windows.zip   ^(unzip, run Drexya.exe^)
    echo Tip: install Inno Setup 6 and re-run to get a proper installer instead.
)
goto :eof

:fail
echo.
echo Build failed - scroll up for the error.
exit /b 1
