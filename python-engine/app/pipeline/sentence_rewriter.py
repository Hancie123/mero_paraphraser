"""Layer 4b: sentence rewriter - change sentence shape while keeping the meaning.

Runs on each Layer 4 draft, before Layer 5 (language_refiner). Layer 4 only
swaps words and fixed phrases; this layer moves clauses and rebuilds
sentences:

    clause_move      "X because Y."            <-> "Because Y, X."
    light_verb       "make a decision"          -> "decide"
    nominal          "by the implementation of" -> "by implementing"
    reduced_relative ", which was trained on"   -> ", trained on"
    expletive        "There are many people who think" -> "Many people think"
    cleft            "It is this factor that drives"   -> "This factor drives"
    voice            "The team analysed the data" <-> "The data was analysed by the team"
    merge            "The app is fast. It is also free." -> "The app is fast and free."
    list_prose       "A, B, and C."             -> "A and B, as well as C."
    reorder          "In 2020, in Nepal, X"     <-> "In Nepal, in 2020, X"

Each one is a pattern over part-of-speech-tagged tokens (core/pos.py) that
returns the new sentence or None when it does not apply. They are written to
refuse anything they are unsure of; Layer 6 then checks numbers, names,
negations and hedges, and a draft that loses one is ranked down.

``level`` (0-100, the "restructure" control) sets how many sentences change:
at most one transformation per sentence below 70, up to two from 70.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ..core import pos
from ..utils.text_utils import sentence_spans

_TOKEN_RE = re.compile(r"\[\[\d+\]\]|[^\W_]+(?:['’][^\W_]+)*|[^\w\s]")
_VERBISH = {"VB", "VBZ", "VBD", "VBN", "VBG", "BE", "HV", "DO", "MD"}
_NOUNS = {"NN", "NNS", "NNP"}
SECOND_FROM = 70  # from this level a sentence may get a second transformation


@dataclass
class Sentence:
    """One sentence split into tokens with their offsets and tags."""

    text: str
    names: frozenset[str]

    def __post_init__(self) -> None:
        self.toks = [(m.group(), m.start(), m.end()) for m in _TOKEN_RE.finditer(self.text)]
        self.words = [t for t, _, _ in self.toks]
        self.low = [w.lower() for w in self.words]
        self.tags = pos.tag(self.words)

    def __len__(self) -> int:
        return len(self.toks)

    def span(self, i: int, j: int) -> str:
        """Original text of tokens i..j-1 (keeps its spacing)."""
        if i >= j:
            return ""
        return self.text[self.toks[i][1] : self.toks[j - 1][2]]

    @property
    def end(self) -> int:
        """Index of the final punctuation token (or len when there is none)."""
        return len(self) - 1 if self.words and self.words[-1] in ".!?" else len(self)

    @property
    def stop(self) -> str:
        return self.words[-1] if self.words and self.words[-1] in ".!?" else ""

    def has_verb(self, i: int, j: int) -> bool:
        return any(t in _VERBISH for t in self.tags[i:j]) or any(
            pos.is_verb_form(w, "VBZ", "VBD") for w in self.words[i:j]
        )

    def comma_free(self, i: int, j: int) -> bool:
        return not any(w in ',;:()"“”' for w in self.words[i:j])

    def is_name(self, i: int) -> bool:
        """A capitalised word that must keep its capital when moved."""
        w = self.words[i]
        if not w[:1].isupper() or w.startswith("[["):
            return False
        low = self.low[i]
        if low in self.names or low == "i" or low.startswith(("i'", "i’")) or (len(w) > 1 and w.isupper()):
            return True
        if i > 0:
            return True  # capitalised mid-sentence
        return pos.options(w)[0] == "NNP"  # unknown capitalised word at the start: treat as a name


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _uncap(sent: Sentence, i: int, text: str) -> str:
    """``text`` (starting with token i) with its first letter lowered unless that word is a name."""
    return text if sent.is_name(i) else text[:1].lower() + text[1:]


def _noun_phrase(sent: Sentence, i: int, limit: int = 6) -> int | None:
    """End index of a simple noun phrase starting at i: "the new team", "Nepal", "them", "costs"."""
    tags = sent.tags
    if i >= sent.end:
        return None
    if tags[i] in ("PRP", "PRPO"):
        return i + 1
    j = i
    if tags[j] == "DT" or tags[j] == "CD":
        j += 1
    while j < sent.end and j - i < limit and tags[j] in ("JJ", "NN", "NNS", "NNP", "CD"):
        j += 1
    if j == i or tags[j - 1] not in _NOUNS:
        return None
    return j


# ---------------------------------------------------------------- 1 clause_move

_FRONT_SC = {"because", "although", "though", "if", "unless", "when", "whenever", "once", "since", "while", "as"}
_BACK_SC = {"because", "although", "though", "if", "unless", "whenever"}
_CONTRAST_SC = {"although", "though", "while"}
_PRONOUNS = {"it", "they", "he", "she", "this", "these", "its", "their", "them"}
_BEFORE_IF_SKIP = {"even", "as", "only", "what", "see", "ask", "asked", "asks", "check", "know", "wonder", "and", "or"}


def clause_move(sent: Sentence) -> str | None:
    words, low, end = sent.words, sent.low, sent.end
    if not sent.stop or end < 6:
        return None
    if low[0] in _FRONT_SC and low[0] != "as":  # "Because Y, X." -> "X because Y."
        try:
            comma = words.index(",", 2)
        except ValueError:
            return None
        if not sent.comma_free(comma + 1, end) or not sent.has_verb(comma + 1, end):
            return None
        if low[1] != "of" and not sent.has_verb(1, comma):
            return None
        x0 = comma + 1
        if low[x0] == "then":
            x0 += 1
        if x0 >= end or sent.tags[x0] == "CC":
            return None
        if low[x0] in _PRONOUNS and any(t in _NOUNS for t in sent.tags[1:comma]):
            return None  # "While AI helps, it must..." -> "It must..., while AI helps": "it" loses its noun
        main = sent.span(x0, end)
        comma_before = "," if low[0] in _CONTRAST_SC else ""  # "X, although Y." keeps its comma
        return f"{_cap(main)}{comma_before} {low[0]} {sent.span(1, comma)}{sent.stop}"
    for k in range(2, end - 2):  # "X because Y." -> "Because Y, X."
        if low[k] not in _BACK_SC or low[k - 1] in _BEFORE_IF_SKIP:
            continue
        if low[k] == "if" and sent.tags[k - 1] in _VERBISH:
            return None  # "decide if" means "whether"
        if low[k] in ("though",) and low[k - 1] == "even":
            return None
        head_end = k - 1 if words[k - 1] == "," else k
        if not sent.comma_free(0, head_end) or not sent.comma_free(k + 1, end):
            return None
        if not sent.has_verb(0, head_end) or (low[k + 1] != "of" and not sent.has_verb(k + 1, end)):
            return None
        head = _uncap(sent, 0, sent.span(0, head_end))
        return f"{_cap(low[k])} {sent.span(k + 1, end)}, {head}{sent.stop}"
    return None


# ---------------------------------------------------------------- 2 light_verb

# (light verb, its noun, verb to use, prepositions dropped after it, needs an object)
_LIGHT: list[tuple[str, str, str, tuple[str, ...], bool]] = [
    ("make", "a decision", "decide", (), False),
    ("make", "an attempt", "try", (), False),
    ("make", "an effort", "try", (), False),
    ("make", "a recommendation", "recommend", (), False),
    ("make", "a suggestion", "suggest", (), False),
    ("make", "an assumption", "assume", (), False),
    ("make", "a choice", "choose", (), False),
    ("make", "a contribution", "contribute", (), False),
    ("make", "a change", "change", ("to",), True),
    ("make", "an improvement", "improve", ("to", "in"), True),
    ("make", "a comparison", "compare", ("of",), True),
    ("make", "use", "use", ("of",), True),
    ("give", "an explanation", "explain", ("of",), False),
    ("give", "a description", "describe", ("of",), True),
    ("give", "consideration", "consider", ("to",), True),
    ("provide", "an explanation", "explain", ("of", "for"), False),
    ("provide", "a description", "describe", ("of",), True),
    ("provide", "support", "support", ("to", "for"), True),
    ("provide", "assistance", "assist", ("to",), True),
    ("take", "action", "act", (), False),
    ("reach", "a conclusion", "conclude", (), False),
    ("reach", "an agreement", "agree", (), False),
    ("come to", "a conclusion", "conclude", (), False),
    ("have", "a discussion", "discuss", ("about", "of", "on"), True),
    ("have", "an impact", "affect", ("on",), True),
    ("have", "an effect", "affect", ("on",), True),
    ("place", "emphasis", "emphasize", ("on",), True),
    ("put", "emphasis", "emphasize", ("on",), True),
] + [
    (verb, noun, target, drops, True)
    for verb in ("carry out", "conduct", "perform")
    for noun, target, drops in (
        ("an analysis", "analyze", ("of",)),
        ("an investigation", "investigate", ("of", "into")),
        ("an evaluation", "evaluate", ("of",)),
        ("an assessment", "assess", ("of",)),
        ("a review", "review", ("of",)),
        ("an examination", "examine", ("of",)),
    )
]


def _forms(lemma: str) -> dict[str, str]:
    """Inflected form -> form name, for a light verb ("make" -> {"made": "past", ...})."""
    return {
        lemma: "base",
        pos.third(lemma): "third",
        pos.past(lemma): "past",
        pos.participle(lemma): "pp" if pos.participle(lemma) != pos.past(lemma) else "past",
        pos.gerund(lemma): "gerund",
    }


def _inflect(lemma: str, form: str, after_aux: bool) -> str:
    if form == "past" and after_aux:
        form = "pp"  # "has made" -> "has decided"
    return {
        "base": lemma,
        "third": pos.third(lemma),
        "past": pos.past(lemma),
        "pp": pos.participle(lemma),
        "gerund": pos.gerund(lemma),
    }[form]


# Targets that read fine with nothing after them: "they decided after ..." works, "they chose
# after ..." does not. Others need one of _TARGET_FOLLOW after them ("chose to", "assumed that").
_STANDALONE = frozenset({"decide", "try", "contribute", "explain", "act", "conclude", "agree"})
_TARGET_FOLLOW = frozenset({"that", "to", "between", "among", "whether", "what", "which", "how"})


def light_verb(sent: Sentence) -> str | None:
    low = sent.low
    for verb, noun, target, drops, needs_object in _LIGHT:
        head, *rest = verb.split()
        forms = _forms(head)
        noun_words = noun.split()
        n = len(rest) + len(noun_words)
        for i in range(len(sent) - n):
            form = forms.get(low[i])
            if form is None or low[i + 1 : i + 1 + n] != rest + noun_words:
                continue
            j = i + 1 + n  # first token after the noun
            nxt = low[j] if j < len(sent) else ""
            dropped = nxt in drops
            if needs_object and not (dropped and j + 1 < sent.end and sent.tags[j + 1] not in ("P",)):
                continue
            if nxt in ("of",) and not dropped:
                continue  # "made a decision of ..." reads oddly as "decided of"
            if not needs_object and target not in _STANDALONE and nxt not in _TARGET_FOLLOW:
                continue  # "make a choice after they ..." -> "choose after they ...": "choose" needs an object
            after_aux = i > 0 and sent.tags[i - 1] in ("HV", "BE")
            if sent.tags[i - 1 if i else 0] == "BE" and form == "past":
                continue  # passive "was made a ..." - leave it
            new = _inflect(target, form, after_aux)
            if sent.words[i][:1].isupper():
                new = _cap(new)
            tail_start = j + 1 if dropped else j
            before = sent.text[: sent.toks[i][1]]
            after = sent.text[sent.toks[tail_start][1] :] if tail_start < len(sent) else ""
            sep = "" if not after or after[:1] in ".,!?;:" else " "
            return f"{before}{new}{sep}{after}"
    return None


# ---------------------------------------------------------------- 3 nominal

_NOMINAL_AFTER = {"by", "through", "for", "after", "before", "without", "in", "on", "of"}


def nominal(sent: Sentence) -> str | None:
    low = sent.low
    for i in range(len(sent) - 3):
        if low[i] != "the" or low[i + 2] != "of":
            continue
        verb = pos.verb_of_noun(low[i + 1])
        if not verb or (i > 0 and low[i - 1] not in _NOMINAL_AFTER):
            continue
        if sent.tags[i + 3] not in ("DT", "NN", "NNS", "NNP", "JJ", "CD"):
            continue
        new = pos.gerund(verb)
        if i == 0:
            new = _cap(new)
        return sent.text[: sent.toks[i][1]] + new + " " + sent.text[sent.toks[i + 3][1] :]
    return None


# ---------------------------------------------------------------- 4 reduced_relative


def _participle(sent: Sentence, k: int) -> bool:
    """Token k is a participle with a complement after it ("trained on", "based in", "causing delays")."""
    word = sent.low[k]
    if k + 1 >= sent.end:
        return False
    opts = pos.options(word)
    if word.endswith("ing"):
        return "VBG" in opts and "JJ" not in opts and sent.tags[k + 1] in ("DT", "NN", "NNS", "NNP", "JJ", "CD")
    if "VBN" not in opts:
        return False
    return sent.low[k + 1] == "by" or (pos.lemma(word) is not None and sent.tags[k + 1] in ("IN", "TO"))


def reduced_relative(sent: Sentence) -> str | None:
    low, tags = sent.low, sent.tags
    for i in range(1, len(sent) - 3):
        if low[i] not in ("which", "who", "that") or low[i + 1] not in ("is", "are", "was", "were"):
            continue
        prev_ok = sent.words[i - 1] == "," or tags[i - 1] in _NOUNS
        if low[i] == "that" and tags[i - 1] not in _NOUNS:
            continue  # "said that was ..." is not a relative clause
        if not prev_ok or not _participle(sent, i + 2):
            continue
        return sent.text[: sent.toks[i][1]] + sent.text[sent.toks[i + 2][1] :]
    return None


# ---------------------------------------------------------------- 5 expletive and cleft


def expletive(sent: Sentence) -> str | None:
    low, tags = sent.low, sent.tags
    if len(sent) < 6 or low[0] != "there" or low[1] not in ("is", "are", "was", "were"):
        return None
    for k in range(3, min(8, sent.end - 1)):
        if not sent.comma_free(2, k) or tags[2] not in ("DT", "CD", "JJ", "NN", "NNS"):
            return None
        if low[k] in ("who", "that") and tags[k - 1] in _NOUNS:
            nxt = low[k + 1]
            if tags[k + 1] in ("DT", "PRP", "PRPO", "IN", "NNP") or nxt in ("the", "a", "an"):
                return None  # "who the team hired": object relative, keep it
            if not (tags[k + 1] in _VERBISH or pos.is_verb_form(nxt, "VBZ", "VBD", "VB")):
                return None
            return _cap(sent.span(2, k)) + " " + sent.text[sent.toks[k + 1][1] :]
        if tags[k] == "VBG" and "JJ" not in pos.options(low[k]) and tags[k - 1] in _NOUNS:
            return f"{_cap(sent.span(2, k))} {low[1]} " + sent.text[sent.toks[k][1] :]
    return None


def cleft(sent: Sentence) -> str | None:
    low, tags = sent.low, sent.tags
    if len(sent) < 6 or low[0] != "it" or low[1] not in ("is", "was"):
        return None
    if tags[2] not in ("DT", "NNP") or low[2] in ("no", "a", "an"):
        return None  # "It is a fact that ...", "It is no wonder that ..."
    for k in range(3, min(9, sent.end - 1)):
        if not sent.comma_free(2, k):
            return None
        if low[k] in ("that", "who") and tags[k - 1] in _NOUNS:
            nxt = low[k + 1]
            if tags[k + 1] in ("DT", "PRP", "NNP", "IN") or not (
                tags[k + 1] in ("VBZ", "VBD", "MD", "BE", "HV") or pos.is_verb_form(nxt, "VBZ", "VBD")
            ):
                return None
            return _cap(sent.span(2, k)) + " " + sent.text[sent.toks[k + 1][1] :]
    return None


# ---------------------------------------------------------------- 6 voice

_NO_PASSIVE = frozenset(
    "have get be become seem let go come lack resemble cost weigh fit suit mean want need like love hate know "
    "feel say tell ask think hope wish include contain last remain stay sound look taste smell equal total "
    "reach number span".split()
)
# A phrase after the object with one of these belongs to the object, so it moves with it:
# "approved the budget for the new school" -> "The budget for the new school was approved ...".
_OBJECT_PREPS = {"of", "for", "on", "about"}
# These usually attach to the verb ("tested the app across five countries") and may stay at the end.
_VERB_PREPS = {"during", "after", "before", "since", "until", "across", "throughout", "despite", "via", "through",
               "from"}  # fmt: skip
# Anything else ("with users", "in Texas", "to the board") could belong to either, so voice refuses.
_BARE_TIME_LEAD = {"last", "this", "next", "every", "each", "that"}
_BARE_TIME = {"yesterday", "today", "tomorrow", "recently", "annually", "weekly", "daily", "monthly"}


_PLURAL_WORDS = frozenset("people children men women police mice feet teeth geese criteria".split())


def _number(sent: Sentence, i: int, j: int) -> str:
    """'pl' or 'sg' for the noun phrase i..j-1."""
    head = sent.low[j - 1]
    if sent.tags[i] in ("PRP", "PRPO"):
        return "pl" if head in ("we", "they", "you", "us", "them", "i", "me") else "sg"
    if "and" in sent.low[i:j]:
        return "pl"
    if head in _PLURAL_WORDS:
        return "pl"
    return "pl" if sent.tags[j - 1] == "NNS" or (head.endswith("s") and not head.endswith("ss")) else "sg"


def _as_object(sent: Sentence, i: int, j: int) -> str:
    if sent.tags[i] == "PRP":
        return pos.SUBJECT_TO_OBJECT[sent.low[i]]
    return _uncap(sent, i, sent.span(i, j))


def _as_subject(sent: Sentence, i: int, j: int) -> str:
    if sent.tags[i] == "PRPO" or sent.low[i] in ("you", "it"):
        return _cap(pos.OBJECT_TO_SUBJECT.get(sent.low[i], sent.low[i]))
    return _cap(sent.span(i, j))


def _time_tail(sent: Sentence, k: int) -> bool:
    """Tokens k..end are a time phrase: "in 2021", "over the past decade", "last year", "yesterday"."""
    end = sent.end
    if k >= end or not sent.comma_free(k, end):
        return False
    words = sent.low[k:end]
    if len(words) == 1 and words[0] in _BARE_TIME:
        return True
    if words[0] in _BARE_TIME_LEAD and 2 <= len(words) <= 3 and words[-1] in _TIME_NOUNS:
        return True
    return _time_phrase(sent, k, end) or (
        sent.low[k] == "for" and len(words) <= 4 and any(w in _TIME_NOUNS for w in words)  # "for weeks"
    )


def _tail(sent: Sentence, k: int) -> str | None:
    """Text from token k to the end punctuation if it can stay after the moved phrases, else None.

    Allowed: nothing, a time phrase, or a comma-free phrase with a verb-attached preposition.
    """
    if k == sent.end:
        return ""
    if _time_tail(sent, k):
        return " " + sent.span(k, sent.end)
    if sent.low[k] not in _VERB_PREPS or not sent.comma_free(k, sent.end) or sent.has_verb(k, sent.end):
        return None
    return " " + sent.span(k, sent.end)


def _np(sent: Sentence, i: int) -> int | None:
    """``_noun_phrase`` that stops before a time phrase: "five engineers | last year"."""
    j = _noun_phrase(sent, i, 5)
    if j is None:
        return None
    for m in range(i + 1, j):
        if sent.low[m] in _BARE_TIME_LEAD and sent.tags[m - 1] in _NOUNS and _time_tail(sent, m):
            return m
    return j


def _subject_end(sent: Sentence) -> int | None:
    """End of the opening noun phrase; "Climate change affects" keeps "change" as part of it."""
    j = _np(sent, 0)
    if j is None or j + 1 >= sent.end:
        return j
    if sent.tags[j] == "VB" and "NN" in pos.options(sent.low[j]) and pos.is_verb_form(sent.low[j + 1], "VBZ", "VBD"):
        return j + 1
    return j


def _object_end(sent: Sentence, o0: int) -> int | None:
    """End of the object starting at o0, taking along an "of/for/on/about" phrase that belongs to it."""
    o_end = _np(sent, o0)
    if o_end is None:
        return None
    if o_end < sent.end and sent.low[o_end] in _OBJECT_PREPS and not _time_tail(sent, o_end):
        if sent.tags[o_end + 1] in ("PRP", "PRPO"):
            return None
        o_end = _np(sent, o_end + 1)
    return o_end


_OBJECT_START = {"DT", "PRPO", "NNP", "CD", "NNS", "NN", "JJ"}
_AGENT_START = {"DT", "NNP", "PRPO", "NNS", "NN", "CD", "JJ"}


def voice(sent: Sentence) -> str | None:
    """Active <-> passive, only when every phrase still attaches to the same word afterwards."""
    if not sent.stop or not sent.comma_free(0, sent.end) or "PH" in sent.tags:
        return None
    subj_end = _subject_end(sent)
    if subj_end is None or subj_end + 2 >= sent.end:
        return None
    low = sent.low
    v = subj_end
    if low[v] in ("was", "were", "is", "are") and low[v + 2 : v + 3] == ["by"]:  # passive -> active
        lemma = pos.lemma(low[v + 1])
        if not lemma or lemma in _NO_PASSIVE or "VBN" not in pos.options(low[v + 1]):
            return None
        a0 = v + 3
        if a0 >= sent.end or sent.tags[a0] not in _AGENT_START or low[a0] in ("means",):
            return None
        a_end = _np(sent, a0)
        if a_end is None:
            return None
        tail = _tail(sent, a_end)  # "by the committee for the school": whose school? refuse
        if tail is None:
            return None
        if low[v] in ("was", "were"):
            verb = pos.past(lemma)
        else:
            verb = lemma if _number(sent, a0, a_end) == "pl" else pos.third(lemma)
        return f"{_as_subject(sent, a0, a_end)} {verb} {_as_object(sent, 0, subj_end)}{tail}{sent.stop}"
    # active -> passive. A pronoun subject becomes an object ("we" -> "by us"); "it", "this"
    # and "you" are left alone, since "by it" / "by you" rarely reads well.
    if sent.tags[0] == "PRPO" or (sent.tags[0] == "PRP" and low[0] not in pos.SUBJECT_TO_OBJECT):
        return None
    if low[0] in ("it", "you", "this", "that", "these", "those"):
        return None
    word = low[v]
    opts = pos.options(word)
    if "VBD" in opts:
        tense = "past"
    elif "VBZ" in opts or ("VB" in opts and _number(sent, 0, subj_end) == "pl"):
        tense = "present"  # "analyses", or "check" after a plural subject
    else:
        return None
    lemma = pos.lemma(word)
    if not lemma or lemma in _NO_PASSIVE:
        return None
    o0 = v + 1
    if sent.tags[o0] not in _OBJECT_START or low[o0] in ("her",) or low[o0] in _TIME_NOUNS | _BARE_TIME_LEAD:
        return None  # "worked last year", "grew this month": not an object
    head_end = _np(sent, o0)
    o_end = _object_end(sent, o0)
    if head_end is None or o_end is None:
        return None
    tail = _tail(sent, o_end)
    if tail is None:
        return None
    plural = _number(sent, o0, head_end) == "pl"  # "millions of people": "millions" decides
    if sent.tags[o0] == "PRPO" and low[o0] == "you":
        plural = True
    be = ("were" if plural else "was") if tense == "past" else ("are" if plural else "is")
    if sent.tags[o0] == "PRPO" and low[o0] in ("me",):
        be = "was" if tense == "past" else "am"
    obj = _as_subject(sent, o0, o_end)
    return f"{obj} {be} {pos.participle(lemma)} by {_as_object(sent, 0, subj_end)}{tail}{sent.stop}"


# ---------------------------------------------------------------- 7 merge (two sentences)

_PRONOUN_NUMBER = {"it": "sg", "he": "sg", "she": "sg", "they": "pl"}


def _antecedent(a: Sentence, pron: str) -> int | None:
    """End of a's subject if the pronoun ``pron`` opening the next sentence can only mean it."""
    subj_end = _noun_phrase(a, 0, 5)
    if subj_end is None or subj_end >= a.end:
        return None
    if _number(a, 0, subj_end) != _PRONOUN_NUMBER[pron]:
        return None
    if pron in ("he", "she") and a.tags[0] not in ("NNP", "PRP"):
        return None
    # The pronoun must have only one possible antecedent: no other noun of that number in sentence a.
    if any(a.tags[k] in _NOUNS and _number(a, k, k + 1) == _PRONOUN_NUMBER[pron] for k in range(subj_end, a.end)):
        return None
    return subj_end


