@echo off
echo ===================================================
echo   Installing Network Monitor Prerequisites...
echo ===================================================
echo.
echo Step 1: Checking for Python...
py --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed!
    echo Please install Python 3 from the Microsoft Store and try again.
    pause
    exit /b
)

echo Step 2: Creating Virtual Environment...
py -m venv venv

echo Step 3: Installing required packages... (This depends on your internet speed)
.\venv\Scripts\python.exe -m pip install -r backend\requirements.txt

echo.
echo ===================================================
echo   INSTALLATION COMPLETE!
echo   You can now double-click 'start.bat' to run the tool.
echo ===================================================
pause
