@echo off
REM ============================================================
REM Build self-contained Windows distribution for YonDiF Recorder
REM
REM Run on a Windows BUILD machine with Python 3.11+ (64-bit, same
REM architecture as the target PCs). End users need NOTHING:
REM no Python, no Chrome, no config editor.
REM
REM Usage:
REM   desktop\build_windows.bat                    full build (downloads Chromium)
REM   desktop\build_windows.bat --skip-browsers     reuse dist\_chromium if present
REM
REM Output (all paths relative to repo root):
REM   dist\YonDiF-Recorder-windows\
REM     YonDiFRecorder\YonDiFRecorder.exe   <- double-click opens the GUI
REM     YonDiFRecorder\chromium\            <- embedded browser (recorder)
REM     YonDiFRecorder\ydfbrowser-cli\      <- embedded player (YAML replay)
REM     version.txt
REM   dist\YonDiF-Recorder-windows.zip      <- send this to colleagues
REM
REM App layout mirrors the macOS bundle: chromium\ and ydfbrowser-cli\
REM sit next to the executable so ydf_recorder.replay / entry.py find
REM them without any environment variable.
REM
REM First launch: GUI opens on the "Environment" tab. Fill base_url /
REM tenant / org / username / password once, Save, then record.
REM Output goes to %USERPROFILE%\Downloads\ydf-recordings\suite_<ts>.yaml
REM ============================================================
setlocal enabledelayedexpansion
chcp 65001 > nul

set ROOT=%~dp0..
cd /d "%ROOT%"
set SKIP_BROWSERS=0
if /I "%~1"=="--skip-browsers" set SKIP_BROWSERS=1

set PYI_DIST=%ROOT%\dist\pyi
set PYI_WORK=%ROOT%\dist\_work
set BUILD_VENV=%ROOT%\dist\_build_venv
set OUTDIR=%ROOT%\dist\YonDiF-Recorder-windows
set APPDIR=%OUTDIR%\YonDiFRecorder
set CHROMIUM_KEEP=%ROOT%\dist\_chromium

REM UTF-8 console + unbuffered output so Chinese log lines are readable
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ==^> [1/8] Build toolchain (PyInstaller)
if not exist "%BUILD_VENV%" (
  python -m venv "%BUILD_VENV%" || goto :fail
  "%BUILD_VENV%\Scripts\pip" install --upgrade pip -q || goto :fail
)
"%BUILD_VENV%\Scripts\pip" install -q pyinstaller || goto :fail
"%BUILD_VENV%\Scripts\pip" install -q . || goto :fail

REM Player runtime: install vendor\ydf-browser WITHOUT deps (playwright must
REM stay aligned with the bundled Chromium), then add the pure-Python deps it
REM still needs at runtime (openpyxl / PyYAML / requests). Skipping these makes
REM the packaged ydfbrowser-cli die with ModuleNotFoundError on first run.
if exist "%ROOT%\vendor\ydf-browser\pyproject.toml" (
  echo     installing vendor\ydf-browser ^(replay runtime^)
  "%BUILD_VENV%\Scripts\pip" install -q --no-deps "%ROOT%\vendor\ydf-browser" || goto :fail
  "%BUILD_VENV%\Scripts\pip" install -q openpyxl PyYAML requests || goto :fail
) else (
  echo     WARNING: vendor\ydf-browser not found - replay will be unavailable
)

echo ==^> [2/8] PyInstaller bundle of the recorder (includes playwright node driver)
if exist "%PYI_DIST%" rmdir /s /q "%PYI_DIST%"
if exist "%PYI_WORK%" rmdir /s /q "%PYI_WORK%"
set PYINSTALLER_CONFIG_DIR=%ROOT%\dist\_pyi_cache
"%BUILD_VENV%\Scripts\pyinstaller" desktop\ydf-recorder.spec ^
  --noconfirm --distpath "%PYI_DIST%" --workpath "%PYI_WORK%" --clean > "%PYI_WORK%.log" 2>&1
if errorlevel 1 (
  echo PyInstaller failed. Tail of log:
  powershell -NoProfile -Command "Get-Content -Tail 40 '%PYI_WORK%.log'"
  goto :fail
)
if not exist "%PYI_DIST%\YonDiFRecorder\YonDiFRecorder.exe" (
  echo Bundle executable not found: %PYI_DIST%\YonDiFRecorder\YonDiFRecorder.exe
  goto :fail
)