def _joinable(a: Sentence, b: Sentence) -> str | None:
    """b's opening pronoun when a and b are short, plain sentences that may be joined."""
    if a.stop != "." or b.stop != "." or "PH" in a.tags or "PH" in b.tags or len(b) < 3:
        return None
    if not a.comma_free(0, a.end) or not b.comma_free(0, b.end) or a.end > 16 or b.end > 14:
        return None
    return b.low[0] if b.low[0] in _PRONOUN_NUMBER else None


def merge(a: Sentence, b: Sentence) -> str | None:
    """Join two short sentences about one subject: "The app is fast. It is also free." -> "... fast and free."."""
    pron = _joinable(a, b)
    if pron is None or b.end > 12:
        return None
    subj_end = _antecedent(a, pron)
    if subj_end is None:
        return None
    also = b.low[1] == "also"  # "It also works offline."
    rest = 2 if also else 1  # index of b's verb
    verb_a, verb_b = a.low[subj_end], b.low[rest]
    if verb_a in ("is", "are", "was", "were") and verb_b == verb_a:  # copula + adjective
        adj_a = a.tags[subj_end + 1 : a.end]
        adj_b = b.tags[rest + 1 : b.end]
        if b.low[rest + 1 : rest + 2] == ["also"]:
            adj_b = b.tags[rest + 2 : b.end]
            rest += 1
        ok = {"JJ", "RB"}
        if not adj_a or not adj_b or not set(adj_a) <= ok or not set(adj_b) <= ok or "and" in a.low:
            return None
        if adj_a[-1] != "JJ" or adj_b[-1] != "JJ":
            return None
        return f"{a.span(0, a.end)} and {b.span(rest + 1, b.end)}."
    tense = "VBZ" if pos.is_verb_form(verb_a, "VBZ") else "VBD" if pos.is_verb_form(verb_a, "VBD") else None
    if tense is None or not pos.is_verb_form(verb_b, tense) or verb_b in ("is", "are", "was", "were"):
        return None
    if a.has_verb(subj_end + 1, a.end) or b.has_verb(rest + 1, b.end):
        return None  # keep it to one verb per sentence
    return f"{a.span(0, a.end)} and {'also ' if also else ''}{b.span(rest, b.end)}."


