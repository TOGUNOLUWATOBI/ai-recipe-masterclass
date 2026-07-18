"""Epic I (Testing requirements) -- Tasks I3/I4: fixed, named end-to-end regression
scenarios for the meal-recommendation pipeline, so a future change to meal_ideas.py
can't silently regress known-good behavior for these specific, curated situations.

This file is deliberately narrow and scenario-driven rather than exhaustive --
test_meal_ideas.py already covers the pipeline's mechanics (coverage math, ranking,
generation fallback/retry, Epic J1 logging, Epic J3 request_id) in depth. Each test
here corresponds to exactly one named scenario from the Epic I backlog and is written
against generate_meal_ideas_from_cart()/generate_meal_ideas_from_store() directly, the
same way test_meal_ideas.py does -- only `pipeline` is a MagicMock, nothing in
meal_ideas.py itself is mocked.

`_row`/`_grounded_result` below are deliberately local copies of test_meal_ideas.py's
own fixture helpers (same shape, same behavior) rather than a cross-file import --
this codebase's other test modules don't import fixtures from each other either, and
keeping this file self-contained means it can be read/run in isolation.

Task I4 scenario 5 ("no eligible offers at that store at all") is intentionally NOT
duplicated here -- it's already covered by
test_meal_ideas.test_from_store_returns_empty_ideas_without_calling_the_pipeline_when_nothing_is_eligible,
which already asserts empty ideas, a non-empty excluded_store_items, and that the
pipeline is never called.
"""

from unittest.mock import MagicMock

from rag.meal_ideas import generate_meal_ideas_from_cart, generate_meal_ideas_from_store


def _row(product_name, store_name="Kiwi", recipe_eligible=True, recipe_exclusion_reason=None, category="main_food"):
    return {
        "product_name": product_name,
        "store_name": store_name,
        "category": category,
        "recipe_eligible": recipe_eligible,
        "recipe_exclusion_reason": recipe_exclusion_reason,
    }


def _grounded_result(title, ingredients, rerank_score=5.0):
    return {
        "id": title,
        "score": 1.0,
        "dense_score": 0.7,
        "rerank_score": rerank_score,
        "text": f"### {title}",
        "payload": {"title": title, "ingredients": ingredients, "instructions": ["Cook it."]},
    }


# ---------------------------------------------------------------------------
# Task I3 -- five fixed cart-sourced scenarios (generate_meal_ideas_from_cart)
# ---------------------------------------------------------------------------


def test_i3_scenario_1_a_beverage_never_surfaces_anywhere_in_the_cart_response():
    """Task I3 scenario 1: cart = chicken, rice, Coca-Cola. Coca-Cola must never be
    mentioned anywhere in the result -- not just kept out of the retrieval query
    (already covered by test_meal_ideas.py's
    test_never_sends_an_excluded_products_name_into_the_retrieval_query), but also
    absent from every idea's own title, required/optional ingredients,
    selected_items_used, and missing_required_ingredients -- and explicitly reported
    in excluded_cart_items with reason "beverage"."""
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = [
        _grounded_result("Chicken and Rice", ["chicken", "rice", "onion"]),
    ]
    discounts = [
        _row("chicken"),
        _row("rice"),
        _row("Coca-Cola", recipe_eligible=False, recipe_exclusion_reason="beverage"),
    ]

    result = generate_meal_ideas_from_cart(
        pipeline, discounts, ["Kiwi::chicken", "Kiwi::rice", "Kiwi::Coca-Cola"],
    )

    assert result["excluded_cart_items"] == [{"product_name": "Coca-Cola", "reason": "beverage"}]
    assert len(result["ideas"]) >= 1
    for idea in result["ideas"]:
        assert "coca" not in (idea["title"] or "").lower()
        assert not any("coca" in ing["name"].lower() for ing in idea["required_ingredients"])
        assert not any("coca" in ing["name"].lower() for ing in idea["optional_ingredients"])
        assert not any("coca" in name.lower() for name in idea["selected_items_used"])
        assert not any("coca" in name.lower() for name in idea["missing_required_ingredients"])


