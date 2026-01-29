"""Ensure per-account folders exist for every user in saved_exams_storage/users.json.

This scans the local users store and calls modules.storage.initialize_account()
for any username that doesn't already have a proper per-account folder (by marker files).

Run locally:
    python .\scripts\ensure_accounts_for_users.py
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent / 'saved_exams_storage'
USERS_FILE = ROOT / 'users.json'


def load_users():
    try:
        if not USERS_FILE.exists():
            print('No users.json found.')
            return {}
        return json.loads(USERS_FILE.read_text(encoding='utf-8') or '{}')
    except Exception as e:
        print('Failed to load users.json:', e)
        return {}


def is_account_folder_ok(acct_dir: Path):
    # marker files that indicate a valid account
    markers = {'exams_metadata.json', 'student_contacts.json', 'app_persistent_config.json', 'messaging_config.json'}
    try:
        files = {p.name for p in acct_dir.iterdir() if p.is_file()}
        return bool(markers.intersection(files))
    except Exception:
        return False


def main():
    users = load_users()
    if not users:
        print('No users to process.')
        return

    try:
        from modules.auth import safe_email_to_schoolid
        from modules import storage as _storage
    except Exception as e:
        print('Failed to import modules.auth or modules.storage:', e)
        sys.exit(1)

    created = 0
    fixed = 0
    for uname in users.keys():
        school_id = safe_email_to_schoolid(f"{uname}@local")
        acct_dir = ROOT / school_id
        if not acct_dir.exists():
            print(f'Creating account folder for user: {uname} -> {school_id}')
            ok = _storage.initialize_account(school_id)
            if ok:
                created += 1
            else:
                print(f'  Failed to initialize account for {school_id}')
            continue

        if not is_account_folder_ok(acct_dir):
            print(f'Account folder missing marker files, attempting to initialize: {school_id}')
            ok = _storage.initialize_account(school_id)
            if ok:
                fixed += 1
            else:
                print(f'  Failed to initialize account for {school_id}')

    print(f'Done. created={created}, fixed={fixed}')


if __name__ == '__main__':
    main()
