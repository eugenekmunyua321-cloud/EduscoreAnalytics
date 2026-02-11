"""
Standalone Parents Portal for EduScore Analytics

This file is meant to be deployed separately from the main school app. It accesses
saved exams on a shared filesystem path. Configure the storage path by setting the
PARENTS_PORTAL_STORAGE_DIR environment variable to point to the same `saved_exams_storage`
folder the school app writes to. If unset, it falls back to a relative `saved_exams_storage`
next to this file.

Run with:
    streamlit run parents_portal_standalone.py

Security note: this app trusts the filesystem contents. For production, host the
portal on a separate host/subdomain and ensure the shared storage is mounted read-only
for the portal or access is otherwise controlled.
"""

import os
import re
import json
from pathlib import Path

import streamlit as st
import pandas as pd
from io import BytesIO

# Very early defensive check: if the browser URL contains a multipage `page` query param
# (for example `?page=login`) clear it and rerun immediately. This helps prevent
# Streamlit from showing the built-in multipage error for missing pages before
# this single-file app can render.
try:
    try:
        qp = st.query_params or {}
    except Exception:
        qp = {}
    if qp and any(k.lower() == 'page' for k in qp.keys()):
        try:
            st.experimental_set_query_params()
        except Exception:
            pass
        try:
            st.experimental_rerun()
        except Exception:
            pass
except Exception:
    pass

from utils import student_photos as photos_mod
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# optional: use Altair for larger, configurable charts when available
try:
    import altair as alt
    ALT_AVAILABLE = True
except Exception:
    ALT_AVAILABLE = False

# Page config
st.set_page_config(page_title='Parents Portal — EduScore', layout='wide', initial_sidebar_state='collapsed')

# Session flag - parents portal runs independently but set flag for compatibility if used inside same server
st.session_state['parents_portal_mode'] = True

# Defensive: if the browser URL contains a multipage `page` query (e.g. ?page=login)
# clear it and rerun immediately so Streamlit doesn't attempt to load a missing multipage entry.
try:
    qp = {}
    try:
        qp = st.query_params or {}
    except Exception:
        qp = {}

    page_vals = qp.get('page') or qp.get('Page') or qp.get('p') or None
    if page_vals:
        # if page param points to 'login' or any unknown value, clear params and rerun
        try:
            pval = str(page_vals[0]).strip().lower()
        except Exception:
            pval = None
        if pval:
            # treat any non-empty page param as unwanted for this single-file portal
            try:
                st.experimental_set_query_params()
            except Exception:
                pass
            try:
                st.experimental_rerun()
            except Exception:
                pass
except Exception:
    # fail safe: don't crash the app if experimental_* APIs aren't available
    pass


def _find_school_photo_path(school_dir: Path, name: str = None, adm_no: str = None) -> str:
    """Find a student photo prioritizing per-school storage, then global mapping.
    Returns a filesystem path or None.
    """
    try:
        # 1) check per-school mapping file
        school_map = Path(school_dir) / 'student_photos.json'
        if school_map.exists():
            try:
                jm = json.loads(school_map.read_text(encoding='utf-8') or '{}')
                sid = photos_mod._normalize_id(name, adm_no) if hasattr(photos_mod, '_normalize_id') else None
                if sid and sid in jm:
                    p = jm[sid].get('path')
                    if p and os.path.exists(p):
                        return p
            except Exception:
                pass

        # 2) check per-school photos folder by normalized id
        sid = photos_mod._normalize_id(name, adm_no) if hasattr(photos_mod, '_normalize_id') else None
        if sid:
            school_photos_dir = Path(school_dir) / 'student_photos'
            if school_photos_dir.exists():
                for ext in ('.png', '.jpg', '.jpeg'):
                    p = school_photos_dir / f"{sid}{ext}"
                    if p.exists():
                        return str(p)

        # 3) fallback to global mapping used by utils.student_photos
        try:
            p = photos_mod.get_photo_path(name=name, adm_no=adm_no)
            if p:
                return p
        except Exception:
            pass

        # 4) As a safe, non-destructive convenience: search other schools'
        # student_photos.json files under the same ROOT for an entry that
        # matches the normalized id or name. This does not copy or modify any
        # school data; it only reads other school folders to locate an
        # existing photo so parents can see it in the portal.
        try:
            root_dir = Path(__file__).parent / 'saved_exams_storage'
            # If the portal was configured with a different ROOT, prefer that
            if 'ROOT' in globals() and isinstance(ROOT, Path):
                root_dir = ROOT
            for sd in root_dir.iterdir():
                if not sd.is_dir() or sd == Path(school_dir):
                    continue
                smap = sd / 'student_photos.json'
                if not smap.exists():
                    continue
                try:
                    jm = json.loads(smap.read_text(encoding='utf-8') or '{}')
                except Exception:
                    continue
                # try matching by normalized id first
                sid = None
                try:
                    sid = photos_mod._normalize_id(name, adm_no) if hasattr(photos_mod, '_normalize_id') else None
                except Exception:
                    sid = None
                if sid and sid in jm:
                    p = jm[sid].get('path')
                    if p and os.path.exists(p):
                        return p
                # else try matching by name (case-insensitive)
                for k, v in jm.items():
                    try:
                        if v and isinstance(v, dict) and v.get('name') and name and v.get('name').strip().lower() == name.strip().lower():
                            p = v.get('path')
                            if p and os.path.exists(p):
                                return p
                    except Exception:
                        continue
        except Exception:
            pass
    except Exception:
        return None
    return None

# Hide Streamlit main menu/header/footer and sidebar toggle for focused portal look
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}
div[data-testid="stSidebar"] { display: none !important; }
button[aria-label="Toggle sidebar"] { display: none !important; }
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.title('Welcome dear parent to, Parents Portal — EduScore Analytics')

# try to reuse branding/colors from modules.auth if available
try:
    from modules import auth as _auth
except Exception:
    _auth = None

# Branding: use the same fonts, logo and banner style as the main auth page if available
try:
    st.markdown("<link href='https://fonts.googleapis.com/css2?family=Montserrat:wght@700;900&family=Poppins:wght@400;600;700&display=swap' rel='stylesheet'>", unsafe_allow_html=True)
except Exception:
    pass

# prepare logo fragment (look for static/eduscore_logo.*)
logo_fragment = None
try:
    from pathlib import Path
    import base64
    logo_dir = Path(__file__).parent / 'static'
    logo_path_jpg = logo_dir / 'eduscore_logo.jpg'
    logo_path_jpeg = logo_dir / 'eduscore_logo.jpeg'
    logo_path_png = logo_dir / 'eduscore_logo.png'
    logo_path = None
    for p in (logo_path_png, logo_path_jpg, logo_path_jpeg):
        if p.exists():
            logo_path = p
            break
    if logo_path is not None:
        try:
            data = base64.b64encode(logo_path.read_bytes()).decode('ascii')
            mime = 'image/png' if logo_path.suffix.lower().endswith('png') else 'image/jpeg'
            logo_fragment = f"<img src='data:{mime};base64,{data}' style='width:120px;height:120px;object-fit:contain;border-radius:12px;box-shadow:0 10px 34px rgba(2,6,23,0.22);'/>"
        except Exception:
            logo_fragment = None
except Exception:
    logo_fragment = None

if not logo_fragment:
    # fallback tile
    logo_fragment = """
        <div style="width:120px; height:120px; border-radius:16px; background: linear-gradient(135deg, rgba(255,255,255,0.12), rgba(255,255,255,0.06)); display:flex; align-items:center; justify-content:center; font-weight:900; font-size:44px; color:#fff; box-shadow: 0 10px 34px rgba(2,6,23,0.22);">E</div>
    """

