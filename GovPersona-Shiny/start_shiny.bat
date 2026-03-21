@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: Find newest R installation automatically
set RSCRIPT=
for /d %%v in ("C:\Program Files\R\R-4.*") do set RSCRIPT=%%v\bin\Rscript.exe

if not exist "%RSCRIPT%" (
  echo  ERROR: R not found in C:\Program Files\R\
  echo  Install R from https://cran.r-project.org/ and try again.
  pause & exit /b 1
)

echo.
echo  Starting GovPersona Shiny (local only)...
echo  Open your browser at: http://127.0.0.1:4747
echo.
"%RSCRIPT%" -e "shiny::runApp('.', port=4747, launch.browser=TRUE)"
if errorlevel 1 (
  echo.
  echo  ERROR: Could not start. Run install_shiny.R first.
  pause
)
