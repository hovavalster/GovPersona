@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo  ============================================================
echo    GovPersona  —  Launcher
echo  ============================================================
echo.

:: ── Find Rscript.exe ────────────────────────────────────────────────────────
set RSCRIPT=
for /d %%v in ("C:\Program Files\R\R-4.*") do set RSCRIPT=%%v\bin\Rscript.exe
if not exist "%RSCRIPT%" (
  echo  ERROR: R not found in C:\Program Files\R\
  echo  Install R from https://cran.r-project.org/ and try again.
  pause & exit /b 1
)
echo  Using R: %RSCRIPT%

:: ── Start Shiny app in a separate window ────────────────────────────────────
echo.
echo  [1/2] Starting Shiny app on port 4747...
start "GovPersona App" "%RSCRIPT%" -e "shiny::runApp('.', port=4747, launch.browser=FALSE)"

:: Wait for app to be ready
echo  Waiting for app to start...
timeout /t 6 /nobreak >nul

:: ── Download cloudflared if missing ─────────────────────────────────────────
if not exist cloudflared.exe (
  echo.
  echo  [2/2] Downloading Cloudflare Tunnel tool (one time only, ~30 MB)...
  powershell -NoProfile -Command ^
    "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe' -UseBasicParsing"
  if not exist cloudflared.exe (
    echo  ERROR: Download failed. Check your internet connection.
    pause & exit /b 1
  )
  echo  Downloaded cloudflared.exe
)

:: ── Start tunnel ────────────────────────────────────────────────────────────
echo.
echo  [2/2] Opening Cloudflare Tunnel...
echo.
echo  ============================================================
echo   WATCH FOR A LINE LIKE:
echo.
echo     https://xxxx-xxxx-xxxx.trycloudflare.com
echo.
echo   Copy that URL and open it in any browser — on any device!
echo   (It changes each time you restart)
echo  ============================================================
echo.

cloudflared tunnel --url http://127.0.0.1:4747

echo.
echo  Tunnel closed. Press any key to exit.
pause >nul
