@echo off
pushd "%~dp0"

if "%~1"=="" (
    echo.
    echo   GovPersona CLI
    echo   ==============
    echo   Ask any Israeli government agency a question.
    echo   The answer is saved as a Word document (.docx).
    echo.
    echo   Usage:
    echo     ask.bat --org finance_ministry -q "Your question here"
    echo     ask.bat --org central_bank -q "What is the interest rate policy?"
    echo     ask.bat --org finance_ministry -q "..." -o C:\Reports\my_report.docx
    echo.
    echo   Available agents:
    echo     finance_ministry      Ministry of Finance (משרד האוצר)
    echo     central_bank          Bank of Israel (בנק ישראל)
    echo     securities_authority  Israel Securities Authority (רשות ניירות ערך)
    echo.
    echo   The output .docx is saved in this folder by default.
    echo.
    pause
    goto :end
)

python ask_govpersona.py %*

:end
popd
pause
