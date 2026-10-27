"""Validated payloads for business-model analysis and use-case ideation."""

from datetime import timedelta
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pydantic_core import PydanticCustomError


NonBlankText = Annotated[str, StringConstraints(pattern=r"\S")]

BusinessModelSection = Literal[
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
]


class StrictModel(BaseModel):
    """Reject incorrect types and fields outside the declared payload."""

    model_config = ConfigDict(strict=True, extra="forbid")


class AnalyzeBusinessModelInput(StrictModel):
    """Business text supplied to the analysis tool."""

    businessContent: NonBlankText


class BusinessModel(StrictModel):
    """The complete 12-section model, including explicit empty sections."""

    endUsers: list[NonBlankText]
    economicBuyers: list[NonBlankText]
    decisionMakers: list[NonBlankText]
    solutions: list[NonBlankText]
    benefits: list[NonBlankText]
    channels: list[NonBlankText]
    relationships: list[NonBlankText]
    businessResources: list[NonBlankText]
    activities: list[NonBlankText]
    partnerships: list[NonBlankText]
    revenuesAndAdvantages: list[NonBlankText]
    costsAndRisks: list[NonBlankText]

    @model_validator(mode="after")
    def require_business_content(self) -> Self:
        """Reject a model with no statements in any section."""
        if not any(self.model_dump().values()):
            raise PydanticCustomError(
                "empty_business_model",
                "businessModel must contain at least one statement",
            )
        return self


class GeneratedBusinessArtifact(StrictModel):
    """Business content that the model may generate, without system metadata."""

    name: NonBlankText
    businessModel: BusinessModel


class BusinessArtifact(StrictModel):
    """The complete record shape, with metadata supplied by backend code."""

    id: NonBlankText
    name: NonBlankText
    uri: NonBlankText
    createdAt: AwareDatetime
    updatedAt: AwareDatetime
    businessModel: BusinessModel

    @model_validator(mode="after")
    def validate_metadata(self) -> Self:
        """Check the canonical URI and create-only UTC timestamp rules."""
        if self.uri != f"catalyst://business-artifact/{self.id}":
            raise ValueError("uri must be the canonical JSON URI for the artifact id")
        for timestamp in (self.createdAt, self.updatedAt):
            if timestamp.utcoffset() != timedelta(0):
                raise ValueError("createdAt and updatedAt must use UTC")
        if self.createdAt != self.updatedAt:
            raise ValueError("createdAt and updatedAt must be equal at creation")
        return self


class IdeateUseCaseInput(StrictModel):
    """Source identifier, requested count and optional ideation focus."""

    artifactId: NonBlankText
    numberOfIdeas: Annotated[int, Field(ge=1)]
    focus: NonBlankText | None = None


class BusinessElementAlignment(StrictModel):
    """An alignment reference whose source-element match is checked later."""

    section: BusinessModelSection
    element: NonBlankText
    rationale: NonBlankText


class GeneratedUseCase(StrictModel):
    """Use-case content that the model may generate, without a case ID."""

    title: NonBlankText
    focus: NonBlankText
    problem: NonBlankText
    targetUsers: list[NonBlankText]
    proposedSolution: NonBlankText
    businessElementAlignment: Annotated[
        list[BusinessElementAlignment], Field(min_length=1)
    ]


class GeneratedUseCaseCatalog(StrictModel):
    """Generated cases before backend metadata and source association are added."""

    useCases: Annotated[list[GeneratedUseCase], Field(min_length=1)]


class UseCase(GeneratedUseCase):
    """The generated content fields plus a required backend-supplied case ID."""

    id: NonBlankText


class SourceArtifactReference(StrictModel):
    """The source association carried by a complete Catalog payload."""

    id: NonBlankText


class UseCaseCatalog(StrictModel):
    """The complete Catalog shape with metadata supplied by backend code."""

    id: NonBlankText
    createdAt: AwareDatetime
    updatedAt: AwareDatetime
    sourceArtifact: SourceArtifactReference
    useCases: Annotated[list[UseCase], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_metadata(self) -> Self:
        """Check create-only UTC timestamps and unique case identifiers."""
        for timestamp in (self.createdAt, self.updatedAt):
            if timestamp.utcoffset() != timedelta(0):
                raise ValueError("createdAt and updatedAt must use UTC")
        if self.createdAt != self.updatedAt:
            raise ValueError("createdAt and updatedAt must be equal at creation")
        case_ids = [case.id for case in self.useCases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("use-case ids must be unique within the catalog")
        return self
