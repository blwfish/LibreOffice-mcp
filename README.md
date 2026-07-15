# lo-mcp

A stdio MCP server for LibreOffice Writer. Minimal scope on purpose: create,
edit, and export Writer documents. No Calc/Impress yet — add them later if
Writer proves useful.

## Why this shape

LibreOffice's own bundled Python interpreter (`LibreOfficePython`, used by
`import uno` for document automation) carries a macOS Launch Constraint —
spawning it as a subprocess from Claude Code's process tree gets SIGKILLed
by macOS (`CODESIGNING 4 Launch Constraint Violation`). Plain `soffice` does
not carry this constraint, but driving Writer interactively needs the `uno`
Python bindings, which only load correctly under LibreOffice's own bundled
interpreter (cross-interpreter `import uno` from an unrelated Python is an
ABI mismatch — observed to hang the process in uninterruptible sleep, not
fail cleanly).

So: a small LibreOffice extension (`extension/`) runs *inside* the
already-running `soffice` process, using LibreOffice's own already-correct
interpreter — no subprocess, no cross-interpreter import. It exposes a
local HTTP server. The MCP server (`src/lo_mcp/`) is a thin, unconstrained
client that talks to it over plain HTTP — same pattern as `freecad-mcp`
connecting to the AICopilot addon running inside FreeCAD.

## Setup

1. Build and install the extension:
   ```bash
   extension/build.sh
   /Applications/LibreOffice.app/Contents/MacOS/unopkg add --force dist/lo-mcp.oxt
   ```
2. Launch (or restart) LibreOffice.
3. In LibreOffice: **lo-mcp menu > Start Server**. This opens
   `127.0.0.1:8794` — local-only, no auth, only listens while you've
   started it.
4. Register the MCP server:
   ```bash
   uv sync
   claude mcp add lo-mcp -- uv run --project /Volumes/Files/claude/lo-mcp lo-mcp
   ```

Call `check_connection` first in any session — if LibreOffice isn't running
or the server wasn't started, it says so.

## Tools

`check_connection`, `create_document`, `open_document`, `list_documents`,
`get_text`, `insert_text`, `find_and_replace`, `save_document`,
`export_document` (pdf/docx/odt/doc/rtf/txt/html), `close_document`.

## Testing

```bash
uv run pytest
```

Requires LibreOffice running with the server started; skips otherwise.

## Extending to Calc/Impress

Add operations to `extension/pythonpath/lo_mcp_extension.py` (new `*Ops`
class or methods, registered in `_OPS`) and matching thin `@mcp.tool()`
wrappers in `src/lo_mcp/server.py`. The HTTP/extension plumbing doesn't
change.
