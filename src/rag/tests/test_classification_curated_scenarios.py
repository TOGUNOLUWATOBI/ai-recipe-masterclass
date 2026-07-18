"""Epic I1 (Testing requirements): fixed, named regression tests locking in
grocery_discounts.classify_product() -- the deterministic keyword heuristic --
behavior for a curated list of real products.

Why this file exists, and why it's separate from test_grocery_discounts.py:
that file tests classify_product() and its keyword-matching helpers as an
implementation (does the suffix-per-token matching work, does the priority
order hold, etc). This file instead tests a *fixed product list* the business
has explicitly signed off on -- 10 products that must always come out
recipe_eligible=True, 10 that must always come out recipe_eligible=False, and
9 deliberately ambiguous cases (bread, yoghurt, smoked salmon, prepared salad,
soup, cream, ice cream, cooking cream, protein shake) whose classification was
argued over and settled. A future change to NON_FOOD_KEYWORDS/SNACK_KEYWORDS/
BEVERAGE_KEYWORDS/READY_MEAL_KEYWORDS/READY_TO_EAT_KEYWORDS (or to the
priority order in classify_product() itself) can silently flip one of these
known-good products -- these tests exist purely to catch that, with one named
test per product so a regression points straight at which product broke,
rather than only at "some heuristic test failed".

classify_product() is the deterministic, no-LLM-call keyword heuristic in
grocery_discounts.py (not product_classifier.py's LLM tier) -- refresh_discounts.py's
own docstring describes it as the cheap first pass every discovered product gets
inline during a discount refresh, which is exactly why it's the right thing to
pin down with a fixed regression suite: unlike the LLM tier, it's reproducible
byte-for-byte given the same heading, with no model/prompt drift to account for.

Every heading below is phrased the way real Tjek/Norwegian-flyer headings look
(see test_grocery_discounts.py's own fixtures for the convention this codebase
uses) -- classify_product() matches keyword suffixes per token, so an English
product name run through it verbatim (e.g. "bread") would never hit any
keyword list and is meaningless as a regression fixture. Every outcome
asserted here was actually produced by running the real heading through the
real function (see the code review notes below for the two cases where no
reasonable heading gets the agreed outcome).

KNOWN GAP against agreed policy (see the test marked KNOWN GAP below): a
"microwave curry" ready meal currently comes out recipe_eligible=True under
the heuristic, even with realistic Norwegian ready-meal headings tried --
READY_MEAL_KEYWORDS has no curry-adjacent keyword, and the obvious fix (a bare
"curry" keyword) was investigated and rejected: a live scan found real
current offers ("CURRY KETCHUP", "MANGO&CURRY") that keyword would wrongly
catch as ready meals. This is asserted as the current actual behavior, not
silently "fixed" (there's no live example to safely derive a better keyword
against yet) and not silently encoded as if it were the agreed outcome.

A second gap ("protein shake") was found and fixed directly: BEVERAGE_KEYWORDS
now includes "proteinshake" (the real compound-word heading, verified safe
against live data -- see grocery_discounts.py's own comment there).
"""

from rag.grocery_discounts import classify_product


# ---------------------------------------------------------------------------
# Eligible products (change spec's Epic A worked examples + this epic's list):
# every one of these must come out recipe_eligible=True with no exclusion
# reason. All are ordinary primary_ingredient headings that don't hit any
# keyword list -- classify_product() defaults to primary_ingredient/eligible
# for exactly that reason (see its docstring).
# ---------------------------------------------------------------------------

def test_eligible_chicken_breast():
    result = classify_product("KYLLINGFILET")
    assert result["recipe_eligible"] is True
    assert result["recipe_exclusion_reason"] is None


def test_eligible_salmon():
    result = classify_product("LAKSEFILET")
    assert result["recipe_eligible"] is True
    assert result["recipe_exclusion_reason"] is None


def test_eligible_potatoes():
    result = classify_product("POTETER 2 KG")
    assert result["recipe_eligible"] is True
    assert result["recipe_exclusion_reason"] is None


def test_eligible_rice():
    """Also guards against the "is" (ice) false-positive regression documented in
    test_grocery_discounts.py's test_is_snack_does_not_false_positive_on_rice --
    "ris" (rice) must never be caught by a bare "is" snack keyword."""
    result = classify_product("URIKO RIS 1 KG")
    assert result["recipe_eligible"] is True
    assert result["recipe_exclusion_reason"] is None


def test_eligible_eggs():
    result = classify_product("PRIOR EGG 12 STK")
    assert result["recipe_eligible"] is True
    assert result["recipe_exclusion_reason"] is None


def test_eligible_frozen_vegetables():
    result = classify_product("FINDUS FROSNE GRØNNSAKER")
    assert result["recipe_eligible"] is True
    assert result["recipe_exclusion_reason"] is None


def test_eligible_canned_tomatoes():
    result = classify_product("HERMETISKE TOMATER")
    assert result["recipe_eligible"] is True
    assert result["recipe_exclusion_reason"] is None


