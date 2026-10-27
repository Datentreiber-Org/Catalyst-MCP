"""Explicit provider configuration with synthetic credentials only."""

import pytest
from pydantic import ValidationError

from catalyst_mcp.settings import LLMSettings


@pytest.fixture
def environment():
    """Supply a complete environment mapping without using local credentials."""
    return {
        "CATALYST_LLM_PROVIDER": "openai",
        "CATALYST_LLM_MODEL": "synthetic-model",
        "OPENAI_API_KEY": "synthetic-private-key-marker",
    }


def test_explicit_settings_and_default_timeout(environment):
    """Preserve the configured model and keep credentials out of representations."""
    original = environment.copy()
    settings = LLMSettings.from_env(environment)
    assert settings.model_dump(mode="json") == {
        "provider": "openai", "model": "synthetic-model", "timeout_seconds": 60.0,
        "max_output_tokens": 8192,
        "ollama_host": "http://localhost:11434/",
    }
    assert settings.api_key.get_secret_value() == environment["OPENAI_API_KEY"]
    assert environment["OPENAI_API_KEY"] not in repr(settings) + settings.model_dump_json()
    assert environment == original
    with pytest.raises(ValidationError):
        settings.model = "another-model"


def test_reads_current_environment_and_custom_timeout(environment, monkeypatch):
    """Read the process environment only when explicitly requested."""
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("CATALYST_LLM_TIMEOUT_SECONDS", "12.5")
    assert LLMSettings.from_env().timeout_seconds == 12.5


@pytest.mark.parametrize("missing", [
    "CATALYST_LLM_PROVIDER", "CATALYST_LLM_MODEL", "OPENAI_API_KEY",
])
def test_required_environment_has_no_implicit_fallback(environment, missing):
    """Fail before client construction if provider, model or credentials are absent."""
    del environment[missing]
    with pytest.raises(ValueError, match="Invalid LLM configuration"):
        LLMSettings.from_env(environment)


@pytest.mark.parametrize("name,value", [
    ("CATALYST_LLM_PROVIDER", "unsupported-provider"),
    ("CATALYST_LLM_PROVIDER", "unsupported-local-provider"),
    ("CATALYST_LLM_PROVIDER", "OPENAI"),
    ("CATALYST_LLM_MODEL", ""),
    ("CATALYST_LLM_MODEL", " \t\n"),
    ("OPENAI_API_KEY", ""),
    ("OPENAI_API_KEY", " \t\n"),
    ("OPENAI_API_KEY", "synthetic-private-key-marker\n"),
    ("CATALYST_LLM_TIMEOUT_SECONDS", ""),
    ("CATALYST_LLM_TIMEOUT_SECONDS", "0"),
    ("CATALYST_LLM_TIMEOUT_SECONDS", "-1"),
    ("CATALYST_LLM_TIMEOUT_SECONDS", "NaN"),
    ("CATALYST_LLM_TIMEOUT_SECONDS", "Infinity"),
    ("CATALYST_LLM_TIMEOUT_SECONDS", "private-invalid-timeout-marker"),
    ("CATALYST_LLM_MAX_OUTPUT_TOKENS", "0"),
    ("CATALYST_LLM_MAX_OUTPUT_TOKENS", "-1"),
    ("CATALYST_LLM_MAX_OUTPUT_TOKENS", "2.5"),
    ("CATALYST_LLM_MAX_OUTPUT_TOKENS", "True"),
])
def test_invalid_configuration_is_rejected_without_values(environment, name, value):
    """Reject unsupported providers and unusable settings with a fixed safe message."""
    environment[name] = value
    with pytest.raises(ValueError) as error:
        LLMSettings.from_env(environment)
    assert str(error.value).startswith("Invalid LLM configuration:")
    assert "synthetic-private-key-marker" not in str(error.value)
    assert "private-invalid-timeout-marker" not in str(error.value)
    assert error.value.__suppress_context__ is True


def test_direct_settings_reject_boolean_timeout_and_unknown_fields(environment):
    """Keep the typed configuration strict outside the environment loader too."""
    values = {
        "provider": "openai", "model": "synthetic-model",
        "api_key": environment["OPENAI_API_KEY"],
    }
    with pytest.raises(ValidationError):
        LLMSettings(**values, timeout_seconds=True)
    with pytest.raises(ValidationError):
        LLMSettings(**values, unrecognized="private-extra-marker")
    with pytest.raises(ValidationError):
        LLMSettings(**values, max_output_tokens=True)


def test_anthropic_uses_only_its_own_credential(environment):
    """Select the matching provider key without using another provider's credential."""
    environment["CATALYST_LLM_PROVIDER"] = "anthropic"
    with pytest.raises(ValueError, match="Invalid LLM configuration"):
        LLMSettings.from_env(environment)
    environment["ANTHROPIC_API_KEY"] = "synthetic-anthropic-marker"
    environment["CATALYST_LLM_MAX_OUTPUT_TOKENS"] = "1024"
    settings = LLMSettings.from_env(environment)
    assert settings.provider == "anthropic"
    assert settings.api_key.get_secret_value() == "synthetic-anthropic-marker"
    assert settings.max_output_tokens == 1024
    assert "synthetic-anthropic-marker" not in repr(settings) + settings.model_dump_json()


def test_ollama_needs_no_key_and_ignores_cloud_credentials(environment):
    """Keep local configuration independent of unrelated cloud credentials."""
    environment["CATALYST_LLM_PROVIDER"] = "ollama"
    environment["ANTHROPIC_API_KEY"] = "unrelated-cloud-key"
    selected = LLMSettings.from_env(environment)
    assert selected.api_key is None
    assert str(selected.ollama_host) == "http://localhost:11434/"
    environment["CATALYST_OLLAMA_HOST"] = "https://inference.example.invalid:1234"
    assert str(LLMSettings.from_env(environment).ollama_host) == "https://inference.example.invalid:1234/"
    with pytest.raises(ValidationError, match="does not use API credentials"):
        LLMSettings(provider="ollama", model="synthetic-model", api_key="synthetic-key")


@pytest.mark.parametrize("host", [
    "", "localhost:11434", "file:///tmp/ollama", "http://",
    "http://user:private-url-marker@localhost:11434",
    "http://localhost:11434/api", "http://localhost:11434?token=private-url-marker",
    "http://localhost:11434/#private-url-marker",
])
def test_invalid_ollama_origin_has_a_safe_configuration_error(environment, host):
    """Reject URLs that cannot represent the documented Ollama server origin."""
    environment["CATALYST_LLM_PROVIDER"] = "ollama"
    environment["CATALYST_OLLAMA_HOST"] = host
    with pytest.raises(ValueError, match="Invalid LLM configuration") as error:
        LLMSettings.from_env(environment)
    assert "private-url-marker" not in str(error.value)


def test_cloud_settings_ignore_unselected_local_host(environment):
    """A local-server setting cannot redirect or break a cloud provider."""
    environment["CATALYST_OLLAMA_HOST"] = "invalid-unselected-host"
    assert LLMSettings.from_env(environment).provider == "openai"
