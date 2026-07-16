"""Translates raw Norwegian grocery/flyer product headings into a plain, mostly-English
description of the actual food -- for feeding into BOTH the retrieval query and the LLM
generation prompt.

CONFIRMED ROOT CAUSE this module exists to fix (live-measured, 2026-07-08/09, see
find_recipes_or_generate() callers in pipeline.py): raw Norwegian flyer headings score
catastrophically low against this app's English-only recipe corpus/reranker (embedding
model bge-base-en-v1.5), so real relevant recipes get rejected by the MIN_RERANK_SCORE
gate and the pipeline falls back to LLM generation -- which then ALSO receives the same
raw Norwegian text and hallucinates unrelated recipes. Translating the dish-identity
words before either retrieval or generation closes that gap:
    'COOP GRILL PERFEKT BOKEROKTE SOMMERKOTELETTER' -> best rerank score -9.18, 0/15 pass
    'pork chops' (translated)                       -> best rerank score +5.77, 15/15 pass

This is deliberately NOT built on top of query_normalizer.py: that module does
edit-distance typo-correction (e.g. "briyani" -> "biryani") against the *existing*
English vocabulary, which has nothing to do with translating a different language's
words in the first place.

Design mirrors grocery_discounts.py's own _is_non_food(): Norwegian is a compounding
language (kotelett -> koteletter -> sommerkoteletter), so matching is done as a SUFFIX
against each individual whitespace/hyphen/slash-separated token, never a substring of
the whole heading -- same reasoning as that module's NON_FOOD_KEYWORDS false-positive
fix (a naive substring check for "ost" would wrongly fire on "frokost"/breakfast, which
is exactly why "frokost" -> "breakfast" is listed below as its own, more specific,
override entry: see _translate_token()'s longest-suffix-wins resolution).

Real Norwegian spelling uses æ/ø/å (løk, kjøttdeig, bøkerøkte, ...) -- the raw Tjek data
has these, so the glossary is keyed on the real characters. A handful of entries also
carry an ASCII-folded duplicate (kjottdeig alongside kjøttdeig, etc.) as a defensive
hedge in case any upstream text extraction ever strips diacritics; harmless either way
since an unmatched ASCII fallback key just never fires against properly-accented input.

Both GROCERY_GLOSSARY and NOISE_TOKENS were seeded from the task's confirmed examples
and then cross-checked (not just assumed) against every one of the 734 distinct real
product_name values in discounts_cache/discounts.db (794 rows, 11 stores, scanned
2026-07-09) -- every suffix added below was verified against that full list to make sure
it does not also match an unrelated real heading (the "frokost" case above is the one
genuine collision that scan turned up).

CONFIRMED LIVE BUG (2026-07-10) that expanded this module's coverage a second time: a
user tapped 'COOP STORFEKJOTT STRIMLET' (Coop beef strips) in production and got an
unrelated 'Boerenkool (Cabbage) Stew' recipe. Root cause: 'storfekjott' correctly
translated to 'beef', but 'strimlet' (a preparation/cut descriptor meaning "cut into
strips") had no glossary entry, so it survived untranslated and in ALL CAPS, dragging
the whole query back into the same low-relevance failure mode this module exists to fix.
This wasn't an isolated missing word -- it's a whole missed CATEGORY: Norwegian
preparation/cut descriptors (how a piece of food is shaped/sized/cooked) that get glued
onto an otherwise-correctly-translated food noun, exactly like the røkt/røkte ("smoked")
case already documented above. See _CUT_DESCRIPTORS, _PREP_STATE_DESCRIPTORS, and
_EXACT_MATCH_ONLY_ENTRIES below for the fix, and _translate_token()'s _EXACT_MATCH_ONLY
handling for why one of these entries ("hel") can't use the same plain-suffix matching
as everything else in this file.
"""

import re
from typing import Dict, Optional

from .grocery_discounts import NORWEGIAN_STORES


