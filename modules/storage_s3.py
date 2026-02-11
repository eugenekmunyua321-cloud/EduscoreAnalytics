"""S3 storage helper for saving and loading exam files.

This module provides simple helpers to upload/download files to S3 while
keeping a fallback to local filesystem. It intentionally implements a small
surface (init_from_env, upload_file, download_file, exists, list_objects,
upload_bytes, download_bytes) used by the app.
"""
from __future__ import annotations
import os
from typing import Optional, List
try:
    import boto3
    from botocore.exceptions import ClientError
except Exception:
    boto3 = None
    ClientError = Exception

_s3 = None
_bucket = None
_prefix = None

def init_from_env(bucket: Optional[str] = None, prefix: Optional[str] = None):
    """Initialize the S3 client using environment or passed values.

    Environment variables used (defaults):
      - S3_BUCKET
      - S3_PREFIX (optional)
    AWS credentials and region are resolved by boto3 from env/instance role.
    """
    global _s3, _bucket, _prefix
    if boto3 is None:
        raise RuntimeError('boto3 is required for S3 support; install boto3')
    _bucket = bucket or os.environ.get('S3_BUCKET')
    _prefix = (prefix or os.environ.get('S3_PREFIX') or '').strip().strip('/')
    if not _bucket:
        raise RuntimeError('S3_BUCKET is required for S3 storage')
    _s3 = boto3.client('s3')
    return True


def _s3_key(key: str) -> str:
    if _prefix:
        return f"{_prefix.rstrip('/')}/{key.lstrip('/')}"
    return key.lstrip('/')


def upload_file(local_path: str, key: str, extra_args: dict = None) -> bool:
    """Upload a local file to S3 under the given logical key."""
    global _s3, _bucket
    if _s3 is None:
        raise RuntimeError('S3 not initialized')
    k = _s3_key(key)
    try:
        _s3.upload_file(local_path, _bucket, k, ExtraArgs=(extra_args or {}))
        return True
    except ClientError:
        return False


def download_file(key: str, local_path: str) -> bool:
    """Download object `key` to a local file path. Creates parent dirs."""
    global _s3, _bucket
    if _s3 is None:
        raise RuntimeError('S3 not initialized')
    k = _s3_key(key)
    os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)
    try:
        _s3.download_file(_bucket, k, local_path)
        return True
    except ClientError:
        return False


def exists(key: str) -> bool:
    """Return True if the key exists in the bucket."""
    global _s3, _bucket
    if _s3 is None:
        raise RuntimeError('S3 not initialized')
    k = _s3_key(key)
    try:
        _s3.head_object(Bucket=_bucket, Key=k)
        return True
    except ClientError:
        return False


def list_objects(prefix: str) -> List[str]:
    """List object keys under the provided prefix (non-recursive listing returns keys).

    Returns logical keys relative to prefix (no leading prefix included).
    """
    global _s3, _bucket
    if _s3 is None:
        raise RuntimeError('S3 not initialized')
    p = _s3_key(prefix)
    try:
        paginator = _s3.get_paginator('list_objects_v2')
        it = paginator.paginate(Bucket=_bucket, Prefix=p)
        out = []
        for page in it:
            for obj in page.get('Contents', []):
                key = obj.get('Key')
                if key is None:
                    continue
                # strip the prefix if present
                if p and key.startswith(p):
                    rel = key[len(p):].lstrip('/')
                else:
                    rel = key
                out.append(rel)
        return out
    except ClientError:
        return []


def upload_bytes(key: str, data: bytes, content_type: str = None) -> bool:
    global _s3, _bucket
    if _s3 is None:
        raise RuntimeError('S3 not initialized')
    k = _s3_key(key)
    extra = {}
    if content_type:
        extra['ContentType'] = content_type
    try:
        _s3.put_object(Bucket=_bucket, Key=k, Body=data, **extra)
        return True
    except ClientError:
        return False


def download_bytes(key: str) -> Optional[bytes]:
    global _s3, _bucket
    if _s3 is None:
        raise RuntimeError('S3 not initialized')
    k = _s3_key(key)
    try:
        resp = _s3.get_object(Bucket=_bucket, Key=k)
        return resp['Body'].read()
    except ClientError:
        return None


def delete_object(key: str) -> bool:
    """Delete an object from the S3 bucket. Returns True on success."""
    global _s3, _bucket
    if _s3 is None:
        raise RuntimeError('S3 not initialized')
    k = _s3_key(key)
    try:
        _s3.delete_object(Bucket=_bucket, Key=k)
        return True
    except ClientError:
        return False
