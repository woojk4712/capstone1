@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: Project .venv is missing. Run scripts\run_backend.ps1 -Install first.
 exit /b 1
)
".venv\Scripts\python.exe" scripts\start_local.py %*
exit /b %errorlevel%
