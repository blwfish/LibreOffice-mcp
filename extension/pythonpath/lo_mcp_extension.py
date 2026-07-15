"""lo-mcp LibreOffice extension.

Runs INSIDE the soffice process (loaded via LibreOffice's own Python UNO
component mechanism), so it uses LibreOffice's own already-initialized
interpreter and `ctx` — no subprocess, no cross-interpreter `import uno`.
Exposes a small local HTTP server so an external, unconstrained MCP client
process can drive Writer without ever spawning or dlopen-ing anything
belonging to the signed LibreOffice app bundle.

Started manually via Tools > lo-mcp > Start Server (see Addons.xcu) rather
than auto-starting on launch, so the HTTP port is only open when you
actually want it.
"""

import http.server
import json
import logging
import threading
import traceback
import uuid

import uno
import unohelper
from com.sun.star.task import XJobExecutor
from com.sun.star.task import XJob
from com.sun.star.lang import XServiceInfo
from com.sun.star.beans import PropertyValue
from com.sun.star.awt.FontWeight import BOLD as FONT_WEIGHT_BOLD
from com.sun.star.awt.FontSlant import ITALIC as FONT_SLANT_ITALIC
from com.sun.star.awt.FontUnderline import SINGLE as FONT_UNDERLINE_SINGLE
from com.sun.star.text.ControlCharacter import LINE_BREAK, PARAGRAPH_BREAK
from com.sun.star.style.BreakType import PAGE_BEFORE as BREAK_PAGE_BEFORE

IMPLEMENTATION_NAME = "net.blw.lomcp.Extension"
# JobExecutor: the Tools > lo-mcp menu (Addons.xcu) dispatches
# service:net.blw.lomcp.Extension?start / ?stop to trigger().
# Job: Jobs.xcu registers this same implementation to auto-run on the
# OnStartApp / onFirstVisibleTask application events, via execute().
SERVICE_NAMES = ("com.sun.star.task.JobExecutor", "com.sun.star.task.Job")

HOST = "127.0.0.1"
PORT = 8794
# Requiring a custom header forces browsers to CORS-preflight cross-origin
# POSTs; since this server never answers with Access-Control-Allow-Origin,
# the preflight fails and the browser blocks the request before it's sent.
# Without this, a "simple" request (e.g. Content-Type: text/plain) from any
# page the user has open would skip preflight and reach do_POST directly.
REQUIRED_HEADER = "X-Lo-Mcp-Client"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lo_mcp")


def _prop(name, value):
    p = PropertyValue()
    p.Name = name
    p.Value = value
    return p


def _iter_enum(enum):
    while enum.hasMoreElements():
        yield enum.nextElement()


def _cell_name(row, col):
    # UNO TextTable cell names are column-letter + 1-based row, e.g. "A1".
    # Callers already reject cols > 26 before this runs.
    return f"{chr(ord('A') + col)}{row + 1}"


_BREAK_BEFORE_VALUES = {"none", "line", "paragraph", "page"}


def _break_type_name(break_type):
    # com.sun.star.style.BreakType is an IDL *enum* (unlike FontWeight/
    # FontSlant/FontUnderline, which are *constants* groups of plain
    # numbers) — PyUNO wraps enum values as uno.Enum objects whose .value
    # is the member's string name (e.g. "PAGE_BEFORE"), not an int.
    return str(getattr(break_type, "value", break_type)).lower()


def _paragraphs(doc):
    return [
        el
        for el in _iter_enum(doc.getText().createEnumeration())
        if el.supportsService("com.sun.star.text.Paragraph")
    ]


def _paragraph_at(doc, index):
    paras = _paragraphs(doc)
    if not paras:
        raise ValueError("document has no paragraphs")
    if index is None:
        index = len(paras) - 1
    if not (-len(paras) <= index < len(paras)):
        raise ValueError(f"paragraph_index {index} out of range; document has {len(paras)} paragraphs")
    return paras[index], len(paras)


# Export filter names, keyed by target format. Writer-only for now.
_FILTERS = {
    "odt": "writer8",
    "pdf": "writer_pdf_Export",
    "docx": "MS Word 2007 XML",
    "doc": "MS Word 97",
    "rtf": "Rich Text Format",
    "txt": "Text",
    "html": "HTML (StarWriter)",
}


