"""Fuzzy-corrects query words against the recipe corpus's own vocabulary — fixes the
"briyani" vs "biryani" gap generically instead of hardcoding known spelling variants.

BM25 does exact token matching, so a misspelled dish name gets literally zero keyword
overlap with the correct spelling even when it's common and well-covered in the corpus.
This builds a vocabulary from every word that appears in a recipe title, and for any
query word not in that vocabulary, substitutes the closest fuzzy match — if one exists
close enough to plausibly be a typo/spelling variant rather than a genuinely different word.
"""

import difflib
import re
from typing import Iterable, List

_STOPWORDS = {
    "recipe", "recipes", "with", "and", "the", "a", "an", "of", "in", "for", "style",
    "how", "do", "make", "what", "can", "i", "to", "or", "you",
}

# Below this ratio, a "correction" is more likely to mangle a real word (garnish -> garish)
# than fix an actual typo — better to leave the query alone than guess wrong.
_MIN_MATCH_RATIO = 0.82


def build_vocabulary(titles: Iterable[str]) -> set:
    vocab = set()
    for title in titles:
        for word in re.findall(r"[a-zA-Z]+", title.lower()):
            if len(word) > 3 and word not in _STOPWORDS:
                vocab.add(word)
    return vocab


def normalize_query(query: str, vocabulary: set) -> str:
    """Leaves the query untouched unless a word looks like a near-miss of a real,
    well-represented corpus term."""
    words = query.split()
    corrected: List[str] = []
    changed = False

    for word in words:
        bare = re.sub(r"[^a-zA-Z]", "", word).lower()
        # Short words are disproportionately likely to be ordinary English (what, make,
        # with, corn...) rather than a misspelled dish name — the vocabulary is built
        # only from recipe titles, so it doesn't "know" common query connector words and
        # will happily "correct" them into something else short and title-like instead.
        if not bare or bare in vocabulary or len(bare) <= 4:
            corrected.append(word)
            continue

        matches = difflib.get_close_matches(bare, vocabulary, n=1, cutoff=_MIN_MATCH_RATIO)
        if matches:
            corrected.append(matches[0])
            changed = True
        else:
            corrected.append(word)

    return " ".join(corrected) if changed else query
