@echo off
pushd "%~dp0"
echo ================================================
echo   GovPersona CLI - First-time setup
echo   (Run this ONCE on the work computer)
echo ================================================
echo.
echo Installing packages from local whl_packages folder...
echo No internet required.
echo.

python -m pip install --no-index --find-links="%~dp0whl_packages" anthropic python-docx

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Installation failed.
    echo.
    echo Try using 'py' instead of 'python':
    echo   py -m pip install --no-index --find-links=whl_packages anthropic python-docx
    echo.
) else (
    echo.
    echo ================================================
    echo   Setup complete!
    echo.
    echo   To ask a question:
    echo     ask.bat --org finance_ministry -q "Your question"
    echo.
    echo   Available agents:
    echo     finance_ministry      Ministry of Finance
    echo     central_bank          Bank of Israel
    echo     securities_authority  Israel Securities Authority
    echo ================================================
)

popd
pause
