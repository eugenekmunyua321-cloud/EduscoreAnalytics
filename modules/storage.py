"""Storage adapter that routes reads/writes to S3 when configured, otherwise
uses the local filesystem. Provides helpers for JSON, pickles and bytes.

This adapter aims to be non-destructive: when S3 is enabled (STORAGE_PROVIDER=s3)
all write operations will target S3 and local writes are skipped. Read operations
prefer S3 and fall back to local files if present.
"""
from __future__ import annotations
import os
import json
from io import BytesIO
from typing import Optional, List

try:
    import pandas as pd
except Exception:
    pd = None

_USE_S3 = os.environ.get('STORAGE_PROVIDER', '').lower() == 's3'
_s3_mod = None
if _USE_S3:
    try:
        from . import storage_s3 as _s3_mod
        try:
            _s3_mod.init_from_env()
        except Exception:
            # initialization may have been done elsewhere; ignore
            pass
    except Exception:
        _s3_mod = None

# When true, disallow any local writes — all writes must go to S3. If S3
# is not available while this is enabled, write ops will fail (return False).
STRICT_S3 = os.environ.get('STORAGE_STRICT_S3', '').lower() in ('1', 'true', 'yes')


BASE_STORAGE = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')


def get_storage_dir() -> str:
    """Return local storage dir path (keeps compatibility)."""
    try:
        sid = None
        # try to import auth lazily to avoid circular imports
        try:
            from . import auth
            sid = auth.get_current_school_id() if hasattr(auth, 'get_current_school_id') else None
        except Exception:
            sid = None
        if sid:
            path = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage', sid)
            os.makedirs(path, exist_ok=True)
            return path
    except Exception:
        pass
    os.makedirs(BASE_STORAGE, exist_ok=True)
    return BASE_STORAGE


def is_s3_enabled():
    """Check if S3 storage is actually configured and working"""
    return _USE_S3 and _s3_mod is not None


def verify_s3_connection():
    """Verify S3 connection works"""
    if not is_s3_enabled():
        return False
    try:
        # Try to access the S3 bucket to verify connection
        if hasattr(_s3_mod, '_s3') and _s3_mod._s3 is not None and hasattr(_s3_mod, '_bucket') and _s3_mod._bucket:
            _s3_mod._s3.head_bucket(Bucket=_s3_mod._bucket)
            return True
        return False
    except Exception:
        return False


def _path_to_key(path: str) -> str:
    """Convert a local path under BASE_STORAGE to an S3 key (relative path).
    If path is already a key (no BASE_STORAGE prefix), return it unchanged.
    """
    if not path:
        return ''
    abs_base = os.path.abspath(BASE_STORAGE)
    abs_path = os.path.abspath(path)
    if abs_path.startswith(abs_base):
        rel = os.path.relpath(abs_path, abs_base)
        return rel.replace('\\', '/')
    # If path appears to be just a relative key, return normalized
    return path.lstrip('/').replace('\\', '/')


def write_bytes(key_or_path: str, data: bytes, content_type: Optional[str] = None) -> bool:
    """Write bytes to S3 (when enabled) or to local filesystem.
    If S3 is enabled we treat key_or_path as an S3 key under the bucket/prefix.
    If S3 not enabled, treat it as a local path and write file.
    """
    # If strict mode requested but S3 isn't available, refuse to write.
    if STRICT_S3 and not (_USE_S3 and _s3_mod is not None):
        return False

    if _USE_S3 and _s3_mod is not None:
        try:
            # Normalize local paths under BASE_STORAGE to relative S3 keys
            key = _path_to_key(key_or_path)
            return _s3_mod.upload_bytes(key, data, content_type=content_type)
        except Exception:
            return False
    # local write
    try:
        local_path = key_or_path
        # if key looks like a relative key (no path separators) map into BASE_STORAGE
        if not os.path.isabs(local_path) and '/' in _path_to_key(local_path):
            local_path = os.path.join(BASE_STORAGE, _path_to_key(local_path))
        os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)
        with open(local_path, 'wb') as fh:
            fh.write(data)
        return True
    except Exception:
        return False


