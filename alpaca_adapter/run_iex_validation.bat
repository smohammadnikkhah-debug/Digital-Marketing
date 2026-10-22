@echo off
setlocal EnableExtensions
REM StockAnalysis Alpaca IEX Validation Runner (Stage D2.3B.5)
REM Strict Read-Only — three samples ~30s apart; execution-suitability uses 0.5% spread gate
REM Preserves prior evidence files (e.g. iex_validation_20261023_0045.*) by using a new dated stem.

set "REPO=C:\Users\zeiva\OneDrive\Desktop\Project\Digital Marketing"
set "PYTHON=C:\Users\zeiva\AppData\Local\Python\bin\python.exe"
set "EVIDENCE=%REPO%\alpaca_adapter\evidence"
set "STEM=iex_validation_20261024_0045"
set "JSON=%EVIDENCE%\%STEM%.json"
set "LOG=%EVIDENCE%\%STEM%.log"

cd /d "%REPO%"
if errorlevel 1 (
  echo FATAL: cannot cd to repo >> "%LOG%"
  exit /b 1
)

if not exist "%EVIDENCE%" mkdir "%EVIDENCE%"

set "PYTHONPATH=%REPO%;%REPO%\stockanalysis\web_app\backend"

echo ===== Stage D2.3B.5 IEX validation start %DATE% %TIME% =====>> "%LOG%"
echo Repo: %REPO%>> "%LOG%"
echo Python: %PYTHON%>> "%LOG%"
echo Samples: 3 x 30s>> "%LOG%"
echo Output JSON: %JSON%>> "%LOG%"

"%PYTHON%" "%REPO%\alpaca_adapter\alpaca_verification.py" --samples 3 --sample-interval-seconds 30 --symbols AAPL,MSFT,SPY --output-json "%JSON%" >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"

echo ===== Stage D2.3B.5 IEX validation end rc=%RC% %DATE% %TIME% =====>> "%LOG%"
exit /b %RC%
