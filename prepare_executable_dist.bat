@echo off
setlocal

echo Preparing executable_dist directory...

:: Create executable_dist directory if it doesn't exist
if not exist "executable_dist" (
    mkdir "executable_dist"
    if %errorlevel% neq 0 (
        echo Error: Failed to create executable_dist directory.
        exit /b 1
    )
)

:: Copy BROWSANKA.exe
copy /Y "dist\BROWSANKA.exe" "executable_dist\BROWSANKA.exe"
if %errorlevel% neq 0 (
    echo Error: Failed to copy BROWSANKA.exe.
    exit /b 1
)

:: Copy favorites.json
copy /Y "favorites.json" "executable_dist\favorites.json"
if %errorlevel% neq 0 (
    echo Error: Failed to copy favorites.json.
    exit /b 1
)

:: Copy eu-sv.txt
copy /Y "eu-sv.txt" "executable_dist\eu-sv.txt"
if %errorlevel% neq 0 (
    echo Error: Failed to copy eu-sv.txt.
    exit /b 1
)

:: Copy servers_cache.json
copy /Y "servers_cache.json" "executable_dist\servers_cache.json"
if %errorlevel% neq 0 (
    echo Error: Failed to copy servers_cache.json.
    exit /b 1
)

:: Copy settings.json
copy /Y "settings.json" "executable_dist\settings.json"
if %errorlevel% neq 0 (
    echo Error: Failed to copy settings.json.
    exit /b 1
)

:: Copy uttanka.ico
copy /Y "uttanka.ico" "executable_dist\uttanka.ico"
if %errorlevel% neq 0 (
    echo Error: Failed to copy uttanka.ico.
    exit /b 1
)

echo executable_dist directory prepared successfully.
endlocal
exit /b 0