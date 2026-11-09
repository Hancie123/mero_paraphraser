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

A, R, V, N = "a", "r", "v", "n"  # adjective, adverb, verb, noun

GROUPS: list[tuple[str, list[str], list[str] | None]] = [
    # --- adjectives -------------------------------------------------------
    (A, ["big", "large", "sizable"], None),
    (A, ["huge", "enormous", "massive", "immense"], None),
    (A, ["tiny", "minuscule"], None),
    (A, ["excellent", "outstanding", "superb"], None),
    (A, ["important", "significant", "crucial", "essential"], None),
    (A, ["difficult", "challenging", "demanding"], None),
    (A, ["easy", "simple", "straightforward", "effortless"], None),
    (A, ["quick", "fast", "rapid", "swift"], None),
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
    (A, ["tired", "exhausted", "weary", "fatigued"], None),
    (A, ["rich", "wealthy", "affluent", "prosperous"], None),
    (A, ["honest", "truthful", "sincere", "candid"], None),
    (A, ["strong", "powerful", "robust"], None),
    (A, ["weak", "feeble", "fragile"], None),
    (A, ["useful", "helpful", "beneficial", "valuable"], None),
    (A, ["interesting", "intriguing", "fascinating", "engaging"], None),
    (A, ["boring", "dull", "tedious", "monotonous"], None),
    (A, ["accurate", "precise", "exact"], None),
    (A, ["sufficient", "adequate", "ample"], None),
    (A, ["typical", "usual", "normal", "customary"], None),
    (A, ["quiet", "silent", "calm", "peaceful"], None),
    (A, ["famous", "renowned", "well-known", "celebrated"], None),
    (A, ["possible", "feasible", "achievable", "viable"], None),
    (A, ["rare", "uncommon", "scarce", "infrequent"], None),
    (A, ["brave", "courageous", "bold", "fearless"], None),
    (A, ["careful", "cautious", "attentive", "mindful"], None),
    (A, ["effective", "successful", "productive", "fruitful"], None),
    (A, ["serious", "severe", "grave"], None),
    (A, ["ready", "prepared"], None),
    # --- adverbs ----------------------------------------------------------
    (R, ["quickly", "rapidly", "swiftly", "promptly"], None),
    (R, ["slowly", "gradually", "steadily"], None),
    (R, ["often", "frequently", "regularly", "commonly"], None),
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
    (R, ["carefully", "cautiously", "attentively", "meticulously"], None),
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
    (V, ["increased", "raised", "expanded"], None),
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
    (V, ["examine", "inspect", "analyze", "investigate", "study"],
     ["examine", "inspect", "analyze", "investigate"]),
    (V, ["construct", "assemble", "build"], ["construct", "assemble"]),
    (V, ["solve", "resolve", "fix", "settle"], ["solve", "resolve"]),
    (V, ["gather", "collect", "accumulate"], None),
    (V, ["achieve", "accomplish", "attain", "reach"], ["achieve", "accomplish", "attain"]),
    (V, ["achieved", "attained", "reached"], ["achieved", "attained"]),
    (V, ["provide", "supply", "offer", "give"], ["provide"]),
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
    (N, ["idea", "concept", "notion", "thought"], None),
    (N, ["result", "outcome", "consequence"], ["outcome", "consequence"]),
    (N, ["goal", "aim", "objective", "target"], ["goal", "objective"]),
    (N, ["method", "approach", "technique", "way"], ["method", "technique"]),
    (N, ["benefit", "advantage", "merit"], ["advantage", "merit"]),
    (N, ["opportunity", "chance", "opening", "possibility"], ["opportunity"]),
    (N, ["purpose", "intention", "aim", "objective"], ["purpose", "intention"]),
    (N, ["example", "instance"], None),
    (N, ["people", "individuals", "persons", "folks"], ["people", "individuals"]),
    (N, ["kid", "child", "youngster"], ["kid", "youngster"]),
    (N, ["job", "occupation", "profession", "career"], ["occupation", "profession"]),
    (N, ["task", "assignment", "duty", "chore"], ["task", "assignment"]),
    (N, ["mistake", "error", "blunder", "slip"], ["mistake", "error", "blunder"]),
    (N, ["answer", "reply", "response"], ["response"]),
    (N, ["research", "study", "investigation", "inquiry"], ["investigation", "inquiry"]),
    (N, ["knowledge", "understanding", "expertise", "awareness"], ["knowledge"]),
    (N, ["skill", "ability", "talent", "capability"], None),
    (N, ["advice", "guidance", "counsel"], ["advice", "guidance"]),
    (N, ["picture", "image", "photo", "photograph"], ["image", "photo", "photograph"]),
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
    (N, ["teacher", "instructor", "educator", "tutor"], None),
    (N, ["student", "learner", "pupil"], None),
    (N, ["friend", "companion", "pal", "buddy"], None),
    (N, ["moment", "instant"], ["moment"]),
    (N, ["effort", "attempt", "endeavor"], ["effort", "endeavor"]),
    (N, ["feature", "characteristic", "trait", "attribute"], ["characteristic", "trait"]),
    (N, ["opinion", "view", "perspective", "viewpoint"], ["opinion", "perspective", "viewpoint"]),
    (N, ["topic", "subject", "theme"], ["topic", "theme"]),
    (N, ["rule", "regulation", "guideline", "principle"], ["regulation", "guideline"]),
    (N, ["danger", "risk", "hazard", "threat"], ["danger", "hazard"]),
    (N, ["growth", "expansion", "development"], ["growth", "expansion"]),
    (N, ["tool", "device", "instrument"], ["tool", "device"]),
    (N, ["place", "location", "spot"], ["location"]),
    (N, ["story", "tale", "narrative", "account"], ["story", "tale", "narrative"]),
    (N, ["gift", "present"], ["gift"]),
    (N, ["noise", "racket", "din"], None),
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


def synonyms_for(word: str) -> list[str] | None:
    """Return replacement candidates for a lowercase word, or ``None``."""
    entry = SYNONYMS.get(word)
    if entry:
        return list(entry[1])
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
            return [pluralize(alt, entry[0]) for alt in entry[1]]
    return None


# Words a formal register prefers, and words it avoids.
FORMAL_PREF = {
    "assist", "assisted", "assisting", "demonstrate", "demonstrated", "utilize",
    "utilizing", "commence", "commenced", "obtain", "acquire", "purchase",
    "purchased", "individuals", "consequently", "furthermore", "moreover",
    "nevertheless", "nonetheless", "significant", "numerous", "sufficient",
    "approximately", "residence", "automobile", "enhance", "enhanced", "examine",
    "ascertain", "comprehend", "inform", "notify", "require", "conclude",
    "concluded", "construct", "accumulate", "attain", "attained", "accomplish",
    "contemplate", "modify", "modified", "occur", "occurred", "encompass",
    "guarantee", "investigate", "inquiry", "investigation", "objective",
    "technique", "advantage", "instance", "error", "response", "guidance",
    "expertise", "capability", "photograph", "vehicle", "journey", "contentment",
    "sorrow", "velocity", "portion", "segment", "client", "instructor",
    "educator", "learner", "companion", "endeavor", "characteristic",
    "perspective", "regulation", "hazard", "expansion", "instrument", "location",
    "narrative", "therefore", "thus", "hence", "entirely", "fully", "primarily",
    "particularly", "immediately", "possibly", "undoubtedly", "readily",
    "meticulously", "considerably", "substantially", "presently", "frequently",
    "typically", "generally", "rapidly", "gradually", "virtually", "ultimately",
    "evidently", "challenging", "intelligent", "prevalent", "customary",
    "evident", "apparent", "principal", "hazardous", "exhausted", "affluent",
    "sincere", "beneficial", "valuable", "fascinating", "tedious", "precise",
    "adequate", "renowned", "feasible", "courageous", "cautious", "severe",
    "prepared", "delighted", "contemporary", "various", "requisite", "notably",
    "specifically", "propose", "proposed", "recommend", "recommended", "select",
    "selected", "generate", "generated", "produce", "produced", "analyze",
    "resolve", "establish", "determine", "discuss", "emphasize", "ensure",
    "affect", "alter", "altered", "seek", "permit", "permitted", "enable",
    "maintain", "retain", "preserve", "discover", "eliminate", "devise",
    "indicate", "regarding", "concerning", "simultaneously", "owing to",
    "due to", "in addition", "as a consequence", "notwithstanding", "postpone",
    "conduct", "perform", "investigate", "address", "handle", "abandon",
}

CASUAL = {
    "pal", "buddy", "folks", "kid", "kids", "tough", "lots of", "plenty of",
    "awesome", "stuff", "chore", "racket", "maybe", "figure out", "find out",
    "right away", "straight away", "e.g.",
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

_WORDY = {
    "in order to": ["to"],
    "due to the fact that": ["because", "since"],
    "at this point in time": ["now", "currently"],
    "at the present time": ["now", "currently"],
    "in the event that": ["if"],
    "a large number of": ["many", "numerous"],
    "a majority of": ["most"],
    "the majority of": ["most"],
    "in spite of the fact that": ["although", "even though"],
    "despite the fact that": ["although", "even though"],
    "with regard to": ["about", "regarding"],
    "with regards to": ["about", "regarding"],
    "in regard to": ["about", "regarding"],
    "in close proximity to": ["near", "close to"],
    "prior to": ["before"],
    "subsequent to": ["after"],
    "each and every": ["every"],
    "first and foremost": ["first"],
    "has the ability to": ["can"],
    "have the ability to": ["can"],
    "is able to": ["can"],
    "are able to": ["can"],
    "on a daily basis": ["daily"],
    "in the near future": ["soon"],
    "a number of": ["several"],
    "as a matter of fact": ["in fact"],
    "at all times": ["always"],
    "until such time as": ["until"],
    "for the purpose of": ["for"],
    "make a decision": ["decide"],
    "made a decision": ["decided"],
    "come to a conclusion": ["conclude"],
    "give consideration to": ["consider"],
    "take into consideration": ["consider"],
    "in a timely manner": ["promptly"],
    "during the course of": ["during"],
    "whether or not": ["whether"],
    "it is important to note that": ["notably,"],
}

GENERAL_PHRASES = _table({
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
})

FORMAL_PHRASES = _table({
    **{k: [o for o in v if o not in CASUAL] or v for k, v in _PHRASAL.items()},
    "a lot of": ["a great deal of"],
    "lots of": ["a great deal of"],
    "really": ["truly"],
    "kids": ["children"],
    "kid": ["child"],
    "stuff": ["material"],
    "maybe": ["perhaps"],
    "totally": ["entirely"],
    "buy": ["purchase"],
    "bought": ["purchased"],
    "buying": ["purchasing"],
    "tough": ["difficult"],
    "awesome": ["excellent"],
    "thanks": ["thank you"],
    "gonna": ["going to"],
    "wanna": ["want to"],
    "gotta": ["have to"],
    "yeah": ["yes"],
    "yep": ["yes"],
    "nope": ["no"],
    "make sure that": ["ensure that"],
})

_SIMPLE_WORDS = {
    "utilize": ["use"], "utilizes": ["uses"], "utilized": ["used"], "utilizing": ["using"],
    "commence": ["start"], "commenced": ["started"], "terminate": ["end"],
    "approximately": ["about"], "sufficient": ["enough"], "adequate": ["enough"],
    "numerous": ["many"], "demonstrate": ["show"], "demonstrated": ["showed"],
    "demonstrates": ["shows"], "assist": ["help"], "assisted": ["helped"],
    "assists": ["helps"], "purchase": ["buy"], "purchased": ["bought"],
    "obtain": ["get"], "obtained": ["got"], "require": ["need"], "requires": ["needs"],
    "additional": ["more"], "facilitate": ["help"], "endeavor": ["try"],
    "subsequently": ["later"], "nevertheless": ["still"], "consequently": ["so"],
    "individuals": ["people"], "inquire": ["ask"], "inform": ["tell"],
    "comprehend": ["understand"], "residence": ["home"], "vehicle": ["car"],
    "automobile": ["car"], "initiate": ["start"], "initiated": ["started"],
    "ascertain": ["find out"], "indicate": ["show"], "indicates": ["shows"],
    "regarding": ["about"], "objective": ["goal"], "methodology": ["method"],
    "modification": ["change"], "modify": ["change"], "modified": ["changed"],
    "enhance": ["improve"], "enhanced": ["improved"], "acquire": ["get"],
    "acquired": ["got"], "possess": ["have"], "possesses": ["has"],
    "beneficial": ["helpful"], "magnitude": ["size"], "optimal": ["best"],
    "whilst": ["while"], "amongst": ["among"], "perceive": ["see"],
    "sufficiently": ["enough"], "prior": ["earlier"], "commencement": ["start"],
}

SIMPLE_PHRASES = _table({**_WORDY, **_SIMPLE_WORDS, "however": ["but"]})
SHORTEN_PHRASES = _table(_WORDY)

CONTRACTIONS = {
    "don't": "do not", "doesn't": "does not", "didn't": "did not", "can't": "cannot",
    "won't": "will not", "isn't": "is not", "aren't": "are not", "wasn't": "was not",
    "weren't": "were not", "haven't": "have not", "hasn't": "has not",
    "hadn't": "had not", "couldn't": "could not", "shouldn't": "should not",
    "wouldn't": "would not", "it's": "it is", "that's": "that is",
    "there's": "there is", "what's": "what is", "he's": "he is", "she's": "she is",
    "i'm": "I am", "you're": "you are", "we're": "we are", "they're": "they are",
    "i've": "I have", "you've": "you have", "we've": "we have", "they've": "they have",
    "i'll": "I will", "you'll": "you will", "we'll": "we will", "they'll": "they will",
    "i'd": "I would", "you'd": "you would", "we'd": "we would", "they'd": "they would",
    "let's": "let us",
}
EXPAND_CONTRACTIONS = _table({k: [v] for k, v in CONTRACTIONS.items()})

_CONTRACTABLE = [
    "do not", "does not", "did not", "is not", "are not", "was not", "cannot",
    "will not", "would not", "could not", "should not", "have not", "has not",
    "it is", "that is", "I am", "we are", "they are", "you are",
]
_REVERSE = {v.lower(): k for k, v in CONTRACTIONS.items()}
CONTRACT_PHRASES = _table({
    p.lower(): [_REVERSE[p.lower()].replace("i'", "I'")] for p in _CONTRACTABLE
})

# Words that only add emphasis; "shorten" mode drops them before another word.
FILLERS = {"very", "really", "basically", "actually", "literally", "essentially"}
