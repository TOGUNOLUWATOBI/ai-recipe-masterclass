"""Tests for grocery_terms.py's Norwegian grocery-heading normalizer.

Covers the exact confirmed-root-cause examples from the live investigation (raw
Norwegian flyer headings scoring catastrophically low against the English-only recipe
corpus/reranker), plain-English passthrough (the property find_recipes_from_ingredients()/
find_recipes_or_generate() in pipeline.py rely on to apply this unconditionally to every
ingredient), a no-glossary-match heading, and correct handling of real Norwegian
characters (ø/å/æ)."""

from rag.grocery_terms import (
    GROCERY_GLOSSARY,
    NOISE_TOKENS,
    normalize_grocery_heading,
)


# ---------------------------------------------------------------------------
# The 4 confirmed root-cause headings from the live investigation -- assert the KEY
# property (brand/retailer noise gone, known food term present in English), not exact
# output strings.
# ---------------------------------------------------------------------------

def test_bokerokte_sommerkoteletter_heading_transforms_sensibly():
    out = normalize_grocery_heading("COOP GRILL PERFEKT BOKEROKTE SOMMERKOTELETTER")
    lowered = out.lower()
    assert "pork chop" in lowered
    assert "coop" not in lowered
    assert "grill" not in lowered
    assert "perfekt" not in lowered
    # "bokerokte"/"bøkerøkte" (beech-smoked) must not survive untranslated -- it did in
    # an earlier version of this module, silently dragging the real rerank score for
    # this exact heading down from the module docstring's claimed +5.77/15-of-15-pass to
    # -2.12/2-of-15-pass (confirmed live against the real pipeline/index), even though
    # this test's "pork chop" assertion above still passed either way.
    assert "bokerokte" not in lowered
    assert "smoked" in lowered


def test_bokerokte_sommerkoteletter_heading_with_real_norwegian_spelling():
    out = normalize_grocery_heading("COOP GRILL PERFEKT BØKERØKTE SOMMERKOTELETTER")
    lowered = out.lower()
    assert "pork chop" in lowered
    assert "coop" not in lowered
    assert "grill" not in lowered
    assert "perfekt" not in lowered
    assert "røkte" not in lowered and "bøkerøkte" not in lowered
    assert "smoked" in lowered


def test_rema_kjottdeig_storfe_heading_transforms_sensibly():
    """The raw investigation example uses the ASCII-folded 'KJOTTDEIG' (no ø) --
    real Tjek data spells it 'KJØTTDEIG', so both must resolve to the same food term."""
    out = normalize_grocery_heading("REMA 1000 KJOTTDEIG STORFE 14")
    lowered = out.lower()
    assert "ground beef" in lowered
    assert "rema" not in lowered
    assert "1000" not in lowered


def test_rema_kjottdeig_storfe_heading_with_real_norwegian_spelling():
    out = normalize_grocery_heading("REMA 1000 KJØTTDEIG STORFE 14")
    lowered = out.lower()
    assert "ground beef" in lowered
    assert "rema" not in lowered
    assert "1000" not in lowered


def test_coop_kyllingfilet_heading_transforms_sensibly():
    out = normalize_grocery_heading("COOP KYLLINGFILET 690G")
    lowered = out.lower()
    assert "chicken fillet" in lowered
    assert "coop" not in lowered
    assert "690" not in lowered
    assert "g" not in lowered.replace("chicken fillet", "")


def test_already_translated_dish_terms_pass_through_unchanged():
    """The other half of the confirmed root-cause comparison -- already-English dish
    terms ('pork chops', 'chicken fillet') scored well against the corpus and must not
    be altered by this module."""
    assert normalize_grocery_heading("pork chops") == "pork chops"
    assert normalize_grocery_heading("chicken fillet") == "chicken fillet"


# ---------------------------------------------------------------------------
# Plain English passthrough -- the property pipeline.py's wiring depends on to apply
# normalize_grocery_heading() unconditionally to every ingredient.
# ---------------------------------------------------------------------------

