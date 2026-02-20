import json
import pytest
from cryptography.fernet import InvalidToken
from src.db.encryption import decrypt_credentials, encrypt_credentials

@pytest.fixture(autouse=True)
def set_required_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://revops:revops@localhost:5432/revops")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv(
        "ENCRYPTION_KEY",
        "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )

# test that the encrypt and decrypt functions round trip
def test_round_trip() -> None:
    payload = {"api_key": "test123"}
    encrypted = encrypt_credentials(payload)
    decrypted = decrypt_credentials(encrypted)
    assert decrypted == payload

# test that the encrypt function returns bytes and not plaintext
def test_encrypt_returns_bytes() -> None:
    payload = {"api_key": "test123"}
    encrypted = encrypt_credentials(payload)
    plaintext_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    assert isinstance(encrypted, bytes)
    assert encrypted != plaintext_json

# test that the decrypt function raises an exception if the data is tampered
def test_decrypt_tampered_data() -> None:
    encrypted = encrypt_credentials({"api_key": "test123"})
    tampered = encrypted[:-1] + bytes([encrypted[-1] ^ 1])

    with pytest.raises(InvalidToken):
        decrypt_credentials(tampered)

# test that the encrypt and decrypt functions work with an empty dictionary
def test_encrypt_decrypt_empty_dict() -> None:
    payload: dict[str, str] = {}
    encrypted = encrypt_credentials(payload)
    decrypted = decrypt_credentials(encrypted)
    assert decrypted == payload

# test that the encrypt and decrypt functions work with a nested dictionary
def test_encrypt_decrypt_nested_dict() -> None:
    payload = {
        "email": {"provider": "sendgrid", "api_key": "sg-test"},
        "crm": {"provider": "hubspot", "token": "hs-token"},
    }
    encrypted = encrypt_credentials(payload)
    decrypted = decrypt_credentials(encrypted)
    assert decrypted == payload
