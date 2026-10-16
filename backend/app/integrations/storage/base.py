"""Object storage interface (contracts/providers.md, R12)."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class PresignedPut:
    url: str
    key: str
    headers: dict[str, str] = field(default_factory=dict)
    expires_in: int = 600


class StorageProvider(Protocol):
    def presign_put(
        self, *, key: str, content_type: str, max_bytes: int, private: bool
    ) -> PresignedPut: ...

    def presign_get(self, *, key: str, ttl_s: int) -> str:
        """Short-lived URL for a private object (admins reviewing documents)."""
        ...

    def public_url(self, *, key: str) -> str: ...

    async def get(self, key: str, *, private: bool = False) -> bytes: ...

    async def put(self, key: str, data: bytes, content_type: str, private: bool) -> None: ...
