"""Provider selection (Principle VII). Factories read settings once and cache the instance;
tests swap implementations with `override_*` or FastAPI `dependency_overrides`."""

from app.core.config import get_settings
from app.integrations.payments.base import PaymentProvider, PayoutProvider
from app.integrations.sms.base import SmsProvider
from app.integrations.storage.base import StorageProvider

_sms: SmsProvider | None = None
_storage: StorageProvider | None = None
_payments: PaymentProvider | None = None
_payouts: PayoutProvider | None = None


def get_sms_provider() -> SmsProvider:
    global _sms
    if _sms is None:
        settings = get_settings()
        if settings.sms_provider == "console":
            from app.integrations.sms.console import ConsoleSmsProvider

            _sms = ConsoleSmsProvider(echo=settings.env != "test")
        else:
            raise NotImplementedError("BeemSmsProvider arrives in T142")
    return _sms


def get_storage() -> StorageProvider:
    global _storage
    if _storage is None:
        settings = get_settings()
        if settings.storage_provider == "local":
            from app.integrations.storage.local import LocalStorage

            _storage = LocalStorage()
        else:
            from app.integrations.storage.s3 import S3Storage

            _storage = S3Storage(settings)
    return _storage


def get_payment_provider() -> PaymentProvider:
    global _payments
    if _payments is None:
        settings = get_settings()
        if settings.payment_provider == "mock":
            from app.integrations.payments.mock import MockPaymentProvider

            secret = settings.payment_callback_secret
            callback_url = (
                f"{settings.mock_callback_base_url or settings.public_api_base_url}"
                f"/api/v1/webhooks/payments/mock/{secret}"
                if settings.env != "test"
                else None
            )
            _payments = MockPaymentProvider(secret=secret, callback_url=callback_url)
        else:
            from app.integrations.payments.azampay import AzamPayProvider

            _payments = AzamPayProvider(settings)
    return _payments


def get_payout_provider() -> PayoutProvider:
    global _payouts
    if _payouts is None:
        settings = get_settings()
        if settings.payout_provider == "mock":
            from app.integrations.payments.mock import MockPayoutProvider

            _payouts = MockPayoutProvider()
        elif settings.payout_provider == "azampay" and settings.azampay_disburse_enabled:
            from app.integrations.payments.azampay import AzamPayProvider

            _payouts = AzamPayProvider(settings)
        else:
            from app.integrations.payments.manual import ManualPayoutProvider

            _payouts = ManualPayoutProvider()
    return _payouts


def override_sms(provider: SmsProvider | None) -> None:
    global _sms
    _sms = provider


def override_storage(provider: StorageProvider | None) -> None:
    global _storage
    _storage = provider


def override_payments(provider: PaymentProvider | None) -> None:
    global _payments
    _payments = provider


def override_payouts(provider: PayoutProvider | None) -> None:
    global _payouts
    _payouts = provider