# ---------------------------------------------------------------- 7b relative_join (two sentences)

_PERSON_NOUNS = frozenset(
    "people person researchers researcher students student teachers teacher workers worker employees employee "
    "users user patients patient children child parents parent doctors doctor nurses nurse scientists scientist "
    "participants participant customers customer staff engineers engineer members member authors author experts "
    "expert farmers farmer residents resident citizens citizen voters voter managers manager leaders leader "
    "men women man woman".split()
)


def relative_join(a: Sentence, b: Sentence) -> str | None:
    """Fold the second sentence into the first as a relative clause.

    "The model uses X. It was trained on Y." -> "The model, which was trained on Y, uses X."
    """
    pron = _joinable(a, b)
    if pron is None or a.tags[0] in ("PRP", "PRPO"):
        return None
    subj_end = _antecedent(a, pron)
    if subj_end is None or a.end - subj_end < 2:
        return None
    if not (a.tags[subj_end] in _VERBISH or pos.is_verb_form(a.low[subj_end], "VBZ", "VBD")):
        return None
    first = 2 if b.low[1] == "also" else 1
    if b.end - first < 2 or not (b.tags[first] in _VERBISH or pos.is_verb_form(b.low[first], "VBZ", "VBD")):
        return None
    head = a.low[subj_end - 1]
    person = a.tags[subj_end - 1] == "NNP" or head in _PERSON_NOUNS or head.endswith(("ers", "ists", "ians"))
    if pron == "it":
        if person:
            return None
        rel = "which"
    elif pron == "they":
        rel = "who" if person else "which"
    else:
        rel = "who"
    return f"{a.span(0, subj_end)}, {rel} {b.span(1, b.end)}, {a.span(subj_end, a.end)}."


