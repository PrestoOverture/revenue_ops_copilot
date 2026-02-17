from pathlib import Path
import pytest
from pydantic import ValidationError
from src.config import Settings

def test_settings_raises_validation_error_when_required_env_vars_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required_vars = ["DATABASE_URL", "OPENAI_API_KEY", "ENCRYPTION_KEY"]
    for var in required_vars:
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    error_text = str(exc_info.value)
    for var in required_vars:
        assert var in error_text

def test_settings_loads_with_valid_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.test"
    env_file.write_text(
        "\n".join(
            [
                "DATABASE_URL=postgresql://revops:revops@localhost:5432/revops",
                "OPENAI_API_KEY=sk-test-key",
                "ENCRYPTION_KEY=MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.DATABASE_URL == "postgresql://revops:revops@localhost:5432/revops"
    assert settings.TEMPORAL_ADDRESS == "localhost:7233"
    assert settings.TEMPORAL_NAMESPACE == "default"
    assert settings.TEMPORAL_TASK_QUEUE == "lead-processing"
    assert settings.OPENAI_API_KEY == "sk-test-key"
    assert settings.ENCRYPTION_KEY == "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
