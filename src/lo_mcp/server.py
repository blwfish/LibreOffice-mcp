from mcp.server.fastmcp import FastMCP

from . import http_client as lo

mcp = FastMCP("lo-mcp")


@mcp.tool()
def check_connection() -> dict:
    """Check whether the lo-mcp LibreOffice extension is reachable.

    Call this first. If not connected, LibreOffice needs to be running with
    the lo-mcp extension's server started (lo-mcp menu > Start Server).
    """
    if lo.ping():
        return {"connected": True}
    return {
        "connected": False,
        "hint": "Launch LibreOffice, then use the lo-mcp menu > Start Server.",
    }


@mcp.tool()
def create_document() -> dict:
    """Create a new, blank Writer document. Returns a doc_id for later calls."""
    return lo.call("create_document")


@mcp.tool()
def open_document(path: str) -> dict:
    """Open an existing document from disk. Returns a doc_id."""
    return lo.call("open_document", {"path": path})


@mcp.tool()
def list_documents() -> dict:
    """List documents currently open via lo-mcp, with their doc_id and modified state."""
    return lo.call("list_documents")


@mcp.tool()
def get_text(doc_id: str) -> dict:
    """Read the full text content of a Writer document."""
    return lo.call("get_text", {"doc_id": doc_id})


@mcp.tool()
def insert_text(doc_id: str, text: str, paragraph_break: bool = False) -> dict:
    """Append text at the end of a Writer document."""
    return lo.call(
        "insert_text",
        {"doc_id": doc_id, "text": text, "paragraph_break": paragraph_break},
    )


@mcp.tool()
def find_and_replace(doc_id: str, search: str, replace: str, regex: bool = False) -> dict:
    """Replace all occurrences of `search` with `replace` in a document. Returns the count replaced."""
    return lo.call(
        "find_and_replace",
        {"doc_id": doc_id, "search": search, "replace": replace, "regex": regex},
    )


@mcp.tool()
def save_document(doc_id: str, path: str | None = None, format: str | None = None) -> dict:
    """Save a document in place (if it already has a location) or to a new path."""
    return lo.call("save_document", {"doc_id": doc_id, "path": path, "format": format})


@mcp.tool()
def export_document(doc_id: str, path: str, format: str | None = None) -> dict:
    """Export a document to `path`. Format is inferred from the extension if omitted.

    Supported formats: odt, pdf, docx, doc, rtf, txt, html.
    """
    return lo.call("export_document", {"doc_id": doc_id, "path": path, "format": format})


@mcp.tool()
def close_document(doc_id: str, force: bool = False) -> dict:
    """Close a document. Refuses if there are unsaved changes unless force=True."""
    return lo.call("close_document", {"doc_id": doc_id, "force": force})


def main():
    mcp.run()
