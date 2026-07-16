"""EN -> Norwegian (Bokmål) translation via a dedicated NMT model -- deliberately NOT
a chat/instruction LLM. Confirmed live (2026-07-15): a general-purpose chat model
(qwen3:8b) asked to translate a real, correct recipe fabricated non-existent Norwegian
words ("brynje" for breadcrumbs, "ingervoks" for ginger, "nøttkrem" for nutmeg) even
when explicitly told to treat the source as ground truth and not deviate from it. A
dedicated MT model trained on millions of real parallel sentence pairs doesn't have
that failure mode -- confirmed on the exact same test case, correctly producing
"brødsmuler", "malt ingefær", "muskatnøtt". The fine-tuned recipe model (toriko3) was
also tried and rejected for this: it ignores a Norwegian instruction outright,
confirmed even with the instruction baked into a fresh Modelfile's own SYSTEM field,
not just a runtime prompt -- see project notes.

Helsinki-NLP/opus-mt-tc-big-en-gmq is a multi-target model covering the North
Germanic languages (Danish, Faroese, Icelandic, Norwegian Bokmål/Nynorsk, Swedish) --
selecting Norwegian Bokmål specifically requires a ">>nob<<" tag prepended to each
input sentence (a Tatoeba Challenge multi-target-model convention taken directly from
the model card's "valid target language labels", not something this module invented).

Sentence-level only: confirmed live that feeding it a whole Markdown-formatted recipe
in one shot ("### " headings, "**bold**", multi-line lists) badly mangles structure --
bold markers get split with stray spaces, newlines collapse into a run-on paragraph,
and translation quality regresses (a word translated correctly in isolation was left
untranslated once buried in that noise). This module has no opinion about recipe
structure -- it only translates whatever strings it's given, one span at a time in a
single batched call. Callers must extract clean prose spans first (title, ingredients
block, instructions block) -- see pipeline.py's _translate_recipe_text()."""

import logging
from typing import List

logger = logging.getLogger(__name__)

MODEL_NAME = "Helsinki-NLP/opus-mt-tc-big-en-gmq"
NORWEGIAN_BOKMAL_TAG = ">>nob<<"


class RecipeTranslator:
    """Lazily loads the MarianMT model on first use, not at import/construction time
    -- constructing this instance is cheap (matches TextEmbedder/CrossEncoderReranker's
    lazy-load pattern elsewhere in this codebase), only the first
    translate_to_norwegian() call pays the model-load cost."""

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self._tokenizer = None
        self._model = None

    def _ensure_loaded(self):
        if self._model is not None:
            return
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        logger.info(f"Loading translation model {self.model_name}...")
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)

    def translate_to_norwegian(self, texts: List[str], max_length: int = 512) -> List[str]:
        """Translates every string in texts in one batched call. Returns "" for any
        blank/whitespace-only input without sending it to the model (Marian expects
        non-empty input); order and length of the result always matches texts."""
        if not texts:
            return []

        blank_mask = [not t or not t.strip() for t in texts]
        non_blank = [t for t, blank in zip(texts, blank_mask) if not blank]

        translated_non_blank: List[str] = []
        if non_blank:
            self._ensure_loaded()
            tagged = [f"{NORWEGIAN_BOKMAL_TAG} {t}" for t in non_blank]
            inputs = self._tokenizer(
                tagged, return_tensors="pt", padding=True, truncation=True, max_length=max_length
            )
            output_ids = self._model.generate(**inputs, max_length=max_length)
            translated_non_blank = [
                self._tokenizer.decode(ids, skip_special_tokens=True) for ids in output_ids
            ]

        result: List[str] = []
        it = iter(translated_non_blank)
        for blank in blank_mask:
            result.append("" if blank else next(it))
        return result
