@echo off
setlocal

set "REPO_ROOT=%~dp0"
set "BUILD_SCRIPT=%REPO_ROOT%scripts\build.ps1"

if not exist "%BUILD_SCRIPT%" (
    echo Build script not found: %BUILD_SCRIPT%
    exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%BUILD_SCRIPT%" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo Build failed with exit code %EXIT_CODE%.
)

exit /b %EXIT_CODE%
