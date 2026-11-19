"""Built-in offline lexicon for the Mero Paraphraser engine.

Synonym groups are ``(part_of_speech, words, keys)``:

* ``words`` are interchangeable terms, most common first.
* ``keys`` are the words that may be *replaced* (``None`` means all of them).
  Ambiguous words (``show`` is also a noun, ``used to`` is an idiom, ...) are
  listed only as replacement targets so they are never rewritten themselves.

Part of speech drives simple inflection: noun and verb groups also match
their ``-s`` forms (``problems`` -> ``issues``, ``helps`` -> ``assists``).
"""

from __future__ import annotations

import json
from pathlib import Path

A, R, V, N = "a", "r", "v", "n"  # adjective, adverb, verb, noun

GROUPS: list[tuple[str, list[str], list[str] | None]] = [
    # --- adjectives -------------------------------------------------------
    (A, ["big", "large", "sizable"], None),
    (A, ["huge", "enormous", "massive", "immense"], None),
    (A, ["tiny", "minuscule"], None),
    (A, ["excellent", "outstanding", "superb"], None),
    (A, ["important", "significant", "essential", "crucial"], ["important", "crucial", "essential"]),
    (A, ["difficult", "challenging", "demanding"], None),
    (A, ["easy", "simple", "straightforward", "effortless"], None),
    # "fast"/"quick" never change: "a rapid app", "a fast question" read oddly.
    (A, ["quick", "fast", "rapid", "swift"], ["rapid", "swift"]),
    (A, ["happy", "glad", "pleased", "delighted"], None),
    (A, ["sad", "unhappy", "sorrowful", "downcast"], None),
    (A, ["beautiful", "lovely", "gorgeous", "stunning"], None),
    (A, ["smart", "intelligent", "clever"], None),
    (A, ["modern", "contemporary", "current"], ["modern", "contemporary"]),
    (A, ["strange", "odd", "unusual", "peculiar"], None),
    (A, ["common", "frequent", "widespread", "prevalent"], None),
    (A, ["necessary", "required", "needed", "requisite"], ["necessary", "requisite"]),
    (A, ["obvious", "evident", "apparent", "noticeable"], None),
    (A, ["entire", "whole"], None),
    (A, ["several", "various", "numerous", "multiple"], None),
    (A, ["main", "primary", "principal", "chief"], None),
    (A, ["popular", "well-liked", "favored"], None),
    (A, ["dangerous", "hazardous", "risky", "perilous"], None),
    (A, ["angry", "irritated", "annoyed"], None),
    (A, ["afraid", "scared", "frightened", "fearful"], None),
    # "tired" stays: "exhausted" is stronger, "weary" old-fashioned.
    (A, ["tired", "exhausted", "weary", "fatigued"], ["weary", "fatigued"]),
    (A, ["rich", "wealthy", "affluent", "prosperous"], None),
    (A, ["honest", "truthful", "sincere", "candid"], None),
    (A, ["strong", "powerful", "robust"], None),
    (A, ["weak", "feeble", "fragile"], None),
    (A, ["useful", "helpful", "beneficial", "valuable"], None),
    (A, ["interesting", "intriguing", "fascinating", "engaging"], None),
    (A, ["boring", "dull", "tedious", "monotonous"], None),
    (A, ["accurate", "precise", "exact"], ["precise", "exact"]),
    (A, ["sufficient", "adequate", "ample"], None),
    (A, ["typical", "usual", "normal", "customary"], None),
    # "quiet" stays: "the shops were quiet" means not busy, not silent or calm.
    (A, ["quiet", "silent", "calm", "peaceful"], ["silent"]),
    (A, ["famous", "renowned", "well-known", "celebrated"], None),
    (A, ["possible", "feasible", "achievable", "viable"], None),
    (A, ["rare", "uncommon", "scarce", "infrequent"], None),
    (A, ["brave", "courageous", "bold", "fearless"], None),
    (A, ["careful", "cautious", "attentive", "mindful"], None),
    (A, ["successful", "effective", "productive", "fruitful"], ["fruitful"]),
    (A, ["serious", "severe", "grave"], ["grave"]),
    (A, ["ready", "prepared"], None),
    # --- adverbs ----------------------------------------------------------
    (R, ["quickly", "rapidly", "swiftly", "promptly"], None),
    (R, ["slowly", "gradually", "steadily"], None),
    (R, ["often", "frequently", "commonly", "regularly"], ["often", "frequently", "commonly"]),
    (R, ["usually", "typically", "generally", "normally", "ordinarily"], None),
    (R, ["furthermore", "moreover", "additionally", "in addition"], None),
    (R, ["however", "nevertheless", "nonetheless", "even so"], None),
    (R, ["therefore", "thus", "consequently", "hence", "as a result"], None),
    (R, ["completely", "entirely", "totally", "fully", "wholly"], None),
    (R, ["extremely", "exceedingly", "incredibly", "remarkably"], None),
    (R, ["almost", "nearly", "virtually", "practically"], None),
    (R, ["suddenly", "abruptly", "unexpectedly", "all of a sudden"], None),
    (R, ["finally", "eventually", "ultimately", "at last"], None),
    (R, ["clearly", "evidently", "obviously", "plainly"], None),
    (R, ["mainly", "mostly", "primarily", "chiefly", "largely"], None),
    (R, ["especially", "particularly", "notably", "specifically"], None),
    (R, ["immediately", "instantly", "right away", "at once"], None),
    (R, ["recently", "lately"], None),
    (R, ["perhaps", "maybe", "possibly", "conceivably"], None),
    (R, ["certainly", "definitely", "undoubtedly", "surely"], None),
    (R, ["easily", "effortlessly", "readily", "with ease"], None),
    (R, ["carefully", "cautiously", "with care"], None),
    (R, ["approximately", "roughly", "about", "around"], ["approximately", "roughly"]),
    (R, ["rarely", "seldom", "infrequently", "hardly ever"], None),
    (R, ["happily", "gladly", "cheerfully", "joyfully"], None),
    (R, ["significantly", "considerably", "substantially", "markedly"], None),
    (R, ["currently", "presently", "at present", "now"], ["currently", "presently"]),
    # --- verbs ------------------------------------------------------------
    (V, ["help", "assist", "aid", "support"], ["assist"]),
    (V, ["helped", "assisted", "aided", "supported"], None),
    (V, ["helping", "assisting", "aiding", "supporting"], None),
    (V, ["show", "demonstrate", "reveal", "illustrate"], ["demonstrate", "reveal", "illustrate"]),
    (V, ["showed", "demonstrated", "revealed", "illustrated"], None),
    (V, ["use", "utilize", "employ"], ["utilize", "employ"]),
    (V, ["utilized", "used"], ["utilized"]),
    (V, ["using", "utilizing", "employing"], None),
    (V, ["begin", "start", "commence", "initiate"], ["begin", "commence", "initiate"]),
    (V, ["began", "started", "commenced", "initiated"], None),
    (V, ["end", "finish", "conclude", "complete"], ["finish", "conclude"]),
    (V, ["finished", "completed", "concluded", "ended"], None),
    (V, ["create", "produce", "generate", "build"], ["create", "produce", "generate"]),
    (V, ["created", "produced", "generated", "built"], None),
    (V, ["get", "obtain", "acquire", "gain"], ["obtain", "acquire"]),
    (V, ["buy", "purchase"], None),
    (V, ["bought", "purchased"], None),
    (V, ["need", "require"], ["require"]),
    (V, ["want", "desire"], ["want"]),
    (V, ["try", "attempt"], ["try"]),
    (V, ["tried", "attempted"], None),
    (V, ["understand", "comprehend", "grasp"], ["understand", "comprehend"]),
    (V, ["explain", "clarify", "describe"], None),
    (V, ["improve", "enhance", "boost", "refine"], None),
    (V, ["improved", "enhanced", "boosted", "refined"], None),
    (V, ["increased", "raised", "expanded"], ["expanded"]),
    (V, ["reduce", "decrease", "lower", "cut", "diminish"], ["reduce"]),
    (V, ["reduced", "decreased", "lowered", "diminished"], None),
    (V, ["choose", "select", "pick", "opt for"], ["choose", "select"]),
    (V, ["chose", "selected", "picked", "opted for"], None),
    (V, ["discover", "uncover", "find"], ["discover", "uncover"]),
    (V, ["discovered", "found", "uncovered"], ["discovered", "uncovered"]),
    (V, ["seem", "appear"], None),
    (V, ["allow", "permit", "enable"], ["allow"]),
    (V, ["allowed", "permitted"], None),
    (V, ["maintain", "retain", "preserve", "keep"], ["maintain", "retain", "preserve"]),
    (V, ["inform", "notify", "tell"], ["inform", "notify"]),
    (V, ["stated", "mentioned", "said", "noted"], ["stated", "mentioned"]),
    (V, ["suggest", "propose", "recommend"], None),
    (V, ["suggested", "proposed", "recommended"], None),
    (V, ["prevent", "hinder", "stop"], ["prevent", "hinder"]),
    (V, ["destroy", "ruin", "demolish", "wreck"], None),
    (V, ["repair", "mend", "fix"], ["repair", "mend"]),
    (V, ["examine", "analyze", "investigate", "inspect", "study"], ["examine", "inspect", "analyze", "investigate"]),
    (V, ["construct", "assemble", "build"], ["construct", "assemble"]),
    (V, ["solve", "resolve", "fix", "settle"], ["solve", "resolve"]),
    (V, ["gather", "collect", "accumulate"], None),
    (V, ["achieve", "accomplish", "attain", "reach"], ["achieve", "accomplish", "attain"]),
    (V, ["achieved", "attained", "reached"], ["achieved", "attained"]),
    (V, ["provide", "give", "offer", "supply"], ["provide"]),
    (V, ["consider", "contemplate", "weigh"], ["consider", "contemplate"]),
    (V, ["include", "contain", "comprise", "encompass"], None),
    (V, ["happen", "occur", "take place", "arise"], ["happen", "occur", "arise"]),
    (V, ["happened", "occurred", "took place", "arose"], ["happened", "occurred", "arose"]),
    (V, ["alter", "modify", "adjust", "change"], ["alter", "modify", "adjust"]),
    (V, ["changed", "altered", "modified", "adjusted"], None),
    (V, ["affect", "influence", "impact"], ["affect"]),
    (V, ["seek", "search for", "look for", "pursue"], ["seek"]),
    (V, ["discuss", "talk about", "debate", "address"], ["discuss"]),
    (V, ["determine", "establish", "ascertain", "figure out"], ["determine", "ascertain"]),
    (V, ["ensure", "guarantee", "make sure"], ["ensure"]),
    (V, ["emphasize", "stress", "highlight", "underline"], ["emphasize"]),
    # --- nouns ------------------------------------------------------------
    (N, ["problem", "issue", "difficulty", "challenge"], None),
    (N, ["idea", "concept", "notion", "thought"], ["idea", "concept", "notion"]),  # "I thought"
    (N, ["outcome", "result"], ["outcome"]),
    (N, ["consequence", "effect", "result"], ["consequence"]),
    (N, ["goal", "aim", "objective", "target"], ["goal", "objective"]),
    (N, ["method", "approach", "technique", "way"], ["method", "technique"]),
    (N, ["benefit", "advantage", "merit"], ["advantage", "merit"]),
    (N, ["opportunity", "chance", "opening", "possibility"], ["opportunity"]),
    (N, ["purpose", "intention", "aim", "objective"], ["purpose", "intention"]),
    (N, ["example", "instance"], None),
    # No "persons": it reads stiff and legal ("kept persons inside").
    (N, ["people", "individuals"], ["people", "individuals"]),
    (N, ["kid", "child", "youngster"], ["kid", "youngster"]),
    (N, ["job", "occupation", "profession", "career"], ["occupation", "profession"]),
    (N, ["task", "assignment", "duty", "chore"], ["task", "assignment"]),
    (N, ["mistake", "error", "blunder", "slip"], ["mistake", "error", "blunder"]),
    (N, ["answer", "reply", "response"], ["response"]),
    (N, ["research", "study", "investigation", "inquiry"], ["investigation", "inquiry"]),
    (N, ["knowledge", "understanding", "expertise", "awareness"], ["knowledge"]),
    (N, ["skill", "ability", "talent", "capability"], None),
    (N, ["advice", "guidance", "counsel"], ["advice", "guidance"]),
    (N, ["picture", "image", "photo", "photograph"], ["photo", "photograph"]),
    (N, ["house", "home", "residence", "dwelling"], ["house", "residence", "dwelling"]),
    (N, ["car", "vehicle", "automobile"], None),
    (N, ["journey", "trip", "voyage", "excursion"], ["journey", "voyage", "excursion"]),
    (N, ["happiness", "joy", "delight", "contentment"], None),
    (N, ["sadness", "sorrow", "grief", "unhappiness"], None),
    (N, ["anger", "rage", "fury"], None),
    (N, ["strength", "power", "might"], ["strength"]),
    (N, ["speed", "pace", "velocity"], ["velocity", "pace"]),
    (N, ["amount", "quantity"], ["quantity"]),
    (N, ["part", "portion", "section", "segment"], ["portion", "section", "segment"]),
    (N, ["customer", "client", "patron", "buyer"], ["customer", "client", "patron"]),
    # "teacher" stays: "his educator" is the wrong register.
    (N, ["teacher", "instructor", "educator", "tutor"], ["instructor", "educator"]),
    (N, ["student", "learner", "pupil"], None),
    (N, ["friend", "companion", "pal", "buddy"], None),
    (N, ["moment", "instant"], ["moment"]),
    (N, ["effort", "attempt", "endeavor"], ["effort", "endeavor"]),
    (N, ["feature", "characteristic", "trait", "attribute"], ["characteristic", "trait"]),
    (N, ["opinion", "view", "perspective", "viewpoint"], ["perspective", "viewpoint"]),
    (N, ["topic", "subject", "theme"], ["topic", "theme"]),
    (N, ["rule", "regulation", "guideline", "principle"], ["guideline"]),
    (N, ["danger", "risk", "hazard", "threat"], ["danger", "hazard"]),
    (N, ["growth", "expansion", "development"], ["growth", "expansion"]),
    (N, ["tool", "device", "instrument"], ["device"]),
    (N, ["story", "tale", "narrative", "account"], ["tale"]),
    (N, ["gift", "present"], ["gift"]),
    (N, ["noise", "racket", "din"], None),
    # --- added for coverage (keys avoid words with a common second part of speech) ---
    (A, ["vital", "essential", "critical"], ["vital"]),
    (A, ["appropriate", "suitable"], None),
    (A, ["relevant", "pertinent", "applicable"], ["relevant", "pertinent"]),
    (A, ["sudden", "abrupt", "unexpected"], ["sudden", "abrupt"]),
    (A, ["constant", "continual", "persistent"], ["constant", "continual"]),
    (A, ["specific", "particular", "precise"], ["specific"]),
    (A, ["complicated", "complex", "involved"], ["complicated"]),
    (A, ["vast", "immense", "enormous"], ["vast"]),
    (A, ["slight", "small", "minor"], ["slight"]),
    (A, ["considerable", "substantial", "sizable"], ["considerable", "substantial"]),
    (A, ["obtainable", "available", "accessible"], ["obtainable"]),
    (A, ["competent", "capable", "skilled"], ["competent"]),
    (A, ["eager", "keen", "enthusiastic"], ["eager", "enthusiastic"]),
    (A, ["harmful", "damaging", "detrimental"], None),
    (A, ["equitable", "fair", "even-handed"], ["equitable"]),
    (A, ["expensive", "costly", "pricey"], ["expensive", "costly"]),
    (A, ["affordable", "inexpensive", "cheap"], ["affordable", "inexpensive"]),
    (A, ["previous", "prior", "earlier", "former"], ["previous"]),
    (A, ["initial", "first", "opening"], ["initial"]),
    (A, ["distinctive", "unique", "characteristic"], ["distinctive"]),
    (A, ["ongoing", "continuing", "current"], ["ongoing", "continuing"]),
    (A, ["outdated", "obsolete", "old-fashioned"], ["outdated", "obsolete"]),
    (A, ["workable", "practical", "realistic"], ["workable"]),
    (A, ["reliable", "dependable", "trustworthy"], None),
    (A, ["flexible", "adaptable", "versatile"], None),
    (A, ["worldwide", "global", "international"], ["worldwide"]),
    (A, ["annual", "yearly"], None),
    (A, ["extensive", "broad", "wide-ranging"], ["extensive"]),
    (A, ["restricted", "limited", "narrow"], ["restricted"]),
    (A, ["surprising", "unexpected", "startling"], ["surprising", "startling"]),
    (A, ["worried", "anxious", "uneasy", "concerned"], ["worried", "anxious", "uneasy"]),
    (A, ["visible", "observable", "noticeable"], ["visible", "observable"]),
    (A, ["optimal", "ideal", "best"], ["optimal"]),
    (A, ["fundamental", "basic", "core"], ["fundamental"]),
    (A, ["genuine", "real", "authentic"], ["genuine", "authentic"]),
    (R, ["increasingly", "progressively", "more and more"], ["increasingly", "progressively"]),
    (R, ["merely", "simply", "only"], ["merely"]),
    (R, ["initially", "at first", "originally"], ["initially"]),
    (R, ["previously", "earlier", "formerly"], ["previously", "formerly"]),
    (R, ["subsequently", "later", "afterwards"], ["subsequently", "afterwards"]),
    (R, ["deliberately", "intentionally", "on purpose"], ["deliberately", "intentionally"]),
    (R, ["accidentally", "unintentionally", "by accident"], ["accidentally", "unintentionally"]),
    (R, ["forcefully", "strongly", "firmly"], ["forcefully"]),
    (R, ["extensively", "widely", "broadly"], ["extensively"]),
    (R, ["properly", "correctly", "appropriately"], ["properly", "correctly"]),
    (R, ["constantly", "continually", "continuously", "all the time"], ["constantly", "continually"]),
    (R, ["occasionally", "sometimes", "at times", "now and then"], ["occasionally"]),
    (R, ["slightly", "marginally", "a little"], ["slightly", "marginally"]),
    (R, ["greatly", "considerably", "substantially"], ["greatly"]),
    (R, ["truly", "genuinely", "really"], ["truly", "genuinely"]),
    (R, ["simultaneously", "concurrently", "at the same time"], ["simultaneously", "concurrently"]),
    (R, ["separately", "individually", "independently"], ["separately", "individually"]),
    (R, ["thoroughly", "comprehensively", "in depth"], ["thoroughly", "comprehensively"]),
    (R, ["precisely", "exactly"], None),
    (V, ["assess", "evaluate", "gauge", "appraise"], ["assess", "evaluate"]),
    (V, ["assessed", "evaluated", "gauged"], ["assessed", "evaluated"]),
    (V, ["assessing", "evaluating", "gauging"], ["assessing", "evaluating"]),
    (V, ["investigated", "examined", "explored", "studied"], ["investigated", "examined"]),
    (V, ["examining", "investigating", "exploring"], ["examining", "investigating"]),
    (V, ["identify", "pinpoint", "recognize", "spot"], ["identify"]),
    (V, ["identified", "pinpointed", "recognized"], ["identified"]),
    (V, ["increase", "raise", "boost"], ["increase"]),
    (V, ["eliminate", "remove", "get rid of"], ["eliminate"]),
    (V, ["eliminated", "removed", "got rid of"], ["eliminated"]),
    (V, ["encourage", "motivate", "inspire", "urge"], ["encourage", "motivate"]),
    (V, ["encouraged", "motivated", "inspired", "urged"], ["encouraged", "motivated"]),
    (V, ["establish", "set up", "create"], ["establish"]),
    (V, ["established", "set up", "created"], ["established"]),
    (V, ["expand", "extend", "broaden", "widen"], ["expand", "broaden", "widen"]),
    (V, ["combine", "merge", "blend", "integrate"], ["combine", "merge"]),
    (V, ["combined", "merged", "blended", "integrated"], ["combined", "merged"]),
    (V, ["predict", "forecast", "anticipate"], ["predict", "forecast"]),
    (V, ["predicted", "forecast", "anticipated"], ["predicted"]),
    (V, ["respond", "reply", "answer"], ["respond"]),
    (V, ["responded", "replied", "answered"], ["responded", "replied"]),
    (V, ["participate", "take part", "engage"], ["participate"]),
    (V, ["participated", "took part", "engaged"], ["participated"]),
    (V, ["participating", "taking part", "engaging"], ["participating"]),
    (V, ["ignore", "overlook", "disregard", "neglect"], ["ignore", "overlook", "disregard"]),
    (V, ["ignored", "overlooked", "disregarded", "neglected"], ["ignored", "overlooked", "disregarded"]),
    (V, ["persuade", "convince"], None),
    (V, ["persuaded", "convinced"], None),
    (V, ["foresee", "anticipate", "expect"], ["foresee", "anticipate"]),
    (V, ["emerge", "surface", "arise"], ["emerge"]),
    (V, ["emerged", "surfaced", "arose"], ["emerged"]),
    (V, ["handle", "manage", "deal with"], ["handle"]),
    (V, ["handled", "managed", "dealt with"], ["handled"]),
    (V, ["verify", "validate", "check"], ["verify", "validate"]),
    (V, ["verified", "validated", "checked"], ["verified", "validated"]),
    (N, ["aspect", "facet", "dimension", "feature"], ["aspect", "facet"]),
    (N, ["factor", "element", "component"], ["factor"]),
    (N, ["impact", "effect", "influence"], ["impact"]),
    (N, ["decision", "choice"], ["decision"]),
    (N, ["domain", "field", "area", "sphere"], ["domain", "sphere"]),
    (N, ["procedure", "process"], ["procedure"]),
    (N, ["strategy", "plan", "tactic"], ["strategy", "tactic"]),
    (N, ["requirement", "prerequisite", "condition"], ["requirement", "prerequisite"]),
    (N, ["trend", "tendency", "pattern"], ["trend", "tendency"]),
    (N, ["shortage", "scarcity", "deficit"], ["shortage", "scarcity"]),
    (N, ["region", "area", "zone"], ["region", "zone"]),
    (N, ["discovery", "finding"], ["discovery"]),
    (N, ["improvement", "enhancement", "advance", "gain"], ["improvement", "enhancement"]),
    (N, ["reduction", "decrease", "decline", "drop"], ["reduction"]),
    (N, ["employee", "worker", "staff member"], ["employee", "worker"]),
    (N, ["company", "firm", "business"], ["company"]),
    (N, ["supervisor", "manager"], ["supervisor"]),
    (N, ["conversation", "dialogue", "discussion", "exchange"], ["conversation", "dialogue"]),
    (N, ["situation", "scenario", "circumstance", "case"], ["situation", "scenario"]),
    (N, ["limitation", "constraint", "restriction"], None),
    (N, ["option", "alternative", "choice"], ["option"]),
    (N, ["obstacle", "barrier", "hurdle", "impediment"], ["obstacle", "barrier", "hurdle"]),
    (N, ["solution", "remedy", "answer", "fix"], ["solution", "remedy"]),
    (N, ["era", "period", "age", "epoch"], ["era", "epoch"]),
    (N, ["specialist", "expert"], ["specialist"]),
    (N, ["implication", "consequence", "ramification"], ["implication", "ramification"]),
    (V, ["transformed", "reshaped", "changed", "altered"], ["transformed", "reshaped"]),
    (R, ["fundamentally", "radically", "deeply"], ["fundamentally", "radically"]),
    (V, ["thrive", "flourish", "prosper"], None),
    (A, ["novel", "new"], ["novel"]),
]

