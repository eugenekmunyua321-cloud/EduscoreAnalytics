"""Migrate existing saved_exams_storage contents into the configured Postgres DB.
This script uses `modules.db` helpers. Configure RENDER_DATABASE_URL or DATABASE_URL in the environment
before running.
"""
import os
import json
from modules import db
from pathlib import Path


def migrate(root_path: str):
    ok = db.init_from_env()
    if not ok:
        print('DB not initialized. Set RENDER_DATABASE_URL or DATABASE_URL in the environment and ensure requirements are installed.')
        return
    root = Path(root_path)
    if not root.exists():
        print('Root path not found:', root)
        return
    # iterate per-account folders and migrate exams_metadata.json and exam files
    for acct in root.iterdir():
        if not acct.is_dir():
            continue
        school_id = acct.name
        meta_path = acct / 'exams_metadata.json'
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding='utf-8') or '{}')
        except Exception:
            meta = {}
        for exam_id, md in meta.items():
            print(f'Migrating exam {exam_id} for {school_id}...')
            db.save_exam_metadata(school_id, exam_id, md)
            exam_dir = acct / exam_id
            if exam_dir.exists() and exam_dir.is_dir():
                # save pickles and config.json
                for fname in ('data.pkl', 'raw_data.pkl', 'config.json'):
                    p = exam_dir / fname
                    if p.exists():
                        try:
                            b = p.read_bytes()
                            db.save_exam_file(school_id, exam_id, fname, b, mimetype='application/octet-stream')
                        except Exception as e:
                            print('Failed to save file', p, e)
    print('Migration complete.')


if __name__ == '__main__':
    ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'saved_exams_storage')
    migrate(ROOT)
