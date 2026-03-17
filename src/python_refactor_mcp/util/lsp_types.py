"""Typed LSP protocol payloads used by the Pyright bridge."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

LSPNumber = int | float
LSPScalar = str | LSPNumber | bool | None
LSPValue = LSPScalar | list["LSPValue"] | dict[str, "LSPValue"]


class LSPPosition(TypedDict):
	"""LSP position payload using 0-based offsets."""

	line: int
	character: int


class LSPRange(TypedDict):
	"""LSP range payload."""

	start: LSPPosition
	end: LSPPosition


class InitializeClientCapabilities(TypedDict, total=False):
	"""Subset of client capabilities used by this server."""

	textDocument: dict[str, LSPValue]
	workspace: dict[str, LSPValue]


class InitializeParams(TypedDict, total=False):
	"""Initialize request parameters."""

	processId: int | None
	rootUri: str | None
	capabilities: InitializeClientCapabilities
	workspaceFolders: list[dict[str, str]] | None
	initializationOptions: dict[str, LSPValue]
	clientInfo: dict[str, str]


class ServerCapabilities(TypedDict, total=False):
	"""Subset of server capabilities used by this project."""

	hoverProvider: bool
	definitionProvider: bool
	referencesProvider: bool
	codeActionProvider: bool | dict[str, LSPValue]
	callHierarchyProvider: bool
	textDocumentSync: int | dict[str, LSPValue]


class ServerInfo(TypedDict, total=False):
	"""Server identity metadata from initialize result."""

	name: str
	version: str


class InitializeResult(TypedDict):
	"""Initialize response payload."""

	capabilities: ServerCapabilities
	serverInfo: NotRequired[ServerInfo]


class TextDocumentIdentifier(TypedDict):
	"""Identifies an existing document by URI."""

	uri: str


class VersionedTextDocumentIdentifier(TextDocumentIdentifier):
	"""Document identifier with version number."""

	version: int


class TextDocumentItem(TypedDict):
	"""Represents an open text document."""

	uri: str
	languageId: str
	version: int
	text: str


class TextDocumentContentChangeEvent(TypedDict):
	"""Full content change payload for didChange."""

	text: str


class TextDocumentPositionParams(TypedDict):
	"""Request parameters for text document + cursor position calls."""

	textDocument: TextDocumentIdentifier
	position: LSPPosition


class DidOpenTextDocumentParams(TypedDict):
	"""didOpen notification parameters."""

	textDocument: TextDocumentItem


class DidChangeTextDocumentParams(TypedDict):
	"""didChange notification parameters."""

	textDocument: VersionedTextDocumentIdentifier
	contentChanges: list[TextDocumentContentChangeEvent]


class DidCloseTextDocumentParams(TypedDict):
	"""didClose notification parameters."""

	textDocument: TextDocumentIdentifier


class ReferenceContext(TypedDict):
	"""Context payload for references request."""

	includeDeclaration: bool


class ReferenceParams(TextDocumentPositionParams):
	"""References request parameters."""

	context: ReferenceContext


class HoverParams(TextDocumentPositionParams):
	"""Hover request parameters."""


class DefinitionParams(TextDocumentPositionParams):
	"""Definition request parameters."""


class MarkupContent(TypedDict):
	"""Marked up text content."""

	kind: Literal["plaintext", "markdown"]
	value: str


class MarkedString(TypedDict, total=False):
	"""Marked string payload."""

	language: str
	value: str


class Hover(TypedDict, total=False):
	"""Hover response payload."""

	contents: str | MarkupContent | MarkedString | list[str | MarkupContent | MarkedString]
	range: LSPRange


class Location(TypedDict):
	"""LSP location payload."""

	uri: str
	range: LSPRange


class LocationLink(TypedDict, total=False):
	"""LSP location link payload."""

	targetUri: str
	targetRange: LSPRange
	targetSelectionRange: LSPRange
	originSelectionRange: LSPRange


class CallHierarchyPrepareParams(TextDocumentPositionParams):
	"""Prepare call hierarchy request parameters."""


class CallHierarchyItem(TypedDict, total=False):
	"""LSP call hierarchy item."""

	name: str
	kind: int
	uri: str
	range: LSPRange
	selectionRange: LSPRange
	detail: str
	tags: list[int]
	data: LSPValue


class CallHierarchyIncomingCallsParams(TypedDict):
	"""Incoming calls request parameters."""

	item: CallHierarchyItem


class CallHierarchyOutgoingCallsParams(TypedDict):
	"""Outgoing calls request parameters."""

	item: CallHierarchyItem


CallHierarchyIncomingCall = TypedDict(
	"CallHierarchyIncomingCall",
	{"from": CallHierarchyItem, "fromRanges": list[LSPRange]},
)


class CallHierarchyOutgoingCall(TypedDict):
	"""Outgoing call edge payload."""

	to: CallHierarchyItem
	fromRanges: list[LSPRange]


class CodeActionContext(TypedDict):
	"""Code action request context."""

	diagnostics: list[LSPDiagnostic]
	only: NotRequired[list[str]]
	triggerKind: NotRequired[int]


class CodeActionParams(TypedDict):
	"""Code action request parameters."""

	textDocument: TextDocumentIdentifier
	range: LSPRange
	context: CodeActionContext


class LSPDiagnostic(TypedDict, total=False):
	"""LSP diagnostic payload."""

	range: LSPRange
	severity: int
	code: int | str
	source: str
	message: str


class PublishDiagnosticsParams(TypedDict):
	"""publishDiagnostics notification payload."""

	uri: str
	diagnostics: list[LSPDiagnostic]


class JSONRPCError(TypedDict):
	"""JSON-RPC error payload."""

	code: int
	message: str
	data: NotRequired[LSPValue]


class JSONRPCRequest(TypedDict):
	"""JSON-RPC request envelope."""

	jsonrpc: Literal["2.0"]
	id: int
	method: str
	params: NotRequired[dict[str, LSPValue]]


class JSONRPCNotification(TypedDict):
	"""JSON-RPC notification envelope."""

	jsonrpc: Literal["2.0"]
	method: str
	params: NotRequired[dict[str, LSPValue]]


class JSONRPCResponse(TypedDict, total=False):
	"""JSON-RPC response envelope."""

	jsonrpc: Literal["2.0"]
	id: int | str
	result: LSPValue
	error: JSONRPCError


InitializeResponse = JSONRPCResponse
HoverResponse = JSONRPCResponse
DefinitionResponse = JSONRPCResponse
ReferencesResponse = JSONRPCResponse
PrepareCallHierarchyResponse = JSONRPCResponse
IncomingCallsResponse = JSONRPCResponse
OutgoingCallsResponse = JSONRPCResponse
CodeActionResponse = JSONRPCResponse
