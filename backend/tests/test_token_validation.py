import hashlib
import hmac
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app import app
from services import auth


@pytest.mark.parametrize("token", ["é.a.a", "a.b.é", "..", "a.b.c.d", "a b.b.c", "a" * 8193, None])
def test_malformed_envelopes_are_authentication_failures(token):
    assert auth.verify_token(token) is None


def signed(payload, header=None):
    header = header if header is not None else {"alg": "HS256", "typ": "JWT"}
    data = f"{auth._base64url_encode(json.dumps(header).encode())}.{auth._base64url_encode(json.dumps(payload).encode())}"
    signature = auth._base64url_encode(hmac.new(auth.JWT_SECRET.encode(), data.encode(), hashlib.sha256).digest())
    return f"{data}.{signature}"


@pytest.mark.parametrize("expires", [None, "tomorrow", True, float("inf"), float("nan"), {}, []])
def test_invalid_signed_expiry_claim_is_rejected(expires):
    assert auth.verify_token(signed({"user_id": str(uuid.uuid4()), "type": "access", "exp": expires})) is None


def test_non_object_signed_claims_and_headers_are_rejected():
    assert auth.verify_token(signed([])) is None
    assert auth.verify_token(signed({"exp": time.time() + 100}, [])) is None


def test_invalid_raw_authorization_header_returns_401_not_500():
    response = TestClient(app).get("/auth/me", headers={"Authorization": b"Bearer \xe9.a.a"})
    assert response.status_code == 401
