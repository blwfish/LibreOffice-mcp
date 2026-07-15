"""End-to-end test against the real lo-mcp LibreOffice extension.

Requires LibreOffice to be running with the lo-mcp extension installed and
its server started (lo-mcp menu > Start Server). Skipped automatically if
the extension isn't reachable.
"""

import os

import pytest

from lo_mcp import http_client as lo

pytestmark = pytest.mark.skipif(
    not lo.ping(), reason="lo-mcp extension not reachable; start it in LibreOffice first"
)


def test_writer_roundtrip(tmp_path):
    doc = lo.call("create_document")
    doc_id = doc["doc_id"]
    try:
        lo.call("insert_text", {"doc_id": doc_id, "text": "Hello lo-mcp"})
        out = lo.call("get_text", {"doc_id": doc_id})
        assert "Hello lo-mcp" in out["text"]

        pdf_path = str(tmp_path / "out.pdf")
        result = lo.call("export_document", {"doc_id": doc_id, "path": pdf_path, "format": "pdf"})
        assert os.path.exists(result["path"])
        with open(result["path"], "rb") as fh:
            assert fh.read(5) == b"%PDF-"
    finally:
        lo.call("close_document", {"doc_id": doc_id, "force": True})


def test_find_and_replace(tmp_path):
    doc = lo.call("create_document")
    doc_id = doc["doc_id"]
    try:
        lo.call("insert_text", {"doc_id": doc_id, "text": "foo bar foo"})
        result = lo.call("find_and_replace", {"doc_id": doc_id, "search": "foo", "replace": "baz"})
        assert result["count"] == 2
        out = lo.call("get_text", {"doc_id": doc_id})
        assert out["text"] == "baz bar baz"
    finally:
        lo.call("close_document", {"doc_id": doc_id, "force": True})


def test_save_then_close_without_force(tmp_path):
    """Regression: storeToURL doesn't clear isModified()/set the doc's URL,
    so a document saved via `path` on its first save always looked
    "modified" to close_document even right after a successful save.
    save_document must use Save-As semantics (storeAsURL) so this succeeds
    without needing force=True.
    """
    path = str(tmp_path / "saved.odt")
    doc = lo.call("create_document")
    doc_id = doc["doc_id"]
    lo.call("insert_text", {"doc_id": doc_id, "text": "content"})
    lo.call("save_document", {"doc_id": doc_id, "path": path})
    result = lo.call("close_document", {"doc_id": doc_id})
    assert result["closed"] == doc_id, f"expected clean close, got {result}"


def test_reopen_edit_save_roundtrip(tmp_path):
    path = str(tmp_path / "roundtrip.odt")
    doc = lo.call("create_document")
    doc_id = doc["doc_id"]
    lo.call("insert_text", {"doc_id": doc_id, "text": "first line"})
    lo.call("save_document", {"doc_id": doc_id, "path": path})
    lo.call("close_document", {"doc_id": doc_id})

    reopened = lo.call("open_document", {"path": path})
    doc_id2 = reopened["doc_id"]
    out = lo.call("get_text", {"doc_id": doc_id2})
    assert out["text"] == "first line"

    lo.call("insert_text", {"doc_id": doc_id2, "text": " second line", "paragraph_break": True})
    lo.call("save_document", {"doc_id": doc_id2})
    result = lo.call("close_document", {"doc_id": doc_id2})
    assert result["closed"] == doc_id2, f"expected clean close after in-place save, got {result}"

    reopened2 = lo.call("open_document", {"path": path})
    doc_id3 = reopened2["doc_id"]
    try:
        out2 = lo.call("get_text", {"doc_id": doc_id3})
        assert "first line" in out2["text"]
        assert "second line" in out2["text"]
    finally:
        lo.call("close_document", {"doc_id": doc_id3, "force": True})


def test_insert_text_formatting_and_paragraph_style():
    doc = lo.call("create_document")
    doc_id = doc["doc_id"]
    try:
        lo.call("insert_text", {"doc_id": doc_id, "text": "Title Line", "style": "Heading 1"})
        lo.call(
            "insert_text",
            {
                "doc_id": doc_id,
                "text": "bold and italic",
                "paragraph_break": True,
                "bold": True,
                "italic": True,
            },
        )
        out = lo.call("get_text", {"doc_id": doc_id})
        assert out["text"] == "Title Line\nbold and italic"

        # set_paragraph_style on an already-written paragraph, default (last)
        lo.call("insert_text", {"doc_id": doc_id, "text": "make me a heading", "paragraph_break": True})
        result = lo.call("set_paragraph_style", {"doc_id": doc_id, "style": "Heading 2"})
        assert result["paragraph_count"] == 3

        with pytest.raises(Exception):
            lo.call("set_paragraph_style", {"doc_id": doc_id, "style": "Heading 2", "paragraph_index": 99})
    finally:
        lo.call("close_document", {"doc_id": doc_id, "force": True})


def test_insert_table_with_data_and_header():
    doc = lo.call("create_document")
    doc_id = doc["doc_id"]
    try:
        result = lo.call(
            "insert_table",
            {
                "doc_id": doc_id,
                "rows": 3,
                "cols": 2,
                "data": [["Name", "Qty"], ["bolt", "12"], ["nut", "8"]],
                "header": True,
            },
        )
        assert result["rows"] == 3
        assert result["cols"] == 2
        table_name = result["name"]

        assert lo.call("get_table_cell", {"doc_id": doc_id, "cell": "A1"})["text"] == "Name"
        assert lo.call("get_table_cell", {"doc_id": doc_id, "cell": "B2"})["text"] == "12"
        assert lo.call("get_table_cell", {"doc_id": doc_id, "cell": "A3"})["text"] == "nut"
        # explicit table_name path
        assert (
            lo.call("get_table_cell", {"doc_id": doc_id, "cell": "A1", "table_name": table_name})["text"]
            == "Name"
        )

        with pytest.raises(Exception):
            lo.call("get_table_cell", {"doc_id": doc_id, "cell": "Z9"})
    finally:
        lo.call("close_document", {"doc_id": doc_id, "force": True})


def test_insert_table_rejects_degenerate_dimensions():
    doc = lo.call("create_document")
    doc_id = doc["doc_id"]
    try:
        with pytest.raises(Exception):
            lo.call("insert_table", {"doc_id": doc_id, "rows": 0, "cols": 2})
        with pytest.raises(Exception):
            lo.call("insert_table", {"doc_id": doc_id, "rows": 2, "cols": 27})
    finally:
        lo.call("close_document", {"doc_id": doc_id, "force": True})


def test_multi_document_isolation():
    doc_a = lo.call("create_document")
    doc_b = lo.call("create_document")
    id_a, id_b = doc_a["doc_id"], doc_b["doc_id"]
    assert id_a != id_b
    try:
        lo.call("insert_text", {"doc_id": id_a, "text": "document A content"})
        lo.call("insert_text", {"doc_id": id_b, "text": "document B content"})

        open_ids = {d["doc_id"] for d in lo.call("list_documents")["documents"]}
        assert {id_a, id_b} <= open_ids

        assert lo.call("get_text", {"doc_id": id_a})["text"] == "document A content"
        assert lo.call("get_text", {"doc_id": id_b})["text"] == "document B content"
    finally:
        lo.call("close_document", {"doc_id": id_a, "force": True})
        lo.call("close_document", {"doc_id": id_b, "force": True})
