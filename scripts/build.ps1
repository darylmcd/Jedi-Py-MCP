param(
	[switch]$OneFile,
	[switch]$Clean
)

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

$null = & $pythonExe -m PyInstaller --version 2>$null
if ($LASTEXITCODE -ne 0) {
	throw "PyInstaller is not installed. Run: pip install -e .[build] or pip install -r requirements.txt"
}

$distDir = Join-Path $repoRoot "dist"
$buildDir = Join-Path $repoRoot "build"
$specFile = Join-Path $repoRoot "python-refactor-mcp.spec"

if ($Clean) {
	foreach ($path in @($distDir, $buildDir, $specFile)) {
		if (Test-Path $path) {
			Remove-Item $path -Recurse -Force
		}
	}
}

$entryPoint = Join-Path $repoRoot "src\python_refactor_mcp\__main__.py"
$modeFlag = if ($OneFile) { "--onefile" } else { "--onedir" }

$arguments = @(
	"-m",
	"PyInstaller",
	"--noconfirm",
	"--clean",
	$modeFlag,
	"--exclude-module",
	"tzdata",
	"--name",
	"python-refactor-mcp",
	"--paths",
	(Join-Path $repoRoot "src"),
	"--collect-submodules",
	"python_refactor_mcp",
	"--collect-submodules",
	"jedi",
	"--collect-submodules",
	"rope",
	$entryPoint
)

Write-Host "Building python-refactor-mcp executable..."
Push-Location $repoRoot
$previousPythonWarnings = $env:PYTHONWARNINGS
$previousSourceDateEpoch = $env:SOURCE_DATE_EPOCH
# SOURCE_DATE_EPOCH: tells PyInstaller to use a fixed reproducible PE timestamp,
# avoiding the OSError(22) 'Invalid argument' warning from set_exe_build_timestamp
# on some Windows / Python 3.14 combinations.
$env:PYTHONWARNINGS = "ignore:Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.:UserWarning"
$env:SOURCE_DATE_EPOCH = "1"
try {
	& $pythonExe @arguments
}
finally {
	$env:PYTHONWARNINGS = $previousPythonWarnings
	$env:SOURCE_DATE_EPOCH = $previousSourceDateEpoch
	Pop-Location
}

if ($LASTEXITCODE -ne 0) {
	throw "PyInstaller build failed."
}

$exePath = if ($OneFile) {
	Join-Path $distDir "python-refactor-mcp.exe"
} else {
	Join-Path $distDir "python-refactor-mcp\python-refactor-mcp.exe"
}

Write-Host "Build completed: $exePath"
Write-Host "Pyright is not bundled. Install the 'pyright' Python package so pyright-langserver is available on PATH."