def _glossary(*groups: Dict[str, str]) -> Dict[str, str]:
    """Merges the category dicts below into one flat glossary -- kept as separate
    per-category literals purely for readability/maintainability, not a runtime
    distinction."""
    merged: Dict[str, str] = {}
    for group in groups:
        merged.update(group)
    return merged


_PORK = {
    "kotelett": "pork chop",
    "koteletter": "pork chop",
    "sommerkoteletter": "pork chop",
    "nakkekotelett": "pork neck chop",
    "svin": "pork",
    "svinekjøtt": "pork",
    "svinekjott": "pork",  # ASCII-folded fallback (task-seeded spelling)
    "svinefilet": "pork fillet",
    "svinenakke": "pork neck",
    "grillribbe": "pork ribs",
    "tynnribbe": "pork ribs",
    "spareribs": "spare ribs",
}

_BEEF = {
    "storfe": "beef",
    "storfekjøtt": "beef",
    "storfekjott": "beef",  # ASCII-folded fallback
    "kjøttdeig": "ground beef",
    "kjottdeig": "ground beef",  # ASCII-folded fallback (task-seeded spelling)
    "biff": "steak",
    "roastbiff": "roast beef",  # more specific than bare "biff" -- longest match wins
    "entrecôte": "ribeye steak",
    "entrecote": "ribeye steak",  # ASCII-folded fallback
    "culotte": "sirloin cap",
}

_LAMB = {
    "lam": "lamb",
    "lammekjøtt": "lamb",
    "lammekjott": "lamb",  # ASCII-folded fallback
    "lammelår": "leg of lamb",
    "lammelar": "leg of lamb",  # ASCII-folded fallback
    "lammekoteletter": "lamb chop",  # overrides the generic "koteletter" -> pork chop
}

_CHICKEN = {
    "kylling": "chicken",
    "kyllingfilet": "chicken fillet",
    "kyllingbryst": "chicken breast",
    "kyllinglår": "chicken thigh",
    "kyllinglar": "chicken thigh",  # ASCII-folded fallback
    "kyllingklubber": "chicken drumsticks",
    "kyllingvinger": "chicken wings",
    "kyllingspyd": "chicken skewers",
    "kyllingburger": "chicken burger",
    "kyllingpølser": "chicken sausage",
    "kyllingpolser": "chicken sausage",  # ASCII-folded fallback
}

_FISH_SEAFOOD = {
    "laks": "salmon",
    "laksefilet": "salmon fillet",
    "lakseburger": "salmon burger",
    "reker": "shrimp",
    "torsk": "cod",
    "makrell": "mackerel",
    "ørret": "trout",
    "orret": "trout",  # ASCII-folded fallback
    "ørretfilet": "trout fillet",
    "fisk": "fish",
    "fiskeburger": "fish burger",
    "fiskekaker": "fish cakes",
    "steinbit": "wolffish",
    "steinbitfilet": "wolffish fillet",
    "østers": "oysters",
    "osters": "oysters",  # ASCII-folded fallback
    "blåskjell": "mussels",
    "blaskjell": "mussels",  # ASCII-folded fallback
    "krabbeskjell": "crab",
}

# Generic cut-of-meat fallbacks -- only take effect when no more specific compound
# above matched (longest-suffix-wins, see _translate_token()), e.g. "grillfilet" or
# "kyllingminuttfilet" which don't have their own dedicated entry.
_GENERIC_CUTS = {
    "filet": "fillet",
    "indrefilet": "tenderloin",
    "ytrefilet": "sirloin",
}

_DAIRY = {
    "ost": "cheese",
    # Guards the "ost" entry above against a real false positive found scanning
    # discounts.db: "Cruesli Solfrokost" (a granola/cereal brand) ends in "ost" purely
    # by coincidence of "frokost" (breakfast) -- same false-positive class as
    # "krem"/"iskrem" documented in grocery_discounts.py. "frokost" is longer than
    # "ost" so it wins the suffix match and correctly translates to "breakfast"
    # instead of wrongly injecting "cheese".
    "frokost": "breakfast",
    "melk": "milk",
    "rømme": "sour cream",
    "yoghurt": "yogurt",
    "kesam": "quark",
}

