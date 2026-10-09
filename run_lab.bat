@echo off
cd /d "%~dp0"
python trust_lab.py setup --bin-dir "%USERPROFILE%\Downloads\multichain-windows-2.3.32"
if errorlevel 1 goto end
python trust_lab.py demo
:end
pause