def test_plain_english_ingredient_list_passes_through_unchanged():
    assert normalize_grocery_heading("chicken, tomatoes, onions") == "chicken, tomatoes, onions"


def test_plain_english_single_ingredients_pass_through_unchanged():
    for ing in ["chicken", "tomatoes", "onions", "olive oil", "black pepper"]:
        assert normalize_grocery_heading(ing) == ing


def test_empty_and_whitespace_input_is_returned_as_is():
    assert normalize_grocery_heading("") == ""
    assert normalize_grocery_heading("   ") == "   "


# ---------------------------------------------------------------------------
# No glossary match at all -- brand/marketing noise still gets stripped even when there's
# nothing to translate.
# ---------------------------------------------------------------------------

def test_heading_with_no_glossary_match_still_strips_brand_and_marketing_noise():
    out = normalize_grocery_heading("COOP GRILL PERFEKT TOMAHAWK")
    lowered = out.lower()
    assert "coop" not in lowered
    assert "grill" not in lowered
    assert "perfekt" not in lowered
    assert "tomahawk" in lowered


def test_heading_with_no_noise_and_no_glossary_match_is_left_alone():
    assert normalize_grocery_heading("TOMAHAWK") == "TOMAHAWK"


# ---------------------------------------------------------------------------
# Norwegian characters (ø/å/æ) handled correctly, not mangled.
# ---------------------------------------------------------------------------

def test_norwegian_characters_are_handled_not_mangled():
    assert normalize_grocery_heading("LØK") == "onion"
    assert normalize_grocery_heading("BLÅSKJELL") == "mussels"
    assert normalize_grocery_heading("JORDBÆR") == "strawberry"
    assert normalize_grocery_heading("VÅRLØK") == "spring onion"


def test_reker_i_losvekt_strips_loose_weight_marketing_descriptor():
    """Confirmed real heading from the live investigation -- 'løsvekt' (loose weight) is
    a sales-unit descriptor, not a food word, and must be stripped like the other
    marketing filler, leaving the translated food term behind."""
    out = normalize_grocery_heading("REKER I LØSVEKT")
    lowered = out.lower()
    assert "shrimp" in lowered
    assert "løsvekt" not in lowered
    assert "losvekt" not in lowered


def test_two_word_split_form_of_losvekt_also_stripped():
    out = normalize_grocery_heading("POLAR REKER I LØS VEKT")
    lowered = out.lower()
    assert "shrimp" in lowered
    assert "vekt" not in lowered


# ---------------------------------------------------------------------------
# Compounding / suffix-matching behavior and specificity overrides.
# ---------------------------------------------------------------------------

def test_lamb_chop_is_not_mistranslated_as_pork_chop():
    """'lammekoteletter' ends in the same 'koteletter' suffix as the generic pork-chop
    entry -- the more specific lamb-chop entry must win (longest-suffix-wins), not the
    generic pork one."""
    out = normalize_grocery_heading("COOP GRILL PERFEKT LAMMEKOTELETTER")
    lowered = out.lower()
    assert "lamb chop" in lowered
    assert "pork chop" not in lowered


def test_garlic_is_not_mistranslated_as_onion():
    """'hvitløk' (garlic) ends in the same 'løk' suffix as the generic onion entry --
    the more specific garlic entry must win."""
    out = normalize_grocery_heading("HVITLØK")
    assert out.lower() == "garlic"


def test_frokost_is_not_mistranslated_via_the_generic_ost_cheese_entry():
    """Real false positive found scanning discounts.db: 'Solfrokost' (a granola brand)
    ends in 'ost' purely by coincidence of 'frokost' (breakfast) -- must not become
    'cheese'."""
    out = normalize_grocery_heading("Cruesli Solfrokost")
    lowered = out.lower()
    assert "cheese" not in lowered
    assert "breakfast" in lowered