_VEGETABLES = {
    "løk": "onion",
    "lok": "onion",  # ASCII-folded fallback (task-seeded spelling)
    "hvitløk": "garlic",  # overrides generic "løk" -- garlic is "white onion", not onion
    "hvitlok": "garlic",  # ASCII-folded fallback
    "vårløk": "spring onion",
    "varlok": "spring onion",  # ASCII-folded fallback
    "purre": "leek",
    "potet": "potato",
    "poteter": "potato",
    "tomat": "tomato",
    "tomater": "tomato",
    "gulrot": "carrot",
    "gulrotter": "carrot",  # task-seeded plural spelling
    "gulrøtter": "carrot",  # standard Bokmål plural
    "blomkål": "cauliflower",
    "brokkoli": "broccoli",
    "brokkolini": "broccolini",
    "paprika": "bell pepper",
    "mais": "corn",
    "maiskolbe": "corn on the cob",
    "maiskolber": "corn on the cob",
}

_FRUIT = {
    "jordbær": "strawberry",
    "eple": "apple",
    "pære": "pear",
    "banan": "banana",
    "drue": "grape",
    "druer": "grape",
    "vannmelon": "watermelon",
    "fersken": "peach",
    "nektarin": "nectarine",
    "nektariner": "nectarine",
    "aprikos": "apricot",
    "aprikoser": "apricot",
    "plomme": "plum",
    "plommer": "plum",
    "sitron": "lemon",
    "appelsin": "orange",
    "appelsinjuice": "orange juice",
    "honningmelon": "honeydew melon",
    "avokado": "avocado",
}

_SAUSAGE_HAM = {
    "pølse": "sausage",
    "pølser": "sausage",
    "polse": "sausage",  # ASCII-folded fallback (task-seeded spelling)
    "polser": "sausage",  # ASCII-folded fallback
    "skinke": "ham",
    "spekeskinke": "cured ham",
}

_MISC_FOOD = {
    "brød": "bread",
    "salat": "lettuce",
    "isbergsalat": "iceberg lettuce",
}

# Preparation descriptors -- these modify a following food noun (a separate token, e.g.
# "BØKERØKTE SOMMERKOTELETTER" = "beech-smoked pork chops") rather than naming a food
# themselves, but per-token suffix matching (see _translate_token()) means they need
# their own entry or they're left as untranslated Norwegian noise attached to an
# otherwise-correct translation. Found live: "COOP GRILL PERFEKT BØKERØKTE
# SOMMERKOTELETTER" (this module's own root-cause example, see module docstring) was
# translating to "BØKERØKTE pork chop" -- the leftover "BØKERØKTE" token dragged the
# rerank score from the claimed +5.77/15-of-15-pass back down to -2.12/2-of-15-pass,
# since the reranker still sees a foreign word glued onto the English one. "røkt"/
# "røkte" as a suffix also correctly covers compounds like "einerrøkt" (juniper-smoked) --
# confirmed against every one of the 734 real discounts.db headings containing this
# suffix, all three real matches (bøkerøkte, einerrøkt, røkt) genuinely mean "smoked".
_PREPARATION = {
    "røkt": "smoked",
    "røkte": "smoked",
    "rokt": "smoked",  # ASCII-folded fallback
    "rokte": "smoked",  # ASCII-folded fallback
}

