"""Engine settings: limits, modes, pinned AI downloads and data folders."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

VERSION = "0.1.0"

APP_DIR = Path(__file__).resolve().parents[1]  # python-engine/app
ENGINE_DIR = APP_DIR.parent  # python-engine
PROMPTS_DIR = APP_DIR / "prompts"

MAX_CHARS = 20_000
CHUNK_CHARS = 1_500  # the rewriting layer works a few paragraphs at a time
CONTEXT_TOKENS = 4_096
STARTUP_TIMEOUT = 180  # seconds to wait for the model to load
MAX_ATTEMPTS = 2  # a part that fails validation is rewritten once more


@dataclass(frozen=True)
class ModeSpec:
    label: str
    prompt: str  # file name in app/prompts
    rule_mode: str  # mode used by the rule-based fallback engine
    temperature: float = 0.0  # added to the strength-based temperature
    length: tuple[float, float] = (0.55, 1.7)  # allowed output/input word ratio


MODES: dict[str, ModeSpec] = {
    "standard": ModeSpec("Standard", "standard.txt", "standard"),
    "academic": ModeSpec("Academic", "academic.txt", "formal", -0.05),
    "professional": ModeSpec("Professional", "professional.txt", "formal", -0.1),
    "fluent": ModeSpec("Fluent", "fluent.txt", "fluent"),
    "simple": ModeSpec("Simple", "simple.txt", "simple", length=(0.4, 1.6)),
    "creative": ModeSpec("Creative", "creative.txt", "creative", 0.1, (0.55, 1.9)),
    "shorten": ModeSpec("Shorten", "shorten.txt", "shorten", -0.1, (0.25, 1.0)),
}
MODE_ALIASES = {"formal": "professional"}  # older clients


# ---------------------------------------------------------------- AI model

MODEL_NAME = "Qwen3 4B Instruct"
BUNDLE_ID = "com.merovision.paraphraser"  # matches tauri.conf.json; the uninstaller cleans this folder


@dataclass(frozen=True)
class Download:
    name: str
    url: str
    sha256: str
    size: int
    target: str  # path relative to the AI home folder
    extract: bool = False


# Pinned, checksummed downloads. Update URL, SHA-256 and size together
# (and MERO_AI_MODEL_FILE in src-tauri/windows/hooks.nsh for the model).
RUNTIME = Download(
    "llama.cpp runtime",
    "https://github.com/ggml-org/llama.cpp/releases/download/b12211/llama-b12211-bin-win-cpu-x64.zip",
    "23729000408c6968faf5e322afc99319d3b8c576ba872ef7663d9b89810090f3",
    24_886_431,
    "runtime/b12211",
    extract=True,
)
MODEL = Download(
    MODEL_NAME,
    "https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/"
    "a06e946bb6b655725eafa393f4a9745d460374c9/Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
    "3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597",
    2_497_281_120,
    "models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
)
DOWNLOADS = (RUNTIME, MODEL)


def ai_home() -> Path:
    """Where the downloaded/installed runtime and model live."""
    if os.environ.get("MERO_AI_HOME"):
        return Path(os.environ["MERO_AI_HOME"])
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / BUNDLE_ID / "ai"
    return Path.home() / ".local" / "share" / BUNDLE_ID / "ai"


def local_model() -> Path | None:
    """A model placed at python-engine/models/model.gguf (development) wins over the installed one."""
    if os.environ.get("MERO_AI_MODEL"):
        return Path(os.environ["MERO_AI_MODEL"])
    p = ENGINE_DIR / "models" / "model.gguf"
    return p if p.is_file() else None
