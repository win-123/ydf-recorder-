@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "RELEASE_ROOT=%SCRIPT_DIR%.."

if /I not "%~1"=="update" if /I not "%YDF_BROWSER_AUTO_UPDATE%"=="0" (
  if exist "%RELEASE_ROOT%\runtime\.venv\Scripts\python.exe" (
    start "" /b "%RELEASE_ROOT%\runtime\.venv\Scripts\python.exe" -m ydf_browser.updater --background >nul 2>&1
  ) else if exist "%RELEASE_ROOT%\runtime\venv\Scripts\python.exe" (
    start "" /b "%RELEASE_ROOT%\runtime\venv\Scripts\python.exe" -m ydf_browser.updater --background >nul 2>&1
  )
)

if exist "%RELEASE_ROOT%\runtime\.venv\Scripts\python.exe" (
  "%RELEASE_ROOT%\runtime\.venv\Scripts\python.exe" -m ydf_browser.cli %*
  exit /b %ERRORLEVEL%
)

if exist "%RELEASE_ROOT%\runtime\venv\Scripts\python.exe" (
  "%RELEASE_ROOT%\runtime\venv\Scripts\python.exe" -m ydf_browser.cli %*
  exit /b %ERRORLEVEL%
)

echo ydf-browser runtime is not installed under %RELEASE_ROOT%\runtime. 1>&2
echo Run scripts\install-runtime.ps1 from this release package. 1>&2
exit /b 127
