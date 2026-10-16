"""S3-compatible storage (MinIO locally, any S3/R2 in production), R12.

Browsers upload with a presigned PUT. A PUT URL cannot enforce a size limit, so callers
check the object size when the upload is confirmed (`head` before processing).
"""

import asyncio
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config

from app.core.config import Settings
from app.integrations.storage.base import PresignedPut

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

PUT_TTL_S = 600


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = self._make_client(settings.s3_endpoint_url)
        self._presigner = self._make_client(
            settings.s3_presign_endpoint_url or settings.s3_endpoint_url
        )

    def _make_client(self, endpoint_url: str) -> "S3Client":
        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=self.settings.s3_region,
            aws_access_key_id=self.settings.s3_access_key,
            aws_secret_access_key=self.settings.s3_secret_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def _bucket(self, private: bool) -> str:
        return self.settings.s3_bucket_private if private else self.settings.s3_bucket_public

    def presign_put(
        self, *, key: str, content_type: str, max_bytes: int, private: bool
    ) -> PresignedPut:
        url = self._presigner.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket(private), "Key": key, "ContentType": content_type},
            ExpiresIn=PUT_TTL_S,
        )
        return PresignedPut(
            url=url, key=key, headers={"Content-Type": content_type}, expires_in=PUT_TTL_S
        )

    def presign_get(self, *, key: str, ttl_s: int) -> str:
        return self._presigner.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.settings.s3_bucket_private, "Key": key},
            ExpiresIn=ttl_s,
        )

    def public_url(self, *, key: str) -> str:
        return f"{self.settings.s3_public_base_url.rstrip('/')}/{key}"

    async def get(self, key: str, *, private: bool = False) -> bytes:
        def _get() -> bytes:
            obj = self._client.get_object(Bucket=self._bucket(private), Key=key)
            return obj["Body"].read()

        return await asyncio.to_thread(_get)

    async def put(self, key: str, data: bytes, content_type: str, private: bool) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket(private),
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def size(self, key: str, *, private: bool = False) -> int | None:
        def _head() -> int | None:
            try:
                return self._client.head_object(Bucket=self._bucket(private), Key=key)[
                    "ContentLength"
                ]
            except self._client.exceptions.ClientError:
                return None

        return await asyncio.to_thread(_head)
