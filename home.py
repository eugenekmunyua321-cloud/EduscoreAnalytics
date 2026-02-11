# home.py
# EDUSCORE ANALYTICS - HOME DASHBOARD
# Main entry point for the exam management system

import streamlit as st
import json
import os
import sys
from pathlib import Path
import uuid

import modules.auth as auth
from modules import storage as storage


# Page configuration
st.set_page_config(
    page_title="EduScore Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"  # restore expanded sidebar by default
)

# Initialize session state
if 'current_page' not in st.session_state:
    st.session_state.current_page = 'home'
if 'show_home_header' not in st.session_state:
    st.session_state.show_home_header = True

# Custom CSS for beautiful cards
def navigate_to(page):
    st.session_state.current_page = page
    st.session_state.show_home_header = (page == 'home')
    # Avoid calling st.rerun() inside callbacks; streamlit will rerun after the interaction.
    return
st.markdown(
"""
<style>
/* Modern gradient background */
.stApp {{
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
}}

.main-header {{
    text-align: center;
    padding: 3rem 2rem;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border-radius: 20px;
    margin-bottom: 3rem;
    box-shadow: 0 10px 30px rgba(102, 126, 234, 0.3);
}}

.main-header h1 {{
    font-size: 3rem !important;
    font-weight: 800 !important;
}

/* Menu section header styling */
.stMarkdown h3 {{
    color: #2d3748 !important;
    font-weight: 700 !important;
    font-size: 1.8rem !important;
}}

/* Style buttons to be less prominent */
div[data-testid="column"] > div > div > button {{
    margin-top: 1rem !important;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 0.8rem 1.5rem !important;
    font-weight: 600 !important;
    box-shadow: 0 4px 10px rgba(102, 126, 234, 0.3) !important;
    transition: all 0.3s ease !important;
}}

div[data-testid="column"] > div > div > button:hover {{
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 15px rgba(102, 126, 234, 0.4) !important;
}}
/* Make the profile form's primary Save button green and the in-form Exit button red */
button[aria-label="Save changes"] {{
    background: #16a34a !important; /* green-600 */
    color: #fff !important;
    border: none !important;
}}
button[aria-label="Exit"] {{
    background: #dc2626 !important; /* red-600 */
    color: #fff !important;
    border: none !important;
}}
</style>
""", unsafe_allow_html=True)
# Override / enhance styles using brand colors so the home page matches the logo/theme
BRAND_A = getattr(auth, 'BRAND_GRAD_A', '#06b6d4')
BRAND_B = getattr(auth, 'BRAND_GRAD_B', '#7c3aed')
BRAND_PRIMARY = getattr(auth, 'BRAND_PRIMARY', '#0f172a')
st.markdown(f"""
<style>
/* Theme overrides */
.stApp {{ background: linear-gradient(135deg, #f3f6fb 0%, #e6eefb 100%); }}
.main-header {{ background: linear-gradient(90deg, {BRAND_A}, {BRAND_B}) !important; box-shadow: 0 14px 40px rgba(15, 23, 42, 0.12) !important; }}
div[data-testid="column"] > div > div > button {{ background: linear-gradient(90deg, {BRAND_A}, {BRAND_B}) !important; color: #fff !important; }}
.banner-pill {{ background: rgba(255,255,255,0.08); padding:8px 12px; border-radius:999px; display:inline-block; font-weight:700; }}
.hero-actions {{ display:flex; gap:8px; justify-content:flex-end; align-items:center; }}
.primary-cta {{ background: linear-gradient(90deg, {BRAND_A}, {BRAND_B}); color: white; padding:10px 14px; border-radius:10px; font-weight:800; box-shadow:0 8px 24px rgba(37,99,235,0.12); border:none; cursor:pointer; }}
.signout-cta {{ background: transparent; color: white; padding:8px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.12); cursor:pointer; }}
</style>
""", unsafe_allow_html=True)

# Placeholder for rendering a modal-style profile overlay (falls back when st.modal unavailable)
PROFILE_OVERLAY_PLACEHOLDER = st.empty()

