@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
if not exist "seed_admin_app.py" (
    echo seed_admin_app.py was not found in this folder.
    echo If you use OneDrive, right-click the project folder and choose "Always keep on this device".
    pause
    exit /b 1
)

set "PY_CMD="
where py >nul 2>&1
if not errorlevel 1 (
    for %%V in (3.12 3.11 3.10 3.9 3.8) do (
        if not defined PY_CMD (
            py -%%V -c "import sys; sys.exit(0)" >nul 2>&1
            if not errorlevel 1 set "PY_CMD=py -%%V"
        )
    )
)
if not defined PY_CMD set "PY_CMD=python"

echo Using: !PY_CMD!
echo.
echo Note: Python 3.14 does not support the interactive photo cropper.
echo       This launcher prefers Python 3.8-3.12 when installed.
echo.

!PY_CMD! -m pip install -r requirements-seed-admin.txt
!PY_CMD! -m streamlit run seed_admin_app.py
pause
