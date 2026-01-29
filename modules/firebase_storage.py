"""Optional Firebase Storage integration helper.

This module performs a best-effort initialization of the Firebase Admin SDK
and exposes simple helpers to upload/download blobs. It is defensive: if the
firebase_admin package or credentials are not available the functions no-op and
return False so the rest of the app continues to use local filesystem storage.

Configuration (recommended via environment variables):
- FIREBASE_SERVICE_ACCOUNT_JSON : JSON string of the service account
- FIREBASE_SERVICE_ACCOUNT_PATH : path to a service account JSON file
- FIREBASE_BUCKET              : explicit GCS bucket name (e.g. my-project.appspot.com)

Security note: Do NOT commit service account keys into the repository. Use
secure environment variables, a secrets manager, or a protected file outside
of version control.
"""
from __future__ import annotations
import os
import json
from typing import Optional

_initialized = False
_bucket = None
_app = None


def init_from_env() -> bool:
    """Initialize firebase_admin from environment variables if possible.
    Returns True if initialized, False otherwise.
    """
    sa_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
    sa_path = os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH')
    bucket = os.environ.get('FIREBASE_BUCKET')
    # If nothing provided, don't initialize.
    if not sa_json and not sa_path:
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials, storage
    except Exception:
        return False

    try:
        if sa_json:
            info = json.loads(sa_json)
            cred = credentials.Certificate(info)
        else:
            cred = credentials.Certificate(sa_path)

        global _app, _bucket, _initialized
        try:
            _app = firebase_admin.initialize_app(cred, options={'storageBucket': bucket} if bucket else None)
        except Exception:
            # If default app already exists, get it
            try:
                _app = firebase_admin.get_app()
            except Exception:
                _app = None

        # Resolve bucket name: prefer explicit env var, then look in service account
        resolved_bucket = bucket
        if not resolved_bucket and sa_json:
            try:
                proj = info.get('project_id')
                if proj:
                    resolved_bucket = f"{proj}.appspot.com"
            except Exception:
                resolved_bucket = None

        if resolved_bucket:
            try:
                _bucket = storage.bucket(resolved_bucket, app=_app)
            except Exception:
                try:
                    _bucket = storage.bucket(app=_app)
                except Exception:
                    _bucket = None
        else:
            try:
                _bucket = storage.bucket(app=_app)
            except Exception:
                _bucket = None

        _initialized = True
        return True
    except Exception:
        return False


def is_initialized() -> bool:
    return bool(_initialized and _app is not None)


def upload_blob(local_path: str, dest_path: str) -> bool:
    """Upload a local file to Firebase Storage at dest_path (blob name).
    Returns True on success, False otherwise.
    """
    if not is_initialized() or not _bucket:
        return False
    try:
        blob = _bucket.blob(dest_path)
        blob.upload_from_filename(local_path)
        return True
    except Exception:
        return False


def download_blob(dest_path: str, local_path: str) -> bool:
    """Download a blob from Firebase Storage to a local file path.
    Returns True on success, False otherwise.
    """
    if not is_initialized() or not _bucket:
        return False
    try:
        blob = _bucket.blob(dest_path)
        blob.download_to_filename(local_path)
        return True
    except Exception:
        return False


def list_blobs(prefix: Optional[str] = None):
    if not is_initialized() or not _bucket:
        return []
    try:
        blobs = list(_bucket.list_blobs(prefix=prefix)) if prefix else list(_bucket.list_blobs())
        return [b.name for b in blobs]
    except Exception:
        return []