# Ensure saved exams are loaded into session state even when `app.py` delegates directly
# to `home.py` (earlier flows put the loader in app.py which is skipped when delegating).
def _load_saved_exams_if_missing():
    import json, os
    import pandas as pd
    # If already populated, skip
    if st.session_state.get('saved_exams'):
        return

    # Use central storage adapter (handles S3 or local filesystem)
    storage_dir = storage.get_storage_dir()
    meta_path = os.path.join(storage_dir, 'exams_metadata.json')

    # Ensure backing dicts exist
    if 'saved_exam_data' not in st.session_state:
        st.session_state.saved_exam_data = {}
    if 'saved_exam_raw_data' not in st.session_state:
        st.session_state.saved_exam_raw_data = {}
    if 'saved_exam_configs' not in st.session_state:
        st.session_state.saved_exam_configs = {}

    st.session_state.saved_exams = []

    all_metadata = {}
    try:
        # adapter read_json will prefer remote when configured
        try:
            m = storage.read_json(meta_path)
        except Exception:
            # adapter may still accept bare keys in some deployments
            m = storage.read_json('exams_metadata.json')
        if isinstance(m, dict):
            all_metadata = m
        else:
            # fallback to local file
            if os.path.exists(meta_path):
                with open(meta_path, 'r', encoding='utf-8') as f:
                    all_metadata = json.load(f)
            else:
                return
    except Exception:
        # fallback to local file
        if not os.path.exists(meta_path):
            return
        with open(meta_path, 'r', encoding='utf-8') as f:
            all_metadata = json.load(f)

    for exam_id, metadata in all_metadata.items():
        st.session_state.saved_exams.append(metadata)

    # Load per-exam data into backing stores (pickles + config)
    for exam_id in all_metadata.keys():
        try:
            # Try adapter-backed pickles/config first
            try:
                d = storage.read_pickle(f"{exam_id}/data.pkl")
                if d is not None:
                    st.session_state.saved_exam_data[exam_id] = d
                rd = storage.read_pickle(f"{exam_id}/raw_data.pkl")
                if rd is not None:
                    st.session_state.saved_exam_raw_data[exam_id] = rd
                cfg = storage.read_json(f"{exam_id}/config.json")
                if cfg is not None:
                    st.session_state.saved_exam_configs[exam_id] = cfg
                # if any of the adapter reads returned data, continue to next exam
                if exam_id in st.session_state.saved_exam_data or exam_id in st.session_state.saved_exam_raw_data or exam_id in st.session_state.saved_exam_configs:
                    continue
            except Exception:
                # adapter read failed; fallback to local files
                pass

            # Local fallback: read from storage_dir cache
            exam_dir = os.path.join(storage_dir, exam_id)
            if not os.path.exists(exam_dir):
                continue
            data_path = os.path.join(exam_dir, 'data.pkl')
            raw_path = os.path.join(exam_dir, 'raw_data.pkl')
            cfg_path = os.path.join(exam_dir, 'config.json')
            if os.path.exists(data_path):
                st.session_state.saved_exam_data[exam_id] = pd.read_pickle(data_path)
            if os.path.exists(raw_path):
                st.session_state.saved_exam_raw_data[exam_id] = pd.read_pickle(raw_path)
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as fh:
                    st.session_state.saved_exam_configs[exam_id] = json.load(fh)
        except Exception:
            # Non-fatal; proceed with other exams
            pass

# Attempt to populate saved exams now (covers cases where app.py delegated early)
try:
    _load_saved_exams_if_missing()
except Exception:
    pass
