# Jedi-Py-MCP — Python MCP server for code analysis and refactoring
# Requires: https://github.com/casey/just — plus Python 3.14+, pyright package

# Variables
python := ".venv/Scripts/python.exe"
converter_format_files := "src/python_refactor_mcp/tools/refactoring/_converter_preflight.py src/python_refactor_mcp/tools/refactoring/dataclass_conversion.py src/python_refactor_mcp/tools/refactoring/typed_dict_conversion.py src/python_refactor_mcp/tools/refactoring/pydantic_conversion.py tests/unit/test_semantic_converters.py"

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

# Run unit + contract tests (both are fast, in-process)
test:
    {{ python }} -m pytest tests/unit/ tests/contract/ -v

# Run integration tests
test-integration:
    pwsh.exe -NoProfile -File scripts/test-integration.ps1

# Run all tests (unit + integration)
test-all: test test-integration

# --- Lint / Format ---

# Run ruff linter
lint:
    {{ python }} -m ruff check .

# Enforce stable formatting on the semantic converter surface
format-check-converters:
    {{ python }} -m ruff format --check {{ converter_format_files }}

# Validate pending changelog fragments (CI sets CHANGELOG_BASE_REF on PRs)
changelog-check:
    {{ python }} scripts/changelog_fragments.py

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

# Bump release metadata, refresh uv.lock, reinstall into the client Python, and verify the CLI
bump-reinstall version target_python="python":
    {{ python }} scripts/bump_reinstall.py "{{ version }}" --target-python "{{ target_python }}"

# Repair or refresh the current locked release without changing its version
reinstall target_python="python":
    {{ python }} scripts/bump_reinstall.py --reinstall-only --target-python "{{ target_python }}"

# --- Aggregates ---

# Fast local sanity check before pushing
validate: changelog-check lint format-check-converters typecheck test

# Local equivalent of CI pipeline (mirrors .github/workflows/ci.yml)
ci: changelog-check lint format-check-converters typecheck typecheck-mypy test test-integration

# Everything including all test suites
full: changelog-check lint format-check-converters typecheck typecheck-mypy test test-integration

# --- Clean ---

# Remove build artifacts
clean:
    pwsh.exe -NoProfile -Command "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist"

# Remove all generated artifacts including caches
clean-all: clean
    pwsh.exe -NoProfile -Command "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue .mypy_cache, .pytest_cache, .ruff_cache"
