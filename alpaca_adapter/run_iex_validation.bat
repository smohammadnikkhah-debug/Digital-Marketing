@echo off
REM StockAnalysis Alpaca IEX Overnight Verification Runner
REM Strict Read-Only Market Hours Validation
cd /d "C:\Users\zeiva\OneDrive\Desktop\Project\Digital Marketing"
"C:\Users\zeiva\AppData\Local\Python\bin\python.exe" "C:\Users\zeiva\OneDrive\Desktop\Project\Digital Marketing\alpaca_adapter\alpaca_verification.py" --output-json "C:\Users\zeiva\OneDrive\Desktop\Project\Digital Marketing\alpaca_adapter\evidence\iex_validation_20261023_0045.json" >> "C:\Users\zeiva\OneDrive\Desktop\Project\Digital Marketing\alpaca_adapter\evidence\iex_validation_20261023_0045.log" 2>&1