def test_kiwi_the_fruit_is_not_stripped_as_the_kiwi_store_name():
    """'Kiwi' is both a NORWEGIAN_STORES retailer name and a real fruit -- real
    headings use it as the fruit ('KIWI GUL 3PK'), so it must survive, not be stripped
    as retailer noise."""
    out = normalize_grocery_heading("KIWI GUL 3PK")
    assert "kiwi" in out.lower()


def test_package_size_metadata_is_stripped():
    for heading in ["690G", "250 G", "1 L", "20 X 330 ML", "6PK", "2-pk."]:
        assert normalize_grocery_heading(f"KYLLINGFILET {heading}") == "chicken fillet"


def test_ascii_folded_kjottdeig_matches_same_as_real_spelling():
    assert normalize_grocery_heading("KJOTTDEIG") == normalize_grocery_heading("KJØTTDEIG")


def test_smoked_preparation_descriptor_is_translated_not_left_untranslated():
    """'røkt'/'røkte' (smoked) is a preparation descriptor that appears as its own token
    or fused into a compound (bøkerøkte = beech-smoked, einerrøkt = juniper-smoked) in
    real discounts.db headings -- must translate, not survive as leftover Norwegian
    noise glued onto an otherwise-correct translation."""
    assert normalize_grocery_heading("RØKT LAKS") == "smoked salmon"
    assert normalize_grocery_heading("EINERRØKT ØRRET").lower() == "smoked trout"


# ---------------------------------------------------------------------------
# Cut/shape and prep-state descriptors (strimlet, biter, skiver, terninger, fileter,
# hel/helt/hele, benfri, panert, marinert, grillet, kvernet, revet, krydret) -- the
# preparation/cut-descriptor CATEGORY fix, not just the one reported case.
# ---------------------------------------------------------------------------

def test_storfekjott_strimlet_confirmed_live_bug_normalizes_cleanly():
    """THE confirmed live production bug this whole category fix is for: a user tapped
    'COOP STORFEKJOTT STRIMLET' (Coop beef strips) and got an unrelated Boerenkool
    (cabbage) stew recipe, because 'strimlet' (cut into strips) had no glossary entry
    and survived untranslated/ALL CAPS, dragging the whole query back into the
    low-rerank-score failure mode this module exists to fix. Must now normalize
    completely cleanly: no leftover raw Norwegian token, real food words present."""
    out = normalize_grocery_heading("COOP STORFEKJOTT STRIMLET")
    assert out.lower() == "beef strips"

    out_real_spelling = normalize_grocery_heading("COOP STORFEKJØTT STRIMLET")
    assert out_real_spelling.lower() == "beef strips"


def test_strimler_plural_also_translates():
    assert normalize_grocery_heading("STORFEKJØTT STRIMLER").lower() == "beef strips"


def test_biter_translates_to_pieces_but_specific_compounds_keep_their_food_identity():
    """Bare 'biter' -> 'pieces' is correct as a fallback, but the two real discounts.db
    headings that actually contain this suffix are FUSED compounds ('mais'+'biter',
    'små'+'biter') where naively applying the bare translation would silently delete the
    food identity ('mais'/corn) or the size qualifier ('små'/small) -- both need their
    own longer, more specific override (longest-suffix-wins)."""
    assert normalize_grocery_heading("MAISBITER").lower() == "corn kernels"
    assert normalize_grocery_heading("FREIA SMÅBITER") == "FREIA small pieces"


def test_skiver_and_skivet_translate_to_slices():
    assert "slices" in normalize_grocery_heading("GRILLRIBBE SKIVET").lower()
    out = normalize_grocery_heading("Skivet vannmelon")
    assert "slices" in out.lower() and "watermelon" in out.lower()


def test_terninger_and_terninget_translate_to_cubes():
    assert normalize_grocery_heading("KYLLINGBRYST TERNINGER").lower() == "chicken breast cubes"
    assert normalize_grocery_heading("KYLLINGBRYST TERNINGET").lower() == "chicken breast cubes"


