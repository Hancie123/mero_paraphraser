"""Build app/data/synonyms_extra.json: adjective and adverb synonyms from WordNet.

Build-time only. The engine reads the JSON with the standard library, so nltk
and wordfreq are never bundled:

    python -m pip install -r python-engine/tools/requirements-build.txt
    python python-engine/tools/build_lexicon.py

Only ``humanizer.swap_predictable`` (and the editor's word suggestions) use
these words. A swap there still needs the model to rate the synonym likely at
that exact spot, so the list can be broad without producing odd rewrites. The
offline rule engine keeps to the hand-written groups in app/core/lexicon.py,
which always win over generated entries.

Filters, in order:

* the word must be common (wordfreq Zipf >= --min-zipf) and used mostly as an
  adjective/adverb (WordNet sense counts), so "present" or "fast" are skipped;
* only its most frequent sense or two are used, never loose "similar to" links;
* verb participles ("tested", "verifying") are skipped on both sides;
* a synonym must be a single common word, not far rarer than the original,
  not the same stem, and not itself mostly a noun or verb;
* the shared sense must be the synonym's most common sense, so a rare reading
  ("loudly" as "aloud", "needs" as "necessarily") does not link two words that
  usually mean different things;
* EXCLUDE and BAD_PAIRS remove what is left after reviewing the output.
"""

from __future__ import annotations

import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))

from app.core import lexicon as lx  # noqa: E402
from app.core.config import AVOID_WORDS  # noqa: E402
from app.utils.text_utils import STOPWORDS  # noqa: E402

OUT = ENGINE / "app" / "data" / "synonyms_extra.json"

# WordNet tags for each lexicon part of speech ("s" is a satellite adjective)
TARGETS = {lx.A: ("a", "s"), lx.R: ("r",)}

# Words WordNet groups wrongly for everyday prose; extend after reviewing the output.
EXCLUDE = {
    "dead", "gay", "queer", "bloody", "damn", "damned", "fucking", "sick", "hot", "high", "stoned",
    "wet", "dry", "loose", "easy", "cheap", "fresh", "straight", "bent", "blue", "green", "black",
    "white", "red", "yellow", "brown", "pink", "grey", "gray", "colored", "coloured",
    # slang and dated slang
    "kinda", "sorta", "groovy", "keen", "swell", "nifty", "dandy", "cool", "wicked", "awesome",
    "horny", "randy", "loco", "nuts", "bats", "crackers", "daft", "alas", "scarce", "satanic",
    "infernal", "demonic", "unholy", "shitty", "crappy", "fab", "wee", "oft", "needs", "forth",
    "anyways", "comfy", "foxy", "wacky", "madly",
    # proper adjectives: never interchangeable
    "celtic", "gaelic",
    # WordNet's main sense for these is not the everyday one (null, vain, struck, ...)
    "primal", "haired", "hairy", "null", "void", "singular", "smitten", "struck", "stricken",
    "swollen", "vain", "gilt", "sterling", "nomadic", "mobile", "monolithic", "pictorial", "mute",
    "unspoken", "outrageous", "funky", "smelly", "fussy", "grumpy", "crimson", "reddish", "extra",
    "redundant", "fatal", "fateful", "drawn", "worn", "undefined", "presently", "instead",
    "alternatively", "sooner", "earlier",
    # common words with other roles ("little time", "work hard", "later in the year", "highly
    # regarded", "simply put", "fine sand")
    "little", "hard", "later", "highly", "simply", "fine", "notwithstanding",
}

# Pairs that share a WordNet sense but read differently in modern prose; blocked both ways.
_BAD = [
    ("rather", "instead"), ("central", "fundamental"), ("plain", "apparent"), ("plain", "evident"),
    ("remarkable", "singular"), ("cheery", "sunny"), ("chic", "smart"), ("problematic", "debatable"),
    ("insistent", "repetitive"), ("ferocious", "furious"), ("fierce", "furious"),
    ("stern", "relentless"), ("stern", "grim"), ("grim", "relentless"), ("fertile", "prolific"),
    ("differently", "otherwise"), ("systematically", "consistently"), ("disruptive", "turbulent"),
    ("disruptive", "tumultuous"), ("really", "actually"), ("gently", "mildly"),
    ("arbitrarily", "randomly"), ("cultural", "ethnic"), ("alien", "exotic"),
    ("aforementioned", "said"), ("crude", "earthy"), ("delicious", "delightful"), ("full", "entire"),
    ("fundamental", "rudimentary"), ("grotesque", "fantastic"), ("hideous", "horrific"),
    ("honorable", "honest"), ("integral", "intact"), ("integral", "inherent"), ("miserable", "poor"),
    ("poor", "pathetic"), ("religious", "spiritual"), ("tender", "sore"), ("unparalleled", "unique"),
    ("crisp", "sharp"), ("dramatic", "spectacular"), ("mysterious", "mystic"),
    ("particular", "special"), ("funny", "curious"), ("funny", "comic"), ("sober", "solemn"),
    ("lousy", "rotten"), ("older", "elderly"), ("everyday", "mundane"), ("bare", "naked"),
    ("tremendous", "wonderful"), ("tremendous", "marvelous"), ("tremendous", "marvellous"),
    ("aggressively", "sharply"), ("brightly", "brilliantly"), ("constantly", "invariably"),
    ("desperately", "urgently"), ("necessarily", "inevitably"), ("purely", "strictly"),
    ("badly", "severely"), ("unusually", "remarkably"), ("perfectly", "utterly"),
    ("absolutely", "perfectly"), ("faithfully", "reliably"), ("firmly", "securely"),
]
BAD_PAIRS = {p for a, b in _BAD for p in ((a, b), (b, a))}