def test_eligible_canned_beans():
    result = classify_product("HERMETISKE BØNNER")
    assert result["recipe_eligible"] is True
    assert result["recipe_exclusion_reason"] is None


def test_eligible_coconut_milk():
    result = classify_product("KOKOSMELK")
    assert result["recipe_eligible"] is True
    assert result["recipe_exclusion_reason"] is None


def test_eligible_pasta_sauce():
    result = classify_product("PASTASAUS")
    assert result["recipe_eligible"] is True
    assert result["recipe_exclusion_reason"] is None


# ---------------------------------------------------------------------------
# Ineligible products (change spec's Epic A worked examples + this epic's
# list): every one of these must come out recipe_eligible=False with a
# sensible recipe_exclusion_reason. "microwave curry" is a confirmed gap --
# see the KNOWN GAP test below instead of an ordinary assertion.
# ---------------------------------------------------------------------------

def test_ineligible_coca_cola():
    result = classify_product("COCA-COLA 1,5L")
    assert result["recipe_eligible"] is False
    assert result["recipe_exclusion_reason"] == "beverage"


def test_ineligible_juice():
    """Real heading observed live 2026-07-16 (see BEVERAGE_KEYWORDS' comment)."""
    result = classify_product("NYPRESSET APPELSINJUICE")
    assert result["recipe_eligible"] is False
    assert result["recipe_exclusion_reason"] == "beverage"


def test_ineligible_chocolate():
    result = classify_product("FREIA MELKESJOKOLADE")
    assert result["recipe_eligible"] is False
    assert result["recipe_exclusion_reason"] == "snack_or_treat"


def test_ineligible_crisps():
    result = classify_product("POTETGULL")
    assert result["recipe_eligible"] is False
    assert result["recipe_exclusion_reason"] == "snack_or_treat"


def test_ineligible_ice_cream():
    result = classify_product("SOFTIS VANILJE")
    assert result["recipe_eligible"] is False
    assert result["recipe_exclusion_reason"] == "snack_or_treat"


def test_ineligible_frozen_pizza():
    result = classify_product("BIG ONE PIZZA AMERICAN CLASSIC OG PEPPERONI")
    assert result["recipe_eligible"] is False
    assert result["recipe_exclusion_reason"] == "finished_meal"


def test_ineligible_ready_made_lasagne():
    result = classify_product("FERDIG LASAGNE")
    assert result["recipe_eligible"] is False
    assert result["recipe_exclusion_reason"] == "finished_meal"


def test_ineligible_microwave_curry_KNOWN_GAP():
    """KNOWN GAP, deliberately left unfixed: the agreed policy is that a
    microwave/ready-to-heat curry (e.g. a Fjordland- or Toro-style pouch meal)
    should be recipe_eligible=False with recipe_exclusion_reason="finished_meal",
    the same as frozen pizza or ready-made lasagne above. Several realistic
    Norwegian ready-meal headings were tried -- "FJORDLAND KYLLINGCURRY MED
    RIS", "TORO KYLLING TIKKA MASALA FERDIGRETT", "MIKROMAT CURRY", "FERDIGRETT
    KYLLINGCURRY" -- and none of them are caught: READY_MEAL_KEYWORDS only
    lists "pizza", "lasagne", and "suppe" (soup), with no curry-adjacent
    keyword at all.

    Unlike the protein-shake gap above, this one was investigated and its
    obvious fix (add a bare "curry" keyword) was rejected on purpose: a live
    scan (2026-07-18) found "CURRY KETCHUP" and "MANGO&CURRY" (both real
    current offers) would be caught as false-positive ready meals -- they're
    condiments, not finished dishes -- since classify_product()'s suffix-per-
    token matching would flag any token ending in "curry". No live current
    offer for a real microwave/ready-meal curry product exists right now to
    derive a safer, more specific keyword against (e.g. "ferdigrett" has zero
    current matches to verify safety or necessity), so the heuristic currently
    classifies this as an ordinary primary_ingredient (recipe_eligible=True),
    which is the WRONG outcome against agreed policy but the safer of the two
    available choices until a real example shows up to test a fix against.
    This test asserts the current actual behavior on purpose, so a future fix
    is a deliberate, visible change to this test rather than a silent flip."""
    result = classify_product("FJORDLAND KYLLINGCURRY MED RIS")
    assert result["food_usage_class"] == "primary_ingredient"
    assert result["recipe_eligible"] is True  # agreed policy says this should be False


def test_ineligible_laundry_detergent():
    result = classify_product("OMO VASKEMIDDEL")
    assert result["recipe_eligible"] is False
    assert result["recipe_exclusion_reason"] == "non_food"


def test_ineligible_shampoo():
    result = classify_product("HEAD & SHOULDERS SJAMPO")
    assert result["recipe_eligible"] is False
    assert result["recipe_exclusion_reason"] == "non_food"


# ---------------------------------------------------------------------------
# Nine explicitly-agreed ambiguous cases. These are deliberate product
# decisions already made (not re-derived here) -- see each docstring for the
# reasoning behind the agreed outcome. "protein shake" is a confirmed gap --
# see the KNOWN GAP test below instead of an ordinary assertion.
# ---------------------------------------------------------------------------