if st.session_state.current_page == 'home':
    # Show subscription countdown banner
    from modules import billing
    storage_dir = storage.get_storage_dir()
    acct_billing = billing.get_account_billing(storage_dir)
    import datetime as _dt
    import time as _t
    expiry_ts = int(acct_billing.get('expiry_ts') or 0)
    now = int(_t.time())
    if expiry_ts > now:
        secs = expiry_ts - now
        try:
            if secs >= 86400:
                days = secs // 86400
                rem = secs % 86400
                hours = rem // 3600
                rem2 = rem % 3600
                minutes = rem2 // 60
                seconds = rem2 % 60
                countdown = f"{days} day{'s' if days!=1 else ''}, {hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                hours = secs // 3600
                rem = secs % 3600
                minutes = rem // 60
                seconds = rem % 60
                countdown = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except Exception:
            countdown = str(_dt.timedelta(seconds=secs))
        st.markdown(f"""
        <div style='background: linear-gradient(90deg, #06b6d4, #7c3aed); color: white; padding: 18px 24px; border-radius: 14px; margin-bottom: 24px; font-size: 1.3rem; font-weight: 700; box-shadow: 0 4px 18px rgba(37,99,235,0.10); text-align:center;'>
            ⏳ <span style='font-size:1.2em;'>Subscription time remaining:</span> <span style='font-size:1.2em; font-weight:900;'>{countdown}</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style='background: linear-gradient(90deg, #ef4444, #f59e42); color: white; padding: 18px 24px; border-radius: 14px; margin-bottom: 24px; font-size: 1.3rem; font-weight: 700; box-shadow: 0 4px 18px rgba(239,68,68,0.10); text-align:center;'>
            ❌ <span style='font-size:1.2em;'>Subscription expired.</span>
        </div>
        """, unsafe_allow_html=True)
    # Show a cool, classy welcome banner with the signed-in school's display name
    try:
        display_name = st.session_state.get('school_display_name') or (st.session_state.get('user_email', '') or '').split('@')[0] or 'Guest'
        # small sanitization
        display_name = str(display_name).strip()
        # Banner styling
        # Header banner removed per user request (keep header area clean)
    except Exception:
        pass

    # Load home page module
    from modules.home_page import render_home_page
    # Make navigate_to available in the module's scope
    import modules.home_page as home_module
    home_module.navigate_to = navigate_to
    # Action buttons: keep Sign out in the header; remove Add New Exam (it's in the page body)
    c1, c2, c3, c4, c5 = st.columns([1,1,1,1,1])
    with c5:
        def _on_signout():
            try:
                auth._sign_out_all()
            except Exception:
                for k in ['user_email','user_uid','school_display_name']:
                    try:
                        del st.session_state[k]
                    except Exception:
                        pass
            st.session_state['current_page'] = 'auth'
            # Let Streamlit perform the rerun automatically after the button interaction.
            return
        # Button to open profile editor/viewer for the signed-in user
        def _open_profile_editor():
            # bump a small nonce so each explicit open gets a unique form instance
            st.session_state['profile_form_nonce'] = st.session_state.get('profile_form_nonce', 0) + 1
            st.session_state['show_profile_editor'] = True
        st.button('View / Edit profile', key='home_view_profile', on_click=_open_profile_editor)

        st.button('Sign out', key='home_sign_out', on_click=_on_signout)
    # If the user clicked to view/edit their profile, show the profile editor at the top of the page
    try:
        # If this is a fresh account that must complete profile, force the editor open
        try:
            must = st.session_state.get('must_complete_profile')
            ue = st.session_state.get('user_email', '') or ''
            if must and ue:
                try:
                    uname = str(ue).split('@')[0]
                except Exception:
                    uname = ''
                if str(must) == str(uname):
                    st.session_state['profile_form_nonce'] = st.session_state.get('profile_form_nonce', 0) + 1
                    st.session_state['show_profile_editor'] = True
                    st.session_state['require_profile_complete'] = True
        except Exception:
            pass

        if st.session_state.get('show_profile_editor'):
            # ensure acct_id exists in this scope to avoid local-variable access errors
            acct_id = ''
            # Ensure we always read/write the per-account admin_meta.json for the signed-in user
            try:
                ue = st.session_state.get('user_email', '') or ''
                acct_id = auth.safe_email_to_schoolid(ue) if ue else ''
                if acct_id:
                    storage_dir = os.path.join(os.path.dirname(__file__), 'saved_exams_storage', acct_id)
                    os.makedirs(storage_dir, exist_ok=True)
                    # No automatic restoration here — only Home saves update the authoritative last-good copy.
                else:
                    # fallback to generic storage dir
                    storage_dir = storage.get_storage_dir()
            except Exception:
                storage_dir = storage.get_storage_dir()
            meta_path = os.path.join(storage_dir, 'admin_meta.json')
            meta = {}
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as fh:
                        meta = json.load(fh) or {}
                except Exception:
                    meta = {}

            # Use staged pending values if present so staged edits persist across reopens
            staged = st.session_state.get('profile_pending') or {}
            default_phone = staged.get('phone', meta.get('phone',''))
            default_school_name = staged.get('school_name', meta.get('school_name',''))
            default_email = staged.get('email', meta.get('email',''))
            default_location = staged.get('location', meta.get('location',''))
            default_country = staged.get('country', meta.get('country',''))

            # Use Streamlit modal if available, otherwise fallback to an inline overlay container
            try:
                modal_fn = getattr(st, 'modal', None)
            except Exception:
                modal_fn = None

            def _render_profile_form(container):
                        container.markdown('## View / Edit your school profile')
                        container.info('Please fill these details and click Confirm & Save. Administrators cannot edit profiles from the admin console.')
                        # show account number read-only
                        acct_no = meta.get('account_number') or '(not set)'
                        container.markdown(f"**System account number:** {acct_no}")

                        # Change password button appears at the top of the profile box (optional)
                        try:
                            if container.button('Change password', key='profile_change_pw_btn_top'):
                                st.session_state['profile_change_inline'] = not st.session_state.get('profile_change_inline', False)
                        except Exception:
                            pass

                        # (inline separate password change removed) password change will be part of the profile form below

                        # Use a stable form key per-account so widget keys survive reruns
                        # (using uuid here caused a new key on each rerun which reset inputs)
                        acct_key = acct_id or 'anon'
                        nonce = st.session_state.get('profile_form_nonce', 0)
                        modal_flag = 'modal' if modal_fn else 'inline'
                        # Use the container's id so forms rendered into different containers get distinct keys
                        try:
                            container_id = str(id(container))
                        except Exception:
                            container_id = uuid.uuid4().hex
                        # include nonce, modal_flag and container_id to ensure each form instance has a unique key
                        form_key = f"profile_modal_form_{acct_key}_{nonce}_{modal_flag}_{container_id}"
                        with container.form(form_key):
                            # Provide explicit stable widget keys so Streamlit preserves values across reruns
                            phone = container.text_input('Phone number', value=str(default_phone), key=f'profile_phone_{acct_key}_{nonce}_{modal_flag}_{container_id}')
                            school_name = container.text_input('School name', value=str(default_school_name), key=f'profile_school_name_{acct_key}_{nonce}_{modal_flag}_{container_id}')
                            contact_email = container.text_input('Contact email', value=default_email, placeholder='Enter contact email here', key=f'profile_email_{acct_key}_{nonce}_{modal_flag}_{container_id}')
                            location = container.text_input('Location', value=str(default_location), key=f'profile_location_{acct_key}_{nonce}_{modal_flag}_{container_id}')
                            country = container.text_input('Country', value=str(default_country), key=f'profile_country_{acct_key}_{nonce}_{modal_flag}_{container_id}')
                            container.markdown('---')
                            # Password change handled via the sidebar form (banner removed)
                            # Ensure local variables exist for the rest of the flow
                            old_pw = new_pw = new_pw2 = ''

                            colc, cold = container.columns([1,1])
                            with colc:
                                # Save changes (pressing Enter will stage the current field values and prompt confirmation)
                                submitted = container.form_submit_button('Save changes')
                            with cold:
                                # Rename the in-form cancel action to 'Exit' per user request; behavior unchanged
                                cancelled = container.form_submit_button('Exit')

                            if submitted:
                                # Password changes are handled via the sidebar; no inline password change requested here
                                change_pw_requested_local = False

                                # If user toggled password change, require the old password and matching new passwords
                                if change_pw_requested_local:
                                    if not (old_pw or '').strip():
                                        container.error('Please enter your current password in the Old password field before saving.')
                                        # keep the form open and do not stage/confirm
                                        st.session_state['profile_confirm_pending'] = False
                                        st.session_state['profile_pending'] = {
                                            'phone': phone,
                                            'school_name': school_name,
                                            'email': contact_email,
                                            'location': location,
                                            'country': country,
                                        }
                                        st.session_state['profile_pending_pw'] = {
                                            'old_pw': old_pw or '',
                                            'new_pw': new_pw or '',
                                            'new_pw2': new_pw2 or ''
                                        }
                                        # stop here so user can correct
                                        pass
                                    elif (new_pw or '') != (new_pw2 or ''):
                                        container.error('New password and confirmation do not match. Please correct them before saving.')
                                        st.session_state['profile_confirm_pending'] = False
                                        st.session_state['profile_pending'] = {
                                            'phone': phone,
                                            'school_name': school_name,
                                            'email': contact_email,
                                            'location': location,
                                            'country': country,
                                        }
                                        st.session_state['profile_pending_pw'] = {
                                            'old_pw': old_pw or '',
                                            'new_pw': new_pw or '',
                                            'new_pw2': new_pw2 or ''
                                        }
                                        pass
                                    else:
                                        # proceed to stage and confirm
                                        st.session_state['profile_pending'] = {
                                            'phone': phone,
                                            'school_name': school_name,
                                            'email': contact_email,
                                            'location': location,
                                            'country': country,
                                        }
                                        st.session_state['profile_pending_pw'] = {
                                            'old_pw': old_pw or '',
                                            'new_pw': new_pw or '',
                                            'new_pw2': new_pw2 or ''
                                        }
                                        st.session_state['profile_confirm_pending'] = True
                                else:
                                    # No password change requested: stage normally
                                    st.session_state['profile_pending'] = {
                                        'phone': phone,
                                        'school_name': school_name,
                                        'email': contact_email,
                                        'location': location,
                                        'country': country,
                                    }
                                    st.session_state['profile_pending_pw'] = {
                                        'old_pw': old_pw or '',
                                        'new_pw': new_pw or '',
                                        'new_pw2': new_pw2 or ''
                                    }
                                    st.session_state['profile_confirm_pending'] = True

                                # If we staged pending profile, write a raw submission snapshot for audit (exact data the user submitted)
                                try:
                                    if st.session_state.get('profile_pending'):
                                        ue = st.session_state.get('user_email','') or ''
                                        acct_for_save = auth.safe_email_to_schoolid(ue) if ue else os.path.basename(storage.get_storage_dir())
                                        raw_path = os.path.join(os.getcwd(), 'saved_exams_storage', acct_for_save, f'admin_meta.submission_raw_{uuid.uuid4().hex}.json')
                                        try:
                                            with open(raw_path, 'w', encoding='utf-8') as rf:
                                                json.dump({'time': int(__import__('time').time()), 'submission': st.session_state['profile_pending']}, rf, indent=2, ensure_ascii=False)
                                        except Exception:
                                            pass
                                except Exception:
                                    pass

                                # Also write a non-authoritative merge so admins can see staged fields immediately
                                try:
                                    if st.session_state.get('profile_pending'):
                                        from modules import storage as _storage
                                        acct_for_save = acct_for_save if 'acct_for_save' in locals() else (auth.safe_email_to_schoolid(st.session_state.get('user_email','')) if st.session_state.get('user_email') else os.path.basename(storage.get_storage_dir()))
                                        # merge (non-force) will skip empty-string overwrites and won't create last-good
                                        _storage.write_admin_meta(acct_for_save, st.session_state.get('profile_pending') or {}, backup=True, force_replace=False)
                                except Exception:
                                    try:
                                        # As a last resort, write the staged values into admin_meta.json without force
                                        root = os.path.join(os.getcwd(), 'saved_exams_storage')
                                        acct_for_save = acct_for_save if 'acct_for_save' in locals() else (auth.safe_email_to_schoolid(st.session_state.get('user_email','')) if st.session_state.get('user_email') else os.path.basename(storage.get_storage_dir()))
                                        admf = os.path.join(root, acct_for_save, 'admin_meta.json')
                                        if os.path.exists(admf):
                                            try:
                                                with open(admf, 'r', encoding='utf-8') as fh:
                                                    cur = json.load(fh) or {}
                                            except Exception:
                                                cur = {}
                                        else:
                                            cur = {}
                                        merged = dict(cur)
                                        for k, v in (st.session_state.get('profile_pending') or {}).items():
                                            # skip empty-string overwrites
                                            try:
                                                if isinstance(v, str) and v.strip() == '' and merged.get(k, '') not in ('', None):
                                                    continue
                                            except Exception:
                                                pass
                                            merged[k] = v
                                        tmp = admf + '.tmp'
                                        with open(tmp, 'w', encoding='utf-8') as fh:
                                            json.dump(merged, fh, indent=2, ensure_ascii=False)
                                        os.replace(tmp, admf)
                                    except Exception:
                                        pass

                            

                            if cancelled:
                                # If profile completion is required for this session, disallow cancelling
                                if st.session_state.get('require_profile_complete'):
                                    container.warning('You must complete your profile before using the application. Please fill the fields and Confirm & Save.')
                                else:
                                    try:
                                        st.session_state['show_profile_editor'] = False
                                        # avoid calling st.experimental_rerun() inside the cancel handler
                                    except Exception:
                                        pass

                            # End of form: render final Confirm/Cancel actions outside the form so Streamlit doesn't complain
                            try:
                                if st.session_state.get('profile_confirm_pending'):
                                    container.markdown('---')
                                    container.warning('Are you sure you want to save these profile changes? This will update the account profile and hide the editor.')
                                    cc, dd = container.columns([1,1])
                                    with cc:
                                        if container.button('Yes — Save changes', key=f'profile_confirm_save_btn_{acct_key}_{nonce}_{modal_flag}_{container_id}'):
                                            # perform actual authoritative save
                                            pending = st.session_state.get('profile_pending') or {}
                                            try:
                                                ue = st.session_state.get('user_email', '') or ''
                                                acct_for_save = auth.safe_email_to_schoolid(ue) if ue else ''
                                                if not acct_for_save:
                                                    acct_for_save = os.path.basename(storage.get_storage_dir())
                                                # If the user requested a password change, attempt it first
                                                pw_pending = st.session_state.get('profile_pending_pw') or {}
                                                pw_old = (pw_pending.get('old_pw') or '').strip()
                                                pw_new = (pw_pending.get('new_pw') or '').strip()
                                                pw_new2 = (pw_pending.get('new_pw2') or '').strip()
                                                pw_change_requested = bool(pw_new or pw_new2)
                                                pw_change_failed = False
                                                if pw_change_requested:
                                                    # Require the user to provide their current password to authorize a change
                                                    if not pw_old:
                                                        container.error('Please provide your current password in the "Old password" field to change your password.')
                                                        pw_change_failed = True
                                                    elif pw_new != pw_new2:
                                                        container.error('New passwords do not match. Please correct and try again.')
                                                        pw_change_failed = True
                                                    else:
                                                        # determine username for reset: prefer signed-in username, then staged email, then admin_meta username
                                                        signed_email = (st.session_state.get('user_email') or pending.get('email') or '').strip()
                                                        username_for_reset = ''
                                                        if signed_email:
                                                            username_for_reset = str(signed_email).split('@')[0]
                                                        else:
                                                            # fallback to stored meta username if present
                                                            try:
                                                                mpath = os.path.join(os.getcwd(), 'saved_exams_storage', acct_for_save, 'admin_meta.json')
                                                                if os.path.exists(mpath):
                                                                    with open(mpath, 'r', encoding='utf-8') as _fh:
                                                                        mm = json.load(_fh) or {}
                                                                    username_for_reset = (mm.get('username') or '').split('@')[0]
                                                            except Exception:
                                                                username_for_reset = ''
                                                        if not username_for_reset:
                                                            container.error('You must be signed in to change your password. Please sign in and try again.')
                                                            pw_change_failed = True
                                                        else:
                                                            # First verify the provided old password matches the signed-in account
                                                            try:
                                                                # Verify password directly against the local users store to avoid side-effects
                                                                ok_auth = False
                                                                info_auth = ''
                                                                try:
                                                                    users_store = auth._load_users()
                                                                    urec = users_store.get(username_for_reset.strip().lower())
                                                                    if not urec:
                                                                        ok_auth = False
                                                                        info_auth = 'Unknown username'
                                                                    else:
                                                                        import base64, hashlib
                                                                        try:
                                                                            salt = base64.b64decode(urec.get('salt') or '')
                                                                            expected = base64.b64decode(urec.get('key') or '')
                                                                            key = hashlib.pbkdf2_hmac('sha256', (pw_old or '').encode('utf-8'), salt, 100000)
                                                                            ok_auth = (len(key) == len(expected) and all(a == b for a, b in zip(key, expected)))
                                                                            info_auth = 'Invalid password' if not ok_auth else 'OK'
                                                                        except Exception as _e:
                                                                            ok_auth = False
                                                                            info_auth = f'Password verification error: {_e}'
                                                                except Exception as _e:
                                                                    ok_auth = False
                                                                    info_auth = f'Users store error: {_e}'
                                                            except Exception:
                                                                ok_auth, info_auth = False, 'Authentication check failed'
                                                                # Log authentication attempt for debugging (no passwords written)
                                                                try:
                                                                    dbg_root = os.path.join(os.getcwd(), 'saved_exams_storage', acct_for_save)
                                                                    os.makedirs(dbg_root, exist_ok=True)
                                                                    dbg_path = os.path.join(dbg_root, 'password_change_debug.log')
                                                                    with open(dbg_path, 'a', encoding='utf-8') as _dbg:
                                                                        _dbg.write(json.dumps({'time': int(__import__('time').time()), 'username': username_for_reset, 'ok_auth': bool(ok_auth), 'info': str(info_auth)}) + "\n")
                                                                except Exception:
                                                                    pass
                                                                if not ok_auth:
                                                                    # Show clear message and include helper info when available
                                                                    try:
                                                                        container.error('Old password is incorrect. Please enter the password you used to sign in.')
                                                                        # also show the helper message for clarity (e.g. 'Unknown username' or 'Invalid password')
                                                                        if info_auth:
                                                                            container.info(f"Auth helper: {info_auth}")
                                                                    except Exception:
                                                                        pass
                                                                    pw_change_failed = True
                                                            else:
                                                                # attempt password reset via auth helper (this will also update stored hash)
                                                                ok_pw, info_pw = auth.reset_local_password(username_for_reset, pw_old or '', pw_new)
                                                                if not ok_pw:
                                                                    msg = info_pw or 'Password change failed'
                                                                    container.error('Password change failed: ' + msg)
                                                                    pw_change_failed = True
                                                                else:
                                                                    # Record a small session flag and inform user
                                                                    st.session_state['password_changed_at'] = int(__import__('time').time())
                                                                    container.info('Password changed successfully. Use your new password on your next sign-in.')

                                                # If password change was requested but failed, abort final save and keep staged data
                                                if pw_change_requested and pw_change_failed:
                                                    # keep the confirmation pending so user can correct details
                                                    st.session_state['profile_confirm_pending'] = True
                                                else:
                                                    ok, err = storage.write_admin_meta(acct_for_save, pending, backup=True, force_replace=True)
                                                    if not ok:
                                                        raise Exception(err or 'Unknown write error')

                                                    container.success('Profile saved')
                                                    # hide the editor until user explicitly opens it again
                                                    st.session_state['show_profile_editor'] = False
                                                    st.session_state['profile_confirm_pending'] = False
                                                    # If a password change was just performed, force the user to re-login
                                                    try:
                                                        if pw_change_requested and not pw_change_failed:
                                                            container.info('Password changed — you will be signed out. Please sign in again with your new password.')
                                                            # clear auth keys from session so the user must re-authenticate
                                                            for _k in ['user_email', 'user_uid', 'school_display_name']:
                                                                try:
                                                                    if _k in st.session_state:
                                                                        del st.session_state[_k]
                                                                except Exception:
                                                                    pass
                                                            # navigate to auth/login page
                                                            st.session_state['current_page'] = 'auth'
                                                            # Avoid calling rerun() inside the callback; Streamlit will rerun after the interaction
                                                    except Exception:
                                                        pass
                                            except Exception as e:
                                                # If an error occurred (including password mismatch or failed reset), show it and keep the editor open
                                                try:
                                                    container.error('Failed to save profile: ' + str(e))
                                                except Exception:
                                                    pass
                                            # clear pending state only if save completed
                                            if not (pw_change_requested and pw_change_failed):
                                                for k in ['profile_pending','profile_pending_pw']:
                                                    try:
                                                        del st.session_state[k]
                                                    except Exception:
                                                        pass
                                    with dd:
                                        # Show a prominent red Exit button that disables the profile feature when clicked
                                        try:
                                            container.markdown("<div style='color:#b91c1c; font-weight:700; margin-bottom:6px;'>\n⛔ This will disable the profile editing feature for this account.\n</div>", unsafe_allow_html=True)
                                        except Exception:
                                            pass
                                        if container.button('⛔ Exit (disable profile)', key=f'profile_confirm_exit_btn_{acct_key}_{nonce}_{modal_flag}_{container_id}'):
                                            try:
                                                ue = st.session_state.get('user_email', '') or ''
                                                acct_for_save = auth.safe_email_to_schoolid(ue) if ue else ''
                                                if not acct_for_save:
                                                    acct_for_save = os.path.basename(storage.get_storage_dir())
                                                # mark profile feature disabled so admin sees it and UI can honor it
                                                try:
                                                    ok, err = storage.write_admin_meta(acct_for_save, {'profile_feature_disabled': True}, backup=True, force_replace=False)
                                                except Exception:
                                                    try:
                                                        from modules import storage as _storage
                                                        ok, err = _storage.write_admin_meta(acct_for_save, {'profile_feature_disabled': True}, backup=True, force_replace=False)
                                                    except Exception:
                                                        ok = False
                                                # hide editor and clear staged data
                                                st.session_state['show_profile_editor'] = False
                                                st.session_state['profile_confirm_pending'] = False
                                                for k in ['profile_pending','profile_pending_pw']:
                                                    try:
                                                        del st.session_state[k]
                                                    except Exception:
                                                        pass
                                                try:
                                                    container.success('Profile feature disabled for this account. You can re-enable from the admin console.')
                                                except Exception:
                                                    pass
                                            except Exception:
                                                try:
                                                    container.error('Failed to disable profile feature')
                                                except Exception:
                                                    pass
                            except Exception:
                                pass

            if modal_fn is not None:
                # st.modal context exists: render a true modal overlay
                try:
                    with st.modal('Profile'):
                        _render_profile_form(st)
                except Exception:
                    # If modal failed for some reason show an error inside the page
                    st.error('Failed to open modal. Please try again.')
            else:
                # Fallback: render an inline profile editor that pushes the page content down
                try:
                    # Use the reserved placeholder so the editor appears in-page and pushes other content
                    try:
                        _render_profile_form(PROFILE_OVERLAY_PLACEHOLDER)
                    except Exception:
                        # As a fallback, create a new container and render into it
                        with st.container():
                            _render_profile_form(st)
                except Exception as e:
                    # If even inline rendering fails, show a friendly message and clear the flag
                    try:
                        st.error('Failed to render inline profile editor: ' + str(e))
                    except Exception:
                        pass
                    try:
                        st.session_state['show_profile_editor'] = False
                    except Exception:
                        pass
    except Exception:
        pass

    # (Header change-password removed) password change is handled inside the profile form below the country field

    # Render the main home page content below the profile editor
    try:
        render_home_page()
    except Exception:
        # Swallow errors silently here per user request (do not show the 'Failed to render' message)
        try:
            # preserve profile editor behavior but avoid signaling an on-page error
            pass
        except Exception:
            pass

