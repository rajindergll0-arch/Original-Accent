# Original Accent installer (Windows). Run by "Install from source.cmd" - no Python needed beforehand.
# 1. Installs uv (Astral's Python manager) for this user if missing.
# 2. Copies the app to %LOCALAPPDATA%\Original Accent\app and builds its own Python 3.12 environment.
# 3. Adds Start menu and desktop shortcuts. Engines (Qwen3-TTS, Chatterbox, Whisper) are
#    installed from inside the app on first run, with progress shown.
$ErrorActionPreference = "Stop"
$src  = Split-Path -Parent $PSScriptRoot
$root = Join-Path $env:LOCALAPPDATA "OriginalAccent"
$app  = Join-Path $root "app"
$venv = Join-Path $root "app-env"

Write-Host "Original Accent setup" -ForegroundColor Cyan
if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
  Write-Warning "No NVIDIA driver found. Original Accent needs an NVIDIA GPU to make voices; it will still install."
}

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
  Write-Host "Installing uv..."
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv did not install. Check the internet connection and try again." }
}

Write-Host "Copying app to $app"
New-Item -ItemType Directory -Force -Path $app | Out-Null
robocopy $src $app /MIR /XD .git __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null

Write-Host "Creating the app's Python environment"
uv venv $venv -p 3.12 --allow-existing
if ($LASTEXITCODE -ne 0) { throw "Could not create the app environment (uv venv)." }
uv pip install -p (Join-Path $venv "Scripts\python.exe") -r (Join-Path $app "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Could not install the app's packages." }

$pyw = Join-Path $venv "Scripts\pythonw.exe"
$ws = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Desktop"))) {
  $lnk = $ws.CreateShortcut((Join-Path $dir "Original Accent.lnk"))
  $lnk.TargetPath = $pyw
  $lnk.Arguments = "-m original_accent"
  $lnk.WorkingDirectory = $app
  $lnk.IconLocation = (Join-Path $app "ui\icon.ico")
  $lnk.Description = "Local voice cloning"
  $lnk.Save()
}
Write-Host "Done. Starting Original Accent..." -ForegroundColor Green
Start-Process -FilePath $pyw -ArgumentList "-m original_accent" -WorkingDirectory $app
exit 0
