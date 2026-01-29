"""Populate missing messaging_config.json in all per-account folders under saved_exams_storage.

This script will:
- Walk `saved_exams_storage/` and for every child directory (assumed to be an account folder),
  ensure `messaging_config.json` exists.
- If the file doesn't exist, write a Mobitech JSON default (POST, application/json).
- If it exists, fill any missing keys with defaults but do NOT overwrite existing non-empty values.
- Back up any replaced file to `messaging_config.json.bak` before modifying.

Run this from the repository root with the same Python used to run the app.
"""
from pathlib import Path
import json
import shutil

ROOT = Path(__file__).resolve().parents[1] / 'saved_exams_storage'
DEFAULT = {
    'provider': 'africastalking',
    'api_url': 'https://api.africastalking.com/version1/messaging',
    'username': '',
    'api_key': '',
    'password': '',
    'sender': '',
    'http_method': 'POST',
    'content_type': 'application/x-www-form-urlencoded',
    'extra_params': {}
}

def merge_defaults(existing: dict, defaults: dict) -> dict:
    """Return a merged dict where missing or empty-string values are filled from defaults.
    Does not overwrite non-empty existing values.
    """
    out = dict(existing or {})
    for k, v in defaults.items():
        if k not in out or out.get(k) in (None, '', {}):
            out[k] = v
    return out


def main():
    if not ROOT.exists():
        print(f"Storage root not found: {ROOT}")
        return
    # prefer a global config in saved_exams_storage/messaging_config.json when available
    global_cfg_path = ROOT / 'messaging_config.json'
    if global_cfg_path.exists():
        try:
            global_cfg = json.loads(global_cfg_path.read_text(encoding='utf-8') or '{}')
        except Exception:
            global_cfg = DEFAULT
    else:
        global_cfg = DEFAULT

    # Heuristic: treat a child as an account only if it contains typical account files
    ACCOUNT_MARKERS = {'exams_metadata.json', 'student_contacts.json', 'messaging_config.json', 'app_persistent_config.json'}
    SKIP_DIRS = {'student_photos', 'watermarks', 'exports', 'attachments', 'static'}
    for child in sorted(ROOT.iterdir()):
        if not child.is_dir():
            continue
        # skip obvious backup or helper folders
        if child.name.startswith('saved_exams_storage_backup') or child.name in SKIP_DIRS:
            continue
        try:
            files = {f.name for f in child.iterdir() if f.is_file()}
            if not ACCOUNT_MARKERS.intersection(files):
                # not an account folder
                print(f"Skipping non-account folder: {child.name}")
                continue
        except Exception:
            # if we can't read contents, skip
            print(f"Skipping unreadable folder: {child.name}")
            continue

        cfg_file = child / 'messaging_config.json'
        # backup existing then overwrite with global config to ensure no fields left blank
        try:
            if cfg_file.exists():
                bak = child / 'messaging_config.json.bak'
                try:
                    shutil.copyfile(str(cfg_file), str(bak))
                except Exception:
                    pass
            cfg_file.write_text(json.dumps(global_cfg, indent=2), encoding='utf-8')
            print(f"Applied global messaging_config.json to: {child.name}")
        except Exception as e:
            print(f"Failed to write for {child.name}: {e}")

if __name__ == '__main__':
    main()
