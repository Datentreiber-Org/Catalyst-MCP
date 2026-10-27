"""CommonMark completeness and content checks for Use-case Catalog views."""

import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime

import pytest
from markdown_it import MarkdownIt

from catalyst_mcp.markdown_views import render_use_case_catalog
from catalyst_mcp.models import BusinessArtifact, BusinessModel, UseCaseCatalog
from catalyst_mcp.repository import SQLiteRepository


@pytest.fixture
def catalog() -> UseCaseCatalog:
    """Supply two distinguishable cases, each with multiple users and alignments."""
    timestamp = datetime(2026, 1, 1, 12, 30, 45, 123456, tzinfo=UTC)
    return UseCaseCatalog(
        id="uc_catalog_demo", createdAt=timestamp, updatedAt=timestamp,
        sourceArtifact={"id": "ba_demo"},
        useCases=[
            {
                "id": f"uc_{number}",
                "title": f"Repair idea {number}",
                "focus": f"Workshop focus {number}",
                "problem": f"Repair problem {number}",
                "targetUsers": [f"Workshop team {number}", f"Rider group {number}"],
                "proposedSolution": f"Proposed repair solution {number}",
                "businessElementAlignment": [
                    {
                        "section": "activities", "element": "Repair bicycles",
                        "rationale": f"Activity rationale {number}",
                    },
                    {
                        "section": "solutions", "element": "Bicycle repairs",
                        "rationale": f"Solution rationale {number}",
                    },
                ],
            }
            for number in (1, 2)
        ],
    )


def _parsed_view(markdown: str) -> dict[tuple[str, ...], list[str]]:
    """Recover literal text by heading path and reject unexpected Markdown syntax."""
    tokens = MarkdownIt("commonmark", {"html": True}).parse(markdown)
    allowed_blocks = {
        "heading_open", "heading_close", "inline", "paragraph_open", "paragraph_close",
        "bullet_list_open", "bullet_list_close", "list_item_open", "list_item_close",
    }
    allowed_inlines = {"text", "hardbreak", "strong_open", "strong_close"}
    result = {}
    heading_path = []
    for index, token in enumerate(tokens):
        assert token.type in allowed_blocks, token.type
        if token.type == "inline":
            assert all(child.type in allowed_inlines for child in token.children or [])
        if token.type == "heading_open":
            level = int(token.tag[1:])
            assert level <= len(heading_path) + 1
            heading_path = heading_path[:level - 1] + [tokens[index + 1].content]
            assert tuple(heading_path) not in result
            result[tuple(heading_path)] = []
        elif token.type == "inline" and tokens[index - 1].type == "paragraph_open":
            assert heading_path
            result[tuple(heading_path)].append(
                "".join(
                    "\n" if child.type == "hardbreak" else child.content
                    for child in token.children or []
                )
            )
    return result


def test_includes_all_metadata_cases_users_and_alignments(catalog):
    """Include every saved field, the derived source URI and all array entries."""
    markdown = render_use_case_catalog(catalog)
    parsed = _parsed_view(markdown)
    data = catalog.model_dump(mode="json")
    root = ("Use-case Catalog",)
    assert parsed[root] == [
        f"ID: {data['id']}",
        f"Created at: {data['createdAt']}",
        f"Updated at: {data['updatedAt']}",
        f"Source artifact ID: {data['sourceArtifact']['id']}",
        f"Source artifact JSON URI: catalyst://business-artifact/{data['sourceArtifact']['id']}",
    ]
    expected_paths = [root]
    for case_number, case in enumerate(data["useCases"], start=1):
        case_path = (*root, f"Use case {case_number}")
        assert parsed[case_path] == [
            f"ID: {case['id']}", f"Title: {case['title']}",
            f"Focus: {case['focus']}", f"Problem: {case['problem']}",
        ]
        users_path = (*case_path, "Target users")
        solution_path = (*case_path, "Proposed solution")
        alignments_path = (*case_path, "Business element alignment")
        assert parsed[users_path] == case["targetUsers"]
        assert parsed[solution_path] == [case["proposedSolution"]]
        assert parsed[alignments_path] == []
        expected_paths.extend([case_path, users_path, solution_path, alignments_path])
        for alignment_number, alignment in enumerate(case["businessElementAlignment"], start=1):
            alignment_path = (*alignments_path, f"Alignment {alignment_number}")
            assert parsed[alignment_path] == [
                f"Section: {alignment['section']}", f"Element: {alignment['element']}",
                f"Rationale: {alignment['rationale']}",
            ]
            expected_paths.append(alignment_path)
    assert tuple(parsed) == tuple(expected_paths)
    assert markdown.endswith("\n")