def read_bytes(key_or_path: str) -> Optional[bytes]:
    """Read bytes from S3 or local filesystem. Returns None if missing."""
    if _USE_S3 and _s3_mod is not None:
        try:
            key = _path_to_key(key_or_path)
            return _s3_mod.download_bytes(key)
        except Exception:
            return None
    try:
        local_path = key_or_path
        if not os.path.isabs(local_path) and '/' in _path_to_key(local_path):
            local_path = os.path.join(BASE_STORAGE, _path_to_key(local_path))
        if not os.path.exists(local_path):
            return None
        with open(local_path, 'rb') as fh:
            return fh.read()
    except Exception:
        return None


def exists(key_or_path: str) -> bool:
    if _USE_S3 and _s3_mod is not None:
        try:
            key = _path_to_key(key_or_path)
            return _s3_mod.exists(key)
        except Exception:
            return False
    local_path = key_or_path
    if not os.path.isabs(local_path) and '/' in _path_to_key(local_path):
        local_path = os.path.join(BASE_STORAGE, _path_to_key(local_path))
    return os.path.exists(local_path)


def list_objects(prefix: str = '') -> List[str]:
    if _USE_S3 and _s3_mod is not None:
        try:
            key = _path_to_key(prefix)
            return _s3_mod.list_objects(key)
        except Exception:
            return []
    # local listing
    root = os.path.join(BASE_STORAGE, prefix) if prefix else BASE_STORAGE
    out = []
    if not os.path.exists(root):
        return out
    for root_dir, dirs, files in os.walk(root):
        for f in files:
            full = os.path.join(root_dir, f)
            rel = os.path.relpath(full, BASE_STORAGE).replace('\\', '/')
            out.append(rel)
    return out


def write_json(key_or_path: str, obj: object) -> bool:
    b = json.dumps(obj, ensure_ascii=False, indent=2).encode('utf-8')
    return write_bytes(key_or_path, b, content_type='application/json')


def read_json(key_or_path: str) -> Optional[object]:
    b = read_bytes(key_or_path)
    if not b:
        return None
    try:
        return json.loads(b.decode('utf-8'))
    except Exception:
        return None


def write_pickle(key_or_path: str, obj) -> bool:
    if pd is None:
        # fallback: use pickle
        import pickle
        b = pickle.dumps(obj)
        return write_bytes(key_or_path, b, content_type='application/octet-stream')
    try:
        buf = BytesIO()
        if isinstance(obj, pd.DataFrame):
            obj.to_pickle(buf)
        else:
            import pickle
            pickle.dump(obj, buf)
        return write_bytes(key_or_path, buf.getvalue(), content_type='application/octet-stream')
    except Exception:
        return False


def read_pickle(key_or_path: str):
    b = read_bytes(key_or_path)
    if not b:
        return None
    try:
        if pd is not None:
            from io import BytesIO
            return pd.read_pickle(BytesIO(b))
        import pickle
        return pickle.loads(b)
    except Exception:
        return None


def download_file(key: str, local_path: str) -> bool:
    """Download from S3 to local path. If S3 not enabled, copy from local storage."""
    # If strict S3-only mode is requested and S3 isn't available, fail.
    if STRICT_S3 and not (_USE_S3 and _s3_mod is not None):
        return False
    if _USE_S3 and _s3_mod is not None:
        try:
            keyn = _path_to_key(key)
            return _s3_mod.download_file(keyn, local_path)
        except Exception:
            return False
    # copy from local stored file
    src = os.path.join(BASE_STORAGE, _path_to_key(key))
    try:
        os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)
        import shutil
        shutil.copyfile(src, local_path)
        return True
    except Exception:
        return False


def upload_file(local_path: str, key: str) -> bool:
    # If strict S3-only mode is requested and S3 isn't available, fail.
    if STRICT_S3 and not (_USE_S3 and _s3_mod is not None):
        return False
    if _USE_S3 and _s3_mod is not None:
        try:
            keyn = _path_to_key(key)
            return _s3_mod.upload_file(local_path, keyn)
        except Exception:
            return False
    # local copy: ensure directory exists
    dest = os.path.join(BASE_STORAGE, _path_to_key(key))
    try:
        os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
        import shutil
        shutil.copyfile(local_path, dest)
        return True
    except Exception:
        return False


def delete(key_or_path: str) -> bool:
    """Delete an object/key or local file. Returns True if deleted or missing.
    When S3 is enabled this will attempt to delete the S3 object; otherwise remove
    the local file if present.
    """
    if _USE_S3 and _s3_mod is not None:
        try:
            return _s3_mod.delete_object(key_or_path)
        except Exception:
            return False
    # local delete
    try:
        local_path = key_or_path
        if not os.path.isabs(local_path) and '/' in _path_to_key(local_path):
            local_path = os.path.join(BASE_STORAGE, _path_to_key(local_path))
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
                return True
            except Exception:
                return False
        # missing is considered success
        return True
    except Exception:
        return False
