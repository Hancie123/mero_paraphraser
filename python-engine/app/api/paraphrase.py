"""Request handlers for the engine protocol (see app/main.py)."""

from __future__ import annotations

import base64
import binascii
import os
import time

from ..core.config import MODES, VERSION
from ..pipeline.orchestrator import ParaphrasePipeline
from ..schemas.paraphrase import ParaphraseError, ParaphraseRequest
from ..utils.docx import MAX_DOCX_BYTES, DocxError, build_docx, clean_docx, read_docx


def paraphrase(req: dict) -> dict:
    return ParaphrasePipeline().process(ParaphraseRequest.from_dict(req))


def _bytes(req: dict) -> bytes:
    data = req.get("data")
    if not isinstance(data, str) or len(data) > MAX_DOCX_BYTES * 4 // 3 + 4:
        raise ParaphraseError("data must be a base64 string of at most 25 MB")
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise ParaphraseError("data is not valid base64") from None


def _b64(blob: bytes) -> str:
    return base64.b64encode(blob).decode("ascii")


def handle(req: dict) -> dict:
    cmd = req.get("cmd")
    try:
        if cmd == "ping":
            return {"version": VERSION, "modes": list(MODES)}
        if cmd == "paraphrase":
            return paraphrase(req)
        if cmd == "export_docx":
            text = req.get("text", "")
            if not isinstance(text, str):
                raise ParaphraseError("text must be a string")
            return {"data": _b64(build_docx(text))}
        if cmd == "read_docx":
            return {"text": read_docx(_bytes(req))}
        if cmd == "clean_docx":
            blob, removed = clean_docx(_bytes(req))
            return {"data": _b64(blob), "removed": removed}
        if cmd == "sleep" and os.environ.get("MERO_ENGINE_TESTING") == "1":
            # Lets the app's tests simulate a stuck engine (timeout / cancel).
            time.sleep(float(req.get("seconds", 1)))
            return {}
    except DocxError as exc:
        raise ParaphraseError(str(exc)) from None
    raise ParaphraseError(f"unknown command {cmd!r}")
