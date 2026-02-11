"""
One-off normalization script for saved exams.

Usage:
  python utils\normalize_saved_exams.py --mapping saved_exams_storage/ta_class_map.json [--apply]

This script will walk all folders under saved_exams_storage, load raw_data.pkl or data.pkl, create
two new columns `grade_norm` and `stream_norm` by applying the mapping (or heuristics), and write
normalized_data.pkl when --apply is provided. Backups are created.

Be careful: run without --apply to preview changes.
"""
import os
import sys
import json
import argparse
import pandas as pd
from modules import storage as _storage


def load_mapping(path):
    try:
        # try storage adapter first (handles S3)
        d = _storage.read_json(path)
        if d is not None:
            return {k.upper(): v for k, v in d.items()}
        # fallback to local file
        with open(path, 'r', encoding='utf-8') as f:
            d = json.load(f)
            return {k.upper(): v for k, v in d.items()}
    except Exception:
        return {}


def normalize_token(tok, cmap):
    if tok is None:
        return ('', '')
    s = str(tok).strip()
    key = s.upper()
    if key in cmap:
        mapped = str(cmap[key])
        # try split into digits + letters
        import re
        m = re.match(r"^(\d+)([A-Za-z]?)$", mapped)
        if m:
            return (m.group(1), m.group(2))
        return (mapped, '')
    # fallback: try to extract digits and trailing letters
    import re
    m = re.match(r".*?(\d+).*?([A-Za-z])?$", s)
    if m:
        return (m.group(1), (m.group(2) or '').upper())
    return (s, '')


def process_exam_folder(folder, cmap, apply=False):
    # folder can be a local path or an exam_id key when using S3
    df = None
    try:
        if os.path.isdir(folder):
            raw = os.path.join(folder, 'raw_data.pkl')
            data = os.path.join(folder, 'data.pkl')
            src = raw if os.path.exists(raw) else (data if os.path.exists(data) else None)
            if not src:
                return None
            df = pd.read_pickle(src)
        else:
            # treat folder as exam_id key
            raw_key = f"{folder}/raw_data.pkl"
            data_key = f"{folder}/data.pkl"
            tmp = _storage.read_pickle(raw_key)
            if tmp is None:
                tmp = _storage.read_pickle(data_key)
            if tmp is None:
                return None
            df = tmp
    except Exception:
        return None
    # find candidate class column
    cls_col = None
    for c in df.columns:
        low = str(c).lower()
        if any(x in low for x in ['class', 'grade', 'form', 'grade_name']):
            cls_col = c
            break
    # fallback: pick the first column with many digits
    if cls_col is None:
        best = None
        best_score = 0
        for c in df.columns:
            try:
                vals = df[c].astype(str).dropna().str.strip()
                if vals.empty:
                    continue
                score = vals.str.contains(r'\d').mean()
                if score > best_score:
                    best_score = score
                    best = c
            except Exception:
                continue
        cls_col = best
    # stream col detection
    stream_col = None
    if cls_col:
        for c in df.columns:
            if c == cls_col:
                continue
            try:
                vals = df[c].astype(str).dropna().str.strip()
                if vals.empty:
                    continue
                if vals.str.match(r'^[A-Za-z]$').mean() > 0.05:
                    stream_col = c
                    break
            except Exception:
                continue

    grade_norm = []
    stream_norm = []
    for i, row in df.iterrows():
        raw_cls = row[cls_col] if cls_col in df.columns else ''
        raw_str = row[stream_col] if stream_col and stream_col in df.columns else ''
        # prefer mapping on raw_cls first
        g, s = normalize_token(raw_cls, cmap)
        if (not g or g == '') and raw_str:
            g2, s2 = normalize_token(raw_str, cmap)
            if g2:
                g = g2
                s = s2 or s
        # fallback combine
        grade_norm.append(g)
        stream_norm.append(s)

    df['grade_norm'] = grade_norm
    df['stream_norm'] = stream_norm

    if apply:
        # backup old data
        bak = os.path.join(folder, 'normalized_backup')
        os.makedirs(bak, exist_ok=True)
        import shutil
        shutil.copy(src, os.path.join(bak, os.path.basename(src)))
        out = os.path.join(folder, 'normalized_data.pkl')
        df.to_pickle(out)
        return out
    return df.head(10)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mapping', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    cmap = load_mapping(args.mapping)
    # Determine storage root. If running in S3 mode, list exam ids from objects.
    if os.environ.get('STORAGE_PROVIDER', '').lower() == 's3':
        objs = _storage.list_objects('')
        # extract top-level directories (exam ids)
        exam_ids = set()
        for o in objs:
            parts = o.split('/')
            if len(parts) >= 2:
                exam_ids.add(parts[0])
        for eid in sorted(exam_ids):
            res = process_exam_folder(eid, cmap, apply=args.apply)
            print('Processed', eid, '->', str(res))
    else:
        # local filesystem
        try:
            storage = _storage.get_storage_dir()
        except Exception:
            storage = os.path.join(os.getcwd(), 'saved_exams_storage')
        if not os.path.exists(storage):
            print('saved_exams_storage not found at', storage)
            sys.exit(1)
        for item in os.listdir(storage):
            f = os.path.join(storage, item)
            if os.path.isdir(f):
                res = process_exam_folder(f, cmap, apply=args.apply)
                print('Processed', item, '->', str(res))


if __name__ == '__main__':
    main()