elif st.session_state.current_page == 'new_exam':
    # Load and execute wrapper page that runs app.py and provides Save UI
    wrapper_path = os.path.join(os.path.dirname(__file__), 'modules', 'new_exam_with_save.py')
    if not os.path.exists(wrapper_path):
        # Fallback to original behavior if wrapper missing
        if st.button("⬅️ Back to Home", key="back_to_home_from_exam"):
            navigate_to('home')
        st.markdown("---")
        with open('app.py', 'r', encoding='utf-8') as f:
            app_code = f.read()
        exec(app_code, globals())
    else:
        # Use utf-8-sig to safely strip any BOM (U+FEFF)
        with open(wrapper_path, 'r', encoding='utf-8-sig') as f:
            wrapper_code = f.read().lstrip('\ufeff')
        ns = globals().copy()
        ns['__file__'] = wrapper_path  # ensure relative paths in wrapper resolve correctly
        exec(wrapper_code, ns)

elif st.session_state.current_page == 'report_cards':
    # Load and execute report_cards.py (the same page that appears in the sidebar)
    report_path = os.path.join(os.path.dirname(__file__), 'pages', 'report_cards.py')
    if os.path.exists(report_path):
        # Read with utf-8-sig to strip U+FEFF automatically; also guard with lstrip
        with open(report_path, 'r', encoding='utf-8-sig') as f:
            report_code = f.read().lstrip('\ufeff')
        ns = globals().copy()
        ns['__file__'] = report_path
        exec(report_code, ns)
    else:
        st.error("Report Cards page not found. Please ensure 'pages/report_cards.py' exists.")

