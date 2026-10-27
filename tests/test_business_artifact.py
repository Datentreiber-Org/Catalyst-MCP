"""Business Artifact contract checks using synthetic bicycle-repair content."""

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from catalyst_mcp.models import (
    AnalyzeBusinessModelInput,
    BusinessArtifact,
    BusinessModel,
    GeneratedBusinessArtifact,
)


BUSINESS_MODEL_SECTIONS = (
    "endUsers",
    "economicBuyers",
    "decisionMakers",
    "solutions",
    "benefits",
    "channels",
    "relationships",
    "businessResources",
    "activities",
    "partnerships",
    "revenuesAndAdvantages",
    "costsAndRisks",
)


@pytest.fixture
def business_model_payload() -> dict[str, list[str]]:
    """Provide a fresh synthetic model with explicit unspecified sections."""
    sections = {section: [] for section in BUSINESS_MODEL_SECTIONS}
    sections["endUsers"] = ["Cyclists"]
    sections["solutions"] = ["Bicycle repairs"]
    sections["activities"] = ["Repair bicycles"]
    sections["revenuesAndAdvantages"] = ["Repair fees"]
    return sections


@pytest.fixture
def artifact_payload(business_model_payload) -> dict[str, Any]:
    """Provide a complete synthetic artifact in its JSON representation."""
    return {
        "id": "ba_demo",
        "name": "Northstar Bikes",
        "uri": "catalyst://business-artifact/ba_demo",
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
        "businessModel": business_model_payload,
    }


def test_analysis_input_preserves_text():
    """Keep valid business text intact, including whitespace and punctuation."""
    text = "  Northstar Bikes repairs bicycles for cyclists.\nFees: €20 & up.  "
    request = AnalyzeBusinessModelInput(businessContent=text)
    assert request.model_dump() == {"businessContent": text}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"businessContent": ""},
        {"businessContent": " \t\n\u2003"},
        {"businessContent": None},
        {"businessContent": 123},
        {"businessContent": b"Bicycle repairs"},
        {"businessContent": ["Bicycle repairs"]},
        {"business_content": "Bicycle repairs"},
        {"businessContent": "Bicycle repairs", "extra": True},
    ],
)
def test_analysis_input_rejects_invalid_payloads(payload):
    """Reject absent, blank, wrongly typed or unexpectedly named input fields."""
    with pytest.raises(ValidationError):
        AnalyzeBusinessModelInput.model_validate(payload)


def test_generated_content_preserves_model(business_model_payload):
    """Return exactly the generated-content contract with all 12 sections."""
    payload = {"name": "Northstar Bikes", "businessModel": business_model_payload}
    generated = GeneratedBusinessArtifact.model_validate(payload)
    assert generated.model_dump() == payload
    assert tuple(generated.businessModel.model_dump()) == BUSINESS_MODEL_SECTIONS


@pytest.mark.parametrize(
    "updates",
    [
        {"name": ""},
        {"name": " \n"},
        {"name": None},
        {"name": 123},
        {"id": "ba_model_supplied"},
        {"uri": "catalyst://business-artifact/ba_model_supplied"},
        {"createdAt": "2026-01-01T00:00:00Z"},
        {"updatedAt": "2026-01-01T00:00:00Z"},
        {"extra": True},
    ],
)
def test_generated_content_rejects_invalid_fields(business_model_payload, updates):
    """Reject invalid names and any attempt to supply system metadata."""
    payload = {"name": "Northstar Bikes", "businessModel": business_model_payload}
    with pytest.raises(ValidationError):
        GeneratedBusinessArtifact.model_validate(payload | updates)


@pytest.mark.parametrize("section", BUSINESS_MODEL_SECTIONS)
@pytest.mark.parametrize(
    "value", [None, "Cyclists", ("Cyclists",), {}, [123], [None], [""], [" \t\n"]]
)
def test_each_section_requires_list_of_nonblank_strings(
    business_model_payload, section, value
):
    """Enforce the array and statement types independently for every section."""
    business_model_payload[section] = value
    with pytest.raises(ValidationError) as error:
        BusinessModel.model_validate(business_model_payload)
    assert error.value.errors()[0]["loc"][0] == section


@pytest.mark.parametrize("section", BUSINESS_MODEL_SECTIONS)
def test_all_sections_are_required(business_model_payload, section):
    """Reject a missing section instead of silently filling it in."""
    del business_model_payload[section]
    with pytest.raises(ValidationError) as error:
        BusinessModel.model_validate(business_model_payload)
    assert error.value.errors()[0]["loc"] == (section,)