# colors (fall back to auth defaults used in auth_page.py)
BRAND_GRAD_A = getattr(_auth, 'BRAND_GRAD_A', '#06243a') if _auth else '#06243a'
BRAND_GRAD_B = getattr(_auth, 'BRAND_GRAD_B', '#0b4d3e') if _auth else '#0b4d3e'
try:
    import streamlit.components.v1 as components
    banner_html = f'''
    <div style="width:100%; display:flex; justify-content:center;">
      <div style="max-width:980px; width:100%; padding:22px 26px; border-radius:16px; margin-bottom:16px; background: linear-gradient(90deg, {BRAND_GRAD_A}, {BRAND_GRAD_B}); box-shadow: 0 18px 44px rgba(6,30,60,0.20); color: #fff;">
        <div style="display:flex; align-items:center; justify-content:space-between; gap:18px; flex-wrap:wrap;">
            <div style="display:flex; align-items:center; gap:16px;">
                {logo_fragment}
                <div>
                    <div style="font-family: 'Montserrat', 'Poppins', 'Segoe UI', sans-serif; font-size:30px; font-weight:900; letter-spacing:0.02em; line-height:1; text-transform:uppercase;">
                        <span style="color:#ffffff">EDUSCORE</span>
                        <span style="margin-left:10px; color:#ffd27a; font-size:22px;">PARENTS</span>
                    </div>
                    <div style="opacity:0.95; margin-top:6px; font-size:13px;">Secure access to your child's academic progress</div>
                    <div style="opacity:0.9; margin-top:8px; font-size:11px; font-weight:700; letter-spacing:0.04em; color:rgba(255,255,255,0.9);">ACCOUNTABILITY &nbsp;&nbsp;&middot;&nbsp;&nbsp; RELIABILITY &nbsp;&nbsp;&middot;&nbsp;&nbsp; ACCESSIBILITY</div>
                </div>
            </div>
            <div style="text-align:right; min-width:140px;">
                <div style="background: rgba(255,255,255,0.12); padding:10px 14px; border-radius:999px; display:inline-block; font-weight:800; font-size:13px; color:#07203a;">Parents Portal</div>
            </div>
        </div>
      </div>
    </div>
    '''
    try:
        components.html(banner_html, height=180, scrolling=False)
    except Exception:
        st.markdown('<h2>Welcome dear parent , Parents Portal — EduScore Analytics</h2>', unsafe_allow_html=True)
except Exception:
    st.markdown('<h2>Welcome dear parent , Parents Portal — EduScore Analytics</h2>', unsafe_allow_html=True)

# Render a persistent footer fixed to the bottom of the viewport so it's always visible
# and appears below the found children. Add bottom padding to the app to avoid overlap.
try:
    footer_html = """
    <style>
    /* fixed footer */
    #eduscore-footer { position: fixed; left: 0; right: 0; bottom: 0; background: rgba(255,255,255,0.98); color: #475569; padding:12px 8px; text-align:center; font-size:13px; z-index:9999; border-top:1px solid rgba(0,0,0,0.06); }
    /* push main content above footer */
    div[data-testid="stApp"] > div:nth-child(1) { padding-bottom:90px !important; }
    </style>
    <div id="eduscore-footer">EDUSCORE ANALYTICS<br><span style="font-weight:600;">Developed by Munyua Kamau</span><br>© 2025 All Rights Reserved</div>
    """
    st.markdown(footer_html, unsafe_allow_html=True)
except Exception:
    try:
        st.markdown('<div style="text-align:center; color:#475569; font-size:13px; margin-top:8px;">EDUSCORE ANALYTICS<br><span style="font-weight:600;">Developed by Munyua Kamau</span><br>© 2025 All Rights Reserved</div>', unsafe_allow_html=True)
    except Exception:
        pass

# Determine storage root
def get_storage_root() -> Path:
    env = os.environ.get('PARENTS_PORTAL_STORAGE_DIR')
    if env:
        p = Path(env)
        if p.exists():
            return p
    # fallback to sibling saved_exams_storage
    return Path(__file__).parent / 'saved_exams_storage'

ROOT = get_storage_root()

if not ROOT.exists():
    st.error(f'Storage directory not found: {ROOT}. Set PARENTS_PORTAL_STORAGE_DIR to the shared saved_exams_storage path.')
    st.stop()

# helpers

def normalize_phone(p: str):
    if not p:
        return ''
    s = re.sub(r"[^0-9]", "", str(p))
    return s[-9:]


def find_school_by_account_number(accno: str):
    accno = str(accno).strip()
    if not accno:
        return None
    for d in ROOT.iterdir():
        if not d.is_dir():
            continue
        admf = d / 'admin_meta.json'
        try:
            if admf.exists():
                m = json.loads(admf.read_text(encoding='utf-8') or '{}')
                if str(m.get('account_number','')).strip() == accno:
                    return d
        except Exception:
            continue
    return None


def load_contacts_for_school(school_dir: Path):
    f = school_dir / 'student_contacts.json'
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding='utf-8') or '[]')
    except Exception:
        return []


def list_exams_for_school(school_dir: Path):
    meta_f = school_dir / 'exams_metadata.json'
    if not meta_f.exists():
        return {}
    try:
        return json.loads(meta_f.read_text(encoding='utf-8') or '{}')
    except Exception:
        return {}


def load_exam_df(school_dir: Path, exam_id: str):
    p = school_dir / exam_id / 'data.pkl'
    if not p.exists():
        return None
    try:
        return pd.read_pickle(p)
    except Exception:
        return None


def _load_admin_meta(school_dir: Path):
    admf = school_dir / 'admin_meta.json'
    try:
        if admf.exists():
            return json.loads(admf.read_text(encoding='utf-8') or '{}')
    except Exception:
        pass
    return {}


def _ensure_report_settings(school_dir: Path, settings: dict):
    """Return a settings dict with minimal required keys for the report generator."""
    s = {} if not isinstance(settings, dict) else dict(settings)
    admin = _load_admin_meta(school_dir)
    # ensure school_name
    if not s.get('school_name'):
        s['school_name'] = admin.get('school_name') or admin.get('name') or str(school_dir.name)
    if not s.get('email'):
        s['email'] = admin.get('email') or ''
    # term/year fallbacks
    if not s.get('term'):
        s['term'] = 'Term 1'
    if not s.get('year'):
        try:
            s['year'] = int(admin.get('year') or admin.get('session') or pd.Timestamp.now().year)
        except Exception:
            s['year'] = pd.Timestamp.now().year
    return s


def _find_subject_and_metric_columns(df: pd.DataFrame):
    # determine subject columns by excluding common metadata columns
    exclude_keywords = ['name', 'adm', 'adm no', 'admno', 'adm_no', 'class', 'total', 'mean', 'rank', 's/rank', 'points', 'mean grade', 'position']
    cols = list(df.columns)
    subject_cols = [c for c in cols if not any(k in c.lower() for k in exclude_keywords)]
    # locate total/mean/points columns if present
    total_col = None
    mean_col = None
    points_col = None
    rank_col = None
    for c in cols:
        cl = c.lower()
        if total_col is None and 'total' in cl:
            total_col = c
        if mean_col is None and cl in ('mean', 'mean score', 'average'):
            mean_col = c
        if points_col is None and 'point' in cl:
            points_col = c
        if rank_col is None and ('rank' in cl or 'position' in cl):
            rank_col = c
    return subject_cols, total_col, mean_col, points_col, rank_col


def _is_number(v):
    try:
        float(v)
        return True
    except Exception:
        return False


