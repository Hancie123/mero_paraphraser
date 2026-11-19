"""Build app/data/pos_lexicon.json: part-of-speech data for the Layer 4b tagger.

Build-time only (nltk + wordfreq); the engine reads the JSON with the standard
library:

    python -m pip install -r python-engine/tools/requirements-build.txt
    python python-engine/tools/build_pos.py

Two tables:

* ``tags``: for each common WordNet lemma, its parts of speech ("n", "v",
  "a", "r") ordered by how often WordNet's tagged corpus uses each one, keeping
  only those with at least --min-share of the uses. "increase" -> "nv",
  "fast" -> "ar". Inflected forms are not stored; app/core/pos.py strips
  suffixes ("analysed" -> "analyse") and knows the irregular verbs.
* ``nominal``: noun -> verb for nominalisations ("implementation" ->
  "implement"), from WordNet's derivational links. Both words must be common,
  the noun must end in a nominal suffix, and the two must share a stem, so
  only the plain "-tion of" kind is kept and not loose links like
  "cause" -> "induce".
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
OUT = ENGINE / "app" / "data" / "pos_lexicon.json"

_WN = {"n": "n", "v": "v", "a": "a", "s": "a", "r": "r"}
_NOMINAL_SUFFIXES = ("tion", "sion", "ment", "ance", "ence", "ysis", "al", "ure")
# Derivational links that read wrongly as "-ing" forms or change meaning.
_BAD_NOMINAL = {"approval", "proposal", "arrival", "survival", "refusal", "removal", "denial", "trial", "rental",
                "nature", "creature", "feature", "measure", "pressure", "pleasure", "structure", "culture",
                "agreement", "statement", "department", "apartment", "government", "movement", "element",
                "ration", "nation", "station", "relation", "position", "condition", "question", "mention",
                # the noun's usual sense is not the act of the verb ("the institution of marriage")
                "accordance", "institution", "constitution", "composition", "admiration", "exhibition",
                "clearance", "contraction", "perfection", "governance", "inheritance", "judgment",
                "occupation", "concession", "delegation", "corruption", "attribution", "accommodation",
                "attention", "appearance", "assurance", "ordinance", "resistance", "acceptance",
                "allowance", "conference", "difference", "reference", "preference", "existence",
                "publication", "application", "association", "organization", "foundation", "generation",
                "election", "collection", "selection", "direction", "production", "construction",
                "settlement", "establishment", "entertainment", "excitement", "equipment", "treatment"}  # fmt: skip


def build(min_zipf: float, min_share: float) -> dict:
    from nltk.corpus import wordnet as wn
    from wordfreq import zipf_frequency

    counts: dict[str, dict[str, int]] = {}
    for synset in wn.all_synsets():
        pos = _WN[synset.pos()]
        for lemma in synset.lemmas():
            word = lemma.name()
            if not word.isalpha() or not word.islower():
                continue
            per = counts.setdefault(word, {})
            per[pos] = per.get(pos, 0) + lemma.count() + 1  # +1 so untagged senses still count a little

    tags: dict[str, str] = {}
    for word, per in counts.items():
        if zipf_frequency(word, "en") < min_zipf:
            continue
        total = sum(per.values())
        kept = sorted((p for p, c in per.items() if c / total >= min_share), key=lambda p: -per[p])
        tags[word] = "".join(kept)

    nominal: dict[str, str] = {}
    for synset in wn.all_synsets("n"):
        for lemma in synset.lemmas():
            noun = lemma.name()
            if noun in nominal or noun in _BAD_NOMINAL or not noun.endswith(_NOMINAL_SUFFIXES):
                continue
            if tags.get(noun, "")[:1] != "n" or zipf_frequency(noun, "en") < min_zipf + 0.5:
                continue
            for rel in lemma.derivationally_related_forms():
                verb = rel.name()
                if rel.synset().pos() != "v" or not verb.isalpha() or len(verb) < 4:
                    continue
                if "v" not in tags.get(verb, "") or zipf_frequency(verb, "en") < min_zipf + 0.5:
                    continue
                if noun[:4] == verb[:4] and len(noun) > len(verb):
                    nominal[noun] = verb
                    break
    return {"tags": dict(sorted(tags.items())), "nominal": dict(sorted(nominal.items()))}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--min-zipf", type=float, default=2.8, help="skip words rarer than this (wordfreq Zipf)")
    p.add_argument("--min-share", type=float, default=0.12, help="keep a part of speech used this often or more")
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args()
    data = build(args.min_zipf, args.min_share)
    about = "Generated by tools/build_pos.py from WordNet (WordNet license) and wordfreq. Do not edit."
    args.out.write_text(
        json.dumps({"_about": about, **data}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.out} ({len(data['tags'])} words, {len(data['nominal'])} nominalisations)")


if __name__ == "__main__":
    main()
