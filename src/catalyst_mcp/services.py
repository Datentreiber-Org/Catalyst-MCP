"""Validated generation workflows that return complete committed records."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from catalyst_mcp.llm_client import AnalysisProvider, IdeationProvider
from catalyst_mcp.models import (
    AnalyzeBusinessModelInput,
    BusinessArtifact,
    GeneratedBusinessArtifact,
    GeneratedUseCaseCatalog,
    IdeateUseCaseInput,
    UseCase,
    UseCaseCatalog,
)
from catalyst_mcp.repository import SQLiteRepository


class SourceArtifactNotFoundError(LookupError):
    """The requested saved source is missing before ideation generation starts."""


DEFAULT_MAX_BUSINESS_CONTENT_CHARS = 20_000
DEFAULT_MAX_NUMBER_OF_IDEAS = 10

_ANALYSIS_CORRECTION = (
    "Return valid JSON with only name and businessModel. "
    "Use a non-blank name and all 12 businessModel sections as arrays of "
    "non-blank strings. Keep unsupported sections empty and include only "
    "source-supported statements. Do not include IDs, URIs or timestamps."
)

_IDEATION_CORRECTION = (
    "Return valid JSON containing only useCases, with exactly the requested number of ideas. "
    "Each case requires non-blank title, focus, problem and proposedSolution, "
    "a targetUsers array of non-blank strings, and at least one businessElementAlignment. "
    "Each alignment requires section, element and a non-blank rationale. "
    "Copy section keys and element strings exactly from the supplied source businessModel. "
    "Honor the requested focus. Do not include IDs, timestamps, URIs or source metadata."
)


def analyze_business_model(
    business_content: str,
    *,
    provider: AnalysisProvider,
    repository: SQLiteRepository,
    max_business_content_chars: int = DEFAULT_MAX_BUSINESS_CONTENT_CHARS,
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


def _validate_generated_use_cases(
    generated: GeneratedUseCaseCatalog,
    source: BusinessArtifact,
    number_of_ideas: int,
) -> None:
    """Check the requested count and every exact reference to the saved source."""
    if len(generated.useCases) != number_of_ideas:
        raise ValueError("Generated use-case count must match numberOfIdeas")
    for case in generated.useCases:
        for alignment in case.businessElementAlignment:
            if alignment.element not in getattr(source.businessModel, alignment.section):
                raise ValueError("Alignment element must exactly match its source section")


def ideate_use_case(
    artifact_id: str,
    number_of_ideas: int,
    *,
    provider: IdeationProvider,
    repository: SQLiteRepository,
    focus: str | None = None,
    max_number_of_ideas: int = DEFAULT_MAX_NUMBER_OF_IDEAS,
) -> UseCaseCatalog:
    """Generate validated ideas from a saved artifact and return a committed Catalog."""
    if type(max_number_of_ideas) is not int or max_number_of_ideas < 1:
        raise ValueError("max_number_of_ideas must be a positive integer")
    request = IdeateUseCaseInput(
        artifactId=artifact_id, numberOfIdeas=number_of_ideas, focus=focus
    )
    if request.numberOfIdeas > max_number_of_ideas:
        raise ValueError(f"numberOfIdeas exceeds maximum of {max_number_of_ideas}")
    source = repository.get_business_artifact(request.artifactId)
    if source is None:
        raise SourceArtifactNotFoundError("Source Business Artifact was not found")

    source_json = source.model_dump_json()
    correction = None
    for _ in range(2):
        response = provider.generate_use_cases(
            source_json, request.numberOfIdeas, focus=request.focus, correction=correction
        )
        try:
            generated = GeneratedUseCaseCatalog.model_validate_json(response)
            _validate_generated_use_cases(generated, source, request.numberOfIdeas)
        except ValueError:
            correction = _IDEATION_CORRECTION
            continue

        timestamp = datetime.now(UTC)
        catalog = UseCaseCatalog(
            id=f"uc_catalog_{uuid4().hex}",
            createdAt=timestamp,
            updatedAt=timestamp,
            sourceArtifact={"id": source.id},
            useCases=[
                UseCase(id=f"uc_{uuid4().hex}", **case.model_dump())
                for case in generated.useCases
            ],
        )
        return repository.save_use_case_catalog(catalog)

    raise RuntimeError(
        "Ideation provider returned invalid Use-case Catalog content after two attempts"
    )