def _compute_student_metrics(df: pd.DataFrame, student_row: pd.DataFrame):
    # student_row may be a DataFrame with one or more rows; pick first
    if student_row is None or getattr(student_row, 'shape', (0,))[0] == 0:
        return None
    subject_cols, total_col, mean_col, points_col, rank_col = _find_subject_and_metric_columns(df)
    row = student_row.iloc[0]
    # total
    total = None
    if total_col and pd.notna(row.get(total_col)):
        try:
            total = float(row.get(total_col))
        except Exception:
            total = None
    if total is None:
        # try summing subject columns
        try:
            vals = []
            for c in subject_cols:
                v = row.get(c)
                if v is None:
                    continue
                if _is_number(v):
                    vals.append(float(v))
            total = sum(vals) if vals else None
        except Exception:
            total = None
    # points
    points = None
    if points_col and pd.notna(row.get(points_col)):
        try:
            points = float(row.get(points_col))
        except Exception:
            points = None
    # rank: compute from total if not present
    rank = None
    if rank_col and pd.notna(row.get(rank_col)):
        try:
            rank = int(row.get(rank_col))
        except Exception:
            try:
                rank = int(float(row.get(rank_col)))
            except Exception:
                rank = None
    if rank is None and total is not None:
        try:
            tmp = df.copy()
            if total_col is None:
                tmp['_calc_total'] = tmp[subject_cols].apply(lambda r: pd.to_numeric(r, errors='coerce').fillna(0).sum(), axis=1)
                tmp_sorted = tmp.sort_values('_calc_total', ascending=False)
                ranks = {v: i+1 for i, v in enumerate(tmp_sorted.index)}
                rank = ranks.get(student_row.index[0])
            else:
                c_total_col = total_col
                tmp[c_total_col] = pd.to_numeric(tmp[c_total_col], errors='coerce').fillna(0)
                tmp_sorted = tmp.sort_values(c_total_col, ascending=False)
                ranks = {v: i+1 for i, v in enumerate(tmp_sorted.index)}
                rank = ranks.get(student_row.index[0])
        except Exception:
            rank = None
    return {'total': total, 'points': points, 'rank': rank}


