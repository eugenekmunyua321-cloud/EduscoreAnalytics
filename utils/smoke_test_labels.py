import os
import json
import pandas as pd
import re

ROOT = os.path.dirname(os.path.dirname(__file__))
from modules import storage as _storage
STORAGE = _storage.get_storage_dir()
META = 'exams_metadata.json'

exclude = {'name', 'adm no', 'adm_no', 'admno', 'class', 'total', 'mean', 'rank'}


def load_metadata():
    data = _storage.read_json(META)
    if not data:
        print('No metadata found (local or S3) at', META)
        return {}
    return data


def build_combined_df_for_exams(exam_ids):
    dfs = []
    for eid in exam_ids:
        raw_key = f"{eid}/raw_data.pkl"
        data_key = f"{eid}/data.pkl"
        dfi = None
        try:
            dtmp = _storage.read_pickle(raw_key)
            if dtmp is not None:
                dfi = dtmp
            else:
                dtmp2 = _storage.read_pickle(data_key)
                if dtmp2 is not None:
                    dfi = dtmp2
        except Exception as e:
            print('Could not read', eid, e)
        if dfi is not None:
            try:
                dfi = dfi.copy()
                dfi['_exam_id'] = eid
            except Exception:
                pass
            dfs.append(dfi)
    if not dfs:
        return None
    return pd.concat(dfs, ignore_index=True)


# copy of the compact label logic used in the page

def compact_class_stream_label(raw_cls, raw_stream, class_map=None, label_style='Compact (MATH 5B)'):
    rc = (str(raw_cls) or '').strip()
    rs = (str(raw_stream) or '').strip()
    try:
        cmap = class_map or {}
        key = rc.upper()
        if key in cmap and cmap[key]:
            mapped = str(cmap[key]).strip()
            return mapped
    except Exception:
        pass
    digits = ''.join(ch for ch in rc if ch.isdigit())
    m = re.match(r'^\s*(\d+)\s*([A-Za-z]+)\s*$', rc)
    if m:
        base = m.group(1)
        stream_from_cls = m.group(2).upper()
    else:
        if digits:
            base = digits
        else:
            base = rc.replace('GRADE', '').replace('GRADE ', '').strip() or rc
        stream_from_cls = ''
    # collapse repeated-digit tokens like '55' -> '5'
    try:
        if isinstance(base, str) and base.isdigit() and len(base) >= 2 and all(ch == base[0] for ch in base):
            base = base[0]
    except Exception:
        pass
    stream_short = (rs or '').replace(' ', '') if rs else ''
    if not stream_short and stream_from_cls:
        stream_short = stream_from_cls
    try:
        if str(stream_short).strip().isdigit():
            stream_short = ''
    except Exception:
        pass
    if stream_short == base:
        stream_short = ''
    if label_style.startswith('Compact'):
        return f"{base}{stream_short}" if stream_short else base
    else:
        grade = f"Grade {base}" if digits else base
        if stream_short:
            return f"{grade} ({stream_short})"
        return grade