@pytest.mark.parametrize("case_index", [0, 1])
def test_labels_empty_target_users(catalog, case_index):
    """Keep the Target users section explicit when its saved array is empty."""
    catalog.useCases[case_index].targetUsers = []
    parsed = _parsed_view(render_use_case_catalog(catalog))
    path = ("Use-case Catalog", f"Use case {case_index + 1}", "Target users")
    assert parsed[path] == ["Not specified"]


@pytest.mark.parametrize("section", tuple(BusinessModel.model_fields))
def test_alignment_section_keys_are_preserved(catalog, section):
    """Show exact machine-checkable section keys without translating their values."""
    catalog.useCases[0].businessElementAlignment[0].section = section
    parsed = _parsed_view(render_use_case_catalog(catalog))
    path = ("Use-case Catalog", "Use case 1", "Business element alignment", "Alignment 1")
    assert parsed[path][0] == f"Section: {section}"


@pytest.mark.parametrize(
    "value",
    [
        r"\ * _ { } [ ] ( ) # + - . ! | ~ =",
        "# Fake heading\n===\n> quote\n- list\n[click](javascript:alert(1))\n```",
        '<script>alert("synthetic")</script> &amp; &#35; Café فارسی 🚲',
        " \tfirst\r\n\n  second\n\n",
        "A backslash\\\nnext\\\n",
    ],
)
def test_supplied_text_stays_literal_in_every_free_text_field(catalog, value):
    """Preserve supplied text in metadata, users, case fields and alignment fields."""
    data = catalog.model_dump(mode="json")
    data["id"] = value
    data["sourceArtifact"]["id"] = value
    case = data["useCases"][0]
    for field in ("id", "title", "focus", "problem", "proposedSolution"):
        case[field] = value
    case["targetUsers"] = [value]
    for alignment in case["businessElementAlignment"]:
        alignment["element"] = value
        alignment["rationale"] = value
    modified = UseCaseCatalog.model_validate_json(json.dumps(data))
    parsed = _parsed_view(render_use_case_catalog(modified))
    root = ("Use-case Catalog",)
    assert parsed[root][0] == f"ID: {value}"
    assert parsed[root][3] == f"Source artifact ID: {value}"
    assert parsed[root][4] == f"Source artifact JSON URI: catalyst://business-artifact/{value}"
    case_path = (*root, "Use case 1")
    assert parsed[case_path] == [
        f"ID: {value}", f"Title: {value}", f"Focus: {value}", f"Problem: {value}",
    ]
    assert parsed[(*case_path, "Target users")] == [value]
    assert parsed[(*case_path, "Proposed solution")] == [value]
    for number in (1, 2):
        path = (*case_path, "Business element alignment", f"Alignment {number}")
        assert parsed[path][1:] == [f"Element: {value}", f"Rationale: {value}"]


