import os
import json
import io
import hashlib
from datetime import datetime
from typing import Optional, Dict, Tuple, List

try:
    from PIL import Image  # type: ignore
    _PIL_AVAILABLE = True
except Exception:
    _PIL_AVAILABLE = False

# Resolve base storage dir similar to other modules
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
from modules import storage as _storage
STORAGE_DIR = _storage.get_storage_dir()
# logical keys / local dir
PHOTOS_DIR = os.path.join(STORAGE_DIR, 'student_photos')
MAPPING_FILE = 'student_photos.json'  # stored at bucket root or local root

# ensure local dir for non-S3 mode
try:
    if not os.environ.get('STORAGE_PROVIDER', '').lower() == 's3':
        os.makedirs(PHOTOS_DIR, exist_ok=True)
except Exception:
    pass


def _load_map() -> Dict[str, Dict]:
    try:
        data = _storage.read_json(MAPPING_FILE)
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def _save_map(map_obj: Dict[str, Dict]) -> None:
    try:
        _storage.write_json(MAPPING_FILE, map_obj)
    except Exception:
        pass


def _normalize_id(name: Optional[str], adm_no: Optional[str]) -> str:
    """Prefer Adm No if present, else stable hash of name.
    Returns a filesystem-safe identifier."""
    if adm_no:
        sid = str(adm_no).strip()
        # keep digits/letters only
        sid = ''.join(ch for ch in sid if ch.isalnum())
        if sid:
            return sid
    nm = (name or '').strip().lower()
    if not nm:
        nm = 'unknown'
    return hashlib.sha1(nm.encode('utf-8')).hexdigest()[:16]


def get_student_id_from_row(row: Dict) -> Tuple[str, str, str]:
    """Extract a stable student id, name, and adm no from a student record/row.
    Supported keys: 'Name', 'Adm No' (fallbacks 'AdmNo','Adm_No')."""
    name = str(row.get('Name', '') or row.get('name', '')).strip()
    adm_no = (
        row.get('Adm No')
        or row.get('AdmNo')
        or row.get('Adm_No')
        or row.get('admno')
        or row.get('adm_no')
        or ''
    )
    adm_no = '' if adm_no is None else str(adm_no).strip()
    sid = _normalize_id(name, adm_no)
    return sid, name, adm_no


def get_photo_path_by_id(student_id: str) -> Optional[str]:
    m = _load_map()
    entry = m.get(student_id)
    if not entry:
        return None
    path = entry.get('path')
    # If stored in S3, path will be a key; download to temp file for local usage
    try:
        if path:
            # S3 mode: read_bytes will return bytes
            b = _storage.read_bytes(path)
            if b:
                # write to a temp file and return path
                import tempfile
                ext = os.path.splitext(path)[1] or '.jpg'
                tf = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                tf.write(b)
                tf.close()
                return tf.name
            # if path exists locally
            if os.path.exists(path):
                return path
    except Exception:
        pass
    # fallback to default path patterns
    for ext in ('.png', '.jpg', '.jpeg'):
        key = f'student_photos/{student_id}{ext}'
        # try S3 first
        try:
            b = _storage.read_bytes(key)
            if b:
                import tempfile
                tf = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                tf.write(b); tf.close()
                return tf.name
        except Exception:
            pass
        p = os.path.join(PHOTOS_DIR, f'{student_id}{ext}')
        if os.path.exists(p):
            return p
    return None


def get_photo_path(name: Optional[str]=None, adm_no: Optional[str]=None) -> Optional[str]:
    sid = _normalize_id(name, adm_no)
    return get_photo_path_by_id(sid)


def delete_photo(name: Optional[str]=None, adm_no: Optional[str]=None) -> bool:
    sid = _normalize_id(name, adm_no)
    m = _load_map()
    ok = False
    if sid in m:
        path = m[sid].get('path')
        try:
            if path:
                try:
                    # Prefer adapter delete when available (handles S3 and local)
                    if hasattr(_storage, 'delete'):
                        try:
                            _storage.delete(path)
                        except Exception:
                            # fallback to removing local file
                            if os.path.exists(path):
                                os.remove(path)
                    else:
                        # adapter has no delete: try storage_s3 if present
                        try:
                            from modules import storage_s3 as _s3_mod
                            try:
                                _s3_mod.init_from_env()
                                _s3_mod.delete_object(path)
                            except Exception:
                                if os.path.exists(path):
                                    os.remove(path)
                        except Exception:
                            if os.path.exists(path):
                                os.remove(path)
                except Exception:
                    try:
                        if os.path.exists(path):
                            os.remove(path)
                    except Exception:
                        pass
        except Exception:
            pass
        m.pop(sid, None)
        _save_map(m)
        ok = True
    else:
        # try removing file if present without map
        for ext in ('.png', '.jpg', '.jpeg'):
            p = os.path.join(PHOTOS_DIR, f'{sid}{ext}')
            if os.path.exists(p):
                try:
                    os.remove(p)
                    ok = True
                except Exception:
                    pass
    return ok