# ---------------------------------------------------------------- 8 list_prose


_ITEM = {"JJ", "NN", "NNS", "NNP", "DT", "CD", "VBN", "VBG"}
_LIST_LEAD = {"including", "especially", "notably", "like", "namely"}


def _item(sent: Sentence, i: int) -> bool:
    """Token i can sit inside a short list item ("improved work-life balance")."""
    if sent.low[i] in ("such", "as", "etc"):
        return False  # "challenges, such as A and B" is an example list, not three items
    return sent.tags[i] in _ITEM or sent.words[i] in ("-", "'", "’")


def list_prose(sent: Sentence) -> str | None:
    """Break a list of three: "We need A, B, and C." -> "We need A and B, as well as C."."""
    low = sent.low
    if not sent.stop:
        return None
    end = sent.end
    if sent.tags[end - 1] == "PH":  # "..., and heatwaves [[1]]."
        end -= 1
    try:
        k = max(i for i in range(end) if low[i] == "and")
    except ValueError:
        return None
    if not 1 <= end - k - 1 <= 5 or not all(_item(sent, i) for i in range(k + 1, end)):
        return None
    b_end = k - 1 if sent.words[k - 1] == "," else k
    c1 = next((i for i in range(b_end - 1, -1, -1) if sent.words[i] == ","), None)
    if c1 is None or not 1 <= b_end - c1 - 1 <= 5 or not all(_item(sent, i) for i in range(c1 + 1, b_end)):
        return None
    a_start = c1
    while a_start > 0 and c1 - a_start < 5 and _item(sent, a_start - 1):
        a_start -= 1
    if a_start == c1 or a_start == 0:
        return None
    if low[a_start] in _LIST_LEAD:
        a_start += 1  # "events, including droughts, floods, and heatwaves"
    elif sent.words[a_start - 1] == ",":
        return None  # a list of four or more: leave it
    if a_start >= c1 or sent.tags[a_start] in ("VBG", "VBN", "RB") and sent.tags[a_start - 1] in _NOUNS:
        return None  # "people working, ..." is a clause, not a list item
    head = sent.text[: sent.toks[a_start][1]]
    tail = sent.text[sent.toks[end - 1][2] :]
    return f"{head}{sent.span(a_start, c1)} and {sent.span(c1 + 1, b_end)}, as well as {sent.span(k + 1, end)}{tail}"


