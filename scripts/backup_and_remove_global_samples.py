#!/usr/bin/env python3
"""
Safe backup-and-remove script for global sample data in saved_exams_storage.

What it does:
- If present, moves `saved_exams_storage/student_contacts.json` into a
  timestamped backup folder `saved_exams_storage_backup_samples_<ts>/student_contacts.json`.
- If present, moves the entire `saved_exams_storage/student_photos/` folder into the
  same timestamped backup folder.

This is non-destructive: files are moved (not deleted) so you can restore them
from the backup if needed. Run this from the repository root.

Usage (PowerShell):
  python .\scripts\backup_and_remove_global_samples.py

"""
import os
import shutil
import datetime
from pathlib import Path


def main():
    repo_root = Path(__file__).resolve().parents[1]
    storage_dir = repo_root / 'saved_exams_storage'
    if not storage_dir.exists():
        print(f"No saved_exams_storage directory found at {storage_dir}")
        return

    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_root = repo_root / f'saved_exams_storage_backup_samples_{ts}'
    backup_root.mkdir(parents=True, exist_ok=True)

    moved_any = False

    contacts = storage_dir / 'student_contacts.json'
    if contacts.exists():
        dest = backup_root / 'student_contacts.json'
        print(f"Moving {contacts} -> {dest}")
        try:
            shutil.move(str(contacts), str(dest))
            moved_any = True
        except Exception as e:
            print(f"Failed to move contacts file: {e}")

    photos = storage_dir / 'student_photos'
    if photos.exists() and any(photos.iterdir()):
        dest = backup_root / 'student_photos'
        print(f"Moving {photos} -> {dest}")
        try:
            shutil.move(str(photos), str(dest))
            moved_any = True
        except Exception as e:
            print(f"Failed to move student_photos: {e}")

    # Also look for a top-level sample exam metadata file that might be global and unwanted
    meta = storage_dir / 'exams_metadata.json'
    if meta.exists():
        # Only move if it contains exams (not empty dict)
        try:
            import json
            data = json.loads(meta.read_text(encoding='utf-8'))
            if data:  # non-empty
                dest = backup_root / 'exams_metadata.json'
                print(f"Moving {meta} -> {dest}")
                try:
                    shutil.move(str(meta), str(dest))
                    moved_any = True
                except Exception as e:
                    print(f"Failed to move exams_metadata.json: {e}")
        except Exception:
            pass

    # Move any global exam folders: heuristics -> folder at storage_dir/* that contains
    # data.pkl or raw_data.pkl at its root. Skip folders that look like per-account
    # folders (those that contain app_persistent_config.json or student_contacts.json).
    for child in storage_dir.iterdir():
        # skip backups created previously
        if child.name.startswith('saved_exams_storage_backup_samples_'):
            continue
        if child.is_dir():
            try:
                # skip known per-account markers
                if (child / 'app_persistent_config.json').exists() or (child / 'student_contacts.json').exists() or (child / 'messaging_config.json').exists():
                    # looks like an account folder -> skip
                    continue
                # detect exam folder markers
                if (child / 'data.pkl').exists() or (child / 'raw_data.pkl').exists() or any(child.glob('*.pkl')):
                    dest = backup_root / child.name
                    print(f"Moving exam folder {child} -> {dest}")
                    try:
                        shutil.move(str(child), str(dest))
                        moved_any = True
                    except Exception as e:
                        print(f"Failed to move {child}: {e}")
            except Exception:
                continue

    if moved_any:
        print(f"Backup completed. Files moved to: {backup_root}")
    else:
        print("No sample global files found to move. Nothing changed.")


if __name__ == '__main__':
    main()