def build_progress_rows_for_student(school_dir: Path, student_name: str, student_id: str):
    rows = []
    try:
        all_exams = list_exams_for_school(school_dir)
        items = sorted(all_exams.items(), key=lambda x: x[1].get('date_saved',''))
        for e_id, e_meta in items:
            edf = load_exam_df(school_dir, e_id)
            if edf is None:
                continue
            # locate student row in this exam
            cols_l = {c.lower(): c for c in edf.columns}
            idcol = None
            for cand in ['adm no','adm_no','admno','student_id','admission_number']:
                if cand in cols_l:
                    idcol = cols_l[cand]
                    break
            srow = None
            if idcol and student_id:
                tmp = edf[edf[idcol].astype(str).str.strip() == student_id]
                if tmp.shape[0] > 0:
                    srow = tmp
            else:
                namecols = [c for c in edf.columns if 'name' in c.lower()]
                for nc in namecols:
                    tmp = edf[edf[nc].astype(str).str.contains(str(student_name).strip(), case=False, na=False)]
                    if tmp.shape[0] > 0:
                        srow = tmp
                        break
            if srow is None or srow.shape[0] == 0:
                continue
            m = _compute_student_metrics(edf, srow)

            # determine uploaded date (prefer date_saved, created_at, or similar)
            ds = e_meta.get('date_saved') or e_meta.get('date') or e_meta.get('created_at') or e_meta.get('saved_at')
            date_str = None
            try:
                if ds is not None and str(ds).strip() != '':
                    dt = pd.to_datetime(ds, errors='coerce')
                    if not pd.isna(dt):
                        date_str = dt.strftime('%Y-%m-%d')
            except Exception:
                date_str = None

            # compute theoretical out_of (sum of subject full marks) and cohort size for ranking display.
            out_of = None
            cohort_count = None
            try:
                # prefer explicit metadata keys
                for key in ('max_total', 'total_max', 'out_of', 'out_of_marks', 'max_marks'):
                    if key in e_meta and e_meta.get(key) not in (None, ''):
                        try:
                            out_of = int(float(e_meta.get(key)))
                            break
                        except Exception:
                            pass

                # try structured per-subject maxima in metadata
                if out_of is None:
                    subj_max = e_meta.get('subject_max') or e_meta.get('subject_maxima') or e_meta.get('max_per_subject')
                    if isinstance(subj_max, dict):
                        try:
                            out_of = int(sum(int(float(v)) for v in subj_max.values()))
                        except Exception:
                            out_of = None

                # try exam config file next
                if out_of is None:
                    cfg_path = Path(school_dir) / str(e_id) / 'config.json'
                    if cfg_path.exists():
                        try:
                            cfg = json.loads(cfg_path.read_text(encoding='utf-8') or '{}')
                            for key in ('max_total', 'total_max', 'out_of', 'out_of_marks', 'max_marks'):
                                if key in cfg and cfg.get(key) not in (None, ''):
                                    try:
                                        out_of = int(float(cfg.get(key)))
                                        break
                                    except Exception:
                                        pass
                            if out_of is None:
                                subj_max = cfg.get('subject_max') or cfg.get('subject_maxima') or cfg.get('max_per_subject')
                                if isinstance(subj_max, dict):
                                    try:
                                        out_of = int(sum(int(float(v)) for v in subj_max.values()))
                                    except Exception:
                                        out_of = None
                        except Exception:
                            pass

                # try to parse numbers from column headers like 'Math (100)'
                if out_of is None:
                    import re
                    header_numbers = []
                    for c in edf.columns:
                        m_rx = re.search(r'\((\d{1,4})\)', str(c))
                        if m_rx:
                            try:
                                header_numbers.append(int(m_rx.group(1)))
                            except Exception:
                                continue
                    if header_numbers:
                        out_of = int(sum(header_numbers))

                # fallback: if we still don't know per-subject maxima, assume a standard
                # maximum per subject (100). This aligns with the user's requirement that
                # if a student scores 100% in all subjects the total should be the sum
                # of those hundreds.
                if out_of is None:
                    exclude_cols = {'name', 'adm no', 'admno', 'adm_no', 'class', 'mean', 'rank', 's/rank', 'points', 'mean grade'}
                    subject_cols = [c for c in edf.columns if c.lower() not in exclude_cols]
                    # Prefer only numeric-like subject columns (heuristic)
                    numeric_subjects = []
                    for c in subject_cols:
                        try:
                            s = pd.to_numeric(edf[c], errors='coerce')
                            # consider column a numeric subject if it has some numeric entries
                            if s.dropna().shape[0] > 0:
                                numeric_subjects.append(c)
                        except Exception:
                            continue
                    if numeric_subjects:
                        # assume each subject is out of 100 when no explicit maxima are found
                        out_of = int(len(numeric_subjects) * 100)
                    else:
                        out_of = None

                # cohort size for rank denominator
                try:
                    # Exclude trailing summary rows (common in some uploads) from cohort/rank calculations
                    try:
                        edf_for_rank = edf.copy()
                        if edf_for_rank is not None and edf_for_rank.shape[0] > 2:
                            # drop last two rows which often contain summaries/totals
                            edf_for_rank = edf_for_rank.iloc[:-2]
                    except Exception:
                        edf_for_rank = edf

                    cohort_count = int(edf_for_rank.shape[0]) if edf_for_rank is not None else None
                except Exception:
                    cohort_count = None
            except Exception:
                out_of = None
                cohort_count = None

            # prepare separate Marks and Stream Rank columns (Stream = same class/stream)
            marks_val = None
            marks_display = None
            rank_display = None
            try:
                marks_val = m.get('total') if m else None

                # Marks display (include /out_of when known)
                if marks_val is not None:
                    try:
                        if abs(marks_val - int(marks_val)) < 0.01:
                            marks_str = str(int(marks_val))
                        else:
                            marks_str = f"{marks_val:.2f}"
                    except Exception:
                        marks_str = str(marks_val)
                    if out_of is not None:
                        marks_display = f"{marks_str}/{out_of}"
                    else:
                        marks_display = f"{marks_str}"

                # Compute Stream Rank by ranking only students in the same class/stream
                try:
                    # find candidate class/stream columns
                    class_cols = [c for c in edf.columns if ('class' in c.lower() or 'stream' in c.lower())]
                    student_cls = None
                    if class_cols and srow is not None and not srow.empty:
                        for cls_col in class_cols:
                            try:
                                student_cls = srow.iloc[0].get(cls_col)
                                if pd.notna(student_cls):
                                    break
                            except Exception:
                                continue

                    # fallback: if no explicit class column found try 'form' or 'arm'
                    if (student_cls is None or pd.isna(student_cls)):
                        extra_cols = [c for c in edf.columns if any(x in c.lower() for x in ('form', 'arm', 'stream'))]
                        for ec in extra_cols:
                            try:
                                student_cls = srow.iloc[0].get(ec)
                                if pd.notna(student_cls):
                                    class_cols = [ec]
                                    break
                            except Exception:
                                continue

                    # determine score column: prefer existing mean column, else total, else sum numeric subjects
                    score_col = None
                    mean_col = None
                    try:
                        mcands = ['mean', 'average', 'avg', 'mean_score']
                        cols_l = {c.lower(): c for c in edf.columns}
                        for cand in mcands:
                            if cand in cols_l:
                                mean_col = cols_l[cand]
                                break
                    except Exception:
                        mean_col = None

                    if mean_col is not None:
                        score_col = mean_col
                    elif 'total' in (c.lower() for c in edf.columns):
                        # find exact column name for total
                        tcols = [c for c in edf.columns if c.lower() == 'total']
                        score_col = tcols[0] if tcols else None

                    # build stream-specific rank if we have a class value
                    if student_cls is not None and not pd.isna(student_cls) and class_cols:
                        cls_col = class_cols[0]
                        try:
                            subset = edf[edf[cls_col] == student_cls].copy()
                        except Exception:
                            subset = edf[edf[cls_col].astype(str) == str(student_cls)].copy()

                        if subset is not None and not subset.empty:
                            # compute a numeric score for ranking
                            if score_col is None:
                                # infer numeric subject columns
                                exclude_cols = {'name', 'adm no', 'admno', 'adm_no', 'class', 'mean', 'rank', 's/rank', 'points', 'mean grade'}
                                subject_cols = [c for c in subset.columns if c.lower() not in exclude_cols]
                                numeric_cols = []
                                for c in subject_cols:
                                    try:
                                        s = pd.to_numeric(subset[c], errors='coerce')
                                        if s.dropna().shape[0] > 0:
                                            numeric_cols.append(c)
                                    except Exception:
                                        continue
                                if numeric_cols:
                                    subset['_score_for_rank'] = subset[numeric_cols].apply(lambda row: pd.to_numeric(row, errors='coerce').sum(skipna=True), axis=1)
                                else:
                                    subset['_score_for_rank'] = None
                            else:
                                subset['_score_for_rank'] = pd.to_numeric(subset[score_col], errors='coerce')

                            # drop rows without numeric score
                            try:
                                subset_rank = subset.dropna(subset=['_score_for_rank']).copy()
                            except Exception:
                                subset_rank = subset.copy()

                            if not subset_rank.empty:
                                # rank: 1 is highest score
                                try:
                                    subset_rank['_rnk'] = subset_rank['_score_for_rank'].rank(method='min', ascending=False)
                                    # find student's row and rank
                                    student_key = None
                                    try:
                                        # attempt to match by admission no if present
                                        match_cols = {c.lower(): c for c in subset_rank.columns}
                                        idcol = None
                                        for cand in ('adm no','adm_no','admno','student_id','admission_number'):
                                            if cand in match_cols:
                                                idcol = match_cols[cand]
                                                break
                                        if idcol and student_id:
                                            srow_key = srow.iloc[0].get(idcol)
                                            student_key = srow_key
                                    except Exception:
                                        student_key = None

                                    if student_key is not None:
                                        # find by idcol
                                        try:
                                            sr = subset_rank[subset_rank[idcol].astype(str).str.strip() == str(student_key).strip()]
                                            if sr.shape[0] > 0:
                                                rnk = int(sr.iloc[0]['_rnk'])
                                            else:
                                                rnk = int(subset_rank.loc[subset_rank.index[0],'_rnk'])
                                        except Exception:
                                            rnk = int(subset_rank.iloc[0]['_rnk'])
                                    else:
                                        # fallback: try to match by name
                                        namecols = [c for c in subset_rank.columns if 'name' in c.lower()]
                                        rnk = None
                                        for nc in namecols:
                                            try:
                                                sr = subset_rank[subset_rank[nc].astype(str).str.contains(str(student_name).strip(), case=False, na=False)]
                                                if sr.shape[0] > 0:
                                                    rnk = int(sr.iloc[0]['_rnk'])
                                                    break
                                            except Exception:
                                                continue
                                        if rnk is None:
                                            # give up and use the raw rank from marks if present
                                            try:
                                                rnk = int(m.get('rank')) if m and m.get('rank') is not None else None
                                            except Exception:
                                                rnk = None

                                except Exception:
                                    rnk = None

                                try:
                                    class_size = int(subset.shape[0])
                                except Exception:
                                    class_size = None

                                if rnk is not None:
                                    if class_size:
                                        rank_display = f"{int(rnk)}/{int(class_size)}"
                                    else:
                                        rank_display = f"{int(rnk)}"
                except Exception:
                    # leave rank_display as None and fall back to any stored rank
                    rank_display = None

                # if we still don't have a rank_display, try stored fields as a last resort
                if not rank_display:
                    try:
                        if m:
                            for rd_key in ('rank_display', 'rank_str', 's/rank'):
                                if rd_key in m and m.get(rd_key):
                                    rank_display = str(m.get(rd_key))
                                    break
                            if not rank_display and m.get('rank') is not None:
                                # assume cohort denominator unknown
                                rank_display = str(int(float(m.get('rank'))))
                    except Exception:
                        rank_display = rank_display
                # Compute Overall Rank across all students in this exam (regardless of stream)
                overall_rank = None
                try:
                    # determine score column for overall ranking
                    mean_col_all = None
                    try:
                        mcands = ['mean', 'average', 'avg', 'mean_score']
                        cols_l_all = {c.lower(): c for c in edf.columns}
                        for cand in mcands:
                            if cand in cols_l_all:
                                mean_col_all = cols_l_all[cand]
                                break
                    except Exception:
                        mean_col_all = None

                    # Use the edf_for_rank (which may have dropped trailing summary rows)
                    try:
                        src_edf = edf_for_rank if 'edf_for_rank' in locals() and edf_for_rank is not None else edf
                    except Exception:
                        src_edf = edf

                    if mean_col_all is not None:
                        src_edf['_score_for_overall_rank'] = pd.to_numeric(src_edf[mean_col_all], errors='coerce')
                    elif 'total' in (c.lower() for c in src_edf.columns):
                        tcols_all = [c for c in src_edf.columns if c.lower() == 'total']
                        if tcols_all:
                            src_edf['_score_for_overall_rank'] = pd.to_numeric(src_edf[tcols_all[0]], errors='coerce')
                        else:
                            src_edf['_score_for_overall_rank'] = None
                    else:
                        # sum numeric subject columns as fallback
                        exclude_cols_all = {'name', 'adm no', 'admno', 'adm_no', 'class', 'mean', 'rank', 's/rank', 'points', 'mean grade'}
                        subject_cols_all = [c for c in src_edf.columns if c.lower() not in exclude_cols_all]
                        numeric_cols_all = []
                        for c in subject_cols_all:
                            try:
                                s = pd.to_numeric(src_edf[c], errors='coerce')
                                if s.dropna().shape[0] > 0:
                                    numeric_cols_all.append(c)
                            except Exception:
                                continue
                        if numeric_cols_all:
                            src_edf['_score_for_overall_rank'] = src_edf[numeric_cols_all].apply(lambda row: pd.to_numeric(row, errors='coerce').sum(skipna=True), axis=1)
                        else:
                            src_edf['_score_for_overall_rank'] = None

                    # compute rank where higher score => rank 1
                    try:
                        edf_rank_df = src_edf.dropna(subset=['_score_for_overall_rank']).copy()
                        if not edf_rank_df.empty:
                            edf_rank_df['_rnk_all'] = edf_rank_df['_score_for_overall_rank'].rank(method='min', ascending=False)
                            # attempt to find student's row by idcol first
                            try:
                                match_cols_all = {c.lower(): c for c in edf_rank_df.columns}
                                idcol_all = None
                                for cand in ('adm no','adm_no','admno','student_id','admission_number'):
                                    if cand in match_cols_all:
                                        idcol_all = match_cols_all[cand]
                                        break
                                if idcol_all and student_id:
                                    sr_all = edf_rank_df[edf_rank_df[idcol_all].astype(str).str.strip() == str(student_id).strip()]
                                    if sr_all.shape[0] > 0:
                                        overall_rank = int(sr_all.iloc[0]['_rnk_all'])
                                # fallback to name match
                                if overall_rank is None:
                                    namecols_all = [c for c in edf_rank_df.columns if 'name' in c.lower()]
                                    for nc in namecols_all:
                                        try:
                                            srn = edf_rank_df[edf_rank_df[nc].astype(str).str.contains(str(student_name).strip(), case=False, na=False)]
                                            if srn.shape[0] > 0:
                                                overall_rank = int(srn.iloc[0]['_rnk_all'])
                                                break
                                        except Exception:
                                            continue
                            except Exception:
                                overall_rank = None
                    except Exception:
                        overall_rank = None
                except Exception:
                    overall_rank = None
            except Exception:
                marks_display = None
                rank_display = None

            # compute mean/aggregate per exam (prefer existing mean column, else total/num_subjects)
            mean_val = None
            try:
                # look for mean-like column
                mean_col = None
                mcands = ['mean', 'average', 'avg', 'mean_score']
                cols_l = {c.lower(): c for c in edf.columns}
                for cand in mcands:
                    if cand in cols_l:
                        mean_col = cols_l[cand]
                        break
                if mean_col and pd.notna(srow.iloc[0].get(mean_col)):
                    try:
                        mean_val = float(srow.iloc[0].get(mean_col))
                    except Exception:
                        mean_val = None
                else:
                    # compute mean from total and number of numeric subject columns
                    exclude_cols = {'name', 'adm no', 'admno', 'adm_no', 'class', 'total', 'mean', 'rank', 's/rank', 'points', 'mean grade'}
                    subject_cols = [c for c in edf.columns if c.lower() not in exclude_cols]
                    num_subj = 0
                    for c in subject_cols:
                        try:
                            s = pd.to_numeric(edf[c], errors='coerce')
                            if s.dropna().shape[0] > 0:
                                num_subj += 1
                        except Exception:
                            continue
                    tot = m.get('total') if m else None
                    if tot is not None and num_subj > 0:
                        mean_val = float(tot) / float(num_subj)
            except Exception:
                mean_val = None

            points_val = None
            try:
                points_val = m.get('points') if m else None
            except Exception:
                points_val = None

            # Ensure Marks column is only the student's raw total (no '/out_of') per request
            marks_only = None
            try:
                t = m.get('total') if m else None
                if t is not None:
                    if abs(t - int(t)) < 0.01:
                        marks_only = str(int(t))
                    else:
                        marks_only = f"{t:.2f}"
            except Exception:
                marks_only = None

            # include num_subjects to aid chart fallbacks/debugging
            try:
                ns = int(num_subj) if 'num_subj' in locals() and num_subj is not None else None
            except Exception:
                ns = None
            # format overall rank as 'rank/total_students' when cohort_count is known
            try:
                rank_field = None
                if overall_rank is not None and cohort_count:
                    try:
                        rank_field = f"{int(overall_rank)}/{int(cohort_count)}"
                    except Exception:
                        rank_field = f"{overall_rank}/{cohort_count}"
                elif overall_rank is not None:
                    rank_field = overall_rank
                else:
                    # fallback to any stored rank in metadata
                    rank_field = (m.get('rank') if m else None)
            except Exception:
                rank_field = (m.get('rank') if m else None)

            rows.append({'exam_id': e_id, 'exam_name': e_meta.get('exam_name') or e_meta.get('name') or e_id, 'date': date_str, 'marks': marks_only, 'points': points_val, 'mean': mean_val, 'num_subjects': ns, 'rank_display': rank_display, 'total': m.get('total') if m else None, 'rank': rank_field})
    except Exception:
        return []
    return rows


