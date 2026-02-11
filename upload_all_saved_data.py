"""Upload all persistent app data to Firebase Storage.

Usage examples (PowerShell):

# Set credentials (process only) and bucket first, then run:
# Set path to service account JSON file
[Environment]::SetEnvironmentVariable('FIREBASE_SERVICE_ACCOUNT_PATH', 'C:\path\to\serviceAccount.json', 'Process')
[Environment]::SetEnvironmentVariable('FIREBASE_BUCKET', 'eduscore-analytics.appspot.com', 'Process')
python .\upload_all_saved_data.py --confirm

# Dry-run to see what would be uploaded
python .\upload_all_saved_data.py --dry-run

Security: do NOT commit service account keys to version control. Use environment variables or a protected file.
"""
from __future__ import annotations
import argparse
import os
import sys
import time
from pathlib import Path

# Import the firebase helper we added. It will attempt to initialize from env vars.
try:
    from modules import firebase_storage as fb
except Exception:
    fb = None

# Directories and files to include (relative to repo root)
INCLUDE_PATHS = [
    'saved_exams_storage',
    'saved_exams_storage_backup_20251128_052137',
    'saved_exams_storage_backup_20251128_153900',
    'saved_exams_storage_backup_20251128_194929',
    'saved_exams_storage_backup_20251201_125813',
    'saved_exams_storage_backup_20251203_122407',
    'saved_exams_storage_backup_20251203_124349',
    'saved_exams_storage_backup_20251206_023545',
    'saved_exams_storage_backup_20251213_001010',
    'saved_exams_storage_backup_20251213_003426',
    'saved_exams_storage_backup_20251213_140433',
    'saved_exams_storage_backup_20251213_140811',
    'saved_exams_storage_backup_20251213_142052',
    'saved_exams_storage_backup_20251213_143424',
    'saved_exams_storage_backup_20251213_144157',
    'saved_exams_storage_backup_20251213_145432',
    'saved_exams_storage_backup_20251221_190610',
    'saved_exams_storage_backup_20251222_202917',
    'saved_exams_storage_backup_20251222_203323',
    'saved_exams_storage_backup_20251225_201013',
    'saved_exams_storage_backup_20251225_202038',
    'saved_exams_storage_backup_20251225_202639',
    'saved_exams_storage_backup_20251225_202710',
    'saved_exams_storage_backup_20260123_223329',
    'saved_exams_storage_backup_20260123_223427',
    'saved_exams_storage_backup_20260125_020206',
    'saved_exams_storage_backup_20260125_033116',
    'saved_exams_storage_backup_samples_20251206_024320',
    'saved_exams_storage_backup_samples_20251206_024453',
    'saved_exams_storage_admin_deleted_1764993322',
    'saved_exams_storage_admin_deleted_1764993329',
    'saved_exams_storage_admin_deleted_1764993347',
    'saved_exams_storage_admin_deleted_1764993437',
    'saved_exams_storage_admin_deleted_1764993447',
    'saved_exams_storage_deleted_backup_1764989942',
    'exam_database',
]
# Additional files to include explicitly
INCLUDE_FILES = [
    'saved_exams_clean_summary.json',
    'raw_marks_backup.csv',
    'app_persistent_config.json',
    'requirements.txt',
]


def gather_files(root: Path):
    """Yield (local_path, relative_path) tuples for files to upload."""
    seen = set()
    for p in INCLUDE_PATHS:
        base = root / p
        if not base.exists():
            continue
        if base.is_file():
            rel = base.relative_to(root).as_posix()
            seen.add(base.resolve())
            yield (str(base.resolve()), rel)
            continue
        for fp in base.rglob('*'):
            if fp.is_file():
                rel = fp.relative_to(root).as_posix()
                seen.add(fp.resolve())
                yield (str(fp.resolve()), rel)
    for f in INCLUDE_FILES:
        p = root / f
        if p.exists() and p.is_file():
            rel = p.relative_to(root).as_posix()
            yield (str(p.resolve()), rel)


def main():
    parser = argparse.ArgumentParser(description='Upload persistent app data to Firebase Storage')
    parser.add_argument('--dry-run', action='store_true', help='List files that would be uploaded')
    parser.add_argument('--confirm', action='store_true', help='Perform upload (requires Firebase env vars or configured helper)')
    parser.add_argument('--prefix', default=None, help='Destination prefix in bucket (defaults to app_backup/<timestamp>)')
    args = parser.parse_args()

    repo_root = Path(__file__).parent

    # Prepare destination prefix
    ts = int(time.time())
    dest_prefix = args.prefix or f"app_backup/{ts}"

    files = list(gather_files(repo_root))
    if not files:
        print('No files found to upload. Check that you are running this from the project root and that storage folders exist.')
        return 1

    print(f'Found {len(files)} files to upload under prefix "{dest_prefix}"')
    for local, rel in files:
        print(' -', rel)

    if args.dry_run:
        print('\nDry run; no uploads performed.')
        return 0

    if not args.confirm:
        print('\nRun with --confirm to perform the upload.')
        return 0

    # Initialize firebase helper
    if fb is None:
        try:
            from modules import firebase_storage as fb
        except Exception:
            fb = None
    if fb is None:
        print('Firebase helper not available (modules/firebase_storage.py missing). Aborting.')
        return 1

    ok = False
    try:
        ok = fb.init_from_env()
    except Exception:
        ok = False
    if not ok or not fb.is_initialized():
        print('Firebase not initialized. Set FIREBASE_SERVICE_ACCOUNT_JSON or FIREBASE_SERVICE_ACCOUNT_PATH and FIREBASE_BUCKET in the environment, and ensure firebase-admin is installed.')
        return 1

    failures = []
    uploaded = 0
    for local, rel in files:
        dest = f'{dest_prefix}/{rel}'
        try:
            print(f'Uploading {rel} -> {dest} ...', end=' ')
            success = fb.upload_blob(local, dest)
            if success:
                print('OK')
                uploaded += 1
            else:
                print('FAILED')
                failures.append((local, dest))
        except Exception as e:
            print('ERROR', e)
            failures.append((local, dest, str(e)))

    print(f'Uploaded {uploaded}/{len(files)} files.')
    if failures:
        print('Failures:')
        for f in failures[:50]:
            print(' -', f)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
