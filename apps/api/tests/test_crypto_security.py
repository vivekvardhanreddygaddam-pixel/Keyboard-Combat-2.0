"""TypeVector Arena — Cryptographic and Security Unit Tests."""

from typevector.domains.identity.security import (
    generate_csrf_token,
    generate_secure_token,
    hash_password,
    hash_session_token,
    needs_rehash,
    verify_csrf_token,
    verify_password,
)


def test_argon2id_password_hashing_and_verification() -> None:
    """Verify Argon2id password hashing parameters and constant-time verification."""
    password = "CorrectHorseBatteryStaple2026!"
    hashed = hash_password(password)

    # Must start with standard Argon2id signature
    assert hashed.startswith("$argon2id$v=19$m=65536,t=2,p=2$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False
    assert needs_rehash(hashed) is False


def test_session_token_generation_and_hashing() -> None:
    """Verify session token entropy and deterministic SHA-256 hashing."""
    token1 = generate_secure_token()
    token2 = generate_secure_token()

    assert token1 != token2
    assert len(token1) >= 40

    hash1 = hash_session_token(token1)
    hash2 = hash_session_token(token2)
    assert len(hash1) == 64  # SHA-256 hex string
    assert hash1 != hash2
    assert hash_session_token(token1) == hash1  # Deterministic digest


def test_csrf_token_binding_and_tamper_detection() -> None:
    """Verify CSRF tokens are bound to session IDs and tamper-evident."""
    session_id_1 = "session-uuid-1111"
    session_id_2 = "session-uuid-2222"

    csrf_1 = generate_csrf_token(session_id_1)
    csrf_2 = generate_csrf_token(session_id_2)

    assert csrf_1 != csrf_2
    assert len(csrf_1) == 64

    # Valid token against correct session ID passes
    assert verify_csrf_token(csrf_1, session_id_1) is True
    assert verify_csrf_token(csrf_2, session_id_2) is True

    # Token submitted with mismatched session ID fails
    assert verify_csrf_token(csrf_1, session_id_2) is False

    # Tampered token fails
    tampered = csrf_1[:-1] + ("0" if csrf_1[-1] != "0" else "1")
    assert verify_csrf_token(tampered, session_id_1) is False