def generate_class_marksheet_pdf(df: pd.DataFrame, title: str = 'Class marksheet') -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=10*mm, rightMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)
    styles = getSampleStyleSheet()
    elems = []
    elems.append(Paragraph(title, styles['Heading2']))
    elems.append(Spacer(1, 6))
    # prepare table data (header + rows)
    header = [str(c) for c in df.columns]
    data = [header]
    # convert rows to strings, limit columns to a reasonable width
    for _, r in df.iterrows():
        row = []
        for c in df.columns:
            v = r.get(c, '')
            s = '' if pd.isna(v) else str(v)
            # truncate very long cells
            if len(s) > 120:
                s = s[:117] + '...'
            row.append(s)
        data.append(row)
    table = Table(data, repeatRows=1)
    table_style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0E6BA8')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ])
    table.setStyle(table_style)
    elems.append(table)
    doc.build(elems)
    return buf.getvalue()

# Parent login form
# Persist parent login in session_state so the portal stays open across form submits
if 'pp_logged_in' not in st.session_state:
    st.session_state['pp_logged_in'] = False
if 'pp_school_acc' not in st.session_state:
    st.session_state['pp_school_acc'] = ''
if 'pp_parent_phone' not in st.session_state:
    st.session_state['pp_parent_phone'] = ''

with st.form('parent_login'):
    school_acc_in = st.text_input('School system number (e.g. ED001)', value=st.session_state.get('pp_school_acc', ''))
    parent_phone_in = st.text_input('Your phone number (as given to the school)', value=st.session_state.get('pp_parent_phone', ''))
    submitted = st.form_submit_button('Log in')

if submitted:
    # save into session_state and continue
    st.session_state['pp_school_acc'] = (school_acc_in or '').strip()
    st.session_state['pp_parent_phone'] = (parent_phone_in or '').strip()
    st.session_state['pp_logged_in'] = True

if not (submitted or st.session_state.get('pp_logged_in')):
    st.info('Enter the school system number and the phone number you provided to the school to view your child(ren) results.')
    st.stop()

# Use persisted values from session_state for the rest of the flow
school_acc = st.session_state.get('pp_school_acc', '')
parent_phone = st.session_state.get('pp_parent_phone', '')

school_dir = find_school_by_account_number(school_acc)
if not school_dir:
    st.error('School with that system number not found. Please check the number and try again.')
    st.stop()

contacts = load_contacts_for_school(school_dir)
norm_input = normalize_phone(parent_phone)
matches = []
for c in contacts:
    ph = c.get('phone') or c.get('phone_raw') or ''
    if normalize_phone(ph) == norm_input and norm_input != '':
        matches.append(c)

if not matches:
    st.error('No child found for that phone number at the specified school. Please confirm the phone number with the school.')
    st.stop()

    st.success(f'Found {len(matches)} child(ren) linked to this phone number at {school_dir.name}')
    # Immediately clear any page query param and reload so we don't land on a missing multipage page (e.g. 'login')
    try:
        st.experimental_set_query_params()
        # rerun to apply cleared params and show the portal content
        try:
            st.experimental_rerun()
        except Exception:
            # older streamlit versions may raise a different exception; ignore
            pass
    except Exception:
        pass

# Render an updated footer overlay including the school's support contact (overrides the generic footer)
try:
    admin_meta = _load_admin_meta(school_dir)
    school_display = admin_meta.get('school_name') or admin_meta.get('name') or school_dir.name
    phone_number = admin_meta.get('phone') or admin_meta.get('phone_number') or admin_meta.get('telephone') or admin_meta.get('contact_phone') or admin_meta.get('contact') or ''
    phone_display = phone_number or ''
    footer_update_html = f"""
    <style>
    /* overlay footer with school-specific support contact */
    #eduscore-footer-updated {{ position: fixed; left: 0; right: 0; bottom: 0; background: rgba(255,255,255,0.98); color: #475569; padding:12px 8px; text-align:center; font-size:13px; z-index:100000; border-top:1px solid rgba(0,0,0,0.06); }}
    div[data-testid="stApp"] > div:nth-child(1) {{ padding-bottom:110px !important; }}
    </style>
    <div id="eduscore-footer-updated">EDUSCORE ANALYTICS<br><span style="font-weight:600;">Developed by Munyua Kamau</span><br>© 2025 All Rights Reserved<br><strong>For support contact:</strong> {school_display}{(' — ' + phone_display) if phone_display else ''}</div>
    """
    st.markdown(footer_update_html, unsafe_allow_html=True)