def test_ambiguous_bread_is_eligible():
    """Agreed: bread is a genuine cooking/meal component (sandwiches, toast,
    stuffing, bread pudding) -- not just a snack. No keyword list flags bread,
    so the heuristic's default-to-primary_ingredient already gets this right."""
    result = classify_product("GRØVBRØD")
    assert result["recipe_eligible"] is True
    assert result["recipe_exclusion_reason"] is None


def test_ambiguous_yoghurt_is_eligible():
    """Agreed: yoghurt is used in cooking (marinades, dressings, raita, baking),
    not just eaten plain. No keyword list flags it."""
    result = classify_product("TINE YOGHURT NATURELL")
    assert result["recipe_eligible"] is True
    assert result["recipe_exclusion_reason"] is None


def test_ambiguous_smoked_salmon_is_eligible():
    """Agreed, and explicitly called out in Epic A2: a processed product like
    smoked salmon must still count as a usable ingredient, alongside canned
    tomatoes/beans/coconut milk/pasta sauce/stock/grated cheese."""
    result = classify_product("RØKT LAKS")
    assert result["recipe_eligible"] is True
    assert result["recipe_exclusion_reason"] is None


def test_ambiguous_prepared_salad_is_ineligible():
    """Agreed: a prepared salad is a ready-to-eat side, not something you cook
    from. The heuristic's READY_TO_EAT_KEYWORDS deliberately only lists the
    specific compound "potetsalat" (potato salad) -- not a bare "salat" suffix,
    which would also catch fresh lettuce/salad greens sold as a raw vegetable
    (see READY_TO_EAT_KEYWORDS' comment in grocery_discounts.py). Potato salad
    is itself a real, common prepared/deli salad, so it's used here as the
    representative heading -- a generic prepared salad without "potetsalat" or
    "spiseklar" in its heading (e.g. a shrimp or pasta salad) would NOT be
    caught by this heuristic today, but that's a narrower gap than this fixed
    product name requires flagging."""
    result = classify_product("MILLS KLASSISK POTETSALAT")
    assert result["recipe_eligible"] is False
    assert result["recipe_exclusion_reason"] == "finished_meal"


def test_ambiguous_soup_is_ineligible():
    """Agreed: soup is treated as a ready-to-heat-and-eat product, like frozen
    pizza or ready-made lasagne -- "suppe" is a READY_MEAL_KEYWORDS entry."""
    result = classify_product("KREMET FISKESUPPE")
    assert result["recipe_eligible"] is False
    assert result["recipe_exclusion_reason"] == "finished_meal"


def test_ambiguous_cream_is_eligible():
    """Agreed: cream ("fløte" in Norwegian -- not to be confused with "krem",
    the lotion/frosting sense NON_FOOD_KEYWORDS' "solkrem" etc. key off of) is a
    genuine cooking ingredient for sauces and desserts. No keyword list flags
    it."""
    result = classify_product("TINE FLØTE")
    assert result["recipe_eligible"] is True
    assert result["recipe_exclusion_reason"] is None


def test_ambiguous_ice_cream_is_ineligible():
    """Agreed: ice cream is a dessert/treat, not a cooking ingredient -- the
    same outcome as the ineligible-products list's "ice cream" case above, but
    listed again here since the change spec explicitly calls it out alongside
    cream/cooking cream to make sure those three don't get conflated by a
    future keyword change. "iskrem" is a SNACK_KEYWORDS entry (a deliberately
    listed full compound, precisely so it does NOT fall through the "krem"
    non-food trap -- see NON_FOOD_KEYWORDS' module docstring)."""
    result = classify_product("ISKREM")
    assert result["recipe_eligible"] is False
    assert result["recipe_exclusion_reason"] == "snack_or_treat"


def test_ambiguous_cooking_cream_is_eligible():
    """Agreed: explicitly a cooking ingredient ("matfløte" in Norwegian). No
    keyword list flags it."""
    result = classify_product("TINE MATFLØTE")
    assert result["recipe_eligible"] is True
    assert result["recipe_exclusion_reason"] is None


def test_ambiguous_protein_shake_is_ineligible():
    """Agreed: a protein shake is a beverage (recipe_eligible=False,
    recipe_exclusion_reason="beverage"), the same as Coca-Cola or juice.

    Previously a KNOWN GAP: a live scan (2026-07-18) confirmed the real
    product heading is the compound Norwegian word "PROTEINSHAKE" (see
    "TINE YT PROTEINSHAKE/ RESTITUSJONSDRIKK 6 PK"), not a space-separated
    "PROTEIN SHAKE" -- BEVERAGE_KEYWORDS now includes "proteinshake"
    specifically (not bare "protein"), since that same live scan also had
    "PROTEINBAR"/"PROTEINBARER" (protein bars, a snack, not a drink) that a
    bare "protein" keyword would have wrongly caught too."""
    result = classify_product("TINE PROTEINSHAKE VANILJE")
    assert result["food_usage_class"] == "beverage"
    assert result["recipe_eligible"] is False
    assert result["recipe_exclusion_reason"] == "beverage"
