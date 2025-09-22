@echo off
setlocal

REM Check if a version tag is provided
if "%~1"=="" (
    echo Usage: %0 vX.Y.Z
    echo Example: %0 v1.0.6
    exit /b 1
)
set "VERSION=%~1"

REM Check for .env file
if not exist .env (
    echo Error: .env file not found.
    echo Please create a .env file with GH_TOKEN=your_token
    exit /b 1
)

REM Load GH_TOKEN from .env file
for /f "tokens=1,* delims==" %%a in ('findstr /B "GH_TOKEN=" .env') do (
    if "%%a"=="GH_TOKEN" set "GH_TOKEN=%%b"
)

REM Check if GH_TOKEN was loaded
if not defined GH_TOKEN (
    echo Error: GH_TOKEN not found in .env file.
    echo Make sure the .env file contains a line like: GH_TOKEN=ghp_...
    exit /b 1
)

echo --- Pushing changes to main ---
REM Use -c credential.helper= and the explicit user:token format
git -c credential.helper= push https://marffinn:%GH_TOKEN%@github.com/marffinn/u-qw-sb.git main
if %errorlevel% neq 0 (
    echo Failed to push to main. Aborting.
    exit /b %errorlevel%
)

echo.
echo --- Creating and pushing tag %VERSION% ---
git tag %VERSION%
REM Use -c credential.helper= and the explicit user:token format
git -c credential.helper= push https://marffinn:%GH_TOKEN%@github.com/marffinn/u-qw-sb.git %VERSION%
if %errorlevel% neq 0 (
    echo Failed to push tag.
    exit /b %errorlevel%
)

echo.
echo Successfully pushed main and tag %VERSION%.
endlocal