"""Simple migration tool to upload the current saved_exams_storage/ tree to S3.

Usage: set environment variables S3_BUCKET and optionally S3_PREFIX, then run:
    python scripts/migrate_saved_exams_to_s3.py

This script will walk the local saved_exams_storage directory and upload files
preserving the relative paths under the S3 prefix.
"""
import os
import sys
from modules import storage

ROOT = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')


def main():
    # storage adapter will initialize S3 when configured; ensure local ROOT exists
    if not os.path.exists(ROOT):
        print('Local saved_exams_storage not found at', ROOT)
        sys.exit(1)
    for root, dirs, files in os.walk(ROOT):
        for f in files:
            local_path = os.path.join(root, f)
            rel = os.path.relpath(local_path, ROOT)
            key = rel.replace('\\', '/')
            print('Uploading', local_path, '->', key)
            try:
                ok = storage.upload_file(local_path, key)
            except Exception:
                ok = False
            if not ok:
                print('Failed:', local_path)
    print('Migration completed. Verify objects in the S3 bucket/prefix.')


if __name__ == '__main__':
    main()