IRREGULAR_PLURALS = {
    "child": "children",
    "person": "people",
    "man": "men",
    "woman": "women",
    "analysis": "analyses",
}


def _build_index() -> dict[str, tuple[str, list[str]]]:
    index: dict[str, tuple[str, list[str]]] = {}
    for pos, words, keys in GROUPS:
        for key in keys if keys is not None else words:
            if key not in words:
                raise ValueError(f"lexicon key {key!r} is not in its group {words}")
            if key in index:
                raise ValueError(f"lexicon key {key!r} appears in more than one group")
            index[key] = (pos, [w for w in words if w != key])
    return index


SYNONYMS = _build_index()


def pluralize(phrase: str, pos: str) -> str:
    """Add ``-s`` inflection: the last word of a noun, the first word of a verb."""
    parts = phrase.split(" ")
    idx = len(parts) - 1 if pos == N else 0
    word = parts[idx]
    if word in IRREGULAR_PLURALS:
        word = IRREGULAR_PLURALS[word]
    elif word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        word = word[:-1] + "ies"
    elif word.endswith(("s", "x", "z", "ch", "sh")):
        word += "es"
    else:
        word += "s"
    parts[idx] = word
    return " ".join(parts)


_IRREGULAR_SINGULAR = {plural: single for single, plural in IRREGULAR_PLURALS.items()}