# ---------------------------------------------------------------- 9 adverbial_front

_TIME_NOUNS = frozenset(
    "year years decade decades century centuries month months week weeks day days today yesterday tomorrow "
    "period periods era time times summer winter spring autumn morning evening night quarter future past "
    "january february march april may june july august september october november december "
    "monday tuesday wednesday thursday friday saturday sunday".split()
)
_TIME_PREPS = {"in", "over", "during", "throughout", "since", "within", "by", "after", "before", "until", "at"}
_YEAR_RE = re.compile(r"(?:1[5-9]|20)\d\ds?")  # "2021", "1990s"
_OF_OK = {"end", "start", "beginning", "middle"}  # "by the end of March", not "in the future of work"
_NOT_PARTICIPLE = {"including", "according", "regarding", "following", "concerning", "depending", "excluding",
                   "considering", "given", "assuming", "compared", "starting", "beginning"}  # fmt: skip


def _time_phrase(sent: Sentence, i: int, j: int) -> bool:
    """Tokens i..j-1 are a time phrase: "over the past two decades", "in 2021", "by the end of March"."""
    if sent.low[i] not in _TIME_PREPS or not 2 <= j - i <= 8 or not sent.comma_free(i, j) or sent.has_verb(i + 1, j):
        return False
    words = sent.low[i + 1 : j]
    for k, w in enumerate(words):
        if w == "of" and (k == 0 or words[k - 1] not in _OF_OK):
            return False
    return any(w in _TIME_NOUNS or _YEAR_RE.fullmatch(w) for w in words)