# Cut/shape descriptors -- same failure mode as _PREPARATION above (a Norwegian word
# glued onto an otherwise-correctly-translated food noun survives untranslated and drags
# the whole heading back into the low-rerank-score failure mode this module exists to
# fix), but these describe HOW a cut/piece is physically shaped or sized rather than how
# it was cooked. CONFIRMED LIVE BUG this group fixes (see module docstring): 'COOP
# STORFEKJOTT STRIMLET' translated to 'beef STRIMLET' -- 'strimlet' (cut into strips) had
# no entry, so it survived untranslated in ALL CAPS.
#
# None of these contain æ/ø/å, so (unlike _PREPARATION above) no ASCII-folded duplicate
# entries are needed.
#
# 'biter' needs a more specific override (longest-suffix-wins, same pattern as
# lammekoteletter/koteletter above): a bare 'biter' -> 'pieces' entry would otherwise
# silently DELETE the food identity out of a fused compound like 'MAISBITER' (corn
# bites/kernels) -- since a whole token gets replaced by its translation, "mais"+"biter"
# glued into one word would lose "mais" (corn) entirely once "biter" matches, which is
# worse than leaving it untranslated. The override, and bare 'biter' itself (moved to
# _EXACT_MATCH_ONLY_ENTRIES below -- see that section for why), are confirmed against
# every one of the 734 real discounts.db headings containing this suffix (only two:
# FREIA SMÅBITER and MAISBITER -- both fully accounted for by the override here; neither
# needs bare 'biter' to match as a suffix).
#
# 'grillskiver' needs its own override for the same reason: 4 of the 5 real headings
# containing "skiver" fuse it into "GRILLSKIVER" ("grill slices" -- thin cuts meant for
# grilling), not the standalone word -- confirmed via discounts.db
# (GRILLSKIVER/GRILLSKIVER MIKS/KALKUN GRILLSKIVER). Bare 'skiver' itself is moved to
# _EXACT_MATCH_ONLY_ENTRIES (it collides with the standalone English word "skiver"), but
# that would otherwise silently stop matching these real fused-compound headings -- this
# override, being a longer/more specific suffix match, catches them independently of
# whatever matching mode bare 'skiver' uses.
_CUT_DESCRIPTORS = {
    "strimlet": "strips",
    "strimler": "strips",
    "maisbiter": "corn kernels",  # overrides bare "biter" -- keeps "corn" identity
    "småbiter": "small pieces",  # overrides bare "biter" -- keeps "små" (small)
    "grillskiver": "grill slices",  # overrides bare "skiver" -- real fused compound
    "skivet": "slices",
    "terninger": "cubes",
    "terninget": "cubes",
    "fileter": "fillets",  # plural of the existing "filet" -> "fillet" in _GENERIC_CUTS
                           # above -- NOT reachable via that entry, since the Norwegian
                           # plural suffix "-er" is appended AFTER "filet", so "fileter"
                           # does not itself end in "filet" ("fileter".endswith("filet")
                           # is False -- last 5 chars are "leter") and needs its own key.
    "helt": "whole",
    "hele": "whole",
    "benfri": "boneless",
}

# 'hel' ("whole", bare/undeclined) is deliberately NOT a normal suffix entry above, even
# though it's the same underlying word as "helt"/"hele" -- confirmed via
# /usr/share/dict/words that a plain suffix match on the 3-letter "hel" would silently
# corrupt real, plausible-in-a-recipe-context English words that happen to share the same
# ending: "a BUSHEL of apples" or "BROTHEL" both end in "hel" and would get their entire
# final token replaced with "whole" ("a buswhole of apples"). "helt"/"hele" don't have
# this problem -- scanning the same dictionary for words ending in either turns up only
# obscure/archaic entries ("nephele", "unhele") with zero realistic collision risk -- so
# they stay ordinary suffix entries in _CUT_DESCRIPTORS above. "hel" instead requires the
# WHOLE token to equal "hel", never merely end with it -- exactly how it appears in the
# real data anyway ("HEL VANNMELON", "VANNMELON HEL" are both the standalone token "hel",
# never fused into a compound). See _translate_token()'s _EXACT_MATCH_ONLY handling.
#
# 'biter' -> 'pieces' and 'revet' -> 'grated' were caught by adversarial review for the
# same collision class as "hel": a plain suffix match would corrupt real English words
# ("a nail-BITER", "an ARBITER of taste", "a BREVET rank") the exact same way "clam" ->
# "lamb" and "ghost"/"defrost" -> "cheese" already did before those were scoped away by
# the normalize=False default (see pipeline.py) -- but since is_grocery_product is a
# client-supplied request flag, not a server-enforced classification, defense-in-depth
# means the raw function itself shouldn't carry an avoidable collision either. Both are
# confirmed via discounts.db to have zero real fused-compound usage that would need
# suffix matching (see _CUT_DESCRIPTORS/_PREP_STATE_DESCRIPTORS comments above for the
# fused-compound overrides that keep 'MAISBITER'/'SMÅBITER' working independently of
# this). 'skiver' -> 'slices' is exact-match-only for the identical reason (collides with
# the standalone English word "skiver") -- 'grillskiver' above is its own suffix entry so
# the real GRILLSKIVER/KALKUN GRILLSKIVER headings still translate correctly.
_EXACT_MATCH_ONLY_ENTRIES = {
    "hel": "whole",
    "biter": "pieces",
    "revet": "grated",
    "skiver": "slices",
}