def lookup(word: str) -> tuple[str, list[str]] | None:
    """``(part_of_speech, candidates)`` for a lowercase word, or ``None``."""
    entry = SYNONYMS.get(word)
    if entry:
        return entry[0], list(entry[1])
    bases = []
    if word in _IRREGULAR_SINGULAR:
        bases.append(_IRREGULAR_SINGULAR[word])
    if len(word) > 4 and word.endswith("ies"):
        bases.append(word[:-3] + "y")
    if len(word) > 3 and word.endswith("es"):
        bases.append(word[:-2])
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        bases.append(word[:-1])
    for base in bases:
        entry = SYNONYMS.get(base)
        if entry and entry[0] in (N, V) and pluralize(base, entry[0]) == word:
            return entry[0], [pluralize(alt, entry[0]) for alt in entry[1]]
    return None


def synonyms_for(word: str) -> list[str] | None:
    """Return replacement candidates for a lowercase word, or ``None``."""
    found = lookup(word)
    return found[1] if found else None


# --- words the rewrite never swaps --------------------------------------------
#
# Hedges set how certain a claim is, negations flip it, and reporting verbs
# ("suggest", "indicate", "show") carry how strong the evidence is. Swapping
# them ("the results suggest" -> "the results propose") changes the meaning,
# so they are never replaced and never offered as replacements.


