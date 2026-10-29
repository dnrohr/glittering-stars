$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = Join-Path $root '.venv\Scripts\python.exe'
$env:QT_QPA_PLATFORM = 'windows'
& $python (Join-Path $root 'desktop.py') --preview --close-after-ms 1200
if ($LASTEXITCODE -ne 0) { throw "Qt launch spike failed: $LASTEXITCODE" }
Write-Output "Native Windows Qt window shown and closed with exit code $LASTEXITCODE"
