@echo off
setlocal
cd /d "%~dp0"
if not exist "seed_admin_app.py" (
    echo seed_admin_app.py was not found in this folder.
    echo If you use OneDrive, right-click the project folder and choose "Always keep on this device".
    pause
    exit /b 1
)
python -m pip install -r requirements.txt
python -m streamlit run seed_admin_app.py
pause