def _forms(*bases: str) -> set[str]:
    out: set[str] = set()
    for b in bases:
        stem = b[:-1] if b.endswith("e") else b
        out |= {b, b + "s", stem + "ed", stem + "ing"}
        if b.endswith("y") and b[-2] not in "aeiou":
            out |= {b[:-1] + "ies", b[:-1] + "ied"}
    return out


HEDGES = frozenset(
    {
        "may",
        "might",
        "could",
        "possibly",
        "perhaps",
        "probably",
        "likely",
        "unlikely",
        "potentially",
        "approximately",
        "roughly",
        "arguably",
        "somewhat",
        "partly",
        "partially",
        "apparently",
        "presumably",
        "maybe",
        "conceivably",
        "seemingly",
        "supposedly",
        "allegedly",
    }
    | _forms("suggest", "appear", "seem", "tend")
)
NEGATIONS = frozenset(
    {
        "not",
        "no",
        "never",
        "none",
        "nor",
        "neither",
        "nobody",
        "nothing",
        "nowhere",
        "without",
        "cannot",
        "unable",
        "hardly",
        "barely",
        "scarcely",
        "rarely",
        "seldom",
        "absent",
        "infrequently",
    }
    | _forms("lack", "fail")
)
REPORTING = frozenset(
    _forms(
        "indicate",
        "imply",
        "propose",
        "claim",
        "argue",
        "assert",
        "contend",
        "state",
        "mention",
        "note",
        "report",
        "recommend",
        "conclude",
        "demonstrate",
        "show",
        "reveal",
        "prove",
        "confirm",
    )
    | {"shown", "proven", "implied", "implies"}
)
FROZEN = HEDGES | NEGATIONS | REPORTING


