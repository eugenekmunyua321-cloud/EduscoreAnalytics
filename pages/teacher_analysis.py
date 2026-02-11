import streamlit as st
import os
import hashlib
import json
import re
import pandas as pd
from datetime import datetime
from utils.pdf_export import generate_analytics_pdf, generate_teacher_table_pdf, generate_teacher_table_bytes
from modules import storage

st.set_page_config(page_title="Teacher Analysis — Accurate Means", layout="wide")

# Block access when parents portal mode is active
try:
    if st.session_state.get('parents_portal_mode'):
        st.markdown("<div style='opacity:0.45;padding:18px;border-radius:8px;background:#f3f4f6;color:#111;'>\
            <strong>Restricted:</strong> This page is not available in Parents Portal mode.</div>", unsafe_allow_html=True)
        st.stop()
except Exception:
    pass


def _safe_rerun():
    """Safely request a rerun: use Streamlit's experimental_rerun if available,
    otherwise set a session flag and stop execution to allow the UI to refresh on next interaction."""
    try:
        if hasattr(st, 'experimental_rerun'):
            st.experimental_rerun()
            return
    except Exception:
        pass
    # fallback: experimental_rerun not available — do nothing and continue rendering
    # (avoid calling st.stop(), which stops the script and hides UI below the caller)
    try:
        st.session_state['_needs_rerun'] = True
    except Exception:
        pass
    return

# Paths (use storage adapter)
BASE = os.path.dirname(os.path.dirname(__file__))
def _storage_dir():
    try:
        return storage.get_storage_dir()
    except Exception:
        return os.path.join(BASE, 'saved_exams_storage')


def _exams_meta_path():
    return os.path.join(_storage_dir(), 'exams_metadata.json')


def _assignments_path():
    return os.path.join(_storage_dir(), 'ta_assignments.json')


def _teachers_path():
    return os.path.join(_storage_dir(), 'ta_teachers.json')


def _ui_state_path():
    return os.path.join(_storage_dir(), 'ta_ui_state.json')


def list_saved_exams():
    try:
        p = _exams_meta_path()
        data = storage.read_json(p) or {}
        if isinstance(data, dict):
            return [v for k, v in data.items()]
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def load_exam_dataframe(exam_id):
    try:
        p1 = os.path.join(str(exam_id), 'data.pkl')
        p2 = os.path.join(str(exam_id), 'raw_data.pkl')
        df = storage.read_pickle(p1)
        if df is not None:
            return df
        rdf = storage.read_pickle(p2)
        if rdf is not None:
            return rdf
    except Exception:
        return None
    return None


def load_assignments():
    try:
        p = _assignments_path()
        return storage.read_json(p) or {}
    except Exception:
        return {}
    return {}


def save_assignments(d):
    try:
        p = _assignments_path()
        return storage.write_json(p, d or {})
    except Exception:
        return False


def load_teachers():
    try:
        p = _teachers_path()
        data = storage.read_json(p)
        if data is not None:
            return data
    except Exception:
        return {'teachers': [], 'class_map': {}, 'inactive': []}
    # ensure modern shape with inactive list for compatibility
    result = {'teachers': [], 'class_map': {}, 'inactive': []}
    try:
        loaded = storage.read_json(_teachers_path())
        if isinstance(loaded, dict):
            result.update({k: loaded.get(k) for k in ['teachers', 'class_map', 'inactive'] if k in loaded})
            # normalize missing keys
            result['teachers'] = result.get('teachers') or []
            result['class_map'] = result.get('class_map') or {}
            result['inactive'] = result.get('inactive') or []
            return result
    except Exception:
        pass
    return result


def save_teachers(d):
    try:
        payload = {'teachers': [], 'class_map': {}, 'inactive': []}
        if isinstance(d, dict):
            payload['teachers'] = d.get('teachers') or []
            payload['class_map'] = d.get('class_map') or {}
            payload['inactive'] = d.get('inactive') or []
        return storage.write_json(_teachers_path(), payload)
    except Exception:
        return False


def load_ui_state():
    try:
        return storage.read_json(_ui_state_path()) or {}
    except Exception:
        return {}
    return {}


def save_ui_state(state_dict=None):
    try:
        # collect defaults from session_state if not provided
        s = state_dict or {}
        keys = ['ta_select_exams_accurate', 'show_teacher_manager', 'ta_manage_mode', 'enable_classify', 'upper_multiselect', 'lower_multiselect', 'ta_paste_teachers', 'ta_selected_teacher']
        for k in keys:
            if k not in s and k in st.session_state:
                s[k] = st.session_state.get(k)
        return storage.write_json(_ui_state_path(), s)
    except Exception:
        return False