def _clause_ok(sent: Sentence, i: int, j: int) -> bool:
    """A plain main clause: has a verb, no commas, no relative clause the phrase could belong to."""
    return (
        j - i >= 4
        and sent.comma_free(i, j)
        and sent.has_verb(i, j)
        and not any(t in ("WH", "THAT") for t in sent.tags[i:j])
    )


def adverbial_front(sent: Sentence) -> str | None:
    """Move a time phrase: "Costs rose over the past decade." <-> "Over the past decade, costs rose."

    Also "X by hiring Y." -> "By hiring Y, X." and "X, offering Y." -> "Offering Y, X."
    """
    low, end = sent.low, sent.end
    if not sent.stop or "PH" in sent.tags[: end - 1]:
        return None
    if low[0] in _TIME_PREPS:  # fronted time phrase -> back
        try:
            comma = sent.words.index(",")
        except ValueError:
            return None
        if _time_phrase(sent, 0, comma) and _clause_ok(sent, comma + 1, end):
            main = sent.span(comma + 1, end)
            phrase = _uncap(sent, 0, sent.span(0, comma))
            return f"{_cap(main)} {phrase}{sent.stop}"
        return None
    for k in range(4, end - 1):
        if sent.words[k - 1] == "," and "VBG" in pos.options(low[k]) and "JJ" not in pos.options(low[k]):
            if low[k] in _NOT_PARTICIPLE or not _clause_ok(sent, 0, k - 1) or not sent.comma_free(k, end):
                continue
            if sent.tags[0] in ("PRP", "PRPO"):
                continue
            return f"{_cap(sent.span(k, end))}, {_uncap(sent, 0, sent.span(0, k - 1))}{sent.stop}"
        by_gerund = low[k] == "by" and "VBG" in pos.options(low[k + 1]) and sent.comma_free(k, end)
        if (by_gerund or _time_phrase(sent, k, end)) and _clause_ok(sent, 0, k):
            return f"{_cap(sent.span(k, end))}, {_uncap(sent, 0, sent.span(0, k))}{sent.stop}"
    return None