def test_preserves_many_cases_long_text_and_duplicate_entries(catalog):
    """Render all cases and preserve long solutions, duplicate users and alignments."""
    first_case = catalog.useCases[0]
    catalog.useCases = [
        first_case.model_copy(deep=True, update={"id": f"uc_{number}"})
        for number in range(25)
    ]
    first_case = catalog.useCases[0]
    first_case.proposedSolution = "Detailed synthetic repair proposal. " * 300 + "Finish."
    first_case.targetUsers = ["Workshop staff", "Workshop staff"]
    first_case.businessElementAlignment.append(
        first_case.businessElementAlignment[0].model_copy(deep=True)
    )
    parsed = _parsed_view(render_use_case_catalog(catalog))
    for number, case in enumerate(catalog.useCases, start=1):
        path = ("Use-case Catalog", f"Use case {number}")
        assert parsed[path][0] == f"ID: {case.id}"
    first_path = ("Use-case Catalog", "Use case 1")
    assert parsed[(*first_path, "Target users")] == first_case.targetUsers
    assert parsed[(*first_path, "Proposed solution")] == [first_case.proposedSolution]
    first_alignment = (*first_path, "Business element alignment", "Alignment 1")
    duplicate_alignment = (*first_path, "Business element alignment", "Alignment 3")
    assert parsed[first_alignment] == parsed[duplicate_alignment]


def test_rendering_is_deterministic_without_payload_changes(catalog):
    """Produce identical output from equivalent records without adding URI fields."""
    original_json = catalog.model_dump_json()
    first = render_use_case_catalog(catalog)
    assert render_use_case_catalog(catalog) == first
    reloaded = UseCaseCatalog.model_validate_json(original_json)
    assert render_use_case_catalog(reloaded) == first
    assert catalog.model_dump_json() == original_json
    assert "uri" not in catalog.model_dump()
    assert "uri" not in catalog.sourceArtifact.model_dump()


def test_saved_view_survives_restart_without_changing_either_record(catalog, tmp_path):
    """Render a saved Catalog after restart while leaving both records and files intact."""
    sections = {section: [] for section in BusinessModel.model_fields}
    sections["activities"] = ["Repair bicycles"]
    sections["solutions"] = ["Bicycle repairs"]
    source = BusinessArtifact(
        id=catalog.sourceArtifact.id, name="Northstar Bikes",
        uri=f"catalyst://business-artifact/{catalog.sourceArtifact.id}",
        createdAt=catalog.createdAt, updatedAt=catalog.updatedAt, businessModel=sections,
    )
    database_path = tmp_path / "catalyst.sqlite3"
    repository = SQLiteRepository(database_path)
    repository.save_business_artifact(source)
    repository.save_use_case_catalog(catalog)
    original_catalog_json = catalog.model_dump_json()
    original_source_json = source.model_dump_json()
    original_files = set(tmp_path.iterdir())
    expected = render_use_case_catalog(repository.get_use_case_catalog(catalog.id))
    reopened = SQLiteRepository(database_path)
    assert render_use_case_catalog(reopened.get_use_case_catalog(catalog.id)) == expected
    script = (
        "import sys\n"
        "from catalyst_mcp.repository import SQLiteRepository\n"
        "from catalyst_mcp.markdown_views import render_use_case_catalog\n"
        "catalog = SQLiteRepository(sys.argv[1]).get_use_case_catalog(sys.argv[2])\n"
        "sys.stdout.write(render_use_case_catalog(catalog))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(database_path), catalog.id],
        cwd=tmp_path, capture_output=True, text=True, check=True, timeout=10,
    )
    assert result.stdout == expected
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        stored_catalog = connection.execute(
            "SELECT source_artifact_id, payload_json FROM use_case_catalogs WHERE id = ?",
            (catalog.id,),
        ).fetchone()
        stored_source = connection.execute(
            "SELECT payload_json FROM business_artifacts WHERE id = ?", (source.id,)
        ).fetchone()[0]
    assert stored_catalog == (source.id, original_catalog_json)
    assert stored_source == original_source_json
    assert catalog.model_dump_json() == original_catalog_json
    assert source.model_dump_json() == original_source_json
    assert set(tmp_path.iterdir()) == original_files
