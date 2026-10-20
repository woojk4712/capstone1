@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Project .venv\Scripts\python.exe is missing.
  exit /b 1
)
".venv\Scripts\python.exe" scripts\diagnose_local_api.py
set "DIAGNOSIS_EXIT=%ERRORLEVEL%"
echo.
echo [WinHTTP Proxy - local console only, not saved in the report]
netsh winhttp show proxy
exit /b %DIAGNOSIS_EXIT%
