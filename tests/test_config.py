import pytest

from community_commander.config import ConfigurationError, Settings


def test_settings_require_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GRAPH_API_TOKEN", raising=False)

    with pytest.raises(ConfigurationError, match="GRAPH_API_TOKEN is required"):
        Settings.from_env()


def test_settings_load_and_normalize_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAPH_API_TOKEN", " secret-token ")
    monkeypatch.setenv("GRAPH_API_BASE_URL", "https://graph.example.test/")
    monkeypatch.setenv("GRAPH_API_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("LOG_LEVEL", "debug")

    settings = Settings.from_env()

    assert settings.graph_api_token == "secret-token"
    assert settings.graph_api_base_url == "https://graph.example.test"
    assert settings.graph_api_timeout_seconds == 2.5
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize("timeout", ["zero", "0", "-1"])
def test_settings_reject_invalid_timeout(monkeypatch: pytest.MonkeyPatch, timeout: str) -> None:
    monkeypatch.setenv("GRAPH_API_TOKEN", "secret-token")
    monkeypatch.setenv("GRAPH_API_TIMEOUT_SECONDS", timeout)

    with pytest.raises(ConfigurationError, match="GRAPH_API_TIMEOUT_SECONDS"):
        Settings.from_env()


def test_configuration_errors_do_not_include_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAPH_API_TOKEN", "top-secret")
    monkeypatch.setenv("GRAPH_API_BASE_URL", "not-a-url")

    with pytest.raises(ConfigurationError) as error:
        Settings.from_env()

    assert "top-secret" not in str(error.value)
