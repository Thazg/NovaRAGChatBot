import pytest

from config.settings import Settings, validate_settings


def configured(**updates):
    config = Settings()
    # Tests are independent of developer .env overrides and provider access.
    config.ENVIRONMENT = "development"
    config.JWT_SECRET = "development-test-secret"
    config.COOKIE_SECURE = False
    config.REFRESH_COOKIE_NAME = "nova_refresh"
    config.REFRESH_COOKIE_SAMESITE = "lax"
    config.LLM_PROVIDER = "groq"
    config.RETRIEVAL_MODE = "bm25"
    for key, value in updates.items():
        setattr(config, key, value)
    return config


@pytest.mark.parametrize("key,value", [("ENVIRONMENT", "prodution"), ("LLM_PROVIDER", "unknown"),
    ("RETRIEVAL_MODE", "dense-only"), ("MAX_UPLOAD_BYTES", 0), ("MAX_CONTEXT_CHARS", -1),
    ("ACCESS_TOKEN_TTL_SECONDS", 0), ("REFRESH_COOKIE_SAMESITE", "invalid"), ("REFRESH_COOKIE_NAME", "bad;name")])
def test_invalid_configuration_fails_before_serving_requests(key, value):
    with pytest.raises(RuntimeError, match=key):
        validate_settings(configured(**{key: value}))


def test_example_secret_and_insecure_production_cookie_are_rejected():
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_settings(configured(ENVIRONMENT="production", JWT_SECRET="replace_with_a_long_random_secret", COOKIE_SECURE=True))
    with pytest.raises(RuntimeError, match="COOKIE_SECURE"):
        validate_settings(configured(ENVIRONMENT="production", JWT_SECRET="x" * 40))
    validate_settings(configured(ENVIRONMENT="production", JWT_SECRET="test-only-" + "x" * 40, COOKIE_SECURE=True))


@pytest.mark.parametrize("updates", [{"REFRESH_COOKIE_NAME": "__Host-nova_refresh"}, {"REFRESH_COOKIE_SAMESITE": "none"}])
def test_secure_cookie_contract_is_validated(updates):
    with pytest.raises(RuntimeError, match="COOKIE_SECURE"):
        validate_settings(configured(**updates))
