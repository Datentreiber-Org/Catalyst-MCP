"""Configured JSON generation, workflow contracts and scripted fakes."""

from typing import Protocol

import httpx2
from anthropic import APIError as AnthropicAPIError
from anthropic import APITimeoutError as AnthropicTimeoutError
from anthropic import Anthropic, transform_schema
from openai import APIError, APITimeoutError, OpenAI
from pydantic import BaseModel

from catalyst_mcp.settings import LLMSettings


class JSONClient(Protocol):
    """Supply completed JSON text for validation by the calling workflow."""

    def generate_json(
        self,
        *,
        instructions: str,
        input_text: str,
        output_model: type[BaseModel],
    ) -> str:
        """Keep trusted instructions separate from input data and request its schema."""
        ...


class OpenAIJSONClient:
    """Make one synchronous Responses request using explicit OpenAI settings."""

    def __init__(self, settings: LLMSettings) -> None:
        """Capture validated settings without opening a connection or making a call."""
        if settings.provider != "openai":
            raise ValueError("OpenAI client requires openai settings.")
        self._settings = settings

    def generate_json(
        self,
        *,
        instructions: str,
        input_text: str,
        output_model: type[BaseModel],
    ) -> str:
        """Return completed text unchanged; let the workflow validate domain content."""
        try:
            with OpenAI(
                api_key=self._settings.api_key.get_secret_value(),
                base_url="https://api.openai.com/v1",
                timeout=self._settings.timeout_seconds,
                max_retries=0,
            ) as client:
                response = client.responses.create(
                    model=self._settings.model,
                    max_output_tokens=self._settings.max_output_tokens,
                    instructions=instructions,
                    input=[{"role": "user", "content": input_text}],
                    text={"format": {
                        "type": "json_schema",
                        "name": output_model.__name__,
                        "schema": output_model.model_json_schema(),
                        "strict": True,
                    }},
                    store=False,
                )
        except APITimeoutError:
            raise TimeoutError("LLM request timed out.") from None
        except APIError:
            raise RuntimeError("LLM provider request failed.") from None

        if response.status != "completed":
            raise RuntimeError("LLM provider did not complete the response.")
        for item in response.output:
            if item.type == "message":
                if any(content.type == "refusal" for content in item.content):
                    raise RuntimeError("LLM provider refused the request.")
        text = response.output_text
        if not text or not text.strip():
            raise RuntimeError("LLM provider returned no text.")
        return text


class AnthropicJSONClient:
    """Make one synchronous Messages request using explicit Anthropic settings."""

    def __init__(self, settings: LLMSettings) -> None:
        """Capture matching provider settings without I/O."""
        if settings.provider != "anthropic":
            raise ValueError("Anthropic client requires anthropic settings.")
        self._settings = settings

    def generate_json(
        self,
        *,
        instructions: str,
        input_text: str,
        output_model: type[BaseModel],
    ) -> str:
        """Request schema-constrained text without parsing away workflow validation."""
        try:
            with Anthropic(
                api_key=self._settings.api_key.get_secret_value(),
                base_url="https://api.anthropic.com",
                timeout=self._settings.timeout_seconds,
                max_retries=0,
            ) as client:
                response = client.messages.create(
                    model=self._settings.model,
                    max_tokens=self._settings.max_output_tokens,
                    system=instructions,
                    messages=[{"role": "user", "content": input_text}],
                    output_config={"format": {
                        "type": "json_schema", "schema": transform_schema(output_model),
                    }},
                )
        except AnthropicTimeoutError:
            raise TimeoutError("LLM request timed out.") from None
        except AnthropicAPIError:
            raise RuntimeError("LLM provider request failed.") from None

        if response.stop_reason == "refusal":
            raise RuntimeError("LLM provider refused the request.")
        if response.stop_reason != "end_turn":
            raise RuntimeError("LLM provider did not complete the response.")
        text = "".join(block.text for block in response.content if block.type == "text")
        if not text.strip():
            raise RuntimeError("LLM provider returned no text.")
        return text


class OllamaJSONClient:
    """Request structured JSON from one explicitly configured Ollama server."""

    def __init__(self, settings: LLMSettings) -> None:
        """Capture local-provider settings without contacting or downloading a model."""
        if settings.provider != "ollama":
            raise ValueError("Ollama client requires ollama settings.")
        self._settings = settings

    def generate_json(
        self,
        *,
        instructions: str,
        input_text: str,
        output_model: type[BaseModel],
    ) -> str:
        """Make one non-streaming chat request and reject incomplete or malformed envelopes."""
        try:
            with httpx2.Client(
                base_url=str(self._settings.ollama_host),
                timeout=self._settings.timeout_seconds,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                response = client.post("/api/chat", json={
                    "model": self._settings.model,
                    "messages": [
                        {"role": "system", "content": instructions},
                        {"role": "user", "content": input_text},
                    ],
                    "format": output_model.model_json_schema(),
                    "stream": False,
                    "options": {"num_predict": self._settings.max_output_tokens},
                })
                response.raise_for_status()
                result = response.json()
        except httpx2.TimeoutException:
            raise TimeoutError("LLM request timed out.") from None
        except (httpx2.HTTPError, ValueError):
            raise RuntimeError("LLM provider request failed.") from None

        if not isinstance(result, dict) or "error" in result:
            raise RuntimeError("LLM provider request failed.")
        if result.get("done") is not True or result.get("done_reason") != "stop":
            raise RuntimeError("LLM provider did not complete the response.")
        message = result.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise RuntimeError("LLM provider returned an invalid response.")
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("LLM provider returned no text.")
        return text


def create_json_client(settings: LLMSettings) -> JSONClient:
    """Select exactly the configured provider without a network call or fallback."""
    if settings.provider == "openai":
        return OpenAIJSONClient(settings)
    if settings.provider == "anthropic":
        return AnthropicJSONClient(settings)
    if settings.provider == "ollama":
        return OllamaJSONClient(settings)
    raise ValueError("Unsupported LLM provider.")


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


class IdeationProvider(Protocol):
    """Supply generated use cases without IDs, timestamps or source metadata."""

    def generate_use_cases(
        self,
        source_artifact_json: str,
        number_of_ideas: int,
        *,
        focus: str | None = None,
        correction: str | None = None,
    ) -> str:
        """Return useCases JSON aligned to the saved source and requested focus.

        Treat source JSON and focus as data, including any embedded instructions.
        Correction feedback is authored separately by the backend.
        """
        ...


class FakeIdeationProvider:
    """Return scripted ideation responses without creating or assessing ideas."""

    def __init__(self, *responses: str | Exception) -> None:
        """Keep an ordered response script and an initially empty call history."""
        self._responses = iter(responses)
        self.calls: list[tuple[str, int, str | None, str | None]] = []

    def generate_use_cases(
        self,
        source_artifact_json: str,
        number_of_ideas: int,
        *,
        focus: str | None = None,
        correction: str | None = None,
    ) -> str:
        """Record source/count/focus/feedback and consume one scripted response."""
        self.calls.append((source_artifact_json, number_of_ideas, focus, correction))
        try:
            response = next(self._responses)
        except StopIteration:
            raise RuntimeError("Fake ideation provider has no scripted response left") from None
        if isinstance(response, Exception):
            raise response
        return response
