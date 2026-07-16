"""Tests for translator.py's RecipeTranslator -- the surrounding logic (blank-input
handling, the ">>nob<<" target-language tagging, batching, lazy model loading) tested
against a fake tokenizer/model so these run fast and offline, without downloading the
real ~600MB Helsinki-NLP/opus-mt-tc-big-en-gmq weights. The model's own translation
quality was validated separately, live, against real recipe text (see project notes
and translator.py's module docstring) -- these tests cover this module's own code."""

from rag.translator import NORWEGIAN_BOKMAL_TAG, RecipeTranslator


class _FakeTokenizer:
    def __init__(self):
        self.calls = []

    def __call__(self, texts, return_tensors=None, padding=None, truncation=None, max_length=None):
        self.calls.append(list(texts))
        return {"texts": list(texts)}

    def decode(self, item, skip_special_tokens=True):
        return item


class _FakeModel:
    def generate(self, texts=None, max_length=None):
        # Strips the tag and uppercases -- a deterministic, easy-to-assert-on stand-in
        # for real translation, just enough to prove the tag was actually prepended.
        return [t.replace(f"{NORWEGIAN_BOKMAL_TAG} ", "").upper() for t in texts]


def _translator_with_fakes():
    translator = RecipeTranslator()
    fake_tokenizer = _FakeTokenizer()
    translator._tokenizer = fake_tokenizer
    translator._model = _FakeModel()
    return translator, fake_tokenizer


def test_translate_to_norwegian_returns_empty_list_for_empty_input():
    translator, tokenizer = _translator_with_fakes()
    assert translator.translate_to_norwegian([]) == []
    assert tokenizer.calls == []


def test_translate_to_norwegian_tags_each_input_with_the_bokmal_target_tag():
    translator, tokenizer = _translator_with_fakes()

    translator.translate_to_norwegian(["chicken", "rice"])

    assert tokenizer.calls == [[f"{NORWEGIAN_BOKMAL_TAG} chicken", f"{NORWEGIAN_BOKMAL_TAG} rice"]]


def test_translate_to_norwegian_returns_translations_in_order():
    translator, _ = _translator_with_fakes()

    result = translator.translate_to_norwegian(["chicken", "rice"])

    assert result == ["CHICKEN", "RICE"]


def test_translate_to_norwegian_preserves_blank_entries_without_sending_them_to_the_model():
    translator, tokenizer = _translator_with_fakes()

    result = translator.translate_to_norwegian(["chicken", "", "rice", "   "])

    assert result == ["CHICKEN", "", "RICE", ""]
    # Only the two non-blank entries should ever reach the model.
    assert tokenizer.calls == [[f"{NORWEGIAN_BOKMAL_TAG} chicken", f"{NORWEGIAN_BOKMAL_TAG} rice"]]


def test_translate_to_norwegian_returns_all_blanks_without_loading_the_model():
    translator = RecipeTranslator()  # deliberately not pre-loaded with fakes

    result = translator.translate_to_norwegian(["", "   "])

    assert result == ["", ""]
    assert translator._model is None  # _ensure_loaded() never ran


def test_translator_loads_the_model_only_once_across_multiple_translate_calls(monkeypatch):
    """Regression guard on the real _ensure_loaded() (not the fake stand-in the other
    tests inject) -- loading Helsinki-NLP/opus-mt-tc-big-en-gmq is expensive, so a
    second translate_to_norwegian() call must reuse the already-loaded model/tokenizer
    rather than reloading from scratch."""
    import transformers

    tokenizer_calls = []
    model_calls = []
    monkeypatch.setattr(
        transformers.AutoTokenizer, "from_pretrained",
        classmethod(lambda cls, name: tokenizer_calls.append(name) or _FakeTokenizer()),
    )
    monkeypatch.setattr(
        transformers.AutoModelForSeq2SeqLM, "from_pretrained",
        classmethod(lambda cls, name: model_calls.append(name) or _FakeModel()),
    )

    translator = RecipeTranslator()
    assert translator._model is None

    translator.translate_to_norwegian(["chicken"])
    translator.translate_to_norwegian(["rice"])

    assert len(tokenizer_calls) == 1
    assert len(model_calls) == 1
