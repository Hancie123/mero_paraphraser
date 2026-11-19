"""A small part-of-speech tagger and verb inflection, standard library only.

Used by Layer 4b (pipeline/sentence_rewriter.py) to match sentence patterns
on tagged words rather than raw text.

Open-class words come from app/data/pos_lexicon.json (built by
tools/build_pos.py from WordNet): each lemma lists its parts of speech, most
common first. Inflected forms are found by stripping suffixes ("analysed" ->
"analyse") and through the irregular-verb table below. Closed-class words
(determiners, pronouns, prepositions, auxiliaries...) are listed here.

Tags (a coarse Penn Treebank set):

    DT determiner   PRP subject pronoun   PRPO object pronoun   IN preposition
    CC and/or/but   SC subordinator      BE / HV / DO / MD auxiliaries
    TO "to"         EX "there"           WH who/which/...       THAT "that"
    NEG not/never   RB adverb            JJ adjective           CD number
    NN / NNS / NNP noun                  VB / VBZ / VBD / VBN / VBG verb
    PH [[n]] placeholder                 P punctuation
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "pos_lexicon.json"

# ------------------------------------------------------------------ closed classes

_CLOSED: dict[str, str] = {}
for _tag, _words in {
    "DT": "a an the this these those my your his its our their each every some any no another all both either "
    "neither such many several few most much",
    "PRP": "i you he she it we they",
    "PRPO": "me him her us them",
    "IN": "of in on at for with from by about into onto over under between through during after before until "
    "without within among across against along around behind beyond near per via despite toward towards upon "
    "like than",
    "CC": "and or but nor",
    "SC": "because although though if unless whereas whenever while once since when",
    "BE": "is are was were be been being am",
    "HV": "has have had having",
    "DO": "do does did",
    "MD": "will would can could should must might may shall",
    "TO": "to",
    "EX": "there",
    "WH": "who whom whose which what where why how",
    "THAT": "that",
    "NEG": "not never",
    "RB": "also very too quite rather just only even still already often always sometimes usually so then now "
    "here soon really almost",
    "CD": "one two three four five six seven eight nine ten eleven twelve twenty hundred thousand million billion",
}.items():
    for _w in _words.split():
        _CLOSED[_w] = _tag

SUBJECT_TO_OBJECT = {"i": "me", "he": "him", "she": "her", "we": "us", "they": "them", "you": "you", "it": "it"}
OBJECT_TO_SUBJECT = {v: k for k, v in SUBJECT_TO_OBJECT.items() if k not in ("you", "it")} | {"you": "you", "it": "it"}

# ------------------------------------------------------------------ irregular verbs

_IRREGULAR_TEXT = """
arise arose arisen|be was been|bear bore borne|beat beat beaten|become became become|begin began begun
bend bent bent|bet bet bet|bind bound bound|bite bit bitten|blow blew blown|break broke broken
bring brought brought|build built built|burn burnt burnt|buy bought bought|catch caught caught
choose chose chosen|come came come|cost cost cost|cut cut cut|deal dealt dealt|dig dug dug|do did done
draw drew drawn|drink drank drunk|drive drove driven|eat ate eaten|fall fell fallen|feed fed fed
feel felt felt|fight fought fought|find found found|fly flew flown|forbid forbade forbidden
forget forgot forgotten|forgive forgave forgiven|freeze froze frozen|get got gotten|give gave given
go went gone|grow grew grown|hang hung hung|have had had|hear heard heard|hide hid hidden|hit hit hit
hold held held|hurt hurt hurt|keep kept kept|know knew known|lay laid laid|lead led led|leave left left
lend lent lent|let let let|lie lay lain|lose lost lost|make made made|mean meant meant|meet met met
overcome overcame overcome|pay paid paid|prove proved proven|put put put|quit quit quit|read read read
ride rode ridden|ring rang rung|rise rose risen|run ran run|say said said|see saw seen|seek sought sought
sell sold sold|send sent sent|set set set|shake shook shaken|shoot shot shot|show showed shown
shut shut shut|sing sang sung|sink sank sunk|sit sat sat|sleep slept slept|speak spoke spoken
spend spent spent|split split split|spread spread spread|stand stood stood|steal stole stolen
stick stuck stuck|strike struck struck|swim swam swum|take took taken|teach taught taught
tear tore torn|tell told told|think thought thought|throw threw thrown|understand understood understood
undertake undertook undertaken|wake woke woken|wear wore worn|win won won|withdraw withdrew withdrawn
write wrote written|undergo underwent undergone|rebuild rebuilt rebuilt|rewrite rewrote rewritten
"""
IRREGULAR: dict[str, tuple[str, str]] = {}
for _entry in re.split(r"[|\n]", _IRREGULAR_TEXT.strip()):
    _lemma, _past, _pp = _entry.split()
    IRREGULAR[_lemma] = (_past, _pp)
_PAST_OF = {past: lemma for lemma, (past, _) in IRREGULAR.items()}
_PP_OF = {pp: lemma for lemma, (_, pp) in IRREGULAR.items()}
_THIRD_IRREGULAR = {"be": "is", "have": "has", "do": "does", "go": "goes"}

# Multi-syllable verbs that double their last consonant: "committed", "occurring".
_DOUBLE = frozenset(
    "admit commit permit submit transmit omit emit control occur refer prefer transfer compel expel propel "
    "equip regret forget begin upset acquit patrol".split()
)

# ------------------------------------------------------------------ data


@cache
def _data() -> dict:
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"tags": {}, "nominal": {}}


def base_tags(word: str) -> str:
    """WordNet parts of speech of a lemma ("nv" for "increase"), or ""."""
    return _data()["tags"].get(word.lower(), "")


def verb_of_noun(noun: str) -> str | None:
    """The verb a nominalisation comes from: "implementation" -> "implement"."""
    return _data()["nominal"].get(noun.lower())


# ------------------------------------------------------------------ inflection

_VOWELS = "aeiou"


def _syllables(word: str) -> int:
    return len(re.findall(r"[aeiouy]+", word))


def _doubles(lemma: str) -> bool:
    if lemma in _DOUBLE:
        return True
    return (
        len(lemma) >= 3
        and _syllables(lemma) == 1
        and lemma[-1] not in _VOWELS + "wxy"
        and lemma[-2] in _VOWELS
        and lemma[-3] not in _VOWELS
    )


def third(lemma: str) -> str:
    """Third person singular: "analyse" -> "analyses", "study" -> "studies"."""
    if lemma in _THIRD_IRREGULAR:
        return _THIRD_IRREGULAR[lemma]
    if lemma.endswith(("s", "x", "z", "ch", "sh")):
        return lemma + "es"
    if lemma.endswith("y") and lemma[-2:-1] not in _VOWELS:
        return lemma[:-1] + "ies"
    return lemma + "s"


def _regular_ed(lemma: str) -> str:
    if lemma.endswith("e"):
        return lemma + "d"
    if lemma.endswith("y") and lemma[-2:-1] not in _VOWELS:
        return lemma[:-1] + "ied"
    if _doubles(lemma):
        return lemma + lemma[-1] + "ed"
    return lemma + "ed"


def past(lemma: str) -> str:
    return IRREGULAR[lemma][0] if lemma in IRREGULAR else _regular_ed(lemma)


def participle(lemma: str) -> str:
    return IRREGULAR[lemma][1] if lemma in IRREGULAR else _regular_ed(lemma)


def gerund(lemma: str) -> str:
    if lemma.endswith("ie"):
        return lemma[:-2] + "ying"
    if lemma.endswith("e") and not lemma.endswith(("ee", "ye", "oe")) and lemma != "be":
        return lemma[:-1] + "ing"
    if _doubles(lemma):
        return lemma + lemma[-1] + "ing"
    return lemma + "ing"


def _verb_lemmas(word: str, endings: tuple[str, ...]) -> list[str]:
    """Candidate lemmas of a regular inflected verb form, e.g. "stopped" -> ["stopp", "stop", ...]."""
    out: list[str] = []
    for end in endings:
        if word.endswith(end) and len(word) > len(end) + 1:
            stem = word[: -len(end)]
            out += [stem, stem + "e"]
            if len(stem) >= 2 and stem[-1] == stem[-2]:
                out.append(stem[:-1])
            if end in ("ied", "ies"):
                out.append(stem + "y")
    return out


def lemma(word: str) -> str | None:
    """Base form of a verb form ("wrote" -> "write", "analysed" -> "analyse"), if it is one."""
    w = word.lower()
    if w in _PAST_OF:
        return _PAST_OF[w]
    if w in _PP_OF:
        return _PP_OF[w]
    if "v" in base_tags(w) and not w.endswith(("ed", "ing")):
        return w
    for cand in _verb_lemmas(w, ("ied", "ies", "ed", "es", "ing", "s", "d")):
        if "v" in base_tags(cand) or cand in IRREGULAR:
            return cand
    return None


# ------------------------------------------------------------------ tagging


@cache
def options(word: str) -> tuple[str, ...]:
    """Every tag ``word`` can have, the most likely first."""
    w = word.lower()
    if re.fullmatch(r"\[\[\d+\]\]", w):
        return ("PH",)
    if not re.search(r"\w", w):
        return ("P",)
    if re.fullmatch(r"[\d.,%]+", w):
        return ("CD",)
    if w in _CLOSED:
        tag = _CLOSED[w]
        return ("DT", "PRPO") if w == "her" else (tag,)
    found: list[str] = []
    for t in base_tags(w):
        found.append({"n": "NN", "v": "VB", "a": "JJ", "r": "RB"}[t])
    if w in _PAST_OF:
        found += ["VBD"] + (["VBN"] if IRREGULAR[_PAST_OF[w]][1] == w else [])
    if w in _PP_OF and "VBN" not in found:
        found.append("VBN")
    if w not in _PAST_OF and w not in _PP_OF:
        if w.endswith("ed") and lemma(w):
            found += ["VBD", "VBN"]
        elif w.endswith("ing") and lemma(w):
            found.append("VBG")
        elif w.endswith("s") and not w.endswith("ss"):
            for cand in _verb_lemmas(w, ("ies", "es", "s")):
                tags = base_tags(cand)
                if "n" in tags and "NNS" not in found:
                    found.append("NNS")
                if "v" in tags and "VBZ" not in found:
                    found.append("VBZ")
    if not found:
        if word[:1].isupper():
            found.append("NNP")
        elif w.endswith("ly"):
            found.append("RB")
        elif w.endswith("ed"):
            found += ["VBD", "VBN"]
        elif w.endswith("ing"):
            found.append("VBG")
        elif w.endswith("s") and not w.endswith(("ss", "us", "is")):
            found.append("NNS")
        else:
            found.append("NN")
    return tuple(dict.fromkeys(found))


_NOUNISH = {"NN", "NNS", "NNP"}
_VERBISH = {"VB", "VBZ", "VBD", "VBN", "VBG"}


def tag(words: list[str]) -> list[str]:
    """One tag per word, picked from ``options`` with a few context rules."""
    tags: list[str] = []
    for i, word in enumerate(words):
        opts = options(word)
        prev = tags[i - 1] if i else None
        prev_word = words[i - 1].lower() if i else None
        pick = opts[0]
        if len(opts) > 1:
            if prev in ("DT", "JJ") or prev_word in ("of",):
                pick = next((o for o in opts if o in _NOUNISH or o == "JJ"), pick)
            elif prev in ("MD", "TO", "DO"):
                pick = next((o for o in opts if o == "VB"), pick)
            elif prev in ("BE", "HV"):
                pick = next((o for o in opts if o in ("VBN", "VBG", "JJ")), pick)
            elif prev in ("PRP", "WH", "THAT"):
                pick = next((o for o in opts if o in ("VBZ", "VBD", "VB")), pick)
            elif prev in ("NN", "NNP"):  # "the data shows"; a bare "balance" after a noun is a compound
                pick = next((o for o in opts if o in ("VBZ", "VBD")), pick)
            elif prev == "NNS":  # "people think"
                pick = next((o for o in opts if o in ("VB", "VBD")), pick)
        if word[:1].isupper() and i > 0 and pick not in ("PRP", "PH") and words[i - 1] not in ".!?":
            pick = "NNP"
        tags.append(pick)
    return tags


def is_verb_form(word: str, *wanted: str) -> bool:
    return any(t in wanted for t in options(word))
