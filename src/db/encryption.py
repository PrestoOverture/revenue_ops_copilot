import json
import logging
from typing import Any, cast
from cryptography.fernet import Fernet
from src.config import Settings

logger = logging.getLogger(__name__)

def _get_fernet() -> Fernet:
    encryption_key = Settings().ENCRYPTION_KEY  # type: ignore[call-arg]
    return Fernet(encryption_key.encode("utf-8"))

# convert the data to a JSON string, encrypt it, and return the encrypted bytes
def encrypt_credentials(data: dict[str, Any]) -> bytes:
    plaintext = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _get_fernet().encrypt(plaintext)

# decrypt the bytes and return the data as a dictionary
def decrypt_credentials(encrypted: bytes) -> dict[str, Any]:
    decrypted = _get_fernet().decrypt(encrypted)
    parsed = json.loads(decrypted.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Decrypted credentials must be a JSON object")
    return cast(dict[str, Any], parsed)