def is_frozen(phrase: str) -> bool:
    """True if any word of ``phrase`` is a hedge, negation or reporting verb."""
    return any(w in FROZEN or w.endswith(("n't", "n\u2019t")) for w in phrase.lower().split())


# --- generated synonyms (app/data/synonyms_extra.json, built by tools/build_lexicon.py) ---
#
# Adjectives and adverbs from WordNet, filtered by word frequency. They are broader than the
# hand-written groups, so they are only offered as editor suggestions (click a changed word),
# where the user picks one in context. The rule engine never swaps a word for them.

EXTRA_FILE = Path(__file__).resolve().parents[1] / "data" / "synonyms_extra.json"


def _load_extra(path: Path = EXTRA_FILE) -> dict[str, tuple[str, list[str]]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}  # the file is optional: without it the hand-written groups still work
    out: dict[str, tuple[str, list[str]]] = {}
    for pos in (A, R):
        group = data.get(pos)
        if not isinstance(group, dict):
            continue
        for word, alts in group.items():
            if word in SYNONYMS or not isinstance(alts, list):
                continue  # hand-written groups win
            alts = [a for a in alts if isinstance(a, str) and a and a != word]
            if alts:
                out[word] = (pos, alts)
    return out


EXTRA_SYNONYMS = _load_extra()


