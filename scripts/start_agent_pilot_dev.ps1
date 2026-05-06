[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[Agent-Pilot] $Message" -ForegroundColor Cyan
}

function Fail-Step {
    param([string]$Message)
    Write-Host "[Agent-Pilot] $Message" -ForegroundColor Red
    exit 1
}

function Assert-PathExists {
    param(
        [string]$Path,
        [string]$FailureMessage
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        Fail-Step $FailureMessage
    }
}

function Assert-CommandExists {
    param(
        [string]$CommandName,
        [string]$FailureMessage
    )

    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        Fail-Step $FailureMessage
    }
}

function Start-AgentPilotWindow {
    param(
        [string]$Title,
        [string]$WorkingDirectory,
        [string]$Command
    )

    $escapedTitle = $Title.Replace("'", "''")
    $escapedWorkingDirectory = $WorkingDirectory.Replace("'", "''")

    $wrappedCommand = @'
$Host.UI.RawUI.WindowTitle = '__TITLE__'
Set-Location -LiteralPath '__WORKDIR__'
__COMMAND__
'@
    $wrappedCommand = $wrappedCommand.Replace("__TITLE__", $escapedTitle)
    $wrappedCommand = $wrappedCommand.Replace("__WORKDIR__", $escapedWorkingDirectory)
    $wrappedCommand = $wrappedCommand.Replace("__COMMAND__", $Command)

    Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command", $wrappedCommand
    ) -WorkingDirectory $WorkingDirectory | Out-Null
}

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$apiPython = Join-Path $workspaceRoot ".venv\Scripts\python.exe"
$cockpitDir = Join-Path $workspaceRoot "clients\agent_pilot_cockpit"
$cockpitNodeModules = Join-Path $cockpitDir "node_modules"
$flutterDir = Join-Path $workspaceRoot "clients\agent_pilot_flutter"
$flutterWindowsDir = Join-Path $flutterDir "windows"

Write-Step "Checking daily development prerequisites..."

Assert-PathExists -Path $apiPython -FailureMessage "Missing .venv Python at '$apiPython'. Please set up the backend environment first."
Assert-PathExists -Path $cockpitNodeModules -FailureMessage "Cockpit dependencies are missing. Run 'npm install' in 'clients\\agent_pilot_cockpit' first."
Assert-CommandExists -CommandName "flutter" -FailureMessage "Flutter is not available on PATH. Install Flutter and verify it with 'flutter doctor'."
Assert-PathExists -Path $flutterWindowsDir -FailureMessage "Flutter Windows scaffold is missing. Run 'flutter create . --platforms=windows,android' in 'clients\\agent_pilot_flutter' first."

Write-Step "Launching backend, cockpit, and Flutter Windows companion..."

Start-AgentPilotWindow `
    -Title "Agent-Pilot API" `
    -WorkingDirectory $workspaceRoot `
    -Command "& '$apiPython' -m uvicorn app.main:app --reload"

Start-AgentPilotWindow `
    -Title "Agent-Pilot Cockpit" `
    -WorkingDirectory $cockpitDir `
    -Command "npm run dev"

Start-AgentPilotWindow `
    -Title "Agent-Pilot Flutter Windows" `
    -WorkingDirectory $flutterDir `
    -Command "flutter run -d windows"

Write-Host ""
Write-Host "Agent-Pilot dev stack is starting in three PowerShell windows:" -ForegroundColor Green
Write-Host "  API:      http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "  Cockpit:  http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "  Windows:  Flutter desktop window" -ForegroundColor Green
Write-Host ""
Write-Host "If Flutter Windows fails immediately, run 'flutter doctor' and install the Visual Studio C++ desktop toolchain." -ForegroundColor Yellow
Write-Host "If cockpit fails immediately, run 'npm install' in 'clients\\agent_pilot_cockpit'." -ForegroundColor Yellow
Write-Host "If the backend fails immediately, check whether port 8000 is already in use." -ForegroundColor Yellow
