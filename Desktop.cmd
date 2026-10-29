@echo off
cd /d "%~dp0"
if exist "%~dp0dist\GlitteringStars\GlitteringStars.exe" (
    start "Glittering Stars" "%~dp0dist\GlitteringStars\GlitteringStars.exe"
) else (
    if exist "%~dp0.venv\Scripts\pythonw.exe" (
        start "Glittering Stars" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0desktop.py"
    ) else (
        start "Glittering Stars" pythonw "%~dp0desktop.py"
    )
)
