# Minimal Director's Lounge — focused on Saved Exams table only
import streamlit as st
import os
import json
import pandas as pd
from datetime import datetime
import hashlib
from utils.pdf_export import generate_teacher_table_bytes
from pathlib import Path
from modules import storage
import base64
import io

# determine per-school storage directory early
STORAGE_DIR = storage.get_storage_dir()

st.set_page_config(page_title="Director's Lounge — Saved Exams", layout="wide")

try:
    # Build same banner fragment used on the auth page for visual consistency
    logo_html = None
    try:
        # search possible static folders: local `pages/static` then repo `static`
        candidates = [
            Path(__file__).parent / 'static',
            Path(__file__).parents[1] / 'static',
            Path(__file__).parents[2] / 'static' if len(Path(__file__).parents) > 2 else Path(__file__).parents[1] / 'static'
        ]
        logo_path = None
        for logo_dir in candidates:
            logo_path_jpg = logo_dir / 'eduscore_logo.jpg'
            logo_path_jpeg = logo_dir / 'eduscore_logo.jpeg'
            logo_path_png = logo_dir / 'eduscore_logo.png'
            for p in (logo_path_png, logo_path_jpg, logo_path_jpeg):
                if p.exists():
                    logo_path = p
                    break
            if logo_path is not None:
                break
        if logo_path is not None:
            try:
                data = base64.b64encode(logo_path.read_bytes()).decode('ascii')
                mime = 'image/png' if logo_path.suffix.lower().endswith('png') else 'image/jpeg'
                # responsive logo in banner per user request (even smaller)
                logo_html = f"<img src='data:{mime};base64,{data}' style='max-width:80px;height:auto;object-fit:contain;border-radius:12px;box-shadow:0 4px 12px rgba(2,6,23,0.12);'/>"
            except Exception:
                logo_html = None
    except Exception:
        logo_html = None

    tile_html = """
        <div style="width:140px; height:140px; border-radius:16px; background: linear-gradient(135deg, rgba(255,255,255,0.12), rgba(255,255,255,0.06)); display:flex; align-items:center; justify-content:center; font-weight:900; font-size:56px; color:#fff; box-shadow: 0 10px 34px rgba(2,6,23,0.22);">E</div>
    """

    logo_fragment = logo_html if logo_html else tile_html

    try:
        import streamlit.components.v1 as components

        banner_html = f'''
        <div style="width:100%; display:flex; justify-content:center;">
          <div style="max-width:1100px; width:100%; padding:14px 18px; border-radius:12px; margin-bottom:12px; background: linear-gradient(90deg, #06243a, #0b4d3e); box-shadow: 0 12px 32px rgba(6,30,60,0.18); color: #fff;">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:18px; flex-wrap:wrap;">
                <div style="display:flex; align-items:center; gap:14px; flex:1; min-width:0;">
                    {logo_fragment}
                    <div style="min-width:0;">
                        <div style="font-family: 'Montserrat', 'Poppins', 'Segoe UI', sans-serif; font-size:26px; font-weight:900; letter-spacing:0.01em; line-height:1.05;">
                            <span style="color:#1b3b8b">EDUSCORE</span>
                            <span style="margin-left:8px; color:#f59e0b">ANALYTICS</span>
                        </div>
                        <!-- Updated tagline per user request (sentence case) -->
                        <div style="opacity:0.98; margin-top:6px; font-size:16px; font-weight:800; text-transform:none;">Because every mark counts</div>
                        <div style="opacity:0.88; margin-top:6px; font-size:13px; font-weight:700;">Results verified and autochecked for errors</div>
                        <div style="margin-top:8px;font-size:24px;font-weight:900;">Director's Lounge</div>
                    </div>
                </div>
                <div style="text-align:right; min-width:120px; display:flex; align-items:center; justify-content:flex-end; gap:10px; flex:0 0 auto;">
                    <div style="background: rgba(255,255,255,0.06); padding:8px 12px; border-radius:999px; display:inline-block; font-weight:700; font-size:12px;">Directors</div>
                </div>
            </div>
          </div>
        </div>
        '''
        components.html(banner_html, height=260, scrolling=False)
    except Exception:
        st.markdown(f"""
        <div style="width:100%; display:flex; justify-content:center;">
          <div style="max-width:920px; width:100%; padding:18px 20px; border-radius:12px; margin-bottom:12px; background: linear-gradient(90deg, #06243a, #0b4d3e); box-shadow: 0 12px 32px rgba(6,30,60,0.18); color: #fff;">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;">
                <div style="display:flex; align-items:center; gap:12px;">
                    {logo_fragment}
                    <div>
                        <div style="font-family: 'Montserrat', 'Poppins', 'Segoe UI', sans-serif; font-size:30px; font-weight:900; letter-spacing:0.01em; line-height:1; text-transform:uppercase;">
                            <span style="color:#1b3b8b">EDUSCORE</span>
                            <span style="margin-left:8px; color:#f59e0b">ANALYTICS</span>
                        </div>
                        <div style="opacity:0.98; margin-top:6px; font-size:16px; font-weight:800; text-transform:none;">Because every mark counts</div>
                        <div style="opacity:0.88; margin-top:6px; font-size:13px; font-weight:700;">Results verified and autochecked for errors</div>
                        <div style="margin-top:8px;font-size:28px;font-weight:900;">Director's Lounge</div>
                    </div>
                </div>
                <div style="text-align:right; min-width:120px;">
                    <div style="background: rgba(255,255,255,0.06); padding:8px 12px; border-radius:999px; display:inline-block; font-weight:700; font-size:12px;">Directors</div>
                </div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)
except Exception:
    # fallback: simple textual header
    st.markdown('<h1>Director\'s Lounge</h1>')

# Footer overlay (fixed at bottom)
footer_html = """
<style>
#eduscore-footer-updated { position: fixed; left: 0; right: 0; bottom: 0; background: linear-gradient(90deg,#0f172a,#0b4d3e); color: #e6eef6; padding:6px 6px; text-align:center; font-size:13px; z-index:100000; border-top:1px solid rgba(255,255,255,0.04); }
div[data-testid="stApp"] > div:nth-child(1) { padding-bottom:80px !important; }
#eduscore-footer-updated small { opacity:0.9; }
</style>
<div id="eduscore-footer-updated">EDUSCORE ANALYTICS &nbsp; <small style="font-weight:600;">Developed by Munyua Kamau</small> &nbsp; <small style="font-weight:700;">Contact: 0793975959</small> &nbsp; © 2025</div>
"""
st.markdown(footer_html, unsafe_allow_html=True)

st.markdown('---')
# --- Parent messages submitted via Parents Portal
try:
    # messages are stored under per-school storage; use storage adapter
    msgs_path = os.path.join(STORAGE_DIR, 'messages', 'parent_messages.json')
    archive_path = os.path.join(STORAGE_DIR, 'messages', 'parent_messages_archived.json')

    def load_messages():
        try:
            data = storage.read_json(msgs_path)
            return data or []
        except Exception:
            return []
        return []

    def save_messages(msgs):
        try:
            return storage.write_json(msgs_path, msgs)
        except Exception as e:
            st.exception(e)
            return False

    def load_archive():
        try:
            data = storage.read_json(archive_path)
            return data or []
        except Exception:
            return []
        return []

    def save_archive(items):
        try:
            return storage.write_json(archive_path, items)
        except Exception as e:
            st.exception(e)
            return False

    messages = load_messages()

    st.markdown('### Messages from Parents')
    st.info('Parents can send short messages to the directors via the Parents Portal. Messages include parent contact details for follow-up.')

    # Controls: refresh and time window filter
    c1, c2, c3 = st.columns([1,2,2])
    with c1:
        if st.button('Refresh'):
            messages = load_messages()
    with c2:
        time_window = st.selectbox('Time window', options=['All', 'Last 7 days', 'Last 30 days', 'Last 90 days', 'Last year'], index=1)
    with c3:
        st.markdown(f"**Total messages:** {len(messages)}")

    # Mass actions
    with st.expander('Actions (archive / delete)'):
        ac1, ac2, ac3 = st.columns([2,2,2])
        with ac1:
            days_for_archive = st.number_input('Archive read messages older than (days)', min_value=0, value=30)
            if st.button('Archive read messages'):
                # archive read messages older than threshold
                now = datetime.utcnow()
                msgs = load_messages()
                to_archive = []
                remaining = []
                for mm in msgs:
                    try:
                        t = datetime.fromisoformat(mm.get('timestamp')) if mm.get('timestamp') else None
                    except Exception:
                        t = None
                    age_days = (now - t).days if t else 0
                    if mm.get('read') and (age_days >= int(days_for_archive)):
                        mm['archived_at'] = datetime.utcnow().isoformat()
                        to_archive.append(mm)
                    else:
                        remaining.append(mm)
                if to_archive:
                    arch = load_archive() or []
                    arch.extend(to_archive)
                    if save_archive(arch):
                        if save_messages(remaining):
                            messages = remaining
                            st.success(f'Archived {len(to_archive)} messages')
                        else:
                            st.error('Failed to update messages file after archiving')
                    else:
                        st.error('Failed to write archive file')
                else:
                    st.info('No read messages found matching the threshold')
        with ac2:
            days_for_delete = st.number_input('Delete messages older than (days)', min_value=0, value=365)
            if st.button('Delete messages older than threshold'):
                now = datetime.utcnow()
                msgs = load_messages()
                remaining = []
                deleted = []
                for mm in msgs:
                    try:
                        t = datetime.fromisoformat(mm.get('timestamp')) if mm.get('timestamp') else None
                    except Exception:
                        t = None
                    age_days = (now - t).days if t else 0
                    if t and age_days >= int(days_for_delete):
                        deleted.append(mm)
                    else:
                        remaining.append(mm)
                if deleted:
                    if save_messages(remaining):
                        messages = remaining
                        st.success(f'Deleted {len(deleted)} messages')
                    else:
                        st.error('Failed to write messages file')
                else:
                    st.info('No messages older than threshold')
        with ac3:
            if st.button('Delete ALL messages'):
                if save_messages([]):
                    messages = []
                    st.success('All messages deleted')
                else:
                    st.error('Failed to clear messages file')

    # Show archived messages expander
    arch = load_archive()
    with st.expander(f'Archived messages ({len(arch)})'):
        if arch:
            # group by year-month
            groups = {}
            for a in arch:
                ts = a.get('timestamp') or a.get('archived_at') or ''
                try:
                    d = datetime.fromisoformat(ts)
                    key = f"{d.year}-{d.month:02d}"
                except Exception:
                    key = 'unknown'
                groups.setdefault(key, 0)
                groups[key] += 1
            for k in sorted(groups.keys(), reverse=True):
                st.markdown(f"**{k}** — {groups[k]} messages")
            if st.button('Purge archived older than 2 years'):
                now = datetime.utcnow()
                kept = []
                purged = 0
                for a in arch:
                    try:
                        t = datetime.fromisoformat(a.get('archived_at') or a.get('timestamp'))
                    except Exception:
                        t = None
                    if t and (now - t).days > 365*2:
                        purged += 1
                    else:
                        kept.append(a)
                if save_archive(kept):
                    st.success(f'Purged {purged} archived messages')
                else:
                    st.error('Failed to update archive file')

    # filter messages by time window
    now = datetime.utcnow()
    def within_window(m):
        if time_window == 'All':
            return True
        try:
            t = datetime.fromisoformat(m.get('timestamp'))
        except Exception:
            return False
        delta = (now - t).days
        if time_window == 'Last 7 days':
            return delta <= 7
        if time_window == 'Last 30 days':
            return delta <= 30
        if time_window == 'Last 90 days':
            return delta <= 90
        if time_window == 'Last year':
            return delta <= 365
        return True

    visible = [m for m in sorted(messages, key=lambda x: x.get('timestamp') or '', reverse=True) if within_window(m)]

    if not visible:
        st.info('No messages from parents yet for the selected time window.')
    else:
        for i, m in enumerate(visible):
            try:
                ts = m.get('timestamp') or ''
                pname = m.get('parent_name') or ''
                pphone = m.get('parent_phone') or ''
                sname = m.get('student_name') or ''
                sid = m.get('student_id') or ''
                txt = m.get('message') or ''
                read_flag = bool(m.get('read'))
                header = f"{pname or 'Parent'} — {pphone}"
                sub = f"Student: {sname} {('(' + sid + ')') if sid else ''}"
                col1, col2 = st.columns([9,1])
                with col1:
                    st.markdown(f"<div style='padding:10px;border-radius:8px;border:1px solid #e6eef6;margin-bottom:8px;'>\n<strong style='font-size:14px'>{header}</strong> <small style='color:#6b7280'>· {ts}</small><div style='color:#374151;margin-top:6px'>{txt}</div><div style='margin-top:6px;color:#6b7280'>{sub}</div>\n</div>", unsafe_allow_html=True)
                with col2:
                    try:
                        key_read = f'pm_read_toggle_{i}_{hash(pphone+ts)}'
                        key_del = f'pm_delete_{i}_{hash(pphone+ts)}'
                        if st.button('Mark as read' if not read_flag else 'Mark as unread', key=key_read):
                            try:
                                on_disk = load_messages()
                                changed = False
                                for mm in on_disk:
                                    if (mm.get('timestamp') == m.get('timestamp')) and (mm.get('parent_phone') == m.get('parent_phone')) and (mm.get('message') == m.get('message')):
                                        mm['read'] = not bool(mm.get('read'))
                                        changed = True
                                        break
                                if changed:
                                    if save_messages(on_disk):
                                        messages = on_disk
                                        st.success('Updated message state')
                                    else:
                                        st.error('Failed to save updated message state')
                            except Exception as e:
                                st.exception(e)
                        if st.button('Delete', key=key_del):
                            try:
                                on_disk = load_messages()
                                new_msgs = [mm for mm in on_disk if not ((mm.get('timestamp') == m.get('timestamp')) and (mm.get('parent_phone') == m.get('parent_phone')) and (mm.get('message') == m.get('message')))]
                                if save_messages(new_msgs):
                                    messages = new_msgs
                                    st.success('Deleted message')
                                else:
                                    st.error('Failed to delete message')
                            except Exception as e:
                                st.exception(e)
                    except Exception:
                        pass
            except Exception:
                continue
except Exception:
    st.exception('Failed loading parent messages')

# Storage and metadata
from modules.storage import get_storage_dir
STORAGE_DIR = get_storage_dir()
META_PATH = os.path.join(STORAGE_DIR, 'exams_metadata.json')

# Load metadata (use storage adapter so this is S3-aware)
try:
    try:
        meta = storage.read_json(META_PATH) or {}
    except Exception:
        # legacy fallback to bare key if adapter accepts it
        try:
            meta = storage.read_json('exams_metadata.json') or {}
        except Exception:
            meta = {}
except Exception:
    meta = {}

saved_exams = list(meta.values()) if isinstance(meta, dict) else meta

if not saved_exams:
    st.warning("No exams saved yet. Upload or save exams and return here.")
    st.stop()

# Browse controls: Year and Class
def _extract_class_field(e):
    return (e.get('class') or e.get('class_name') or e.get('grade') or e.get('grade_name') or e.get('klass') or '')

all_years = sorted(list({(e.get('year') or 'Unknown') for e in saved_exams}))
all_classes = sorted(list({str(_extract_class_field(e)).strip() for e in saved_exams if _extract_class_field(e)}))

# Show total saved exams and present the full table (no browse controls)
st.markdown(f"<div style='font-size:16px;font-weight:700;margin-bottom:6px;'>Total Exams Saved: {len(saved_exams)}</div>", unsafe_allow_html=True)

# --- Filters: Year / Term / Exam Kind (Director view) ---
def _normalize_term_label_local(t):
    if not t:
        return ''
    s = str(t).strip().lower()
    s_n = ''.join(ch for ch in s if ch.isalnum() or ch.isspace() or ch=='-')
    if 'end' in s_n and 'term' in s_n:
        return 'End Term'
    import re
    if re.search(r'(?:term\s*-?\s*1|term1|termone|first|one|\b1\b)', s_n):
        return 'Term 1'
    if re.search(r'(?:term\s*-?\s*2|term2|termtwo|second|two|\b2\b)', s_n):
        return 'Term 2'
    if re.search(r'(?:term\s*-?\s*3|term3|termthree|third|three|\b3\b)', s_n):
        return 'Term 3'
    return str(t).strip()

def _exam_kind_from_label_local(name: str) -> str:
    try:
        if not name:
            return ''
        parts = [p.strip() for p in str(name).split(' - ') if p.strip()]
        first = parts[0] if parts else str(name)
        first_l = first.lower()
        if 'end' in first_l and 'term' in first_l:
            return 'End Term'
        # normalize term labels as kinds
        if 'term' in first_l:
            return first.title()
        return first.title()
    except Exception:
        return str(name)

# Build filter option sets
all_meta = saved_exams
# Build years robustly: handle numeric year fields and various date formats safely
years_set = set()
for m in all_meta:
    y = m.get('year')
    if y is None or y == '':
        ds = m.get('date_saved') or m.get('saved_at') or ''
        if ds:
            try:
                ys = str(ds).split('-')[0]
            except Exception:
                ys = str(ds)
            years_set.add(str(ys))
    else:
        years_set.add(str(y))
years = sorted(years_set)
terms = sorted({_normalize_term_label_local(m.get('term') or '') for m in all_meta if (m.get('term') or '')})
kinds = sorted({_exam_kind_from_label_local(m.get('exam_name') or '') for m in all_meta if (m.get('exam_name') or '')})

col_y, col_t, col_k = st.columns([1,1,2])
with col_y:
    year_choice = st.selectbox('Year', options=['All'] + years, index=0, key='dl_year')
with col_t:
    term_choice = st.selectbox('Term', options=['All'] + terms, index=0, key='dl_term')
with col_k:
    kind_choice = st.selectbox('Exam Kind', options=['All'] + kinds, index=0, key='dl_kind')

def _matches_filters(meta):
    if year_choice != 'All':
        # try explicit year field first, else parse from saved date
        y = meta.get('year') or ''
        if not y:
            ds = meta.get('date_saved') or meta.get('saved_at') or ''
            if isinstance(ds, str) and '-' in ds:
                y = ds.split('-')[0]
        if str(y) != str(year_choice):
            return False
    if term_choice != 'All':
        if _normalize_term_label_local(meta.get('term') or '') != term_choice:
            return False
    if kind_choice != 'All':
        if _exam_kind_from_label_local(meta.get('exam_name') or '') != kind_choice:
            return False
    return True

filtered = [m for m in saved_exams if _matches_filters(m)]

# Build table rows
rows = []
for e in sorted(filtered, key=lambda x: (x.get('year') or '', x.get('exam_name') or '')):
    eid = e.get('exam_id')
    exam_name = e.get('exam_name') or eid
    exam_dir = os.path.join(STORAGE_DIR, eid) if eid else None
    data_p = os.path.join(exam_dir or '', 'data.pkl')
    raw_p = os.path.join(exam_dir or '', 'raw_data.pkl')

    students_cnt = ''
    subjects_cnt = ''

    # try to read pickles for counts
    try:
        df = None
        if eid and os.path.exists(data_p):
            df = pd.read_pickle(data_p)
        elif eid and os.path.exists(raw_p):
            df = pd.read_pickle(raw_p)
        if isinstance(df, pd.DataFrame):
            # student count
            name_col = None
            for c in df.columns:
                if 'name' in str(c).lower():
                    name_col = c; break
            if name_col:
                names = df[name_col].astype(str).str.strip()
                mask = ~names.str.lower().isin(['totals','total','mean','average','means'])
                students_cnt = int(names[mask].dropna().nunique())
            else:
                students_cnt = len(df)
            # subjects heuristic
            sub_cnt = 0
            for c in df.columns:
                lc = str(c).lower()
                if lc in ('name','adm','adm no','admno','class','total','mean','rank'):
                    continue
                try:
                    ser = pd.to_numeric(df[c], errors='coerce')
                    if ser.notna().any():
                        sub_cnt += 1
                except Exception:
                    try:
                        vals = df[c].astype(str).dropna().str.strip()
                        if vals.nunique() > 1 and vals.str.len().median() <= 5:
                            sub_cnt += 1
                    except Exception:
                        pass
            subjects_cnt = sub_cnt
    except Exception:
        students_cnt = ''
        subjects_cnt = ''

    date_saved = e.get('saved_at') or e.get('date_saved') or e.get('created_at') or e.get('time') or ''
    if date_saved and isinstance(date_saved, (int, float)):
        try:
            date_saved = datetime.fromtimestamp(float(date_saved)).strftime('%Y-%m-%d %H:%M')
        except Exception:
            date_saved = str(date_saved)

    # Compute director-friendly summary columns: Mean Score, Top Student, Best Performed Subject
    mean_score = ''
    top_student = ''
    best_subject = ''
    try:
        if isinstance(df, pd.DataFrame):
            # detect name column and mask out summary rows (Totals / Mean / Average)
            name_col = None
            for c in df.columns:
                if 'name' in str(c).lower():
                    name_col = c
                    break
            summary_tokens = ['totals', 'total', 'mean', 'average', 'means']
            valid_idx_mask = None
            if name_col:
                try:
                    names = df[name_col].astype(str).str.strip()
                    valid_idx_mask = ~names.str.lower().isin(summary_tokens)
                except Exception:
                    valid_idx_mask = pd.Series([True] * len(df), index=df.index)
            else:
                # no name column; assume all rows are student rows
                valid_idx_mask = pd.Series([True] * len(df), index=df.index)

            df_valid = df[valid_idx_mask]

            # detect numeric subject columns (exclude known non-subject columns)
            numeric_cols = []
            for c in df.columns:
                lc = str(c).lower()
                if lc in ('name', 'adm', 'adm no', 'admno', 'class', 'rank'):
                    continue
                # treat explicit mean/totals columns as non-subject here
                if any(tok in lc for tok in ('total', 'mean', 'average')):
                    continue
                try:
                    ser = pd.to_numeric(df[c], errors='coerce')
                    if ser.notna().any():
                        numeric_cols.append(c)
                except Exception:
                    pass

            # find totals column if present (prefer a column with 'total' in its name)
            totals_col = None
            for c in df.columns:
                if 'total' in str(c).lower():
                    totals_col = c
                    break

            if totals_col and totals_col in df.columns:
                totals = pd.to_numeric(df[totals_col], errors='coerce')
                totals_valid = totals[valid_idx_mask]
            elif numeric_cols:
                totals_all = df[numeric_cols].apply(pd.to_numeric, errors='coerce').sum(axis=1)
                totals_valid = totals_all[valid_idx_mask]
                totals = totals_all
            else:
                totals = None
                totals_valid = None

            # Mean score computed from student rows only
            if totals_valid is not None:
                try:
                    mean_score = f"{float(totals_valid.dropna().mean()):.2f}"
                except Exception:
                    mean_score = ''

            # top student by totals (exclude summary rows)
            try:
                if totals_valid is not None and not totals_valid.dropna().empty:
                    idx = totals_valid.idxmax()
                    if name_col and idx in df.index:
                        top_student = str(df.at[idx, name_col])
                    else:
                        top_student = ''
            except Exception:
                top_student = ''

            # best performed subject = subject column with highest average (computed on student rows)
            try:
                if numeric_cols and not df_valid.empty:
                    col_means = {}
                    for c in numeric_cols:
                        ser = pd.to_numeric(df_valid[c], errors='coerce')
                        if ser.notna().any():
                            col_means[c] = ser.dropna().mean()
                    if col_means:
                        best_subject = max(col_means.items(), key=lambda x: x[1])[0]
            except Exception:
                best_subject = ''
    except Exception:
        mean_score = ''
        top_student = ''
        best_subject = ''

    rows.append({
        'Exam': exam_name,
        'Date Saved': date_saved,
        'Class': _extract_class_field(e) or e.get('class_name') or '',
        'Students': students_cnt,
        'Subjects': subjects_cnt,
        'Mean Score': mean_score,
        'Top Student': top_student,
        'Best Performed Subject': best_subject
    })

# Display table and stop (no cards)
try:
    df_out = pd.DataFrame(rows)
    # ensure columns order and presence match Director's requirements
    desired_cols = ['Exam', 'Date Saved', 'Class', 'Students', 'Subjects', 'Mean Score', 'Top Student', 'Best Performed Subject']
    for c in desired_cols:
        if c not in df_out.columns:
            df_out[c] = ''
    df_out = df_out[desired_cols]
    # replace empty values with 'N/A' for clarity
    df_out[['Mean Score', 'Top Student', 'Best Performed Subject']] = df_out[['Mean Score', 'Top Student', 'Best Performed Subject']].replace(['', None], 'N/A')
    st.dataframe(df_out, use_container_width=True)
except Exception:
    st.write(rows)

st.caption('Only the saved-exams table is shown here for Director review. Detailed tiles/controls have been removed to keep the view concise.')

# --- Manage Saved Exams (match Saved Exams page layout) ---
st.markdown('<div class="section-header">Manage Saved Exams</div>', unsafe_allow_html=True)

# Helper: normalize class names (same logic as saved_exams page)
def normalize_class_name(cls_raw: str) -> str:
    if not cls_raw:
        return "Unknown"
    class_str = str(cls_raw).strip().lower()
    import re
    class_str = re.sub(r'[^a-z0-9]+', ' ', class_str)
    class_str = re.sub(r'\s+', ' ', class_str).strip()
    number_words = {
        'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5',
        'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10',
        'eleven': '11', 'twelve': '12'
    }
    for word, digit in number_words.items():
        class_str = re.sub(rf'\b{word}\b', digit, class_str)
    m = re.search(r'(grade|form)\s*([0-9]{1,2})', class_str)
    if m:
        return f"Grade {m.group(2)}"
    m2 = re.search(r'\b([0-9]{1,2})\b', class_str)
    if m2:
        return f"Grade {m2.group(1)}"
    return class_str.title()

# Utility to load single exam from disk (used for preview/rebuild)
def load_exam_from_disk_local(exam_id):
    try:
        # Use storage adapter (S3-aware) to load exam artifacts
        data_key = os.path.join(str(exam_id), 'data.pkl')
        raw_key = os.path.join(str(exam_id), 'raw_data.pkl')
        cfg_key = os.path.join(str(exam_id), 'config.json')

        exam_data = None
        exam_raw = None
        cfg = {}

        try:
            if storage.exists(data_key):
                exam_data = storage.read_pickle(data_key)
        except Exception:
            exam_data = None

        try:
            if storage.exists(raw_key):
                exam_raw = storage.read_pickle(raw_key)
        except Exception:
            exam_raw = None

        try:
            cfg = storage.read_json(cfg_key) or {}
        except Exception:
            cfg = {}

        return exam_data, exam_raw, cfg
    except Exception:
        return None, None, {}

def delete_exam_from_disk_local(exam_id):
    try:
        # Remove all objects under the exam prefix via storage adapter
        try:
            objs = storage.list_objects(prefix=str(exam_id))
            for o in objs:
                try:
                    storage.delete(o)
                except Exception:
                    pass
        except Exception:
            pass

        # Update central metadata via storage adapter
        try:
            try:
                all_md = storage.read_json(META_PATH) or {}
            except Exception:
                all_md = storage.read_json('exams_metadata.json') or {}
            all_md.pop(exam_id, None)
            try:
                storage.write_json(META_PATH, all_md)
            except Exception:
                storage.write_json('exams_metadata.json', all_md)
        except Exception:
            pass

        return True
    except Exception:
        return False


# Helper: compute mean totals per stream/arm/section when available
def compute_stream_means_from_df(df):
    try:
        if not isinstance(df, pd.DataFrame):
            return {}

        # detect name column and exclude summary rows
        name_col = next((c for c in df.columns if 'name' in str(c).lower()), None)
        summary_tokens = ['totals', 'total', 'mean', 'average', 'means']
        if name_col:
            try:
                names = df[name_col].astype(str).str.strip()
                mask = ~names.str.lower().isin(summary_tokens)
            except Exception:
                mask = pd.Series([True] * len(df), index=df.index)
        else:
            mask = pd.Series([True] * len(df), index=df.index)

        df_valid = df[mask]

        # detect numeric subject columns (exclude known non-subjects)
        numeric_cols = []
        for c in df.columns:
            lc = str(c).lower()
            if lc in ('name', 'adm', 'adm no', 'admno', 'class', 'rank'):
                continue
            if any(tok in lc for tok in ('total', 'mean', 'average')):
                continue
            try:
                ser = pd.to_numeric(df[c], errors='coerce')
                if ser.notna().any():
                    numeric_cols.append(c)
            except Exception:
                pass

        if not numeric_cols:
            return {}

        # compute per-row totals
        totals = df[numeric_cols].apply(pd.to_numeric, errors='coerce').sum(axis=1)
        df_copy = df.copy()
        df_copy['__totals__'] = totals

        # detect stream/arm/section column candidates
        stream_col = None
        # prefer explicit stream-like column names if present
        for cand in ('stream', 'arm', 'section', 'stream_name'):
            for c in df.columns:
                if cand == str(c).lower():
                    stream_col = c
                    break
            if stream_col:
                break

        # fallback: pick a short-text categorical column with small unique count.
        # Include 'Class' as a candidate because many sheets store "9W"/"9E" there.
        if stream_col is None:
            for c in df.columns:
                lc = str(c).lower()
                if lc in ('name', 'adm', 'adm no', 'admno', 'rank'):
                    continue
                if c in numeric_cols:
                    continue
                try:
                    vals = df[c].dropna().astype(str).str.strip()
                    nunq = vals.nunique()
                    if 1 < nunq <= max(2, min(50, int(len(df) / 2))):
                        # prefer relatively short labels (like '9W', 'W', 'East')
                        median_len = int(vals.str.len().median() or 0)
                        contains_letter = vals.str.contains(r'[A-Za-z]').any()
                        # Accept if labels contain letters (streams usually do) and are short-ish
                        if contains_letter and median_len <= 8:
                            stream_col = c
                            break
                except Exception:
                    continue

        if stream_col is None:
            return {}

        # group by stream and compute mean of totals (student rows only)
        try:
            grp = df_copy.loc[mask].groupby(stream_col)['__totals__'].mean().dropna()
            # format to plain dict
            return {str(k): float(v) for k, v in grp.items()}
        except Exception:
            return {}
    except Exception:
        return {}


# --- Teacher ranking helpers (local, lightweight copy of teacher_analysis logic)
def detect_stream_column_local(df):
    hints = ['stream', 'arm', 'stream_code', 'arm_code', 'class_stream', 'stream_name', 'section', 'class']
    for c in df.columns:
        lc = str(c).lower()
        if any(h in lc for h in hints):
            try:
                vals = df[c].astype(str).dropna().str.strip()
                if vals.empty:
                    continue
                uniq = vals.drop_duplicates()
                if len(uniq) <= 1:
                    continue
                if uniq.str.len().median() <= 8 and len(uniq) <= max(100, len(df) // 2):
                    ser_num = pd.to_numeric(df[c], errors='coerce')
                    if ser_num.notna().sum() / max(1, len(df)) > 0.5:
                        continue
                    return c
            except Exception:
                return c
    # fallback: look for a short categorical column
    for c in df.columns:
        try:
            vals = df[c].astype(str).dropna().str.strip()
        except Exception:
            continue
        if vals.empty:
            continue
        try:
            ser_num = pd.to_numeric(df[c], errors='coerce')
            if ser_num.notna().sum() / max(1, len(df)) > 0.5:
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
        if n > 0 and (pattern.sum() / n) > 0.05 and len(uniq) <= 200:
            return c
    return None


def candidate_subject_columns_local(df, stream_col=None):
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


def compute_teacher_ranking_for_exam(eid, df):
    # load assignments mapping (storage-aware)
    try:
        assignments = storage.read_json('ta_assignments.json') or {}
    except Exception:
        assignments = {}

    stream_col = detect_stream_column_local(df)
    subj_cols = candidate_subject_columns_local(df, stream_col=stream_col)

    teacher_vals = {}
    teacher_subjects = {}

    # iterate streams (or single group '')
    streams = []
    if stream_col:
        raw_vals = df[stream_col].dropna().unique()
        for s in raw_vals:
            ss = str(s).strip()
            if not re.search(r'[A-Za-z]', ss):
                continue
            streams.append(s)
        if len(streams) < 1:
            streams = ['']
    else:
        streams = ['']

    for s in streams:
        mask = (df[stream_col].astype(str).str.strip() == str(s).strip()) if stream_col else pd.Series(True, index=df.index)
        n_students = int(mask.sum()) if mask is not None else len(df)
        assign_map = {}
        try:
            assign_map = assignments.get(str(eid), {}).get(str(s), {}) if isinstance(assignments, dict) else {}
        except Exception:
            assign_map = {}
        for subj in subj_cols:
            try:
                teacher = assign_map.get(subj, '') if isinstance(assign_map, dict) else ''
                if not teacher:
                    continue
                sraw = pd.to_numeric(df.loc[mask, subj], errors='coerce')
                out_of = 100.0
                percent = (sraw.fillna(0.0) / float(out_of)) * 100.0
                if percent.empty:
                    continue
                mean_percent = float(percent.mean())
                teacher_vals.setdefault(teacher, []).append(mean_percent)
                teacher_subjects.setdefault(teacher, set()).add(subj)
            except Exception:
                continue

    # Build DataFrame
    rows = []
    for t, vals in teacher_vals.items():
        try:
            cnt = len(vals)
            ssum = round(sum(vals),2)
            avg = round(sum(vals)/cnt,2) if cnt>0 else 0.0
            subs = ', '.join(sorted(teacher_subjects.get(t, [])))
            rows.append({'Teacher': t, 'Count': cnt, 'SumMean': ssum, 'AvgMean': avg, 'Subjects': subs})
        except Exception:
            continue
    if not rows:
        return pd.DataFrame(columns=['Teacher','Count','SumMean','AvgMean','Subjects'])
    df_out = pd.DataFrame(rows).sort_values('AvgMean', ascending=False)
    return df_out

# Group exams by year and normalized class
grouped = {}
class_display_map = {}
for e in saved_exams:
    # derive year from saved date if present
    date_saved = e.get('date_saved') or e.get('saved_at') or ''
    if isinstance(date_saved, str) and '-' in date_saved:
        year = date_saved.split('-')[0]
    else:
        year = e.get('year') or 'Unknown'
    cls_raw = e.get('class') or e.get('class_name') or e.get('grade') or e.get('grade_name') or e.get('klass') or 'Unspecified'
    cls_norm = normalize_class_name(cls_raw)
    class_display_map[cls_norm] = cls_norm
    grouped.setdefault(year, {}).setdefault(cls_norm, []).append(e)

# Render grouped structure using the same expanders and actions as Saved Exams page
for year in sorted(grouped.keys(), reverse=True, key=lambda x: (x == 'Unknown', x)):
    with st.expander(f"📅 {year}", expanded=False):
        for cls_norm in sorted(grouped[year].keys(), key=lambda x: (x == 'Unspecified', x)):
            cls_display = class_display_map.get(cls_norm, cls_norm)
            with st.expander(f"🏷️ Class: {cls_display}"):
                exams_in_group = grouped[year][cls_norm]
                for exam in exams_in_group:
                    exam_id = exam.get('exam_id')
                    exam_name = exam.get('exam_name') or 'Unnamed Exam'
                    with st.expander(f"🗂️ {exam_name}"):
                        m1, m2, m3 = st.columns(3)
                        with m1:
                            st.write(f"Date Saved: {exam.get('date_saved') or exam.get('saved_at','N/A')}")
                            # attempt to compute per-stream mean scores and render alongside class
                            try:
                                ddf_local = None
                                try:
                                    ddf_local, _, _ = load_exam_from_disk_local(exam_id)
                                except Exception:
                                    ddf_local = None

                                class_display = exam.get('class_name') or exam.get('class') or ''
                                stream_means = {}
                                if isinstance(ddf_local, pd.DataFrame):
                                    stream_means = compute_stream_means_from_df(ddf_local)

                                # Only show the class label here; per-stream means are shown near the preview control below
                                st.write(f"Class: {class_display}")
                            except Exception:
                                st.write(f"Class: {exam.get('class_name') or exam.get('class') or ''}")
                        with m2:
                            # compute counts: try metadata fields then disk
                            students = exam.get('total_students') or exam.get('students') or ''
                            subjects = exam.get('num_subjects') or exam.get('subjects') or ''
                            # fallback to reading pickles on disk if missing
                            if not students or not subjects:
                                try:
                                    ddf, rddf, cfg = load_exam_from_disk_local(exam_id)
                                    if students in (None, '', 0) and isinstance(ddf, pd.DataFrame):
                                        # detect name col
                                        name_col = None
                                        for c in ddf.columns:
                                            if 'name' in str(c).lower():
                                                name_col = c; break
                                        if name_col:
                                            names = ddf[name_col].astype(str).str.strip()
                                            mask = ~names.str.lower().isin(['totals','total','mean','average','means'])
                                            students = int(names[mask].dropna().nunique())
                                        else:
                                            students = len(ddf)
                                    if subjects in (None, '', 0) and isinstance(ddf, pd.DataFrame):
                                        sub_cnt = 0
                                        for c in ddf.columns:
                                            lc = str(c).lower()
                                            if lc in ('name','adm','adm no','admno','class','total','mean','rank'):
                                                continue
                                            try:
                                                ser = pd.to_numeric(ddf[c], errors='coerce')
                                                if ser.notna().any():
                                                    sub_cnt += 1
                                            except Exception:
                                                try:
                                                    vals = ddf[c].astype(str).dropna().str.strip()
                                                    if vals.nunique() > 1 and vals.str.len().median() <= 5:
                                                        sub_cnt += 1
                                                except Exception:
                                                    pass
                                        subjects = sub_cnt
                                except Exception:
                                    pass
                            st.write(f"Students: {students}")
                            st.write(f"Subjects: {subjects}")
                        with m3:
                            cfg = {}
                            try:
                                _, _, cfg = load_exam_from_disk_local(exam_id)
                            except Exception:
                                cfg = {}
                            grading_on = cfg.get('grading_enabled', False)
                            rank_basis = cfg.get('ranking_basis', 'Totals')
                            st.write(f"Grading: {'On' if grading_on else 'Off'}")
                            st.write(f"Rank by: {rank_basis}")

                        # Preview checkbox and actions (Open/Delete/Rebuild) matching Saved Exams page behavior
                        # Show per-stream means near the preview control for quick glance
                        try:
                            _df_for_preview, _raw_for_preview, _ = load_exam_from_disk_local(exam_id)
                            _stream_means_preview = compute_stream_means_from_df(_df_for_preview) if _df_for_preview is not None else {}
                        except Exception:
                            _stream_means_preview = {}

                        if _stream_means_preview:
                            # try to infer grade number for nicer labels and show each stream mean on its own colored line
                            import re
                            grade_num = ''
                            try:
                                cls_disp_preview = exam.get('class_name') or exam.get('class') or ''
                                m = re.search(r"(\d{1,2})", str(cls_disp_preview))
                                if m:
                                    grade_num = m.group(1)
                            except Exception:
                                grade_num = ''

                            try:
                                vals_list = [float(v) for v in _stream_means_preview.values()]
                                max_val = max(vals_list) if vals_list else None
                                min_val = min(vals_list) if vals_list else None
                            except Exception:
                                max_val = None
                                min_val = None

                            st.write('Stream means:')
                            for k, v in sorted(_stream_means_preview.items(), key=lambda x: str(x[0])):
                                lbl = str(k)
                                if grade_num and not any(ch.isdigit() for ch in lbl):
                                    if not lbl.startswith(str(grade_num)):
                                        lbl = f"{grade_num}{lbl}"
                                try:
                                    fv = float(v)
                                except Exception:
                                    fv = None
                                color = '#374151'
                                if fv is not None and max_val is not None and fv == max_val:
                                    color = '#16a34a'
                                if fv is not None and min_val is not None and fv == min_val:
                                    color = '#dc2626'
                                try:
                                    if fv is not None:
                                        st.markdown(f"<div style='color:{color}; font-weight:700'>{lbl}: {fv:.2f}</div>", unsafe_allow_html=True)
                                    else:
                                        st.markdown(f"<div style='color:{color}; font-weight:700'>{lbl}: {v}</div>", unsafe_allow_html=True)
                                except Exception:
                                    if fv is not None:
                                        st.write(f"{lbl}: {fv:.2f}")
                                    else:
                                        st.write(f"{lbl}: {v}")

                        if st.checkbox(f"Preview first 10 rows", key=f"prev_manage_{exam_id}"):
                            data_df = None
                            try:
                                # try to load from disk
                                data_df, raw_df, cfg = load_exam_from_disk_local(exam_id)
                            except Exception:
                                data_df = None
                            if isinstance(data_df, pd.DataFrame):
                                st.dataframe(data_df.head(10), use_container_width=True)
                            else:
                                st.info("No data available for this exam.")
                                exam_dir = os.path.join(STORAGE_DIR, exam_id)
                                files = []
                                try:
                                    if os.path.exists(exam_dir):
                                        files = os.listdir(exam_dir)
                                except Exception:
                                    files = []
                                raw_exists = 'raw_data.pkl' in files
                                data_exists = 'data.pkl' in files
                                st.write(f"Data file present: {data_exists}")
                                st.write(f"Raw file present: {raw_exists}")
                                if files:
                                    st.write('Files in exam folder:')
                                    for f in files:
                                        st.write('-', f)
                                else:
                                    st.write('No files found in the exam folder.')

                        # Open / Delete actions removed per request — directors can view the full marksheet instead.

                        # If raw exists but generated data missing, offer rebuild
                        try:
                            ddf, rddf, _ = load_exam_from_disk_local(exam_id)
                        except Exception:
                            ddf, rddf = None, None
                        if (ddf is None) and (rddf is not None):
                            if st.button("🔧 Rebuild from raw & Generate", key=f"rebuild_{exam_id}"):
                                st.session_state['selected_saved_exam_id'] = exam_id
                                st.session_state['rebuild_from_raw'] = True
                                st.session_state['view'] = 'analysis'
                                st.success('Rebuilding from raw data and opening analysis...')

                        # Show Teacher Ranking for this exam (director view)
                        if st.button('Show Teacher Ranking', key=f'teacher_rank_{exam_id}'):
                            try:
                                df_local, _, _ = load_exam_from_disk_local(exam_id)
                            except Exception:
                                df_local = None
                            if isinstance(df_local, pd.DataFrame):
                                tr_df = compute_teacher_ranking_for_exam(exam_id, df_local)
                                if tr_df.empty:
                                    st.info('No teacher assignments detected for this exam.')
                                else:
                                    st.markdown('### Teacher ranking')
                                    st.dataframe(tr_df.reset_index(drop=True), use_container_width=True)
                                    try:
                                        csvb = tr_df.to_csv(index=False).encode('utf-8')
                                        st.download_button('Download teacher ranking CSV', data=csvb, file_name=f'teacher_ranking_{exam_id}.csv', mime='text/csv')
                                    except Exception:
                                        pass
                            else:
                                st.info('No marksheet available to compute teacher ranking.')

                        # View full marksheet inline and allow CSV download
                        if st.button("View Full Marksheet", key=f"view_full_{exam_id}"):
                            df_full = None
                            # prefer generated data, fall back to raw
                            try:
                                df_full, raw_df, _ = load_exam_from_disk_local(exam_id)
                                if df_full is None and raw_df is not None:
                                    df_full = raw_df
                            except Exception:
                                df_full = None

                            if isinstance(df_full, pd.DataFrame):
                                with st.expander(f"Full Marksheet — {exam_name}", expanded=True):
                                    st.dataframe(df_full, use_container_width=True)
                                    try:
                                        csv_bytes = df_full.to_csv(index=False).encode('utf-8')
                                        st.download_button(label='Download CSV', data=csv_bytes, file_name=f"{exam_id or exam_name}.csv", mime='text/csv')
                                    except Exception:
                                        st.info('Unable to prepare CSV download for this marksheet.')
                            else:
                                st.info('Full marksheet not available on disk for this exam.')

# End Manage Saved Exams

# Note: navigation is handled immediately in the button callback by setting `current_page`.
# No explicit rerun call is required (and some Streamlit versions don't expose experimental_rerun).

# End of Manage Saved Exams section

# --- Assignment analytics (per-exam-kind teacher summaries and combined rankings)
def _compute_assignment_analytics_local(selected_eids, exams_meta_local, assignments):
    """Compute analytics using the explicit subject->teacher assignments stored in assignments.
    This function trusts the assignment keys (subject names) and matches them to dataframe
    columns using a normalization mapping so that assigned subjects are used even if
    df column formatting differs slightly.
    """
    # Build mapping exam kind -> list of eids
    kind_map = {}
    for eid in selected_eids:
        meta = next((x for x in exams_meta_local if (x.get('exam_id') == eid or x.get('id') == eid)), {}) or {}
        name = meta.get('exam_name') or ''
        kind = _exam_kind_from_label_local(name)
        kind_map.setdefault(kind, []).append(eid)

    combined_teacher_rows = []
    combined_subject_rows = []
    combined_unassigned = {}

    def _norm(s):
        try:
            return re.sub(r'[^A-Za-z0-9]', '', str(s)).upper().strip()
        except Exception:
            return str(s).upper()

    for kind, eids in kind_map.items():
        teacher_vals = {}
        subject_vals = {}
        teacher_subjects = {}
        for eid in eids:
            try:
                df, _, _ = load_exam_from_disk_local(eid)
            except Exception:
                df = None
            if df is None or not isinstance(df, pd.DataFrame) or df.empty:
                # nothing to compute for this exam
                continue

            # build normalized column map for subject lookup
            norm_to_col = { _norm(c): c for c in df.columns }

            # iterate assignment entries for this exam
            assign_for_exam = assignments.get(str(eid), {}) if isinstance(assignments, dict) else {}
            # if there are no assignment entries for this exam, mark all subjects as unassigned
            if not assign_for_exam:
                continue

            for stream_key, subj_map in assign_for_exam.items():
                # build mask for this stream (if stream_key is '' or 'All' treat as all students)
                try:
                    if stream_key is None or str(stream_key).strip() == '':
                        mask = pd.Series(True, index=df.index)
                    else:
                        # try matching stream column by detecting one
                        stream_col = detect_stream_column_local(df)
                        if stream_col and stream_key is not None:
                            mask = df[stream_col].astype(str).str.strip() == str(stream_key).strip()
                        else:
                            mask = pd.Series(True, index=df.index)
                except Exception:
                    mask = pd.Series(True, index=df.index)

                if not isinstance(subj_map, dict):
                    continue

                for assigned_subj, teacher in subj_map.items():
                    try:
                        if not teacher:
                            combined_unassigned.setdefault(assigned_subj, set()).add(str(stream_key) or 'All students')
                            continue
                        # find matching dataframe column
                        col = None
                        norm_assigned = _norm(assigned_subj)
                        if norm_assigned in norm_to_col:
                            col = norm_to_col[norm_assigned]
                        else:
                            # try fuzzy fallback: substring match of normalized names
                            for k, v in norm_to_col.items():
                                if norm_assigned == k or norm_assigned in k or k in norm_assigned:
                                    col = v
                                    break
                        if col is None or col not in df.columns:
                            # cannot compute mean for this assigned subject; record as unassigned for visibility
                            combined_unassigned.setdefault(assigned_subj, set()).add(str(stream_key) or 'All students')
                            continue

                        ser = pd.to_numeric(df.loc[mask, col], errors='coerce')
                        if ser.dropna().empty:
                            combined_unassigned.setdefault(assigned_subj, set()).add(str(stream_key) or 'All students')
                            continue
                        # percent assuming out_of 100 as used elsewhere
                        percent = (ser.fillna(0.0) / 100.0) * 100.0
                        mean_percent = float(percent.mean())
                        teacher_vals.setdefault(teacher, []).append(mean_percent)
                        # record per-teacher subject -> streams mapping
                        teacher_subjects.setdefault(teacher, {}).setdefault(assigned_subj, set()).add(str(stream_key) or 'All students')
                        subject_vals.setdefault(assigned_subj, []).append(mean_percent)
                    except Exception:
                        continue

        for t, vals in teacher_vals.items():
            # format subjects with stream lists e.g. ENG (6W,6E)
            subj_map = teacher_subjects.get(t, {}) if isinstance(teacher_subjects.get(t, {}), dict) else {}
            parts = []
            for sname, streams in subj_map.items():
                try:
                    stream_txt = ','.join(sorted(set([str(x) for x in streams if x is not None and str(x).strip()!=''])))
                except Exception:
                    stream_txt = ''
                if stream_txt:
                    parts.append(f"{sname} ({stream_txt})")
                else:
                    parts.append(f"{sname}")
            subs = ', '.join(parts)
            combined_teacher_rows.append({'ExamKind': kind, 'Teacher': t, 'Count': len(vals), 'SumMean': round(sum(vals),2), 'AvgMean': round(sum(vals)/len(vals),2) if vals else 0.0, 'Subjects': subs})
        for sname, vals in subject_vals.items():
            combined_subject_rows.append({'ExamKind': kind, 'Subject': sname, 'Count': len(vals), 'SumMean': round(sum(vals),2), 'AvgMean': round(sum(vals)/len(vals),2) if vals else 0.0})

    df_comb_teacher = pd.DataFrame(combined_teacher_rows) if combined_teacher_rows else pd.DataFrame(columns=['ExamKind','Teacher','Count','SumMean','AvgMean','Subjects'])
    df_comb_subject = pd.DataFrame(combined_subject_rows) if combined_subject_rows else pd.DataFrame(columns=['ExamKind','Subject','Count','SumMean','AvgMean'])
    combined_unassigned = {k: sorted(list(v)) for k,v in combined_unassigned.items()}
    return df_comb_teacher, df_comb_subject, combined_unassigned


# Compute analytics for the currently filtered exams — prefer assignment-backed exams when available
try:
    selected_ids_local = [m.get('exam_id') for m in filtered if m.get('exam_id')]
except Exception:
    selected_ids_local = []

# Load assignments from the same source used by Teacher Analysis (storage-aware)
try:
    assignments = storage.read_json('ta_assignments.json') or {}
except Exception:
    assignments = {}

# If no filtered exams have assignments but assignments exist for other exams,
# include those assignment-backed exam ids so analytics reflect Teacher Analysis data.
assignment_eids = [str(k) for k in list(assignments.keys()) if k]
if assignment_eids:
    # include union of filtered and assignment-backed ids
    combined_ids = set(selected_ids_local or []) | set(assignment_eids)
    # prefer showing only the assignment-backed set if the filtered set is empty
    if not selected_ids_local:
        selected_ids_local = sorted(list(set(assignment_eids)))
    else:
        selected_ids_local = sorted(list(combined_ids))

st.markdown('---')
st.markdown('### Assignment analytics (Per-exam-kind teacher summaries)')
if not selected_ids_local:
    st.info('No exams available to compute assignment analytics for the current filters.')
else:
    # additional table-level filters (Year / Term / Exam Kind) for the teacher summaries
    col_f1, col_f2, col_f3 = st.columns([1,1,2])
    # reuse global lists 'years', 'terms', 'kinds' defined earlier
    try:
        sel_year_t = col_f1.selectbox('Year (table)', options=['All'] + years, index=0, key='dl_year_tbl')
    except Exception:
        sel_year_t = col_f1.selectbox('Year (table)', options=['All'] + (years if 'years' in globals() else []), index=0, key='dl_year_tbl')
    try:
        sel_term_t = col_f2.selectbox('Term (table)', options=['All'] + terms, index=0, key='dl_term_tbl')
    except Exception:
        sel_term_t = col_f2.selectbox('Term (table)', options=['All'] + (terms if 'terms' in globals() else []), index=0, key='dl_term_tbl')
    try:
        sel_kind_t = col_f3.selectbox('Exam Kind (table)', options=['All'] + kinds, index=0, key='dl_kind_tbl')
    except Exception:
        sel_kind_t = col_f3.selectbox('Exam Kind (table)', options=['All'] + (kinds if 'kinds' in globals() else []), index=0, key='dl_kind_tbl')

    # determine which exam ids to include according to these table filters
    def _meta_matches(meta):
        if not meta:
            return False
        if sel_year_t != 'All':
            y = meta.get('year') or ''
            if not y:
                ds = meta.get('date_saved') or meta.get('saved_at') or ''
                if isinstance(ds, str) and '-' in ds:
                    y = ds.split('-')[0]
            if str(y) != str(sel_year_t):
                return False
        if sel_term_t != 'All':
            if _normalize_term_label_local(meta.get('term') or '') != sel_term_t:
                return False
        if sel_kind_t != 'All':
            if _exam_kind_from_label_local(meta.get('exam_name') or '') != sel_kind_t:
                return False
        return True

    # build final list of exam ids for the table
    final_ids = [eid for eid in selected_ids_local if any((m.get('exam_id') == eid or m.get('id') == eid) and _meta_matches(m) for m in saved_exams)]

    # load teachers registry to get classification (Upper/Lower) mapping
    class_map_local = {}
    try:
        tdata = storage.read_json('ta_teachers.json') or {}
        class_map_local = tdata.get('class_map', {}) if isinstance(tdata, dict) else {}
    except Exception:
        class_map_local = {}

    # caching / persistence: compute a cache key based on final_ids, filters and assignments content hash
    try:
        assign_mtime = hashlib.sha1(json.dumps(assignments or {}, sort_keys=True).encode()).hexdigest()
    except Exception:
        assign_mtime = ''
    cache_obj = {'ids': sorted(final_ids), 'year': sel_year_t, 'term': sel_term_t, 'kind': sel_kind_t, 'assign_mtime': assign_mtime}
    try:
        cache_key = hashlib.sha1(json.dumps(cache_obj, sort_keys=True).encode()).hexdigest()
    except Exception:
        cache_key = str(abs(hash(str(cache_obj))))
    # Use storage-backed cache path (S3-aware). Persist snapshots under 'exports/<filename>'
    cache_path = os.path.join('exports', f'director_teacher_summaries_{cache_key}.csv')

    # if a cached snapshot exists in storage, load it (persistence across refreshes)
    df_teach = None
    try:
        if storage.exists(cache_path):
            try:
                data_bytes = storage.read_bytes(cache_path)
                df_teach = pd.read_csv(io.BytesIO(data_bytes))
            except Exception:
                df_teach = None
    except Exception:
        df_teach = None

    if df_teach is None:
        df_teach, df_subj, unassigned = _compute_assignment_analytics_local(final_ids, saved_exams, assignments)
        # add Group column and reorder columns (Teacher first)
        try:
            if not df_teach.empty:
                df_teach['Group'] = df_teach['Teacher'].apply(lambda x: class_map_local.get(x, ''))
                # ensure desired order: Teacher, Group, ExamKind, Count, SumMean, AvgMean, Subjects
                cols_order = ['Teacher', 'Group', 'ExamKind', 'Count', 'SumMean', 'AvgMean', 'Subjects']
                for c in cols_order:
                    if c not in df_teach.columns:
                        df_teach[c] = ''
                df_teach = df_teach[cols_order]
        except Exception:
            pass
        # persist snapshot to cache
        try:
            if df_teach is not None:
                try:
                    storage.write_bytes(cache_path, df_teach.to_csv(index=False).encode('utf-8'))
                except Exception:
                    # fallback: attempt local write if storage not available
                    try:
                        cache_dir = os.path.join(STORAGE_DIR, 'exports')
                        os.makedirs(cache_dir, exist_ok=True)
                        cache_file = os.path.join(cache_dir, f'director_teacher_summaries_{cache_key}.csv')
                        df_teach.to_csv(cache_file, index=False)
                    except Exception:
                        pass
        except Exception:
            pass
    if df_teach is None or (hasattr(df_teach, 'empty') and df_teach.empty):
        st.info('No teacher assignment summaries available for the selected exams')
        # As a helpful hint, if assignments.json contains entries, point the director to those exams
        if assignment_eids:
            st.info('Assignments exist for other saved exams; try removing filters or use the Teacher Analysis page to manage assignments.')
    else:
        # Ensure AvgMean numeric and sort descending for ranking
        try:
            df_teach['AvgMean'] = pd.to_numeric(df_teach['AvgMean'], errors='coerce')
        except Exception:
            pass
        try:
            df_teach = df_teach.sort_values('AvgMean', ascending=False).reset_index(drop=True)
        except Exception:
            pass

        # Remove SumMean column (not required) and format AvgMean to 2 decimals for display
        try:
            if 'SumMean' in df_teach.columns:
                df_teach = df_teach.drop(columns=['SumMean'])
        except Exception:
            pass

        try:
            df_teach['AvgMean'] = df_teach['AvgMean'].apply(lambda x: round(float(x), 2) if pd.notna(x) else x)
        except Exception:
            pass

        st.markdown('Per-exam-kind teacher summaries (ranked by AvgMean — highest to lowest)')
        # Color-code Group column when present
        try:
            def _group_color(val):
                try:
                    v = str(val).strip()
                    if not v:
                        return ''
                    if v.lower() == 'upper':
                        return 'color: #16a34a; font-weight:700'
                    if v.lower() == 'lower':
                        return 'color: #0ea5e9; font-weight:700'
                    return 'color: #6b7280; font-weight:700'
                except Exception:
                    return ''
            # Prepare a display copy where AvgMean is formatted to 2 decimal places
            try:
                display_df = df_teach.copy()
                display_df['AvgMean'] = display_df['AvgMean'].apply(lambda x: f"{float(x):.2f}" if pd.notna(x) else '')
            except Exception:
                display_df = df_teach.copy()

            # Color-code Group column when present on the display copy
            try:
                if 'Group' in display_df.columns:
                    sty = display_df.style.applymap(lambda x: _group_color(x), subset=['Group'])
                else:
                    sty = None
                # display styled or plain dataframe
                if sty is not None:
                    st.dataframe(sty, use_container_width=True)
                else:
                    st.dataframe(display_df.reset_index(drop=True), use_container_width=True)
            except Exception:
                st.dataframe(display_df.reset_index(drop=True), use_container_width=True)
        except Exception:
            st.dataframe(df_teach.reset_index(drop=True), use_container_width=True)

        # Prepare downloadable CSV
        try:
            csvb = df_teach.to_csv(index=False).encode('utf-8')
            st.download_button('Download teacher summaries CSV', csvb, file_name='teacher_summaries.csv', mime='text/csv')
        except Exception:
            pass

        # Prepare and offer PDF download using existing PDF helper
        try:
            # Build a PDF-friendly dataframe (format numeric columns)
            pdf_df = df_teach.copy()
            # ensure SumMean removed
            try:
                if 'SumMean' in pdf_df.columns:
                    pdf_df = pdf_df.drop(columns=['SumMean'])
            except Exception:
                pass
            for col in pdf_df.columns:
                if pd.api.types.is_numeric_dtype(pdf_df[col]):
                    if 'Mean' in str(col):
                        pdf_df[col] = pdf_df[col].apply(lambda x: format(x, '.2f') if pd.notna(x) else '')
                    else:
                        pdf_df[col] = pdf_df[col].apply(lambda x: format(x, '.0f') if pd.notna(x) else '')
            title_text = f"Teacher summaries — Year: {sel_year_t}; Term: {sel_term_t}; Kind: {sel_kind_t}"
            pdf_bytes = generate_teacher_table_bytes(pdf_df, title=title_text)
            st.download_button('Download teacher summaries PDF', pdf_bytes, file_name='teacher_summaries.pdf', mime='application/pdf')
        except Exception:
            pass

    # Per-exam-kind subject summaries and unassigned-subject lists removed per director request

st.markdown('---')
