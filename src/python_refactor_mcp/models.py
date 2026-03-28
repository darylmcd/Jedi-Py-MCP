"""Shared Pydantic models for MCP tool inputs and outputs."""

from __future__ import annotations

from pydantic import BaseModel, Field


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


class SignatureOperation(BaseModel):
    """One operation applied by change_signature refactoring."""

    op: str
    index: int | None = None
    name: str | None = None
    new_name: str | None = None
    default: str | None = None
    new_order: list[int] | None = None


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


class DiffPreview(BaseModel):
    """Unified diff preview for one file."""

    file_path: str
    unified_diff: str
