$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run uv sync --locked first. See README.md.' }
$env:PYTHONUTF8 = '1'
$env:GRADIO_ANALYTICS_ENABLED = 'False'
$env:CAMPUS_NOW = '2026-10-20T09:00:00+08:00'
$env:CAMPUS_DB = Join-Path $PSScriptRoot 'data/demo.sqlite'
if (-not (Test-Path -LiteralPath $env:CAMPUS_DB)) {
    & $pythonExe -m scripts.seed --base-date 2026-10-20
    if ($LASTEXITCODE -ne 0) { throw 'Seed failed' }
}
Write-Host 'Open the local URL printed below. Ctrl+C stops the demo. Fixed simulated clock: 2026-10-20 09:00 UTC+08.'
& $pythonExe -m app.ui