# Preparation/cooking-state descriptors -- how the raw cut was seasoned, marinated, or
# cooked, as opposed to _CUT_DESCRIPTORS above (how it's physically shaped/sized). Same
# rationale and same longest-suffix-wins resolution as everywhere else in this file.
#
# 'malt' (a third common Norwegian word for "ground"/"minced" meat, alongside kjøttdeig's
# own dedicated "ground beef" mapping) is deliberately NOT included here, despite being
# suggested during scoping: scanning discounts.db turned up a real, confirmed
# false-positive collision -- "FILTERMALT KJELDSBERG" is a filter-ground COFFEE product
# (Kjeldsberg is a Norwegian coffee brand), not meat, and ends in "malt" -- a bare "malt"
# entry would wrongly inject "minced" into a coffee listing. 'malt' is also itself an
# ordinary English word (malt vinegar, malted milk, single malt whisky), so it would
# additionally corrupt legitimate English free text fed through this function -- a worse
# version of the exact class of bug ADVERSARIAL_ENGLISH_INGREDIENTS (see test_pipeline.py)
# exists to catch. 'kvernet' (a distinct, unambiguous Norwegian-only word for the same
# "ground/minced" concept, from "kvern" = mill/grinder) is used instead -- no such
# collision found against either discounts.db or /usr/share/dict/words.
_PREP_STATE_DESCRIPTORS = {
    "panert": "breaded",
    "panerte": "breaded",
    "marinert": "marinated",
    "marinerte": "marinated",
    "grillet": "grilled",
    "grillmarinert": "grilled",  # overrides bare "marinert" -- longest-suffix-wins,
                                 # same pattern as lammekoteletter/koteletter above
    "kvernet": "minced",
    # "revet" ("grated") moved to _EXACT_MATCH_ONLY_ENTRIES -- see that section.
    "krydret": "seasoned",  # real example: "GRILLRIBBE KRYDRET" -> seasoned pork ribs
}

GROCERY_GLOSSARY: Dict[str, str] = _glossary(
    _PORK, _BEEF, _LAMB, _CHICKEN, _FISH_SEAFOOD, _GENERIC_CUTS, _DAIRY,
    _VEGETABLES, _FRUIT, _SAUSAGE_HAM, _MISC_FOOD, _PREPARATION,
    _CUT_DESCRIPTORS, _EXACT_MATCH_ONLY_ENTRIES, _PREP_STATE_DESCRIPTORS,
)

# Keys in GROCERY_GLOSSARY that must match a token EXACTLY, never merely as a suffix --
# see _EXACT_MATCH_ONLY_ENTRIES above for why "hel" needs this. Kept as a separate
# frozenset (rather than, say, a sentinel value in GROCERY_GLOSSARY itself) so the
# glossary stays a plain str->str dict everywhere else in this file.
_EXACT_MATCH_ONLY = frozenset(_EXACT_MATCH_ONLY_ENTRIES)

