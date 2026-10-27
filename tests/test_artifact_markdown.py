"""CommonMark structure and content checks for Business Artifact views."""

import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime

import pytest
from markdown_it import MarkdownIt

from catalyst_mcp.markdown_views import render_business_artifact
from catalyst_mcp.models import BusinessArtifact, BusinessModel
from catalyst_mcp.repository import SQLiteRepository


SECTION_HEADINGS = (
    "End users", "Economic buyers", "Decision makers", "Solutions", "Benefits",
    "Channels", "Relationships", "Business resources", "Activities", "Partnerships",
    "Revenues and advantages", "Costs and risks",
)


@pytest.fixture
def artifact() -> BusinessArtifact:
    """Supply a synthetic artifact with distinguishable content in every section."""
    sections = {
        field: [f"Synthetic statement for {field}"]
        for field in BusinessModel.model_fields
    }
    sections["activities"] = ["Repair bicycles", "Inspect repaired bicycles"]
    timestamp = datetime(2026, 1, 1, 12, 30, 45, 123456, tzinfo=UTC)
    return BusinessArtifact(
        id="ba_demo", name="Northstar Bikes",
        uri="catalyst://business-artifact/ba_demo",
        createdAt=timestamp, updatedAt=timestamp, businessModel=sections,
    )


def _parsed_view(markdown: str) -> dict[str, list[str]]:
    """Recover parsed text by heading and reject structure outside the template."""
    tokens = MarkdownIt("commonmark", {"html": True}).parse(markdown)
    allowed_blocks = {
        "heading_open", "heading_close", "inline", "paragraph_open", "paragraph_close",
        "bullet_list_open", "bullet_list_close", "list_item_open", "list_item_close",
    }
    allowed_inlines = {"text", "hardbreak", "strong_open", "strong_close"}
    result = {}
    current_heading = None
    for index, token in enumerate(tokens):
        assert token.type in allowed_blocks, token.type
        if token.type == "inline":
            assert all(child.type in allowed_inlines for child in token.children or [])
        if token.type == "heading_open":
            current_heading = tokens[index + 1].content
            assert current_heading not in result
            result[current_heading] = []
        elif token.type == "inline" and tokens[index - 1].type == "paragraph_open":
            assert current_heading is not None
            result[current_heading].append(
                "".join(
                    "\n" if child.type == "hardbreak" else child.content
                    for child in token.children or []
                )
            )
    return result


def test_includes_complete_metadata_and_all_sections(artifact):
    """Include every field, all 12 sections and every statement in saved order."""
    markdown = render_business_artifact(artifact)
    parsed = _parsed_view(markdown)
    data = artifact.model_dump(mode="json")
    assert tuple(parsed) == ("Business Artifact", *SECTION_HEADINGS)
    assert parsed["Business Artifact"] == [
        f"Name: {data['name']}",
        f"ID: {data['id']}",
        f"Canonical JSON URI: {data['uri']}",
        f"Created at: {data['createdAt']}",
        f"Updated at: {data['updatedAt']}",
    ]
    for field, heading in zip(BusinessModel.model_fields, SECTION_HEADINGS, strict=True):
        assert parsed[heading] == data["businessModel"][field]
    assert markdown.endswith("\n")


@pytest.mark.parametrize("field", tuple(BusinessModel.model_fields))
def test_labels_each_empty_section(artifact, field):
    """Keep an empty section present and explicitly label its missing content."""
    setattr(artifact.businessModel, field, [])
    parsed = _parsed_view(render_business_artifact(artifact))
    heading = SECTION_HEADINGS[tuple(BusinessModel.model_fields).index(field)]
    assert parsed[heading] == ["Not specified"]
    assert tuple(parsed) == ("Business Artifact", *SECTION_HEADINGS)


