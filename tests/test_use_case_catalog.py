"""Ideation and Catalog contract checks using synthetic workshop ideas."""

import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from catalyst_mcp.models import (
    BusinessElementAlignment,
    BusinessModel,
    GeneratedUseCase,
    GeneratedUseCaseCatalog,
    IdeateUseCaseInput,
    SourceArtifactReference,
    UseCase,
    UseCaseCatalog,
)


CASE_CONTENT_FIELDS = {
    "title", "focus", "problem", "targetUsers", "proposedSolution",
    "businessElementAlignment",
}


@pytest.fixture
def generated_case_payload() -> dict[str, Any]:
    """Supply one fresh synthetic idea with an alignment reference."""
    return {
        "title": "Repair request triage",
        "focus": "Workshop efficiency",
        "problem": "Staff manually route repair requests.",
        "targetUsers": ["Workshop staff"],
        "proposedSolution": "Classify repair requests and suggest a work queue.",
        "businessElementAlignment": [
            {
                "section": "activities",
                "element": "Repair bicycles",
                "rationale": "Routes repair work to workshop staff.",
            }
        ],
    }


@pytest.fixture
def catalog_payload(generated_case_payload) -> dict[str, Any]:
    """Add fixed metadata to form a complete synthetic Catalog JSON payload."""
    return {
        "id": "uc_catalog_demo",
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
        "sourceArtifact": {"id": "ba_demo"},
        "useCases": [{"id": "uc_demo", **generated_case_payload}],
    }


@pytest.mark.parametrize(
    "optional_fields", [{}, {"focus": None}, {"focus": "  Workshop efficiency\n"}]
)
def test_input_preserves_optional_focus(optional_fields):
    """Accept omitted or null focus and preserve any supplied non-blank text."""
    payload = {"artifactId": "ba_demo", "numberOfIdeas": 1, **optional_fields}
    request = IdeateUseCaseInput.model_validate(payload)
    assert request.model_dump() == {
        "artifactId": "ba_demo", "numberOfIdeas": 1,
        "focus": optional_fields.get("focus"),
    }


def test_input_defers_configurable_upper_count_limit():
    """Keep a runtime-configurable upper limit out of the standalone schema."""
    request = IdeateUseCaseInput(artifactId="ba_demo", numberOfIdeas=11)
    assert request.numberOfIdeas == 11


@pytest.mark.parametrize(
    "updates",
    [
        {"artifactId": ""}, {"artifactId": " \n"}, {"artifactId": 123},
        {"artifactId": None}, {"numberOfIdeas": 0}, {"numberOfIdeas": -1},
        {"numberOfIdeas": True}, {"numberOfIdeas": False},
        {"numberOfIdeas": "1"}, {"numberOfIdeas": 1.0}, {"numberOfIdeas": None},
        {"focus": ""}, {"focus": " \t"}, {"focus": 123}, {"focus": []},
        {"extra": True},
    ],
)
def test_input_rejects_invalid_fields(updates):
    """Reject invalid identifiers, counts, focus values and undocumented fields."""
    payload = {"artifactId": "ba_demo", "numberOfIdeas": 1}
    with pytest.raises(ValidationError):
        IdeateUseCaseInput.model_validate(payload | updates)


@pytest.mark.parametrize("field", ["artifactId", "numberOfIdeas"])
def test_input_requires_source_and_count(field):
    """Require both arguments even when the optional focus is omitted."""
    payload = {"artifactId": "ba_demo", "numberOfIdeas": 1}
    del payload[field]
    with pytest.raises(ValidationError) as error:
        IdeateUseCaseInput.model_validate(payload)
    assert error.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize("section", tuple(BusinessModel.model_fields))
def test_alignment_accepts_exact_section_names(section):
    """Accept each section name structurally; matching its source comes later."""
    payload = {"section": section, "element": "Repair bicycles", "rationale": "Helps staff."}
    assert BusinessElementAlignment.model_validate(payload).model_dump() == payload


@pytest.mark.parametrize(
    "updates",
    [
        {"section": "Activities"}, {"section": "business_resources"},
        {"section": "unknown"}, {"section": None}, {"section": 123},
        {"element": ""}, {"element": " \n"}, {"element": 123},
        {"rationale": ""}, {"rationale": None}, {"extra": True},
    ],
)
def test_alignment_rejects_invalid_fields(generated_case_payload, updates):
    """Reject unknown section names, blank content and unexpected fields."""
    payload = generated_case_payload["businessElementAlignment"][0]
    with pytest.raises(ValidationError):
        BusinessElementAlignment.model_validate(payload | updates)


