param(
    [string]$Python = (Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"),
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SpecFile = Join-Path $PSScriptRoot "GlitteringStars.spec"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python was not found at '$Python'. Install the desktop requirements or pass -Python."
}
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $RepoRoot "dist\packaged"
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
$WorkDirectory = Join-Path $RepoRoot "build\packaged-work"
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
New-Item -ItemType Directory -Force -Path $WorkDirectory | Out-Null

& $Python -m PyInstaller --noconfirm --clean --workpath $WorkDirectory `
    --distpath $OutputDirectory $SpecFile
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}
$AppDirectory = Join-Path $OutputDirectory "GlitteringStars"
$Executable = Join-Path $AppDirectory "GlitteringStars.exe"
if (-not (Test-Path -LiteralPath $Executable)) {
    throw "Build completed without expected executable: $Executable"
}
Write-Host "Built: $Executable"
