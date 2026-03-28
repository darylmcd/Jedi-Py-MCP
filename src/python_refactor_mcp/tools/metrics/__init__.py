"""AST-based code metrics, dependency analysis, and architecture tools."""

from .architecture import check_layer_violations, extract_protocol, get_coupling_metrics, interface_conformance
from .complexity import code_metrics
from .coverage import get_type_coverage
from .dependencies import get_module_dependencies
from .duplicates import find_duplicated_code
from .unused import find_unused_imports

__all__ = [
    "check_layer_violations",
    "code_metrics",
    "extract_protocol",
    "find_duplicated_code",
    "find_unused_imports",
    "get_coupling_metrics",
    "get_module_dependencies",
    "get_type_coverage",
    "interface_conformance",
]