@pytest.mark.parametrize("field", ["section", "element", "rationale"])
def test_alignment_requires_every_field(generated_case_payload, field):
    """Require all three parts of an alignment entry."""
    payload = generated_case_payload["businessElementAlignment"][0]
    del payload[field]
    with pytest.raises(ValidationError) as error:
        BusinessElementAlignment.model_validate(payload)
    assert error.value.errors()[0]["loc"] == (field,)


def test_generated_catalog_preserves_content(generated_case_payload):
    """Preserve the complete generated shape, including an empty target-user list."""
    generated_case_payload["targetUsers"] = []
    payload = {"useCases": [generated_case_payload]}
    generated = GeneratedUseCaseCatalog.model_validate(payload)
    assert generated.model_dump() == payload


@pytest.mark.parametrize("field", ["title", "focus", "problem", "proposedSolution"])
@pytest.mark.parametrize("value", ["", " \t\n", None, 123])
def test_generated_case_requires_nonblank_text(generated_case_payload, field, value):
    """Require text content without coercing or accepting blank statements."""
    generated_case_payload[field] = value
    with pytest.raises(ValidationError) as error:
        GeneratedUseCase.model_validate(generated_case_payload)
    assert error.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("targetUsers", None), ("targetUsers", "Workshop staff"),
        ("targetUsers", ("Workshop staff",)), ("targetUsers", [123]),
        ("targetUsers", [" \n"]), ("businessElementAlignment", []),
        ("businessElementAlignment", None), ("businessElementAlignment", {}),
        ("businessElementAlignment", [{}]),
    ],
)
def test_generated_case_rejects_invalid_arrays(generated_case_payload, field, value):
    """Validate user arrays and require at least one complete alignment entry."""
    generated_case_payload[field] = value
    with pytest.raises(ValidationError) as error:
        GeneratedUseCase.model_validate(generated_case_payload)
    assert error.value.errors()[0]["loc"][0] == field


@pytest.mark.parametrize("field", sorted(CASE_CONTENT_FIELDS))
def test_generated_case_requires_every_field(generated_case_payload, field):
    """Keep every documented content field required, including targetUsers."""
    del generated_case_payload[field]
    with pytest.raises(ValidationError) as error:
        GeneratedUseCase.model_validate(generated_case_payload)
    assert error.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize("value", [[], None, {}, [{}], ("case",)])
def test_generated_catalog_requires_cases(value):
    """Require a non-empty array of complete generated use cases."""
    with pytest.raises(ValidationError):
        GeneratedUseCaseCatalog(useCases=value)


@pytest.mark.parametrize(
    ("model", "field"),
    [
        (GeneratedUseCase, "id"), (GeneratedUseCase, "createdAt"),
        (GeneratedUseCaseCatalog, "id"), (GeneratedUseCaseCatalog, "createdAt"),
        (GeneratedUseCaseCatalog, "updatedAt"),
        (GeneratedUseCaseCatalog, "sourceArtifact"), (GeneratedUseCaseCatalog, "uri"),
    ],
)
def test_generated_payloads_reject_metadata(generated_case_payload, model, field):
    """Keep IDs, timestamps and source associations outside provider content."""
    payload = (
        generated_case_payload if model is GeneratedUseCase
        else {"useCases": [generated_case_payload]}
    )
    with pytest.raises(ValidationError) as error:
        model.model_validate(payload | {field: "model-supplied metadata"})
    assert error.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize("value", [None, "", " \n", 123])
def test_complete_case_requires_nonblank_id(generated_case_payload, value):
    """Require a usable backend-supplied ID on the complete case."""
    with pytest.raises(ValidationError):
        UseCase.model_validate({"id": value, **generated_case_payload})


def test_catalog_json_round_trip_preserves_content(catalog_payload):
    """Preserve every field, special characters and the order of nested arrays."""
    first_case = catalog_payload["useCases"][0]
    first_case["targetUsers"] = ["Workshop staff", "  Café riders\n<all ages> & friends  "]
    first_case["businessElementAlignment"].append(
        {"section": "solutions", "element": "Bicycle repairs", "rationale": "Preserve *text*."}
    )
    second_case = deepcopy(first_case)
    second_case["id"] = "uc_second"
    second_case["title"] = "Repair queue forecast"
    catalog_payload["useCases"].append(second_case)
    catalog = UseCaseCatalog.model_validate_json(json.dumps(catalog_payload))
    assert catalog.model_dump(mode="json") == catalog_payload
    serialized = catalog.model_dump_json()
    assert json.loads(serialized) == catalog_payload
    assert UseCaseCatalog.model_validate_json(serialized) == catalog