def suggestions_for(word: str) -> list[str] | None:
    """``synonyms_for`` plus generated synonyms, minus frozen words and opposites. For the editor's suggestions."""
    if is_frozen(word):
        return None
    found = synonyms_for(word)
    if found is None:
        entry = EXTRA_SYNONYMS.get(word)
        found = entry[1] if entry else None
    alts = [a for a in found or [] if not is_frozen(a) and not opposed(word, a)]
    return alts or None


# --- word frequency (app/data/word_freq.json, built by tools/build_freq.py) ------
#
# Zipf frequencies of the words in GROUPS. The rule engine prefers a synonym about as
# common as the word it replaces, so "tired" does not become "weary".

FREQ_FILE = Path(__file__).resolve().parents[1] / "data" / "word_freq.json"


def _load_freq(path: Path = FREQ_FILE) -> dict[str, float]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}  # optional: without it no candidate is down-ranked
    freq = data.get("zipf")
    return {w: float(f) for w, f in freq.items() if isinstance(f, (int, float))} if isinstance(freq, dict) else {}


WORD_FREQ = _load_freq()


def much_rarer(candidate: str, original: str, gap: float) -> bool:
    """True if ``candidate`` is more than ``gap`` Zipf points rarer than ``original`` (unknown: False)."""
    a, b = WORD_FREQ.get(candidate.lower()), WORD_FREQ.get(original.lower())
    return a is not None and b is not None and b - a > gap