def test_i3_scenario_2_an_everyday_protein_and_veg_cart_yields_a_workable_meal():
    """Task I3 scenario 2: cart = salmon, potatoes, broccoli -- an ordinary, mostly-
    makeable everyday meal. At least one returned idea must be "complete" or
    "nearly_complete", not stuck at "partial"."""
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = [
        _grounded_result("Salmon Traybake", ["salmon fillet", "potatoes", "broccoli"]),
    ]
    discounts = [_row("salmon"), _row("potatoes"), _row("broccoli")]

    result = generate_meal_ideas_from_cart(
        pipeline, discounts, ["Kiwi::salmon", "Kiwi::potatoes", "Kiwi::broccoli"],
    )

    assert len(result["ideas"]) >= 1
    assert any(idea["completion_status"] in ("complete", "nearly_complete") for idea in result["ideas"])


def test_i3_scenario_3_a_cart_of_two_ineligible_items_still_makes_no_recommendation_call():
    """Task I3 scenario 3: cart = frozen pizza (ready_meal/finished_meal), energy
    drink (beverage) -- both ineligible, so zero eligible ingredients. Unlike the
    existing single-item
    test_meal_ideas.test_returns_empty_ideas_without_calling_the_pipeline_when_nothing_is_eligible,
    this confirms the same "no recommendation call made" guarantee (Task C8) holds
    with multiple ineligible items carrying different exclusion reasons, not just
    one."""
    pipeline = MagicMock()
    discounts = [
        _row("Frozen Pizza", recipe_eligible=False, recipe_exclusion_reason="finished_meal"),
        _row("Energy Drink", recipe_eligible=False, recipe_exclusion_reason="beverage"),
    ]

    result = generate_meal_ideas_from_cart(
        pipeline, discounts, ["Kiwi::Frozen Pizza", "Kiwi::Energy Drink"],
    )

    assert result["ideas"] == []
    reasons = {item["product_name"]: item["reason"] for item in result["excluded_cart_items"]}
    assert reasons == {"Frozen Pizza": "finished_meal", "Energy Drink": "beverage"}
    pipeline.find_recipes_from_ingredients.assert_not_called()


def test_i3_scenario_4_processed_but_useful_cooking_components_are_all_eligible():
    """Task I3 scenario 4 / Epic A2: cart = canned tomatoes, pasta, cheese -- all
    processed, shelf-stable products, but each is a genuine, useful cooking
    component. Epic A2's eligibility rule is "useful as a cooking component," not
    "unprocessed vs. processed", so none of the three should be excluded, and all
    three should reach the (mocked) retrieval call."""
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = [
        _grounded_result("Pasta with Tomato and Cheese", ["canned tomatoes", "pasta", "cheese"]),
    ]
    discounts = [_row("canned tomatoes"), _row("pasta"), _row("cheese")]

    result = generate_meal_ideas_from_cart(
        pipeline, discounts, ["Kiwi::canned tomatoes", "Kiwi::pasta", "Kiwi::cheese"],
    )

    assert result["excluded_cart_items"] == []
    called_ingredients = pipeline.find_recipes_from_ingredients.call_args.args[0]
    assert set(called_ingredients) == {"canned tomatoes", "pasta", "cheese"}


def test_i3_scenario_5_a_four_item_cart_can_split_into_more_than_one_idea():
    """Task I3 scenario 5: cart = chicken, rice, taco shells, yoghurt. The system is
    allowed (never forced) to return more than one idea, and each idea must only use
    the subset of cart ingredients actually relevant to it (Task C6) -- never
    combining all four into one forced dish. Mocks two clearly different corpus
    results: a chicken-and-rice recipe and a separate taco-based recipe."""
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = [
        _grounded_result("Chicken and Rice", ["chicken", "rice", "onion"]),
        _grounded_result("Beef Tacos", ["taco shells", "ground beef", "lettuce"]),
    ]
    discounts = [_row("chicken"), _row("rice"), _row("taco shells"), _row("yoghurt")]

    result = generate_meal_ideas_from_cart(
        pipeline,
        discounts,
        ["Kiwi::chicken", "Kiwi::rice", "Kiwi::taco shells", "Kiwi::yoghurt"],
    )

    assert len(result["ideas"]) == 2
    titles = {idea["title"] for idea in result["ideas"]}
    assert titles == {"Chicken and Rice", "Beef Tacos"}

    chicken_idea = next(i for i in result["ideas"] if i["title"] == "Chicken and Rice")
    taco_idea = next(i for i in result["ideas"] if i["title"] == "Beef Tacos")

    # Each idea only used its own relevant subset -- never all four cart ingredients,
    # and never the other idea's ingredients.
    assert set(chicken_idea["selected_items_used"]) == {"chicken", "rice"}
    assert set(taco_idea["selected_items_used"]) == {"taco shells"}


