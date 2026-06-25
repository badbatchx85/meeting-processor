# Build the Meeting Processor Windows NSIS installer.
#
# Lite strategy (mirrors macOS): bundle the raw meeting_processor source + built
# SPA; the app bootstraps a venv + pip install on first run. The Python payload
# is declared in tauri.windows.conf.json `bundle.resources` (NSIS must include
# it during the build, unlike the macOS post-build inject).
#
# `npm run build` emits the SPA into meeting_processor/web/spa (per vite.config),
# so staging the meeting_processor/ tree below captures the freshly built SPA.
$ErrorActionPreference = "Stop"
# $ErrorActionPreference="Stop" does NOT halt on a non-zero exit from a native
# command (npm/npx) under Windows PowerShell 5.1, so check $LASTEXITCODE
# explicitly after each — otherwise a failed SPA/tauri build ships silently.

$Root    = (Resolve-Path "$PSScriptRoot\..").Path
$Desktop = Join-Path $Root "desktop"
$Tauri   = Join-Path $Desktop "src-tauri"
$Res     = Join-Path $Tauri "resources"

Write-Host "==> 1/3 Building SPA"
Push-Location (Join-Path $Root "frontend")
if (-not (Test-Path "node_modules")) {
    npm ci
    if ($LASTEXITCODE) { throw "npm ci failed ($LASTEXITCODE)" }
}
npm run build
if ($LASTEXITCODE) { throw "npm run build failed ($LASTEXITCODE)" }
Pop-Location

Write-Host "==> 2/3 Staging Python payload into resources/"
New-Item -ItemType Directory -Force -Path (Join-Path $Res "meeting_processor") | Out-Null
robocopy (Join-Path $Root "meeting_processor") (Join-Path $Res "meeting_processor") /MIR /XD __pycache__ /XF *.pyc | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" } else { $global:LASTEXITCODE = 0 }
Copy-Item (Join-Path $Root "requirements.txt") (Join-Path $Res "requirements.txt") -Force

Write-Host "==> 3/3 tauri build (nsis)"
Push-Location $Tauri
npx --yes "@tauri-apps/cli@^2" build --config tauri.windows.conf.json --bundles nsis
if ($LASTEXITCODE) { throw "tauri build failed ($LASTEXITCODE)" }
Pop-Location

Write-Host "Done. Installer:"
Get-ChildItem (Join-Path $Tauri "target\release\bundle\nsis\*-setup.exe") | ForEach-Object { Write-Host $_.FullName }