# --- opposites (app/data/antonyms.json, built by tools/build_antonyms.py) -------
#
# A synonym that is the opposite of the word it replaces, or of a word next to it
# ("strong and weak" -> "strong and powerless"), is never used or suggested.

ANTONYM_FILE = Path(__file__).resolve().parents[1] / "data" / "antonyms.json"


def _load_antonyms(path: Path = ANTONYM_FILE) -> dict[str, frozenset[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}  # optional, like synonyms_extra.json
    return {
        w: frozenset(o for o in opp if isinstance(o, str))
        for w, opp in data.items()
        if not w.startswith("_") and isinstance(opp, list)
    }


ANTONYMS = _load_antonyms()


def _bases(word: str) -> set[str]:
    """``word`` plus naive singular / base forms, so "decreases" matches "decrease"."""
    out = {word}
    for suf in ("es", "s", "ed", "d", "ing"):
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            out.add(word[: -len(suf)])
    return out


def opposed(a: str, b: str) -> bool:
    """True if words ``a`` and ``b`` (lowercase) are opposites, e.g. "increase" / "decreases"."""
    left, right = _bases(a), _bases(b)
    return any(right & ANTONYMS.get(x, frozenset()) for x in left) or any(
        left & ANTONYMS.get(y, frozenset()) for y in right
    )


# Slang the rewrite never picks.
CASUAL = {
    "pal",
    "buddy",
    "folks",
    "kid",
    "kids",
    "tough",
    "lots of",
    "plenty of",
    "awesome",
    "stuff",
    "chore",
    "racket",
    "maybe",
    "figure out",
    "find out",
    "right away",
    "straight away",
    "e.g.",
    "pricey",
    "cheap",
}

# --- phrase tables: tuple-of-lowercase-words -> replacement options ----------


def _table(raw: dict[str, list[str]]) -> dict[tuple[str, ...], list[str]]:
    return {tuple(k.split(" ")): v for k, v in raw.items()}


_PHRASAL = {
    "get rid of": ["eliminate", "remove", "dispose of"],
    "come up with": ["devise", "create", "think of"],
    "came up with": ["devised", "created", "thought of"],
    "look into": ["investigate", "examine", "explore"],
    "put off": ["postpone", "delay"],
    "carry out": ["conduct", "perform", "execute"],
    "carried out": ["conducted", "performed", "executed"],
    "point out": ["note", "highlight", "indicate"],
    "pointed out": ["noted", "highlighted", "indicated"],
    "set up": ["establish", "arrange", "configure"],
    "give up": ["abandon", "quit", "stop"],
    "go up": ["rise", "increase"],
    "go down": ["fall", "decline", "drop"],
    "deal with": ["handle", "address", "manage"],
    "talk about": ["discuss"],
    "look for": ["seek", "search for"],
    "find out": ["discover", "learn", "determine"],
    "found out": ["discovered", "learned", "determined"],
    "figure out": ["work out", "determine", "understand"],
}

GENERAL_PHRASES = _table(
    {
        **_PHRASAL,
        "a lot of": ["plenty of", "lots of", "a great deal of"],
        "in order to": ["to", "so as to"],
        "as well as": ["along with", "together with"],
        "because of": ["due to", "owing to", "on account of"],
        "in spite of": ["despite"],
        "despite": ["in spite of"],
        "at the same time": ["simultaneously", "concurrently"],
        "for example": ["for instance"],
        "for instance": ["for example"],
        "as a result": ["consequently", "as a consequence"],
        "in the end": ["ultimately", "eventually"],
        "most of the time": ["usually", "generally", "typically"],
        "right away": ["immediately", "at once", "straight away"],
        "a number of": ["several", "various", "numerous"],
        "due to the fact that": ["because", "since"],
        "in the event that": ["if"],
        "prior to": ["before"],
        "with regard to": ["regarding", "concerning"],
        "in the near future": ["soon", "shortly"],
        "on a daily basis": ["daily", "every day"],
        "the majority of": ["most"],
        "make sure that": ["ensure that", "confirm that"],
        "try to": ["attempt to", "strive to", "seek to"],
        "in addition to": ["besides", "as well as"],
        "in addition": ["also", "on top of that"],
        "a great deal of": ["much", "a lot of"],
        "in terms of": ["regarding", "when it comes to"],
        "as soon as": ["once", "the moment"],
        "at this point in time": ["now", "at this point"],
        "at the moment": ["right now", "currently", "at present"],
        "in particular": ["particularly", "especially"],
        "on the other hand": ["by contrast", "then again"],
        "in contrast": ["by contrast", "conversely"],
        "in general": ["generally", "on the whole"],
        "a wide range of": ["a broad range of", "many different", "a variety of"],
        "a variety of": ["a range of", "various"],
        "a large number of": ["many", "a great many"],
        "a small number of": ["a few", "a handful of"],
        "is able to": ["can"],
        "are able to": ["can"],
        "was able to": ["could", "managed to"],
        "were able to": ["could", "managed to"],
        "has the ability to": ["can", "is able to"],
        "have the ability to": ["can", "are able to"],
        "in light of": ["given", "considering"],
        "with respect to": ["regarding", "concerning"],
        "in relation to": ["regarding", "concerning"],
        "as a consequence": ["as a result"],
        "for the purpose of": ["for"],
        "in the course of": ["during"],
        "take into account": ["consider", "allow for"],
        "takes into account": ["considers"],
        "took into account": ["considered"],
        "taken into account": ["considered"],
        "make use of": ["use"],
        "makes use of": ["uses"],
        "made use of": ["used"],
        "turned out to be": ["proved to be"],
        "bring about": ["cause", "produce"],
        "brings about": ["causes", "produces"],
        "brought about": ["caused", "produced"],
        "keep in mind": ["remember", "bear in mind"],
        "bear in mind": ["keep in mind", "remember"],
        "in the long run": ["over time", "eventually"],
        "in the long term": ["over time"],
        "at first": ["initially"],
        "in fact": ["actually", "in reality"],
        "of course": ["naturally"],
        "in other words": ["put simply", "that is"],
        "even though": ["although", "though"],
        "although": ["though", "even though"],
        "is made up of": ["consists of", "is composed of"],
        "are made up of": ["consist of", "are composed of"],
        "consists of": ["is made up of", "comprises"],
        "as a whole": ["overall"],
        "each and every": ["every"],
        "first and foremost": ["first", "above all"],
        "in today's world": ["today", "these days"],
        "nowadays": ["these days", "today"],
        "in recent years": ["over the past few years", "recently"],
        "so as to": ["to", "in order to"],
        "by means of": ["through", "by"],
        "in accordance with": ["in line with", "following"],
        "with the exception of": ["except", "apart from"],
        "apart from": ["besides", "aside from"],
        "aside from": ["apart from", "besides"],
        "in comparison with": ["compared with"],
        "in comparison to": ["compared to"],
        "in response to": ["in reply to"],
        "in the meantime": ["meanwhile"],
        "meanwhile": ["in the meantime"],
        "as opposed to": ["rather than", "instead of"],
        "in my opinion": ["in my view", "to my mind"],
        "for this reason": ["because of this", "for that reason"],
        "in spite of the fact that": ["although", "even though"],
        "despite the fact that": ["although", "even though"],
        "until now": ["so far", "to date"],
        "a couple of": ["a few"],
        "contribute to": ["add to", "play a part in"],
        "contributes to": ["adds to", "plays a part in"],
        "contributed to": ["added to", "played a part in"],
        "focus on": ["concentrate on", "center on"],
        "focuses on": ["concentrates on", "centers on"],
        "focused on": ["concentrated on", "centered on"],
        "rely on": ["depend on", "count on"],
        "relies on": ["depends on"],
        "relied on": ["depended on"],
        "strike the right balance": ["find the right balance"],
        "strike a balance": ["find a balance"],
        "in conclusion": ["to conclude", "in closing"],
    }
)

CONTRACTIONS = {
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "can't": "cannot",
    "won't": "will not",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "haven't": "have not",
    "hasn't": "has not",
    "hadn't": "had not",
    "couldn't": "could not",
    "shouldn't": "should not",
    "wouldn't": "would not",
    "it's": "it is",
    "that's": "that is",
    "there's": "there is",
    "what's": "what is",
    "he's": "he is",
    "she's": "she is",
    "i'm": "I am",
    "you're": "you are",
    "we're": "we are",
    "they're": "they are",
    "i've": "I have",
    "you've": "you have",
    "we've": "we have",
    "they've": "they have",
    "i'll": "I will",
    "you'll": "you will",
    "we'll": "we will",
    "they'll": "they will",
    "i'd": "I would",
    "you'd": "you would",
    "we'd": "we would",
    "they'd": "they would",
    "let's": "let us",
}
_CONTRACTABLE = [
    "do not",
    "does not",
    "did not",
    "is not",
    "are not",
    "was not",
    "cannot",
    "will not",
    "would not",
    "could not",
    "should not",
    "have not",
    "has not",
    "it is",
    "that is",
    "I am",
    "we are",
    "they are",
    "you are",
]
_REVERSE = {v.lower(): k for k, v in CONTRACTIONS.items()}
CONTRACT_PHRASES = _table({p.lower(): [_REVERSE[p.lower()].replace("i'", "I'")] for p in _CONTRACTABLE})
