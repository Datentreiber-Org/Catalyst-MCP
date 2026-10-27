"""Validated generation workflows that return complete committed records."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from catalyst_mcp.llm_client import AnalysisProvider
from catalyst_mcp.models import (
    AnalyzeBusinessModelInput,
    BusinessArtifact,
    GeneratedBusinessArtifact,
)
from catalyst_mcp.repository import SQLiteRepository


_ANALYSIS_CORRECTION = (
    "Return valid JSON with only name and businessModel. "
    "Use a non-blank name and all 12 businessModel sections as arrays of "
    "non-blank strings. Keep unsupported sections empty and include only "
    "source-supported statements. Do not include IDs, URIs or timestamps."
)


def analyze_business_model(
    business_content: str,
    *,
    provider: AnalysisProvider,
    repository: SQLiteRepository,
    max_business_content_chars: int = 20_000,
) -> BusinessArtifact:
    """Validate analysis output, add metadata and return only after commit."""
    if type(max_business_content_chars) is not int or max_business_content_chars < 1:
        raise ValueError("max_business_content_chars must be a positive integer")
    request = AnalyzeBusinessModelInput(businessContent=business_content)
    if len(request.businessContent) > max_business_content_chars:
        raise ValueError(
            f"businessContent exceeds maximum of {max_business_content_chars} characters"
        )

    correction = None
    for _ in range(2):
        response = provider.generate_business_model(
            request.businessContent, correction=correction
        )
        try:
            generated = GeneratedBusinessArtifact.model_validate_json(response)
        except ValidationError as error:
            if any(
                detail["type"] == "empty_business_model"
                for detail in error.errors(
                    include_input=False, include_context=False, include_url=False
                )
            ):
                raise ValueError(
                    "Insufficient business content: generated business model is empty"
                ) from None
            correction = _ANALYSIS_CORRECTION
            continue

        artifact_id = f"ba_{uuid4().hex}"
        timestamp = datetime.now(UTC)
        artifact = BusinessArtifact(
            id=artifact_id,
            name=generated.name,
            uri=f"catalyst://business-artifact/{artifact_id}",
            createdAt=timestamp,
            updatedAt=timestamp,
            businessModel=generated.businessModel,
        )
        return repository.save_business_artifact(artifact)

    raise RuntimeError(
        "Analysis provider returned invalid Business Artifact content after two attempts"
    )