def save_photo(file_bytes: bytes, filename: str, name: Optional[str]=None, adm_no: Optional[str]=None, max_size: int = 512) -> Optional[str]:
    """Persist a student's photo and update mapping. Returns path or None.
    - max_size: longest side in pixels (resize if PIL available).
    """
    sid = _normalize_id(name, adm_no)
    # choose extension
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ('.png', '.jpg', '.jpeg'):
        ext = '.png'
    # Process image into bytes (optionally resize)
    try:
        out_bytes = None
        if _PIL_AVAILABLE:
            from io import BytesIO as _BI
            buf = _BI()
            with Image.open(io.BytesIO(file_bytes)) as im:
                im = im.convert('RGB') if ext in ('.jpg', '.jpeg') else im.convert('RGBA')
                w, h = im.size
                if max(w, h) > max_size:
                    scale = max_size / float(max(w, h))
                    new_w = max(1, int(w * scale))
                    new_h = max(1, int(h * scale))
                    im = im.resize((new_w, new_h))
                if ext in ('.jpg', '.jpeg'):
                    im.save(buf, format='JPEG', quality=90)
                else:
                    im.save(buf, format='PNG')
            out_bytes = buf.getvalue()
        else:
            out_bytes = file_bytes
    except Exception:
        return None

    # Try to persist via storage adapter (S3-first). Fall back to local file if adapter not available.
    key = f'student_photos/{sid}{ext}'
    saved_path = None
    try:
        if _storage is not None and hasattr(_storage, 'write_bytes'):
            try:
                ok = _storage.write_bytes(key, out_bytes, content_type='image/jpeg' if ext in ('.jpg', '.jpeg') else 'image/png')
                if ok:
                    saved_path = key
            except Exception:
                saved_path = None
        # local fallback
        if saved_path is None:
            os.makedirs(PHOTOS_DIR, exist_ok=True)
            out_path = os.path.join(PHOTOS_DIR, f'{sid}{ext}')
            try:
                with open(out_path, 'wb') as f:
                    f.write(out_bytes)
                saved_path = out_path
            except Exception:
                return None
    except Exception:
        return None

    # update mapping
    m = _load_map()
    m[sid] = {
        'path': saved_path,
        'name': name or '',
        'adm_no': adm_no or '',
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    _save_map(m)
    return saved_path


def list_all_photos() -> Dict[str, Dict]:
    """Return the full mapping of student_id -> entry."""
    return _load_map()


def import_bulk(photo_bytes_lookup: Dict[str, bytes], mapping: List[Dict[str, str]], overwrite: bool = True, max_size: int = 512) -> Dict[str, str]:
    """Bulk import photos.
    Args:
        photo_bytes_lookup: dict filename -> raw bytes for each image (already read from zip or uploads).
        mapping: list of dict rows each containing at minimum one of: 'Adm No' or 'Admission', plus 'Name', and either a 'Filename' column
                 referencing a key in photo_bytes_lookup OR a 'Photo' column giving a filename.
        overwrite: If False, skip students that already have a photo.
        max_size: resize limit for longest side.
    Returns:
        dict of student_id -> status message ("imported", "skipped", "missing-file", "error")
    """
    results: Dict[str, str] = {}
    for row in mapping:
        name = row.get('Name') or row.get('name') or ''
        adm = row.get('Adm No') or row.get('Admission') or row.get('adm_no') or ''
        filename = row.get('Filename') or row.get('Photo') or row.get('photo') or ''
        sid = _normalize_id(name, adm)
        if not filename:
            results[sid] = 'missing-file'
            continue
        if not overwrite and get_photo_path_by_id(sid):
            results[sid] = 'skipped'
            continue
        # match case-insensitively in provided lookup
        key_match = None
        lower_map = {k.lower(): k for k in photo_bytes_lookup.keys()}
        if filename.lower() in lower_map:
            key_match = lower_map[filename.lower()]
        else:
            # try without extension or partial
            base = os.path.splitext(filename.lower())[0]
            for k_low, orig in lower_map.items():
                if os.path.splitext(k_low)[0] == base:
                    key_match = orig; break
        if not key_match:
            results[sid] = 'missing-file'
            continue
        try:
            saved = save_photo(photo_bytes_lookup[key_match], key_match, name=name, adm_no=adm, max_size=max_size)
            results[sid] = 'imported' if saved else 'error'
        except Exception:
            results[sid] = 'error'
    return results


def export_class_template(students: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Produce a template rows list with keys: Name, Adm No, Filename.
    Caller can serialize to CSV for user to fill Filename column.
    """
    template = []
    for s in students:
        name = s.get('Name') or s.get('name') or ''
        adm = s.get('Adm No') or s.get('AdmNo') or s.get('adm_no') or ''
        template.append({'Name': name, 'Adm No': adm, 'Filename': ''})
    return template


def validate_mapping_against_students(mapping: List[Dict[str, str]], students: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    """Validate CSV mapping rows against a list of students.
    Returns dict with keys: matched, missing_adm, missing_name, duplicate_rows.
    Matching rule: prefer Adm No match; fallback to exact name match (case-insensitive).
    """
    # Build quick lookups
    by_adm = {}
    by_name = {}
    for s in students:
        name = str(s.get('Name', s.get('name', ''))).strip()
        adm = str(s.get('Adm No', s.get('AdmNo', s.get('adm_no', '')))).strip()
        if adm:
            by_adm[adm] = s
        if name:
            by_name[name.lower()] = s
    matched = []
    missing_adm = []
    missing_name = []
    seen_keys = set()
    duplicate_rows = []
    for r in mapping:
        nm = str(r.get('Name', r.get('name', ''))).strip()
        ad = str(r.get('Adm No', r.get('Admission', r.get('adm_no', '')))).strip()
        key = (nm.lower(), ad)
        if key in seen_keys:
            duplicate_rows.append(r)
            continue
        seen_keys.add(key)
        row_target = None
        if ad and ad in by_adm:
            row_target = by_adm[ad]
        elif nm and nm.lower() in by_name:
            row_target = by_name[nm.lower()]
        if row_target is None:
            if ad:
                missing_adm.append(r)
            else:
                missing_name.append(r)
        else:
            matched.append(r)
    return {
        'matched': matched,
        'missing_adm': missing_adm,
        'missing_name': missing_name,
        'duplicate_rows': duplicate_rows,
    }