echo ==^> [3/8] Assemble distribution folder
if exist "%OUTDIR%" rmdir /s /q "%OUTDIR%"
mkdir "%OUTDIR%"
xcopy /e /i /q "%PYI_DIST%\YonDiFRecorder" "%APPDIR%" || goto :fail

echo ==^> [4/8] Embedded Chromium
if "%SKIP_BROWSERS%"=="0" (
  echo     downloading chromium + headless shell, one time ~250MB
  set PLAYWRIGHT_BROWSERS_PATH=%APPDIR%\chromium
  "%BUILD_VENV%\Scripts\python" -m playwright install chromium chromium-headless-shell || goto :fail
) else (
  if exist "%CHROMIUM_KEEP%" (
    echo     reusing dist\_chromium
    xcopy /e /i /q "%CHROMIUM_KEEP%" "%APPDIR%\chromium" || goto :fail
  ) else (
    echo     WARNING: --skip-browsers given but dist\_chromium not found
    echo     Recording will fail until chromium is present.
  )
)

echo ==^> [5/8] Embedded player (ydf-browser CLI, used by replay)
if exist "%ROOT%\vendor\ydf-browser\pyproject.toml" (
  "%BUILD_VENV%\Scripts\pyinstaller" desktop\ydfbrowser-cli.spec ^
    --noconfirm --distpath "%PYI_DIST%" --workpath "%PYI_WORK%" > nul 2>&1
  if exist "%PYI_DIST%\ydfbrowser-cli" (
    xcopy /e /i /q "%PYI_DIST%\ydfbrowser-cli" "%APPDIR%\ydfbrowser-cli" > nul
    echo     ydfbrowser-cli bundled
  ) else (
    echo     WARNING: ydfbrowser-cli build failed - recording still works, replay will not
  )
)

echo ==^> [6/8] Version marker
"%BUILD_VENV%\Scripts\python" -c "import ydf_recorder; print(ydf_recorder.__version__)" > "%OUTDIR%\version.txt"

echo ==^> [7/8] First-run notes
> "%OUTDIR%\README.txt" echo YonDiF Recorder - Windows build
>> "%OUTDIR%\README.txt" echo.
>> "%OUTDIR%\README.txt" echo 1. Double-click YonDiFRecorder\YonDiFRecorder.exe
>> "%OUTDIR%\README.txt" echo 2. On the Environment tab fill base_url / tenant / default_org
>> "%OUTDIR%\README.txt" echo    / username / password, then click Save
>> "%OUTDIR%\README.txt" echo 3. Record tab: pick the environment, set the menu path, start
>> "%OUTDIR%\README.txt" echo 4. Replay tab: pick a YAML, inject file variables if needed
>> "%OUTDIR%\README.txt" echo.
>> "%OUTDIR%\README.txt" echo Config lives in %%USERPROFILE%%\.ydf-recorder\env.yaml
>> "%OUTDIR%\README.txt" echo Recordings go to %%USERPROFILE%%\Downloads\ydf-recordings\
>> "%OUTDIR%\README.txt" echo Do not move YonDiFRecorder.exe away from its folder -
>> "%OUTDIR%\README.txt" echo it needs _internal\ , chromium\ and ydfbrowser-cli\ next to it.
>> "%OUTDIR%\README.txt" echo.
>> "%OUTDIR%\README.txt" echo Tip: unzip to a path without Chinese characters or spaces
>> "%OUTDIR%\README.txt" echo (e.g. D:\Tools\YonDiF-Recorder) - Chromium handles such paths
>> "%OUTDIR%\README.txt" echo poorly on some Windows setups. Always unzip first; do not run
>> "%OUTDIR%\README.txt" echo the exe from inside the .zip preview.

echo ==^> [8/8] Zip
if exist "%OUTDIR%.zip" del /q "%OUTDIR%.zip"
powershell -NoProfile -Command "Compress-Archive -Path '%OUTDIR%' -DestinationPath '%OUTDIR%.zip' -Force"
if errorlevel 1 (
  echo WARNING: zip failed, ship the folder instead: %OUTDIR%
)

echo.
echo Done.
echo   Folder: %OUTDIR%
echo   Zip   : %OUTDIR%.zip
echo End users: unzip anywhere, double-click YonDiFRecorder\YonDiFRecorder.exe
exit /b 0

:fail
echo.
echo BUILD FAILED
exit /b 1
