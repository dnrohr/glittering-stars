@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" generate.py --panic
pause