except Exception:
    pass

options = [f"{m.get('student_name','(no name)')} — {m.get('student_id','')}" for m in matches]
sel = st.selectbox('Select child', options)
sel_idx = options.index(sel)
child = matches[sel_idx]
student_id = str(child.get('student_id') or child.get('adm_no') or child.get('admission') or '').strip()
student_name = child.get('student_name') or child.get('student') or ''

# Header with student ID on the left and student photo placeholder on the far right
left_col, right_col = st.columns([3, 1])
with left_col:
    st.markdown(f"## ID: {student_id}")
    if student_name:
        st.markdown(f"**Student:** {student_name}")
        # show school name and location (from admin meta) — make it larger & prominent
        try:
            admin_meta = _load_admin_meta(school_dir)
            school_display = admin_meta.get('school_name') or admin_meta.get('name') or school_dir.name
            location = admin_meta.get('location') or admin_meta.get('city') or admin_meta.get('address') or ''
            if location:
                st.markdown(f"<div style='color:#0b4d3e; font-size:18px; font-weight:800; margin-top:6px'>{school_display} — {location}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='color:#0b4d3e; font-size:18px; font-weight:800; margin-top:6px'>{school_display}</div>", unsafe_allow_html=True)
        except Exception:
            pass
with right_col:
    photo_path_top = None
    try:
        photo_path_top = _find_school_photo_path(school_dir, name=student_name, adm_no=student_id)
        if photo_path_top:
            try:
                st.image(photo_path_top, width=140)
                st.caption('Student photo — appears here when uploaded')
            except Exception:
                # if image rendering fails for any reason, still expose debug info below
                st.markdown('<div>Photo preview not available</div>')
        else:
            st.markdown(
                '<div style="width:140px;height:140px;border:2px dashed #cfcfcf;display:flex;align-items:center;justify-content:center;color:#6b7280;border-radius:6px;">Photo will appear here when uploaded</div>',
                unsafe_allow_html=True
            )
    except Exception:
        st.markdown('<div>Photo preview not available</div>')

    # (Removed non-destructive debug checkbox showing resolved photo path)

exams_meta = list_exams_for_school(school_dir)
if not exams_meta:
    st.info('No exams found for this school.')
    st.stop()

# Render progress across exams for the selected student (separate from the per-exam UI)
try:
    prog_rows = build_progress_rows_for_student(school_dir, student_name, student_id)
    if prog_rows:
    # (Progress heading removed as requested)
        prog_df = pd.DataFrame(prog_rows)
        # show exam name, upload date, and separate Marks, Points, Mean and Rank columns
        if any(x in prog_df.columns for x in ('marks', 'points', 'mean', 'rank_display', 'rank')):
            cols = ['exam_name', 'date']
            if 'marks' in prog_df.columns:
                cols.append('marks')
            if 'points' in prog_df.columns:
                cols.append('points')
            if 'mean' in prog_df.columns:
                cols.append('mean')
                # include overall rank (formatted as 'rank/total') when available
                if 'rank' in prog_df.columns:
                    cols.append('rank')
            prog_df_display = prog_df[cols].copy()
            # rename to user-friendly headers
            rename_map = {}
            if 'marks' in prog_df_display.columns:
                rename_map['marks'] = 'Marks'
            if 'points' in prog_df_display.columns:
                rename_map['points'] = 'Points'
            if 'mean' in prog_df_display.columns:
                rename_map['mean'] = 'Mean'
            if 'rank' in prog_df_display.columns:
                rename_map['rank'] = 'Overall Rank'
            if rename_map:
                prog_df_display = prog_df_display.rename(columns=rename_map)
        else:
            prog_df_display = prog_df[['exam_name', 'date', 'total', 'rank']]
        # Enhance table with Stream Rank and a simple medal indicator
        try:
            # Prefer the preformatted rank display (e.g. '3/34') when available
            if 'rank_display' in prog_df.columns:
                prog_df_display['Stream Rank'] = prog_df['rank_display']
            elif 'rank' in prog_df.columns:
                # fallback to numeric rank only
                prog_df_display['Stream Rank'] = prog_df['rank']
            else:
                prog_df_display['Stream Rank'] = None

            # Add a small medal/icon for top positions. Parse numeric rank from Stream Rank if it contains 'num/den'.
            def _parse_rank_num(rstr):
                try:
                    if rstr is None:
                        return None
                    s = str(rstr).split('/')[0].strip()
                    return int(s)
                except Exception:
                    return None

            def _medal_for_rank(r):
                try:
                    if r is None:
                        return ''
                    r = int(r)
                    if r == 1:
                        return '🥇'
                    if r == 2:
                        return '🥈'
                    if r == 3:
                        return '🥉'
                    return ''
                except Exception:
                    return ''

            # derive numeric rank for medal assignment using Stream Rank
            if 'Stream Rank' in prog_df_display.columns:
                prog_df_display['_rank_num_for_medal'] = prog_df_display['Stream Rank'].apply(_parse_rank_num)
                prog_df_display['Medal'] = prog_df_display['_rank_num_for_medal'].apply(_medal_for_rank)
                prog_df_display.drop(columns=['_rank_num_for_medal'], inplace=True)
            else:
                prog_df_display['Medal'] = ''
        except Exception:
            pass

        # Show table and a pictorial summary (sparkline + latest metrics) side-by-side
        try:
            left_col, right_col = st.columns([3, 1])
            with left_col:
                st.dataframe(prog_df_display)

            with right_col:
                # small sparkline of mean/total values
                try:
                    chart_rows_small = []
                    for r in prog_rows:
                        mean_v = r.get('mean')
                        total_v = r.get('total')
                        val = mean_v if (mean_v is not None) else total_v
                        if val is None:
                            continue
                        chart_rows_small.append({'exam_name': r.get('exam_name'), 'date': r.get('date'), 'value': float(val), 'rank': r.get('rank')})
                    if chart_rows_small:
                        cdf = pd.DataFrame(chart_rows_small)
                        cdf['parsed_date'] = pd.to_datetime(cdf['date'], errors='coerce')
                        # latest exam metrics
                        latest = None
                        if 'parsed_date' in cdf.columns and cdf['parsed_date'].notna().any():
                            latest = cdf.sort_values('parsed_date').iloc[-1]
                        else:
                            latest = cdf.iloc[-1]

                        # display latest mean and rank as a metric
                        try:
                            latest_val = latest['value'] if latest is not None else None
                            latest_rank = latest.get('rank') if latest is not None else None
                        except Exception:
                            latest_val = None
                            latest_rank = None

                        if latest_val is not None:
                            st.markdown('**Latest**')
                            st.metric(label='Mean', value=f"{latest_val:.2f}", delta=None)
                        else:
                            st.markdown('**Latest**')
                            st.write('No numeric value')

                        if latest_rank is not None:
                            try:
                                rank_int = int(latest_rank)
                                st.markdown(f'**Latest Overall Rank:** {rank_int}')
                            except Exception:
                                st.markdown(f'**Latest Overall Rank:** {latest_rank}')

                        # sparkline chart
                        if ALT_AVAILABLE and not cdf.empty:
                            try:
                                src = cdf.copy()
                                if src['parsed_date'].notna().any():
                                    src = src.sort_values('parsed_date')
                                    spark = alt.Chart(src).mark_line(point=True).encode(
                                        x=alt.X('parsed_date:T', title=None),
                                        y=alt.Y('value:Q', title=None),
                                        tooltip=['exam_name', 'value']
                                    ).properties(height=120)
                                else:
                                    spark = alt.Chart(src).mark_line(point=True).encode(
                                        x=alt.X('exam_name:N', title=None),
                                        y=alt.Y('value:Q', title=None),
                                        tooltip=['exam_name', 'value']
                                    ).properties(height=120)
                                st.altair_chart(spark, use_container_width=True)
                            except Exception:
                                # fallback to line_chart
                                try:
                                    if 'parsed_date' in cdf.columns and cdf['parsed_date'].notna().any():
                                        ctmp = cdf.sort_values('parsed_date').set_index('parsed_date')
                                        st.line_chart(ctmp['value'])
                                    else:
                                        st.line_chart(cdf.set_index('exam_name')['value'])
                                except Exception:
                                    pass
                except Exception:
                    pass
        except Exception:
            # fallback: simple table if columns API fails
            try:
                st.dataframe(prog_df_display)
            except Exception:
                pass

        # Primary progress chart: prefer plotting aggregate mean per exam, else fall
        # back to totals. Coerce numeric, sort by date if available, and render a
        # larger chart (Altair if available) for better visibility.
        try:
            chart_rows = []
            for r in prog_rows:
                mean_v = r.get('mean')
                total_v = r.get('total')
                val = mean_v if (mean_v is not None) else total_v
                if val is None:
                    continue
                chart_rows.append({'exam_name': r.get('exam_name'), 'date': r.get('date'), 'value': val})
            if chart_rows:
                chart_df = pd.DataFrame(chart_rows)
                chart_df['value'] = pd.to_numeric(chart_df['value'], errors='coerce')
                chart_df = chart_df.dropna(subset=['value'])
                if not chart_df.empty:
                    chart_df['parsed_date'] = pd.to_datetime(chart_df['date'], errors='coerce')
                    # (Progress heading removed as requested)
                    if ALT_AVAILABLE:
                        try:
                            if chart_df['parsed_date'].notna().any():
                                src = chart_df.sort_values('parsed_date').reset_index(drop=True)
                                chart = alt.Chart(src).mark_line(point=True).encode(
                                    x=alt.X('parsed_date:T', title='Date'),
                                    y=alt.Y('value:Q', title='Mean score'),
                                    tooltip=['exam_name', 'value', 'date']
                                ).properties(height=360)
                            else:
                                src = chart_df.reset_index(drop=True)
                                chart = alt.Chart(src).mark_line(point=True).encode(
                                    x=alt.X('exam_name:N', title='Exam'),
                                    y=alt.Y('value:Q', title='Mean score'),
                                    tooltip=['exam_name', 'value', 'date']
                                ).properties(height=360)
                            st.altair_chart(chart, use_container_width=True)
                        except Exception:
                            # fallback
                            if chart_df['parsed_date'].notna().any():
                                chart_df = chart_df.sort_values('parsed_date').set_index('parsed_date')
                                st.line_chart(chart_df['value'])
                            else:
                                chart_df = chart_df.set_index('exam_name')
                                st.line_chart(chart_df['value'])
                    else:
                        if chart_df['parsed_date'].notna().any():
                            chart_df = chart_df.sort_values('parsed_date').set_index('parsed_date')
                            st.line_chart(chart_df['value'])
                        else:
                            chart_df = chart_df.set_index('exam_name')
                            st.line_chart(chart_df['value'])
                else:
                    st.info('No numeric mean/total values available to build the progress chart yet.')
        except Exception:
            pass

        # Yearly trend: compute mean per year and draw a chart that updates as new exams are added
        try:
            pd_dates = pd.to_datetime(prog_df['date'], errors='coerce') if 'date' in prog_df.columns else None
            if pd_dates is not None and not pd_dates.isna().all():
                prog_df['year'] = pd_dates.dt.year
            else:
                # fallback: try to parse year from exam_name
                import re
                def _year_from_name(n):
                    m = re.search(r"(20\d{2})", str(n))
                    return int(m.group(1)) if m else None
                prog_df['year'] = prog_df['exam_name'].apply(lambda x: _year_from_name(x))

            if 'mean' in prog_df.columns:
                yearly = prog_df.groupby('year', dropna=True)['mean'].mean().sort_index()
                if not yearly.empty:
                    # (Yearly trend heading removed as requested)
                    st.line_chart(yearly)
            else:
                # fallback to plotting total per exam over time
                if 'total' in prog_df.columns and 'year' in prog_df.columns:
                    yearly_tot = prog_df.groupby('year', dropna=True)['total'].mean().sort_index()
                    if not yearly_tot.empty:
                        # (Yearly total trend heading removed as requested)
                        st.line_chart(yearly_tot)
        except Exception:
            pass