def spelling_variant(a: str, b: str) -> bool:
    """colourful/colorful, sceptical/skeptical, sizeable/sizable: the same word, not a synonym."""
    return SequenceMatcher(None, a, b).ratio() >= 0.8


def pos_share(wn, word: str, targets: tuple[str, ...]) -> float:
    """Share of ``word``'s tagged uses (SemCor counts) that are the target part of speech."""
    lemmas = wn.lemmas(word)
    total = sum(lemma.count() for lemma in lemmas)
    if total == 0:  # never tagged: accept only words WordNet has in no other part of speech
        return 1.0 if lemmas and all(lemma.synset().pos() in targets for lemma in lemmas) else 0.0
    return sum(lemma.count() for lemma in lemmas if lemma.synset().pos() in targets) / total


def verb_form(wn, word: str) -> bool:
    """True for participles like "tested" or "verifying": swapping them can hit a verb ("they tested it")."""
    return word.endswith(("ed", "ing")) and wn.morphy(word, wn.VERB) not in (None, word)


def main_senses(wn, word: str, targets: tuple[str, ...]) -> list:
    """The word's first sense, plus the second when it is used at least a quarter as often."""
    senses = []
    for synset in wn.synsets(word):
        if synset.pos() not in targets:
            continue
        count = next((lemma.count() for lemma in synset.lemmas() if lemma.name().lower() == word), 0)
        senses.append((synset, count))
    if not senses:
        return []
    first, top = senses[0]
    out = [first]
    if len(senses) > 1 and top > 0 and senses[1][1] >= top / 4:
        out.append(senses[1][0])
    return out


def build(min_zipf: float, max_gap: float, max_synonyms: int, min_share: float) -> dict[str, dict[str, list[str]]]:
    from nltk.corpus import wordnet as wn
    from wordfreq import zipf_frequency

    def zipf(word: str) -> float:
        return zipf_frequency(word, "en")

    def plain(word: str) -> bool:
        return word.isalpha() and word.isascii() and word.islower()

    hand_written = set(lx.SYNONYMS)
    result: dict[str, dict[str, list[str]]] = {}
    for pos, targets in TARGETS.items():
        entries: dict[str, list[str]] = {}
        names = {n for t in targets for n in wn.all_lemma_names(pos=t)}
        for word in sorted(names):
            if (not plain(word) or len(word) < 4 or word in hand_written or word in STOPWORDS
                    or word in EXCLUDE or word in AVOID_WORDS or verb_form(wn, word)):
                continue
            freq = zipf(word)
            if freq < min_zipf or pos_share(wn, word, targets) < min_share:
                continue
            candidates: dict[str, float] = {}
            for synset in main_senses(wn, word, targets):
                for lemma in synset.lemmas():
                    alt = lemma.name().lower()
                    if (alt == word or alt in candidates or not plain(alt) or len(alt) < 3
                            or alt[:5] == word[:5] or alt in EXCLUDE or alt in AVOID_WORDS or alt in STOPWORDS
                            or (word, alt) in BAD_PAIRS or spelling_variant(word, alt)):
                        continue
                    alt_freq = zipf(alt)
                    if alt_freq < min_zipf or alt_freq < freq - max_gap:
                        continue
                    if verb_form(wn, alt) or pos_share(wn, alt, targets) < min_share:
                        continue
                    if synset not in main_senses(wn, alt, targets)[:1]:
                        continue  # the synonym's own most common meaning
                    if any(spelling_variant(alt, c) for c in candidates):
                        continue  # marvelous and marvellous: keep one
                    candidates[alt] = alt_freq
            if candidates:
                ranked = sorted(candidates, key=lambda a: (-candidates[a], a))
                entries[word] = ranked[:max_synonyms]
        result[pos] = entries
    return result


def dump(payload: dict) -> str:
    """JSON with one word per line, so regenerating gives a readable diff."""
    lines = ["{", f' "_about": {json.dumps(payload["_about"])},']
    groups = [k for k in payload if k != "_about"]
    for gi, pos in enumerate(groups):
        lines.append(f' "{pos}": {{')
        items = sorted(payload[pos].items())
        for i, (word, alts) in enumerate(items):
            lines.append(f"  {json.dumps(word)}: {json.dumps(alts)}" + ("," if i < len(items) - 1 else ""))
        lines.append(" }" + ("," if gi < len(groups) - 1 else ""))
    return "\n".join(lines + ["}", ""])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--min-zipf", type=float, default=3.0, help="minimum word frequency (Zipf scale, 3 = once per million words)")
    p.add_argument("--max-gap", type=float, default=1.5, help="how much rarer than the original a synonym may be (Zipf)")
    p.add_argument("--max-synonyms", type=int, default=4)
    p.add_argument("--min-share", type=float, default=0.7, help="minimum share of uses as an adjective/adverb")
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args()

    import nltk
    nltk.download("wordnet", quiet=True)

    data = build(args.min_zipf, args.max_gap, args.max_synonyms, args.min_share)
    payload = {"_about": "Generated by tools/build_lexicon.py from WordNet 3.0 and wordfreq. Do not edit; "
                         "add words to app/core/lexicon.py (they take priority) or EXCLUDE instead.",
               **data}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(dump(payload), encoding="utf-8")
    counts = ", ".join(f"{len(v)} {'adjectives' if k == lx.A else 'adverbs'}" for k, v in data.items())
    print(f"Wrote {args.out} ({counts})")


if __name__ == "__main__":
    main()