import os
from pathlib import Path
try:
    from . import auth
except Exception:
    auth = None
try:
    # optional DB helper
    from . import db as _db
except Exception:
    _db = None
USE_DB_STRICT = os.environ.get('USE_DB_STRICT', 'true').lower() in ('1', 'true', 'yes')

BASE_STORAGE = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')

def get_storage_dir():
    """Return the storage directory for the current signed-in school (if any),
    otherwise return the shared saved_exams_storage path. Creates the directory if missing.
    """
    try:
        # If strict DB-only mode is requested and DB helper is available, prefer DB
        if USE_DB_STRICT and _db is not None:
            try:
                _db.init_from_env()
                if _db.enabled():
                    # Return a sentinel path that callers shouldn't write to; this
                    # signals DB-only operation. We still return a path string for
                    # compatibility but do not create directories.
                    sid = auth.get_current_school_id() if auth is not None else None
                    if sid:
                        return os.path.join('DB_ONLY_STORAGE', sid)
                    return 'DB_ONLY_STORAGE'
            except Exception:
                pass
        if auth is not None:
            sid = auth.get_current_school_id()
            if sid:
                path = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage', sid)
                os.makedirs(path, exist_ok=True)
                return path
    except Exception:
        pass
    path = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')
    os.makedirs(path, exist_ok=True)
    return path