def test_catalog_accepts_backend_datetime_values(catalog_payload):
    """Accept UTC datetime objects supplied directly by backend code."""
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    catalog_payload.update(createdAt=timestamp, updatedAt=timestamp)
    catalog = UseCaseCatalog.model_validate(catalog_payload)
    assert catalog.createdAt == catalog.updatedAt == timestamp


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", ""), ("id", " \t"), ("id", 123),
        ("createdAt", "2026-01-01T00:00:00"),
        ("updatedAt", "2026-01-01T00:00:00"),
        ("createdAt", "2026-01-01T01:00:00+01:00"),
        ("updatedAt", "2026-01-01T01:00:00+01:00"),
        ("updatedAt", "2026-01-02T00:00:00Z"),
        ("createdAt", 1767225600), ("updatedAt", None),
        ("sourceArtifact", {}), ("sourceArtifact", {"id": ""}),
        ("sourceArtifact", {"id": 123}),
        ("sourceArtifact", {"id": "ba_demo", "uri": "catalyst://business-artifact/ba_demo"}),
        ("useCases", []), ("useCases", None),
        ("uri", "catalyst://use-case-catalog/uc_catalog_demo"),
        ("extra", True),
    ],
)
def test_catalog_rejects_invalid_fields(catalog_payload, field, value):
    """Reject inconsistent timestamps, invalid source references and extra fields."""
    catalog_payload[field] = value
    with pytest.raises(ValidationError):
        UseCaseCatalog.model_validate_json(json.dumps(catalog_payload))


@pytest.mark.parametrize("field", ["id", "createdAt", "updatedAt", "sourceArtifact", "useCases"])
def test_catalog_requires_every_field(catalog_payload, field):
    """Require complete metadata and cases instead of generating defaults."""
    del catalog_payload[field]
    with pytest.raises(ValidationError) as error:
        UseCaseCatalog.model_validate_json(json.dumps(catalog_payload))
    assert error.value.errors()[0]["loc"] == (field,)


def test_catalog_rejects_missing_case_id(catalog_payload):
    """Require IDs on nested complete cases as well as on the catalog."""
    del catalog_payload["useCases"][0]["id"]
    with pytest.raises(ValidationError) as error:
        UseCaseCatalog.model_validate_json(json.dumps(catalog_payload))
    assert error.value.errors()[0]["loc"] == ("useCases", 0, "id")


def test_catalog_rejects_duplicate_case_ids(catalog_payload):
    """Prevent two cases in one catalog from sharing an identifier."""
    catalog_payload["useCases"].append(deepcopy(catalog_payload["useCases"][0]))
    with pytest.raises(ValidationError, match="ids must be unique"):
        UseCaseCatalog.model_validate_json(json.dumps(catalog_payload))


def test_json_schemas_describe_exact_contracts():
    """Describe required fields, section names and non-empty array constraints."""
    contracts = [
        (IdeateUseCaseInput, {"artifactId", "numberOfIdeas", "focus"}),
        (BusinessElementAlignment, {"section", "element", "rationale"}),
        (GeneratedUseCase, CASE_CONTENT_FIELDS),
        (GeneratedUseCaseCatalog, {"useCases"}),
        (UseCase, CASE_CONTENT_FIELDS | {"id"}),
        (SourceArtifactReference, {"id"}),
        (UseCaseCatalog, {"id", "createdAt", "updatedAt", "sourceArtifact", "useCases"}),
    ]
    for model, expected_fields in contracts:
        schema = model.model_json_schema()
        required_fields = expected_fields - {"focus"} if model is IdeateUseCaseInput else expected_fields
        assert set(schema["properties"]) == expected_fields
        assert set(schema["required"]) == required_fields
        assert schema["additionalProperties"] is False
    alignment_schema = BusinessElementAlignment.model_json_schema()
    assert alignment_schema["properties"]["section"]["enum"] == list(BusinessModel.model_fields)
    case_schema = GeneratedUseCase.model_json_schema()
    assert case_schema["properties"]["businessElementAlignment"]["minItems"] == 1
    for model in (GeneratedUseCaseCatalog, UseCaseCatalog):
        assert model.model_json_schema()["properties"]["useCases"]["minItems"] == 1
    count_schema = IdeateUseCaseInput.model_json_schema()["properties"]["numberOfIdeas"]
    assert count_schema["minimum"] == 1
    assert "maximum" not in count_schema
