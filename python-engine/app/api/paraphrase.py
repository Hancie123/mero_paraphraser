"""Request handlers for the engine protocol (see app/main.py)."""

from __future__ import annotations

import base64
import binascii
import os
import time

from ..core import thesaurus
from ..core.config import MODES, VERSION
from ..pipeline.orchestrator import ParaphrasePipeline
from ..schemas.paraphrase import ParaphraseError, ParaphraseRequest
from ..utils.docx import MAX_DOCX_BYTES, DocxError, build_docx, clean_docx, read_docx


def paraphrase(req: dict) -> dict:
    return ParaphrasePipeline().process(ParaphraseRequest.from_dict(req))


def suggest(req: dict) -> dict:
    """Similar words for one word of the result, grouped by meaning (the word picker)."""
    word, context = req.get("word", ""), req.get("context", "")
    if not isinstance(word, str) or not isinstance(context, str) or len(word) > 60 or len(context) > 2000:
        raise ParaphraseError("word and context must be short strings")
    word = word.strip()
    senses = thesaurus.senses_for(word, context)
    risky = bool(senses) and thesaurus.is_risky(word)
    return {
        "word": word,
        "senses": [s.to_dict() for s in senses],
        "note": thesaurus.FROZEN_NOTE if risky else "",
    }


# Rephrasing a selection: a few versions, each from its own seed, with more change than
# the main run so the versions actually differ. MAX_TRIES bounds the work for short text
# that keeps coming back the same.
REPHRASE_MIN_STRENGTH = 60
REPHRASE_MIN_RESTRUCTURE = 70
REPHRASE_MAX_CHARS = 2_000


def rephrase(req: dict) -> dict:
    """2-3 different rewrites of a selected sentence or phrase."""
    text = req.get("text", "")
    if not isinstance(text, str) or not text.strip():
        raise ParaphraseError("text must be a non-empty string")
    if len(text) > REPHRASE_MAX_CHARS:
        raise ParaphraseError(f"select at most {REPHRASE_MAX_CHARS:,} characters to rephrase")
    count = max(1, min(5, int(req.get("count", 3))))
    base = ParaphraseRequest.from_dict({**req, "cmd": "paraphrase"})
    seed = base.seed if base.seed is not None else 0
    pipeline = ParaphrasePipeline()
    seen = {" ".join(text.split()).lower()}
    out: list[str] = []
    for k in range(count * 4):
        request = ParaphraseRequest(
            text,
            base.mode,
            max(base.strength, REPHRASE_MIN_STRENGTH),
            seed + k * 7919,
            base.prefs,
            max(base.restructure, REPHRASE_MIN_RESTRUCTURE),
        )
        result = pipeline.process(request)
        if result["report"]["warnings"]:
            continue  # a version that lost a number, name or negation is not offered
        key = " ".join(result["text"].split()).lower()
        if key not in seen:
            seen.add(key)
            out.append(result["text"])
        if len(out) == count:
            break
    return {"alternatives": out}


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
        if cmd == "suggest":
            return suggest(req)
        if cmd == "rephrase":
            return rephrase(req)
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
