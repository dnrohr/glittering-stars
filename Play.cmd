@echo off
cd /d "%~dp0"
tasklist /FI "IMAGENAME eq loopMIDI.exe" /NH | find /I "loopMIDI.exe" >nul
if errorlevel 1 start "" "C:\Program Files (x86)\Tobias Erichsen\loopMIDI\loopMIDI.exe"
tasklist /FI "IMAGENAME eq Surge XT.exe" /NH | find /I "Surge XT.exe" >nul
if errorlevel 1 start "" "C:\Program Files\Surge Synth Team\Surge XT\Surge XT.exe"
timeout /t 3 /nobreak >nul
".venv\Scripts\python.exe" generate.py %*
pause
