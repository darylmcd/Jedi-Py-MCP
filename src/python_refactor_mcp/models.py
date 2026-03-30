"""Shared Pydantic models for MCP tool inputs and outputs."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Position(BaseModel):
    """0-based line and character offset."""

    line: int = Field(ge=0)
    character: int = Field(ge=0)


class Range(BaseModel):
    """Text range in a file using 0-based positions."""

    start: Position
    end: Position


class Location(BaseModel):
    """A file location for symbols and references."""

    file_path: str
    range: Range
    context: str | None = None


class TextEdit(BaseModel):
    """A textual replacement for a file range."""

    file_path: str
    range: Range
    new_text: str


class SymbolInfo(BaseModel):
    """Metadata for a discovered symbol."""

    name: str
    kind: str
    file_path: str
    range: Range
    container: str | None = None


class SymbolOutlineItem(BaseModel):
    """Hierarchical symbol outline item for a document or workspace."""

    name: str
    kind: str
    file_path: str
    range: Range
    selection_range: Range
    detail: str | None = None
    container: str | None = None
    children: list[SymbolOutlineItem] = Field(default_factory=list)


class Diagnostic(BaseModel):
    """A diagnostic issue reported by analysis backends."""

    file_path: str
    range: Range
    severity: str
    message: str
    code: str | None = None
    tags: list[int] = Field(default_factory=list)


class ReferenceResult(BaseModel):
    """Reference search result for a symbol."""

    symbol: str
    definition: Location | None = None
    references: list[Location]
    total_count: int
    source: str
    truncated: bool = False


class TypeInfo(BaseModel):
    """Type information returned for an expression or symbol."""

    expression: str
    type_string: str
    documentation: str | None = None
    source: str


class CompletionItem(BaseModel):
    """One code completion candidate at a source position."""

    label: str
    kind: str
    detail: str | None = None
    insert_text: str | None = None
    documentation: str | None = None


class ParameterInfo(BaseModel):
    """One function signature parameter."""

    label: str
    documentation: str | None = None


class SignatureInfo(BaseModel):
    """Signature help for a call site."""

    label: str
    parameters: list[ParameterInfo]
    active_parameter: int | None = None
    active_signature: int | None = None
    documentation: str | None = None


class DocumentHighlight(BaseModel):
    """In-document symbol usage with access kind metadata."""

    range: Range
    kind: str


class PrepareRenameResult(BaseModel):
    """Rename preflight payload describing editable range and placeholder."""

    range: Range
    placeholder: str


class InlayHint(BaseModel):
    """One inlay hint item returned from language server analysis."""

    position: Position
    label: str
    kind: str | None = None
    padding_left: bool = False
    padding_right: bool = False


class SemanticToken(BaseModel):
    """One decoded semantic token entry for a document."""

    range: Range
    token_type: str
    modifiers: list[str] = Field(default_factory=list)


class FoldingRange(BaseModel):
    """Foldable region metadata for a source file."""

    start_line: int
    end_line: int
    kind: str | None = None


class CallHierarchyItem(BaseModel):
    """One node in a call hierarchy graph."""

    name: str
    kind: str
    file_path: str
    range: Range
    detail: str | None = None


class CallHierarchyResult(BaseModel):
    """Call hierarchy data for callers and callees."""

    item: CallHierarchyItem
    callers: list[CallHierarchyItem]
    callees: list[CallHierarchyItem]
    truncated: bool = False


class TypeHierarchyItem(BaseModel):
    """One node in a type hierarchy graph."""

    name: str
    kind: str
    file_path: str
    range: Range
    detail: str | None = None


class TypeHierarchyResult(BaseModel):
    """Type hierarchy data for supertypes/subtypes traversal."""

    item: TypeHierarchyItem
    supertypes: list[TypeHierarchyItem]
    subtypes: list[TypeHierarchyItem]
    truncated: bool = False


class SelectionRangeResult(BaseModel):
    """Nested selection ranges from inner-most to outer-most scope."""

    position: Position
    ranges: list[Range]


class DocumentationEntry(BaseModel):
    """Documentation entry returned from Jedi help lookup."""

    name: str
    module_path: str | None = None
    kind: str | None = None
    full_doc: str | None = None
    signatures: list[str] = Field(default_factory=list)


class DocumentationResult(BaseModel):
    """Documentation lookup result for one source position."""

    file_path: str
    line: int
    character: int
    entries: list[DocumentationEntry]


class RefactorResult(BaseModel):
    """Refactoring edit payload and optional diagnostics."""

    edits: list[TextEdit]
    files_affected: list[str]
    description: str
    applied: bool = False
    diagnostics_after: list[Diagnostic] | None = None
    diffs: list[DiffPreview] | None = None


_VALID_SIGNATURE_OPS = frozenset({"add", "remove", "reorder", "inline_default", "normalize", "rename"})


class SignatureOperation(BaseModel):
    """One operation applied by change_signature refactoring."""

    op: str
    index: int | None = None
    name: str | None = None
    new_name: str | None = None
    default: str | None = None
    new_order: list[int] | None = None

    @field_validator("op")
    @classmethod
    def _validate_op(cls, value: str) -> str:
        if value not in _VALID_SIGNATURE_OPS:
            raise ValueError(f"Invalid operation '{value}'. Must be one of: {sorted(_VALID_SIGNATURE_OPS)}")
        return value


class ConstructorSite(BaseModel):
    """A class constructor invocation site."""

    class_name: str
    file_path: str
    range: Range
    arguments: list[str]


class StructuralMatch(BaseModel):
    """A structural pattern match found in code."""

    file_path: str
    range: Range
    matched_text: str


class DeadCodeItem(BaseModel):
    """Detected dead or unreachable code candidate."""

    name: str
    kind: str
    file_path: str
    range: Range
    reason: str
    confidence: str = "medium"


class ImportSuggestion(BaseModel):
    """Suggested import for an unresolved symbol."""

    symbol: str
    module: str
    import_statement: str


class DiagnosticSummary(BaseModel):
    """Aggregated diagnostic counts for a file."""

    file_path: str
    error_count: int
    warning_count: int
    information_count: int
    hint_count: int
    total_count: int


class PaginatedDiagnosticSummary(BaseModel):
    """Paginated wrapper for workspace diagnostic summaries."""

    items: list[DiagnosticSummary]
    total_count: int
    offset: int = 0
    truncated: bool = False


class PaginatedDeadCode(BaseModel):
    """Paginated wrapper for dead code detection results."""

    items: list[DeadCodeItem]
    total_count: int
    offset: int = 0
    truncated: bool = False


class DiffPreview(BaseModel):
    """Unified diff preview for one file."""

    file_path: str
    unified_diff: str


class InferredType(BaseModel):
    """Deep type inference result following imports and assignments."""

    name: str
    full_name: str | None = None
    type_string: str
    module_path: str | None = None
    line: int | None = None
    character: int | None = None
    description: str | None = None


class TypeHintResult(BaseModel):
    """Type hint annotation string for a symbol."""

    name: str
    type_hint: str | None = None
    full_name: str | None = None


class SyntaxErrorItem(BaseModel):
    """A syntax error detected by Jedi's parser."""

    file_path: str
    message: str
    line: int
    character: int
    until_line: int | None = None
    until_character: int | None = None