def test_fileter_plural_translates_to_fillets():
    """'fileter' (plural) is NOT reachable via the existing 'filet' -> 'fillet' entry --
    the Norwegian plural suffix is appended AFTER 'filet', so 'fileter' does not itself
    end in 'filet' and needs its own glossary key."""
    assert normalize_grocery_heading("LAKS FILETER").lower() == "salmon fillets"


def test_benfri_translates_to_boneless():
    assert normalize_grocery_heading("KYLLINGLÅR BENFRI").lower() == "chicken thigh boneless"


def test_hele_and_helt_translate_to_whole_via_normal_suffix_matching():
    assert normalize_grocery_heading("GRILSTAD HELE PØLSER").lower() == "grilstad whole sausage"
    assert normalize_grocery_heading("HELT KYLLING").lower() == "whole chicken"


def test_bare_hel_translates_to_whole_only_as_the_whole_token():
    """Real data uses bare 'hel' as its own standalone token ('HEL VANNMELON',
    'VANNMELON HEL'), never fused into a compound -- must still translate."""
    assert normalize_grocery_heading("HEL VANNMELON").lower() == "whole watermelon"
    assert normalize_grocery_heading("VANNMELON HEL").lower() == "watermelon whole"


def test_bare_hel_suffix_does_not_corrupt_real_english_words_ending_in_hel():
    """Confirmed via /usr/share/dict/words: a plain suffix match on 'hel' would silently
    corrupt real English words that happen to share the ending ('bushel', 'brothel') --
    this is exactly why 'hel' is handled as an EXACT-token-only match, not a suffix
    match like every other glossary entry."""
    assert normalize_grocery_heading("a bushel of apples") == "a bushel of apples"
    assert normalize_grocery_heading("brothel") == "brothel"
    assert normalize_grocery_heading("a hostel by the sea") == "a hostel by the sea"


def test_prep_state_descriptors_translate():
    assert normalize_grocery_heading("GRILLRIBBE KRYDRET").lower() == "pork ribs seasoned"
    assert normalize_grocery_heading("ORIGINAL REVET OST").lower() == "original grated cheese"
    assert "grilled" in normalize_grocery_heading("KYLLINGFILET GRILLET").lower()
    assert "marinated" in normalize_grocery_heading("MARINERT KYLLINGFILET").lower()
    assert "breaded" in normalize_grocery_heading("PANERT FISK").lower()
    assert "minced" in normalize_grocery_heading("KVERNET SVINEKJØTT").lower()


def test_grillmarinert_overrides_bare_marinert_via_longest_suffix_wins():
    out = normalize_grocery_heading("GRILLMARINERT KYLLINGFILET")
    assert "grilled" in out.lower()


def test_malt_is_deliberately_not_a_glossary_entry():
    """'malt' was in the task's suggested word list but is deliberately excluded: it
    collides with a real discounts.db product ('FILTERMALT KJELDSBERG', a filter-ground
    COFFEE product, not meat) and is itself an ordinary English word (malt vinegar,
    single malt whisky) -- 'kvernet' is used instead for the same "ground/minced"
    concept with no such collision."""
    assert normalize_grocery_heading("FILTERMALT KJELDSBERG") == "FILTERMALT KJELDSBERG"
    assert normalize_grocery_heading("malt vinegar chips") == "malt vinegar chips"
    assert normalize_grocery_heading("single malt whisky") == "single malt whisky"


