@echo off
pushd "%~dp0"
echo ================================================
echo   GovPersona CLI - First-time setup
echo ================================================
echo.
echo Installing anthropic and python-docx from local packages...
echo (No internet connection required)
echo.

python -m pip install --no-index --find-links="%~dp0whl_packages" anthropic python-docx

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Installation failed.
    echo.
    echo Possible reasons:
    echo   - The whl_packages\ folder is missing or incomplete
    echo   - Python is not in PATH  (try: py -m pip install ... instead)
    echo.
    echo Ask your GovPersona contact to re-download the whl_packages folder.
) else (
    echo.
    echo ================================================
    echo   Setup complete!
    echo.
    echo   To ask a question, run ask.bat or:
    echo   python ask_govpersona.py --org finance_ministry -q "Your question here"
    echo ================================================
)

popd
pause
