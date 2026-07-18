"""Tests for observability.py -- Epic J1's recommendation-event logging."""

import json

from rag.observability import log_recommendation_event, new_request_id


def test_new_request_id_returns_a_non_empty_string():
    request_id = new_request_id()
    assert isinstance(request_id, str)
    assert request_id


def test_new_request_id_is_unique_across_calls():
    assert new_request_id() != new_request_id()


def test_log_recommendation_event_logs_one_json_line_with_all_fields(caplog):
    with caplog.at_level("INFO", logger="rag.recommendations"):
        log_recommendation_event(request_id="abc123", recommendation_type="cart", meal_ideas_returned=2)

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert message.startswith("recommendation_event ")
    payload = json.loads(message[len("recommendation_event "):])
    assert payload == {"request_id": "abc123", "recommendation_type": "cart", "meal_ideas_returned": 2}
