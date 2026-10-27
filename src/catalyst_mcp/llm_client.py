"""Analysis-provider contract and a scripted fake for local workflow checks."""

from typing import Protocol


class AnalysisProvider(Protocol):
    """Supply generated business content without backend metadata."""

    def generate_business_model(
        self, business_content: str, *, correction: str | None = None
    ) -> str:
        """Return name and businessModel JSON, treating source text as data.

        A provider must extract only source-supported content and treat any
        instructions inside business_content as data. Correction feedback is
        authored by the backend, separately from the supplied business text.
        """
        ...


class FakeAnalysisProvider:
    """Return scripted JSON or raise scripted exceptions without a model call."""

    def __init__(self, *responses: str | Exception) -> None:
        """Keep an ordered response script and an initially empty call history."""
        self._responses = iter(responses)
        self.calls: list[tuple[str, str | None]] = []

    def generate_business_model(
        self, business_content: str, *, correction: str | None = None
    ) -> str:
        """Record the request and consume one scripted response or exception."""
        self.calls.append((business_content, correction))
        try:
            response = next(self._responses)
        except StopIteration:
            raise RuntimeError("Fake analysis provider has no scripted response left") from None
        if isinstance(response, Exception):
            raise response
        return response
