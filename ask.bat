@echo off
pushd "%~dp0"

if "%~1"=="" (
    echo.
    echo   GovPersona CLI - Ask a question
    echo.
    echo   Usage:
    echo     ask.bat --org finance_ministry -q "Your question here"
    echo     ask.bat --org central_bank -q "What is the interest rate policy?"
    echo     ask.bat --org finance_ministry -q "..." -o my_report.docx
    echo.
    echo   Available agents:
    echo     finance_ministry      Ministry of Finance
    echo     central_bank          Bank of Israel
    echo     securities_authority  Israel Securities Authority
    echo.
    echo   The answer is saved as a Word document (.docx) in this folder.
    echo.
    pause
    goto :end
)

python ask_govpersona.py %*

:end
popd
pause
