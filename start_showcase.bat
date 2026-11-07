@echo off
REM Showcase day: double-click this file to start PharmaFind for phones.
cd /d "%~dp0"
call venv\Scripts\activate
python showcase.py
pause