def initialize_account(school_id: str):
    """Create a fresh per-school storage folder with empty datasets and
    prefilled messaging configuration copied from the global config (if present).

    This is called when a new local account is created so each account starts
    with no exams, no photos, no contacts, and no message history. The only
    thing copied into new accounts is the messaging provider info (messaging_config.json)
    so schools can send messages if they configure credentials.
    """
    try:
        if not school_id:
            return False
        # If DB-only and DB available, write initial empty objects into the kv store.
        try:
            if USE_DB_STRICT and _db is not None:
                _db.init_from_env()
                if _db.enabled():
                    # create default keys under storage:<school_id>:<filename>
                    defaults = {
                        'exams_metadata.json': {},
                        'student_contacts.json': [],
                        'student_photos.json': {},
                        'sent_messages_log.json': [],
                        'purchases.json': {},
                        'ta_teachers.json': {},
                        'teacher_assignments.json': {},
                        'ta_assignments.json': {},
                        'ta_assignments_simple.json': {},
                        'ta_class_map.json': {},
                        'ta_selected_exams.json': {},
                        'ta_settings.json': {},
                        'report_card_settings.json': {},
                        'app_persistent_config.json': {},
                    }
                    for k, v in defaults.items():
                        try:
                            _db.set_kv(f'storage:{school_id}:{k}', v)
                        except Exception:
                            pass
                    # ensure student_photos key exists as empty dict
                    try:
                        _db.set_kv(f'storage:{school_id}:student_photos', {})
                    except Exception:
                        pass
                    return True
        except Exception:
            pass
        root = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')
        acct_dir = os.path.join(root, school_id)
        os.makedirs(acct_dir, exist_ok=True)

        # Helper to write file if missing
        def write_if_missing(fname, data):
            """Write initial JSON data for the account. When S3 is enabled or
            strict S3 mode is requested, write into S3 using the adapter; otherwise
            create a local file if missing.
            """
            # If S3 is available (or strict requested), write to the per-account key
            if (_USE_S3 and _s3_mod is not None) or STRICT_S3:
                try:
                    # Use storage adapter's JSON writer with key <school_id>/<fname>
                    key = f'{school_id}/{fname}'
                    write_json(key, data)
                    return
                except Exception:
                    # fallthrough to local attempt if adapter fails and strict not enforced
                    if STRICT_S3:
                        return
            p = os.path.join(acct_dir, fname)
            if os.path.exists(p):
                return
            try:
                import json
                with open(p, 'w', encoding='utf-8') as fh:
                    json.dump(data, fh, indent=2, ensure_ascii=False)
            except Exception:
                pass

        # Create empty containers
        write_if_missing('exams_metadata.json', {})
        write_if_missing('student_contacts.json', [])
        write_if_missing('student_photos.json', {})
        write_if_missing('sent_messages_log.json', [])
        write_if_missing('purchases.json', {})
        write_if_missing('ta_teachers.json', {})
        write_if_missing('teacher_assignments.json', {})
        write_if_missing('ta_assignments.json', {})
        write_if_missing('ta_assignments_simple.json', {})
        write_if_missing('ta_class_map.json', {})
        write_if_missing('ta_selected_exams.json', {})
        write_if_missing('ta_settings.json', {})
        write_if_missing('report_card_settings.json', {})

        # Create a per-account app config with empty school/class/exam names so new accounts start blank
        acct_app_cfg = os.path.join(acct_dir, 'app_persistent_config.json')
        if not os.path.exists(acct_app_cfg):
            try:
                import json
                acct_cfg = {
                    "school_name": "",
                    "class_name": "",
                    "exam_name": "",
                    "font_family": "Poppins",
                    "font_size": 14,
                    "font_weight": "normal",
                    "font_color": "#111111",
                    "primary_color": "#0E6BA8",
                    "apply_to": ["whole_app"],
                    "input_mode": "paste",
                    "combined_subjects": {},
                    "grading_enabled": False,
                    "grading_system": [
                        {"grade": "A", "min": 80, "max": 100},
                        {"grade": "B", "min": 70, "max": 79},
                        {"grade": "C", "min": 60, "max": 69},
                        {"grade": "D", "min": 50, "max": 59},
                        {"grade": "E", "min": 0, "max": 49}
                    ]
                }
                with open(acct_app_cfg, 'w', encoding='utf-8') as fh:
                    json.dump(acct_cfg, fh, indent=2, ensure_ascii=False)
            except Exception:
                pass

        # Ensure student_photos dir exists but empty. Under strict S3 mode we
        # don't create local directories; the app should store photos to S3.
        if not STRICT_S3:
            photos_dir = os.path.join(acct_dir, 'student_photos')
            os.makedirs(photos_dir, exist_ok=True)

        # Create a default admin_meta.json so admin features don't accidentally
        # create a minimal file later which would wipe user-provided profile data.
        def write_admin_meta_default():
            try:
                import json, time
                adm = os.path.join(acct_dir, 'admin_meta.json')
                if os.path.exists(adm):
                    return
                username = (school_id or '').replace('_at_', '')
                created = int(time.time())
                default_meta = {
                    'account_number': '',
                    'username': username,
                    'email': f"{username}@local" if username else '',
                    'phone': '',
                    'school_name': '',
                    'location': '',
                    'country': '',
                    'created_at': created,
                    'trial_until': 0,
                    'active': False,
                    'disabled': False
                }
                with open(adm, 'w', encoding='utf-8') as fh:
                    json.dump(default_meta, fh, indent=2, ensure_ascii=False)
            except Exception:
                pass

        try:
            write_admin_meta_default()
        except Exception:
            pass

        # Copy messaging_config.json from global storage if present, else create a minimal default
        global_msg = os.path.join(root, 'messaging_config.json')
        acct_msg = os.path.join(acct_dir, 'messaging_config.json')
        if os.path.exists(global_msg) and not os.path.exists(acct_msg):
            try:
                import shutil
                shutil.copyfile(global_msg, acct_msg)
            except Exception:
                pass
        else:
            # minimal default: Africa's Talking (the project uses AT credentials)
            write_if_missing('messaging_config.json', {
                'provider': 'africastalking',
                'api_url': 'https://api.africastalking.com/version1/messaging',
                'username': '',
                'api_key': '',
                'password': '',
                'sender': '',
                'http_method': 'POST',
                'content_type': 'application/x-www-form-urlencoded',
                'extra_params': {}
            })

        return True
    except Exception:
        return False


