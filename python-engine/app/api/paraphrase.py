"""Request handlers for the engine protocol (see app/main.py)."""

from __future__ import annotations

from ..core.config import MODES, VERSION
from ..core.model_manager import ModelManager
from ..pipeline.orchestrator import ParaphrasePipeline
from ..schemas.paraphrase import ParaphraseError, ParaphraseRequest

model_manager = ModelManager()


def paraphrase(req: dict) -> dict:
    """``engine``: "basic" (rule-based, the default), "ai" (local model) or "auto" (AI when installed)."""
    request = ParaphraseRequest.from_dict(req)
    if request.engine == "ai" and not model_manager.installed():
        raise ParaphraseError("the AI model is not installed")
    use_ai = request.engine in ("ai", "auto")
    return ParaphrasePipeline(model_manager, use_ai).process(request)


def handle(req: dict) -> dict:
    cmd = req.get("cmd")
    if cmd == "ping":
        return {"version": VERSION, "modes": list(MODES), "ai": model_manager.status()}
    if cmd == "paraphrase":
        return paraphrase(req)
    if cmd == "ai_status":
        return model_manager.status()
    if cmd == "ai_download":
        return model_manager.start_download()
    if cmd == "ai_cancel":
        return model_manager.cancel_download()
    if cmd == "ai_remove":
        return model_manager.remove()
    if cmd == "ai_warm":
        return model_manager.warm()
    raise ParaphraseError(f"unknown command {cmd!r}")
