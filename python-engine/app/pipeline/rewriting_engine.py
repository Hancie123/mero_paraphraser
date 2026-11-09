"""Layer 4: AI rewriting engine - rewrite for clarity, fluency and the right style.

Rewrites one part at a time with the local model, using the mode's prompt plus
what layers 2 and 3 found (register, names, key terms, relationships). Without
the model it falls back to the rule-based engine so the app always works.

``drafts`` writes several versions at once (llama-server batches them) and
returns each with the model's token probabilities, so the orchestrator can keep
the least predictable one (see humanizer.py).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache

from ..core import rule_engine
from ..core.config import AVOID_WORDS, CASUAL_MODES, HUMAN_SAMPLING, MODES, PROMPTS_DIR, SAMPLING
from ..core.model_manager import ModelManager
from ..schemas.paraphrase import Context, Facts, ParaphraseError
from ..utils.text_utils import PLACEHOLDER_RE
from .humanizer import Tokens, custom_avoid_words, style_sample
from .semantic_analyzer import HEDGE_RE, NEGATION_RE

# Single-token ids for each spelling of an AVOID_WORDS entry (None: more than one
# token, so it can't be biased without hurting other words). Filled lazily.
_token_cache: dict[str, int | None] = {}


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


CASUAL_NOTE = ("Sound like a person, not a template: start sentences in different ways, let a few be short, "
               "and use contractions where they read naturally. Now and then a short fragment or a natural "
               "connector (\"That said,\" \"Here's the thing:\") is fine, used sparingly.")
FORMAL_NOTE = "Vary sentence length and how sentences begin, as a careful human writer would."
PLAIN_NOTE = FORMAL_NOTE + " Contractions are fine where the original's tone allows them; don't add slang."


def build_user_prompt(text: str, mode: str, strength: int, context: Context, facts: Facts,
                      feedback: list[str] | None = None) -> str:
    lines = [prompt(MODES[mode].prompt), strength_instruction(strength)]
    if mode in ("fluent", "creative"):
        lines.append(CASUAL_NOTE)
    elif mode in CASUAL_MODES and context.register == "general":
        lines.append(PLAIN_NOTE)
    else:
        lines.append(FORMAL_NOTE)
    sample = style_sample(mode)
    if sample:
        lines.append("Match the voice and rhythm of this human writing sample (its style only; "
                     "don't use any of its content):\n<<<\n" + sample + "\n>>>")
    if mode not in ("simple", "creative") and REGISTER_NOTES[context.register]:
        lines.append(REGISTER_NOTES[context.register])
    if facts.names:
        lines.append("Keep these names exactly as written: " + ", ".join(facts.names[:15]) + ".")
    terms = [t for t in context.terms if t in text.lower()]
    if terms:
        lines.append("Use these key terms consistently; don't swap them for loose synonyms: " + ", ".join(terms) + ".")
    if facts.numbers:
        lines.append("Keep these numbers: " + ", ".join(facts.numbers[:20]) + ".")
    # A bolder, more human rewrite tends to drop hedges ("Studies suggest" -> "Research indicates"),
    # which makes claims stronger than the author wrote. Name the exact words to keep.
    hedges = _unique(HEDGE_RE.findall(text))
    if hedges:
        lines.append("Keep exactly the hedging the original has (" + ", ".join(hedges[:8]) + "): keep these "
                     "words or ones just as tentative where they are, and don't add hedges (may, might, "
                     "potentially, it could be argued) to anything the original states plainly.")
    else:
        lines.append("The original states its claims plainly: don't add hedges such as may, might or "
                     "potentially, and don't add caveats.")
    negations = _unique(NEGATION_RE.findall(text))
    if negations:
        lines.append("Keep every negation (" + ", ".join(negations[:8]) + "), or say the same thing with "
                     "another negative word, so no statement flips.")
    if context.relationships:
        lines.append("Keep the logical relationships in the text (" + ", ".join(context.relationships) + ").")
    if feedback:
        lines.append("Your previous rewrite had these problems; avoid them this time: " + " ".join(feedback))
    return "\n".join(lines) + "\n\nText:\n" + text


@dataclass
class Draft:
    text: str  # rewritten part, with the source's surrounding whitespace
    tokens: Tokens = field(default_factory=list)  # (start, end, logprob) in ``text``; empty without the model
    prompt: str = ""  # the user prompt that produced it (for preference data)


def clean_draft(out: str, source: str, tokens: Tokens | None = None) -> Draft:
    """Strip chatty wrappers and restore the part's surrounding whitespace, keeping tokens aligned."""
    start = len(out) - len(out.lstrip())
    end = len(out.rstrip())
    for prefix in ("Here is the rewritten text:", "Here's the rewritten text:", "Rewritten text:", "Rewrite:"):
        if out[start:end].lower().startswith(prefix.lower()):
            start += len(prefix)
            start += len(out[start:end]) - len(out[start:end].lstrip())
    if end - start >= 2 and out[start] == out[end - 1] == '"' and not source.strip().startswith('"'):
        start, end = start + 1, end - 1
        start += len(out[start:end]) - len(out[start:end].lstrip())
        end = start + len(out[start:end].strip())
    body = out[start:end]
    if not body:
        return Draft(source)
    lead = source[: len(source) - len(source.lstrip())]
    trail = source[len(source.rstrip()):]
    shift = len(lead) - start
    aligned = [(a + shift, b + shift, lp, alts) for a, b, lp, alts in tokens or [] if a >= start and b <= end]
    return Draft(lead + body + trail, aligned)


def clean_reply(out: str, source: str) -> str:
    return clean_draft(out, source).text


