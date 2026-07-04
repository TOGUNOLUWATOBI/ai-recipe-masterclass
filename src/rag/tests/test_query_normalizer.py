"""Tests for query_normalizer.py — the most important test here is the regression
guard: an earlier version of this normalizer mangled ordinary English query words
("what" -> "wheat", "make" -> "maker", "with" -> "witch") because the vocabulary is
built only from recipe titles, which don't contain common sentence connector words."""

from rag.query_normalizer import build_vocabulary, normalize_query

VOCAB = build_vocabulary([
    "Jollof Rice", "Egusi Soup", "Chicken Curry", "Biryani Masala Powder Recipe",
    "Norwegian Butter Cookies",
])


def test_normalize_query_leaves_known_words_unchanged():
    assert normalize_query("jollof rice", VOCAB) == "jollof rice"


def test_normalize_query_fixes_food_word_typo():
    assert normalize_query("chiken curry", VOCAB) == "chicken curry"


def test_normalize_query_does_not_mangle_common_english_words():
    """Regression test for the exact bug found this session: 4-letter connector words
    ("what", "make", "with") are not recipe-title vocabulary, but they are correct,
    ordinary English — not typos — and must not get "corrected" into something else."""
    query = "what can i make with chicken and rice"
    assert normalize_query(query, VOCAB) == query


def test_normalize_query_leaves_genuinely_uncovered_words_alone():
    """No vocabulary entry is close enough to "ribbe" to safely guess at — leaving it
    unchanged is correct; guessing wrong would be worse than not correcting at all."""
    query = "norwegian ribbe"
    assert normalize_query(query, VOCAB) == query


def test_build_vocabulary_excludes_stopwords_and_short_words():
    vocab = build_vocabulary(["The Best Recipe With A Cat"])
    assert "with" not in vocab
    assert "the" not in vocab
    assert "a" not in vocab
    assert "best" in vocab
    assert "recipe" not in vocab  # explicit stopword — appears in nearly every title
