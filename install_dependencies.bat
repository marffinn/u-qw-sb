@echo off

echo Installing dependencies...

:: Check if pip is installed
python -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo pip is not installed. Please install pip first.
    exit /b 1
)

:: Install dependencies from requirements.txt
python -m pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo Failed to install dependencies.
    exit /b 1
)

echo Dependencies installed successfully.
pause
