"""AST-based security scanning for common Python vulnerability patterns."""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from python_refactor_mcp.models import SecurityFinding, SecurityScanResult

_LOGGER = logging.getLogger(__name__)

_DANGEROUS_CALLS: dict[str, tuple[str, str, str]] = {
    "eval": ("SEC001", "high", "Use of eval() can execute arbitrary code"),
    "exec": ("SEC002", "high", "Use of exec() can execute arbitrary code"),
    "compile": ("SEC003", "medium", "Use of compile() may execute arbitrary code"),
    "__import__": ("SEC004", "medium", "Dynamic import via __import__()"),
}

_DANGEROUS_ATTR_CALLS: dict[tuple[str, str], tuple[str, str, str]] = {
    ("os", "system"): ("SEC010", "high", "os.system() is vulnerable to shell injection"),
    ("os", "popen"): ("SEC011", "high", "os.popen() is vulnerable to shell injection"),
    ("pickle", "loads"): ("SEC020", "high", "pickle.loads() can execute arbitrary code during deserialization"),
    ("pickle", "load"): ("SEC021", "high", "pickle.load() can execute arbitrary code during deserialization"),
    ("yaml", "load"): ("SEC022", "medium", "yaml.load() without SafeLoader can execute arbitrary code"),
    ("marshal", "loads"): ("SEC023", "high", "marshal.loads() can execute arbitrary code"),
}

_SUBPROCESS_SHELL_FUNCS = {"call", "run", "Popen", "check_call", "check_output"}


def _scan_file(file_path: str) -> list[SecurityFinding]:
    """Scan a single Python file for security issues."""
    try:
        source = Path(file_path).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=file_path)
    except (OSError, SyntaxError):
        return []

    source_lines = source.splitlines()
    findings: list[SecurityFinding] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        line = getattr(node, "lineno", 0) - 1
        snippet = source_lines[line].strip() if 0 <= line < len(source_lines) else None

        # Direct dangerous calls: eval(), exec(), etc.
        if isinstance(node.func, ast.Name) and node.func.id in _DANGEROUS_CALLS:
            rule_id, severity, message = _DANGEROUS_CALLS[node.func.id]
            findings.append(SecurityFinding(
                rule_id=rule_id, severity=severity, file_path=file_path,
                line=line, message=message, snippet=snippet,
            ))

        # Attribute calls: os.system(), pickle.loads(), etc.
        if isinstance(node.func, ast.Attribute):
            value = node.func.value
            if isinstance(value, ast.Name):
                key = (value.id, node.func.attr)
                if key in _DANGEROUS_ATTR_CALLS:
                    rule_id, severity, message = _DANGEROUS_ATTR_CALLS[key]
                    findings.append(SecurityFinding(
                        rule_id=rule_id, severity=severity, file_path=file_path,
                        line=line, message=message, snippet=snippet,
                    ))

            # subprocess.call/run/Popen with shell=True
            if isinstance(value, ast.Name) and value.id == "subprocess" and node.func.attr in _SUBPROCESS_SHELL_FUNCS:
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        msg = f"subprocess.{node.func.attr}() with shell=True is vulnerable to injection"
                        findings.append(SecurityFinding(
                            rule_id="SEC030", severity="high", file_path=file_path,
                            line=line, message=msg, snippet=snippet,
                        ))

    return findings


async def security_scan(
    file_path: str | None = None,
    file_paths: list[str] | None = None,
) -> SecurityScanResult:
    """Run security scan on one or more Python files."""
    paths: list[str] = []
    if file_paths:
        paths.extend(file_paths)
    if file_path:
        paths.append(file_path)

    all_findings: list[SecurityFinding] = []
    for path in paths:
        all_findings.extend(_scan_file(path))

    return SecurityScanResult(
        findings=all_findings,
        files_scanned=len(paths),
        total_findings=len(all_findings),
    )
