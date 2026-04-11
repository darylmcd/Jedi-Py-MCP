# Jedi-Py-MCP — Python MCP server for code analysis and refactoring
# Requires: https://github.com/casey/just — plus Python 3.14+, pyright package

# Variables
python := ".venv/Scripts/python.exe"

# Cross-platform shell
set windows-shell := ["pwsh.exe", "-NoProfile", "-Command"]
set shell := ["sh", "-cu"]

# Show available recipes
default:
    @just --list

# --- Build ---

# Build PyInstaller executable (directory bundle)
build:
    {{ python }} -m PyInstaller --noconfirm --clean --onedir --exclude-module tzdata --name python-refactor-mcp --paths src --collect-submodules python_refactor_mcp --collect-submodules jedi --collect-submodules rope src/python_refactor_mcp/__main__.py

# Build PyInstaller executable via PowerShell script
build-release:
    pwsh.exe -NoProfile -File scripts/build.ps1

# Build single-file executable
build-onefile:
    pwsh.exe -NoProfile -File scripts/build.ps1 -OneFile

# --- Test ---

# Run unit tests
test:
    {{ python }} -m pytest tests/unit/ -v

# Run integration tests
test-integration:
    pwsh.exe -NoProfile -File scripts/test-integration.ps1

# Run all tests (unit + integration)
test-all: test test-integration

# --- Lint / Format ---

# Run ruff linter
lint:
    {{ python }} -m ruff check .

# Run ruff with auto-fix
lint-fix:
    {{ python }} -m ruff check . --fix

# Run Pyright type checker
typecheck:
    {{ python }} -m pyright .

# Run mypy type checker
typecheck-mypy:
    {{ python }} -m mypy .

# --- Run ---

# Run the MCP server against a workspace (pass workspace path as argument)
run workspace:
    {{ python }} -m python_refactor_mcp {{ workspace }}

# --- Aggregates ---

# Fast local sanity check before pushing
validate: lint typecheck test

# Local equivalent of CI pipeline (mirrors .github/workflows/ci.yml)
ci: lint typecheck typecheck-mypy test test-integration

# Everything including all test suites
full: lint typecheck typecheck-mypy test test-integration

# --- Clean ---

# Remove build artifacts
clean:
    pwsh.exe -NoProfile -Command "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist"

# Remove all generated artifacts including caches
clean-all: clean
    pwsh.exe -NoProfile -Command "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue .mypy_cache, .pytest_cache, .ruff_cache"