# ---------------------------------------------------------------------------
# Task I4 -- eight store-sourced scenarios (generate_meal_ideas_from_store)
# ---------------------------------------------------------------------------


def test_i4_scenario_1_compatible_ingredients_at_one_store_yield_a_sensible_idea():
    """Task I4 scenario 1: chicken, rice, onion all discounted at "Kiwi" -- a
    sensible idea should come back using some of them. (The existing
    test_meal_ideas.test_from_store_only_considers_the_requested_stores_offers only
    asserts what reaches the retrieval call/store_name, not that a populated,
    sensible idea is actually returned -- that's the gap this test closes.)"""
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = [
        _grounded_result("Chicken and Rice", ["chicken", "rice", "onion"]),
    ]
    discounts = [
        _row("chicken", store_name="Kiwi"),
        _row("rice", store_name="Kiwi"),
        _row("onion", store_name="Kiwi"),
    ]

    result = generate_meal_ideas_from_store(pipeline, discounts, "Kiwi")

    assert len(result["ideas"]) == 1
    idea = result["ideas"][0]
    assert idea["title"] == "Chicken and Rice"
    assert len(idea["selected_items_used"]) > 0
    assert set(idea["selected_items_used"]) <= {"chicken", "rice", "onion"}


def test_i4_scenario_2_protein_only_store_offers_still_call_the_pipeline_and_report_missing_carbs():
    """Task I4 scenario 2: a store offering only proteins (chicken breast, salmon --
    no carbs/veg) is still a valid non-empty eligible set, so retrieval must still be
    attempted, and whatever recipe comes back should report the required ingredients
    this store doesn't stock as missing_required_ingredients rather than hiding the
    gap."""
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = [
        _grounded_result("Chicken and Rice", ["chicken breast", "rice", "onion"]),
    ]
    discounts = [
        _row("chicken breast", store_name="Kiwi"),
        _row("salmon", store_name="Kiwi"),
    ]

    result = generate_meal_ideas_from_store(pipeline, discounts, "Kiwi")

    pipeline.find_recipes_from_ingredients.assert_called_once()
    assert len(result["ideas"]) == 1
    idea = result["ideas"][0]
    assert idea["missing_required_ingredients"] == ["rice", "onion"]


def test_i4_scenario_3_a_store_of_only_snacks_and_beverages_returns_no_ideas():
    """Task I4 scenario 3: store offers = only Coca-Cola (beverage) and crisps
    (snack_or_treat), both ineligible -- mirrors Task I3 scenario 3's multi-item "no
    recommendation call made" pattern, but via the store path."""
    pipeline = MagicMock()
    discounts = [
        _row("Coca-Cola", store_name="Kiwi", recipe_eligible=False, recipe_exclusion_reason="beverage"),
        _row("Crisps", store_name="Kiwi", recipe_eligible=False, recipe_exclusion_reason="snack_or_treat"),
    ]

    result = generate_meal_ideas_from_store(pipeline, discounts, "Kiwi")

    assert result["ideas"] == []
    reasons = {item["product_name"]: item["reason"] for item in result["excluded_store_items"]}
    assert reasons == {"Coca-Cola": "beverage", "Crisps": "snack_or_treat"}
    pipeline.find_recipes_from_ingredients.assert_not_called()


def test_i4_scenario_4_a_mixed_food_and_non_food_store_excludes_only_the_non_food_item():
    """Task I4 scenario 4: store offers = chicken breast + laundry detergent. Only
    the food item is eligible/used; the non-food item is excluded with reason
    "non_food" and never reaches the ingredient list handed to retrieval."""
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = [
        _grounded_result("Simple Chicken Breast", ["chicken breast"]),
    ]
    discounts = [
        _row("chicken breast", store_name="Kiwi"),
        _row("Laundry Detergent", store_name="Kiwi", recipe_eligible=False, recipe_exclusion_reason="non_food"),
    ]

    result = generate_meal_ideas_from_store(pipeline, discounts, "Kiwi")

    assert result["excluded_store_items"] == [{"product_name": "Laundry Detergent", "reason": "non_food"}]
    called_ingredients = pipeline.find_recipes_from_ingredients.call_args.args[0]
    assert called_ingredients == ["chicken breast"]
    assert not any("detergent" in ing.lower() for ing in called_ingredients)


