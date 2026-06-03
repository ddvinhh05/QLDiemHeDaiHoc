"""Băm mật khẩu PBKDF2-SHA256 (hỗ trợ mật khẩu plain cũ khi đăng nhập)."""
import hashlib
import secrets

_PREFIX = "pbkdf2_sha256$"
_ITERATIONS = 120_000


def hash_password(plain: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        plain.encode("utf-8"),
        salt.encode("utf-8"),
        _ITERATIONS,
    )
    return f"{_PREFIX}{salt}${digest.hex()}"


def is_password_hashed(stored: str) -> bool:
    return bool(stored) and str(stored).startswith(_PREFIX)


def verify_password(plain: str, stored: str) -> bool:
    if stored is None:
        return False
    stored = str(stored)
    if not is_password_hashed(stored):
        return plain == stored
    try:
        _p, salt, hexd = stored.split("$", 2)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            plain.encode("utf-8"),
            salt.encode("utf-8"),
            _ITERATIONS,
        )
        return secrets.compare_digest(digest.hex(), hexd)
    except (ValueError, TypeError):
        return plain == stored
