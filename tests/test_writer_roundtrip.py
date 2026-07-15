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
