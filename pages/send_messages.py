import streamlit as st
import json
from pathlib import Path
import pandas as pd
from utils import messaging
import ssl
import socket
from urllib.parse import urlparse
import requests
import copy
import shutil
import datetime

# Paths
from modules.storage import get_storage_dir
BASE = Path(get_storage_dir())
CONTACTS_FILE = BASE / 'student_contacts.json'
CONFIG_FILE = BASE / 'messaging_config.json'
LOG_FILE = BASE / 'sent_messages_log.json'
META_FILE = BASE / 'exams_metadata.json'


st.set_page_config(page_title="Send Messages", layout="wide")
# Sanitize accidental admin-hidden message on this page only.
# Intercept common Streamlit output helpers and remove the exact
# unwanted sentence before rendering so cached or file content can't show it.
_BAD_PHRASE = "This page is hidden while the administrator console is active."
def _sanitize_args_kwargs(args, kwargs):
    new_args = []
    for a in args:
        if isinstance(a, str) and _BAD_PHRASE in a:
            a = a.replace(_BAD_PHRASE, '')
        new_args.append(a)
    new_kwargs = {}
    for k, v in (kwargs or {}).items():
        if isinstance(v, str) and _BAD_PHRASE in v:
            v = v.replace(_BAD_PHRASE, '')
        new_kwargs[k] = v
    return tuple(new_args), new_kwargs

def _wrap_streamlit(func):
    def _wrapped(*args, **kwargs):
        a, k = _sanitize_args_kwargs(args, kwargs)
        return func(*a, **k)
    return _wrapped

try:
    _st_markdown = st.markdown
    _st_write = st.write
    _st_info = st.info
    _st_error = st.error
    _st_warning = st.warning
    _st_success = st.success
    _st_caption = st.caption
    st.markdown = _wrap_streamlit(_st_markdown)
    st.write = _wrap_streamlit(_st_write)
    st.info = _wrap_streamlit(_st_info)
    st.error = _wrap_streamlit(_st_error)
    st.warning = _wrap_streamlit(_st_warning)
    st.success = _wrap_streamlit(_st_success)
    st.caption = _wrap_streamlit(_st_caption)
except Exception:
    pass

# Block access when parents portal mode is active
try:
    if st.session_state.get('parents_portal_mode'):
        st.markdown("<div style='opacity:0.45;padding:18px;border-radius:8px;background:#f3f4f6;color:#111;'>\
            <strong>Restricted:</strong> This page is not available in Parents Portal mode.</div>", unsafe_allow_html=True)
        st.stop()
except Exception:
    pass
# Attractive banner header
st.markdown(
        """
        <div style="background: linear-gradient(90deg,#0f172a,#0b84ff); padding:18px; border-radius:8px;">
            <h1 style="color: #ffffff; margin: 0; font-family: Helvetica, Arial, sans-serif;">Send Messages</h1>
            <p style="color: #e6f2ff; margin: 4px 0 0 0;">Prepare and deliver exam result messages to parents — select exams, preview messages, then confirm to send.</p>
        </div>
        """,
        unsafe_allow_html=True,
)

# Page styling: make primary buttons green and give the page a modern feel
st.markdown(
        """
        <style>
            /* Style Streamlit buttons to a pleasant green */
            .stButton>button {
                background-color: #16a34a;
                color: white;
                border: none;
                padding: 8px 14px;
                border-radius: 8px;
            }
            .stButton>button:hover {
                background-color: #15803d;
            }
            /* Slightly larger, modern font for headings */
            h1, h2, h3 { font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial; }
            /* Make metric cards stand out */
            .stMetric { border-radius: 8px; }
        </style>
        """,
        unsafe_allow_html=True,
)

# Clear-log red button styling (specific class for the footer button)
st.markdown("""
<style>
.clear-log-red {
    display: inline-block;
    background-color: #dc2626; /* red */
    color: white;
    padding: 10px 16px;
    border-radius: 8px;
    font-weight: 700;
    text-align: center;
}
.clear-log-red:hover { background-color: #b91c1c; }
</style>
""", unsafe_allow_html=True)

# Helpers
def load_contacts():
    try:
        if CONTACTS_FILE.exists():
            return json.loads(CONTACTS_FILE.read_text(encoding='utf-8'))
        return []
    except Exception:
        return []


def load_config():
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        return {}
    except Exception:
        return {}


def _ensure_scheme(u: str) -> str:
    if not u:
        return u
    u = u.strip()
    if not u.startswith('http://') and not u.startswith('https://'):
        return 'https://' + u
    return u


def _tls_check(host: str, port: int = 443, timeout: int = 8):
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                return {'ok': True, 'tls_version': ssock.version(), 'cipher': ssock.cipher()[0]}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _http_options_check(url: str, headers: dict = None, timeout: int = 8):
    try:
        r = requests.options(url, headers=headers or {}, timeout=timeout)
        return {'ok': True, 'status_code': r.status_code, 'headers': dict(r.headers)}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def safe_rerun():
    """Attempt to rerun the Streamlit script in a way that works across versions.
    Fallbacks to st.stop() if no rerun mechanism is available.
    """
    try:
        # preferred API when available
        st.experimental_rerun()
        return
    except Exception:
        pass
    try:
        # try raising Streamlit's internal RerunException (may vary by version)
        from streamlit.runtime.scriptrunner.script_runner import RerunException
        raise RerunException()
    except Exception:
        try:
            # last resort: stop the script (client will refresh on next interaction)
            st.stop()
        except Exception:
            # give up silently
            return


def build_preview_message(recipient: dict) -> str:
    """Attempt to construct a preview message for a recipient by reading the
    exam data pickle and computing numeric subject parts, totals and ranks if
    an explicit prepared message isn't available.
    Returns empty string on failure.
    """
    try:
        exam_id = recipient.get('exam_id')
        exam_name = recipient.get('exam_name', '')
        student_name = (recipient.get('student_name') or '').strip()
        parent_name = (recipient.get('parent_name') or '').strip()
        if not exam_id or not student_name:
            return ''
        exam_path = BASE / exam_id / 'data.pkl'
        if not exam_path.exists():
            return ''
        exdf = pd.read_pickle(exam_path)
        # find name column
        name_col = None
        for c in ['student_name','name','Name','student','Student','student full name','Student Name']:
            if c in exdf.columns:
                name_col = c
                break
        if name_col is None:
            return ''
        # normalize and find the student's row
        try:
            exdf['__name_norm'] = exdf[name_col].astype(str).str.lower().str.replace(r"\s+", ' ', regex=True).str.strip()
            target_norm = student_name.lower().replace('\n',' ').strip()
            rows = exdf[exdf['__name_norm'] == target_norm]
            if rows.empty:
                # try contains fallback
                rows = exdf[exdf[name_col].astype(str).str.lower().str.contains(student_name.lower().strip())]
                if rows.empty:
                    return ''
            row = rows.iloc[0]
        except Exception:
            return ''

        # detect numeric subject columns
        cols = list(exdf.columns)
        ignore_cols = {name_col, '__name_norm', 'parent_name', 'Parent', 'Class', 'class', 'class_name', 'grade', 'stream'}
        numeric_subjects = []
        for c in cols:
            if c in ignore_cols:
                continue
            # skip auxiliary columns that are not subjects (rank/position etc.)
            try:
                lc = str(c).lower()
                if 'rank' in lc or 'position' in lc or lc.strip() in ('s/rank', 's_rank', 's rank'):
                    continue
            except Exception:
                pass
            try:
                if pd.to_numeric(exdf[c], errors='coerce').notna().sum() > 0:
                    numeric_subjects.append(c)
            except Exception:
                continue
        # prefer an explicit score/total column if present
        score_candidates = ['TOTALS','TOTAL','Total','total','Score','score','Total Marks','Marks','Total_Marks']
        score_col = None
        for sc in score_candidates:
            if sc in exdf.columns:
                # ensure the column contains numeric values for at least some rows
                try:
                    if pd.to_numeric(exdf[sc], errors='coerce').notna().sum() > 0:
                        score_col = sc
                        break
                except Exception:
                    continue

        parts = []
        totals_sum = None
        # only compute totals if we have a reliable source: either an explicit score column
        # with numeric values, or at least two numeric subject-like columns (heuristic).
        can_compute = False
        if score_col:
            can_compute = True
        elif len(numeric_subjects) >= 2:
            can_compute = True

        if can_compute:
            vals = []
            # Always attempt to collect per-subject parts when numeric subject columns exist.
            for s in numeric_subjects:
                try:
                    v = row.get(s)
                    num = pd.to_numeric(v, errors='coerce')
                    if pd.notna(num):
                        vals.append(num)
                        parts.append(f"{s}: {int(num) if float(num).is_integer() else float(num)}")
                except Exception:
                    continue

            # Prefer an explicit score column for the total, but still include subject parts above.
            if score_col:
                try:
                    v = row.get(score_col)
                    num = pd.to_numeric(v, errors='coerce')
                    if pd.notna(num):
                        totals_sum = int(num)
                    else:
                        # fall back to summing subject vals if score column is not numeric for this row
                        if vals:
                            totals_sum = int(sum([float(x) for x in vals]))
                except Exception:
                    totals_sum = None
            else:
                if vals:
                    totals_sum = int(sum([float(x) for x in vals]))
        else:
            # not enough reliable numeric data to build a preview
            return ''

        # compute ranks if we have totals
        class_rank_str = 'N/A'
        overall_rank_str = 'N/A'
        if totals_sum is not None:
            try:
                tmp = exdf.copy()
                # sum numeric subjects per row
                tmp['_calc_total'] = 0
                for s in numeric_subjects:
                    tmp[s] = pd.to_numeric(tmp[s], errors='coerce')
                    tmp['_calc_total'] = tmp['_calc_total'].fillna(0) + tmp[s].fillna(0)
                # drop rows without a numeric calc total
                tmp2 = tmp[tmp['_calc_total'].notna()].copy()
                if not tmp2.empty:
                    tmp2['_overall_rank'] = tmp2['_calc_total'].rank(ascending=False, method='min')
                    class_col = None
                    for cc in ['Class','class','class_name','className','Grade','GRADE']:
                        if cc in tmp2.columns:
                            class_col = cc
                            break
                    if class_col:
                        tmp2['_class_rank'] = tmp2.groupby(class_col)['_calc_total'].rank(ascending=False, method='min')
                    # find the matching row in tmp2
                    try:
                        tmp2['__name_norm'] = tmp2[name_col].astype(str).str.lower().str.replace(r"\s+", ' ', regex=True).str.strip()
                        my = tmp2[tmp2['__name_norm'] == target_norm]
                        if not my.empty:
                            r = my.iloc[0]
                            overall_rank = int(r.get('_overall_rank'))
                            overall_size = int(len(tmp2))
                            overall_rank_str = f"{overall_rank}/{overall_size}"
                            if class_col and pd.notna(r.get('_class_rank')):
                                class_rank = int(r.get('_class_rank'))
                                class_size = int(len(tmp2[tmp2.get(class_col) == r.get(class_col)])) if class_col in tmp2.columns else None
                                class_rank_str = f"{class_rank}/{class_size}" if class_size else str(class_rank)
                    except Exception:
                        pass
            except Exception:
                pass

        subj_str = ', '.join(parts)
        parent = parent_name or (row.get('parent_name') if 'parent_name' in row else '') or ''
        student_disp = student_name or ''
        total_disp = totals_sum if totals_sum is not None else 'N/A'
        message_text = f"Dear {parent}, Results for {student_disp} — {exam_name}. {subj_str + '.' if subj_str else ''} Total: {total_disp}. Class Rank: {class_rank_str}. Overall Rank: {overall_rank_str}."
        return message_text
    except Exception:
        return ''





