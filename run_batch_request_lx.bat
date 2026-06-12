@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" batch_request_lx.py %1
) else (
    python batch_request_lx.py %1
)
exit /b %ERRORLEVEL%
