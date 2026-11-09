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
    xtc: float = 0.0  # XTC probability at moderate strength (0 = off); see SAMPLING


MODES: dict[str, ModeSpec] = {
    "standard": ModeSpec("Standard", "standard.txt", "standard", xtc=0.15),
    "academic": ModeSpec("Academic", "academic.txt", "formal", -0.05, xtc=0.0),
    "professional": ModeSpec("Professional", "professional.txt", "formal", -0.1, xtc=0.0),
    "fluent": ModeSpec("Fluent", "fluent.txt", "fluent", xtc=0.1),
    # XTC favours less common words: off where precision or plain wording matters.
    "simple": ModeSpec("Simple", "simple.txt", "simple", length=(0.4, 1.6), xtc=0.0),
    "creative": ModeSpec("Creative", "creative.txt", "creative", 0.1, (0.55, 1.9), xtc=0.4),
    "shorten": ModeSpec("Shorten", "shorten.txt", "shorten", -0.1, (0.25, 1.0), xtc=0.0),
}

# ---------------------------------------------------------------- Layer 4 sampling (llama.cpp)
#
# DRY penalises repeating any sequence longer than dry_allowed_length tokens
# that already appears in the context, which discourages formulaic repetition
# and copying the source verbatim. Brackets and parentheses are sequence
# breakers so the [[n]] placeholders and citations can be copied freely.
# XTC sometimes removes the most likely tokens when several are plausible,
# so the wording is less predictable. Its probability is set per mode.
SAMPLING = {
    "dry_multiplier": 0.5,
    "dry_base": 1.75,
    "dry_allowed_length": 4,
    "dry_penalty_last_n": CONTEXT_TOKENS,  # whole context (this llama.cpp build rejects -1)
    "dry_sequence_breakers": ["\n", ":", '"', "*", "[", "]", "(", ")"],
    "xtc_threshold": 0.1,
}

# Words that make text read as AI-written, discouraged while generating via
# logit_bias (-100 is a ban). Skipped when the source itself uses the word.
# Multi-word phrases are handled afterwards by Layer 5 (language_refiner).
AVOID_WORDS: dict[str, float] = {
    "delve": -100, "delves": -100, "delved": -100, "delving": -100,
    "tapestry": -100, "testament": -8, "multifaceted": -8, "realm": -6,
    "seamless": -6, "seamlessly": -6, "embark": -6, "showcasing": -5,
    "underscore": -5, "underscores": -5, "pivotal": -5, "intricate": -4,
    "moreover": -5, "furthermore": -5, "additionally": -3, "notably": -3,
    "crucial": -3, "leverage": -3, "foster": -2, "robust": -2, "heightened": -4,
    "meticulous": -6, "meticulously": -6, "paramount": -5, "commendable": -6,
    "unwavering": -6, "holistic": -4, "synergy": -6, "bustling": -6, "vibrant": -3,
    "nuanced": -3, "utilize": -4, "utilizes": -4, "utilized": -4, "facilitate": -3,
    "facilitates": -3, "endeavor": -4, "endeavors": -4, "myriad": -5, "plethora": -6,
    "invaluable": -4, "noteworthy": -4, "profound": -2, "transformative": -4,
    "elevate": -5, "elevates": -5, "dynamically": -5, "landscape": -3,
    "—": -8,  # em dash
}

# ---------------------------------------------------------------- Human-like output (app/pipeline/humanizer.py)
#
# AI detectors such as GPTZero score text by how predictable each word is to a
# language model (perplexity) and how much that varies between sentences
# (burstiness). Layer 4 therefore writes several drafts in parallel, scores
# each with the model's own token probabilities, and keeps the least
# predictable one that still passes validation. It then rewrites the flattest
# sentence and swaps a few of the most predictable words for synonyms.
PARALLEL = 3  # llama-server slots: drafts are generated at the same time
SERVER_CONTEXT = CONTEXT_TOKENS * 2  # one KV pool shared by the slots (--kv-unified)


def drafts_for(strength: int) -> int:
    """Number of drafts Layer 4 writes per part (MERO_DRAFTS overrides it)."""
    if os.environ.get("MERO_DRAFTS"):
        return max(1, min(PARALLEL, int(os.environ["MERO_DRAFTS"])))
    return 2 if strength < 34 else 3


# Replaces llama.cpp's top_k 40 / top_p 0.9 for rewrites: those cut off every
# less likely word, which is exactly what makes model text predictable. min_p
# still drops nonsense, and dynamic temperature runs cooler when the model is
# sure (names, numbers, [[n]] tokens) and warmer when several words fit.
HUMAN_SAMPLING = {
    "top_k": 0,
    "top_p": 1.0,
    "min_p": 0.08,
    "dynatemp_range": 0.3,
    "dynatemp_exponent": 1.0,
}
SWAP_RATE = 0.05  # share of words swapped for synonyms at strength 100 (scaled down below)
SWAP_MIN_PROB = 0.6  # only words the model was at least this sure of are swapped
MAX_SWAPS = 6  # per part
FLAT_SENTENCE = 0.5  # rewrite a sentence whose surprisal is below this share of the part's average
CASUAL_MODES = ("standard", "fluent", "creative", "simple")  # contractions, "And"/"But" openers
STYLE_SAMPLE_CHARS = 1_200  # longest style sample put in the prompt
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


def style_dirs() -> list[Path]:
    """Folders searched for human writing samples (<mode>.txt, then all.txt); the user's folder wins."""
    if os.environ.get("MERO_STYLE_DIR"):
        return [Path(os.environ["MERO_STYLE_DIR"])]
    return [ai_home().parent / "style", PROMPTS_DIR / "style"]


def local_model() -> Path | None:
    """A model placed at python-engine/models/model.gguf (development) wins over the installed one."""
    if os.environ.get("MERO_AI_MODEL"):
        return Path(os.environ["MERO_AI_MODEL"])
    p = ENGINE_DIR / "models" / "model.gguf"
    return p if p.is_file() else None
