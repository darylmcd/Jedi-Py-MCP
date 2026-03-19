param()

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
	$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
	if ($null -eq $pythonCommand) {
		throw "Python was not found. Create .venv or ensure python is available on PATH."
	}

	$pythonExe = $pythonCommand.Source
}

Write-Host "Running integration tests with RUN_MCP_INTEGRATION=1..."
Push-Location $repoRoot
$previousRunIntegration = $env:RUN_MCP_INTEGRATION
$env:RUN_MCP_INTEGRATION = "1"
try {
	& $pythonExe -m pytest tests/integration/ -v
}
finally {
	$env:RUN_MCP_INTEGRATION = $previousRunIntegration
	Pop-Location
}

if ($LASTEXITCODE -ne 0) {
	throw "Integration tests failed."
}