def compute_subject_parts(recipient: dict, min_subjects: int = 1):
    """Return (subj_str, total_sum) if numeric subject data can be extracted from exam pickle.
    Returns (None, None) if not enough reliable numeric data found.
    """
    try:
        exam_id = recipient.get('exam_id')
        student_name = (recipient.get('student_name') or '').strip()
        if not exam_id or not student_name:
            return (None, None)
        exam_path = BASE / exam_id / 'data.pkl'
        if not exam_path.exists():
            return (None, None)
        exdf = pd.read_pickle(exam_path)
        # find name column
        name_col = None
        for c in ['student_name','name','Name','student','Student','student full name','Student Name']:
            if c in exdf.columns:
                name_col = c
                break
        if name_col is None:
            return (None, None)
        # detect numeric subject columns
        ignore_cols = {name_col, 'parent_name', 'Parent', 'Class', 'class', 'class_name', 'grade', 'stream'}
        numeric_subjects = []
        for c in exdf.columns:
            if c in ignore_cols:
                continue
            # skip rank/position columns which may be numeric but are not subject marks
            try:
                lc = str(c).lower()
                if 'rank' in lc or 'position' in lc or lc.strip() in ('s/rank', 's_rank', 's rank'):
                    continue
            except Exception:
                pass
            try:
                if pd.to_numeric(exdf[c], errors='coerce').notna().sum() > 0:
                    numeric_subjects.append(c)
            except Exception:
                continue

        # prefer explicit total/score column if present
        score_candidates = ['TOTALS','TOTAL','Total','total','Score','score','Total Marks','Marks','Total_Marks']
        score_col = None
        for sc in score_candidates:
            if sc in exdf.columns:
                try:
                    if pd.to_numeric(exdf[sc], errors='coerce').notna().sum() > 0:
                        score_col = sc
                        break
                except Exception:
                    continue

        if not score_col and len(numeric_subjects) < min_subjects:
            return (None, None)

        # find student row
        try:
            exdf['__name_norm'] = exdf[name_col].astype(str).str.lower().str.replace(r"\s+", ' ', regex=True).str.strip()
            target_norm = student_name.lower().replace('\n',' ').strip()
            rows = exdf[exdf['__name_norm'] == target_norm]
            if rows.empty:
                rows = exdf[exdf[name_col].astype(str).str.lower().str.contains(student_name.lower().strip(), na=False)]
                if rows.empty:
                    return (None, None)
            row = rows.iloc[0]
        except Exception:
            return (None, None)

        parts = []
        total_sum = None
        # Collect per-subject parts when available
        vals = []
        for s in numeric_subjects:
            try:
                v = row.get(s)
                num = pd.to_numeric(v, errors='coerce')
                if pd.notna(num):
                    vals.append(num)
                    parts.append(f"{s}: {int(num) if float(num).is_integer() else float(num)}")
            except Exception:
                continue

        # Prefer explicit score column for total; fall back to summing subject vals
        if score_col:
            try:
                v = row.get(score_col)
                num = pd.to_numeric(v, errors='coerce')
                if pd.notna(num):
                    total_sum = int(num)
                elif vals:
                    total_sum = int(sum([float(x) for x in vals]))
            except Exception:
                total_sum = None
        else:
            if vals:
                total_sum = int(sum([float(x) for x in vals]))

        if not parts:
            return (None, None)

        return (', '.join(parts), total_sum)
    except Exception:
        return (None, None)


def render_send_results(results: list):
    """Render a clean summary table for send results and per-result details.
    - results: list of {'contact':..., 'result': ...} as returned by messaging loop.
    """
    try:
        if not results:
            st.info('No send results to show')
            return
        rows = []
        for i, r in enumerate(results):
            contact = r.get('contact', {}) if isinstance(r, dict) else {}
            res = r.get('result', {}) if isinstance(r, dict) else {}
            ok = res.get('ok') if isinstance(res, dict) else None
            status_code = res.get('status_code') if isinstance(res, dict) else None
            # provider message and first recipient details
            prov_msg = None
            first_rec = {}
            try:
                j = res.get('json') if isinstance(res, dict) else None
                sms = j.get('SMSMessageData') if isinstance(j, dict) else None
                if isinstance(sms, dict):
                    prov_msg = sms.get('Message')
                    recs = sms.get('Recipients') or []
                    if recs:
                        first_rec = recs[0]
            except Exception:
                prov_msg = None

            num = first_rec.get('number') if isinstance(first_rec, dict) else None
            recip_status = first_rec.get('status') if isinstance(first_rec, dict) else None
            cost = first_rec.get('cost') if isinstance(first_rec, dict) else None
            message_id = first_rec.get('messageId') if isinstance(first_rec, dict) else None

            rows.append({
                'idx': i,
                'phone': contact.get('phone') or contact.get('phone_raw') or '',
                'student': contact.get('student_name',''),
                'exam': contact.get('exam_name',''),
                'total': contact.get('total'),
                'class_rank': contact.get('class_rank'),
                'overall_rank': contact.get('overall_rank'),
                'parent': contact.get('parent_name',''),
                'status_ok': ok,
                'status_code': status_code,
                'recipient_number': num,
                'recipient_status': recip_status,
                'cost': cost,
                'message_id': message_id,
                'provider_message': prov_msg,
            })

        df = pd.DataFrame(rows)

        # friendly/detailed status mapping using provider result payloads
        def _map_status_from_result(res_obj):
            try:
                # try to find recipient-level status
                j = res_obj.get('json') if isinstance(res_obj, dict) else None
                sms = j.get('SMSMessageData') if isinstance(j, dict) else None
                first_rec_local = {}
                if isinstance(sms, dict):
                    recs = sms.get('Recipients') or []
                    if recs:
                        first_rec_local = recs[0]

                recip_status = first_rec_local.get('status') if isinstance(first_rec_local, dict) else None
                if recip_status:
                    s = str(recip_status).lower()
                    if 'black' in s or 'block' in s:
                        return 'Blacklisted'
                    if 'success' in s or 'deliv' in s or s in ('true','1','100'):
                        return 'Delivered'
                    if 'queued' in s or 'sent' in s or 'accepted' in s:
                        return 'Sent'
                    if 'fail' in s or 'error' in s or 'reject' in s:
                        return 'Failed'

                # fallback to top-level flags
                if isinstance(res_obj, dict):
                    if res_obj.get('ok') is True:
                        # ok true but no recipient status -> treat as Sent
                        return 'Sent'
                    if res_obj.get('ok') is False:
                        # inspect error or status_code
                        st_code = res_obj.get('status_code')
                        if st_code:
                            try:
                                sc = int(st_code)
                                if sc >= 400:
                                    return f'Failed ({sc})'
                            except Exception:
                                pass
                        # generic failure
                        return 'Failed'

                # inspect provider-level message text for clues
                prov_msg_local = None
                try:
                    prov_msg_local = sms.get('Message') if isinstance(sms, dict) else None
                except Exception:
                    prov_msg_local = None
                if prov_msg_local and isinstance(prov_msg_local, str):
                    low = prov_msg_local.lower()
                    if 'blacklist' in low or 'blocked' in low:
                        return 'Blacklisted'
                    if 'sent to' in low or 'total cost' in low or 'success' in low:
                        return 'Sent'

                return 'Unknown'
            except Exception:
                return 'Unknown'

        status_details = [ _map_status_from_result(r.get('result', {})) for r in results ]
        df['status_detail'] = status_details
        # legacy quick 'sent' column for simple truthy display
        df['sent'] = df['recipient_status'].fillna(df['status_ok']).apply(lambda v: 'Success' if str(v).lower() in ('success','true','1','100') or str(v).startswith('Success') else str(v))
        display_cols = ['idx','phone','student','exam','total','class_rank','overall_rank','status_detail','sent','cost','message_id','provider_message']
        try:
            st.markdown(f"**Sent results: {len(rows)} entries**")
            st.dataframe(df[display_cols].fillna(''))
        except Exception:
            st.write(df[display_cols].fillna(''))

        # per-result expanders with raw JSON
        for i, r in enumerate(results):
            title = f"Result {i}: {r.get('contact',{}).get('student_name','')} — {r.get('contact',{}).get('phone','')}"
            with st.expander(title, expanded=False):
                try:
                    # redact sensitive fields before showing raw JSON
                    sr = copy.deepcopy(r)
                    # redact contact info
                    try:
                        c = sr.get('contact')
                        if isinstance(c, dict):
                            for k in ('phone','phone_raw','student_name','parent_name'):
                                if k in c and c.get(k):
                                    c[k] = '[REDACTED]'
                    except Exception:
                        pass
                    # redact phone numbers in provider/result payloads
                    try:
                        res = sr.get('result')
                        if isinstance(res, dict):
                            # redact recipients numbers in SMSMessageData if present
                            j = res.get('json')
                            if isinstance(j, dict):
                                sms = j.get('SMSMessageData')
                                if isinstance(sms, dict):
                                    recs = sms.get('Recipients') or []
                                    for recp in recs:
                                        if isinstance(recp, dict) and 'number' in recp:
                                            recp['number'] = '[REDACTED]'
                            # redact payload 'to' if present
                            payload = res.get('payload')
                            if isinstance(payload, dict) and 'to' in payload:
                                payload['to'] = '[REDACTED]'
                            # redact any plain-text fields that may contain the phone
                            if 'text' in res and isinstance(res['text'], str):
                                res['text'] = res['text'].replace('+254750332126', '[REDACTED]')
                    except Exception:
                        pass
                    st.json(sr)
                except Exception:
                    try:
                        # fallback: try to redact simple contact info then write
                        rr = copy.deepcopy(r)
                        if isinstance(rr.get('contact'), dict):
                            rr['contact'].pop('phone', None)
                            rr['contact'].pop('student_name', None)
                        st.write(rr)
                    except Exception:
                        st.write({'error': 'failed to render result'})
    except Exception as e:
        st.error('Failed to render send results: ' + str(e))


def _map_status_from_result(res_obj):
    """Map a provider result object (as stored in the log) to a friendly status.
    Conservative rules:
    - Mark Delivered only when the provider explicitly indicates delivery (e.g. 'delivered', 'deliv').
    - Treat general 'success' or 'accepted' as Sent (pending delivery confirmation).
    - Detect blacklist/block and failures.
    Returns one of: Delivered, Sent, Blacklisted, Failed, Unknown
    """
    try:
        j = res_obj.get('json') if isinstance(res_obj, dict) else None
        sms = j.get('SMSMessageData') if isinstance(j, dict) else None
        first_rec_local = {}
        if isinstance(sms, dict):
            recs = sms.get('Recipients') or []
            if recs:
                first_rec_local = recs[0]

        recip_status = first_rec_local.get('status') if isinstance(first_rec_local, dict) else None
        if recip_status:
            s = str(recip_status).lower()
            # explicit delivery markers (include common variants like 'dlvrd')
            if any(k in s for k in ('deliver','deliv','delivered','dlvrd','delivered_to','deliveredto','delivered_to_handset','delivered_to_network')):
                return 'Delivered'
            # blacklist/blocked
            if 'black' in s or 'block' in s:
                return 'Blacklisted'
            # explicit failures
            if 'fail' in s or 'error' in s or 'reject' in s or 'rejected' in s:
                return 'Failed'
            # success/accepted/sent/queued -> treat as Sent (not necessarily delivered)
            if 'success' in s or 'accepted' in s or 'queued' in s or 'sent' in s or s in ('true','1','100'):
                return 'Sent'

        # top-level flags
        if isinstance(res_obj, dict):
            if res_obj.get('ok') is True:
                return 'Sent'
            if res_obj.get('ok') is False:
                st_code = res_obj.get('status_code')
                if st_code:
                    try:
                        sc = int(st_code)
                        if sc >= 400:
                            return f'Failed ({sc})'
                    except Exception:
                        pass
                return 'Failed'

        # inspect provider message text for clues
        prov_msg_local = None
        try:
            prov_msg_local = sms.get('Message') if isinstance(sms, dict) else None
        except Exception:
            prov_msg_local = None
        if prov_msg_local and isinstance(prov_msg_local, str):
            low = prov_msg_local.lower()
            if 'blacklist' in low or 'blocked' in low:
                return 'Blacklisted'
            if any(k in low for k in ('delivered','deliv','dlvrd','delivered_to','deliveredto')):
                return 'Delivered'
            # 'sent to' / 'total cost' often means provider accepted the message
            if 'sent to' in low or 'total cost' in low or 'success' in low or 'accepted' in low:
                return 'Sent'

        return 'Unknown'
    except Exception:
        return 'Unknown'


