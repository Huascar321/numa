from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct

from app.settings import Settings


PBKDF2_ITERATIONS = 100_000
SALT_SIZE = 16
NONCE_SIZE = 16
TAG_SIZE = 32
VERSION_HEADER = b"v1"


def _derive_keys(secret_key: str, salt: bytes) -> tuple[bytes, bytes]:
    """Derive 32-byte encryption key and 32-byte MAC key using PBKDF2-HMAC-SHA256."""
    key_material = hashlib.pbkdf2_hmac(
        "sha256",
        secret_key.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=64,
    )
    enc_key = key_material[:32]
    mac_key = key_material[32:]
    return enc_key, mac_key


def _generate_keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    """Generate CTR keystream using HMAC-SHA256 in counter mode."""
    keystream = bytearray()
    counter = 0
    while len(keystream) < length:
        block = hmac.new(
            enc_key,
            nonce + struct.pack(">Q", counter),
            hashlib.sha256,
        ).digest()
        keystream.extend(block)
        counter += 1
    return bytes(keystream[:length])


def _compute_mac(mac_key: bytes, salt: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    """Compute HMAC-SHA256 over authenticated payload."""
    payload = VERSION_HEADER + salt + nonce + ciphertext
    return hmac.new(mac_key, payload, hashlib.sha256).digest()


def encrypt_token(token: str, key: str) -> str:
    """Encrypt a plaintext token using authenticated symmetric encryption."""
    if not token:
        raise ValueError("token must not be empty")
    if not key:
        raise ValueError("encryption key must not be empty")

    salt = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)
    enc_key, mac_key = _derive_keys(key, salt)

    plaintext_bytes = token.encode("utf-8")
    keystream = _generate_keystream(enc_key, nonce, len(plaintext_bytes))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext_bytes, keystream))

    tag = _compute_mac(mac_key, salt, nonce, ciphertext)
    packed = salt + nonce + ciphertext + tag
    encoded = base64.urlsafe_b64encode(packed).decode("ascii")
    return f"v1:{encoded}"


def decrypt_token(encrypted_token: str, key: str) -> str:
    """Decrypt and verify an encrypted token string."""
    if not encrypted_token:
        raise ValueError("encrypted token must not be empty")
    if not key:
        raise ValueError("encryption key must not be empty")

    if not encrypted_token.startswith("v1:"):
        raise ValueError("unsupported token encryption version")

    raw_payload = encrypted_token[3:]
    try:
        packed = base64.urlsafe_b64decode(raw_payload.encode("ascii"))
    except Exception as exc:
        raise ValueError("invalid base64 in encrypted token") from exc

    min_length = SALT_SIZE + NONCE_SIZE + TAG_SIZE + 1
    if len(packed) < min_length:
        raise ValueError("encrypted token payload is too short")

    salt = packed[:SALT_SIZE]
    nonce = packed[SALT_SIZE : SALT_SIZE + NONCE_SIZE]
    ciphertext = packed[SALT_SIZE + NONCE_SIZE : -TAG_SIZE]
    tag = packed[-TAG_SIZE:]

    enc_key, mac_key = _derive_keys(key, salt)
    expected_tag = _compute_mac(mac_key, salt, nonce, ciphertext)

    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("token authentication tag mismatch or corrupted ciphertext")

    keystream = _generate_keystream(enc_key, nonce, len(ciphertext))
    plaintext_bytes = bytes(a ^ b for a, b in zip(ciphertext, keystream))

    try:
        return plaintext_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("failed to decode plaintext token as utf-8") from exc


def get_encryption_key(settings: Settings) -> str:
    """Get the token encryption key from settings or derive from configured secrets."""
    if hasattr(settings, "token_encryption_key") and settings.token_encryption_key:
        return settings.token_encryption_key
    if settings.gmail_client_secret:
        return f"gmail-secret:{settings.gmail_client_secret}"
    if settings.database_url:
        return f"db-fallback:{settings.database_url}"
    return "numa-default-local-token-encryption-key"