class RewritingEngine:
    def __init__(self, model_manager: ModelManager, use_ai: bool):
        self.models = model_manager
        self.use_ai = use_ai and model_manager.installed()

    @property
    def name(self) -> str:
        return "ai" if self.use_ai else "basic"

    def rewrite(self, text: str, mode: str, strength: int, context: Context, facts: Facts,
                seed: int | None, feedback: list[str] | None = None) -> str:
        return self.drafts(text, mode, strength, context, facts, seed, feedback, 1)[0].text

    def drafts(self, text: str, mode: str, strength: int, context: Context, facts: Facts,
               seed: int | None, feedback: list[str] | None = None, n: int = 1) -> list[Draft]:
        """``n`` different rewrites of ``text``, generated in parallel."""
        seeds = [None if seed is None else seed + k * 101 for k in range(n)]
        if not self.use_ai:
            bump = 1 if feedback else 0
            return [Draft(rule_engine.paraphrase(text, MODES[mode].rule_mode, strength,
                                                 None if s is None else s + bump)["text"]) for s in seeds]
        system = prompt("system.txt")
        user = build_user_prompt(text, mode, strength, context, facts, feedback)
        extra = self.sampling(text, mode, strength, retry=bool(feedback))  # tokenizes once, before the threads
        temp = temperature(mode, strength, retry=bool(feedback))
        max_tokens = min(2048, int(len(text) / 2.5) + 128)

        def make(reply: str, tokens: Tokens) -> Draft:
            draft = clean_draft(reply, text, tokens)
            draft.prompt = user
            return draft

        def one(s: int | None) -> Draft:
            return make(*self.models.complete_scored(system, user, temperature=temp, max_tokens=max_tokens,
                                                     seed=s, extra=extra))

        if n == 1:
            return [one(seeds[0])]
        # One request for all drafts: the prompt is read once, not once per draft.
        try:
            shared = self.models.complete_scored_many(system, user, n=n, temperature=temp,
                                                      max_tokens=max_tokens, seed=seeds[0], extra=extra)
        except ParaphraseError:
            shared = []
        if len(shared) == n:
            return [make(reply, tokens) for reply, tokens in shared]
        # Older llama.cpp without n_cmpl (or the request failed): separate parallel requests.
        with ThreadPoolExecutor(max_workers=n) as pool:
            results = list(pool.map(lambda s: _try(one, s), seeds))
        good = [r for r in results if isinstance(r, Draft)]
        if not good:
            raise next(r for r in results if isinstance(r, Exception))
        return good

    def rewrite_sentence(self, part: str, start: int, end: int, mode: str, strength: int,
                         seed: int | None, vary_length: bool = False) -> str | None:
        """A fresh version of ``part[start:end]`` that fits the surrounding text, or None.

        ``vary_length`` asks for a short sentence plus a longer one, for text whose
        sentences are all about the same length.
        """
        if not self.use_ai:
            return None
        sentence = part[start:end]
        task = prompt("sentence.txt")
        if vary_length:
            task += (" The sentences around it are all about the same length, so break the pattern: "
                     "split it into one short sentence (under eight words) and one longer one.")
        user = (task + "\n\nPARAGRAPH:\n" + part[:start] + "<<" + sentence + ">>" + part[end:]
                + "\n\nSENTENCE:\n" + sentence)
        try:
            reply = self.models.complete(
                prompt("system.txt"), user,
                temperature=min(1.2, temperature(mode, strength) + 0.1),
                max_tokens=min(512, int(len(sentence) / 2) + 64),
                seed=seed,
                extra=self.sampling(sentence, mode, strength),
            )
        except ParaphraseError:
            return None
        new = clean_reply(reply, sentence).strip().strip("<>").strip()
        if "\n" in new or not new or sorted(PLACEHOLDER_RE.findall(new)) != sorted(PLACEHOLDER_RE.findall(sentence)):
            return None  # must stay one sentence with the same [[n]] tokens
        if new[-1:] not in ".!?" and sentence.rstrip()[-1:] in ".!?":
            new += sentence.rstrip()[-1]
        return new

    def sampling(self, source: str, mode: str, strength: int, retry: bool = False) -> dict:
        """Sampling settings (see HUMAN_SAMPLING), DRY + XTC and a logit_bias against AI-typical words."""
        xtc = MODES[mode].xtc * (0.5 + strength / 100)
        if retry:
            xtc /= 2  # the retry is about accuracy; take fewer risks
        params = {**HUMAN_SAMPLING, **SAMPLING, "xtc_probability": round(min(0.6, xtc), 3)}
        if retry:
            params["min_p"] = max(params["min_p"], 0.12)
        bias = self.avoid_bias(source)
        if bias:
            params["logit_bias"] = bias
        return params

    def avoid_bias(self, source: str) -> dict[str, float]:
        """Token bias for AVOID_WORDS, except words the source itself uses."""
        src = source.lower()
        bias: dict[str, float] = {}
        for word, value in {**AVOID_WORDS, **custom_avoid_words()}.items():
            if word in src:
                continue
            spellings = {word, " " + word} if not word.isalpha() else {
                word, " " + word, word.capitalize(), " " + word.capitalize()}
            for spelling in spellings:
                token = self._single_token(spelling)
                if token is not None:
                    bias[str(token)] = value
        return bias

    def _single_token(self, spelling: str) -> int | None:
        if spelling not in _token_cache:
            try:
                ids = self.models.tokenize(spelling)
            except ParaphraseError:
                return None  # not cached: try again next time
            _token_cache[spelling] = ids[0] if len(ids) == 1 else None
        return _token_cache[spelling]


def _try(fn, arg):
    try:
        return fn(arg)
    except Exception as exc:  # one failed draft shouldn't lose the others
        return exc


def _unique(words: list[str]) -> list[str]:
    return list(dict.fromkeys(w.lower() for w in words))
