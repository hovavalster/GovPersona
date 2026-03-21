@echo off
pushd "%~dp0"
echo Starting GovPersona on http://localhost:8502 ...
streamlit run app.py --server.port 8502
pause
popd
