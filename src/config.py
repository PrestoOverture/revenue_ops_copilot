import base64
import binascii
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# make sure application fails fast if required environment variables are not set
# and if the environment variables are not valid
class Settings(BaseSettings):
    DATABASE_URL: str
    TEMPORAL_ADDRESS: str = "localhost:7233"
    TEMPORAL_NAMESPACE: str = "default"
    TEMPORAL_TASK_QUEUE: str = "lead-processing"
    OPENAI_API_KEY: str
    EMAIL_PROVIDER: str | None = None
    SENDGRID_API_KEY: str | None = None
    EMAIL_FROM: str | None = None
    CRM_PROVIDER: str | None = None
    HUBSPOT_API_KEY: str | None = None
    ENCRYPTION_KEY: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except binascii.Error as exc:
            raise ValueError("ENCRYPTION_KEY must be valid base64") from exc

        if len(decoded) != 32:
            raise ValueError("ENCRYPTION_KEY must decode to exactly 32 bytes")

        return value