# ---------------------------------------------------------------- 10 reorder fronted phrases


def reorder(sent: Sentence) -> str | None:
    """Swap two opening phrases: "In 2020, in Nepal, X" <-> "In Nepal, in 2020, X"."""
    tags, words = sent.tags, sent.words
    if tags[0] != "IN":
        return None
    try:
        c1 = words.index(",")
        c2 = words.index(",", c1 + 1)
    except ValueError:
        return None
    if not (2 <= c1 <= 5 and tags[c1 + 1] == "IN" and 2 <= c2 - c1 - 1 <= 5):
        return None
    if sent.has_verb(0, c2) or c2 + 1 >= sent.end:
        return None
    first = _uncap(sent, 0, sent.span(0, c1))
    return f"{_cap(sent.span(c1 + 1, c2))}, {first}, {sent.text[sent.toks[c2 + 1][1] :]}"


# ---------------------------------------------------------------- driver

Transform = Callable[[Sentence], "str | None"]
TRANSFORMS: dict[str, Transform] = {
    "clause_move": clause_move,
    "light_verb": light_verb,
    "nominal": nominal,
    "reduced_relative": reduced_relative,
    "expletive": expletive,
    "cleft": cleft,
    "voice": voice,
    "list_prose": list_prose,
    "adverbial_front": adverbial_front,
    "reorder": reorder,
}