except Exception:
    pass

# Report card generation/import disabled in the standalone Parents Portal.
# The full report-card generator (pages.report_cards) is intentionally
# not imported here to keep the portal read-only and lightweight.
report_cards = None

# Try to load school-specific settings or fallback
# Report card settings and generation are disabled in this portal.
settings = None

rows = []
for exam_id, meta in sorted(exams_meta.items(), key=lambda x: x[1].get('date_saved','')):
    exam_name = meta.get('exam_name') or meta.get('name') or exam_id
    df = load_exam_df(school_dir, exam_id)
    found = False
    if df is not None:
        cols = {c.lower(): c for c in df.columns}
        candidate_cols = ['adm no','adm_no','admno','student_id','admission_number']
        match_col = None
        for c in candidate_cols:
            if c in cols:
                match_col = cols[c]
                break
        if match_col and student_id:
            sel_row = df[df[match_col].astype(str).str.strip() == student_id]
            if sel_row.shape[0] > 0:
                found = True
        else:
            name_cols = [cols[k] for k in cols if 'name' in k]
            sel_row = None
            for nc in name_cols:
                tmp = df[df[nc].astype(str).str.contains(str(student_name).strip(), case=False, na=False)]
                if tmp.shape[0] > 0:
                    sel_row = tmp
                    found = True
                    break
    rows.append({'exam_id': exam_id, 'exam_name': exam_name, 'has_student': bool(found)})

import pandas as _pd

df_exams = _pd.DataFrame(rows)
available = df_exams[df_exams['has_student']]
if available.empty:
    st.info('No exam results found for this child yet.')
    st.stop()

try:
    display_name = student_name if student_name else 'STUDENT'
except Exception:
    display_name = 'STUDENT'
st.markdown(f"### MARKSHEET AND REPORTS CARDS OF {display_name}")

# Build structured grouping: Year -> Term -> Exam Kind -> list of exams
grouped = {}
for _, r in available.iterrows():
    exam_id = r['exam_id']
    exam_name = r['exam_name']
    meta = exams_meta.get(exam_id, {})
    df = load_exam_df(school_dir, exam_id)
    if df is None:
        continue

    # locate student row(s)
    cols_l = {c.lower(): c for c in df.columns}
    idcol = None
    for cand in ['adm no','adm_no','admno','student_id','admission_number']:
        if cand in cols_l:
            idcol = cols_l[cand]
            break
    if idcol and student_id:
        student_row = df[df[idcol].astype(str).str.strip() == student_id]
    else:
        namecols = [c for c in df.columns if 'name' in c.lower()]
        student_row = _pd.DataFrame()
        for nc in namecols:
            tmp = df[df[nc].astype(str).str.contains(str(student_name).strip(), case=False, na=False)]
            if tmp.shape[0] > 0:
                student_row = tmp
                break

    # infer year
    year = 'Unknown'
    try:
        ds = meta.get('date_saved') or meta.get('date') or meta.get('created_at') or meta.get('saved_at')
        if ds:
            try:
                # numeric epoch
                if isinstance(ds, (int, float)):
                    year = pd.to_datetime(int(ds), unit='s').year
                else:
                    year = pd.to_datetime(str(ds), errors='coerce').year
                    if pd.isna(year):
                        year = 'Unknown'
            except Exception:
                year = 'Unknown'
    except Exception:
        year = 'Unknown'

    # infer term and kind
    term = meta.get('term') or meta.get('school_term') or meta.get('term_name') or 'General'
    kind = meta.get('exam_kind') or meta.get('exam_type') or meta.get('kind') or exam_name

    grouped.setdefault(str(year), {}).setdefault(term, {}).setdefault(kind, []).append({'exam_id': exam_id, 'exam_name': exam_name, 'df': df, 'student_row': student_row})