# Retailer/brand names -- derived from grocery_discounts.NORWEGIAN_STORES (imported, not
# duplicated) split into individual words, since a heading like "REMA 1000 KJØTTDEIG..."
# tokenizes "Rema 1000" into separate "rema"/"1000" tokens. "coop" is added explicitly
# too (not just implied by "Coop Prix" splitting to "coop"/"prix") because plenty of real
# headings use it completely bare -- "COOP GRILL PERFEKT...", "COOP KYLLINGFILET 690G" --
# not just as part of the full "Coop Prix" dealer name.
#
# "Kiwi" is excluded from this derived set even though it's a NORWEGIAN_STORES key:
# scanning discounts.db turned up real headings where "kiwi" is the FRUIT, not the store
# ("KIWI GUL 3PK", "...JORDBÆR & KIWI/SITRON") and none where it's used as a bare
# store-brand prefix the way "COOP ..." is -- so stripping it would silently delete a
# real food word for no corresponding benefit in this dataset.
_STORE_NOISE_WORDS = {word.lower() for store_name in NORWEGIAN_STORES for word in store_name.split()} - {"kiwi"}

# Marketing/sales-unit filler that carries no dish-identity signal (confirmed live: these
# are the exact words sitting between the retailer name and the actual food noun in
# headings like "COOP GRILL PERFEKT BØKERØKTE SOMMERKOTELETTER"). løsvekt/løs/vekt (and
# their ASCII-folded/split forms) all describe loose-weight/scale-priced selling, not the
# food itself -- e.g. "REKER I LØSVEKT" and "POLAR REKER I LØS VEKT" are the same concept
# spelled as one word vs. two.
NOISE_TOKENS = _STORE_NOISE_WORDS | {
    "coop",
    "grill",
    "perfekt",
    "losvekt", "løsvekt",
    "løs", "los",
    "vekt",
    "fersk", "ferske",
    "frossen", "frosne", "frosset",
}

# Packaging/size metadata -- weights, volumes, and multipack counts -- is never
# dish-relevant, so it's stripped from the raw text before tokenizing (e.g. "690G",
# "250 G", "1 L", "20 X 330 ML", "2-pk.", "6PK"). The (?!\w) after the unit is load-
# bearing, not decorative: without it, a real heading like "4+1 GASSGRILL" gets its
# trailing bare number ("1") + space + unit-letter match greedily eat into the START of
# the following unrelated word ("G" of "GASSGRILL"), mangling it to "ASSGRILL" -- (?!\w)
# requires the unit to actually end there (followed by non-word/end-of-string), not
# continue into more letters.
_PACKAGE_SIZE_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?[\s-]*(?:x[\s-]*\d+(?:[.,]\d+)?[\s-]*)?(?:kg|g|ml|cl|dl|l|stk|pk)(?!\w)\.?",
    re.IGNORECASE,
)

# A bare leftover number (or percentage, e.g. the "14" in "KJØTTDEIG STORFE 14%" meaning
# 14% fat) is pure packaging/spec metadata once any attached unit has already been
# stripped above -- never dish-relevant either.
_PURE_NUMBER_RE = re.compile(r"^\d+(?:[.,]\d+)?%?$")

_TOKEN_RE = re.compile(r"[^\s\-/]+")
_TOKEN_PUNCT = ".,;:()&"

# Two-word preparation phrases -- "uten bein"/"uten ben" (without bone) and "med
# bein"/"med ben" (with bone; "bein"/"ben" are both standard Bokmål spellings, not a
# diacritic variant) can't be caught by the per-token suffix matching above, since
# they're two separate whitespace-separated tokens: "uten"/"med" don't carry food-
# identity meaning on their own, and bare "bein"/"ben" alone is too short/generic a
# suffix to add safely by itself (same class of risk as bare "hel" above -- "ben" in
# particular is also the common English name "Ben"). Handled instead as a whole-phrase
# substitution up front, the same technique _PACKAGE_SIZE_RE already uses for packaging
# metadata.
#
# Not confirmed against any real discounts.db heading -- 0 of the 734 real product names
# contain either word -- but added defensively per the same investigation that surfaced
# the strimlet gap, since it's the same preparation-descriptor category and the exact
# two-word Norwegian phrase has no plausible English collision.
_BONELESS_PHRASE_RE = re.compile(r"\buten[\s-]+be(?:in|n)\b", re.IGNORECASE)
_BONE_IN_PHRASE_RE = re.compile(r"\bmed[\s-]+be(?:in|n)\b", re.IGNORECASE)