@pytest.mark.parametrize("location", ["name", "id", "statement"])
@pytest.mark.parametrize(
    "value",
    [
        r"\ * _ { } [ ] ( ) # + - . ! | ~ =",
        "A & B < C > D &amp; &#35; &lt;script&gt;",
        '<script>alert("synthetic")</script><img src=x onerror="alert(1)">',
        "[click](javascript:alert(1)) ![image](https://example.invalid/x)",
        "# Fake heading\n---\n> Fake quote\n1. fake list\n- fake list\n~~~\n```\n[value]: url",
        "First line\nSecond line",
        "\nFirst\n\nLast\n\n",
        "  leading and trailing  ",
        "First\n    indented\n\n  \nLast",
        "Tabs:\tvalue\r\nNext line\rEnd",
        "**Not specified**",
        "Café — فارسی — 🚲",
        "A backslash\\\nnext\\\n",
        "Ends with a newline\n",
    ],
)
def test_supplied_text_stays_literal_and_complete(artifact, location, value):
    """Preserve text and whitespace without introducing Markdown or active HTML."""
    if location == "name":
        artifact.name = value
    elif location == "id":
        artifact.id = value
        artifact.uri = f"catalyst://business-artifact/{value}"
    else:
        artifact.businessModel.activities = [value]
    parsed = _parsed_view(render_business_artifact(artifact))
    assert tuple(parsed) == ("Business Artifact", *SECTION_HEADINGS)
    if location == "name":
        assert parsed["Business Artifact"][0] == f"Name: {value}"
    elif location == "id":
        assert parsed["Business Artifact"][1] == f"ID: {value}"
        assert parsed["Business Artifact"][2] == f"Canonical JSON URI: {artifact.uri}"
    else:
        assert parsed["Activities"] == [value]


def test_preserves_long_content_and_duplicate_statements(artifact):
    """Render the full array without truncating, summarizing or deduplicating it."""
    statement = "Detailed synthetic repair process. " * 300 + "Finish."
    artifact.businessModel.activities = [statement, statement, "Final inspection"]
    parsed = _parsed_view(render_business_artifact(artifact))
    assert parsed["Activities"] == artifact.businessModel.activities


def test_rendering_is_deterministic_and_does_not_mutate_input(artifact):
    """Produce the same view repeatedly and from an equivalent JSON-loaded record."""
    original_json = artifact.model_dump_json()
    first = render_business_artifact(artifact)
    assert render_business_artifact(artifact) == first
    reloaded = BusinessArtifact.model_validate_json(original_json)
    assert render_business_artifact(reloaded) == first
    assert artifact.model_dump_json() == original_json


def test_saved_view_survives_restart_without_storage_changes(artifact, tmp_path):
    """Render after a process restart while leaving saved JSON and files unchanged."""
    database_path = tmp_path / "catalyst.sqlite3"
    repository = SQLiteRepository(database_path)
    repository.save_business_artifact(artifact)
    original_json = artifact.model_dump_json()
    original_files = set(tmp_path.iterdir())
    expected = render_business_artifact(repository.get_business_artifact(artifact.id))
    reopened = SQLiteRepository(database_path)
    assert render_business_artifact(reopened.get_business_artifact(artifact.id)) == expected
    script = (
        "import sys\n"
        "from catalyst_mcp.repository import SQLiteRepository\n"
        "from catalyst_mcp.markdown_views import render_business_artifact\n"
        "artifact = SQLiteRepository(sys.argv[1]).get_business_artifact(sys.argv[2])\n"
        "sys.stdout.write(render_business_artifact(artifact))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(database_path), artifact.id],
        cwd=tmp_path, capture_output=True, text=True, check=True, timeout=10,
    )
    assert result.stdout == expected
    with closing(sqlite3.connect(database_path, autocommit=True)) as connection:
        stored_json = connection.execute(
            "SELECT payload_json FROM business_artifacts WHERE id = ?", (artifact.id,)
        ).fetchone()[0]
        assert connection.execute("SELECT COUNT(*) FROM use_case_catalogs").fetchone() == (0,)
    assert stored_json == original_json
    assert artifact.model_dump_json() == original_json
    assert set(tmp_path.iterdir()) == original_files
