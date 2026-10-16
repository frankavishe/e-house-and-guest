"""Application settings, read from environment variables and `.env` (research.md)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    payout_provider: Literal["manual", "azampay"] = "manual"
    payment_callback_secret: str = "dev-only-change-me-callback-secret"
    public_api_base_url: str = "http://localhost:8000"
    azampay_env: Literal["sandbox", "live"] = "sandbox"
    azampay_app_name: str = ""
    azampay_client_id: str = ""
    azampay_client_secret: str = ""
    azampay_api_key: str = ""
    azampay_callback_password: str = ""

    # SMS (R11)
    sms_provider: Literal["console", "beem"] = "console"
    beem_api_key: str = ""
    beem_secret_key: str = ""
    beem_sender_id: str = ""

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

    @property
    def is_dev_like(self) -> bool:
        """Dev-only endpoints (mock payments) are enabled only in dev and test."""
        return self.env in ("dev", "test")


@lru_cache
def get_settings() -> Settings:
    return Settings()