def test_entirely_empty_model_is_rejected():
    """Require at least one statement even when every section is present."""
    with pytest.raises(ValidationError, match="at least one statement"):
        BusinessModel.model_validate({section: [] for section in BUSINESS_MODEL_SECTIONS})


def test_unknown_section_is_rejected(business_model_payload):
    """Catch an extra or misspelled section rather than discarding it."""
    business_model_payload["business_resources"] = []
    with pytest.raises(ValidationError) as error:
        BusinessModel.model_validate(business_model_payload)
    assert error.value.errors()[0]["loc"] == ("business_resources",)


def test_artifact_json_round_trip_preserves_content(artifact_payload):
    """Preserve all fields, empty sections, array order and special characters."""
    artifact_payload["businessModel"]["endUsers"] = [
        "Cyclists <all ages> & commuters",
        "  Café riders\n*Weekend club*  ",
    ]
    artifact = BusinessArtifact.model_validate_json(json.dumps(artifact_payload))
    assert artifact.model_dump(mode="json") == artifact_payload
    serialized = artifact.model_dump_json()
    assert json.loads(serialized) == artifact_payload
    assert BusinessArtifact.model_validate_json(serialized) == artifact


def test_artifact_accepts_backend_datetime_values(artifact_payload):
    """Allow backend code to supply UTC datetime objects without parsing text."""
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    artifact_payload.update(createdAt=timestamp, updatedAt=timestamp)
    artifact = BusinessArtifact.model_validate(artifact_payload)
    assert artifact.createdAt == artifact.updatedAt == timestamp


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", ""),
        ("id", " \t"),
        ("id", 123),
        ("id", "ba_other"),
        ("name", " \n"),
        ("name", 123),
        ("uri", None),
        ("uri", "catalyst://business-artifact/ba_other"),
        ("uri", "catalyst://business-artifact/ba_demo/view.md"),
        ("createdAt", "2026-01-01T00:00:00"),
        ("updatedAt", "2026-01-01T00:00:00"),
        ("createdAt", "2026-01-01T01:00:00+01:00"),
        ("updatedAt", "2026-01-01T01:00:00+01:00"),
        ("createdAt", "2026-01-01"),
        ("updatedAt", "not a timestamp"),
        ("createdAt", 1767225600),
        ("updatedAt", None),
        ("updatedAt", "2026-01-02T00:00:00Z"),
    ],
)
def test_artifact_rejects_invalid_metadata(artifact_payload, field, value):
    """Reject invalid metadata, inconsistent URIs and invalid creation times."""
    artifact_payload[field] = value
    with pytest.raises(ValidationError):
        BusinessArtifact.model_validate_json(json.dumps(artifact_payload))


@pytest.mark.parametrize(
    "field", ["id", "name", "uri", "createdAt", "updatedAt", "businessModel"]
)
def test_artifact_requires_every_field(artifact_payload, field):
    """Require supplied metadata and content rather than generating defaults."""
    del artifact_payload[field]
    with pytest.raises(ValidationError) as error:
        BusinessArtifact.model_validate_json(json.dumps(artifact_payload))
    assert error.value.errors()[0]["loc"] == (field,)


def test_artifact_rejects_extra_fields(artifact_payload):
    """Keep the complete artifact free of undocumented domain fields."""
    artifact_payload["owner"] = "Synthetic owner"
    with pytest.raises(ValidationError) as error:
        BusinessArtifact.model_validate_json(json.dumps(artifact_payload))
    assert error.value.errors()[0]["loc"] == ("owner",)


def test_json_schemas_describe_exact_contracts():
    """Advertise only the required contract fields and forbid extra properties."""
    contracts = [
        (AnalyzeBusinessModelInput, {"businessContent"}),
        (BusinessModel, set(BUSINESS_MODEL_SECTIONS)),
        (GeneratedBusinessArtifact, {"name", "businessModel"}),
        (
            BusinessArtifact,
            {"id", "name", "uri", "createdAt", "updatedAt", "businessModel"},
        ),
    ]
    for model, expected_fields in contracts:
        schema = model.model_json_schema()
        assert set(schema["properties"]) == expected_fields
        assert set(schema["required"]) == expected_fields
        assert schema["additionalProperties"] is False
