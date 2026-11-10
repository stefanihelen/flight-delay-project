@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo [1/2] Checking current source sizes from manifests...
python crawler\audit_source_sizes.py
if errorlevel 1 goto failed
echo [2/2] Exporting local raw samples...
python crawler\export_raw_samples.py
if errorlevel 1 goto failed
echo.
echo Completed. Read data\samples\raw\member1\README.md
pause
exit /b 0
:failed
echo.
echo Stopped. Please copy the error message. Original raw files were preserved.
pause
exit /b 1
