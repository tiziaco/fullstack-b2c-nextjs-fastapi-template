"""RS256 verification exercised with real keys, not a patched `jwt.decode`.

Every test in test_auth_utils.py patches `app.utils.auth.jwt.decode`, so the
signature check — the part that runs through `cryptography` — never executes.
That is right for the policy logic those tests cover (azp allowlist, missing
sub, error mapping), but it means the suite stays green regardless of what the
`cryptography` dependency does, and that dependency is four majors from where
it was.

These sign and verify with a real RSA key, so pyjwt's RSAAlgorithm and the
`cryptography` primitives underneath it actually run.
"""

import time
from unittest.mock import MagicMock

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import settings
from app.utils.auth import ClerkJWTVerifier

pytestmark = pytest.mark.unit

ISSUER = "https://clerk.test.example"
ORIGIN = "http://localhost:3000"


@pytest.fixture(scope="module")
def keypair():
    """One 2048-bit key for the module — generation is the slow part."""
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


@pytest.fixture(scope="module")
def other_public_key():
    """A second, unrelated key, for the token-signed-by-someone-else case."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()


@pytest.fixture(autouse=True)
def _auth_settings(monkeypatch):
    monkeypatch.setattr(settings.cors, "ALLOWED_ORIGINS", [ORIGIN])
    monkeypatch.setattr(settings.auth, "ISSUER", ISSUER)


def _sign(private_key, **overrides) -> str:
    claims = {
        "sub": "user_abc123",
        "iss": ISSUER,
        "azp": ORIGIN,
        "exp": int(time.time()) + 300,
        **overrides,
    }
    return pyjwt.encode(claims, private_key, algorithm="RS256")


def _verifier_serving(public_key) -> ClerkJWTVerifier:
    """A verifier whose JWKS lookup hands back `public_key`.

    Only the network fetch is stubbed; `jwt.decode` runs for real.
    """
    verifier = ClerkJWTVerifier()
    verifier._jwks_client = MagicMock()
    verifier._jwks_client.get_signing_key_from_jwt.return_value = MagicMock(key=public_key)
    return verifier


def test_a_genuinely_signed_token_verifies(keypair):
    """The happy path, with pyjwt and cryptography doing the real work."""
    private, public = keypair

    payload = _verifier_serving(public).verify_token(_sign(private))

    assert payload is not None, "real RS256 verification failed"
    assert payload["sub"] == "user_abc123"


def test_a_token_signed_with_a_different_key_is_rejected(keypair, other_public_key):
    """Non-vacuity: proves the signature is checked, not merely decoded."""
    private, _ = keypair

    assert _verifier_serving(other_public_key).verify_token(_sign(private)) is None


def test_a_tampered_payload_is_rejected(keypair):
    """Flipping a byte in the claims must invalidate the signature."""
    private, public = keypair
    header, body, sig = _sign(private).split(".")
    tampered = f"{header}.{body[:-2]}{'A' if body[-2] != 'A' else 'B'}{body[-1]}.{sig}"

    assert _verifier_serving(public).verify_token(tampered) is None


def test_an_expired_token_is_rejected_through_the_real_path(keypair):
    """The exp branch, reached via pyjwt itself rather than a mocked raise."""
    private, public = keypair

    expired = _sign(private, exp=int(time.time()) - 60)

    assert _verifier_serving(public).verify_token(expired) is None
