"""Deterministic Markdown views of complete saved records."""

from html import escape

from catalyst_mcp.models import BusinessArtifact


_BUSINESS_MODEL_SECTIONS = (
    ("endUsers", "End users"),
    ("economicBuyers", "Economic buyers"),
    ("decisionMakers", "Decision makers"),
    ("solutions", "Solutions"),
    ("benefits", "Benefits"),
    ("channels", "Channels"),
    ("relationships", "Relationships"),
    ("businessResources", "Business resources"),
    ("activities", "Activities"),
    ("partnerships", "Partnerships"),
    ("revenuesAndAdvantages", "Revenues and advantages"),
    ("costsAndRisks", "Costs and risks"),
)

_MARKDOWN_ESCAPES = str.maketrans(
    {character: f"\\{character}" for character in "\\`*_{}[]()#+-.!|~="}
)


def _escape_markdown(value: str) -> str:
    """Keep supplied text literal within a bullet, including its whitespace."""
    trailing_newlines = len(value) - len(value.rstrip("\n"))
    lines = []
    for line in value.rstrip("\n").split("\n"):
        escaped = escape(line.translate(_MARKDOWN_ESCAPES), quote=False)
        escaped = escaped.replace("\t", "&#9;").replace("\r", "&#13;")
        content = escaped.strip(" ")
        if content:
            leading_spaces = len(escaped) - len(escaped.lstrip(" "))
            trailing_spaces = len(escaped) - len(escaped.rstrip(" "))
            escaped = "&#32;" * leading_spaces + content + "&#32;" * trailing_spaces
        else:
            escaped = "&#32;" * len(escaped)
        lines.append(escaped)
    return "\\\n  ".join(lines) + "&#10;" * trailing_newlines


def render_business_artifact(artifact: BusinessArtifact) -> str:
    """Render every artifact field in a fixed template without changing the record."""
    data = artifact.model_dump(mode="json")
    metadata = (
        ("Name", data["name"]),
        ("ID", data["id"]),
        ("Canonical JSON URI", data["uri"]),
        ("Created at", data["createdAt"]),
        ("Updated at", data["updatedAt"]),
    )
    lines = ["# Business Artifact", ""]
    for label, value in metadata:
        lines.append(f"- **{label}:** {_escape_markdown(value)}")
    for field, heading in _BUSINESS_MODEL_SECTIONS:
        lines.extend(["", f"## {heading}", ""])
        elements = data["businessModel"][field]
        if elements:
            lines.extend(f"- {_escape_markdown(element)}" for element in elements)
        else:
            lines.append("Not specified")
    return "\n".join(lines) + "\n"