def render_sent_messages_log(limit: int = 200):
    """Render an interactive audit log of sent messages read from LOG_FILE.
    - limit: number of most-recent entries to show
    """
    try:
        st.markdown('### Message audit log')
        if not LOG_FILE.exists():
            st.info('No sent messages log found.')
            return
        # controls: refresh, redact (Clear will be at the bottom as a prominent red button)
        c1, c2 = st.columns([1,1])
        with c1:
            refresh = st.button('Refresh statuses')
        with c2:
            redact = st.checkbox('Redact phone numbers', value=False)

        # clear confirmation state
        if 'confirm_clear_log' not in st.session_state:
            st.session_state['confirm_clear_log'] = False

        # clear confirmation is handled by a footer control to avoid accidental clicks
        if st.session_state.get('confirm_clear_log'):
            st.warning('You are about to permanently clear the sent messages log. This action is irreversible but an automatic backup will be created. Confirm to proceed.')
            ca, cb = st.columns([1,1])
            with ca:
                if st.button('Confirm clear log'):
                    try:
                        # backup
                        bak_dir = LOG_FILE.parent
                        tsstr = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                        bak_name = f"sent_messages_log.{tsstr}.bak.json"
                        bak_path = bak_dir / bak_name
                        shutil.copy(str(LOG_FILE), str(bak_path))
                        # clear
                        LOG_FILE.write_text('[]', encoding='utf-8')
                        st.success(f'Log cleared and backed up to {bak_name}')
                        st.session_state['confirm_clear_log'] = False
                        # reload
                        try:
                            raw = []
                        except Exception:
                            pass
                    except Exception as e:
                        st.error('Failed to clear log: ' + str(e))
            with cb:
                if st.button('Cancel'):
                    st.session_state['confirm_clear_log'] = False

        # load log
        try:
            raw = json.loads(LOG_FILE.read_text(encoding='utf-8'))
        except Exception:
            st.error('Failed to read log file')
            return

        if not isinstance(raw, list) or len(raw) == 0:
            st.info('No entries in the sent messages log.')
            return

        # load saved contacts so we can annotate rows with student/parent/class where possible
        contacts_list = load_contacts() if callable(load_contacts) else []
        # build quick lookup by phone (normalized forms)
        phone_map = {}
        def _norm_num(p):
            if not p: return ''
            s = str(p)
            # drop leading + and non-digits
            s = ''.join([c for c in s if c.isdigit()])
            # drop leading country code '0' prefixes if present? keep digits as-is
            return s

        for c in contacts_list:
            ph = c.get('phone') or c.get('phone_e164') or c.get('phone_raw') or c.get('mobile') or c.get('msisdn') or ''
            n = _norm_num(ph)
            if not n:
                continue
            phone_map.setdefault(n, []).append(c)

        # helper to find contact by phone (tries exact, longest suffix match)
        def find_contact_by_phone(ph):
            if not ph:
                return (None, None)
            n = _norm_num(ph)
            if not n:
                return (None, None)
            # exact
            if n in phone_map:
                return (phone_map.get(n)[0], 'exact')
            # longest suffix match: try decreasing lengths but prefer longer matches to avoid collisions
            best = None
            best_len = 0
            for k, lst in phone_map.items():
                if k == n:
                    return (lst[0], 'exact')
                if n.endswith(k) or k.endswith(n) or k.endswith(n[-9:]):
                    L = min(len(k), len(n))
                    if L > best_len:
                        best = lst[0]
                        best_len = L
            if best:
                return (best, f'suffix({best_len})')
            # fallback: try last 9,8,7 digits
            for L in (11,10,9,8,7):
                if len(n) > L:
                    key = n[-L:]
                    for k, lst in phone_map.items():
                        if k.endswith(key):
                            return (lst[0], f'suffix({L})')
            return (None, None)

        # build rows
        rows = []
        for e in raw[-limit:][::-1]:
            ph = e.get('phone') or e.get('to') or ''
            # student/parent/class may be stored at top-level or may not exist in older logs.
            student = e.get('student_name') or e.get('student') or ''
            parent = e.get('parent_name') or e.get('parent') or ''
            # class information if available
            cls = e.get('class') or e.get('class_name') or e.get('grade') or ''
            exam = e.get('exam_name') or ''
            # try to infer exam name from message if not present
            msg = e.get('message') or ''
            prov = e.get('provider') or ''
            ts = e.get('time')
            try:
                import datetime
                tstr = datetime.datetime.fromtimestamp(float(ts)).strftime('%Y-%m-%d %H:%M:%S') if ts else ''
            except Exception:
                tstr = str(ts)

            # raw provider recipient status (if present) e.g., 'Sent' vs 'Success'
            provider_status = ''
            try:
                res = e.get('response') or e.get('result') or {}
                j = res.get('json') if isinstance(res, dict) else None
                sms = j.get('SMSMessageData') if isinstance(j, dict) else None
                if isinstance(sms, dict):
                    recs = sms.get('Recipients') or []
                    if recs and isinstance(recs[0], dict):
                        provider_status = recs[0].get('status') or ''
                # fallback: top-level status_code or status field
                if not provider_status:
                    provider_status = res.get('status') or res.get('status_code') or ''
            except Exception:
                provider_status = ''

            status = _map_status_from_result(e.get('response') or e.get('result') or {})
            mid = None
            try:
                res = e.get('response') or e.get('result') or {}
                j = res.get('json') if isinstance(res, dict) else None
                sms = j.get('SMSMessageData') if isinstance(j, dict) else None
                if isinstance(sms, dict):
                    recs = sms.get('Recipients') or []
                    if recs:
                        mid = recs[0].get('messageId')
            except Exception:
                mid = None

            # if no student found in log entry, attempt to look up from contacts by phone
            resolved_by = ''
            if not student:
                # normalized phone key
                nph = _norm_num(ph)
                candidates = phone_map.get(nph, []) if nph else []
                # if we have candidates, try to disambiguate using the message text
                chosen = None
                chosen_note = None
                if candidates:
                    mlow = (msg or '').lower()
                    # prefer matching by explicit parent name parsed earlier (if available)
                    if parent:
                        parent_matches = []
                        for c in candidates:
                            pname = (c.get('parent_name') or c.get('parent') or c.get('guardian') or '').strip()
                            if pname and pname.lower() == parent.lower():
                                parent_matches.append(c)
                        # only auto-select if parent match is unambiguous (single candidate)
                        if len(parent_matches) == 1:
                            chosen = parent_matches[0]
                            chosen_note = 'matched_parent_field'
                    # first, look for an exact name occurrence in the message (student or parent)
                    if chosen is None:
                        # collect student name matches in message
                        student_matches = []
                        parent_text_matches = []
                        for c in candidates:
                            sname = (c.get('student_name') or c.get('student') or '').strip()
                            pname = (c.get('parent_name') or c.get('parent') or c.get('guardian') or '').strip()
                            if sname and sname.lower() in mlow:
                                student_matches.append(c)
                            if pname and pname.lower() in mlow:
                                parent_text_matches.append(c)
                        # prefer student name matches if unambiguous
                        if len(student_matches) == 1:
                            chosen = student_matches[0]
                            chosen_note = 'matched_in_message(student)'
                        # otherwise only accept a parent-text match when it's unambiguous
                        elif len(parent_text_matches) == 1:
                            chosen = parent_text_matches[0]
                            chosen_note = 'matched_in_message(parent)'
                    # if still ambiguous, prefer exact match by phone string form (non-normalized)
                    if chosen is None and len(candidates) == 1:
                        chosen = candidates[0]
                        chosen_note = 'exact_single'
                    # fallback to previous longest-suffix logic using find_contact_by_phone
                    if chosen is None:
                        found, note = find_contact_by_phone(ph)
                        if found:
                            chosen = found
                            chosen_note = note
                if chosen:
                    student = (chosen.get('student_name') or chosen.get('student') or student or '').strip()
                    parent = parent or chosen.get('parent_name') or chosen.get('guardian') or chosen.get('parent') or ''
                    cls = cls or chosen.get('class') or chosen.get('Class') or chosen.get('class_name') or chosen.get('grade') or chosen.get('form') or chosen.get('stream') or ''
                    resolved_by = chosen_note or ''
            # normalize student display
            if isinstance(student, str):
                student = student.strip()

            rows.append({'time': tstr, 'phone': ph, 'student': student, 'parent': parent, 'class': cls, 'exam': exam, 'message': msg, 'provider': prov, 'provider_status': provider_status, 'status': status, 'message_id': mid, 'resolved_by': resolved_by})

        df = pd.DataFrame(rows)
        if redact and 'phone' in df.columns:
            df['phone'] = df['phone'].apply(lambda v: '[REDACTED]' if v else '')

        # Render a compact HTML table with color-coded status for clarity
        try:
            def _status_color(s):
                if not s: return '#6b7280'  # gray
                ls = str(s).lower()
                if 'deliver' in ls:
                    return '#15803d'  # darker green for Delivered
                # treat Sent as green per user preference
                if 'sent' in ls or 'success' in ls or 'accepted' in ls:
                    return '#16a34a'  # green
                if 'black' in ls or 'block' in ls:
                    return '#dc2626'  # red
                if 'fail' in ls or 'error' in ls:
                    return '#991b1b'  # dark red
                return '#6b7280'

            html = ['<div style="overflow:auto"><table style="border-collapse:collapse; width:100%;">']
            html.append('<thead><tr><th style="text-align:left;padding:6px;border-bottom:1px solid #ddd;">Time</th><th style="text-align:left;padding:6px;border-bottom:1px solid #ddd;">Student</th><th style="text-align:left;padding:6px;border-bottom:1px solid #ddd;">Parent</th><th style="text-align:left;padding:6px;border-bottom:1px solid #ddd;">Class</th><th style="text-align:left;padding:6px;border-bottom:1px solid #ddd;">Phone</th><th style="text-align:left;padding:6px;border-bottom:1px solid #ddd;">Provider Status</th><th style="text-align:left;padding:6px;border-bottom:1px solid #ddd;">Status</th></tr></thead>')
            html.append('<tbody>')
            for _, r in df.iterrows():
                time = r.get('time','')
                stud = r.get('student','')
                resolved_by = r.get('resolved_by','')
                stud_disp = stud
                try:
                    if resolved_by:
                        stud_disp = f"{stud} <span style='color:#6b7280;font-size:0.85em'>({resolved_by})</span>"
                except Exception:
                    stud_disp = stud
                # parent name may be in the message payload; try to infer from stored message if available
                parent = ''
                try:
                    # if message string contains 'Dear <PARENT>,' extract naive parent name
                    m = r.get('message','') or ''
                    if 'dear ' in m.lower():
                        part = m.split(',',1)[0]
                        parent = part.replace('Dear','').strip()
                except Exception:
                    parent = ''
                phone = r.get('phone','')
                provider_stat = r.get('provider_status','')
                status = r.get('status','')
                # prefer coloring based on provider-reported status when available, otherwise mapped status
                color = _status_color(provider_stat or status)
                ph_display = phone if not redact else ('[REDACTED]' if phone else '')
                prov_display = provider_stat if provider_stat else ''
                class_display = r.get('class','')
                html.append(f"<tr><td style='padding:6px;border-bottom:1px solid #f3f4f6'>{time}</td><td style='padding:6px;border-bottom:1px solid #f3f4f6'>{stud_disp}</td><td style='padding:6px;border-bottom:1px solid #f3f4f6'>{parent}</td><td style='padding:6px;border-bottom:1px solid #f3f4f6'>{class_display}</td><td style='padding:6px;border-bottom:1px solid #f3f4f6'>{ph_display}</td><td style='padding:6px;border-bottom:1px solid #f3f4f6'>{prov_display}</td><td style='padding:6px;border-bottom:1px solid #f3f4f6'><span style='background:{color};color:white;padding:4px 8px;border-radius:6px'>{status}</span></td></tr>")
            html.append('</tbody></table></div>')
            st.markdown(''.join(html), unsafe_allow_html=True)
        except Exception:
            st.write(df)

        # Footer area: clear log as a prominent red button and page footer
        try:
            st.markdown('---')
            f1, f2 = st.columns([1,3])
            with f1:
                # decorative red button (HTML) for visual prominence
                st.markdown("<div class='clear-log-red'>Clear Log (Backup then erase)</div>", unsafe_allow_html=True)
                # actual actionable button (hidden label) - clicking triggers confirmation
                if st.button('Confirm Clear Log Action', key='clear_log_footer'):
                    st.session_state['confirm_clear_log'] = True
            with f2:
                st.markdown("<div style='text-align:right;color:#6b7280;'>© 2025 Eduscore Analytics</div>", unsafe_allow_html=True)
        except Exception:
            pass
        except Exception:
            st.write(df)

        # detail view for selected log entry
        try:
            sel = st.selectbox('Inspect entry (by index)', options=list(df.index.astype(str)), index=0)
            idx = int(sel)
            entry = raw[::-1][idx]
            # also show the annotated row from our table (if available)
            try:
                ann = df.iloc[idx].to_dict()
                if redact and 'phone' in ann:
                    ann['phone'] = '[REDACTED]'
                st.markdown('**Annotated row (resolved):**')
                st.json(ann)
            except Exception:
                pass
            # redact if requested
            if redact and isinstance(entry, dict):
                try:
                    if 'phone' in entry: entry['phone'] = '[REDACTED]'
                    if 'response' in entry and isinstance(entry['response'], dict):
                        j = entry['response'].get('json')
                        if isinstance(j, dict):
                            sms = j.get('SMSMessageData')
                            if isinstance(sms, dict):
                                recs = sms.get('Recipients') or []
                                for r in recs:
                                    if 'number' in r: r['number'] = '[REDACTED]'
                except Exception:
                    pass
            st.json(entry)
        except Exception:
            pass
    except Exception as e:
        st.error('Failed to render message log: ' + str(e))

