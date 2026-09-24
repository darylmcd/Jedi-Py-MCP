"""Shared, described parameter types for MCP tool signatures.

MCPServer builds each tool's ``inputSchema`` from the wrapped function's
signature, so ``Annotated[..., Field(description=...)]`` metadata on a parameter
becomes that property's schema ``description``. This module is the single
source of parameter descriptions: :data:`PARAM_DESCRIPTIONS` maps a parameter
name to text that is true for every tool using that name, and the aliases below
bind it to the parameter's type. Defaults stay on each tool signature.

A parameter whose meaning differs between tools gets a distinct alias with its
own text (for example :data:`NewMethodName` versus :data:`MethodName`) rather
than a shared sentence that is wrong for some callers.

Tool modules use ``from __future__ import annotations`` and MCPServer resolves
annotations with ``eval_str=True``, so every alias must be imported into the
module namespace that declares the tool.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

PARAM_DESCRIPTIONS: dict[str, str] = {
    "file_path": "Absolute path to the target Python file; it must lie inside the workspace.",
    "file_paths": (
        "Optional batch of absolute Python file paths (each inside the workspace) to process or scope the call to; "
        "the tool description states how it combines with file_path."
    ),
    "apply": "false (the default) returns a preview without touching disk; true writes the edits.",
    "line": "0-based line number (LSP convention).",
    "character": "0-based character offset within the line (LSP convention).",
    "start_line": "0-based line where the range starts (LSP convention).",
    "start_character": "0-based character offset where the range starts (LSP convention).",
    "end_line": "0-based line where the range ends (LSP convention).",
    "end_character": "0-based character offset where the range ends (LSP convention).",
    "limit": (
        "Maximum number of results to return. The tool description states what is counted, any default cap, "
        "and how truncation is reported."
    ),
    "offset": "Number of results to skip before the returned page (pagination).",
    "root_path": (
        "Absolute directory to scan when no explicit file scope is given; defaults to the workspace root. "
        "Must lie inside the workspace."
    ),
    "source_file": "Absolute path to the source Python module the tool reads from; it must lie inside the workspace.",
    "class_name": "Name of the target class.",
    "class_names": "Names of the classes to compare, all defined in file_path.",
    "method_name": "Name of the existing method to operate on.",
    "function_name": "Name of the existing top-level function to operate on.",
    "new_name": "New identifier for the symbol.",
    "members": "Names of the class members to move.",
    "depth": "How many levels to traverse from the starting symbol.",
    "max_items": "Maximum number of items to collect during the traversal.",
    "include_declaration": "Include the symbol's own declaration site in the results.",
    "suppress_codes": "Diagnostic rule codes to drop from the results (for example reportMissingImports).",
    "exclude_patterns": "Regular expressions; files whose path matches any of them are skipped.",
    "exclude_test_files": "Skip test files (test_*.py, *_test.py, and conftest.py).",
    "query": "Symbol name or name fragment to search for.",
    "pattern": "LibCST matcher expression (m.* DSL) describing the code to match.",
    "count": "Number of history operations to step through.",
    "package_name": "Dotted import name of the package to generate stubs for (for example requests).",
    "name": "Name to look up in the auto-import cache.",
    "edits": "TextEdit objects to preview, typically taken from a refactoring tool's preview output.",
    "steps": 'Ordered refactoring steps, each {"tool": <name>, "args": {...}}.',
    "index": "0-based position of the parameter in the signature (self counts for methods).",
}

_NEW_METHOD_NAME = "Name for the newly extracted method."
_OPTIONAL_FILE_PATH = (
    "Absolute path to a single Python file that scopes the call (it must lie inside the workspace); "
    "omit it to use the tool's default scope described in the tool description."
)
_OPTIONAL_CLASS_NAME = (
    "Class to select when several classes could match the position; omit it to use the class nearest the position."
)
_CALL_DIRECTION = "Which side of the call hierarchy to return: 'callers', 'callees', or 'both'."
_TYPE_DIRECTION = "Which side of the type hierarchy to return: 'supertypes', 'subtypes', or 'both'."
_ROPE_PATTERN = "rope restructuring pattern to match; ${name} wildcards bind sub-expressions reused in goal."

FilePath = Annotated[str, Field(description=PARAM_DESCRIPTIONS["file_path"])]
OptionalFilePath = Annotated[str | None, Field(description=_OPTIONAL_FILE_PATH)]
FilePaths = Annotated[list[str] | None, Field(description=PARAM_DESCRIPTIONS["file_paths"])]
Apply = Annotated[bool, Field(description=PARAM_DESCRIPTIONS["apply"])]
Line = Annotated[int, Field(description=PARAM_DESCRIPTIONS["line"])]
Character = Annotated[int, Field(description=PARAM_DESCRIPTIONS["character"])]
StartLine = Annotated[int, Field(description=PARAM_DESCRIPTIONS["start_line"])]
StartCharacter = Annotated[int, Field(description=PARAM_DESCRIPTIONS["start_character"])]
EndLine = Annotated[int, Field(description=PARAM_DESCRIPTIONS["end_line"])]
OptionalEndLine = Annotated[int | None, Field(description=PARAM_DESCRIPTIONS["end_line"])]
EndCharacter = Annotated[int, Field(description=PARAM_DESCRIPTIONS["end_character"])]
Limit = Annotated[int | None, Field(description=PARAM_DESCRIPTIONS["limit"])]
Offset = Annotated[int, Field(description=PARAM_DESCRIPTIONS["offset"])]
RootPath = Annotated[str | None, Field(description=PARAM_DESCRIPTIONS["root_path"])]
SourceFile = Annotated[str, Field(description=PARAM_DESCRIPTIONS["source_file"])]
ClassName = Annotated[str, Field(description=PARAM_DESCRIPTIONS["class_name"])]
OptionalClassName = Annotated[str | None, Field(description=_OPTIONAL_CLASS_NAME)]
ClassNames = Annotated[list[str], Field(description=PARAM_DESCRIPTIONS["class_names"])]
MethodName = Annotated[str, Field(description=PARAM_DESCRIPTIONS["method_name"])]
NewMethodName = Annotated[str, Field(description=_NEW_METHOD_NAME)]
FunctionName = Annotated[str, Field(description=PARAM_DESCRIPTIONS["function_name"])]
NewName = Annotated[str, Field(description=PARAM_DESCRIPTIONS["new_name"])]
Members = Annotated[list[str], Field(description=PARAM_DESCRIPTIONS["members"])]
Depth = Annotated[int, Field(description=PARAM_DESCRIPTIONS["depth"])]
MaxItems = Annotated[int, Field(description=PARAM_DESCRIPTIONS["max_items"])]
OptionalMaxItems = Annotated[int | None, Field(description=PARAM_DESCRIPTIONS["max_items"])]
IncludeDeclaration = Annotated[bool, Field(description=PARAM_DESCRIPTIONS["include_declaration"])]
SuppressCodes = Annotated[list[str] | None, Field(description=PARAM_DESCRIPTIONS["suppress_codes"])]
ExcludePatterns = Annotated[list[str] | None, Field(description=PARAM_DESCRIPTIONS["exclude_patterns"])]
ExcludeTestFiles = Annotated[bool, Field(description=PARAM_DESCRIPTIONS["exclude_test_files"])]
CallDirection = Annotated[str, Field(description=_CALL_DIRECTION)]
TypeDirection = Annotated[str, Field(description=_TYPE_DIRECTION)]
Query = Annotated[str, Field(description=PARAM_DESCRIPTIONS["query"])]
MatcherPattern = Annotated[str, Field(description=PARAM_DESCRIPTIONS["pattern"])]
RopePattern = Annotated[str, Field(description=_ROPE_PATTERN)]
HistoryCount = Annotated[int, Field(description=PARAM_DESCRIPTIONS["count"])]
PackageName = Annotated[str, Field(description=PARAM_DESCRIPTIONS["package_name"])]
AutoImportName = Annotated[str, Field(description=PARAM_DESCRIPTIONS["name"])]
TransactionSteps = Annotated[list[dict[str, Any]], Field(description=PARAM_DESCRIPTIONS["steps"])]
ParameterIndex = Annotated[int, Field(ge=0, description=PARAM_DESCRIPTIONS["index"])]
