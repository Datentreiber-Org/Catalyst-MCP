"""Validated payloads for business-model analysis."""

from datetime import timedelta
from typing import Annotated, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StringConstraints,
    model_validator,
)


NonBlankText = Annotated[str, StringConstraints(pattern=r"\S")]


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
            raise ValueError("businessModel must contain at least one statement")
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
