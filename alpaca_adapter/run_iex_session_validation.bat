@echo off
setlocal EnableExtensions
REM Stage D2.3B.6 — parameterized read-only IEX session validation
REM Usage: run_iex_session_validation.bat <session_id> <minutes_after_open> <stem>
REM Example: run_iex_session_validation.bat open_plus_15 15 iex_validation_20261026_0945ET_open15

if "%~1"=="" (
  echo FATAL: session_id required
  exit /b 1
)
if "%~2"=="" (
  echo FATAL: minutes_after_open required
  exit /b 1
)
if "%~3"=="" (
  echo FATAL: evidence stem required
  exit /b 1
)

set "SESSION_ID=%~1"
set "MINUTES_AFTER_OPEN=%~2"
set "STEM=%~3"
set "SESSION_LABEL=%SESSION_ID% (+%MINUTES_AFTER_OPEN% min after US open)"

set "REPO=C:\Users\zeiva\OneDrive\Desktop\Project\Digital Marketing"
set "PYTHON=C:\Users\zeiva\AppData\Local\Python\bin\python.exe"
set "EVIDENCE=%REPO%\alpaca_adapter\evidence"
set "JSON=%EVIDENCE%\%STEM%.json"
set "LOG=%EVIDENCE%\%STEM%.log"

cd /d "%REPO%"
if errorlevel 1 (
  echo FATAL: cannot cd to repo >> "%LOG%"
  exit /b 1
)

if not exist "%EVIDENCE%" mkdir "%EVIDENCE%"

set "PYTHONPATH=%REPO%;%REPO%\stockanalysis\web_app\backend"

echo ===== D2.3B.6 session=%SESSION_ID% start %DATE% %TIME% =====>> "%LOG%"
echo Repo: %REPO%>> "%LOG%"
echo Python: %PYTHON%>> "%LOG%"
echo Samples: 3 x 30s>> "%LOG%"
echo Session: %SESSION_ID% minutes_after_open=%MINUTES_AFTER_OPEN%>> "%LOG%"
echo Output JSON: %JSON%>> "%LOG%"

"%PYTHON%" "%REPO%\alpaca_adapter\alpaca_verification.py" ^
  --samples 3 ^
  --sample-interval-seconds 30 ^
  --symbols AAPL,MSFT,SPY ^
  --session-id "%SESSION_ID%" ^
  --session-label "%SESSION_LABEL%" ^
  --minutes-after-open %MINUTES_AFTER_OPEN% ^
  --output-json "%JSON%" >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"

echo ===== D2.3B.6 session=%SESSION_ID% end rc=%RC% %DATE% %TIME% =====>> "%LOG%"
exit /b %RC%