def write_admin_meta(school_id: str, updates: dict, backup: bool = True, force_replace: bool = False):
    """Merge `updates` into the existing admin_meta.json for `school_id` and write atomically.
    Returns (True, None) on success or (False, error_message) on failure.
    Creates an optional timestamped backup and returns an error message on failure.
    """
    try:
        if not school_id:
            return False, 'school_id required'
        # If DB-only mode is enabled and DB available, use kv store
        try:
            if USE_DB_STRICT and _db is not None:
                _db.init_from_env()
                if _db.enabled():
                    key = f'storage:{school_id}:admin_meta.json'
                    cur = _db.get_kv(key) or {}
                    # proceed to merge updates into cur (same logic as before)
                    preserved = ['account_number', 'username', 'created_at', 'trial_until', 'active', 'disabled']
                    if force_replace:
                        merged = dict((updates or {}))
                        for k in preserved:
                            if k in cur and k not in merged:
                                merged[k] = cur.get(k)
                    else:
                        merged = dict(cur)
                        skipped = {}
                        for k, v in (updates or {}).items():
                            try:
                                if isinstance(v, str) and v.strip() == '' and k in cur and cur.get(k) not in (None, ''):
                                    skipped[k] = {'existing': cur.get(k), 'skipped_update': v}
                                    continue
                            except Exception:
                                pass
                            merged[k] = v
                    try:
                        _db.set_kv(key, merged)
                    except Exception:
                        pass
                    # create a lightweight backup entry if requested
                    if backup:
                        try:
                            _db.set_kv(f'storage:{school_id}:admin_meta.backup', {'saved': int(__import__('time').time()), 'meta': merged})
                        except Exception:
                            pass
                    return True, None
        except Exception:
            pass
        root = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')
        acct_dir = os.path.join(root, school_id)
        os.makedirs(acct_dir, exist_ok=True)
        adm_path = os.path.join(acct_dir, 'admin_meta.json')
        cur = {}
        try:
            if os.path.exists(adm_path):
                import json
                with open(adm_path, 'r', encoding='utf-8') as fh:
                    cur = json.load(fh) or {}
        except Exception:
            cur = {}

        # Determine the object to write.
        # By default we merge updates into current meta so unrelated fields are preserved.
        # If force_replace=True we will replace the writable fields with `updates` while
        # preserving a small set of system keys (account_number, username, created_at, trial_until, active, disabled).
        if force_replace:
            preserved = ['account_number', 'username', 'created_at', 'trial_until', 'active', 'disabled']
            merged = dict((updates or {}))
            # restore preserved system keys from current meta when not provided in updates
            for k in preserved:
                if k in cur and k not in merged:
                    merged[k] = cur.get(k)
        else:
            # Merge updates into current meta, but do not allow empty-string updates to
            # overwrite existing non-empty values. This prevents background processes
            # from wiping user-provided profile fields with default empty strings.
            merged = dict(cur)
            skipped = {}
            for k, v in (updates or {}).items():
                try:
                    # If incoming value is a string and empty, and current has a non-empty value,
                    # skip overwriting unless caller explicitly provided None.
                    if isinstance(v, str) and v.strip() == '' and k in cur and cur.get(k) not in (None, ''):
                        skipped[k] = {'existing': cur.get(k), 'skipped_update': v}
                        continue
                except Exception:
                    pass
                merged[k] = v

        # Write atomically
        try:
            import json, time
            tmp = adm_path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(merged, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, adm_path)
        except Exception as e:
            try:
                with open(adm_path, 'w', encoding='utf-8') as fh:
                    import json
                    json.dump(merged, fh, indent=2, ensure_ascii=False)
            except Exception as e2:
                return False, f'Failed to write admin_meta: {e2}'

        # Optional backup for inspection
        created_backup = None
        if backup:
            try:
                import json, time
                ts = int(time.time())
                bpath = os.path.join(acct_dir, f'admin_meta.backup_{ts}.json')
                with open(bpath, 'w', encoding='utf-8') as bf:
                    json.dump({'saved': ts, 'meta': merged}, bf, indent=2, ensure_ascii=False)
                created_backup = bpath
            except Exception:
                created_backup = None

        # If force_replace was requested, delete other previous backups and raw submission snapshots
        if force_replace:
            try:
                import glob
                # remove other admin_meta.backup_*.json files except the one we just created
                pattern = os.path.join(acct_dir, 'admin_meta.backup_*.json')
                for p in glob.glob(pattern):
                    try:
                        if created_backup and os.path.abspath(p) == os.path.abspath(created_backup):
                            continue
                        os.remove(p)
                    except Exception:
                        pass
                # remove any raw submission snapshots
                rawpat = os.path.join(acct_dir, 'admin_meta.submission_raw_*.json')
                for p in glob.glob(rawpat):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            except Exception:
                pass

        # If this write was authoritative (force_replace), also persist a last-good copy
        # that we'll use to detect and repair out-of-band changes.
        if force_replace:
            try:
                import json, time
                lg = os.path.join(acct_dir, 'admin_meta.last_good.json')
                tmp_lg = lg + '.tmp'
                with open(tmp_lg, 'w', encoding='utf-8') as fh:
                    json.dump({'saved': int(time.time()), 'meta': merged}, fh, indent=2, ensure_ascii=False)
                os.replace(tmp_lg, lg)
            except Exception:
                pass

        # append debug global log entry with some details about changes and skipped keys
        try:
            import json, time
            logp = os.path.join(root, 'debug_profile_saves.log')
            entry = {'time': int(time.time()), 'school_id': school_id, 'keys': list((updates or {}).keys()), 'force_replace': bool(force_replace)}
            # include skipped keys info if any
            if not force_replace and 'skipped' in locals() and skipped:
                entry['skipped'] = skipped
            # include a simple before/after diff sample
            try:
                diff = {}
                for k in (updates or {}).keys():
                    diff[k] = {'before': cur.get(k), 'after': merged.get(k)}
                entry['diff'] = diff
            except Exception:
                pass
            with open(logp, 'a', encoding='utf-8') as lf:
                lf.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception:
            pass

        return True, None
    except Exception as e:
        return False, str(e)