def _translate_token(core: str) -> Optional[str]:
    """Returns the English translation for a lowercased, punctuation-stripped token, or
    None if nothing in the glossary matches. Norwegian compounds put the head noun last
    (kyllingfilet = kylling+filet), so matching is a SUFFIX check per token -- and when
    more than one glossary key matches (e.g. "lammekoteletter" ends in both
    "koteletter" and its own more specific "lammekoteletter"), the LONGEST matching key
    wins, since it's always the more specific one.

    Keys in _EXACT_MATCH_ONLY are the one exception: the token must equal the key
    exactly, not merely end with it (see _EXACT_MATCH_ONLY_ENTRIES for why "hel" needs
    this -- a plain suffix match would corrupt real English words like "bushel")."""
    best_key = None
    for key in GROCERY_GLOSSARY:
        is_match = core == key if key in _EXACT_MATCH_ONLY else core.endswith(key)
        if is_match and (best_key is None or len(key) > len(best_key)):
            best_key = key
    return GROCERY_GLOSSARY[best_key] if best_key is not None else None


def _is_noise_token(core: str) -> bool:
    return any(core.endswith(kw) for kw in NOISE_TOKENS)


def normalize_grocery_heading(heading: str) -> str:
    """Turns a raw Norwegian grocery/flyer product heading into a cleaned-up, mostly-
    English description of the actual food -- suitable for both the retrieval query and
    the LLM generation prompt. Strips retailer/brand names and marketing filler
    (NOISE_TOKENS), strips packaging/size metadata (weights, volumes, multipack counts),
    and translates known Norwegian food-noun suffixes via GROCERY_GLOSSARY.

    Plain English input passes through completely unchanged: every span of the original
    string that isn't recognized as noise or a glossary hit is copied through verbatim
    (not reconstructed from re-joined tokens), so casing, punctuation, and spacing on an
    already-English ingredient string like "chicken, tomatoes, onions" survive exactly
    as given.

    Never returns an empty string -- if literally everything in the heading turns out to
    be noise, the original heading is returned as-is so the caller always has *something*
    to search/generate with.
    """
    if not heading or not heading.strip():
        return heading

    text = _PACKAGE_SIZE_RE.sub("", heading)
    text = _BONELESS_PHRASE_RE.sub("boneless", text)
    text = _BONE_IN_PHRASE_RE.sub("bone-in", text)

    pieces = []
    pos = 0
    changed = False
    for m in _TOKEN_RE.finditer(text):
        pieces.append(text[pos:m.start()])  # separator chars, copied verbatim
        raw = m.group(0)
        core = raw.strip(_TOKEN_PUNCT).lower()

        if not core:
            pieces.append(raw)
        elif _PURE_NUMBER_RE.match(core) or _is_noise_token(core):
            changed = True  # drop this token entirely
        else:
            translation = _translate_token(core)
            if translation is not None:
                pieces.append(translation)
                changed = True
            else:
                pieces.append(raw)
        pos = m.end()
    pieces.append(text[pos:])

    if text != heading:
        changed = True

    if not changed:
        return heading

    result = "".join(pieces)
    # Translating adjacent tokens can produce an immediate duplicate word, e.g. "SVIN
    # GRILLRIBBE" -> "pork" + "pork ribs" = "pork pork ribs" -- collapse those (only ever
    # touches output built above, never plain-passthrough text, since we're already past
    # the `if not changed` early return).
    result = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", result, flags=re.IGNORECASE)
    result = re.sub(r"[ \t]{2,}", " ", result).strip(" \t-/")
    return result or heading