if __name__ == '__main__':
    meta = load_metadata()
    if not meta:
        print('No saved exams metadata. Nothing to test.')
        raise SystemExit(0)
    # meta is likely a dict exam_id -> info
    exam_ids = list(meta.keys())[:3]
    print('Testing exam ids:', exam_ids)
    combined = build_combined_df_for_exams(exam_ids)
    if combined is None:
        print('Could not load exam pickles for', exam_ids)
        raise SystemExit(0)
    # find subject cols
    subject_cols = [c for c in combined.columns if str(c).lower().strip() not in exclude and (pd.api.types.is_numeric_dtype(combined[c]) or pd.to_numeric(combined[c], errors='coerce').notna().any())]
    print('Detected subject columns:', subject_cols)

    # detect stream column using heuristics
    stream_col = None
    name_hints = ['stream', 'arm', 'stream_code', 'arm_code', 'class_stream']
    for c in combined.columns:
        if c == '_exam_id':
            continue
        lname = str(c).lower()
        if any(h in lname for h in name_hints):
            stream_col = c
            break
    if stream_col is None:
        for c in combined.columns:
            if c == '_exam_id':
                continue
            try:
                vals = combined[c].astype(str).dropna().str.strip()
            except Exception:
                continue
            if vals.empty:
                continue
            n = len(vals)
            single_letter = vals.str.match(r'^[A-Za-z]$').sum()
            digit_letter = vals.str.match(r'^\d+[A-Za-z]+$').sum()
            uniq = vals.drop_duplicates()
            if n > 0 and (single_letter / n) > 0.05 and len(uniq) <= 26:
                stream_col = c
                break
            if n > 0 and (digit_letter / n) > 0.05 and len(uniq) <= 200:
                stream_col = c
                break
            if len(uniq) <= 12 and all(re.match(r'^[A-Za-z0-9]{1,3}$', str(s)) for s in uniq):
                stream_col = c
                break
    print('Detected stream column:', stream_col)

    # build labels
    opt_map = {}
    class_map = {}  # not loading persisted map for smoke test
    meta_map = {v.get('exam_id'): v for v in meta.values()} if isinstance(meta, dict) else {v.get('exam_id'): v for v in meta}
    # build exam_grade_map
    exam_grade_map = {}
    for eid in exam_ids:
        em = meta.get(eid) or {}
        clsname = (em.get('class_name') or em.get('exam_name') or '')
        m = re.search(r'(\d+)', clsname)
        if m:
            grade_compact = m.group(1)
        else:
            grade_compact = clsname.upper().replace(' ', '_')
        exam_grade_map[eid] = grade_compact

    options = []
    if stream_col:
        pairs = combined.groupby(['_exam_id', stream_col])[subject_cols].apply(lambda df: df.notna().any()).reset_index()
        for idx, row in pairs.iterrows():
            eid = row['_exam_id']
            stream_val = row[stream_col]
            if pd.isna(stream_val) or str(stream_val).strip().upper() in ('NAN', ''):
                stream_val = ''
            grade_compact = exam_grade_map.get(eid, '')
            for subj in subject_cols:
                try:
                    if row.get(subj):
                        compact = compact_class_stream_label(grade_compact, stream_val, class_map)
                        subj_disp = re.sub(r'[^A-Za-z0-9 ]', ' ', str(subj)).upper()
                        subj_disp = re.sub(r'\s+', ' ', subj_disp).strip()
                        label = f"{subj_disp} {compact}".strip()
                        options.append(label)
                        opt_map[label] = {'subject': subj, 'class': grade_compact, 'stream': stream_val}
                except Exception:
                    pass
    else:
        pairs = combined.groupby(['_exam_id'])[subject_cols].apply(lambda df: df.notna().any()).reset_index()
        for idx, row in pairs.iterrows():
            eid = row['_exam_id']
            grade_compact = exam_grade_map.get(eid, '')
            for subj in subject_cols:
                try:
                    if row.get(subj):
                        compact = compact_class_stream_label(grade_compact, '', class_map)
                        subj_disp = re.sub(r'[^A-Za-z0-9 ]', ' ', str(subj)).upper()
                        subj_disp = re.sub(r'\s+', ' ', subj_disp).strip()
                        label = f"{subj_disp} {compact}".strip()
                        options.append(label)
                        opt_map[label] = {'subject': subj, 'class': grade_compact, 'stream': ''}
                except Exception:
                    pass

    options = sorted({o for o in options if 'NAN' not in str(o).upper()})
    print('\nGenerated labels (sample 100):')
    for lbl in options[:100]:
        print(lbl)

    # report any labels containing repeated digits
    bad = [o for o in options if re.search(r'(\d)\1+', o)]
    if bad:
        print('\nLabels with repeated digits detected:')
        for b in bad:
            print(b)
    else:
        print('\nNo labels with repeated digits found.')
