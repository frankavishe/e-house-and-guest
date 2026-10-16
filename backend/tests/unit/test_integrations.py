"""Local provider implementations (T017, T018)."""

from urllib.parse import urlparse

from app.core.config import Settings
from app.integrations.sms.console import ConsoleSmsProvider
from app.integrations.storage.local import LocalStorage
from app.integrations.storage.s3 import S3Storage


async def test_console_sms_keeps_outbox() -> None:
    sms = ConsoleSmsProvider(echo=False)
    result = await sms.send(to="+255712345678", text="hello")
    assert result.ok and result.provider_ref
    last = sms.last_to("+255712345678")
    assert last is not None and last.text == "hello"


async def test_local_storage_roundtrip() -> None:
    storage = LocalStorage()
    await storage.put("a/b.jpg", b"img", "image/jpeg", private=True)
    assert await storage.get("a/b.jpg", private=True) == b"img"
    assert await storage.size("a/b.jpg", private=True) == 3
    assert await storage.size("a/b.jpg") is None
    assert storage.public_url(key="x.webp").endswith("/public/x.webp")


def test_s3_presigned_urls_use_browser_endpoint() -> None:
    settings = Settings(
        s3_endpoint_url="http://minio:9000",
        s3_presign_endpoint_url="http://localhost:9010",
        s3_public_base_url="http://localhost:9010/public",
    )
    storage = S3Storage(settings)
    put = storage.presign_put(
        key="docs/id.jpg", content_type="image/jpeg", max_bytes=10, private=True
    )
    parsed = urlparse(put.url)
    assert parsed.netloc == "localhost:9010" and parsed.path == "/private/docs/id.jpg"
    assert put.headers == {"Content-Type": "image/jpeg"}
    get = storage.presign_get(key="docs/id.jpg", ttl_s=60)
    assert "X-Amz-Expires=60" in get
    assert storage.public_url(key="p/1.webp") == "http://localhost:9010/public/p/1.webp"
