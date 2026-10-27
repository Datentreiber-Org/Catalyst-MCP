"""Explicit environment configuration for the currently supported LLM provider."""

import os
from collections.abc import Mapping
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    AnyHttpUrl,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)


class LLMSettings(BaseModel):
    """Keep provider/model selection and network timeout separate from credentials."""

    model_config = ConfigDict(
        strict=True, extra="forbid", frozen=True, hide_input_in_errors=True
    )

    provider: Literal["openai", "anthropic", "ollama"]
    model: Annotated[str, StringConstraints(pattern=r"\S")]
    api_key: SecretStr | None = Field(default=None, exclude=True, repr=False, min_length=1)
    timeout_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 60.0
    max_output_tokens: Annotated[int, Field(gt=0)] = 8192
    ollama_host: AnyHttpUrl = AnyHttpUrl("http://localhost:11434")

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        """Reject blank or whitespace-containing credentials without echoing them."""
        if value is None:
            return None
        raw = value.get_secret_value()
        if not raw or any(character.isspace() for character in raw):
            raise ValueError("API key must be non-empty and contain no whitespace")
        return value

    @field_validator("ollama_host")
    @classmethod
    def validate_ollama_host(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        """Require an HTTP(S) origin without embedded credentials or URL suffixes."""
        if (
            value.username is not None or value.password is not None
            or value.path not in (None, "/")
            or value.query is not None or value.fragment is not None
        ):
            raise ValueError("Ollama host must be an HTTP(S) origin without credentials or URL suffixes")
        return value

    @model_validator(mode="after")
    def validate_provider_credentials(self) -> Self:
        """Require cloud credentials and keep the local Ollama adapter credential-free."""
        if self.provider in ("openai", "anthropic") and self.api_key is None:
            raise ValueError("The selected cloud provider requires an API key")
        if self.provider == "ollama" and self.api_key is not None:
            raise ValueError("The local Ollama adapter does not use API credentials")
        return self

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        """Read only supported variables; do not load files or modify the environment."""
        values = os.environ if environ is None else environ
        try:
            provider = values["CATALYST_LLM_PROVIDER"]
            key_name = {
                "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
            }.get(provider)
            return cls(
                provider=provider,
                model=values["CATALYST_LLM_MODEL"],
                api_key=values[key_name] if key_name is not None else None,
                timeout_seconds=float(values.get("CATALYST_LLM_TIMEOUT_SECONDS", "60")),
                max_output_tokens=int(values.get("CATALYST_LLM_MAX_OUTPUT_TOKENS", "8192")),
                ollama_host=(
                    values.get("CATALYST_OLLAMA_HOST", "http://localhost:11434")
                    if provider == "ollama" else "http://localhost:11434"
                ),
            )
        except (KeyError, TypeError, ValueError):
            raise ValueError(
                "Invalid LLM configuration: choose openai, anthropic or ollama, set a non-blank "
                "CATALYST_LLM_MODEL and the matching cloud API key without whitespace, "
                "a positive finite CATALYST_LLM_TIMEOUT_SECONDS (default 60), "
                "positive integer CATALYST_LLM_MAX_OUTPUT_TOKENS (default 8192), "
                "and an HTTP(S) origin for CATALYST_OLLAMA_HOST (default http://localhost:11434)."
            ) from None
