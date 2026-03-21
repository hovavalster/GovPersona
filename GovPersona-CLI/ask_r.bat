@echo off
pushd "%~dp0"

if "%~1"=="" (
    echo.
    echo   GovPersona CLI (R version)
    echo   ==========================
    echo   Asks a government agency a question and saves the answer as a Word document.
    echo.
    echo   Usage:
    echo     ask_r.bat --org finance_ministry -q "Your question here"
    echo     ask_r.bat --org central_bank -q "What is the interest rate policy?"
    echo     ask_r.bat --org finance_ministry -q "..." -o C:\Reports\answer.docx
    echo.
    echo   Available agents:
    echo     finance_ministry      Ministry of Finance
    echo     central_bank          Bank of Israel
    echo     securities_authority  Israel Securities Authority
    echo.
    pause
    goto :end
)

Rscript "%~dp0ask_govpersona.R" %*

:end
popd
pause