class WriterOps:
    """Open Writer documents and the operations on them.

    All calls arrive on the HTTP server's request thread, not the UNO
    "main" thread. LibreOffice's UNO proxies serialize access via their own
    bridge locking, so this is the same threading model LibreOffice's own
    Basic IDE and other in-process automation use — fine for the simple
    sequential text ops here, but not a guarantee for arbitrarily heavy
    concurrent access.
    """

    def __init__(self, ctx):
        self.ctx = ctx
        smgr = ctx.ServiceManager
        self.desktop = smgr.createInstanceWithContext(
            "com.sun.star.frame.Desktop", ctx
        )
        self.docs = {}

    def _doc(self, doc_id):
        try:
            return self.docs[doc_id]
        except KeyError:
            raise KeyError(f"unknown doc_id: {doc_id}") from None

    def create_document(self, args):
        doc = self.desktop.loadComponentFromURL(
            "private:factory/swriter", "_blank", 0, (_prop("Hidden", False),)
        )
        doc_id = str(uuid.uuid4())
        self.docs[doc_id] = doc
        return {"doc_id": doc_id}

    def open_document(self, args):
        path = args["path"]
        url = uno.systemPathToFileUrl(path)
        doc = self.desktop.loadComponentFromURL(url, "_blank", 0, (_prop("Hidden", False),))
        doc_id = str(uuid.uuid4())
        self.docs[doc_id] = doc
        return {"doc_id": doc_id, "path": path}

    def list_documents(self, args):
        out = []
        stale = []
        for doc_id, doc in self.docs.items():
            try:
                url = doc.getURL()
                modified = bool(doc.isModified())
            except Exception:
                # Closed outside the API (e.g. the user closed the window in
                # Writer directly) — the UNO proxy is now disposed and every
                # call on it throws. Drop it instead of failing the whole
                # listing over one stale doc_id.
                stale.append(doc_id)
                continue
            out.append({"doc_id": doc_id, "url": url, "modified": modified})
        for doc_id in stale:
            del self.docs[doc_id]
        return {"documents": out}

    def get_text(self, args):
        doc = self._doc(args["doc_id"])
        return {"text": doc.getText().getString()}

    def insert_text(self, args):
        doc = self._doc(args["doc_id"])
        text = doc.getText()
        cursor = text.createTextCursor()
        cursor.gotoEnd(False)

        break_before = args.get("break_before") or "none"
        if break_before not in _BREAK_BEFORE_VALUES:
            raise ValueError(
                f"break_before must be one of {sorted(_BREAK_BEFORE_VALUES)}, got {break_before!r}"
            )
        if break_before == "line":
            text.insertControlCharacter(cursor, LINE_BREAK, False)
        elif break_before in ("paragraph", "page"):
            text.insertControlCharacter(cursor, PARAGRAPH_BREAK, False)
            if break_before == "page":
                # Standard UNO idiom: after inserting the paragraph break the
                # cursor sits in the new (now-current) paragraph, so setting
                # BreakType here sets that paragraph's own break property —
                # this is what "Insert > Page Break" does under the hood.
                cursor.BreakType = BREAK_PAGE_BEFORE

        # Mark where the new text starts so formatting below applies only to
        # what we just inserted, not anything already in the document.
        insert_start = text.createTextCursorByRange(cursor.getEnd())
        text.insertString(cursor, args["text"], False)
        if any(args.get(k) for k in ("bold", "italic", "underline", "style", "char_style")):
            fmt_cursor = text.createTextCursorByRange(insert_start.getStart())
            fmt_cursor.gotoRange(cursor.getEnd(), True)
            if args.get("bold"):
                fmt_cursor.CharWeight = FONT_WEIGHT_BOLD
            if args.get("italic"):
                fmt_cursor.CharPosture = FONT_SLANT_ITALIC
            if args.get("underline"):
                fmt_cursor.CharUnderline = FONT_UNDERLINE_SINGLE
            if args.get("style"):
                fmt_cursor.ParaStyleName = args["style"]
            if args.get("char_style"):
                fmt_cursor.CharStyleName = args["char_style"]
        return {"ok": True}

    def set_paragraph_style(self, args):
        doc = self._doc(args["doc_id"])
        para, count = _paragraph_at(doc, args.get("paragraph_index"))
        para.ParaStyleName = args["style"]
        return {"ok": True, "paragraph_count": count}

    def get_paragraph_style(self, args):
        doc = self._doc(args["doc_id"])
        para, count = _paragraph_at(doc, args.get("paragraph_index"))
        return {
            "style": para.ParaStyleName,
            "break_type": _break_type_name(para.BreakType),
            "paragraph_count": count,
        }

    def list_styles(self, args):
        doc = self._doc(args["doc_id"])
        family = args.get("family") or "ParagraphStyles"
        families = doc.getStyleFamilies()
        if not families.hasByName(family):
            raise ValueError(f"no style family {family!r}; known: {sorted(families.getElementNames())}")
        names = list(families.getByName(family).getElementNames())
        return {"family": family, "styles": sorted(names)}

    def insert_table(self, args):
        doc = self._doc(args["doc_id"])
        rows = int(args["rows"])
        cols = int(args["cols"])
        if rows < 1 or cols < 1:
            raise ValueError(f"rows and cols must both be >= 1, got rows={rows} cols={cols}")
        if cols > 26:
            raise ValueError(f"insert_table supports at most 26 columns, got cols={cols}")
        data = args.get("data")
        header = bool(args.get("header", False))

        table = doc.createInstance("com.sun.star.text.TextTable")
        table.initialize(rows, cols)
        text = doc.getText()
        cursor = text.createTextCursor()
        cursor.gotoEnd(False)
        text.insertTextContent(cursor, table, False)

        if data:
            for r, row_values in enumerate(data[:rows]):
                for c, value in enumerate(row_values[:cols]):
                    table.getCellByName(_cell_name(r, c)).setString(str(value))

        if header:
            for c in range(cols):
                cell = table.getCellByName(_cell_name(0, c))
                cell_cursor = cell.getText().createTextCursor()
                cell_cursor.gotoStart(False)
                cell_cursor.gotoEnd(True)
                cell_cursor.CharWeight = FONT_WEIGHT_BOLD

        return {"ok": True, "name": table.getName(), "rows": rows, "cols": cols}

    def get_table_cell(self, args):
        doc = self._doc(args["doc_id"])
        tables = doc.getTextTables()
        name = args.get("table_name")
        if name:
            if not tables.hasByName(name):
                raise ValueError(f"no table named {name!r}; known: {list(tables.getElementNames())}")
            table = tables.getByName(name)
        else:
            if tables.getCount() == 0:
                raise ValueError("document has no tables")
            table = tables.getByIndex(0)
        cell = args["cell"]
        if cell not in table.getCellNames():
            raise ValueError(f"no cell {cell!r} in table {table.getName()!r}; known: {list(table.getCellNames())}")
        return {"text": table.getCellByName(cell).getString()}

    def find_and_replace(self, args):
        doc = self._doc(args["doc_id"])
        rd = doc.createReplaceDescriptor()
        rd.setSearchString(args["search"])
        rd.setReplaceString(args["replace"])
        rd.SearchRegularExpression = bool(args.get("regex", False))
        count = doc.replaceAll(rd)
        return {"count": int(count)}

    def save_document(self, args):
        doc = self._doc(args["doc_id"])
        path = args.get("path")
        fmt = args.get("format")
        if path is None:
            if fmt is not None:
                # doc.store() always re-saves in the document's current
                # format; silently accepting `format` here would look like
                # an in-place conversion but do nothing.
                raise ValueError("format requires path; in-place save (path omitted) keeps the current format")
            if not doc.getURL():
                raise ValueError("document has no location; provide path")
            doc.store()
            return {"path": uno.fileUrlToSystemPath(doc.getURL())}
        # Save As semantics: the document now lives at `path` and is clean.
        # storeAsURL (not storeToURL) is what sets the doc's own URL and
        # clears isModified() — using storeToURL here left close_document
        # refusing to close a document that had just been successfully saved.
        filt, url = self._resolve(path, fmt)
        doc.storeAsURL(url, (_prop("FilterName", filt),))
        return {"path": path, "filter": filt}

    def export_document(self, args):
        doc = self._doc(args["doc_id"])
        path = args["path"]
        # Export semantics: write a copy to `path` without changing the
        # document's own save location or modified state (e.g. exporting an
        # in-progress .odt to .pdf shouldn't make the .odt look "saved").
        filt, url = self._resolve(path, args.get("format"))
        doc.storeToURL(url, (_prop("FilterName", filt),))
        return {"path": path, "filter": filt}

    def _resolve(self, path, fmt):
        fmt = fmt or path.rsplit(".", 1)[-1].lower()
        filt = _FILTERS.get(fmt)
        if not filt:
            raise ValueError(f"no filter for format={fmt!r}; known: {sorted(_FILTERS)}")
        return filt, uno.systemPathToFileUrl(path)

    def close_document(self, args):
        doc_id = args["doc_id"]
        doc = self._doc(doc_id)
        if doc.isModified() and not args.get("force"):
            return {
                "closed": None,
                "warning": "document has unsaved changes; save_document first or pass force=true",
            }
        doc.close(False)
        del self.docs[doc_id]
        return {"closed": doc_id}


