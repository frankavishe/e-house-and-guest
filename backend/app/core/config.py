"""Application settings, read from environment variables and `.env` (research.md)."""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Must be set to real values outside dev/test; their defaults are public in this repo.
_SECRETS = (
    "jwt_secret",
    "otp_hmac_key",
    "fernet_key",
    "payment_callback_secret",
    "s3_access_key",
    "s3_secret_key",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Root `.env` when running from backend/, local `.env` otherwise. Real env vars win.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["dev", "test", "staging", "prod"] = "dev"

    # Database
    database_url: str = "postgresql+asyncpg://rental:rental@localhost:5432/rental"
    test_database_url: str = "postgresql+asyncpg://rental:rental@localhost:5433/rental_test"

    # Auth (R10)
    jwt_secret: str = "dev-only-change-me-jwt-secret-32-bytes"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 2_592_000
    otp_hmac_key: str = "dev-only-change-me-otp-hmac-key"
    cookie_secure: bool = False

    # Encryption at rest (R18)
    fernet_key: str = "ZGV2LW9ubHktY2hhbmdlLW1lLWZlcm5ldC1rZXktMzI="

    # Payments (R6, R7)
    payment_provider: Literal["mock", "azampay"] = "mock"
    # `manual`: payouts wait for an admin to send the money and mark them paid (R7 fallback).
    payout_provider: Literal["manual", "mock", "azampay"] = "manual"
    payment_callback_secret: str = "dev-only-change-me-callback-secret"
    public_api_base_url: str = "http://localhost:8000"
    # Where the mock provider posts its callbacks; inside docker the API reaches itself on
    # its container port, not the host-mapped one. Defaults to public_api_base_url.
    mock_callback_base_url: str = ""
    azampay_env: Literal["sandbox", "live"] = "sandbox"
    azampay_app_name: str = ""
    azampay_client_id: str = ""
    azampay_client_secret: str = ""
    azampay_api_key: str = ""
    azampay_callback_password: str = ""
    # AzamPay disbursement stays off until R7 is verified against the sandbox; until then
    # PAYOUT_PROVIDER=azampay falls back to manual payouts.
    azampay_disburse_enabled: bool = False
    azampay_disburse_source_name: str = ""
    azampay_disburse_source_bank: str = ""
    azampay_disburse_source_account: str = ""

    # SMS (R11)
    sms_provider: Literal["console", "beem"] = "console"
    beem_api_key: str = ""
    beem_secret_key: str = ""
    beem_sender_id: str = ""
    beem_base_url: str = "https://apisms.beem.africa"

    # Object storage (R12)
    storage_provider: Literal["s3", "local"] = "s3"
    s3_endpoint_url: str = "http://localhost:9000"
    # Endpoint used in presigned URLs handed to browsers; defaults to s3_endpoint_url.
    # In docker the API reaches MinIO as http://minio:9000 but browsers need localhost.
    s3_presign_endpoint_url: str = ""
    s3_public_base_url: str = "http://localhost:9000/public"
    s3_region: str = "us-east-1"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket_public: str = "public"
    s3_bucket_private: str = "private"
    upload_max_bytes: int = 10_485_760

    # Business
    business_timezone: str = "Africa/Dar_es_Salaam"
    default_language: Literal["sw", "en"] = "sw"

    @model_validator(mode="after")
    def _refuse_dev_values_outside_dev(self) -> "Settings":
        """Staging and prod do not start with a dev default secret, insecure cookies, or (prod)
        the console SMS / mock payment providers (docs/security.md)."""
        if self.env not in ("staging", "prod"):
            return self
        fields = type(self).model_fields
        problems = [
            f"{name} is the dev default"
            for name in _SECRETS
            if getattr(self, name) == fields[name].default
        ]
        if len(self.jwt_secret) < 32:
            problems.append("jwt_secret is shorter than 32 characters")
        if not self.cookie_secure:
            problems.append("cookie_secure must be true")
        if self.env == "prod":
            if self.sms_provider == "console":
                problems.append("sms_provider is console")
            if self.payment_provider == "mock" or self.payout_provider == "mock":
                problems.append("payment_provider/payout_provider is mock")
        if problems:
            raise ValueError(f"unsafe settings for env={self.env}: " + "; ".join(problems))
        return self

    @property
    def is_dev_like(self) -> bool:
        """Dev-only endpoints (mock payments) are enabled only in dev and test."""
        return self.env in ("dev", "test")


@lru_cache
def get_settings() -> Settings:
    return Settings()