@dataclass
class Reshaped:
    text: str
    count: int  # transformations applied
    used: list[str]  # their names, in order


def _locked_hit(text: str, locked: Iterable[str]) -> bool:
    low = text.lower()
    return any(t and t.lower() in low for t in locked)


_LEAD_TAGS = {"RB", "IN", "DT", "JJ", "NN", "CC"}


def _split_lead(sent: Sentence) -> tuple[str, str] | None:
    """("However", "remote work also ...") for a sentence opening with a short adverbial and a comma."""
    try:
        comma = sent.words.index(",")
    except ValueError:
        return None
    if not 1 <= comma <= 3 or comma + 5 > len(sent) or not all(t in _LEAD_TAGS for t in sent.tags[:comma]):
        return None
    if sent.low[0] in _TIME_PREPS | _FRONT_SC:
        return None  # "In 2020, ..." and "If so, ..." are handled by the transformations themselves
    return sent.span(0, comma), sent.text[sent.toks[comma + 1][1] :]


def _try(sentence: str, names: frozenset[str], skip: set[str], rng: random.Random) -> tuple[str, str] | None:
    sent = Sentence(sentence, names)
    if len(sent) < 4:
        return None
    hits = [(name, out) for name, fn in TRANSFORMS.items() if name not in skip and (out := fn(sent))]
    lead = _split_lead(sent)
    if lead:  # "However, X." -> transform X, then put "However," back
        body = Sentence(_cap(lead[1]), names)
        for name, fn in TRANSFORMS.items():
            if name in skip or name == "reorder" or any(n == name for n, _ in hits):
                continue
            out = fn(body)
            if out:
                shaped = Sentence(out, names)
                hits.append((name, f"{lead[0]}, {_uncap(shaped, 0, out)}"))
    hits = [(n, o) for n, o in hits if o and o != sentence]
    return rng.choice(hits) if hits else None


def reshape(
    text: str,
    level: int,
    rng: random.Random,
    names: Iterable[str] = (),
    locked: Iterable[str] = (),
) -> Reshaped:
    """Restructure some sentences of ``text``; ``level`` 0 leaves it unchanged."""
    if level <= 0 or not text.strip():
        return Reshaped(text, 0, [])
    names = frozenset(n.lower() for n in names for n in n.split())
    locked = tuple(locked)
    p = min(level / 100, 1.0)
    second = max(0.0, (level - SECOND_FROM + 10) / 60) if level >= SECOND_FROM else 0.0
    spans = sentence_spans(text)
    out: list[str] = []
    used: list[str] = []
    pos_ = 0
    k = 0
    while k < len(spans):
        a, b = spans[k]
        out.append(text[pos_:a])
        sentence = text[a:b]
        pos_ = b
        if _locked_hit(sentence, locked):
            out.append(sentence)
            k += 1
            continue
        # merge with the next sentence when they sit on the same line
        if k + 1 < len(spans) and rng.random() < p * 0.5:
            na, nb = spans[k + 1]
            gap = text[b:na]
            if gap == " " and not _locked_hit(text[na:nb], locked):
                merged = merge(Sentence(sentence, names), Sentence(text[na:nb], names))
                if merged:
                    out.append(merged)
                    used.append("merge")
                    pos_ = nb
                    k += 2
                    continue
        if rng.random() < p:
            hit = _try(sentence, names, set(), rng)
            if hit:
                used.append(hit[0])
                sentence = hit[1]
                if second and rng.random() < second:
                    again = _try(sentence, names, {hit[0]}, rng)
                    if again:
                        used.append(again[0])
                        sentence = again[1]
        out.append(sentence)
        k += 1
    out.append(text[pos_:])
    return Reshaped("".join(out), len(used), used)
