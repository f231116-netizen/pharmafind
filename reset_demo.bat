@echo off
REM Start over with fresh demo data. Only use this when you WANT a clean start.
REM Deletes: all reservations, prescriptions, stock/price changes, search history, drivers' jobs.
REM Keeps:   customer accounts (phone numbers, names).
REM Close start_showcase.bat (the black window) first.
cd /d "%~dp0"
call venv\Scripts\activate
echo.
echo  This DELETES all reservations, prescriptions and stock changes,
echo  and makes fresh demo data. Customer accounts are kept.
echo  Close the showcase window (start_showcase.bat) first.
echo.
set /p answer=Type YES and press Enter to start over:
if /I not "%answer%"=="YES" (
  echo Nothing was changed.
  pause
  exit /b
)
python seed.py
echo.
echo Done. Now double-click start_showcase.bat again.
pause