elif st.session_state.current_page == 'student_history':
    # Load and execute student_history.py
    student_path = os.path.join(os.path.dirname(__file__), 'pages', 'student_history.py')
    if os.path.exists(student_path):
        with open(student_path, 'r', encoding='utf-8-sig') as f:
            student_code = f.read().lstrip('\ufeff')
        ns = globals().copy()
        ns['__file__'] = student_path
        exec(student_code, ns)
    else:
        st.error("Student History page not found. Please ensure 'pages/student_history.py' exists.")

elif st.session_state.current_page == 'directors_lounge':
    # Load and execute directors_lounge.py
    dl_path = os.path.join(os.path.dirname(__file__), 'pages', 'directors_lounge.py')
    if os.path.exists(dl_path):
        with open(dl_path, 'r', encoding='utf-8-sig') as f:
            dl_code = f.read().lstrip('\ufeff')
        ns = globals().copy()
        ns['__file__'] = dl_path
        exec(dl_code, ns)
    else:
        st.error("Director's Lounge page not found. Please ensure 'pages/directors_lounge.py' exists.")

elif st.session_state.current_page == 'bulk_photo_uploader':
    # Load and execute bulk_photo_uploader.py
    photo_path = os.path.join(os.path.dirname(__file__), 'pages', 'bulk_photo_uploader.py')
    if os.path.exists(photo_path):
        with open(photo_path, 'r', encoding='utf-8-sig') as f:
            photo_code = f.read().lstrip('\ufeff')
        ns = globals().copy()
        ns['__file__'] = photo_path
        exec(photo_code, ns)
    else:
        st.error("Bulk Photo Uploader page not found. Please ensure 'pages/bulk_photo_uploader.py' exists.")


elif st.session_state.current_page == 'auth':
    # Render the standalone auth_page (no sidebar should be visible while on this page)
    try:
        import auth_page
        auth_page.render_auth_page()
    except Exception:
        # fallback to modules.auth renderer
        from modules import auth as _auth
        _auth.render_login_page()
    # Stop further home rendering while on auth page
    st.stop()

else:
    # Other modules - placeholder for now
    if st.button("⬅️ Back to Home", key="back_to_home"):
        navigate_to('home')
    
    st.markdown("---")
    st.info(f"The page '{st.session_state.current_page}' is not available in this build.")

    


