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
