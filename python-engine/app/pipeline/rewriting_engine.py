"""Layer 4: AI rewriting engine - rewrite for clarity, fluency and the right style.

Rewrites one part at a time with the local model, using the mode's prompt plus
what layers 2 and 3 found (register, names, key terms, relationships). Without
the model it falls back to the rule-based engine so the app always works.
"""

from __future__ import annotations

from functools import lru_cache

from ..core import rule_engine
from ..core.config import MODES, PROMPTS_DIR
from ..core.model_manager import ModelManager
from ..schemas.paraphrase import Context, Facts


@lru_cache(maxsize=None)
def prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def strength_instruction(strength: int) -> str:
    if strength < 34:
        return "Make light edits: change some words and phrases, and keep most sentence structures."
    if strength < 67:
        return "Rewrite it moderately: rephrase most sentences and restructure some of them."
    return "Rewrite it thoroughly: restructure the sentences and change most of the wording."


def temperature(mode: str, strength: int, retry: bool = False) -> float:
    t = 0.5 + 0.4 * strength / 100 + MODES[mode].temperature
    if retry:
        t -= 0.25  # a calmer second attempt
    return round(max(0.1, min(1.2, t)), 2)


REGISTER_NOTES = {
    "academic": "The source is academic writing; keep an appropriate academic register and precise terminology.",
    "professional": "The source is professional writing; keep it polished and appropriate for work.",
    "general": "",
}


def build_user_prompt(text: str, mode: str, strength: int, context: Context, facts: Facts,
                      feedback: list[str] | None = None) -> str:
    lines = [prompt(MODES[mode].prompt), strength_instruction(strength)]
    if mode not in ("simple", "creative") and REGISTER_NOTES[context.register]:
        lines.append(REGISTER_NOTES[context.register])
    if facts.names:
        lines.append("Keep these names exactly as written: " + ", ".join(facts.names[:15]) + ".")
    terms = [t for t in context.terms if t in text.lower()]
    if terms:
        lines.append("Use these key terms consistently; don't swap them for loose synonyms: " + ", ".join(terms) + ".")
    if facts.numbers:
        lines.append("Keep these numbers: " + ", ".join(facts.numbers[:20]) + ".")
    if context.relationships:
        lines.append("Keep the logical relationships in the text (" + ", ".join(context.relationships) + ").")
    if feedback:
        lines.append("Your previous rewrite had these problems; avoid them this time: " + " ".join(feedback))
    return "\n".join(lines) + "\n\nText:\n" + text


def clean_reply(out: str, source: str) -> str:
    """Strip chatty wrappers and restore the part's surrounding whitespace."""
    out = out.strip()
    for prefix in ("Here is the rewritten text:", "Here's the rewritten text:", "Rewritten text:", "Rewrite:"):
        if out.lower().startswith(prefix.lower()):
            out = out[len(prefix):].lstrip()
    if len(out) >= 2 and out[0] == out[-1] == '"' and not source.strip().startswith('"'):
        out = out[1:-1].strip()
    if not out:
        return source
    lead = source[: len(source) - len(source.lstrip())]
    trail = source[len(source.rstrip()):]
    return lead + out + trail


class RewritingEngine:
    def __init__(self, model_manager: ModelManager, use_ai: bool):
        self.models = model_manager
        self.use_ai = use_ai and model_manager.installed()

    @property
    def name(self) -> str:
        return "ai" if self.use_ai else "basic"

    def rewrite(self, text: str, mode: str, strength: int, context: Context, facts: Facts,
                seed: int | None, feedback: list[str] | None = None) -> str:
        if not self.use_ai:
            seed = None if seed is None else seed + (1 if feedback else 0)
            return rule_engine.paraphrase(text, MODES[mode].rule_mode, strength, seed)["text"]
        reply = self.models.complete(
            prompt("system.txt"),
            build_user_prompt(text, mode, strength, context, facts, feedback),
            temperature=temperature(mode, strength, retry=bool(feedback)),
            max_tokens=min(2048, int(len(text) / 2.5) + 128),
            seed=seed,
        )
        return clean_reply(reply, text)
