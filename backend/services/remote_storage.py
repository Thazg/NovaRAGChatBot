import logging
from pathlib import Path
from typing import List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from config.settings import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        if not settings.B2_KEY_ID or not settings.B2_APP_KEY:
            return None
        _client = boto3.client(
            "s3",
            endpoint_url=settings.B2_ENDPOINT,
            aws_access_key_id=settings.B2_KEY_ID,
            aws_secret_access_key=settings.B2_APP_KEY,
        )
    return _client


def upload_file(remote_path: str, local_path: Path) -> bool:
    client = _get_client()
    if not client:
        return False
    try:
        client.upload_file(str(local_path), settings.B2_BUCKET, remote_path)
        return True
    except (BotoCoreError, ClientError) as exc:
        logger.error("B2 upload failed: %s", exc)
        return False


def download_file(remote_path: str, local_path: Path) -> bool:
    client = _get_client()
    if not client:
        return False
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        client.download_file(settings.B2_BUCKET, remote_path, str(local_path))
        return True
    except (BotoCoreError, ClientError):
        return False


def file_exists(remote_path: str) -> bool:
    client = _get_client()
    if not client:
        return False
    try:
        client.head_object(Bucket=settings.B2_BUCKET, Key=remote_path)
        return True
    except (BotoCoreError, ClientError):
        return False


def list_files(prefix: str = "") -> List[str]:
    client = _get_client()
    if not client:
        return []
    try:
        keys: List[str] = []
        continuation_token = None
        while True:
            params = {"Bucket": settings.B2_BUCKET, "Prefix": prefix}
            if continuation_token:
                params["ContinuationToken"] = continuation_token
            response = client.list_objects_v2(**params)
            keys.extend(obj["Key"] for obj in response.get("Contents", []))
            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")
        return keys
    except (BotoCoreError, ClientError):
        return []


def delete_file(remote_path: str) -> bool:
    client = _get_client()
    if not client:
        return False
    try:
        client.delete_object(Bucket=settings.B2_BUCKET, Key=remote_path)
        return True
    except (BotoCoreError, ClientError) as exc:
        logger.error("B2 delete failed: %s", exc)
        return False


def upload_bytes(remote_path: str, data: bytes) -> bool:
    client = _get_client()
    if not client:
        return False
    try:
        client.put_object(Bucket=settings.B2_BUCKET, Key=remote_path, Body=data)
        return True
    except (BotoCoreError, ClientError) as exc:
        logger.error("B2 upload failed: %s", exc)
        return False


def download_bytes(remote_path: str) -> Optional[bytes]:
    client = _get_client()
    if not client:
        return None
    try:
        response = client.get_object(Bucket=settings.B2_BUCKET, Key=remote_path)
        return response["Body"].read()
    except (BotoCoreError, ClientError):
        return None
