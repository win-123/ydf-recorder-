@echo off
REM ============================================================
REM Build self-contained Windows distribution for YonDiF Recorder
REM
REM Run this on a Windows BUILD machine that has Python 3.11+.
REM End users need NOTHING (no Python, no Chrome, no config tool).
REM
REM Usage:
REM   desktop\build_windows.bat                (full build, downloads Chromium)
REM   desktop\build_windows.bat --skip-browsers   (reuse existing chromium)
REM
REM Output:
REM   dist\YonDiF-Recorder-windows\
REM     YonDiFRecorder.exe          <- double-click to record
REM     chromium\                   <- embedded browser (auto-detected)
REM     version.txt
REM   dist\YonDiF-Recorder-windows.zip   <- send this to colleagues
REM
REM First run creates %USERPROFILE%\.ydf-recorder\env.yaml and opens it in
REM Notepad: fill base_url / username / password / tenant / default_org,
REM relaunch, and recording starts. Output goes to
REM %USERPROFILE%\Downloads\ydf-recordings\suite_<timestamp>.yaml
REM ============================================================
setlocal enabledelayedexpansion

set ROOT=%~dp0..
cd /d "%ROOT%"
set SKIP_BROWSERS=0
if /I "%~1"=="--skip-browsers" set SKIP_BROWSERS=1

echo ==^> [1/6] Build toolchain (PyInstaller)
if not exist dist\_build_venv (
  python -m venv dist\_build_venv
  dist\_build_venv\Scripts\pip install --upgrade pip
)
dist\_build_venv\Scripts\pip install -q pyinstaller
dist\_build_venv\Scripts\pip install -q .

echo ==^> [2/6] PyInstaller bundle (includes playwright node driver)
if exist dist\pyi rmdir /s /q dist\pyi
if exist dist\_work rmdir /s /q dist\_work
set PYINSTALLER_CONFIG_DIR=%ROOT%\dist\_pyi_cache
dist\_build_venv\Scripts\pyinstaller desktop\ydf-recorder.spec --noconfirm --distpath dist\pyi --workpath dist\_work --clean
if errorlevel 1 (
  echo PyInstaller failed.
  exit /b 1
)

echo ==^> [3/6] Assemble distribution folder
set OUTDIR=dist\YonDiF-Recorder-windows
if exist "%OUTDIR%" rmdir /s /q "%OUTDIR%"
mkdir "%OUTDIR%"
xcopy /e /i /q "dist\pyi\YonDiFRecorder" "%OUTDIR%"

echo ==^> [4/6] Embedded Chromium
if "%SKIP_BROWSERS%"=="0" (
  echo     downloading chromium + headless shell, one time ~250MB
  set PLAYWRIGHT_BROWSERS_PATH=%OUTDIR%\chromium
  dist\_build_venv\Scripts\python -m playwright install chromium chromium-headless-shell
) else (
  if exist dist\_chromium\ (
    xcopy /e /i /q "dist\_chromium" "%OUTDIR%\chromium"
  ) else (
    echo     WARNING: --skip-browsers given but dist\_chromium not found
  )
)

echo ==^> [5/6] Version marker
dist\_build_venv\Scripts\python -c "import ydf_recorder; print(ydf_recorder.__version__)" > "%OUTDIR%\version.txt"

echo ==^> [6/6] Zip
if exist "%OUTDIR%.zip" del /q "%OUTDIR%.zip"
powershell -NoProfile -Command "Compress-Archive -Path '%OUTDIR%' -DestinationPath '%OUTDIR%.zip' -Force"

echo.
echo Done.
echo   Folder: %OUTDIR%
echo   Zip   : %OUTDIR%.zip
echo End users: unzip, double-click YonDiFRecorder.exe.
echo First run opens the config template in Notepad; fill it and relaunch.
