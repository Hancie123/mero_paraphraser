"""Request handlers for the engine protocol (see app/main.py)."""

from __future__ import annotations

from ..core.config import MODES, VERSION
from ..pipeline.orchestrator import ParaphrasePipeline
from ..schemas.paraphrase import ParaphraseError, ParaphraseRequest


def paraphrase(req: dict) -> dict:
    return ParaphrasePipeline().process(ParaphraseRequest.from_dict(req))


def handle(req: dict) -> dict:
    cmd = req.get("cmd")
    if cmd == "ping":
        return {"version": VERSION, "modes": list(MODES)}
    if cmd == "paraphrase":
        return paraphrase(req)
    raise ParaphraseError(f"unknown command {cmd!r}")