def prepare_messages_action(sel_df, contacts_df_local, limit_val):
    """Prepare messages for the provided selection dataframe and contacts.
    This encapsulates the existing prepare logic so it can be invoked from multiple places.
    Results are written to st.session_state['prepared_messages'] and ['prepared_unmatched'].
    """
    prepared = []
    unmatched_overall = []

    # diagnostic counters
    total_exam_rows_scanned = 0
    valid_total_rows = 0
    merged_rows_total = 0
    merged_rows_with_phone = 0
    missing_total_count = 0
    missing_phone_count = 0

    def pick_default_cols(cols_list, candidates):
        for c in candidates:
            if c in cols_list:
                return c
        return cols_list[0] if cols_list else None

    for _, meta in sel_df.iterrows():
        exam_id = meta.get('exam_id')
        exam_name = meta.get('exam_name','')
        exam_path = BASE / exam_id / 'data.pkl'
        if not exam_path.exists():
            continue
        try:
            exdf = pd.read_pickle(exam_path)
        except Exception:
            continue

        cols = list(exdf.columns)
        match_col = pick_default_cols(cols, ['student_id','student','adm','adm_no','Admission','admno'])
        name_col = pick_default_cols(cols, ['student_name','name','Name','student','Student','student full name','Student Name'])
        score_col = pick_default_cols(cols, ['TOTALS','TOTAL','Total','total','Score','score','Total Marks','Marks','Total_Marks'])
        class_col_in = pick_default_cols(cols, ['Class','class','class_name','className','Grade','GRADE'])

        numeric_subjects = []
        for c in cols:
            if c in {match_col,name_col,score_col,class_col_in}:
                continue
            # skip rank/position columns which are not subject marks
            try:
                lc = str(c).lower()
                if 'rank' in lc or 'position' in lc or lc.strip() in ('s/rank', 's_rank', 's rank'):
                    continue
            except Exception:
                pass
            try:
                if pd.to_numeric(exdf[c], errors='coerce').notna().sum() > 0:
                    numeric_subjects.append(c)
            except Exception:
                continue

        # compute ranks
        try:
            tmp = exdf.copy()
            tmp[score_col] = pd.to_numeric(tmp[score_col], errors='coerce')
            tmp['overall_rank'] = tmp[score_col].rank(ascending=False, method='min')
            if class_col_in in tmp.columns:
                tmp['class_rank'] = tmp.groupby(class_col_in)[score_col].rank(ascending=False, method='min')
            else:
                tmp['class_rank'] = None
        except Exception:
            tmp = exdf.copy()
            tmp['overall_rank'] = None
            tmp['class_rank'] = None

        # drop exam rows with missing/invalid totals
        try:
            if score_col in tmp.columns:
                before_count = len(tmp)
                tmp = tmp[pd.to_numeric(tmp[score_col], errors='coerce').notna()].copy()
                after_count = len(tmp)
                total_exam_rows_scanned += before_count
                valid_total_rows += after_count
                missing_total_count += (before_count - after_count)
            else:
                if 'Total' in tmp.columns:
                    before_count = len(tmp)
                    tmp = tmp[pd.to_numeric(tmp['Total'], errors='coerce').notna()].copy()
                    after_count = len(tmp)
                    total_exam_rows_scanned += before_count
                    valid_total_rows += after_count
                    missing_total_count += (before_count - after_count)
        except Exception:
            pass

        # Merge exam rows (t) with contacts (c) -> exam-driven
        try:
            c = contacts_df_local.copy()
            c['__name_norm'] = c.get('student_name','').astype(str).str.lower().str.replace(r"\s+", ' ', regex=True).str.strip()
            c = c.drop_duplicates(subset=['__name_norm'], keep='first')

            t = tmp.copy()
            if name_col in t.columns:
                t['__name_norm'] = t[name_col].astype(str).str.lower().str.replace(r"\s+", ' ', regex=True).str.strip()
            else:
                t['__name_norm'] = t.index.astype(str)

            merged = t.merge(c, on='__name_norm', how='left')
            # diagnostic
            try:
                merged_rows_total += len(merged)
                def _has_phone(r):
                    rp = r.get('phone') if 'phone' in r else r.get('phone_raw')
                    try:
                        if pd.isna(rp):
                            return False
                    except Exception:
                        pass
                    if rp is None:
                        return False
                    s = str(rp).strip().lower()
                    return s not in ('', 'nan', 'none')
                merged_with_phone_count = merged.apply(_has_phone, axis=1).sum()
                merged_rows_with_phone += int(merged_with_phone_count)
            except Exception:
                pass
        except Exception:
            merged = tmp.copy()

        # filter by selected classes
        try:
            if st.session_state.get('class_sel', None):
                sel_norms = [str(x).lower().replace('grade ', '').strip() for x in st.session_state.get('class_sel')]
                def _matches(row):
                    exam_cv = str(row.get(class_col_in, '')).lower()
                    if exam_cv and exam_cv != 'nan':
                        for s in sel_norms:
                            if not s:
                                continue
                            if s == exam_cv or s in exam_cv or exam_cv in s:
                                return True
                            if s.isdigit() and s in exam_cv:
                                return True
                        return False
                    cgrade = str(row.get('grade', '')).lower()
                    cstream = str(row.get('stream', '')).lower()
                    for s in sel_norms:
                        if not s:
                            continue
                        if s == cgrade or s in cgrade:
                            return True
                        if s == cstream or s in cstream:
                            return True
                    return False
                merged = merged[merged.apply(_matches, axis=1)].copy()
        except Exception:
            pass

        # apply recipient limit per exam
        try:
            if limit_val and int(limit_val) > 0:
                merged = merged.head(int(limit_val))
        except Exception:
            pass

        # compute sizes
        try:
            overall_size = int(len(tmp))
        except Exception:
            overall_size = None
        class_counts = {}
        try:
            if class_col_in in tmp.columns:
                class_counts = tmp.groupby(class_col_in).size().to_dict()
        except Exception:
            class_counts = {}

        for _, row in merged.iterrows():
            # normalize phone
            raw_phone = None
            if 'phone' in row:
                raw_phone = row.get('phone')
            elif 'phone_raw' in row:
                raw_phone = row.get('phone_raw')
            try:
                if pd.isna(raw_phone):
                    phone = None
                else:
                    phone = str(raw_phone).strip()
                    if phone.lower() in ('', 'nan', 'none'):
                        phone = None
            except Exception:
                phone = str(raw_phone).strip() if raw_phone is not None else None

            student_name_val = None
            if name_col in row and pd.notna(row.get(name_col)):
                student_name_val = row.get(name_col)
            elif 'student_name' in row and pd.notna(row.get('student_name')):
                student_name_val = row.get('student_name')
            else:
                student_name_val = ''

            if not phone or str(phone).strip() == '':
                missing_phone_count += 1
                unmatched_overall.append({'exam_id': exam_id, 'exam_name': exam_name, 'student_name': student_name_val, 'reason': 'missing_phone'})
                continue

            parts = []
            for s in numeric_subjects:
                try:
                    v = row.get(s)
                    if pd.isna(v) or v is None:
                        continue
                    parts.append(f"{s}: {v}")
                except Exception:
                    continue
            subj_str = ', '.join(parts)

            total_val = None
            try:
                if score_col in row and pd.notna(row.get(score_col)):
                    total_val = pd.to_numeric(row.get(score_col), errors='coerce')
                    if pd.notna(total_val):
                        total_val = int(total_val)
                    else:
                        total_val = None
                elif 'Total' in row and pd.notna(row.get('Total')):
                    tmp_total = pd.to_numeric(row.get('Total'), errors='coerce')
                    total_val = int(tmp_total) if pd.notna(tmp_total) else None
            except Exception:
                total_val = None

            if total_val is None:
                missing_total_count += 1
                unmatched_overall.append({'exam_id': exam_id, 'exam_name': exam_name, 'student_name': student_name_val, 'reason': 'missing_total'})
                continue

            try:
                class_rank_raw = row.get('class_rank') if 'class_rank' in row else None
                overall_rank_raw = row.get('overall_rank') if 'overall_rank' in row else None
                class_rank = int(class_rank_raw) if pd.notna(class_rank_raw) else None
                overall_rank = int(overall_rank_raw) if pd.notna(overall_rank_raw) else None
            except Exception:
                class_rank = None
                overall_rank = None

            try:
                cls_key = row.get(class_col_in) if class_col_in in row else None
                class_size = int(class_counts.get(cls_key, 0)) if cls_key is not None else None
            except Exception:
                class_size = None

            class_rank_str = f"{class_rank}/{class_size}" if class_rank is not None and class_size else (str(class_rank) if class_rank is not None else 'N/A')
            overall_rank_str = f"{overall_rank}/{overall_size}" if overall_rank is not None and overall_size else (str(overall_rank) if overall_rank is not None else 'N/A')

            parent = row.get('parent_name','') or ''
            student = student_name_val or ''

            message_text = f"Dear {parent}, Results for {student} — {exam_name}. {subj_str}. Total: {total_val if total_val is not None else 'N/A'}. Class Rank: {class_rank_str}. Overall Rank: {overall_rank_str}."

            prepared.append({'phone': phone, 'message': message_text, 'student_name': student, 'exam_id': exam_id, 'exam_name': exam_name, 'total': total_val, 'class_rank': class_rank, 'class_size': class_size, 'overall_rank': overall_rank, 'overall_size': overall_size})

    # filter out prepared messages with empty/None/NaN totals (extra safety)
    try:
        filtered_prepared = [p for p in prepared if not pd.isna(p.get('total'))]
    except Exception:
        filtered_prepared = [p for p in prepared if p.get('total') is not None and str(p.get('total')).strip() != '']

    st.session_state['prepared_messages'] = filtered_prepared
    st.session_state['prepared_unmatched'] = unmatched_overall
    st.session_state['prepare_diagnostics'] = {'total_exam_rows_scanned': total_exam_rows_scanned, 'valid_total_rows': valid_total_rows, 'missing_total_rows': missing_total_count, 'merged_rows_total': merged_rows_total, 'merged_rows_with_phone': merged_rows_with_phone, 'missing_phone_count': missing_phone_count, 'prepared_count': len(filtered_prepared)}

    return st.session_state['prepare_diagnostics']


# Messaging configuration is admin-managed and not shown to school users
st.sidebar.info('Messaging configuration is managed centrally by the system administrator and is not visible to schools.')


# Load contacts
contacts = load_contacts()
contacts_df = pd.DataFrame(contacts)
if contacts_df.empty:
    st.info('No contacts found. Add them on the Parent Contacts page first.')
    st.stop()


# Controls
cols = st.columns([3,1])
with cols[1]:
    # UI for limiting recipients per exam removed per user request; default to 0 (all recipients)
    limit = 0


# Load exam metadata
exams_meta = {}
if META_FILE.exists():
    try:
        exams_meta = json.loads(META_FILE.read_text(encoding='utf-8'))
    except Exception:
        exams_meta = {}

if not exams_meta:
    st.info('No saved exams metadata found. Save exams first or upload an exam CSV.')
    st.stop()

meta_df = pd.DataFrame([v for v in exams_meta.values()])
# Year / Term / Kind selectors
years = sorted(meta_df['year'].unique())
year_sel = st.selectbox('Year', options=['All'] + [str(y) for y in years], index=0)
term_options = sorted(meta_df['term'].unique())
term_sel = st.selectbox('Term', options=['All'] + term_options, index=0)
# derive exam kinds from exam_name (prefix before '-')
def kind_of(name):
    return name.split('-')[0].strip() if isinstance(name, str) and '-' in name else name