# Task I4 scenario 5 ("no eligible offers at that store at all") is intentionally not
# duplicated here -- see module docstring: it's already covered end-to-end by
# test_meal_ideas.test_from_store_returns_empty_ideas_without_calling_the_pipeline_when_nothing_is_eligible,
# which already asserts empty ideas, a non-empty excluded_store_items, and that the
# pipeline is never called.


def test_i4_scenario_6_expired_valid_until_rows_are_still_treated_as_normal_eligible_rows():
    """Task I4 scenario 6: meal_ideas.py has no expiry-awareness of its own --
    resolve_store_items()/filter_eligible_items() (confirmed by reading both
    functions) operate purely on whatever discount rows they're handed, regardless of
    any valid_until field; neither function references "valid_until" anywhere.
    Dropping stale/expired rows before they ever reach this module is a mobile-side
    concern (Epic B6), not something meal_ideas.py does or should duplicate. This
    test documents that actual division of responsibility: a row with a valid_until
    in the past is not treated any differently from a current one."""
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = [
        _grounded_result("Simple Chicken Breast", ["chicken breast"]),
    ]
    expired_row = _row("chicken breast", store_name="Kiwi")
    expired_row["valid_until"] = "2020-01-01"  # long expired -- meal_ideas.py never looks at this field
    discounts = [expired_row]

    result = generate_meal_ideas_from_store(pipeline, discounts, "Kiwi")

    assert result["excluded_store_items"] == []
    assert len(result["ideas"]) == 1
    pipeline.find_recipes_from_ingredients.assert_called_once()


def test_i4_scenario_7_duplicate_products_at_the_same_store_produce_one_ingredient():
    """Task I4 scenario 7: two literal discount rows for the same product at the same
    store (e.g. two differently-priced KYLLINGFILET offers/promotions) must still
    collapse to one ingredient reaching retrieval. normalize_and_dedupe()'s dedup
    behavior already has its own unit test across two *different* stores (see
    test_meal_ideas.test_normalize_and_dedupe_collapses_the_same_ingredient_from_two_stores),
    but not end-to-end through generate_meal_ideas_from_store with a same-store
    duplicate -- that's the gap this test closes."""
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = [
        _grounded_result("Chicken and Rice", ["chicken fillet", "rice"]),
    ]
    discounts = [
        _row("KYLLINGFILET", store_name="Kiwi"),
        _row("KYLLINGFILET", store_name="Kiwi"),  # e.g. a second, differently-priced promo row
    ]

    result = generate_meal_ideas_from_store(pipeline, discounts, "Kiwi")

    called_ingredients = pipeline.find_recipes_from_ingredients.call_args.args[0]
    assert called_ingredients == ["chicken fillet"]


def test_i4_scenario_8_norwegian_product_names_reach_retrieval_already_normalized():
    """Task I4 scenario 8: KYLLINGFILET, LAKSEFILET, POTETER at one store must reach
    the mocked pipeline.find_recipes_from_ingredients call already translated to
    their English equivalents (chicken fillet, salmon fillet, potato) via
    grocery_terms.normalize_grocery_heading(). test_meal_ideas.py already unit-tests
    normalize_and_dedupe()'s translation directly (see
    test_normalize_and_dedupe_translates_norwegian_headings) and end-to-end with a
    single Norwegian item (test_from_store_only_considers_the_requested_stores_offers),
    but not an end-to-end version with all three of these headings together through
    generate_meal_ideas_from_store -- that's the gap this test closes."""
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = [
        _grounded_result(
            "Chicken, Salmon and Potato Traybake", ["chicken fillet", "salmon fillet", "potato"],
        ),
    ]
    discounts = [
        _row("KYLLINGFILET", store_name="Kiwi"),
        _row("LAKSEFILET", store_name="Kiwi"),
        _row("POTETER", store_name="Kiwi"),
    ]

    result = generate_meal_ideas_from_store(pipeline, discounts, "Kiwi")

    called_ingredients = pipeline.find_recipes_from_ingredients.call_args.args[0]
    assert set(called_ingredients) == {"chicken fillet", "salmon fillet", "potato"}
    assert not any(name.isupper() for name in called_ingredients)
