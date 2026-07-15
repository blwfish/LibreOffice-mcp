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
def insert_text(
    doc_id: str,
    text: str,
    break_before: str = "none",
    bold: bool = False,
    italic: bool = False,
    underline: bool = False,
    style: str | None = None,
    char_style: str | None = None,
) -> dict:
    """Append text at the end of a Writer document.

    break_before controls what precedes the text: "none" (default, keeps
    typing in the current paragraph), "line" (soft line break, same
    paragraph), "paragraph" (starts a new paragraph), or "page" (starts a
    new paragraph on a new page).

    bold/italic/underline apply direct character formatting to just the text
    being inserted. style is a paragraph style name (e.g. "Heading 1",
    "Title") applied to the paragraph the text lands in; char_style is a
    character style name (e.g. "Emphasis", "Strong Emphasis") applied to
    just the inserted run. Use list_styles to see what's actually available
    in a given document rather than guessing names.
    """
    return lo.call(
        "insert_text",
        {
            "doc_id": doc_id,
            "text": text,
            "break_before": break_before,
            "bold": bold,
            "italic": italic,
            "underline": underline,
            "style": style,
            "char_style": char_style,
        },
    )


@mcp.tool()
def set_paragraph_style(doc_id: str, style: str, paragraph_index: int | None = None) -> dict:
    """Apply a paragraph style (e.g. "Heading 1", "Title") to an existing paragraph.

    Defaults to the last paragraph if paragraph_index is omitted. Index is
    0-based and counts paragraphs only — tables don't count.
    """
    return lo.call(
        "set_paragraph_style",
        {"doc_id": doc_id, "style": style, "paragraph_index": paragraph_index},
    )


@mcp.tool()
def get_paragraph_style(doc_id: str, paragraph_index: int | None = None) -> dict:
    """Read a paragraph's style name and break type. Defaults to the last paragraph."""
    return lo.call(
        "get_paragraph_style",
        {"doc_id": doc_id, "paragraph_index": paragraph_index},
    )


@mcp.tool()
def list_styles(doc_id: str, family: str = "ParagraphStyles") -> dict:
    """List style names available in a document for a given style family.

    family is one of "ParagraphStyles" (default), "CharacterStyles",
    "PageStyles", "FrameStyles", "NumberingStyles". Use this before calling
    insert_text(style=...)/char_style=.../set_paragraph_style to find valid
    names instead of guessing — built-in style sets vary slightly by
    LibreOffice version and locale, and documents can also define custom
    styles.
    """
    return lo.call("list_styles", {"doc_id": doc_id, "family": family})


@mcp.tool()
def insert_table(
    doc_id: str,
    rows: int,
    cols: int,
    data: list[list[str]] | None = None,
    header: bool = False,
) -> dict:
    """Insert a table at the end of the document. Supports up to 26 columns.

    data, if given, is a 2D list of row values written into cells (values
    beyond the table's rows/cols are ignored). header=True bolds row 1.
    """
    return lo.call(
        "insert_table",
        {"doc_id": doc_id, "rows": rows, "cols": cols, "data": data, "header": header},
    )


@mcp.tool()
def get_table_cell(doc_id: str, cell: str, table_name: str | None = None) -> dict:
    """Read a table cell's text (e.g. cell="A1"). Uses the first table if table_name is omitted."""
    return lo.call(
        "get_table_cell",
        {"doc_id": doc_id, "cell": cell, "table_name": table_name},
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