class ScopeContext(BaseModel):
    """Enclosing scope at a source position."""

    name: str
    kind: str
    file_path: str
    line: int
    character: int
    full_name: str | None = None


class NameEntry(BaseModel):
    """A defined name in a file (broader than symbol outline)."""

    name: str
    kind: str
    file_path: str | None = None
    line: int
    character: int
    full_name: str | None = None
    description: str | None = None


class FunctionMetrics(BaseModel):
    """Complexity metrics for a single function."""

    name: str
    file_path: str
    line: int
    cyclomatic_complexity: int
    cognitive_complexity: int
    nesting_depth: int
    loc: int
    parameter_count: int


class CodeMetricsResult(BaseModel):
    """Code metrics for one or more files."""

    functions: list[FunctionMetrics]
    total_functions: int
    avg_cyclomatic: float
    max_cyclomatic: int


class ModuleDependency(BaseModel):
    """An import dependency between two modules."""

    source: str
    target: str
    import_name: str
    line: int


class DependencyGraph(BaseModel):
    """Module dependency graph with optional circular dependency detection."""

    dependencies: list[ModuleDependency]
    modules: list[str]
    circular_dependencies: list[list[str]]


class UnusedImport(BaseModel):
    """An unused import found in a file."""

    file_path: str
    module: str
    name: str | None = None
    line: int
    message: str


class DuplicateGroup(BaseModel):
    """A group of duplicated code fragments."""

    hash: str
    function_name: str
    occurrences: list[dict[str, object]]
    count: int


class TypeCoverageReport(BaseModel):
    """Type annotation coverage report for a file or project."""

    file_path: str | None = None
    total_functions: int
    annotated_return: int
    annotated_params: int
    total_params: int
    return_coverage_pct: float
    param_coverage_pct: float
    unannotated: list[dict[str, object]]


class CouplingMetrics(BaseModel):
    """Afferent/efferent coupling and instability for a module."""

    module: str
    afferent_coupling: int
    efferent_coupling: int
    instability: float


class LayerViolation(BaseModel):
    """An import that violates declared layer ordering."""

    source_module: str
    target_module: str
    source_layer: int
    target_layer: int
    import_line: int


class StaticError(BaseModel):
    """A static analysis error from rope's finderrors."""

    file_path: str
    line: int
    message: str



class InterfaceComparison(BaseModel):
    """Result of comparing class interfaces for protocol conformance."""

    classes: list[str]
    common_methods: list[str]
    unique_methods: dict[str, list[str]]
    signature_mismatches: list[dict[str, object]]


class ProtocolSource(BaseModel):
    """Generated Protocol class source code."""

    protocol_name: str
    source_code: str
    methods: list[str]


class PublicAPIItem(BaseModel):
    """A public symbol in a module's API."""

    name: str
    kind: str
    line: int
    file_path: str


class EnvironmentInfo(BaseModel):
    """Python environment metadata."""

    path: str
    python_version: str
    is_virtualenv: bool


class HistoryEntry(BaseModel):
    """Single entry from refactoring history."""

    description: str
    date: str
    files_affected: list[str]


class TestCoverageEntry(BaseModel):
    """Symbol-to-test mapping entry."""

    symbol_name: str
    file_path: str
    line: int
    test_references: list[str]
    covered: bool


class TestCoverageMap(BaseModel):
    """Test coverage mapping for source symbols."""

    entries: list[TestCoverageEntry]
    total_symbols: int
    covered_count: int
    coverage_pct: float


class SecurityFinding(BaseModel):
    """Single finding from security scan."""

    rule_id: str
    severity: str
    file_path: str
    line: int
    message: str
    snippet: str | None = None


class SecurityScanResult(BaseModel):
    """Aggregated security scan results."""

    findings: list[SecurityFinding]
    files_scanned: int
    total_findings: int