def restore_if_tampered(school_id: str):
    """If the admin_meta.json file was changed after the last authoritative save,
    restore the last-good copy (admin_meta.last_good.json). Returns (True, message)
    if a restoration was performed, or (False, reason) otherwise.
    """
    try:
        if not school_id:
            return False, 'school_id required'
        root = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')
        acct_dir = os.path.join(root, school_id)
        adm = os.path.join(acct_dir, 'admin_meta.json')
        lg = os.path.join(acct_dir, 'admin_meta.last_good.json')
        if not os.path.exists(lg) or not os.path.exists(adm):
            return False, 'no last-good or admin_meta missing'
        try:
            import json
            with open(lg, 'r', encoding='utf-8') as f:
                lg_obj = json.load(f) or {}
            lg_meta = lg_obj.get('meta') if isinstance(lg_obj, dict) else lg_obj
        except Exception:
            return False, 'failed to read last-good'
        try:
            with open(adm, 'r', encoding='utf-8') as f:
                adm_meta = json.load(f) or {}
        except Exception:
            adm_meta = {}
        # If they match, nothing to do
        if adm_meta == lg_meta:
            return False, 'no change'
        # Otherwise, restore the last-good copy atomically
        try:
            import json, time
            tmp = adm + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(lg_meta, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, adm)
            # log the restoration to diagnostics
            diag = os.path.join(root, 'profile_save_diagnostics.jsonl')
            entry = {'time': int(time.time()), 'acct': school_id, 'action': 'restored_last_good', 'note': 'admin_meta replaced by non-authoritative writer; restored last-good copy.'}
            try:
                with open(diag, 'a', encoding='utf-8') as df:
                    df.write(json.dumps(entry, ensure_ascii=False) + '\n')
            except Exception:
                pass
            # also append to debug log
            try:
                logp = os.path.join(root, 'debug_profile_saves.log')
                with open(logp, 'a', encoding='utf-8') as lf:
                    lf.write(json.dumps({'time': int(time.time()), 'school_id': school_id, 'action': 'restored_last_good'}, ensure_ascii=False) + '\n')
            except Exception:
                pass
            return True, 'restored'
        except Exception as e:
            return False, f'restore failed: {e}'
    except Exception as e:
        return False, str(e)


def ensure_last_good(school_id: str):
    """Ensure that a last-good file exists for the given account by copying the
    current admin_meta.json into admin_meta.last_good.json if the latter is missing.
    Returns (True, message) if created or already exists, (False, reason) otherwise.
    """
    try:
        if not school_id:
            return False, 'school_id required'
        root = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')
        acct_dir = os.path.join(root, school_id)
        adm = os.path.join(acct_dir, 'admin_meta.json')
        lg = os.path.join(acct_dir, 'admin_meta.last_good.json')
        if not os.path.exists(adm):
            return False, 'admin_meta missing'
        if os.path.exists(lg):
            return True, 'already'
        try:
            import json, time
            with open(adm, 'r', encoding='utf-8') as f:
                adm_meta = json.load(f) or {}
            tmp = lg + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump({'saved': int(time.time()), 'meta': adm_meta}, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, lg)
            return True, 'created'
        except Exception as e:
            return False, f'failed: {e}'
    except Exception as e:
        return False, str(e)
