@echo off
pushd "%~dp0"
echo ================================================
echo   GovPersona CLI - Download offline packages
echo   Run this on your HOME laptop (needs internet)
echo ================================================
echo.
echo Downloading anthropic + python-docx and all their dependencies...
echo Output: GovPersona-CLI\whl_packages\
echo.

if not exist "GovPersona-CLI\whl_packages" mkdir "GovPersona-CLI\whl_packages"

python -m pip download anthropic python-docx --dest "GovPersona-CLI\whl_packages"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Download failed. Make sure you have internet access.
) else (
    echo.
    echo ================================================
    echo   Done! Packages saved to GovPersona-CLI\whl_packages\
    echo.
    echo   NEXT STEPS:
    echo   1. Run: python export_kb.py   (exports the knowledge base)
    echo   2. Copy GovPersona-CLI\ folder to USB / email
    echo   3. On work computer: run install.bat, then ask.bat
    echo ================================================
)

popd
pause
