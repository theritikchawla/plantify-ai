"""
Tests for ai_service.py. A FAKE client replaces Gemini, so these tests are
free, fast, and need no internet connection or API key.
"""

import json

import pytest

import ai_service
from ai_service import PlantAIError


def good_reply(**overrides):
    reply = {
        "is_plant": True,
        "image_quality": "good",
        "common_name": "Swiss cheese plant",
        "scientific_name": "Monstera deliciosa",
        "confidence": "high",
        "confidence_explanation": "Distinctive split leaves.",
        "description": "A climbing houseplant.",
        "visible_characteristics": ["Split leaves", "Glossy green surface"],
        "alternatives": [
            {"common_name": "Philodendron", "scientific_name": "Philodendron sp.", "reason": "Similar leaves."}
        ],
        "needs_better_photo": False,
        "better_photo_advice": "",
        "care": {field: f"Advice about {field}." for field in ai_service.CARE_FIELDS},
    }
    reply.update(overrides)
    return json.dumps(reply)


# ---------- parse_and_validate ----------
def test_valid_reply_is_accepted():
    result = ai_service.parse_and_validate(good_reply())
    assert result["is_plant"] is True
    assert result["common_name"] == "Swiss cheese plant"
    assert result["care"]["watering"] == "Advice about watering."
    assert len(result["alternatives"]) == 1


def test_json_inside_code_fences_is_accepted():
    result = ai_service.parse_and_validate("```json\n" + good_reply() + "\n```")
    assert result["scientific_name"] == "Monstera deliciosa"


@pytest.mark.parametrize("bad", ["", "   ", "not json at all", "[1, 2, 3]", "{broken json"])
def test_malformed_reply_raises_friendly_error(bad):
    with pytest.raises(PlantAIError):
        ai_service.parse_and_validate(bad)


def test_missing_care_fields_get_safe_default():
    result = ai_service.parse_and_validate(good_reply(care={"sunlight": "Bright light."}))
    assert result["care"]["sunlight"] == "Bright light."
    assert result["care"]["pet_toxicity"] == ai_service.NOT_AVAILABLE


def test_invalid_confidence_becomes_low_and_asks_for_better_photo():
    result = ai_service.parse_and_validate(good_reply(confidence="absolutely certain"))
    assert result["confidence"] == "low"
    assert result["needs_better_photo"] is True
    assert result["better_photo_advice"]  # a default tip was added


def test_unnamed_plant_is_marked_unknown_and_not_saveable():
    result = ai_service.parse_and_validate(good_reply(common_name="", scientific_name=""))
    assert result["common_name"] == ai_service.UNKNOWN_PLANT
    assert ai_service.is_saveable(result) is False


def test_not_a_plant_is_not_saveable():
    result = ai_service.parse_and_validate(good_reply(is_plant=False, common_name=""))
    assert result["is_plant"] is False
    assert ai_service.is_saveable(result) is False


def test_is_plant_must_be_real_boolean_true():
    result = ai_service.parse_and_validate(good_reply(is_plant="yes"))
    assert result["is_plant"] is False


def test_html_and_links_are_neutralised():
    nasty = '<script>alert(1)</script> [click](http://evil.example) costs $5'
    result = ai_service.parse_and_validate(good_reply(description=nasty))
    assert "<" not in result["description"]
    assert "](" not in result["description"]
    assert "$" not in result["description"]


def test_long_text_and_long_lists_are_trimmed():
    result = ai_service.parse_and_validate(
        good_reply(description="a" * 5000, visible_characteristics=["leaf"] * 50)
    )
    assert len(result["description"]) <= ai_service.MAX_TEXT_LENGTH
    assert len(result["visible_characteristics"]) <= ai_service.MAX_LIST_ITEMS


def test_wrong_types_do_not_crash():
    result = ai_service.parse_and_validate(
        good_reply(visible_characteristics="oops", alternatives=5, care="nope")
    )
    assert result["visible_characteristics"] == []
    assert result["alternatives"] == []
    assert result["care"]["sunlight"] == ai_service.NOT_AVAILABLE


# ---------- identify_plant with a fake client ----------
class FakeInteraction:
    def __init__(self, text):
        self.output_text = text


class FakeInteractions:
    def __init__(self, behaviours):
        self.behaviours = list(behaviours)  # one item per call: text or exception
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        behaviour = self.behaviours.pop(0)
        if isinstance(behaviour, Exception):
            raise behaviour
        return FakeInteraction(behaviour)


class FakeClient:
    def __init__(self, behaviours):
        self.interactions = FakeInteractions(behaviours)


class FakeAPIError(Exception):
    def __init__(self, code, message="boom"):
        super().__init__(message)
        self.code = code


@pytest.fixture(autouse=True)
def fixed_models(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "main-model")
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "backup-model")


def test_identify_plant_success_sends_image_and_schema():
    client = FakeClient([good_reply()])
    result = ai_service.identify_plant(b"fake-image-bytes", "image/jpeg", client=client)
    assert result["common_name"] == "Swiss cheese plant"

    call = client.interactions.calls[0]
    assert call["model"] == "main-model"
    assert call["store"] is False
    assert call["input"][1]["type"] == "image"
    assert call["response_format"]["mime_type"] == "application/json"


def test_rate_limit_falls_back_to_backup_model():
    client = FakeClient([FakeAPIError(429), good_reply()])
    result = ai_service.identify_plant(b"x", "image/jpeg", client=client)
    assert result["is_plant"] is True
    assert [c["model"] for c in client.interactions.calls] == ["main-model", "backup-model"]


def test_rate_limit_on_both_models_gives_friendly_message():
    client = FakeClient([FakeAPIError(429), FakeAPIError(429)])
    with pytest.raises(PlantAIError) as caught:
        ai_service.identify_plant(b"x", "image/jpeg", client=client)
    assert "limit" in caught.value.user_message.lower()


def test_bad_api_key_does_not_trigger_fallback():
    client = FakeClient([FakeAPIError(403, "API key not valid")])
    with pytest.raises(PlantAIError) as caught:
        ai_service.identify_plant(b"x", "image/jpeg", client=client)
    assert ".env" in caught.value.user_message
    assert len(client.interactions.calls) == 1  # no second attempt


def test_timeout_message():
    client = FakeClient([TimeoutError("request timed out")])
    with pytest.raises(PlantAIError) as caught:
        ai_service.identify_plant(b"x", "image/jpeg", client=client)
    assert "too long" in caught.value.user_message


def test_unknown_error_hides_technical_details():
    client = FakeClient([RuntimeError("secret internal stack trace")])
    with pytest.raises(PlantAIError) as caught:
        ai_service.identify_plant(b"x", "image/jpeg", client=client)
    assert "secret" not in caught.value.user_message


def test_malformed_reply_is_not_retried():
    client = FakeClient(["this is not json", good_reply()])
    with pytest.raises(PlantAIError):
        ai_service.identify_plant(b"x", "image/jpeg", client=client)
    assert len(client.interactions.calls) == 1


def test_missing_api_key_message(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "your_api_key_here")
    with pytest.raises(PlantAIError) as caught:
        ai_service.identify_plant(b"x", "image/jpeg")  # no fake client -> real path
    assert "API key" in caught.value.user_message
