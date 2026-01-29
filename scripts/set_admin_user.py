"""Create or update an admin local user and ensure admins.json includes them.

Usage:
    python set_admin_user.py --username munyua --password "@MUNYUA2103"

If no args provided, defaults will be username=munyua and password='@MUNYUA2103'.

This writes/updates `saved_exams_storage/users.json` and `saved_exams_storage/admins.json`.
It uses PBKDF2-HMAC-SHA256 with 100k iterations to derive the stored key (same as app).
"""
import argparse
import os
import json
import base64
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'saved_exams_storage'
USERS_FILE = ROOT / 'users.json'
ADMINS_FILE = ROOT / 'admins.json'

def ensure_dir():
    ROOT.mkdir(parents=True, exist_ok=True)

def load_users():
    if not USERS_FILE.exists():
        return {}
    try:
        return json.loads(USERS_FILE.read_text(encoding='utf-8') or '{}')
    except Exception:
        return {}

def save_users(users: dict):
    tmp = USERS_FILE.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as fh:
        json.dump(users, fh, indent=2, ensure_ascii=False)
    tmp.replace(USERS_FILE)

def load_admins():
    if not ADMINS_FILE.exists():
        return []
    try:
        data = json.loads(ADMINS_FILE.read_text(encoding='utf-8') or '{}')
        if isinstance(data, dict):
            return data.get('admins', [])
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []

def save_admins(admins: list):
    ADMINS_FILE.write_text(json.dumps({'admins': admins}, indent=2), encoding='utf-8')

def create_or_update_user(username: str, password: str, display_name: str = None):
    users = load_users()
    username = username.strip().lower()
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    users[username] = {
        'display_name': display_name or username,
        'salt': base64.b64encode(salt).decode('ascii'),
        'key': base64.b64encode(key).decode('ascii')
    }
    save_users(users)
    print(f"Created/updated user: {username}")

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--username', '-u', default='munyua')
    p.add_argument('--password', '-p', default='@MUNYUA2103')
    args = p.parse_args()
    ensure_dir()
    create_or_update_user(args.username, args.password, display_name=args.username)
    admins = load_admins()
    email_like = f"{args.username}@local"
    if email_like not in admins:
        admins.append(email_like)
        save_admins(admins)
        print(f"Added admin: {email_like} to {ADMINS_FILE}")
    else:
        print(f"Admin already present: {email_like}")
    print('Done.')