_OPS = {
    name: getattr(WriterOps, name)
    for name in (
        "create_document",
        "open_document",
        "list_documents",
        "get_text",
        "insert_text",
        "set_paragraph_style",
        "get_paragraph_style",
        "list_styles",
        "insert_table",
        "get_table_cell",
        "find_and_replace",
        "save_document",
        "export_document",
        "close_document",
    )
}

_ops_instance = None
_ops_lock = threading.Lock()


class RequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _respond(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/ping":
            self._respond(200, {"ok": True})
        else:
            self._respond(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.headers.get(REQUIRED_HEADER) is None:
            self._respond(403, {"ok": False, "error": f"missing required {REQUIRED_HEADER} header"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
            op = req["op"]
            handler = _OPS.get(op)
            if handler is None:
                raise ValueError(f"unknown op: {op!r}; known: {sorted(_OPS)}")
            with _ops_lock:
                result = handler(_ops_instance, req.get("args", {}))
            self._respond(200, {"ok": True, "result": result})
        except Exception as e:
            logger.error("request failed: %s\n%s", e, traceback.format_exc())
            self._respond(500, {"ok": False, "error": str(e)})


_server = None
_server_thread = None


class LoMcpExtension(unohelper.Base, XJobExecutor, XJob, XServiceInfo):
    def __init__(self, ctx):
        self.ctx = ctx

    def trigger(self, args):
        """XJobExecutor: manual start/stop from the Tools > lo-mcp menu."""
        try:
            if args == "start":
                self._start()
            elif args == "stop":
                self._stop()
        except Exception:
            logger.error(traceback.format_exc())

    def execute(self, args):
        """XJob: auto-start on the OnStartApp/onFirstVisibleTask events
        (Jobs.xcu). _start() is idempotent, so it's harmless if both events
        fire and call this twice.
        """
        try:
            self._start()
        except Exception:
            logger.error(traceback.format_exc())
        return ()

    def _start(self):
        global _ops_instance, _server, _server_thread
        if _server is not None:
            logger.info("lo-mcp server already running")
            return
        _ops_instance = WriterOps(self.ctx)
        _server = http.server.ThreadingHTTPServer((HOST, PORT), RequestHandler)
        _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
        _server_thread.start()
        logger.info("lo-mcp server started on http://%s:%s", HOST, PORT)

    def _stop(self):
        global _ops_instance, _server
        if _server is None:
            return
        _server.shutdown()
        _server = None
        _ops_instance = None
        logger.info("lo-mcp server stopped")

    def getImplementationName(self):
        return IMPLEMENTATION_NAME

    def supportsService(self, name):
        return name in SERVICE_NAMES

    def getSupportedServiceNames(self):
        return SERVICE_NAMES


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(
    LoMcpExtension, IMPLEMENTATION_NAME, SERVICE_NAMES
)
