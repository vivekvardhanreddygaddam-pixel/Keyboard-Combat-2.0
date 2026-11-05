"""TypeVector Arena — Password Hashing and Cryptographic Security Utilities."""

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from typevector.config import settings

# OWASP Recommended Argon2id parameters
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against an Argon2id hash using constant-time comparison."""
    try:
        return _hasher.verify(hashed, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    """Check if the hash needs upgrading to newer parameter standards."""
    return _hasher.check_needs_rehash(hashed)


def generate_secure_token() -> str:
    """Generate a high-entropy cryptographically random session token (256-bit)."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Compute SHA-256 digest of a session token for secure database storage.

    Session tokens are NEVER stored in plaintext in the database to mitigate
    session hijacking in the event of an unauthorized database dump.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token(session_id: str) -> str:
    """Generate an HMAC-SHA256 CSRF token cryptographically bound to the session."""
    message = f"tv-csrf:{session_id}".encode()
    key = settings.app_secret_key.encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def verify_csrf_token(token: str, session_id: str) -> bool:
    """Verify a CSRF token using constant-time HMAC comparison."""
    expected = generate_csrf_token(session_id)
    return hmac.compare_digest(token, expected)