meta_df['kind'] = meta_df['exam_name'].apply(kind_of)
kind_options = sorted(meta_df['kind'].unique())
kind_sel = st.selectbox('Exam kind', options=['All'] + kind_options, index=0)
class_options = sorted(meta_df['class_name'].unique())
class_sel = st.multiselect('Classes to include (choose one or more)', options=class_options, default=class_options)


# Filter metadata
sel = meta_df.copy()
if year_sel != 'All':
    sel = sel[sel['year'] == int(year_sel)]
if term_sel != 'All':
    sel = sel[sel['term'] == term_sel]
if kind_sel != 'All':
    sel = sel[sel['kind'] == kind_sel]
if class_sel:
    sel = sel[sel['class_name'].isin(class_sel)]

st.markdown(f"Found {len(sel)} saved exams matching filters")

if sel.empty:
    st.info('No saved exams match the selected filters.')
else:
    sel = sel.sort_values(['class_name','exam_name'])
    try:
        st.markdown('### Matching saved exams')
        st.dataframe(sel[['exam_id','exam_name','class_name','year','term']].reset_index(drop=True))
    except Exception:
        pass

    if st.button('Prepare messages for all matching exams'):
        # call the centralized prepare action so it can be reused elsewhere
        diagnostics = prepare_messages_action(sel, contacts_df, limit)
        # ensure quick-send panel moves down after preparing so it appears below the last feature
        try:
            st.session_state['move_quick_send_down'] = True
        except Exception:
            st.session_state.update({'move_quick_send_down': True})
        try:
            st.success(f"Prepared {diagnostics.get('prepared_count',0)} messages across {len(sel)} exams. {diagnostics.get('missing_phone_count',0)} students missing phone numbers.")
            # present a compact, friendly diagnostics summary
            with st.expander('Preparation summary', expanded=True):
                try:
                    cols = st.columns(4)
                    metrics = [
                        ('Total exam rows scanned', 'total_exam_rows_scanned'),
                        ('Valid total rows', 'valid_total_rows'),
                        ('Missing total rows', 'missing_total_count'),
                        ('Merged rows total', 'merged_rows_total'),
                        ('Merged rows with phone', 'merged_rows_with_phone'),
                        ('Missing phone count', 'missing_phone_count'),
                        ('Prepared count', 'prepared_count'),
                    ]
                    for i, (label, key) in enumerate(metrics):
                        try:
                            val = diagnostics.get(key, 0)
                        except Exception:
                            val = 0
                        cols[i % 4].metric(label, str(val))
                except Exception:
                    st.write(diagnostics)
        except Exception:
            pass

    # After preparing messages we persist them to session_state. Render preview and confirm-send
    # sanitize any existing prepared messages in session_state: remove entries with missing totals
    _existing_prepared = st.session_state.get('prepared_messages', [])
    try:
        sanitized = [p for p in _existing_prepared if (p.get('total') is not None and not pd.isna(p.get('total')))]
    except Exception:
        sanitized = [p for p in _existing_prepared if p.get('total') is not None and str(p.get('total')).strip() != '']
    if len(sanitized) != len(_existing_prepared):
        st.session_state['prepared_messages'] = sanitized

    # ensure the move flag exists
    if 'move_quick_send_down' not in st.session_state:
        st.session_state['move_quick_send_down'] = False

    # Render a compact Quick-send form immediately under the Prepare button so
    # users can access send features without pressing Prepare. This duplicates the
    # compact send UI that also exists later, but uses unique widget keys so both
    # locations can coexist safely.
    if not st.session_state.get('move_quick_send_down', False):
        # build a recipient_pool similar to the later full-panel logic so the compact
        # form works even when Prepare hasn't been run.
        prepared_list_top = st.session_state.get('prepared_messages', []) or []
        unmatched_list_top = st.session_state.get('prepared_unmatched', []) or []
        normalized_unmatched_top = []
        for u in unmatched_list_top:
            normalized_unmatched_top.append({'phone': u.get('phone') or u.get('phone_raw') or '', 'message': '', 'student_name': u.get('student_name',''), 'exam_id': u.get('exam_id',''), 'exam_name': u.get('exam_name',''), 'total': None, 'class_rank': None, 'class_size': None, 'overall_rank': None, 'overall_size': None})

        if prepared_list_top:
            recipient_pool_top = prepared_list_top + normalized_unmatched_top
        else:
            recipient_pool_top = []
            try:
                contacts_list_top = load_contacts()
            except Exception:
                contacts_list_top = []

            def _pick_name_col_local(cols_list):
                candidates = ['student_name','name','Name','student','Student','student full name','Student Name']
                for c in candidates:
                    if c in cols_list:
                        return c
                return cols_list[0] if cols_list else None

            for _, mrow in meta_df.iterrows():
                exam_id = mrow.get('exam_id')
                exam_name = mrow.get('exam_name')
                exam_path = BASE / exam_id / 'data.pkl'
                if not exam_path.exists():
                    continue
                try:
                    exdf = pd.read_pickle(exam_path)
                except Exception:
                    continue
                name_col_local = _pick_name_col_local(list(exdf.columns))
                parent_col_local = None
                for pc in ('parent_name','Parent','parent'):
                    if pc in exdf.columns:
                        parent_col_local = pc
                        break

                for _, erow in exdf.iterrows():
                    student_name = str(erow.get(name_col_local,'')).strip()
                    parent_name = str(erow.get(parent_col_local,'')) if parent_col_local else ''
                    name_norm = student_name.lower().replace('\n',' ').strip()
                    found = next((c for c in contacts_list_top if str(c.get('student_name','')).lower().strip() == name_norm), None)
                    phone = ''
                    p_parent = ''
                    if found:
                        phone = found.get('phone') or found.get('phone_raw') or ''
                        p_parent = found.get('parent_name') or ''
                    parent_final = p_parent or parent_name or ''
                    recipient_pool_top.append({'phone': phone, 'message': '', 'student_name': student_name, 'exam_id': exam_id, 'exam_name': exam_name, 'total': None, 'class_rank': None, 'class_size': None, 'overall_rank': None, 'overall_size': None, 'parent_name': parent_final})

        # Build exam metadata map to power the top filters
        try:
            exam_meta_map_top = meta_df.set_index('exam_id')[[ 'year', 'term', 'kind', 'class_name']].to_dict('index')
        except Exception:
            exam_meta_map_top = {}

        top_years = sorted({str(exam_meta_map_top.get(p.get('exam_id'), {}).get('year')) for p in recipient_pool_top if exam_meta_map_top.get(p.get('exam_id'))})
        top_terms = sorted({str(exam_meta_map_top.get(p.get('exam_id'), {}).get('term')) for p in recipient_pool_top if exam_meta_map_top.get(p.get('exam_id'))})
        top_kinds = sorted({str(exam_meta_map_top.get(p.get('exam_id'), {}).get('kind')) for p in recipient_pool_top if exam_meta_map_top.get(p.get('exam_id'))})
        top_classes = sorted({str(exam_meta_map_top.get(p.get('exam_id'), {}).get('class_name')) for p in recipient_pool_top if exam_meta_map_top.get(p.get('exam_id'))})

        # Top compact quick-send form (unique keys)
        with st.form('compact_quick_send_form_top'):
            st.markdown('## Quick send to recipients')
            # Filter selectors: Year, Term, Exam kind, Class
            cy1, cy2, cy3, cy4 = st.columns([1,1,1,1])
            with cy1:
                top_year = st.selectbox('Year (recipients)', options=['All'] + [y for y in top_years if y and y != 'None'], index=0, key='top_year')
            with cy2:
                top_term = st.selectbox('Term (recipients)', options=['All'] + [t for t in top_terms if t and t != 'None'], index=0, key='top_term')
            with cy3:
                top_kind = st.selectbox('Exam kind (recipients)', options=['All'] + [k for k in top_kinds if k and k != 'None'], index=0, key='top_kind')
            with cy4:
                top_class = st.selectbox('Class (recipients)', options=['All'] + [c for c in top_classes if c and c != 'None'], index=0, key='top_class')

            # Build labels for the compact top form honoring selected filters
            labels_top = []
            for i, p in enumerate(recipient_pool_top):
                nm = p.get('student_name') or ''
                ex = p.get('exam_name') or ''
                ph = p.get('phone') or ''
                keep = True
                meta = exam_meta_map_top.get(p.get('exam_id'), {})
                if top_year != 'All' and meta.get('year') is not None and str(meta.get('year')) != top_year:
                    keep = False
                if top_term != 'All' and meta.get('term') is not None and str(meta.get('term')) != top_term:
                    keep = False
                if top_kind != 'All' and meta.get('kind') is not None and str(meta.get('kind')) != top_kind:
                    keep = False
                if top_class != 'All' and meta.get('class_name') is not None and str(meta.get('class_name')) != top_class:
                    keep = False
                if keep:
                    labels_top.append(f"{i}: {nm} — {ex} ({ph})")

            compact_selected_top = st.multiselect('Select recipients to send (only these will be sent)', options=labels_top, default=[], key='compact_select_top')
            try:
                compact_indices_top = [int(s.split(':',1)[0]) for s in compact_selected_top]
            except Exception:
                compact_indices_top = []

            st.markdown(f'**Selected (in form):** {len(compact_indices_top)}')

            for idx in compact_indices_top:
                p = recipient_pool_top[idx]
                st.markdown(f"**{p.get('student_name','')} — {p.get('exam_name','')}**")
                c1, c2 = st.columns([2,2])
                with c1:
                    st.text_input(f'Phone for {idx}', value=str(p.get('phone') or ''), key=f'compact_phone_top_{idx}')
                with c2:
                    st.text_input(f'Parent name for {idx}', value=str(p.get('parent_name') or ''), key=f'compact_parent_top_{idx}')

            compact_apply_top = st.form_submit_button('Apply selection', key='compact_apply_top')

        if compact_apply_top:
            st.session_state['applied_selected_labels_top'] = compact_selected_top
            applied_ed_top = {}
            for idx in compact_indices_top:
                phone_val = st.session_state.get(f'compact_phone_top_{idx}', '')
                parent_val = st.session_state.get(f'compact_parent_top_{idx}', '')
                if phone_val or parent_val:
                    applied_ed_top[str(idx)] = {'phone': phone_val, 'parent_name': parent_val}
            st.session_state['applied_edits_top'] = applied_ed_top

        applied_labels_top = st.session_state.get('applied_selected_labels_top', []) or []
        applied_edits_top = st.session_state.get('applied_edits_top', {}) or {}
        try:
            applied_indices_top = [int(s.split(':',1)[0]) for s in applied_labels_top]
        except Exception:
            applied_indices_top = []

        st.markdown(f'**Applied selection:** {len(applied_indices_top)}')
        if applied_indices_top:
            try:
                first = applied_indices_top[0]
                base = recipient_pool_top[first].get('message') or ''
                ed = applied_edits_top.get(str(first), {})
                if ed.get('parent_name') and base.lower().startswith('dear'):
                    parts = base.split(',',1)
                    if len(parts) > 1:
                        base = f"Dear {ed.get('parent_name')}," + parts[1]
                # if there's no prepared message, attempt to build a preview from exam data
                if not base:
                    try:
                        preview_try = build_preview_message(recipient_pool_top[first])
                        if preview_try:
                            base = preview_try
                    except Exception:
                        pass
                st.markdown('#### Message preview (first selected)')
                st.code(base)
                # top debug buttons removed per user request
            except Exception:
                pass

        if applied_indices_top:
            if st.button('Send selected messages', key='compact_send_top'):
                st.session_state['compact_pending_send_top'] = True

        if st.session_state.get('compact_pending_send_top'):
            st.warning('You are about to send messages to the applied recipients. Recipients without phone numbers will be skipped.')
            cs1, cs2 = st.columns([1,1])
            with cs1:
                if st.button('Confirm — Send now', key='compact_confirm_top'):
                    to_send = []
                    skipped = []
                    try:
                        contacts_list = load_contacts()
                    except Exception:
                        contacts_list = []

                    for i in applied_indices_top:
                        rec = dict(recipient_pool_top[i])
                        edits = applied_edits_top.get(str(i), {})
                        if edits.get('phone'):
                            rec['phone'] = edits.get('phone')
                        if edits.get('parent_name'):
                            rec['parent_name'] = edits.get('parent_name')
                        if not rec.get('phone'):
                            skipped.append(rec.get('student_name',''))
                            continue
                        to_send.append(rec)
                        nm_norm = str(rec.get('student_name','')).lower().strip()
                        found = None
                        for c in contacts_list:
                            if str(c.get('student_name','')).lower().strip() == nm_norm:
                                found = c
                                break
                        if found is not None:
                            if rec.get('phone'):
                                found['phone_raw'] = rec.get('phone')
                                found['phone'] = rec.get('phone')
                            if rec.get('parent_name'):
                                found['parent_name'] = rec.get('parent_name')
                        else:
                            contacts_list.append({'student_id':'','student_name':rec.get('student_name',''), 'grade':'', 'stream':'', 'parent_name': rec.get('parent_name') or '', 'phone_raw': rec.get('phone') or '', 'phone': rec.get('phone') or ''})

                    if skipped:
                        st.warning(f"Skipped {len(skipped)} recipients with no phone: {', '.join(skipped[:10])}{'...' if len(skipped)>10 else ''}")
                    if not to_send:
                        st.info('No recipients with phone numbers to send to.')
                    else:
                        try:
                            CONTACTS_FILE.write_text(json.dumps(contacts_list, indent=2), encoding='utf-8')
                        except Exception:
                            pass
                        cfg = load_config()
                        results = []
                        with st.spinner(f'Sending {len(to_send)} messages...'):
                            for c in to_send:
                                msg = c.get('message') or ''
                                if not msg:
                                    try:
                                        msg = build_preview_message(c) or ''
                                    except Exception:
                                        msg = ''
                                    if not msg:
                                        # try to extract subject parts (relaxed) so sent message includes marks when available
                                        try:
                                            subj, tot = compute_subject_parts(c, min_subjects=1)
                                            if subj:
                                                total_disp = tot if tot is not None else 'N/A'
                                                msg = f"Dear {c.get('parent_name','')}, Results for {c.get('student_name','')} — {c.get('exam_name')}. {subj}. Total: {total_disp}."
                                            else:
                                                msg = f"Dear {c.get('parent_name','')}, Results for {c.get('student_name','')} — {c.get('exam_name')}. Total: {c.get('total') if c.get('total') is not None else 'N/A'}."
                                        except Exception:
                                            msg = f"Dear {c.get('parent_name','')}, Results for {c.get('student_name','')} — {c.get('exam_name')}. Total: {c.get('total') if c.get('total') is not None else 'N/A'}."
                                res = messaging.send_single(c.get('phone'), msg, config=cfg, test_mode=False)
                                results.append({'contact': c, 'result': res})
                        st.success(f"Sent {len(results)} messages")
                        render_send_results(results)
                    st.session_state['compact_pending_send_top'] = False

            with cs2:
                if st.button('Cancel', key='compact_cancel_top'):
                    st.session_state['compact_pending_send_top'] = False

    prepared = st.session_state.get('prepared_messages', [])
    unmatched = st.session_state.get('prepared_unmatched', [])

    # move any prepared entries that lack phone numbers into unmatched
    try:
        prepared_with_phone = []
        moved_count = 0
        for p in prepared:
            raw_ph = p.get('phone') if p.get('phone') is not None else p.get('phone_raw')
            try:
                if pd.isna(raw_ph):
                    ph = None
                else:
                    ph = str(raw_ph).strip()
                    if ph.lower() in ('', 'nan', 'none'):
                        ph = None
            except Exception:
                ph = str(raw_ph).strip() if raw_ph is not None else None

            if ph:
                prepared_with_phone.append(p)
            else:
                moved_count += 1
                unmatched.append({'exam_id': p.get('exam_id'), 'exam_name': p.get('exam_name'), 'student_name': p.get('student_name'), 'reason': 'missing_phone'})

        if moved_count > 0:
            st.session_state['prepared_messages'] = prepared_with_phone
            st.session_state['prepared_unmatched'] = unmatched
            prepared = prepared_with_phone
    except Exception:
        # fallback: leave prepared as-is
        pass
    if prepared:
        st.markdown('### Prepared messages')
        # Build a dataframe for display with friendly rank strings
        try:
            preview_df = pd.DataFrame(prepared)
            preview_df['class_rank_str'] = preview_df.apply(lambda r: f"{int(r['class_rank'])}/{int(r['class_size'])}" if (r.get('class_rank') is not None and r.get('class_size')) else (str(int(r['class_rank'])) if r.get('class_rank') is not None else 'N/A'), axis=1)
            preview_df['overall_rank_str'] = preview_df.apply(lambda r: f"{int(r['overall_rank'])}/{int(r['overall_size'])}" if (r.get('overall_rank') is not None and r.get('overall_size')) else (str(int(r['overall_rank'])) if r.get('overall_rank') is not None else 'N/A'), axis=1)
            display_df = preview_df[['student_name','exam_name','phone','total','class_rank_str','overall_rank_str']].rename(columns={'student_name':'Student','exam_name':'Exam','phone':'Phone','total':'Total','class_rank_str':'Class Rank','overall_rank_str':'Overall Rank'})
        except Exception:
            display_df = pd.DataFrame(prepared)

        st.dataframe(display_df.reset_index(drop=True))

        # --- Bulk-send control for all prepared messages (appears immediately under the prepared table) ---
        if st.button(f"Send all prepared messages ({len(prepared)})", key='send_all_prepared'):
            if not prepared:
                st.warning('No prepared messages to send.')
            else:
                st.session_state['pending_bulk_send'] = True

        if st.session_state.get('pending_bulk_send'):
            st.warning('You are about to send ALL prepared messages. This will deliver SMS to real phone numbers.')
            c1, c2 = st.columns([1,1])
            with c1:
                if st.button('Confirm — Send ALL now', key='confirm_send_all'):
                    try:
                        contacts_list = load_contacts()
                    except Exception:
                        contacts_list = []

                    to_send = []
                    for rec in prepared:
                        r = dict(rec)
                        to_send.append(r)
                        nm_norm = str(r.get('student_name','')).lower().strip()
                        found = None
                        for c in contacts_list:
                            if str(c.get('student_name','')).lower().strip() == nm_norm:
                                found = c
                                break
                        if found is not None:
                            if r.get('phone'):
                                found['phone_raw'] = r.get('phone')
                                found['phone'] = r.get('phone')
                            if r.get('parent_name'):
                                found['parent_name'] = r.get('parent_name')
                        else:
                            contacts_list.append({'student_id':'','student_name':r.get('student_name',''), 'grade':'', 'stream':'', 'parent_name': r.get('parent_name') or '', 'phone_raw': r.get('phone') or '', 'phone': r.get('phone') or ''})

                    try:
                        CONTACTS_FILE.write_text(json.dumps(contacts_list, indent=2), encoding='utf-8')
                    except Exception:
                        pass

                    # filter out recipients with no phone to avoid provider errors
                    filtered_to_send = [r for r in to_send if r.get('phone') and str(r.get('phone')).strip()]
                    skipped = [r.get('student_name','') for r in to_send if not (r.get('phone') and str(r.get('phone')).strip())]
                    if skipped:
                        st.warning(f"Skipped {len(skipped)} recipients with no phone: {', '.join(skipped[:10])}{'...' if len(skipped)>10 else ''}")
                    if not filtered_to_send:
                        st.info('No recipients with phone numbers to send to.')
                    else:
                        cfg = load_config()
                        results = []
                        with st.spinner(f'Sending {len(filtered_to_send)} messages...'):
                            for c in filtered_to_send:
                                msg = c.get('message') or ''
                                # fallback message if none present; try building from exam data first
                                if not msg:
                                    try:
                                        msg = build_preview_message(c) or ''
                                    except Exception:
                                        msg = ''
                                    if not msg:
                                        try:
                                            subj, tot = compute_subject_parts(c, min_subjects=1)
                                            if subj:
                                                total_disp = tot if tot is not None else 'N/A'
                                                msg = f"Dear {c.get('parent_name','')}, Results for {c.get('student_name','')} — {c.get('exam_name','')}. {subj}. Total: {total_disp}."
                                            else:
                                                msg = f"Dear {c.get('parent_name','')}, Results for {c.get('student_name','')} — {c.get('exam_name','')}. Total: {c.get('total') if c.get('total') is not None else 'N/A'}."
                                        except Exception:
                                            msg = f"Dear {c.get('parent_name','')}, Results for {c.get('student_name','')} — {c.get('exam_name','')}. Total: {c.get('total') if c.get('total') is not None else 'N/A'}."
                                res = messaging.send_single(c.get('phone'), msg, config=cfg, test_mode=False)
                                results.append({'contact': c, 'result': res})
                        st.success('Done')
                        render_send_results(results)
                    st.session_state['pending_bulk_send'] = False

            with c2:
                if st.button('Cancel', key='cancel_send_all'):
                    st.session_state['pending_bulk_send'] = False

        # selection controls: present selector in a modal/popover for better UX
        labels = []
        for i, p in enumerate(prepared):
            nm = p.get('student_name') or ''
            ex = p.get('exam_name') or ''
            ph = p.get('phone') or ''
            labels.append(f"{i}: {nm} — {ex} ({ph})")

        # persist selected labels in session_state across reruns
        if 'selected_labels' not in st.session_state:
            st.session_state['selected_labels'] = labels.copy()

        # Persist selected labels and compute selected indices (selection UI moved to bottom of page)
        if 'selected_labels' not in st.session_state:
            st.session_state['selected_labels'] = labels.copy()
        selected_labels = st.session_state.get('selected_labels', labels)
        try:
            selected_indices = [int(s.split(':',1)[0]) for s in selected_labels if s in labels]
        except Exception:
            selected_indices = [i for i in range(len(prepared))]

        st.markdown(f"**Selected to send (choose recipients at the bottom):** {len(selected_indices)} / {len(prepared)} — **Missing phone:** {len(unmatched)}")

        # Manage missing phones: show a pop-over/modal when available, otherwise use sidebar fallback.
        def _render_missing_ui(container):
            """Render the manage-missing-phones UI into the provided container (st, modal, or st.sidebar).
            This function uses only the provided container for all UI elements so it can be rendered inside a modal or the sidebar.
            """
            container.markdown('### Manage missing phones')
            container.markdown('Filter by class and add phone numbers. Click "Load list" to gather unmatched students (fast).')

            # Prepare a minimal mapping of unmatched entries by exam_id to avoid repeated file reads
            # Instead of relying only on previously prepared_unmatched, proactively scan the selected
            # exams for students without phones so the user sees the full list immediately.
            unmatched_by_exam = {}
            # start with any existing unmatched (if present)
            for u in unmatched:
                eid = u.get('exam_id')
                unmatched_by_exam.setdefault(eid, []).append(u)

            # Also scan selected exams (sel) to find any students in the selected classes lacking phones
            try:
                # contacts lookup
                try:
                    current_contacts = load_contacts()
                except Exception:
                    current_contacts = []

                contact_name_set = {str(c.get('student_name','')).lower().strip(): c for c in current_contacts}

                # iterate selected exams (sel is the filtered meta dataframe in outer scope)
                for _, meta2 in sel.iterrows():
                    exam_id2 = meta2.get('exam_id')
                    exam_name2 = meta2.get('exam_name','')
                    ep = BASE / exam_id2 / 'data.pkl'
                    if not ep.exists():
                        continue
                    try:
                        exdf2 = pd.read_pickle(ep)
                    except Exception:
                        continue

                    # identify name and score columns
                    name_candidates = ['student_name','name','Name','student','Student','student full name','Student Name']
                    score_candidates = ['TOTALS','TOTAL','Total','total','Score','score','Total Marks','Marks','Total_Marks']
                    found_name = None
                    for nc in name_candidates:
                        if nc in exdf2.columns:
                            found_name = nc
                            break
                    found_score = None
                    for sc in score_candidates:
                        if sc in exdf2.columns:
                            found_score = sc
                            break

                    if found_name is None:
                        continue

                    # normalize names in the exam dataframe
                    try:
                        exdf2['__name_norm'] = exdf2[found_name].astype(str).str.lower().str.replace(r"\s+", ' ', regex=True).str.strip()
                    except Exception:
                        exdf2['__name_norm'] = exdf2.index.astype(str)

                    # if a score column exists, filter to rows with numeric totals (we only message students with totals)
                    if found_score and found_score in exdf2.columns:
                        try:
                            exdf2[found_score] = pd.to_numeric(exdf2[found_score], errors='coerce')
                            exdf2 = exdf2[exdf2[found_score].notna()]
                        except Exception:
                            pass

                    # filter exam rows by the selected classes (session-level class_sel if set)
                    try:
                        class_filter = st.session_state.get('class_sel', None)
                        if class_filter:
                            # prefer 'Class' or class-like column
                            class_col = None
                            for cc in ['Class','class','class_name','className','Grade','GRADE']:
                                if cc in exdf2.columns:
                                    class_col = cc
                                    break
                            if class_col:
                                exdf2 = exdf2[exdf2[class_col].isin(class_filter)]
                    except Exception:
                        pass

                    for _, xr in exdf2.iterrows():
                        nm = str(xr.get(found_name,'')).strip()
                        if not nm:
                            continue
                        nm_norm = str(nm).lower().replace('\n',' ').strip()
                        contact = contact_name_set.get(nm_norm)
                        has_phone = False
                        if contact:
                            ph = contact.get('phone') or contact.get('phone_raw')
                            if ph and str(ph).strip() and str(ph).strip().lower() not in ('', 'nan', 'none'):
                                has_phone = True
                        if not has_phone:
                            unmatched_by_exam.setdefault(exam_id2, []).append({'exam_id': exam_id2, 'exam_name': exam_name2, 'student_name': nm})
            except Exception:
                # if anything fails, fall back to the original unmatched list only
                pass

            if 'enriched_unmatched' not in st.session_state:
                st.session_state['enriched_unmatched'] = None

            load_list = container.button('Load list')
            if load_list or st.session_state.get('enriched_unmatched') is None:
                with st.spinner('Loading unmatched students (reading each exam once)...'):
                    enriched = []
                    classes_set = set()
                    # read each exam file once
                    for eid, entries in unmatched_by_exam.items():
                        ep = BASE / eid / 'data.pkl'
                        exdf = None
                        if ep.exists():
                            try:
                                exdf = pd.read_pickle(ep)
                            except Exception:
                                exdf = None

                        # prepare name normalization in exdf if available
                        name_candidates = ['student_name','name','Name','student','Student','student full name','Student Name']
                        found_col = None
                        if exdf is not None:
                            for nc in name_candidates:
                                if nc in exdf.columns:
                                    found_col = nc
                                    break
                            if found_col:
                                exdf['__name_norm'] = exdf[found_col].astype(str).str.lower().str.replace(r"\s+", ' ', regex=True).str.strip()

                        for u in entries:
                            name = (u.get('student_name') or '').strip()
                            name_norm = str(name).lower().replace('\n',' ').strip()
                            exam_class_val = ''
                            exam_parent_val = ''
                            if exdf is not None and found_col:
                                rows = exdf[exdf.get('__name_norm','') == name_norm]
                                if not rows.empty:
                                    exam_class_val = rows.iloc[0].get('Class') if 'Class' in rows.columns else rows.iloc[0].get('class', '')
                                    # try to get parent name from exam row if available
                                    exam_parent_val = rows.iloc[0].get('parent_name') if 'parent_name' in rows.columns else rows.iloc[0].get('Parent', '')
                            enriched_u = dict(u)
                            enriched_u['exam_class'] = exam_class_val or ''
                            enriched_u['exam_parent'] = exam_parent_val or ''
                            if enriched_u['exam_class']:
                                classes_set.add(str(enriched_u['exam_class']))
                            enriched.append(enriched_u)

                    st.session_state['enriched_unmatched'] = enriched
                    st.session_state['enriched_unmatched_classes'] = sorted(list(classes_set))

            # show filter and limited list with 'load more' behaviour
            # Use only the classes the user selected in the main "Classes to include" selector
            try:
                selected_classes_outer = class_sel if isinstance(class_sel, (list, tuple)) and len(class_sel) > 0 else None
            except Exception:
                selected_classes_outer = None
            if selected_classes_outer:
                classes_list = [str(x) for x in selected_classes_outer]
            else:
                classes_list = st.session_state.get('enriched_unmatched_classes', []) or []

            # require at least one class to be present; show message if none
            if not classes_list:
                container.markdown('No classes available to filter. Select classes in the main selector first and click Load list.')
                return

            sel_class_side = container.selectbox('Filter missing phones by class', options=classes_list, index=0)

            # pagination / load more
            per_page = 50
            if 'missing_page' not in st.session_state:
                st.session_state['missing_page'] = 1
            max_show = st.session_state['missing_page'] * per_page

            enriched_unmatched = st.session_state.get('enriched_unmatched', []) or []
            # flexible class matching: normalize and allow contains or numeric match so 'GRADE 6' matches '6G' etc.
            import re
            def _norm_class(s):
                if s is None:
                    return ''
                ss = str(s).lower()
                ss = ss.replace('grade ', '').replace('grade', '')
                ss = ss.replace(' ', '').replace('-', '').strip()
                return ss

            sel_norm = _norm_class(sel_class_side)
            def _class_matches(exam_class, sel_class_n):
                if not exam_class:
                    return False
                a = _norm_class(exam_class)
                b = sel_class_n
                if not a or not b:
                    return False
                if a == b:
                    return True
                if a in b or b in a:
                    return True
                # numeric match
                da = ''.join(re.findall(r"\d+", a))
                db = ''.join(re.findall(r"\d+", b))
                if da and db and da == db:
                    return True
                return False

            display_items = [e for e in enriched_unmatched if _class_matches(e.get('exam_class',''), sel_norm)]
            total_items = len(display_items)
            display_items_page = display_items[:max_show]

            if not display_items_page:
                container.markdown('No unmatched students in the selected class (after loading).')
            # load current contacts so we can prefill existing phones
            try:
                _current_contacts = load_contacts()
            except Exception:
                _current_contacts = []

            def _normalize_phone_simple(raw):
                if not raw or str(raw).strip() == '':
                    return ''
                s = str(raw).strip()
                if s.startswith('+'):
                    return s
                digits = ''.join(ch for ch in s if ch.isdigit())
                if not digits:
                    return ''
                if digits.startswith('0'):
                    return '+254' + digits.lstrip('0')
                if digits.startswith('254'):
                    return '+' + digits
                if digits.startswith('7') and len(digits) in (9,10):
                    return '+254' + digits[-9:]
                return digits

            new_phones = {}
            new_parents = {}
            for i, u in enumerate(display_items_page):
                name = u.get('student_name') or ''
                exam_n = u.get('exam_name') or ''
                key = f'side_add_phone_{i}_{hash(name)}'
                parent_key = f'side_parent_{i}_{hash(name)}'
                container.markdown(f"**{i+1}. {name} — {exam_n} — Class: {u.get('exam_class','')}**")
                # prefill with any existing contact phone or exam parent
                name_norm_pref = str(name).lower().replace('\n',' ').strip()
                existing_contact = next((c for c in _current_contacts if str(c.get('student_name','')).lower().strip() == name_norm_pref), None)
                existing_phone_val = ''
                existing_parent_val = ''
                if existing_contact is not None:
                    existing_phone_val = existing_contact.get('phone') or existing_contact.get('phone_raw') or ''
                    existing_parent_val = existing_contact.get('parent_name') or ''
                # exam parent fallback from enriched_unmatched entries
                exam_parent_fb = u.get('exam_parent','') or ''
                if not existing_parent_val and exam_parent_fb:
                    existing_parent_val = exam_parent_fb

                new_phones[key] = container.text_input('Phone (include country code)', value=existing_phone_val, key=key)
                new_parents[parent_key] = container.text_input('Parent / Guardian name', value=existing_parent_val, key=parent_key)

            if total_items > max_show:
                if container.button('Load more'):
                    st.session_state['missing_page'] += 1
                    safe_rerun()

            if container.button('Save phones'):
                try:
                    contacts_list = load_contacts()
                except Exception:
                    contacts_list = []
                updated = 0
                for i, u in enumerate(display_items_page):
                    name = u.get('student_name') or ''
                    key = f'side_add_phone_{i}_{hash(name)}'
                    parent_key = f'side_parent_{i}_{hash(name)}'
                    phone_val = new_phones.get(key)
                    parent_val = new_parents.get(parent_key)
                    if phone_val or parent_val:
                        phone_val = str(phone_val or '').strip()
                        parent_val = str(parent_val or '').strip()
                        if phone_val or parent_val:
                            # normalize before saving so Parent Contacts shows normalized numbers
                            phone_norm = _normalize_phone_simple(phone_val) if phone_val else ''
                            nm_norm = str(name).lower().replace('\n',' ').strip()
                            found = None
                            for c in contacts_list:
                                if str(c.get('student_name','')).lower().strip() == nm_norm:
                                    found = c
                                    break
                            if found is not None:
                                if phone_val:
                                    found['phone_raw'] = phone_val
                                    found['phone'] = phone_norm
                                if parent_val:
                                    found['parent_name'] = parent_val
                            else:
                                contacts_list.append({'student_id': '', 'student_name': name, 'grade': '', 'stream': '', 'parent_name': parent_val or '', 'phone_raw': phone_val or '', 'phone': phone_norm or ''})
                            updated += 1
                try:
                    CONTACTS_FILE.write_text(json.dumps(contacts_list, indent=2), encoding='utf-8')
                except Exception as e:
                    container.error('Failed to save contacts: ' + str(e))
                    return

                # Refresh in-memory contacts and re-run the centralized prepare logic so prepared messages update immediately
                try:
                    new_contacts = load_contacts()
                    new_contacts_df = pd.DataFrame(new_contacts)
                except Exception:
                    new_contacts_df = pd.DataFrame(contacts_list)

                # Call the central prepare action to rebuild prepared lists using updated contacts
                try:
                    prepare_messages_action(sel, new_contacts_df, limit)
                except Exception:
                    pass

                container.success(f'Updated {updated} contacts and refreshed prepared messages')
                safe_rerun()

        # Render the Manage Missing Phones UI directly on the page (always visible inside an expander)
        st.markdown('### Manage missing phones')
        # Manage missing phones expander: closed by default to avoid excessive scrolling
        with st.expander('Manage missing phones', expanded=False):
            _render_missing_ui(st)

        # single-item preview
        preview_idx = st.selectbox('Preview message for', options=labels, index=0)
        try:
            pi = int(preview_idx.split(':',1)[0])
            st.markdown('#### Message preview')
            st.code(prepared[pi]['message'])
        except Exception:
            pass

        # --- Send selected recipients area (always visible) ---
        st.markdown('---')
        st.markdown('## Quick send to recipients')
        st.markdown('Quickly send prepared messages to selected recipients (always available). You can include students without phones; these will be skipped. Preview the message below before confirming.')

        # Build a recipient pool consisting of prepared messages (with phones) and prepared_unmatched (no phones)
        prepared_list = st.session_state.get('prepared_messages', []) or []
        unmatched_list = st.session_state.get('prepared_unmatched', []) or []
        # normalize unmatched entries into prepared-like dicts
        normalized_unmatched = []
        for u in unmatched_list:
            normalized_unmatched.append({'phone': u.get('phone') or u.get('phone_raw') or '', 'message': '', 'student_name': u.get('student_name',''), 'exam_id': u.get('exam_id',''), 'exam_name': u.get('exam_name',''), 'total': None, 'class_rank': None, 'class_size': None, 'overall_rank': None, 'overall_size': None})

        # If there are no prepared messages (user hasn't clicked Prepare),
        # build a recipient pool directly from available exam data and saved contacts
        if prepared_list:
            recipient_pool = prepared_list + normalized_unmatched
        else:
            recipient_pool = []
            try:
                contacts_list = load_contacts()
            except Exception:
                contacts_list = []

            def _pick_name_col(cols_list):
                candidates = ['student_name','name','Name','student','Student','student full name','Student Name']
                for c in candidates:
                    if c in cols_list:
                        return c
                return cols_list[0] if cols_list else None

            for _, mrow in meta_df.iterrows():
                exam_id = mrow.get('exam_id')
                exam_name = mrow.get('exam_name')
                exam_path = BASE / exam_id / 'data.pkl'
                if not exam_path.exists():
                    continue
                try:
                    exdf = pd.read_pickle(exam_path)
                except Exception:
                    continue
                name_col = _pick_name_col(list(exdf.columns))
                parent_col = None
                for pc in ('parent_name','Parent','parent'):
                    if pc in exdf.columns:
                        parent_col = pc
                        break

                for _, erow in exdf.iterrows():
                    student_name = str(erow.get(name_col,'')).strip()
                    parent_name = str(erow.get(parent_col,'')) if parent_col else ''
                    # find contact phone by normalized name
                    name_norm = student_name.lower().replace('\n',' ').strip()
                    found = next((c for c in contacts_list if str(c.get('student_name','')).lower().strip() == name_norm), None)
                    phone = ''
                    p_parent = ''
                    if found:
                        phone = found.get('phone') or found.get('phone_raw') or ''
                        p_parent = found.get('parent_name') or ''
                    parent_final = p_parent or parent_name or ''
                    recipient_pool.append({'phone': phone, 'message': '', 'student_name': student_name, 'exam_id': exam_id, 'exam_name': exam_name, 'total': None, 'class_rank': None, 'class_size': None, 'overall_rank': None, 'overall_size': None, 'parent_name': parent_final})

        # Build exam metadata map to support bottom filters (year/term/kind/class)
        try:
            exam_meta_map = meta_df.set_index('exam_id')[[ 'year', 'term', 'kind', 'class_name']].to_dict('index')
        except Exception:
            exam_meta_map = {}

        # compute bottom filters based on recipient pool
        bottom_years = sorted({str(exam_meta_map.get(p.get('exam_id'), {}).get('year')) for p in recipient_pool if exam_meta_map.get(p.get('exam_id'))})
        bottom_terms = sorted({str(exam_meta_map.get(p.get('exam_id'), {}).get('term')) for p in recipient_pool if exam_meta_map.get(p.get('exam_id'))})
        bottom_kinds = sorted({str(exam_meta_map.get(p.get('exam_id'), {}).get('kind')) for p in recipient_pool if exam_meta_map.get(p.get('exam_id'))})
        bottom_classes = sorted({str(exam_meta_map.get(p.get('exam_id'), {}).get('class_name')) for p in recipient_pool if exam_meta_map.get(p.get('exam_id'))})

        bcol1, bcol2, bcol3, bcol4 = st.columns([1,1,1,1])
        with bcol1:
            bottom_year = st.selectbox('Year (recipients)', options=['All'] + [y for y in bottom_years if y and y != 'None'], index=0, key='bottom_year')
        with bcol2:
            bottom_term = st.selectbox('Term (recipients)', options=['All'] + [t for t in bottom_terms if t and t != 'None'], index=0, key='bottom_term')
        with bcol3:
            bottom_kind = st.selectbox('Exam kind (recipients)', options=['All'] + [k for k in bottom_kinds if k and k != 'None'], index=0, key='bottom_kind')
        with bcol4:
            bottom_class = st.selectbox('Class (recipients)', options=['All'] + [c for c in bottom_classes if c and c != 'None'], index=0, key='bottom_class')

        # If the bottom filter set changed since last run, clear the compact selection
        try:
            current_filter_state = (str(bottom_year), str(bottom_term), str(bottom_kind), str(bottom_class))
            prev_filter_state = st.session_state.get('compact_filter_state')
            if prev_filter_state != current_filter_state:
                # clear the compact form selection so options refresh cleanly
                for k in ('compact_select', 'applied_selected_labels', 'applied_edits', 'selected_labels'):
                    if k in st.session_state:
                        try:
                            del st.session_state[k]
                        except Exception:
                            st.session_state[k] = []
                st.session_state['compact_filter_state'] = current_filter_state
        except Exception:
            pass

        labels_bottom = []
        for i, p in enumerate(recipient_pool):
            nm = p.get('student_name') or ''
            ex = p.get('exam_name') or ''
            ph = p.get('phone') or ''
            keep = True
            meta = exam_meta_map.get(p.get('exam_id'), {})
            if bottom_year != 'All' and meta.get('year') is not None and str(meta.get('year')) != bottom_year:
                keep = False
            if bottom_term != 'All' and meta.get('term') is not None and str(meta.get('term')) != bottom_term:
                keep = False
            if bottom_kind != 'All' and meta.get('kind') is not None and str(meta.get('kind')) != bottom_kind:
                keep = False
            if bottom_class != 'All' and meta.get('class_name') is not None and str(meta.get('class_name')) != bottom_class:
                keep = False
            if keep:
                labels_bottom.append(f"{i}: {nm} — {ex} ({ph})")

        # NOTE: recipient selection and send UI moved to the bottom-most section.
        # Users must click "Load recipients" to populate the selectable list below.
        # This avoids heavy reruns while browsing filters.
        prev = st.session_state.get('selected_labels', []) or []
        safe_default = [v for v in prev if v in labels_bottom]
        if not safe_default:
            safe_default = []

        # --- Compact Quick send panel (select, preview, confirm) ---
        with st.form('compact_quick_send_form'):
            # default to nothing selected per user request
            compact_selected = st.multiselect('Select recipients to send (only these will be sent)', options=labels_bottom, default=[], key='compact_select')
            try:
                compact_indices = [int(s.split(':',1)[0]) for s in compact_selected]
            except Exception:
                compact_indices = []

            st.markdown(f'**Selected (in form):** {len(compact_indices)}')

            # inline edits for selected recipients
            for idx in compact_indices:
                p = recipient_pool[idx]
                st.markdown(f"**{p.get('student_name','')} — {p.get('exam_name','')}**")
                c1, c2 = st.columns([2,2])
                with c1:
                    st.text_input(f'Phone for {idx}', value=str(p.get('phone') or ''), key=f'compact_phone_{idx}')
                with c2:
                    st.text_input(f'Parent name for {idx}', value=str(p.get('parent_name') or ''), key=f'compact_parent_{idx}')

            compact_apply = st.form_submit_button('Apply selection', key='compact_apply')

        if compact_apply:
            st.session_state['applied_selected_labels'] = compact_selected
            applied_ed = {}
            for idx in compact_indices:
                phone_val = st.session_state.get(f'compact_phone_{idx}', '')
                parent_val = st.session_state.get(f'compact_parent_{idx}', '')
                if phone_val or parent_val:
                    applied_ed[str(idx)] = {'phone': phone_val, 'parent_name': parent_val}
            st.session_state['applied_edits'] = applied_ed

        # show applied selection and preview
        applied_labels = st.session_state.get('applied_selected_labels', []) or []
        applied_edits = st.session_state.get('applied_edits', {}) or {}
        try:
            applied_indices = [int(s.split(':',1)[0]) for s in applied_labels]
        except Exception:
            applied_indices = []

        st.markdown(f'**Applied selection:** {len(applied_indices)}')
        if applied_indices:
            # preview first selected message
            try:
                first = applied_indices[0]
                base = recipient_pool[first].get('message') or ''
                ed = applied_edits.get(str(first), {})
                if ed.get('parent_name') and base.lower().startswith('dear'):
                    parts = base.split(',',1)
                    if len(parts) > 1:
                        base = f"Dear {ed.get('parent_name')}," + parts[1]
                # fallback to build_preview_message when prepared message is empty
                if not base:
                    try:
                        built = build_preview_message(recipient_pool[first])
                        if built:
                            base = built
                    except Exception:
                        pass
            except Exception:
                base = ''
            st.markdown('#### Message preview (first selected)')
            st.code(base)
            # diagnostics for this preview
            try:
                render_preview_diagnostics(recipient_pool[first])
            except Exception:
                pass
            # 'Show raw message to be sent' button removed per user request
            # One-click exam row inspector for bottom preview
            try:
                if st.button('Show exam row', key=f'show_row_{first}'):
                    ep = BASE / recipient_pool[first].get('exam_id', '') / 'data.pkl'
                    if not ep.exists():
                        st.error('Exam file not found: ' + str(ep))
                    else:
                        try:
                            edf = pd.read_pickle(ep)
                            # detect name column
                            name_col = None
                            for c in ['student_name','name','Name','student','Student','student full name','Student Name']:
                                if c in edf.columns:
                                    name_col = c
                                    break
                            if name_col is None:
                                st.warning('No name-like column found in exam file')
                            else:
                                edf['__name_norm'] = edf[name_col].astype(str).str.lower().str.replace(r"\s+", ' ', regex=True).str.strip()
                                target = str(recipient_pool[first].get('student_name','')).lower().replace('\n',' ').strip()
                                matches = edf[edf['__name_norm'] == target]
                                if matches.empty:
                                    matches = edf[edf[name_col].astype(str).str.lower().str.contains(str(recipient_pool[first].get('student_name','')).lower().strip(), na=False)]
                                if matches.empty:
                                    st.warning('No matching rows found in exam file')
                                else:
                                    st.dataframe(matches.head(20))
                        except Exception as e:
                            st.error('Failed to read exam pickle: ' + str(e))
            except Exception:
                pass

        # send flow: show send button and require confirmation
        if applied_indices:
            if st.button('Send selected messages', key='compact_send'):
                st.session_state['compact_pending_send'] = True

        if st.session_state.get('compact_pending_send'):
            st.warning('You are about to send messages to the applied recipients. Recipients without phone numbers will be skipped.')
            cs1, cs2 = st.columns([1,1])
            with cs1:
                if st.button('Confirm — Send now', key='compact_confirm'):
                    to_send = []
                    skipped = []
                    try:
                        contacts_list = load_contacts()
                    except Exception:
                        contacts_list = []

                    for i in applied_indices:
                        rec = dict(recipient_pool[i])
                        edits = applied_edits.get(str(i), {})
                        if edits.get('phone'):
                            rec['phone'] = edits.get('phone')
                        if edits.get('parent_name'):
                            rec['parent_name'] = edits.get('parent_name')
                        if not rec.get('phone'):
                            skipped.append(rec.get('student_name',''))
                            continue
                        to_send.append(rec)
                        # update contacts_list
                        nm_norm = str(rec.get('student_name','')).lower().strip()
                        found = None
                        for c in contacts_list:
                            if str(c.get('student_name','')).lower().strip() == nm_norm:
                                found = c
                                break
                        if found is not None:
                            if rec.get('phone'):
                                found['phone_raw'] = rec.get('phone')
                                found['phone'] = rec.get('phone')
                            if rec.get('parent_name'):
                                found['parent_name'] = rec.get('parent_name')
                        else:
                            contacts_list.append({'student_id':'','student_name':rec.get('student_name',''), 'grade':'', 'stream':'', 'parent_name': rec.get('parent_name') or '', 'phone_raw': rec.get('phone') or '', 'phone': rec.get('phone') or ''})

                    if skipped:
                        st.warning(f"Skipped {len(skipped)} recipients with no phone: {', '.join(skipped[:10])}{'...' if len(skipped)>10 else ''}")
                    if not to_send:
                        st.info('No recipients with phone numbers to send to.')
                    else:
                        try:
                            CONTACTS_FILE.write_text(json.dumps(contacts_list, indent=2), encoding='utf-8')
                        except Exception:
                            pass
                        cfg = load_config()
                        results = []
                        with st.spinner(f'Sending {len(to_send)} messages...'):
                            for c in to_send:
                                msg = c.get('message') or ''
                                if not msg:
                                    msg = f"Dear {c.get('parent_name','')}, Results for {c.get('student_name','')} — {c.get('exam_name')}. Total: {c.get('total') if c.get('total') is not None else 'N/A'}."
                                res = messaging.send_single(c.get('phone'), msg, config=cfg, test_mode=False)
                                results.append({'contact': c, 'result': res})
                        st.success(f"Sent {len(results)} messages")
                        render_send_results(results)
                    st.session_state['compact_pending_send'] = False

            with cs2:
                if st.button('Cancel', key='compact_cancel'):
                    st.session_state['compact_pending_send'] = False
        # Auto-load recipients so Quick send is always available
        if not st.session_state.get('recipients_loaded'):
            st.session_state['labels_bottom_cached'] = labels_bottom
            st.session_state['recipient_pool_cached'] = recipient_pool
            st.session_state['recipients_loaded'] = True

        # show current loaded count
        cached_labels = st.session_state.get('labels_bottom_cached', []) or []
        st.markdown(f'**Loaded recipients:** {len(cached_labels)}')

        # Quick send UI removed per user request; recipients and sending should be managed elsewhere.

        # Message audit log: always visible below the applied selection
        try:
            render_sent_messages_log(limit=500)
        except Exception:
            pass
