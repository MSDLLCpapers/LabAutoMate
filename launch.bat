@echo off
title LabAutoMate
cd /d "%~dp0"
echo.
echo  ============================================
echo   LabAutoMate - AI Lab Automation Assistant
echo  ============================================
echo.

rem == Step 1: ensure uv is available ================================
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [SETUP] uv not found. Installing via PowerShell...
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if %errorlevel% neq 0 (
        echo [ERROR] uv installation failed.
        echo [ERROR] Install manually: https://github.com/astral-sh/uv
        pause
        exit /b 1
    )
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    where uv >nul 2>&1
    if %errorlevel% neq 0 (
        echo [INFO] uv installed. Close this window and run launch.bat again.
        pause
        exit /b 0
    )
    echo [OK] uv installed successfully.
) else (
    for /f "tokens=*" %%v in ('uv --version') do echo [OK] %%v found.
)
echo.

rem == Step 2: create .venv if needed ================================
if not exist ".venv\Scripts\python.exe" (
    echo [SETUP] Creating virtual environment with uv...
    uv venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment already exists.
)
echo.

rem == Step 3: install LabAutoMate dependencies =====================
echo [SETUP] Syncing LabAutoMate dependencies (skipped if up to date)...
uv pip install -q --python ".venv\Scripts\python.exe" -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install LabAutoMate dependencies.
    pause
    exit /b 1
)
echo [OK] LabAutoMate dependencies ready.
echo.

rem == Step 4: install PyLabDrivers if not already installed =========
uv pip show --python ".venv\Scripts\python.exe" pylabdrivers >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] PyLabDrivers already installed.
    goto :softcheck
)

rem Try the expected sibling folder first
set "PLD_PATH=%~dp0..\PyLabDrivers"
if exist "%PLD_PATH%\setup.py" goto :install_pld

rem Sibling folder not found - ask the user
echo.
echo [SETUP] PyLabDrivers was not found automatically.
echo [SETUP] Please enter the full path to your PyLabDrivers folder.
echo [SETUP] Example: C:\Users\YourName\Documents\PyLabDrivers
echo [SETUP] Leave blank and press Enter to skip (drivers will be unavailable).
echo.
set "PLD_PATH="
set /p PLD_PATH=Path to PyLabDrivers: 
if "%PLD_PATH%"=="" (
    echo [WARN] Skipping PyLabDrivers. Automation Script driver injection unavailable.
    goto :launch
)
if not exist "%PLD_PATH%\setup.py" (
    echo [ERROR] setup.py not found at: %PLD_PATH%
    echo [ERROR] Check the path and run launch.bat again.
    pause
    exit /b 1
)

:install_pld
rem Final check - skip if already installed by any previous means
uv pip show --python ".venv\Scripts\python.exe" pylabdrivers >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] PyLabDrivers already installed, skipping reinstall.
    goto :softcheck
)
echo [SETUP] Installing PyLabDrivers from: %PLD_PATH%
uv pip install -q --python ".venv\Scripts\python.exe" -e "%PLD_PATH%"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install PyLabDrivers.
    pause
    exit /b 1
)
echo [OK] PyLabDrivers installed.
echo.

:softcheck
rem == Step 5: install pySoftcheck (required by Huber driver) =========
".venv\Scripts\python.exe" -c "import softcheck" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] pySoftcheck already installed.
    goto :launch
)
set "SC_WHEEL="
for %%F in ("%~dp0pysoftcheck-*.whl") do set "SC_WHEEL=%%~fF"
if not defined SC_WHEEL (
    echo [INFO] Optional: pySoftcheck not found. It is only needed for the Huber chiller driver.
    echo [INFO] To enable it, download the pySoftcheck wheel from Huber:
    echo [INFO]   https://www.huber-usa.com/fileadmin/user_upload/huber-online.com/Downloads/Software/pysoftcheck-3.0.0-py3-none-any.whl
    echo [INFO] Place the .whl file next to this launch.bat and run it again.
    goto :launch
)
echo [SETUP] Installing pySoftcheck from: %SC_WHEEL%
uv pip install -q --python ".venv\Scripts\python.exe" "%SC_WHEEL%"
if %errorlevel% neq 0 (
    echo [WARN] pySoftcheck installation failed. Huber driver will be unavailable.
) else (
    echo [OK] pySoftcheck installed.
)
echo.

:launch
echo.
echo [INFO] All dependencies ready.
echo [INFO] Starting LabAutoMate...
echo [INFO] Open http://localhost:8501 in your browser.
echo [INFO] Press Ctrl+C in this window to stop.
echo.
".venv\Scripts\streamlit.exe" run app.py
echo.
pause