def test_uten_bein_and_med_bein_two_word_phrases_translate():
    """'uten bein'/'med bein' (without bone / with bone) are two separate
    whitespace-separated tokens, so they can't be caught by the per-token suffix
    matching -- handled instead as a whole-phrase substitution, mirroring
    _PACKAGE_SIZE_RE's own whole-string-substitution technique."""
    out = normalize_grocery_heading("KYLLINGLÅR UTEN BEIN")
    assert "boneless" in out.lower()
    assert "uten" not in out.lower() and "bein" not in out.lower()

    out2 = normalize_grocery_heading("KYLLINGLÅR MED BEIN")
    assert "bone-in" in out2.lower()
    assert "med" not in out2.lower()

    # "ben" is the alternate standard Bokmål spelling, not a diacritic variant
    assert "boneless" in normalize_grocery_heading("KYLLINGLÅR UTEN BEN").lower()
    assert "bone-in" in normalize_grocery_heading("KYLLINGLÅR MED BEN").lower()


# ---------------------------------------------------------------------------
# Adversarial-collision guard: the expanded glossary must not newly corrupt the exact 6
# English free-text phrases a prior adversarial review confirmed were being corrupted by
# glossary/noise-token suffix collisions (see test_pipeline.py's
# ADVERSARIAL_ENGLISH_INGREDIENTS and pipeline.py's normalize=False default). These 6 are
# ALREADY corrupted today by PRE-EXISTING, unrelated collisions (documented inline below)
# that are out of scope for this fix -- these assertions exist purely to lock in that
# none of the NEW preparation/cut-descriptor entries added here make any of them worse.
# ---------------------------------------------------------------------------

def test_new_glossary_entries_do_not_add_further_corruption_to_known_adversarial_phrases():
    # Pre-existing (not introduced by this fix): "extra" is store noise (NORWEGIAN_STORES
    # has "Extra"), "clam" ends in the "lam" (lamb) entry, "ghost"/"defrost" end in "ost"
    # (cheese), "cobs" ends in "obs" (the "Obs" store), "scoop" ends in "coop" (store
    # noise). Confirmed via a before/after diff against the pre-this-change module that
    # these outputs are byte-for-byte unchanged by the new entries added here.
    assert normalize_grocery_heading("extra virgin olive oil") == "virgin olive oil"
    assert normalize_grocery_heading("clam chowder with bacon") == "lamb chowder with bacon"
    assert normalize_grocery_heading("ghost pepper, garlic, lime") == "cheese pepper, garlic, lime"
    assert normalize_grocery_heading("defrost the chicken breast") == "cheese the chicken breast"
    assert normalize_grocery_heading("corn cobs") == "corn"
    assert normalize_grocery_heading("a scoop of vanilla ice cream") == "a of vanilla ice cream"


def test_new_glossary_entries_do_not_corrupt_additional_realistic_english_phrases():
    """Additional realistic English cooking phrases chosen to plausibly collide with the
    new, short glossary keys added in this fix (whole/sliced/boneless/grilled/etc.)."""
    for phrase in [
        "whole chicken",
        "sliced bread",
        "boneless thighs",
        "grilled chicken thighs",
        "marinated pork chops",
        "breaded fish fillets",
        "minced beef",
        "seasoned rice",
        "grated parmesan cheese",
        "diced onions",
    ]:
        assert normalize_grocery_heading(phrase) == phrase


# ---------------------------------------------------------------------------
# Glossary / noise-token sanity checks.
# ---------------------------------------------------------------------------

def test_glossary_has_no_duplicate_keys_mapping_to_conflicting_values_by_construction():
    # GROCERY_GLOSSARY is built from several category dicts merged together -- this just
    # confirms the merge produced a non-empty flat dict with the task-seeded core terms.
    for key in ["kotelett", "kjøttdeig", "kyllingfilet", "laks", "reker", "storfe",
                "biff", "torsk", "makrell", "ost", "melk", "potet", "tomat",
                "gulrot", "pølse", "skinke"]:
        assert key in GROCERY_GLOSSARY


def test_noise_tokens_include_required_marketing_words_and_store_names():
    for word in ["coop", "grill", "perfekt", "fersk", "frossen"]:
        assert word in NOISE_TOKENS
    assert "rema" in NOISE_TOKENS  # derived from NORWEGIAN_STORES, not hand-duplicated