def detect_stream_column(df):
    hints = ['stream', 'arm', 'stream_code', 'arm_code', 'class_stream', 'stream_name', 'section', 'class']
    for c in df.columns:
        lc = str(c).lower()
        if any(h in lc for h in hints):
            # verify this column looks like a stream: multiple distinct short tokens, not numeric-dominant
            try:
                vals = df[c].astype(str).dropna().str.strip()
                uniq = vals.drop_duplicates()
                if len(uniq) <= 1:
                    continue
                # prefer columns with short token values
                if uniq.str.len().median() <= 6 and len(uniq) <= max(100, len(df) // 2):
                    # avoid numeric-dominant columns
                    ser_num = pd.to_numeric(df[c], errors='coerce')
                    if ser_num.notna().sum() / max(1, len(df)) > 0.5:
                        continue
                    # prefer columns where many values look like grade-streams (e.g. '9g','8b','2y')
                    pattern = vals.str.match(r'^\s*\d+\s*[A-Za-z]+\s*$')
                    letter_only = vals.str.match(r'^\s*[A-Za-z]+\s*$')
                    if (pattern.sum() + letter_only.sum()) / max(1, len(vals)) > 0.05:
                        return c
                    # fallback: accept this hint column
                    return c
            except Exception:
                return c
    for c in df.columns:
        try:
            vals = df[c].astype(str).dropna().str.strip()
        except Exception:
            continue
        if vals.empty:
            continue
        # skip columns that are mostly numeric (likely marks) to avoid mistaking marks for streams
        try:
            ser_num = pd.to_numeric(df[c], errors='coerce')
            n = len(df)
            num_ratio = ser_num.notna().sum() / max(1, n)
            unique_ratio = ser_num.dropna().nunique() / max(1, ser_num.notna().sum()) if ser_num.notna().sum() > 0 else 0
            # if more than 50% numeric or too many distinct numeric values, skip
            if num_ratio > 0.5 or unique_ratio > 0.5:
                continue
        except Exception:
            pass
        n = len(vals)
        single_letter = (vals.str.match(r'^[A-Za-z]$').sum())
        digit_letter = (vals.str.match(r'^\d+[A-Za-z]+$').sum())
        pattern = vals.str.match(r'^\s*\d+\s*[A-Za-z]+\s*$')
        uniq = vals.drop_duplicates()
        if n > 0 and (single_letter / n) > 0.05 and len(uniq) <= 26:
            return c
        if n > 0 and (digit_letter / n) > 0.05 and len(uniq) <= 200:
            return c
        # prefer digit+letter streams
        if n > 0 and (pattern.sum() / n) > 0.05 and len(uniq) <= 200:
            return c
    return None


def candidate_subject_columns(df, stream_col=None):
    exclude = {'name', 'adm', 'adm no', 'admno', 'class', 'total', 'mean', 'rank'}
    cols = []
    for c in df.columns:
        if c == stream_col or c == '_exam_id':
            continue
        lc = str(c).lower()
        if any(x in lc for x in exclude):
            continue
        try:
            ser = pd.to_numeric(df[c], errors='coerce')
            if ser.notna().any():
                cols.append(c)
                continue
        except Exception:
            pass
        try:
            non_null = df[c].astype(str).str.strip().replace('nan', '').replace('', pd.NA).dropna()
            if non_null.empty:
                continue
            median_len = int(non_null.str.len().median())
            if median_len <= 4 and len(non_null.drop_duplicates()) <= max(50, min(200, len(df) // 2)):
                cols.append(c)
        except Exception:
            continue
    return cols


def load_exam_out_of(eid):
    """Load config.json for exam and return a mapping of normalized subject -> out_of value."""
    cfg_path = os.path.join(STORAGE_DIR, str(eid), 'config.json')
    out_map = {}
    try:
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            for k, v in cfg.items():
                if isinstance(k, str) and k.lower().startswith('out_'):
                    sub = k[4:]
                    # normalize key
                    nk = re.sub(r'[^A-Za-z0-9]', '', sub).upper().strip()
                    try:
                        out_map[nk] = float(v)
                    except Exception:
                        pass
    except Exception:
        pass
    return out_map


def _normalize_col_name(c):
    return re.sub(r'[^A-Za-z0-9]', '', str(c)).upper().strip()


def _format_avg_cols_for_display(df):
    """Return a copy of df where any column whose name contains 'avg' is
    formatted to two decimal places as strings for consistent display in Streamlit."""
    try:
        if df is None:
            return df
        d2 = df.copy()
        for col in list(d2.columns):
            if 'avg' in str(col).lower():
                try:
                    d2[col] = d2[col].apply(lambda x: f"{float(x):.2f}" if pd.notna(x) else '')
                except Exception:
                    # best-effort: coerce numeric then format
                    try:
                        d2[col] = pd.to_numeric(d2[col], errors='coerce').apply(lambda x: f"{float(x):.2f}" if pd.notna(x) else '')
                    except Exception:
                        pass
        return d2
    except Exception:
        return df


st.markdown("""
<div style="background: linear-gradient(90deg,#0f172a,#1e293b); padding:18px; border-radius:8px; color: white;">
    <h1 style="margin:0; font-family: 'Segoe UI', Roboto, sans-serif; font-size:32px; line-height:1.1;">Teacher Analysis</h1>
    <p style="margin:6px 0 0 0; opacity:0.95; font-size:14px;">Per-subject stream means, teacher assignment management and printable exports — accurate, compact and export-ready.</p>
</div>
""", unsafe_allow_html=True)

# ---- Load metadata and provide filters: exam kind, term, year ----
exams_meta = list_saved_exams()
if not exams_meta:
    st.info('No saved exams metadata found in storage')
    st.stop()

# derive exam kinds from exam_name (first segment before ' - ')
def _exam_kind(meta):
    name = (meta.get('exam_name') or '')
    parts = [p.strip() for p in name.split(' - ') if p.strip()]
    return parts[0] if parts else 'UNKNOWN'

all_kinds = sorted({_exam_kind(m) for m in exams_meta})
all_terms = sorted({m.get('term') for m in exams_meta if m.get('term')})
all_years = sorted({m.get('year') for m in exams_meta if m.get('year')}, reverse=True)

# order: Year, Term, Exam Kind
def normalize_term_label(t):
    if not t:
        return ''
    s = str(t).strip().lower()
    # common patterns -> Term 1/2/3
    if re.search(r'1|one|first', s):
        return 'Term 1'
    if re.search(r'2|two|second', s):
        return 'Term 2'
    if re.search(r'3|three|third', s):
        return 'Term 3'
    return t

# filter selectors: Year (All), Term (multi), Exam kinds (multi)
all_norm_terms = sorted({normalize_term_label(m.get('term')) for m in exams_meta if m.get('term')})
cols = st.columns([1, 2, 3, 1])
with cols[0]:
    sel_year = st.selectbox('Year', options=['All'] + all_years, index=0)
with cols[1]:
    sel_terms = st.multiselect('Term(s)', options=['All'] + all_norm_terms, default=['All'])
with cols[2]:
    sel_kinds = st.multiselect('Exam kinds', options=all_kinds, default=all_kinds)
with cols[3]:
    st.write(' ')

def _matches_filter(meta):
    kind = _exam_kind(meta)
    year = meta.get('year')
    term = normalize_term_label(meta.get('term'))
    if sel_kinds and len(sel_kinds) > 0 and kind not in sel_kinds:
        return False
    if sel_year != 'All' and year != sel_year:
        return False
    if sel_terms and 'All' not in sel_terms and term not in sel_terms:
        return False
    return True

filtered_meta = [m for m in exams_meta if _matches_filter(m)]

if not filtered_meta:
    st.info('No exams match the selected filters')
    st.stop()

opts = []
meta_map = {}
for e in filtered_meta:
    eid = e.get('exam_id') or e.get('id')
    label = e.get('exam_name') or e.get('class_name') or eid
    if label:
        opts.append(label)
        meta_map[label] = e

# Restore persisted exam selection (store ids in ui_state as 'ta_select_exam_ids')
try:
    persisted_ids = ui_state.get('ta_select_exam_ids') or []
    if persisted_ids:
        # build id -> label map for available options
        id_to_label = {}
        for lbl, m in meta_map.items():
            mid = m.get('exam_id') or m.get('id')
            if mid is not None:
                id_to_label[str(mid)] = lbl
        restored = [id_to_label.get(str(x)) for x in persisted_ids if id_to_label.get(str(x))]
        if restored:
            st.session_state['ta_select_exams_accurate'] = restored
except Exception:
    pass

# ---- Teacher registry (persistent) ----
teachers_store = load_teachers() or {'teachers': [], 'class_map': {}}
# normalize older formats: if file contains a plain list, accept it
if isinstance(teachers_store, list):
    teachers_store = {'teachers': teachers_store, 'class_map': {}}
elif not isinstance(teachers_store, dict):
    teachers_store = {'teachers': [], 'class_map': {}}
teachers = teachers_store.get('teachers', [])
class_map = teachers_store.get('class_map', {})
inactive = teachers_store.get('inactive', []) or []

# Load persisted UI state (if any) and seed session_state so widget defaults persist across
# navigation. We only persist UI controls here (selected exams, sidebar selections);
# assignments and teacher registry remain persisted separately on disk.
try:
    ui_state = load_ui_state() or {}
except Exception:
    ui_state = {}

# seed some session keys with persisted values if they aren't already set
for k, default in {
    'show_teacher_manager': False,
    'ta_manage_mode': 'Single',
    'enable_classify': False,
    'ta_paste_teachers': '',
    'ta_selected_teacher': '',
    'upper_multiselect': [],
    'lower_multiselect': []
}.items():
    if k not in st.session_state:
        if k in ui_state:
            st.session_state[k] = ui_state.get(k)
        else:
            st.session_state[k] = default

# If a previous run set pending selections (from move actions), apply them before widgets are instantiated
try:
    if 'upper_multiselect_pending' in st.session_state:
        st.session_state['upper_multiselect'] = st.session_state.pop('upper_multiselect_pending') or []
    if 'lower_multiselect_pending' in st.session_state:
        st.session_state['lower_multiselect'] = st.session_state.pop('lower_multiselect_pending') or []
except Exception:
    pass

# Normalize teacher entries: older formats may have stored teacher objects as dicts.
# Ensure `teachers`, `inactive`, and `class_map` keys are all string-based names.
try:
    norm_teachers = []
    for t in teachers:
        if isinstance(t, dict):
            # common fields that may contain the name
            name = t.get('name') or t.get('teacher') or t.get('full_name') or None
            if not name:
                # fallback: stringify a reasonable identifier
                try:
                    name = str(t.get('id') or t.get('teacher_id') or json.dumps(t, ensure_ascii=False))
                except Exception:
                    name = str(t)
            name = str(name).strip()
            if name:
                norm_teachers.append(name)
        elif t is None:
            continue
        else:
            norm_teachers.append(str(t).strip())
    teachers = [t for t in norm_teachers if t]
except Exception:
    # fallback: coerce all to strings
    teachers = [str(t) for t in teachers if t is not None]

try:
    inactive = [str(x).strip() for x in (inactive or []) if x is not None]
except Exception:
    inactive = []

st.markdown('---')
st.markdown('---')
# Manage teachers via sidebar overlay to avoid pushing content down
if 'show_teacher_manager' not in st.session_state:
    st.session_state['show_teacher_manager'] = False
if st.button('Manage teachers'):
    st.session_state['show_teacher_manager'] = True
    try:
        save_ui_state()
    except Exception:
        pass

    # Show total registered teachers including any deactivated entries.
    try:
        # Count only active teachers as 'Registered' (deactivated teachers are excluded)
        active_teachers = [t for t in teachers if t not in inactive]
        active_count = len(active_teachers)
        inactive_count = len([t for t in teachers if t in inactive])
        st.write(f"Registered teachers: {active_count} (Active: {active_count}, Inactive: {inactive_count})")
    except Exception:
        st.write(f"Registered teachers: {len(teachers)}")
if st.session_state.get('show_teacher_manager'):
    with st.sidebar.expander('Manage teachers (paste, add)', expanded=True):
        st.write('Paste newline-separated teacher names (or comma).')
        paste = st.text_area('Paste names here', key='ta_paste_teachers')
        if st.button('Add pasted teachers', key='add_pasted_teachers'):
            raw = paste.replace(',', '\n')
            added = 0
            for line in [x.strip() for x in raw.splitlines() if x.strip()]:
                if line not in teachers:
                    teachers.append(line)
                    class_map[line] = class_map.get(line, 'Lower')
                    added += 1
            if added:
                save_teachers({'teachers': teachers, 'class_map': class_map})
                try:
                    save_ui_state()
                except Exception:
                    pass
                st.success(f'Added {added} teachers')
            else:
                st.info('No new teachers added')
        st.markdown('---')
        # Optional classification — simplified UI: choose Upper / Lower teacher lists
        enable_classify = st.checkbox('Enable classification (Upper / Lower)', value=False, key='enable_classify', on_change=save_ui_state)
        if enable_classify:
            st.write('Classify teachers into Upper and Lower groups. Use the lists below to move teachers between groups.')
            colA, colB = st.columns(2)
            # defaults: prefer persisted UI selections, fall back to class_map
            # build defaults from persisted ui_state or class_map, ensure values exist in current teachers
            persisted_upper = [t for t in (st.session_state.get('upper_multiselect') or []) if t in teachers]
            persisted_lower = [t for t in (st.session_state.get('lower_multiselect') or []) if t in teachers]
            classmap_upper = [t for t in teachers if class_map.get(t) == 'Upper']
            classmap_lower = [t for t in teachers if class_map.get(t) == 'Lower']
            upper_default = persisted_upper or classmap_upper
            lower_default = persisted_lower or classmap_lower
            # enforce exclusivity: remove any overlap from lower_default
            lower_default = [t for t in lower_default if t not in set(upper_default)]
            # options for each list exclude the teachers already selected in the other list
            upper_options = [t for t in teachers if t not in set(lower_default)]
            lower_options = [t for t in teachers if t not in set(upper_default)]
            with colA:
                st.markdown('**Upper teachers**')
                upper_sel = st.multiselect('Select Upper teachers (searchable)', options=upper_options, default=upper_default, key='upper_multiselect', on_change=save_ui_state)
                # show selected teachers in a scrollable box for visibility
                sel_upper = st.session_state.get('upper_multiselect') or []
                st.markdown(f"<div style='max-height:160px;overflow:auto;border:1px solid #eee;padding:8px;background:#fafafa;'>" + ('<br>'.join(sel_upper) if sel_upper else '<span style="color:#777">No teachers selected</span>') + "</div>", unsafe_allow_html=True)
            with colB:
                st.markdown('**Lower teachers**')
                lower_sel = st.multiselect('Select Lower teachers (searchable)', options=lower_options, default=lower_default, key='lower_multiselect', on_change=save_ui_state)
                sel_lower = st.session_state.get('lower_multiselect') or []
                st.markdown(f"<div style='max-height:160px;overflow:auto;border:1px solid #eee;padding:8px;background:#fafafa;'>" + ('<br>'.join(sel_lower) if sel_lower else '<span style="color:#777">No teachers selected</span>') + "</div>", unsafe_allow_html=True)

            # Note: move buttons removed — use the multiselects to assign teachers to groups.
            st.info('Use the Upper and Lower multiselect boxes to manage classification. Selecting items in one box will exclude them from the other.')

            if st.button('Save classifications', key='classify_save_teachers'):
                try:
                    # persist class_map from current selections
                    upper_sel = [t for t in (st.session_state.get('upper_multiselect') or []) if t in teachers]
                    lower_sel = [t for t in (st.session_state.get('lower_multiselect') or []) if t in teachers]
                    # enforce exclusivity: remove overlaps (upper precedence)
                    lower_sel = [t for t in lower_sel if t not in set(upper_sel)]
                    for t in teachers:
                        if t in upper_sel:
                            class_map[t] = 'Upper'
                        elif t in lower_sel:
                            class_map[t] = 'Lower'
                        else:
                            class_map[t] = class_map.get(t, 'Lower')
                    save_teachers({'teachers': teachers, 'class_map': class_map, 'inactive': inactive})
                    save_ui_state()
                    st.success('Saved classifications')
                except Exception as _e:
                    st.error(f'Failed to save classifications: {_e}')
            if st.button('Clear classifications (set all to Lower)', key='classify_clear'):
                for t in teachers:
                    class_map[t] = 'Lower'
                save_teachers({'teachers': teachers, 'class_map': class_map, 'inactive': inactive})
                save_ui_state()
                st.success('All teachers set to Lower')
        st.markdown('---')
        st.write('Registered teachers')
        # compact manager: choose Single or Bulk mode to reduce visual noise
        mode = st.radio('Mode', options=['Single', 'Bulk'], index=0, key='ta_manage_mode', on_change=save_ui_state)
        if mode == 'Single':
            sel = st.selectbox('Teacher', options=teachers or [''], key='ta_selected_teacher', on_change=save_ui_state)
            if sel:
                status = 'Inactive' if sel in inactive else 'Active'
                badge = ("🟥 Inactive" if sel in inactive else "🟩 Active")
                st.markdown(f"**Status:** {badge}")
                colA, colB = st.columns(2)
                with colA:
                    if st.button('Unassign selected', key='unassign_selected'):
                        try:
                            assigns = load_assignments() or {}
                            changed = False
                            for aeid, streams in assigns.items():
                                if not isinstance(streams, dict):
                                    continue
                                for sk, subj_map in list(streams.items()):
                                    if not isinstance(subj_map, dict):
                                        continue
                                    for subj in list(subj_map.keys()):
                                        try:
                                            if subj_map.get(subj) == sel:
                                                subj_map[subj] = ''
                                                changed = True
                                        except Exception:
                                            continue
                                    try:
                                        if subj_map.get('_single_teacher') == sel:
                                            subj_map['_single_teacher'] = ''
                                            changed = True
                                    except Exception:
                                        pass
                            if changed:
                                save_assignments(assigns)
                                st.success(f'Unassigned {sel} from current assignments')
                            else:
                                st.info(f'No current assignments found for {sel}')
                        except Exception as e:
                            st.error(f'Failed to unassign {sel}: {e}')
                        _safe_rerun()
                with colB:
                    if sel in inactive:
                        if st.button('Reactivate', key='reactivate_selected'):
                            try:
                                if sel in inactive:
                                    inactive.remove(sel)
                                save_teachers({'teachers': teachers, 'class_map': class_map, 'inactive': inactive})
                                st.success(f'{sel} reactivated')
                            except Exception as e:
                                st.error(f'Failed to reactivate: {e}')
                            _safe_rerun()
                    else:
                        if st.button('Deactivate', key='deactivate_selected'):
                            try:
                                if sel not in inactive:
                                    inactive.append(sel)
                                save_teachers({'teachers': teachers, 'class_map': class_map, 'inactive': inactive})
                                st.success(f'{sel} deactivated')
                            except Exception as e:
                                st.error(f'Failed to deactivate: {e}')
                            _safe_rerun()
        else:
            mult = st.multiselect('Teachers (bulk)', options=teachers, default=[], key='ta_selected_teachers_bulk')
            if mult:
                colA, colB = st.columns(2)
                with colA:
                    if st.button('Unassign selected (bulk)', key='unassign_bulk'):
                        try:
                            assigns = load_assignments() or {}
                            changed = False
                            for t in mult:
                                for aeid, streams in assigns.items():
                                    if not isinstance(streams, dict):
                                        continue
                                    for sk, subj_map in list(streams.items()):
                                        if not isinstance(subj_map, dict):
                                            continue
                                        for subj in list(subj_map.keys()):
                                            try:
                                                if subj_map.get(subj) == t:
                                                    subj_map[subj] = ''
                                                    changed = True
                                            except Exception:
                                                continue
                                        try:
                                            if subj_map.get('_single_teacher') == t:
                                                subj_map['_single_teacher'] = ''
                                                changed = True
                                        except Exception:
                                            pass
                            if changed:
                                save_assignments(assigns)
                                st.success(f'Unassigned {len(mult)} teachers from current assignments')
                            else:
                                st.info('No current assignments found for selected teachers')
                        except Exception as e:
                            st.error(f'Failed bulk unassign: {e}')
                        _safe_rerun()
                with colB:
                    if st.button('Deactivate selected', key='deactivate_bulk'):
                        try:
                            added = 0
                            for t in mult:
                                if t not in inactive:
                                    inactive.append(t)
                                    added += 1
                            save_teachers({'teachers': teachers, 'class_map': class_map, 'inactive': inactive})
                            st.success(f'Deactivated {added} teachers')
                        except Exception as e:
                            st.error(f'Failed bulk deactivate: {e}')
                        _safe_rerun()
                    if st.button('Reactivate selected', key='reactivate_bulk'):
                        try:
                            reactivated = 0
                            for t in mult:
                                if t in inactive:
                                    inactive.remove(t)
                                    reactivated += 1
                            save_teachers({'teachers': teachers, 'class_map': class_map, 'inactive': inactive})
                            st.success(f'Reactivated {reactivated} teachers')
                        except Exception as e:
                            st.error(f'Failed bulk reactivate: {e}')
                        _safe_rerun()
        if st.button('Close', key='classify_close'):
            st.session_state['show_teacher_manager'] = False
            try:
                save_ui_state()
            except Exception:
                pass

st.markdown('---')

selected = st.multiselect('Select exams', options=opts, key='ta_select_exams_accurate', on_change=save_ui_state)
selected_ids = [meta_map[s].get('exam_id') for s in selected if s in meta_map]
try:
    # persist selected exam ids so they survive full page refreshes
    save_ui_state({'ta_select_exam_ids': selected_ids})
except Exception:
    pass
if not selected_ids:
    st.info('Select one or more exams to load generated marksheets.')
    st.stop()

exam_dfs = {}
for eid in selected_ids:
    df = load_exam_dataframe(eid)
    if df is not None:
        dfi = df.copy()
        dfi['_exam_id'] = eid
        exam_dfs[eid] = dfi

if not exam_dfs:
    st.error('No data files (data.pkl/raw_data.pkl) found for selected exams')
    st.stop()

assignments = load_assignments() or {}
# Prune numeric-only stream keys from assignments (in-memory) for all exams to avoid showing them.
# This avoids showing '9.00' or '495' as streams coming from saved assignments.
try:
    for eid in list(assignments.keys()):
        streams_map = assignments.get(eid, {})
        if isinstance(streams_map, dict):
            for sk in list(streams_map.keys()):
                if not re.search(r'[A-Za-z]', str(sk)):
                    assignments.setdefault(eid, {}).pop(sk, None)
except Exception:
    pass

results = {}
for eid, dfi in exam_dfs.items():
    df = dfi
    stream_col = detect_stream_column(df)
    subj_cols = candidate_subject_columns(df, stream_col=stream_col)
    # keep a copy of all detected subject-like columns so we can show combined components
    all_subj_cols = list(subj_cols)
    # Detect combined/total columns by numeric relationship: if a 'combined' column equals
    # the sum of two/three other subject columns (within tolerance) treat it as combined and
    # hide the component columns from the assignment sheet.
    try:
        import itertools
        numeric_cols = []
        for c in subj_cols:
            try:
                ser = pd.to_numeric(df[c], errors='coerce')
                if ser.notna().any():
                    numeric_cols.append(c)
            except Exception:
                continue

        # normalize map for reliable comparisons (handle stray spaces/symbols)
        norm_map = { re.sub(r'[^A-Za-z0-9]', '', str(c)).upper().strip(): c for c in subj_cols }
        combined_candidates = [c for c in subj_cols if re.search(r'(?i)(tot|combined|total|combined%)', c)]
        components_to_remove = set()
        combine_map = {}
        for cc in combined_candidates:
            try:
                cc_series = pd.to_numeric(df[cc], errors='coerce').fillna(0)
                if cc_series.abs().sum() == 0:
                    continue
                found = False
                others = [c for c in numeric_cols if c != cc]
                # try pairs and triplets (reasonable subject counts)
                for r in (2, 3):
                    for combo in itertools.combinations(others, r):
                        ssum = sum(pd.to_numeric(df[x], errors='coerce').fillna(0) for x in combo)
                        mad = (cc_series - ssum).abs().mean()
                        denom = cc_series.abs().mean() if cc_series.abs().mean() != 0 else 1.0
                        rel = mad / denom
                        # if mean absolute diff is small in absolute or relative terms, accept
                        if mad < 1e-6 or rel < 0.02:
                            components_to_remove.update(combo)
                            # record the mapping for UI review
                            combine_map.setdefault(cc, []).append(tuple(combo))
                            found = True
                            break
                    if found:
                        break
            except Exception:
                continue

        # normalize removed components so we reliably exclude them even when names have
        # stray spaces or punctuation differences (e.g. 'ENG ' vs 'ENG')
        removed_norms = { re.sub(r'[^A-Za-z0-9]', '', str(c)).upper().strip() for c in components_to_remove }
        if removed_norms:
            subj_cols = [c for c in subj_cols if re.sub(r'[^A-Za-z0-9]', '', str(c)).upper().strip() not in removed_norms]
        removed_list = list(components_to_remove)
        # assignable subjects are those remaining after removing combined components
        assignable_subj_cols = list(subj_cols)
        # keep full list for display
        subj_cols = list(all_subj_cols)
        # include combine_map in locals so we can store it in results
        try:
            _combine_map = combine_map
        except NameError:
            _combine_map = {}
    except Exception:
        pass
    res_by_stream = {}
    out_map = load_exam_out_of(eid)
    if stream_col:
        # Collect unique stream values and filter out pure-numeric values (e.g. 9.00, 495)
        raw_vals = df[stream_col].dropna().unique()
        raw_streams = []
        for s in raw_vals:
            ss = str(s).strip()
            # skip values that contain no letters at all (pure numeric or symbols)
            if not re.search(r'[A-Za-z]', ss):
                continue
            raw_streams.append(s)
        # if after filtering there are fewer than 2 distinct letter-containing stream values,
        # treat as no stream column (prevents numeric-like class values from becoming streams)
        if len(raw_streams) < 2:
            stream_col = None
            raw_streams = []
        def _stream_sort_key(x):
            try:
                # treat pure numeric-like values as numbers for sorting
                xs = str(x).strip()
                if re.match(r'^-?\d+(?:\.\d+)?$', xs):
                    return (0, float(xs))
            except Exception:
                pass
            # fallback: sort by lowercase string
            return (1, str(x).lower())

        streams = sorted(raw_streams, key=_stream_sort_key)
        for s in streams:
            mask = df[stream_col].astype(str).str.strip() == str(s).strip()
            n_students = int(mask.sum())
            subj_stats = {}
            for c in subj_cols:
                try:
                    # load raw marks for this subject for all students in stream (NaN for missing)
                    sraw = pd.to_numeric(df.loc[mask, c], errors='coerce')
                    cnt = int(sraw.notna().sum())
                    # determine out_of for this subject from config
                    # per user request: treat all subjects as out of 100
                    out_of = 100.0
                    # convert to percentages; missing -> 0
                    percent = (sraw.fillna(0.0) / float(out_of)) * 100.0
                    sum_percent = float(percent.sum()) if not percent.empty else 0.0
                    denom = n_students if n_students > 0 else cnt
                    mean_percent = (sum_percent / denom) if denom > 0 else None
                    subj_stats[c] = {'sum_percent': round(sum_percent,2), 'count_present': cnt, 'students_in_stream': n_students, 'mean_percent': round(mean_percent,2) if mean_percent is not None else None, 'out_of': out_of}
                except Exception:
                    subj_stats[c] = {'sum_percent': 0.0, 'count_present': 0, 'students_in_stream': n_students, 'mean_percent': None, 'out_of': None}
            res_by_stream[str(s)] = subj_stats
    else:
        mask = pd.Series(True, index=df.index)
        n_students = int(len(df))
        subj_stats = {}
        out_map = load_exam_out_of(eid)
        for c in subj_cols:
            try:
                sraw = pd.to_numeric(df.loc[mask, c], errors='coerce')
                cnt = int(sraw.notna().sum())
                # per user request: treat all subjects as out of 100
                out_of = 100.0
                percent = (sraw.fillna(0.0) / float(out_of)) * 100.0
                sum_percent = float(percent.sum()) if not percent.empty else 0.0
                denom = n_students if n_students > 0 else cnt
                mean_percent = (sum_percent / denom) if denom > 0 else None
                subj_stats[c] = {'sum_percent': round(sum_percent,2), 'count_present': cnt, 'students_in_stream': n_students, 'mean_percent': round(mean_percent,2) if mean_percent is not None else None, 'out_of': out_of}
            except Exception:
                subj_stats[c] = {'sum_percent': 0.0, 'count_present': 0, 'students_in_stream': n_students, 'mean_percent': None, 'out_of': None}
        res_by_stream[''] = subj_stats
    results[eid] = {'stream_col': stream_col, 'subjects': subj_cols, 'assignable_subjects': assignable_subj_cols if 'assignable_subj_cols' in locals() else list(subj_cols), 'by_stream': res_by_stream, 'removed_components': removed_list if 'removed_list' in locals() else [], 'combine_map': _combine_map if '_combine_map' in locals() else {}}

for exam_idx, eid in enumerate(selected_ids):
    emeta = next((x for x in exams_meta if x.get('exam_id') == eid), {}) or {}
    header = emeta.get('exam_name') or emeta.get('class_name') or str(eid)
    st.header(f"Exam: {header}")
    r = results.get(eid) or {}
    subj_cols = r.get('subjects') or []
    assignable_subj_cols = r.get('assignable_subjects', []) or []
    removed_components = r.get('removed_components', []) or []
    combine_map = r.get('combine_map', {}) or {}
    # require user confirmation of detected combined mappings before assignments are allowed.
    # When combined mappings are detected and not yet confirmed, protect the components by
    # preventing any assignments until the user confirms.
    # consider session state (immediate UI) and persisted assignments
    # We no longer block assignments for detected combined totals.
    # Always allow assigning subjects; removed components are not auto-hidden. The user asked
    # to remove the combine/confirm/manual protection UI permanently.
    effective_assignable_subj_cols = list(assignable_subj_cols)
    # per user request, do not show hidden combined components UI
    by_stream = r.get('by_stream') or {}
    if not subj_cols:
        st.write('No subject-like columns detected for this exam')
        continue
    # (Removed subject sheet display as requested.)
    # Subjects are still available in the assignment UI; combined components are protected
    # after the user confirms detected combine mappings.
    teacher_options = [''] + list(teachers)
    streams_list = list(by_stream.keys())
    for s in streams_list:
        stats = by_stream.get(s, {})
        is_valid_stream = bool(s and re.search(r'[A-Za-z]', str(s)))
        stream_label = s if s else 'All students (no stream detected)'
        if not is_valid_stream and s:
            st.subheader(f"Stream: {stream_label}  ⚠️ (numeric-only — assignments disabled)")
        else:
            st.subheader(f"Stream: {stream_label}")

        # show per-stream subject columns and stats
        rows = []
        for subj in subj_cols:
            info = stats.get(subj, {})
            teacher = assignments.get(str(eid), {}).get(str(s), {}).get(subj, '')
            # Exclude CountPresent per user request (remove this column from all table sheets)
            rows.append({'Subject': subj, 'OutOf': info.get('out_of'), 'Sum(%)': info.get('sum_percent'), 'StudentsInStream': info.get('students_in_stream'), 'Mean(%)': info.get('mean_percent'), 'AssignedTeacher': teacher})
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

        # Provide a download-to-PDF button for this stream's assignment sheet.
        try:
            outdir_stream = os.path.join(STORAGE_DIR, 'exports')
            os.makedirs(outdir_stream, exist_ok=True)
            # Prepare a display dataframe matching the shown columns
            try:
                # build display dataframe without CountPresent
                display_df = pd.DataFrame(rows)[['Subject', 'OutOf', 'Sum(%)', 'StudentsInStream', 'Mean(%)', 'AssignedTeacher']]
            except Exception:
                display_df = pd.DataFrame(rows)
            # Format numeric columns for PDF: Means -> 2 decimals; other numeric columns -> 0 decimals
            try:
                pdf_df = display_df.copy()
                for col in pdf_df.columns:
                    if pdf_df[col].dtype.kind in 'biufc':
                        if 'Mean' in col:
                            pdf_df[col] = pdf_df[col].apply(lambda x: format(x, '.2f') if pd.notna(x) else '')
                        else:
                            pdf_df[col] = pdf_df[col].apply(lambda x: format(x, '.0f') if pd.notna(x) else '')
            except Exception:
                pdf_df = display_df.copy()
            kind = _exam_kind(emeta)
            term_disp = normalize_term_label(emeta.get('term')) or ''
            year_disp = emeta.get('year') or ''
            title_text = f'Assignments — {kind}; Stream: {stream_label}; Term: {term_disp}; Year: {year_disp}'
            slug_stream = re.sub(r'[^A-Za-z0-9_-]', '_', str(stream_label))[:80]
            kind_slug = re.sub(r'[^A-Za-z0-9_-]', '_', str(kind))[:80]
            ts_local = datetime.now().strftime('%Y%m%d_%H%M%S')
            outname = f'Assignments_{eid}_{kind_slug}_{slug_stream}_{ts_local}.pdf'
            outpath = os.path.join(outdir_stream, outname)
            pdf_bytes = generate_teacher_table_bytes(pdf_df, title=title_text)
            # Save a copy for records
            try:
                with open(outpath, 'wb') as _outf:
                    _outf.write(pdf_bytes)
            except Exception:
                pass
            st.success(f'Prepared PDF: {outname} ({len(pdf_bytes)} bytes)')
            st.download_button(f'Download assignment sheet PDF — {stream_label}', pdf_bytes, file_name=outname, mime='application/pdf', key=f'dl_assign__{eid}__{slug_stream}__{ts_local}')
        except Exception as _e:
            st.error(f'Failed to prepare PDF for this stream: {_e}')

        if not is_valid_stream and s:
            st.warning('This stream appears numeric-only; assignments are disabled.')
            continue

        # Assignments are always allowed (confirmed/combined protection UI removed per user request)

        single_key = f"single__{eid}__{s}"
        current_single = assignments.get(str(eid), {}).get(str(s), {}).get('_single_teacher', '')
        use_single = st.checkbox('Use one teacher for all subjects', value=bool(current_single), key=single_key)
        if use_single:
            sel_single = st.selectbox('Select teacher for all subjects', options=teacher_options, index=teacher_options.index(current_single) if current_single in teacher_options else 0, key=f'select_single__{eid}__{s}')
            assignments.setdefault(str(eid), {}).setdefault(str(s), {})['_single_teacher'] = sel_single
            for subj in effective_assignable_subj_cols:
                assignments.setdefault(str(eid), {}).setdefault(str(s), {})[subj] = sel_single
            # persist assignment immediately so selections are permanent until manually changed
            try:
                save_assignments(assignments)
            except Exception:
                pass
        else:
            if '_single_teacher' in assignments.get(str(eid), {}).get(str(s), {}):
                assignments.setdefault(str(eid), {}).setdefault(str(s), {}).pop('_single_teacher', None)
            cols_hdr = st.columns([3, 2])
            with cols_hdr[0]:
                st.write('Subject')
            with cols_hdr[1]:
                st.write('Teacher')
            # Compact assignment UI: render subjects in two columns to save vertical space
            compact = True
            assign_list = effective_assignable_subj_cols if effective_assignable_subj_cols else []
            if not assign_list:
                # still render the full subject list but mark them as protected
                for subj in subj_cols:
                    st.write(f"{subj} — *protected / not assignable*")
            else:
                left = assign_list[::2]
                right = assign_list[1::2]
                col_left, col_right = st.columns(2)
                with col_left:
                    for j, subj in enumerate(left):
                        key = f"assign__{eid}__{s}__L__{j}"
                        r0, r1 = st.columns([3, 2])
                        with r0:
                            st.write(subj)
                        with r1:
                            current = assignments.get(str(eid), {}).get(str(s), {}).get(subj, '')
                            sel_idx = teacher_options.index(current) if current in teacher_options else 0
                            val = st.selectbox('', options=teacher_options, index=sel_idx, key=key)
                            assignments.setdefault(str(eid), {}).setdefault(str(s), {})[subj] = val.strip()
                            # persist change immediately
                            try:
                                save_assignments(assignments)
                            except Exception:
                                pass
                with col_right:
                    for j, subj in enumerate(right):
                        key = f"assign__{eid}__{s}__R__{j}"
                        r0, r1 = st.columns([3, 2])
                        with r0:
                            st.write(subj)
                        with r1:
                            current = assignments.get(str(eid), {}).get(str(s), {}).get(subj, '')
                            sel_idx = teacher_options.index(current) if current in teacher_options else 0
                            val = st.selectbox('', options=teacher_options, index=sel_idx, key=key)
                            assignments.setdefault(str(eid), {}).setdefault(str(s), {})[subj] = val.strip()
                            # persist change immediately
                            try:
                                save_assignments(assignments)
                            except Exception:
                                pass

        # Removed Bulk assign and Quick assign per user request (manual select + compact UI used)

    st.markdown('---')

# --- Assignment analytics: per exam kind and combined summaries
def _compute_assignment_analytics(selected_eids):
    # Build mapping exam kind -> list of eids
    kind_map = {}
    for eid in selected_eids:
        meta = next((x for x in exams_meta if x.get('exam_id') == eid), {}) or {}
        kind = _exam_kind(meta)
        kind_map.setdefault(kind, []).append(eid)

    all_kinds = sorted(kind_map.keys())
    combined_teacher_rows = []
    combined_subject_rows = []
    # map subject -> set of streams where it is unassigned across selected exams
    combined_unassigned = {}

    for kind, eids in kind_map.items():
        teacher_vals = {}
        subject_vals = {}
        # collect subjects assigned per teacher for this kind
        teacher_subjects = {}
        unassigned = set()
        for eid in eids:
            res = results.get(eid, {})
            by_stream = res.get('by_stream', {})
            subj_list = res.get('subjects', [])
            # gather assigned subjects
            assigned_any = set()
            for s, stats in by_stream.items():
                assign_map = assignments.get(str(eid), {}).get(str(s), {})
                # determine a readable stream label
                stream_label = s if s else 'All students'
                for subj in subj_list:
                    teacher = assign_map.get(subj, '') if isinstance(assign_map, dict) else ''
                    if not subj or subj.startswith('_'):
                        continue
                    if teacher:
                        # assigned in this stream
                        assigned_any.add(subj)
                        mean = stats.get(subj, {}).get('mean_percent') if stats else None
                        if mean is not None:
                            teacher_vals.setdefault(teacher, []).append(float(mean))
                            subject_vals.setdefault(subj, []).append(float(mean))
                            # track subject for this teacher
                            teacher_subjects.setdefault(teacher, set()).add(subj)
                    else:
                        # not assigned in this stream -> mark subj as unassigned for this stream
                        combined_unassigned.setdefault(subj, set()).add(str(stream_label))
            # unassigned subjects in this exam (subjects not assigned in any stream)
            for subj in subj_list:
                if subj not in assigned_any:
                    unassigned.add(subj)
        # build per-kind summaries
        for t, vals in teacher_vals.items():
            subs = sorted(teacher_subjects.get(t, []))
            subs_txt = ', '.join(subs)
            combined_teacher_rows.append({'ExamKind': kind, 'Teacher': t, 'Count': len(vals), 'SumMean': round(sum(vals),2), 'AvgMean': round(sum(vals)/len(vals),2), 'Subjects': subs_txt})
        for sname, vals in subject_vals.items():
            combined_subject_rows.append({'ExamKind': kind, 'Subject': sname, 'Count': len(vals), 'SumMean': round(sum(vals),2), 'AvgMean': round(sum(vals)/len(vals),2)})

    # Combined across all kinds
    if combined_teacher_rows:
        df_comb_teacher = pd.DataFrame(combined_teacher_rows)
    else:
        df_comb_teacher = pd.DataFrame(columns=['ExamKind','Teacher','Count','SumMean','AvgMean','Subjects'])
    if combined_subject_rows:
        df_comb_subject = pd.DataFrame(combined_subject_rows)
    else:
        df_comb_subject = pd.DataFrame(columns=['ExamKind','Subject','Count','SumMean','AvgMean'])

    # convert combined_unassigned sets to sorted lists for display
    combined_unassigned = {k: sorted(list(v)) for k, v in combined_unassigned.items()}
    return df_comb_teacher, df_comb_subject, combined_unassigned

if assignments:
    # Automatically save assignments and show analytics / export options on the page
    # (the previous "Save all assignments to disk" button has been removed per request)
    # before saving, remove any assignments for non-assignable (combined) components
    try:
        for eid, meta in results.items():
            removed = meta.get('removed_components', []) or []
            if not removed:
                continue
            # iterate streams for this exam
            stream_map = assignments.get(str(eid), {})
            for stream_key, subj_map in list(stream_map.items()):
                if not isinstance(subj_map, dict):
                    continue
                for rc in removed:
                    subj_map.pop(rc, None)
    except Exception:
        pass
    ok = save_assignments(assignments)
    if ok:
        st.success('Assignments saved to disk')
    else:
        st.error('Failed to save assignments')

    # After saving, compute and show analytics (teacher summaries and unassigned list)
    df_teach, df_subj, unassigned = _compute_assignment_analytics(selected_ids)
    st.markdown('### Assignment analytics')
    if not df_teach.empty:
        st.markdown('Per-exam-kind teacher summaries (Sum and Average of assigned subject means)')
        # prepare export folder and timestamp for per-kind/combined downloads
        outdir = os.path.join(STORAGE_DIR, 'exports')
        os.makedirs(outdir, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        if st.button('Regenerate prepared PDFs'):
            st.session_state.pop('pdf_cache', None)
            st.session_state.pop('pdf_cache_hash', None)
            _safe_rerun()

        # Option: split per-kind tables by classification (Upper/Lower)
        split_by_groups = st.checkbox('Split per-kind tables by classification (Upper / Lower)', value=False)

        # Build a cache of generated PDFs so downloads are instant and don't block on click
        try:
            # compute a simple hash of the current assignments snapshot to avoid regenerating unnecessarily
            assign_snapshot = json.dumps(assignments or {}, sort_keys=True)
            current_hash = hashlib.sha1(assign_snapshot.encode()).hexdigest()
        except Exception:
            current_hash = None

        cache_key = f'pdf_cache_hash'
        if 'pdf_cache' not in st.session_state or st.session_state.get(cache_key) != current_hash:
            # regenerate cache
            pdf_cache = {}
            kinds = sorted(df_teach['ExamKind'].unique())
            # per-kind PDFs (optionally split by group)
            # use only Upper and Lower classifications for splitting (if present in class_map)
            groups = [g for g in ['Upper', 'Lower']]
            for kind in kinds:
                try:
                    sub = df_teach[df_teach['ExamKind'] == kind].copy()
                    sub = sub.sort_values('AvgMean', ascending=False)
                    display_cols = ['Teacher', 'Count', 'SumMean', 'AvgMean', 'Subjects']
                    slug = re.sub(r'[^A-Za-z0-9_-]', '_', str(kind))
                    # build a clear title including exam kind, term and year if available
                    rep = next((m for m in exams_meta if _exam_kind(m) == kind), {}) or {}
                    term = rep.get('term') or rep.get('exam_name')
                    year = rep.get('year')
                    title_text = f"{kind} — {term or ''}, {year or ''}".strip().strip(',')
                    # Always prepare per-group PDFs for Upper and Lower so downloads exist for both groups
                    for grp in groups:
                        try:
                            gslug = re.sub(r'[^A-Za-z0-9_-]', '_', str(grp))[:80]
                            outname = f'TeacherRanking_{slug}_{gslug}_{ts}.pdf'
                            outpath_k = os.path.join(outdir, outname)
                            # filter sub by teachers in this group
                            teachers_in_group = [t for t, v in class_map.items() if v == grp]
                            sub_grp = sub[sub['Teacher'].isin(teachers_in_group)].copy()
                            # format numeric columns for PDF
                            try:
                                pdf_sub = sub_grp[display_cols].copy()
                                for col in pdf_sub.columns:
                                    if pd.api.types.is_numeric_dtype(pdf_sub[col]):
                                        if 'Mean' in str(col):
                                            pdf_sub[col] = pdf_sub[col].apply(lambda x: format(x, '.2f') if pd.notna(x) else '')
                                        else:
                                            pdf_sub[col] = pdf_sub[col].apply(lambda x: format(x, '.0f') if pd.notna(x) else '')
                            except Exception:
                                pdf_sub = sub_grp[display_cols].copy()
                            pdf_bytes = generate_teacher_table_bytes(pdf_sub, title=f"{title_text} — Group: {grp}")
                            try:
                                key = os.path.join('teacher_analysis', outname)
                                storage.write_bytes(key, pdf_bytes, content_type='application/pdf')
                                pdf_cache[f"{slug}__{gslug}"] = {'bytes': pdf_bytes, 'filename': outname, 'path': key}
                            except Exception:
                                # fallback to local file for record
                                try:
                                    with open(outpath_k, 'wb') as _f:
                                        _f.write(pdf_bytes)
                                    pdf_cache[f"{slug}__{gslug}"] = {'bytes': pdf_bytes, 'filename': outname, 'path': outpath_k}
                                except Exception:
                                    pdf_cache[f"{slug}__{gslug}"] = {'error': 'failed to persist pdf'}
                        except Exception as _e:
                            pdf_cache[f"{slug}__{gslug}"] = {'error': str(_e)}

                    # Also prepare a combined per-kind PDF (not split)
                    try:
                        outname = f'TeacherRanking_{slug}_{ts}.pdf'
                        outpath_k = os.path.join(outdir, outname)
                        # format numeric columns for PDF
                        try:
                            pdf_sub = sub[display_cols].copy()
                            for col in pdf_sub.columns:
                                if pd.api.types.is_numeric_dtype(pdf_sub[col]):
                                    if 'Mean' in str(col):
                                        pdf_sub[col] = pdf_sub[col].apply(lambda x: format(x, '.2f') if pd.notna(x) else '')
                                    else:
                                        pdf_sub[col] = pdf_sub[col].apply(lambda x: format(x, '.0f') if pd.notna(x) else '')
                        except Exception:
                            pdf_sub = sub[display_cols].copy()
                        pdf_bytes = generate_teacher_table_bytes(pdf_sub, title=title_text)
                        try:
                            key = os.path.join('teacher_analysis', outname)
                            storage.write_bytes(key, pdf_bytes, content_type='application/pdf')
                            pdf_cache[slug] = {'bytes': pdf_bytes, 'filename': outname, 'path': key}
                        except Exception:
                            try:
                                with open(outpath_k, 'wb') as _f:
                                    _f.write(pdf_bytes)
                                pdf_cache[slug] = {'bytes': pdf_bytes, 'filename': outname, 'path': outpath_k}
                            except Exception:
                                pdf_cache[slug] = {'error': 'failed to persist pdf'}
                    except Exception as _e:
                        pdf_cache[slug] = {'error': str(_e)}
                except Exception as e:
                    pdf_cache[slug] = {'error': str(e)}

            # combined average ranking
            try:
                grp = df_teach.groupby('Teacher').agg({'AvgMean': 'mean', 'Count': 'sum', 'SumMean': 'sum'}).reset_index()
                grp = grp.rename(columns={'AvgMean': 'CombinedAvgMean', 'Count': 'TotalCount', 'SumMean': 'TotalSumMean'})
                grp['CombinedAvgMean'] = grp['CombinedAvgMean'].round(2)
                grp = grp.sort_values('CombinedAvgMean', ascending=False)
                # aggregate Subjects across kinds for each teacher
                try:
                    subj_series = df_teach.groupby('Teacher')['Subjects'].apply(lambda s: ', '.join(sorted({x.strip() for xs in s.dropna() for x in xs.split(',') if x.strip()}))).reset_index(name='Subjects')
                    grp = grp.merge(subj_series, on='Teacher', how='left')
                except Exception:
                    grp['Subjects'] = ''
                # Build a descriptive title including the exam kinds, term(s) and year
                kinds_list = sorted(df_teach['ExamKind'].unique())
                kinds_str = ', '.join(kinds_list) if kinds_list else 'Selected exams'
                # sel_terms and sel_year are in scope from the page filters; fall back to sensible defaults
                term_display = 'All terms' if (not sel_terms or 'All' in sel_terms) else ', '.join(sel_terms)
                year_display = sel_year if sel_year and sel_year != 'All' else 'All years'
                combined_title = f'Combined teacher average ranking — Kinds: {kinds_str}; Terms: {term_display}; Year: {year_display}'
                # create a sanitized filename incorporating the kinds
                kinds_slug = re.sub(r'[^A-Za-z0-9_-]', '_', kinds_str)[:120]
                outname = f'TeacherCombinedAvg_{kinds_slug}_{ts}.pdf'
                outpath_c = os.path.join(outdir, outname)
                # prepare pdf table with formatting and include Subjects
                try:
                    pdf_grp = grp[['Teacher', 'TotalCount', 'TotalSumMean', 'CombinedAvgMean', 'Subjects']].copy()
                    for col in pdf_grp.columns:
                        if pd.api.types.is_numeric_dtype(pdf_grp[col]):
                            if 'Mean' in str(col):
                                pdf_grp[col] = pdf_grp[col].apply(lambda x: format(x, '.2f') if pd.notna(x) else '')
                            else:
                                pdf_grp[col] = pdf_grp[col].apply(lambda x: format(x, '.0f') if pd.notna(x) else '')
                except Exception:
                    pdf_grp = grp[['Teacher', 'TotalCount', 'TotalSumMean', 'CombinedAvgMean']].copy()
                    pdf_grp['Subjects'] = ''
                pdf_bytes = generate_teacher_table_bytes(pdf_grp, title=combined_title)
                try:
                    key = os.path.join('teacher_analysis', outname)
                    storage.write_bytes(key, pdf_bytes, content_type='application/pdf')
                    pdf_cache['combined'] = {'bytes': pdf_bytes, 'filename': outname, 'path': key}
                except Exception:
                    try:
                        with open(outpath_c, 'wb') as _f:
                            _f.write(pdf_bytes)
                        pdf_cache['combined'] = {'bytes': pdf_bytes, 'filename': outname, 'path': outpath_c}
                    except Exception:
                        pdf_cache['combined'] = {'error': 'failed to persist pdf'}
            except Exception as e:
                pdf_cache['combined'] = {'error': str(e)}

            # Also prepare per-group combined PDFs (Upper/Lower) so downloads exist for both
            try:
                groups_for_comb = ['Upper', 'Lower']
                for grp_name in groups_for_comb:
                    try:
                        gslug = re.sub(r'[^A-Za-z0-9_-]', '_', str(grp_name))[:80]
                        outname_g = f'TeacherCombinedAvg_{kinds_slug}_{gslug}_{ts}.pdf'
                        outpath_g = os.path.join(outdir, outname_g)
                        # filter grp by teachers in this group
                        teachers_in_group = [t for t, v in class_map.items() if v == grp_name]
                        grp_filtered = grp[grp['Teacher'].isin(teachers_in_group)].copy()
                        # ensure Subjects aggregated column exists (may be missing)
                        if 'Subjects' not in grp_filtered.columns:
                            try:
                                subj_series = df_teach.groupby('Teacher')['Subjects'].apply(lambda s: ', '.join(sorted({x.strip() for xs in s.dropna() for x in xs.split(',') if x.strip()}))).reset_index(name='Subjects')
                                grp_filtered = grp_filtered.merge(subj_series, on='Teacher', how='left')
                            except Exception:
                                grp_filtered['Subjects'] = ''
                        # prepare PDF table formatting
                        try:
                            pdf_grp_g = grp_filtered[['Teacher', 'TotalCount', 'TotalSumMean', 'CombinedAvgMean', 'Subjects']].copy()
                            for col in pdf_grp_g.columns:
                                if pd.api.types.is_numeric_dtype(pdf_grp_g[col]):
                                    if 'Mean' in str(col):
                                        pdf_grp_g[col] = pdf_grp_g[col].apply(lambda x: format(x, '.2f') if pd.notna(x) else '')
                                    else:
                                        pdf_grp_g[col] = pdf_grp_g[col].apply(lambda x: format(x, '.0f') if pd.notna(x) else '')
                        except Exception:
                            pdf_grp_g = grp_filtered[['Teacher', 'TotalCount', 'TotalSumMean', 'CombinedAvgMean']].copy()
                            pdf_grp_g['Subjects'] = ''
                        pdf_bytes_g = generate_teacher_table_bytes(pdf_grp_g, title=f"{combined_title} — Group: {grp_name}")
                        try:
                            keyg = os.path.join('teacher_analysis', outname_g)
                            storage.write_bytes(keyg, pdf_bytes_g, content_type='application/pdf')
                            pdf_cache[f'combined__{gslug}'] = {'bytes': pdf_bytes_g, 'filename': outname_g, 'path': keyg}
                        except Exception:
                            try:
                                with open(outpath_g, 'wb') as _fg:
                                    _fg.write(pdf_bytes_g)
                                pdf_cache[f'combined__{gslug}'] = {'bytes': pdf_bytes_g, 'filename': outname_g, 'path': outpath_g}
                            except Exception as eg:
                                pdf_cache[f'combined__{gslug}'] = {'error': str(eg)}
                    except Exception as eg:
                        pdf_cache[f'combined__{gslug}'] = {'error': str(eg)}
            except Exception:
                pass

            st.session_state['pdf_cache'] = pdf_cache
            st.session_state[cache_key] = current_hash

        # Optional combined-average ranking across kinds (displayed from cache)
        show_combined_avg = st.checkbox('Show combined average ranking (mean of AvgMean across exam kinds) for each teacher', value=False)
        if show_combined_avg:
            cached = st.session_state.get('pdf_cache', {})
            # if splitting by classification, show per-group combined tables and downloads
            groups_for_display = ['Upper', 'Lower']
            if split_by_groups:
                st.subheader('Combined average ranking (split by classification)')
                for grp_name in groups_for_display:
                    gslug = re.sub(r'[^A-Za-z0-9_-]', '_', str(grp_name))[:80]
                    cinfo = cached.get(f'combined__{gslug}') or {}
                    st.markdown(f'**Group: {grp_name}**')
                    # build and display table for this group
                    grp_table = df_teach.groupby('Teacher').agg({'AvgMean': 'mean', 'Count': 'sum', 'SumMean': 'sum'}).reset_index()
                    grp_table = grp_table.rename(columns={'AvgMean': 'CombinedAvgMean', 'Count': 'TotalCount', 'SumMean': 'TotalSumMean'})
                    try:
                        subj_series = df_teach.groupby('Teacher')['Subjects'].apply(lambda s: ', '.join(sorted({x.strip() for xs in s.dropna() for x in xs.split(',') if x.strip()}))).reset_index(name='Subjects')
                        grp_table = grp_table.merge(subj_series, on='Teacher', how='left')
                    except Exception:
                        grp_table['Subjects'] = ''
                    # filter by teachers in this classification
                    teachers_in_group = [t for t, v in class_map.items() if v == grp_name]
                    grp_table = grp_table[grp_table['Teacher'].isin(teachers_in_group)].copy()
                    grp_table = grp_table.sort_values('CombinedAvgMean', ascending=False)
                    display_cols_comb = ['Teacher', 'TotalCount', 'TotalSumMean', 'CombinedAvgMean', 'Subjects']
                    # format CombinedAvgMean to 2 decimals for display
                    try:
                        dispct = grp_table[display_cols_comb].copy()
                        if 'CombinedAvgMean' in dispct.columns:
                            dispct['CombinedAvgMean'] = dispct['CombinedAvgMean'].apply(lambda x: f"{float(x):.2f}" if pd.notna(x) else '')
                        st.dataframe(dispct.reset_index(drop=True), use_container_width=True)
                    except Exception:
                        st.dataframe(grp_table[display_cols_comb].reset_index(drop=True), use_container_width=True)
                    if 'bytes' in cinfo:
                        st.success(f'Prepared combined PDF for {grp_name}: {cinfo.get("filename")} ({len(cinfo.get("bytes", b""))} bytes)')
                        st.download_button(f'Download combined average PDF — {grp_name}', cinfo['bytes'], file_name=cinfo.get('filename'), mime='application/pdf', key=f'dl_combined__{gslug}__{ts}')
                    else:
                        st.info(f'No prepared combined PDF for {grp_name}')
            else:
                cinfo = cached.get('combined') or {}
                if 'bytes' in cinfo:
                    # display overall combined table
                    grp = df_teach.groupby('Teacher').agg({'AvgMean': 'mean', 'Count': 'sum', 'SumMean': 'sum'}).reset_index()
                    grp = grp.rename(columns={'AvgMean': 'CombinedAvgMean', 'Count': 'TotalCount', 'SumMean': 'TotalSumMean'})
                    grp['CombinedAvgMean'] = grp['CombinedAvgMean'].round(2)
                    try:
                        subj_series = df_teach.groupby('Teacher')['Subjects'].apply(lambda s: ', '.join(sorted({x.strip() for xs in s.dropna() for x in xs.split(',') if x.strip()}))).reset_index(name='Subjects')
                        grp = grp.merge(subj_series, on='Teacher', how='left')
                    except Exception:
                        grp['Subjects'] = ''
                    grp = grp.sort_values('CombinedAvgMean', ascending=False)
                    display_cols_comb = ['Teacher', 'TotalCount', 'TotalSumMean', 'CombinedAvgMean', 'Subjects']
                    st.subheader('Combined average ranking (across selected kinds)')
                    # format CombinedAvgMean to 2 decimals for display
                    try:
                        dispct = grp[display_cols_comb].copy()
                        if 'CombinedAvgMean' in dispct.columns:
                            dispct['CombinedAvgMean'] = dispct['CombinedAvgMean'].apply(lambda x: f"{float(x):.2f}" if pd.notna(x) else '')
                        st.dataframe(dispct.reset_index(drop=True), use_container_width=True)
                    except Exception:
                        st.dataframe(grp[display_cols_comb].reset_index(drop=True), use_container_width=True)
                    st.success(f'Prepared combined PDF: {cinfo.get("filename")} ({len(cinfo.get("bytes", b""))} bytes)')
                    st.download_button('Download combined average PDF', cinfo['bytes'], file_name=cinfo.get('filename'), mime='application/pdf', key=f'dl_combined__{ts}')
                else:
                    st.error(f'Failed to prepare combined PDF: {cinfo.get("error")}')

        # per-kind display and download from cache (optionally split by groups)
        cached = st.session_state.get('pdf_cache', {})
        groups = ['Upper', 'Lower']
        for kind in sorted(df_teach['ExamKind'].unique()):
            st.subheader(f'{kind}')
            sub = df_teach[df_teach['ExamKind'] == kind].copy()
            sub = sub.sort_values('AvgMean', ascending=False)
            display_cols = ['Teacher', 'Count', 'SumMean', 'AvgMean', 'Subjects']
            slug = re.sub(r'[^A-Za-z0-9_-]', '_', str(kind))
            if split_by_groups and groups:
                for grp in groups:
                    st.markdown(f'**Group: {grp}**')
                    teachers_in_group = [t for t, v in class_map.items() if v == grp]
                    sub_grp = sub[sub['Teacher'].isin(teachers_in_group)].copy()
                    # format AvgMean to 2 decimals for display
                    try:
                        disp = sub_grp[display_cols].copy()
                        if 'AvgMean' in disp.columns:
                            disp['AvgMean'] = disp['AvgMean'].apply(lambda x: f"{float(x):.2f}" if pd.notna(x) else '')
                        st.dataframe(disp.reset_index(drop=True), use_container_width=True)
                    except Exception:
                        st.dataframe(sub_grp[display_cols].reset_index(drop=True), use_container_width=True)
                    gslug = re.sub(r'[^A-Za-z0-9_-]', '_', str(grp))[:80]
                    cinfo = cached.get(f"{slug}__{gslug}") or {}
                    if 'bytes' in cinfo:
                        st.success(f'Prepared PDF: {cinfo.get("filename")} ({len(cinfo.get("bytes", b""))} bytes)')
                        st.download_button(f'Download {kind} — {grp} PDF', cinfo['bytes'], file_name=cinfo.get('filename'), mime='application/pdf', key=f'dl__{slug}__{gslug}__{ts}')
                    else:
                        st.info(f'No PDF prepared for {kind} — {grp}')
            else:
                # format AvgMean to 2 decimals for display
                try:
                    disp = sub[display_cols].copy()
                    if 'AvgMean' in disp.columns:
                        disp['AvgMean'] = disp['AvgMean'].apply(lambda x: f"{float(x):.2f}" if pd.notna(x) else '')
                    st.dataframe(disp.reset_index(drop=True), use_container_width=True)
                except Exception:
                    st.dataframe(sub[display_cols].reset_index(drop=True), use_container_width=True)
                cinfo = cached.get(slug) or {}
                if 'bytes' in cinfo:
                    st.success(f'Prepared PDF: {cinfo.get("filename")} ({len(cinfo.get("bytes", b""))} bytes)')
                    st.download_button(f'Download {kind} PDF', cinfo['bytes'], file_name=cinfo.get('filename'), mime='application/pdf', key=f'dl__{slug}__{ts}')
                else:
                    st.error(f'Failed to prepare PDF for {kind}: {cinfo.get("error")}')
    else:
        st.info('No teacher assignment summaries available yet')
    # Per-exam-kind subject summaries removed per user request
    if unassigned:
        st.markdown('Subjects not assigned anywhere (combined across selected exams)')
        for subj, streams in unassigned.items():
            try:
                streams_list = ', '.join(streams) if streams else 'All students'
            except Exception:
                streams_list = str(streams)
            st.write(f'- {subj} — Streams: {streams_list}')
else:
    st.info('No assignments present to save or analyze')

st.caption('Means computed as sum of marks for subject in the stream ÷ number of students in that stream (as requested).')
st.markdown('---')
# Footer: thank-you, contact and COPYRIGHT
st.markdown("""
<div style='background:transparent; padding:12px 6px 18px 6px; border-radius:6px; margin-top:8px;'>
    <div style='font-size:13px; color:#374151; text-align:center;'>
        <strong>Thank you for choosing EduScore Analytics</strong>
        <div style='margin-top:6px; font-size:12px; color:#6b7280;'>MUNYUA KAMAU — 0793975959</div>
        <div style='margin-top:8px; font-size:11px; color:#9ca3af;'>COPY RIGHT © {year} EduScore Analytics</div>
    </div>
</div>
""".format(year=datetime.now().year), unsafe_allow_html=True)