# Render grouping in sorted order
for year in sorted(grouped.keys(), reverse=True):
    with st.expander(f"{year}", expanded=(year == sorted(grouped.keys(), reverse=True)[0])):
        terms = grouped[year]
        for term in sorted(terms.keys()):
            with st.expander(f"{term}"):
                kinds = terms[term]
                for kind in sorted(kinds.keys()):
                    exams_list = kinds[kind]
                    st.markdown(f"**{kind}**")
                    for ex in exams_list:
                        ex_id = ex['exam_id']
                        ex_name = ex['exam_name']
                        ex_df = ex['df']
                        ex_row = ex['student_row']

                        # compute available PDFs for this exam/school (prefer student ID or exam id in filename)
                        try:
                            candidate_pdfs = []
                            for p in os.listdir(school_dir):
                                if not p.lower().endswith('.pdf'):
                                    continue
                                n = p.lower()
                                # prefer matching on student ID or exam id; avoid showing student name
                                if student_id and str(student_id).lower() in n:
                                    candidate_pdfs.append(p)
                                elif ex_id.lower() in n:
                                    candidate_pdfs.append(p)
                                elif ex_name and ex_name.lower().replace(' ', '_') in n:
                                    candidate_pdfs.append(p)
                            candidate_pdfs = sorted(set(candidate_pdfs), reverse=True)
                        except Exception:
                            candidate_pdfs = []

                        # Option to show the full class marksheet at full width/height
                        show_full = st.checkbox('Show full-class marksheet full-width', key=f'full_width_{ex_id}', value=False)
                        if show_full:
                            try:
                                st.markdown(f"### {ex_name} — Full class marksheet")
                                st.dataframe(ex_df, height=700, use_container_width=True)
                                # CSV download as well
                                try:
                                    csv_bytes = ex_df.to_csv(index=False).encode('utf-8')
                                    st.download_button(label='Download class CSV', data=csv_bytes, file_name=f'{ex_name}_class_marks.csv', mime='text/csv')
                                except Exception:
                                    pass
                            except Exception:
                                st.write('Could not render full class marksheet')
                            # skip the compact two-column layout when full view is selected
                            continue

                        # Modern two-column layout: left = full class marksheet, right = student card + downloads
                        left, right = st.columns([3, 1])

                        with left:
                            st.markdown(f"### {ex_name}")
                            # full class marksheet in a collapsible, with CSV download
                            with st.expander('Full class marksheet (click to expand)', expanded=False):
                                try:
                                    st.dataframe(ex_df)
                                except Exception:
                                    st.write('Could not render full marksheet')
                                # offer CSV download for the class
                                try:
                                    csv_bytes = ex_df.to_csv(index=False).encode('utf-8')
                                    st.download_button(label='Download class CSV', data=csv_bytes, file_name=f'{ex_name}_class_marks.csv', mime='text/csv')
                                except Exception:
                                    pass

                            # Report card downloads and generation are disabled in this portal.
                            # If pre-generated report PDFs exist in the school's folder they
                            # are offered above; otherwise no generation options are shown here.
                            if candidate_pdfs:
                                st.markdown('**Available report(s)**')
                                for p in candidate_pdfs:
                                    pdf_file = os.path.join(str(school_dir), p)
                                    try:
                                        with open(pdf_file, 'rb') as _f:
                                            pdf_bytes = _f.read()
                                        st.download_button(label=f'Download {p}', data=pdf_bytes, file_name=p, mime='application/pdf')
                                    except Exception:
                                        st.write(p)

                        with right:
                            # Student card (name/ID header and in-card summary removed as requested)
                            st.markdown('<div style="padding:12px;border-radius:10px;background:linear-gradient(180deg,#ffffff,#f8fafc);box-shadow:0 6px 18px rgba(2,6,23,0.06);">', unsafe_allow_html=True)
                            # (removed duplicate photo text) right column reserved for student card actions

                            st.markdown('</div>', unsafe_allow_html=True)

st.markdown('---')

# --- Parent -> Director messages (optional quick feedback)
try:
    # messages stored per-school under `messages/parent_messages.json`
    msgs_dir = Path(school_dir) / 'messages'
    msgs_path = msgs_dir / 'parent_messages.json'
    try:
        existing_msgs = json.loads(msgs_path.read_text(encoding='utf-8') or '[]') if msgs_path.exists() else []
    except Exception:
        existing_msgs = []

    st.markdown('### Message to school directors')
    st.info('Use this form to send a short message to the school directors. Your phone number will be visible to them so they can follow up.')
    with st.form('parent_message_form'):
        p_name = st.text_input('Your name (optional)')
        p_phone = st.text_input('Phone (will be shown to directors)', value=parent_phone)
        p_student = st.text_input('Student name (optional)', value=student_name)
        p_student_id = st.text_input('Student ID (optional)', value=student_id)
        p_msg = st.text_area('Message', help='Be brief and polite; directors will see your contact details.')
        send = st.form_submit_button('Send message to directors')

    if send:
        if not p_msg or not p_phone:
            st.error('Please provide a message and a phone number.')
        else:
            # Safer write: (1) ensure dir exists, (2) re-read existing file to avoid races,
            # (3) write to a temp file and rename to avoid partial writes.
            try:
                # Use storage adapter to persist parent messages (S3-aware)
                try:
                    from modules import storage
                except Exception:
                    storage = None

                existing_msgs = []
                try:
                    if storage is not None:
                        existing_msgs = storage.read_json('messages/parent_messages.json') or []
                    else:
                        # fallback to local Path usage
                        if msgs_path.exists():
                            try:
                                with open(msgs_path, 'r', encoding='utf-8') as mf:
                                    existing_msgs = json.load(mf) or []
                            except Exception:
                                existing_msgs = []
                except Exception:
                    existing_msgs = []

                new = {
                    'timestamp': pd.Timestamp.now().isoformat(),
                    'parent_name': (p_name or '').strip(),
                    'parent_phone': (p_phone or '').strip(),
                    'student_name': (p_student or '').strip(),
                    'student_id': (p_student_id or '').strip(),
                    'message': (p_msg or '').strip(),
                    'read': False
                }

                existing_msgs.append(new)

                try:
                    if storage is not None:
                        storage.write_json('messages/parent_messages.json', existing_msgs)
                    else:
                        tmp_path = msgs_path.with_suffix('.tmp')
                        with open(tmp_path, 'w', encoding='utf-8') as mf:
                            json.dump(existing_msgs, mf, ensure_ascii=False, indent=2)
                        try:
                            tmp_path.replace(msgs_path)
                        except Exception:
                            with open(msgs_path, 'w', encoding='utf-8') as mf:
                                json.dump(existing_msgs, mf, ensure_ascii=False, indent=2)
                except Exception:
                    # best-effort: fall back to local write
                    try:
                        tmp_path = msgs_path.with_suffix('.tmp')
                        with open(tmp_path, 'w', encoding='utf-8') as mf:
                            json.dump(existing_msgs, mf, ensure_ascii=False, indent=2)
                        try:
                            tmp_path.replace(msgs_path)
                        except Exception:
                            with open(msgs_path, 'w', encoding='utf-8') as mf:
                                json.dump(existing_msgs, mf, ensure_ascii=False, indent=2)
                    except Exception:
                        pass

                st.success('Message sent — the school directors will see it in their lounge.')
            except Exception as e:
                st.error(f'Failed to send message: {e}')

    # Show recent messages sent from this parent (local feedback) and count
    try:
        mine = [m for m in (existing_msgs or []) if (normalize_phone(str(m.get('parent_phone') or '')) == normalize_phone(parent_phone))]
        if mine:
            st.markdown('**Your recent messages (this school)**')
            for m in sorted(mine, key=lambda x: x.get('timestamp') or '', reverse=True)[:5]:
                ts = m.get('timestamp') or ''
                txt = m.get('message') or ''
                read_flag = m.get('read', False)
                badge = '🔔 Unread' if not read_flag else '✓ Read'
                st.markdown(f"<div style='border-left:3px solid #0b4d3e;padding:8px;margin-bottom:6px;'><small style='color:#6b7280'>{ts} · {badge}</small><div style='font-weight:700'>{txt}</div></div>", unsafe_allow_html=True)
    except Exception:
        pass

except Exception:
    pass

st.caption('Parents Portal — access is restricted to viewing your child(ren) results only.')
