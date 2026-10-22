"""In-memory storage for tests and offline dev (STORAGE_PROVIDER=local)."""

from app.integrations.storage.base import PresignedPut


class LocalStorage:
    def __init__(self, base_url: str = "http://storage.local") -> None:
        self.base_url = base_url.rstrip("/")
        self.objects: dict[tuple[bool, str], tuple[bytes, str]] = {}

    def presign_put(
        self, *, key: str, content_type: str, max_bytes: int, private: bool
    ) -> PresignedPut:
        bucket = "private" if private else "public"
        return PresignedPut(
            url=f"{self.base_url}/{bucket}/{key}?upload=1",
            key=key,
            headers={"Content-Type": content_type},
        )

    def presign_get(self, *, key: str, ttl_s: int) -> str:
        return f"{self.base_url}/private/{key}?ttl={ttl_s}"

    def public_url(self, *, key: str) -> str:
        return f"{self.base_url}/public/{key}"

    async def get(self, key: str, *, private: bool = False) -> bytes:
        try:
            return self.objects[(private, key)][0]
        except KeyError:
            raise FileNotFoundError(key) from None

    async def put(self, key: str, data: bytes, content_type: str, private: bool) -> None:
        self.objects[(private, key)] = (data, content_type)

    async def delete(self, key: str, *, private: bool = False) -> None:
        self.objects.pop((private, key), None)

    async def size(self, key: str, *, private: bool = False) -> int | None:
        obj = self.objects.get((private, key))
        return len(obj[0]) if obj else None
