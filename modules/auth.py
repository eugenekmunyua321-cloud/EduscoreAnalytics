import os
import json
import streamlit as st
from pathlib import Path
import hashlib
import base64
import time
try:
    import modules.billing as billing
except Exception:
    billing = None
try:
    from . import db as _db
except Exception:
    _db = None
USE_DB_STRICT = os.environ.get('USE_DB_STRICT', 'true').lower() in ('1', 'true', 'yes')

# Google/Firebase sign-in removed: this app now uses local username/password accounts only.
# Any previous firebase admin/client configuration files are ignored. Local accounts are
# stored in `saved_exams_storage/users.json` and managed by the helpers below.


USERS_FILE = Path(__file__).parent.parent / 'saved_exams_storage' / 'users.json'

# Branding colors (easy to tweak)
BRAND_PRIMARY = '#0f172a'  # deep navy
BRAND_ACCENT = '#2563eb'   # blue-600
BRAND_GRAD_A = '#06b6d4'   # cyan-500
BRAND_GRAD_B = '#7c3aed'   # violet-600
CARD_BG = '#ffffff'
TEXT_MUTED = '#4b5563'

def _safe_rerun():
    """Attempt to rerun the Streamlit app in a way compatible with multiple versions.
    Tries st.experimental_rerun(), then experimental_set_query_params(), then falls back to
    setting a session sentinel and stopping the script.
    """
    try:
        if hasattr(st, 'experimental_rerun'):
            try:
                st.experimental_rerun()
                return
            except Exception:
                pass
        # try forcing a small query param change which causes a rerun in many Streamlit versions
        if hasattr(st, 'experimental_set_query_params'):
            try:
                import time
                st.experimental_set_query_params(_rerun=int(time.time()))
                return
            except Exception:
                pass
    except Exception:
        pass
    # final fallback: set a small sentinel and stop; next user interaction will re-run
    try:
        st.session_state['_rerun_sentinel'] = st.session_state.get('_rerun_sentinel', 0) + 1
    except Exception:
        pass
    try:
        st.stop()
    except Exception:
        return


def _clear_user_session_keep_auth():
    """Clear session state keys that may contain user-specific data while keeping auth keys.
    Call this after a new sign-in so that previous account data isn't visible to the new account.
    """
    preserve = {'user_email', 'user_uid', 'school_display_name'}
    keys = list(st.session_state.keys())
    for k in keys:
        if k in preserve:
            continue
        try:
            del st.session_state[k]
        except Exception:
            pass
    # end for


def _clear_auth_ui_inputs():
    """Clear the auth UI input fields (sidebar, overlay, main) so forms are blank.
    Call this for new accounts or when you want the UI emptied.
    """
    keys_to_clear = [
        'sidebar_local_username', 'sidebar_local_password', 'sidebar_reg_username',
        'sidebar_reg_password', 'sidebar_reg_password2',
        'overlay_local_username', 'overlay_local_password', 'overlay_reg_username',
        'overlay_reg_password', 'overlay_reg_password2',
        'main_local_username', 'main_local_password', 'main_reg_username',
        'main_reg_password', 'main_reg_password2',
        'login_start_fresh'
    ]
    for k in keys_to_clear:
        try:
            # set to empty string for text inputs, False for checkboxes
            if k == 'login_start_fresh':
                st.session_state[k] = False
            else:
                st.session_state[k] = ''
        except Exception:
            try:
                del st.session_state[k]
            except Exception:
                pass


def _handle_post_signin(new_email: str, prefer_empty: bool = False, display_name: str = None):
    prev = st.session_state.get('user_email')
    st.session_state['user_email'] = new_email
    st.session_state['user_uid'] = safe_email_to_schoolid(new_email)
    if display_name:
        st.session_state['school_display_name'] = display_name
    else:
        st.session_state['school_display_name'] = st.session_state.get('school_display_name') or new_email.split('@')[0]

    if prefer_empty or (prev and prev != new_email):
        _clear_user_session_keep_auth()
        # Remove all exam-related session state to prevent data mixing
        for k in list(st.session_state.keys()):
            if k.startswith('saved_exam') or k.startswith('saved_exams') or k in ['cfg', 'current_page', 'view', 'selected_saved_exam_id', 'raw_marks']:
                try:
                    del st.session_state[k]
                except Exception:
                    pass
        # clear UI inputs so sidebar/overlay/main fields are blank for a new account
        try:
            _clear_auth_ui_inputs()
        except Exception:
            pass

    # After sign-in, check billing status. If the account has no active subscription
    # keep the user on the sign-in page and set a billing block so the sign-in UI
    # can show the payment/confirmation controls. Admin accounts bypass this.
    try:
        billing_block = False
        try:
            if billing is not None:
                secs = billing.seconds_until_expiry()
                is_admin = new_email.strip().lower() == 'admin@local'
                if secs <= 0 and not is_admin:
                    billing_block = True
        except Exception:
            billing_block = False

        if billing_block:
            st.session_state['billing_block'] = True
            # Mark billing block so UI can show payment/confirmation controls.
            # Do not set a non-existent multipage name (e.g. 'login') because some
            # Streamlit builds may not include a page with that id and will show
            # a "page not available" banner. Keep navigation keys untouched and
            # rely on the app/home UI to respect 'billing_block' when rendering.
            # Note: we intentionally avoid setting 'current_page' here.
        else:
            st.session_state['current_page'] = 'home'
            st.session_state['show_home_header'] = True
            # Do not set deprecated navigation keys 'view' or 'force_delegate_home'
    except Exception:
        pass


def _sign_out_all():
    keys = list(st.session_state.keys())
    for k in keys:
        try:
            del st.session_state[k]
        except Exception:
            pass
    try:
        st.session_state['current_page'] = 'home'
        st.session_state['show_home_header'] = True
    except Exception:
        pass


def safe_email_to_schoolid(email: str) -> str:
    if not email:
        return ''
    s = email.strip().lower()
    safe = ''.join([c if c.isalnum() or c in ('@', '.') else '_' for c in s])
    return safe.replace('@', '_at_').replace('.', '_')


def get_current_school_id():
    if 'user_email' in st.session_state and st.session_state.get('user_email'):
        return safe_email_to_schoolid(st.session_state.get('user_email'))
    return None


# --- Local user store ---
def _load_users():
    try:
        # If DB-only mode and DB available, read users from kv store
        try:
            if USE_DB_STRICT and _db is not None:
                _db.init_from_env()
                if _db.enabled():
                    users = _db.get_kv('users')
                    return users or {}
        except Exception:
            pass
        if not USERS_FILE.exists():
            return {}
        with USERS_FILE.open('r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_users(users: dict):
    try:
        # If DB-only and DB available, persist users into KV store
        try:
            if USE_DB_STRICT and _db is not None:
                _db.init_from_env()
                if _db.enabled():
                    return _db.set_kv('users', users)
        except Exception:
            pass
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = USERS_FILE.with_suffix('.tmp')
        with tmp.open('w', encoding='utf-8') as fh:
            json.dump(users, fh, indent=2, ensure_ascii=False)
        tmp.replace(USERS_FILE)
        return True
    except Exception:
        return False


def _generate_account_number():
    """Generate next account number like ED001, ED002... stored in accounts_index.json"""
    try:
        # If DB-only, store accounts_index in KV store
        try:
            if USE_DB_STRICT and _db is not None:
                _db.init_from_env()
                if _db.enabled():
                    idx = _db.get_kv('accounts_index') or {}
                    last = int(idx.get('last', 0) or 0)
                    nxt = last + 1
                    idx['last'] = nxt
                    try:
                        _db.set_kv('accounts_index', idx)
                    except Exception:
                        pass
                    return f"ED{nxt:03d}"
        except Exception:
            pass
        idx_file = USERS_FILE.parent / 'accounts_index.json'
        idx = {}
        if idx_file.exists():
            try:
                import json
                idx = json.loads(idx_file.read_text(encoding='utf-8') or '{}')
            except Exception:
                idx = {}
        last = int(idx.get('last', 0) or 0)
        nxt = last + 1
        idx['last'] = nxt
        try:
            idx_file.write_text(__import__('json').dumps(idx, indent=2, ensure_ascii=False), encoding='utf-8')
        except Exception:
            pass
        return f"ED{nxt:03d}"
    except Exception:
        # fallback: timestamp-based id
        try:
            return 'ED' + str(int(__import__('time').time()))
        except Exception:
            return 'ED000'


def create_local_user(username: str, password: str, display_name: str = None):
    try:
        if not username or not password:
            return False, 'Username and password are required.'
        username = username.strip().lower()
        users = _load_users()
        if username in users:
            return False, 'Username already exists.'
        salt = os.urandom(16)
        key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        users[username] = {
            'display_name': display_name or username,
            'salt': base64.b64encode(salt).decode('ascii'),
            'key': base64.b64encode(key).decode('ascii'),
            'created_at': int(time.time())
        }
        if _save_users(users):
            # initialize per-account storage skeleton so new accounts start empty
            try:
                from . import storage as _storage
                school_id = safe_email_to_schoolid(f"{username}@local")
                try:
                    _storage.initialize_account(school_id)
                except Exception:
                    pass
                # write admin_meta.json with account_number and default trial (30 days)
                acct_dir = USERS_FILE.parent / school_id
                try:
                    acct_dir.mkdir(parents=True, exist_ok=True)
                    adm = acct_dir / 'admin_meta.json'
                    created = int(time.time())
                    accno = _generate_account_number()
                    meta = {
                        'account_number': accno,
                        'username': username,
                        'email': f"{username}@local",
                        'phone': '',
                        'school_name': '',
                        'location': '',
                        'country': '',
                        'created_at': created,
                        'trial_until': created + 30 * 86400,
                        'active': True,
                        'disabled': False
                    }
                    try:
                        # Use storage helper to write admin_meta atomically and merge safely
                        try:
                            from . import storage as _storage
                            _storage.write_admin_meta(school_id, meta, backup=True, force_replace=False)
                        except Exception:
                            # Fallback: try importing storage again and use it; as a last resort, write directly
                            try:
                                from . import storage as _storage
                                _storage.write_admin_meta(school_id, meta, backup=True, force_replace=False)
                            except Exception:
                                try:
                                    adm.write_text(__import__('json').dumps(meta, indent=2, ensure_ascii=False), encoding='utf-8')
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    # Also create a billing.json file granting a 30-day trial (expiry_ts)
                    try:
                        bill = acct_dir / 'billing.json'
                        billing_obj = {
                            'expiry_ts': int(created + 30 * 86400),
                            'period_days': 30,
                            'last_payment_amount': 0.0
                        }
                        try:
                            bill.write_text(__import__('json').dumps(billing_obj, indent=2, ensure_ascii=False), encoding='utf-8')
                        except Exception:
                            pass
                    except Exception:
                        pass
                except Exception:
                    pass

                # notify admin by appending to admin_notifications.json in root storage
                try:
                    root_notify = USERS_FILE.parent
                    notif = root_notify / 'admin_notifications.json'
                    nots = []
                    if notif.exists():
                        try:
                            nots = __import__('json').loads(notif.read_text(encoding='utf-8') or '[]')
                        except Exception:
                            nots = []
                    nots.append({'type': 'new_account', 'username': username, 'account_number': accno, 'status': 'pending', 'created_at': int(time.time())})
                    try:
                        notif.write_text(__import__('json').dumps(nots, indent=2, ensure_ascii=False), encoding='utf-8')
                    except Exception:
                        pass
                except Exception:
                    pass

                # set session flag so UI can prompt the user to complete profile
                try:
                    st.session_state['must_complete_profile'] = username
                    # keep user on the login/profile page so they can complete the profile
                    try:
                        st.session_state['current_page'] = 'login'
                        st.session_state['billing_block'] = False
                    except Exception:
                        pass
                except Exception:
                    pass
            except Exception:
                pass
            return True, 'User created.'
        return False, 'Failed to save user store.'
    except Exception as e:
        return False, f'Failed to create user: {e}'


def reset_local_password(username: str, old_password: str, new_password: str):
    """Reset password only if old_password matches. Updates salt/key."""
    try:
        if not username or not old_password or not new_password:
            return False, 'All fields required.'
        ok, info = authenticate_local_user(username, old_password)
        if not ok:
            return False, 'Old password incorrect.'
        users = _load_users()
        u = users.get(username.strip().lower())
        if not u:
            return False, 'Unknown user.'
        salt = os.urandom(16)
        key = hashlib.pbkdf2_hmac('sha256', new_password.encode('utf-8'), salt, 100000)
        u['salt'] = base64.b64encode(salt).decode('ascii')
        u['key'] = base64.b64encode(key).decode('ascii')
        users[username.strip().lower()] = u
        if _save_users(users):
            return True, 'Password updated.'
        return False, 'Failed to save new password.'
    except Exception as e:
        return False, str(e)


def admin_reset_password(username: str, new_password: str):
    """Force-reset a user's password without requiring the old password.
    Intended for use by administrators. Records a small audit entry when successful.
    """
    try:
        if not username or not new_password:
            return False, 'Username and new password required.'
        username = username.strip().lower()
        users = _load_users()
        u = users.get(username)
        if not u:
            return False, 'Unknown user.'
        salt = os.urandom(16)
        key = hashlib.pbkdf2_hmac('sha256', new_password.encode('utf-8'), salt, 100000)
        u['salt'] = base64.b64encode(salt).decode('ascii')
        u['key'] = base64.b64encode(key).decode('ascii')
        users[username] = u
        if _save_users(users):
            # write a lightweight audit entry to admin_actions.log (keep small and non-sensitive)
            try:
                root = USERS_FILE.parent
                audit = root / 'admin_actions.log'
                prev = []
                if audit.exists():
                    try:
                        prev = json.loads(audit.read_text(encoding='utf-8') or '[]')
                    except Exception:
                        prev = []
                prev.append({'time': int(time.time()), 'action': 'admin_reset_password', 'username': username})
                try:
                    audit.write_text(json.dumps(prev[-200:], indent=2, ensure_ascii=False), encoding='utf-8')
                except Exception:
                    pass
            except Exception:
                pass
            return True, 'Password reset.'
        return False, 'Failed to save users.'
    except Exception as e:
        return False, str(e)


def authenticate_local_user(username: str, password: str):
    try:
        if not username or not password:
            return False, 'Username and password required.'
        username = username.strip().lower()
        users = _load_users()
        u = users.get(username)
        if not u:
            return False, 'Unknown username.'
        salt = base64.b64decode(u.get('salt'))
        expected = base64.b64decode(u.get('key'))
        key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        if len(key) == len(expected) and all(a == b for a, b in zip(key, expected)):
            # Check per-account admin_meta.json for disabled flag
            try:
                acct_dir = USERS_FILE.parent / safe_email_to_schoolid(f"{username}@local")
                ameta = acct_dir / 'admin_meta.json'
                if ameta.exists():
                    try:
                        am = json.loads(ameta.read_text(encoding='utf-8') or '{}')
                        if bool(am.get('disabled', False)):
                            return False, 'Account disabled. Contact administrator.'
                    except Exception:
                        pass
            except Exception:
                pass
            # Enforce expiry: block login if expiry_ts is missing, zero, or expired (non-admins only)
            is_admin = username.strip().lower() == 'admin'
            if not is_admin:
                try:
                    import modules.billing as billing
                    acct_dir = USERS_FILE.parent / safe_email_to_schoolid(f"{username}@local")
                    acct = billing.get_account_billing(str(acct_dir)) or {}
                    expiry_ts = int(acct.get('expiry_ts') or 0)
                    import time as _t
                    debug_info = {
                        'checked_dir': str(acct_dir),
                        'expiry_ts': expiry_ts,
                        'now': int(_t.time()),
                        'acct': acct,
                        'username': username
                    }
                    st.session_state['debug_auth_check'] = debug_info
                    # Also log to file for persistent inspection
                    try:
                        debug_log_path = USERS_FILE.parent / 'debug_auth_log.json'
                        import json as _json
                        prev = []
                        if debug_log_path.exists():
                            try:
                                prev = _json.loads(debug_log_path.read_text(encoding='utf-8') or '[]')
                            except Exception:
                                prev = []
                        prev.append(debug_info)
                        debug_log_path.write_text(_json.dumps(prev[-50:], indent=2, ensure_ascii=False), encoding='utf-8')
                    except Exception:
                        pass
                    if expiry_ts <= 0 or expiry_ts <= int(_t.time()):
                        return False, 'Subscription expired. Please submit payment receipt for confirmation before signing in.'
                except Exception as e:
                    st.session_state['debug_auth_error'] = str(e)
                    # Also log error to file
                    try:
                        debug_log_path = USERS_FILE.parent / 'debug_auth_log.json'
                        import json as _json
                        prev = []
                        if debug_log_path.exists():
                            try:
                                prev = _json.loads(debug_log_path.read_text(encoding='utf-8') or '[]')
                            except Exception:
                                prev = []
                        prev.append({'error': str(e), 'username': username})
                        debug_log_path.write_text(_json.dumps(prev[-50:], indent=2, ensure_ascii=False), encoding='utf-8')
                    except Exception:
                        pass
                    return False, 'Subscription expired. Please submit payment receipt for confirmation before signing in.'
            return True, u.get('display_name') or username
        return False, 'Invalid password.'
    except Exception as e:
        return False, f'Authentication error: {e}'


def show_login_ui():
    st.sidebar.markdown('### School sign-in (local)')
    st.sidebar.write('Sign in with a local username/password stored on this machine.')
    st.sidebar.markdown('')
    st.sidebar.markdown('**Sign in**')
    sidebar_username = st.sidebar.text_input('Username', value='', key='sidebar_local_username')
    sidebar_password = st.sidebar.text_input('Password', value='', type='password', key='sidebar_local_password')
    if st.sidebar.button('Sign in with local account'):
        ok, info = authenticate_local_user(sidebar_username, sidebar_password)
        if ok:
            email_like = f"{sidebar_username}@local"
            _handle_post_signin(email_like, prefer_empty=False, display_name=info)
            st.sidebar.success(f'Signed in as {email_like}')
            _safe_rerun()
        else:
            st.sidebar.error(info)

    st.sidebar.markdown('')
    st.sidebar.markdown('**Register new local account**')
    reg_user = st.sidebar.text_input('New username', value='', key='sidebar_reg_username')
    reg_pass = st.sidebar.text_input('New password', value='', type='password', key='sidebar_reg_password')
    reg_pass2 = st.sidebar.text_input('Confirm password', value='', type='password', key='sidebar_reg_password2')
    if st.sidebar.button('Register new local account'):
        if not reg_user or not reg_pass:
            st.sidebar.error('Please provide a username and password.')
        elif reg_pass != reg_pass2:
            st.sidebar.error('Passwords do not match.')
        else:
            ok, msg = create_local_user(reg_user, reg_pass, display_name=reg_user)
            if ok:
                email_like = f"{reg_user}@local"
                _handle_post_signin(email_like, prefer_empty=True, display_name=reg_user)
                st.sidebar.success('Account created and signed in.')
                _safe_rerun()
            else:
                st.sidebar.error(msg)

    if st.sidebar.button('Sign out'):
        _sign_out_all()
        st.sidebar.info('Signed out')
        _safe_rerun()


def require_login_overlay(blocking: bool = True):
    if st.session_state.get('user_uid') and st.session_state.get('user_email'):
        return

    overlay_css = """
    <style>
     .auth-overlay { position: fixed; left:0; top:0; right:0; bottom:0; background: linear-gradient(90deg, rgba(0,0,0,0.6), rgba(0,0,0,0.5)); z-index: 9999; display:flex; align-items:center; justify-content:center; pointer-events: none; }
     .auth-card { background: linear-gradient(180deg, #ffffff, #fbfbfe); padding: 28px; border-radius:12px; max-width:520px; width:92%; box-shadow:0 12px 40px rgba(3,20,55,0.18); pointer-events: auto; position: relative; z-index: 10001; font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial; }
     .auth-card h3 { margin: 0 0 8px 0; color: #03204a; }
     .auth-card p { margin: 0 0 12px 0; color: #2b3a55; }
     .auth-hr { height:1px; background: linear-gradient(90deg,#e6eefb,#ffffff); margin:14px 0; border-radius:4px; }
    </style>
    """
    st.markdown(overlay_css, unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 0.8, 1])
    with col2:
        st.markdown("""
        <div class='auth-overlay'>
          <div class='auth-card'>
            <h3>Welcome back</h3>
            <p>Sign in to access your school's dashboard.</p>
            <div class='auth-hr'></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('---')
        st.markdown('**Local account (username/password)**')
        ov_user = st.text_input('Username', value='', key='overlay_local_username')
        ov_pass = st.text_input('Password', value='', type='password', key='overlay_local_password')
        if st.button('Sign in with local account', key='overlay_local_signin'):
            ok, info = authenticate_local_user(ov_user, ov_pass)
            if ok:
                email_like = f"{ov_user}@local"
                _handle_post_signin(email_like, prefer_empty=False, display_name=info)
                st.success(f'Signed in as {email_like}')
                _safe_rerun()
            else:
                st.error(info)

        st.markdown('Register new local account')
        reg_user = st.text_input('New username', value='', key='overlay_reg_username')
        reg_pass = st.text_input('New password', value='', type='password', key='overlay_reg_password')
        reg_pass2 = st.text_input('Confirm password', value='', type='password', key='overlay_reg_password2')
        if st.button('Register new local account', key='overlay_reg_create'):
            if not reg_user or not reg_pass:
                st.error('Please provide a username and password.')
            elif reg_pass != reg_pass2:
                st.error('Passwords do not match.')
            else:
                ok, msg = create_local_user(reg_user, reg_pass, display_name=reg_user)
                if ok:
                    email_like = f"{reg_user}@local"
                    _handle_post_signin(email_like, prefer_empty=True, display_name=reg_user)
                    st.success('Account created and signed in.')
                    _safe_rerun()
                else:
                    st.error(msg)

    if blocking and not (st.session_state.get('user_uid') and st.session_state.get('user_email')):
        st.stop()


def render_login_page():
    # Brief login intro (removed 'under construction' banner per admin request)
    try:
        st.markdown("""
        <div style='padding:8px; border-radius:6px; background:#f1f5f9; color:#0f172a;'>
            <strong style='font-size:16px'>Sign in</strong>
            <div style='margin-top:6px; color:#374151'>Use your local username and password. If your subscription has expired, you'll be prompted to submit a payment receipt for admin approval on this page.</div>
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        try:
            st.info('Sign in using your local username/password. If your subscription expired, submit a payment receipt below for admin approval.')
        except Exception:
            pass
    # If a newly-registered user must complete their profile, show the profile form here.
    try:
        must = st.session_state.get('must_complete_profile')
        if must:
            st.markdown('### Complete your school profile')
            st.info('Please complete these details so the administrator can see your school information.')
            with st.form('complete_profile'):
                phone = st.text_input('Phone number', value='', key='profile_phone')
                school_name = st.text_input('School name', value='', key='profile_school_name')
                contact_email = st.text_input('Contact email', value=f"{must}@local", key='profile_email')
                location = st.text_input('Location', value='', key='profile_location')
                country = st.text_input('Country', value='', key='profile_country')
                submit = st.form_submit_button('Save profile')
            if submit:
                try:
                    sid = safe_email_to_schoolid(f"{must}@local")
                    acct_dir = USERS_FILE.parent / sid
                    acct_dir.mkdir(parents=True, exist_ok=True)
                    admf = acct_dir / 'admin_meta.json'
                    am = {}
                    if admf.exists():
                        try:
                            am = json.loads(admf.read_text(encoding='utf-8') or '{}')
                        except Exception:
                            am = {}
                    am.update({
                        'phone': str(phone).strip(),
                        'school_name': str(school_name).strip(),
                        'email': str(contact_email).strip(),
                        'location': str(location).strip(),
                        'country': str(country).strip()
                    })
                    try:
                        # Use force_replace here: this initial profile completion
                        # by the user should be authoritative for their account.
                        try:
                            from . import storage as _storage
                            _storage.write_admin_meta(sid, am, backup=True, force_replace=True)
                        except Exception:
                            # Try storage again as a fallback, then last-resort direct write
                            try:
                                from . import storage as _storage
                                _storage.write_admin_meta(sid, am, backup=True, force_replace=True)
                            except Exception:
                                try:
                                    admf.write_text(json.dumps(am, indent=2, ensure_ascii=False), encoding='utf-8')
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    # mark notification as completed if present
                    try:
                        root_notify = USERS_FILE.parent
                        notif = root_notify / 'admin_notifications.json'
                        if notif.exists():
                            try:
                                nlist = json.loads(notif.read_text(encoding='utf-8') or '[]')
                            except Exception:
                                nlist = []
                            for n in nlist:
                                if n.get('type') == 'new_account' and n.get('username') == must and n.get('status') == 'pending':
                                    n['status'] = 'profile_completed'
                                    n['completed_at'] = int(time.time())
                            try:
                                notif.write_text(json.dumps(nlist, indent=2, ensure_ascii=False), encoding='utf-8')
                            except Exception:
                                pass
                    except Exception:
                        pass
                    st.success('Profile saved. You may continue to the app.')
                    try:
                        del st.session_state['must_complete_profile']
                    except Exception:
                        st.session_state['must_complete_profile'] = False
                    _safe_rerun()
                except Exception as e:
                    st.error('Failed to save profile: ' + str(e))
            # stop further rendering to keep focus on profile
            st.stop()
    except Exception:
        pass
    # If already signed in, normally we skip rendering the login page. However,
    # if the account is billing-blocked (no active subscription) we still render
    # the login page so the user can confirm payment from here.
    if st.session_state.get('user_uid') and st.session_state.get('user_email'):
        # If user is signed in and NOT billing-blocked show a read-only profile view
        if not st.session_state.get('billing_block'):
            try:
                sid = st.session_state.get('user_uid')
                acct_dir = USERS_FILE.parent / sid
                admf = acct_dir / 'admin_meta.json'
                am = {}
                if admf.exists():
                    try:
                        am = json.loads(admf.read_text(encoding='utf-8') or '{}')
                    except Exception:
                        am = {}
                st.markdown('### Your school profile')
                st.write('These details were provided during account setup; they are read-only. Contact the administrator to make changes.')
                cols = st.columns(2)
                left, right = cols[0], cols[1]
                with left:
                    st.markdown(f"**Account number:** {am.get('account_number','(not set)')}")
                    st.markdown(f"**School name:** {am.get('school_name','')}")
                    st.markdown(f"**Contact email:** {am.get('email','')}")
                with right:
                    st.markdown(f"**Phone:** {am.get('phone','')}")
                    st.markdown(f"**Location:** {am.get('location','')}")
                    st.markdown(f"**Country:** {am.get('country','')}")
                # show trial expiry if present
                try:
                    tu = am.get('trial_until') or am.get('trial_until_ts')
                    if tu:
                        import datetime as _dt
                        try:
                            expiry = _dt.datetime.fromtimestamp(int(tu)).strftime('%Y-%m-%d')
                            st.markdown(f"**Trial until:** {expiry}")
                        except Exception:
                            st.markdown(f"**Trial until:** {tu}")
                except Exception:
                    pass
            except Exception:
                pass
            return

        st.markdown(f"""
        <style>
            :root {{ --brand-primary: {BRAND_PRIMARY}; --brand-accent: {BRAND_ACCENT}; --grad-a: {BRAND_GRAD_A}; --grad-b: {BRAND_GRAD_B}; --card-bg: {CARD_BG}; --muted: {TEXT_MUTED}; }}
            .login-hero {{ display:flex; align-items:center; justify-content:center; min-height:75vh; font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial; background: linear-gradient(180deg, #f8fafc, #eef2ff); padding:32px 0; }}
            .login-card {{ display:flex; gap:28px; align-items:stretch; max-width:1000px; width:96%; background: var(--card-bg); padding:28px; border-radius:16px; box-shadow:0 26px 80px rgba(2,6,23,0.12); overflow:hidden; }}
            .login-left {{ flex:1; padding:28px 30px; background: linear-gradient(180deg, rgba(6,182,212,0.06), rgba(124,58,237,0.04)); display:flex; flex-direction:column; justify-content:center; gap:12px; }}
            .login-left h2 {{ margin:0; color: var(--brand-primary); font-size:22px; line-height:1.12; }}
            .login-left p {{ color:var(--muted); margin-top:4px; max-width:46ch; }}
            .brand-pill {{ display:inline-block; background: linear-gradient(90deg,var(--grad-a),var(--grad-b)); color:white; padding:8px 14px; border-radius:999px; font-weight:700; letter-spacing:0.2px; font-size:14px; box-shadow:0 6px 18px rgba(37,99,235,0.12); }}
            .login-right {{ width:420px; padding:18px 22px 22px 22px; display:flex; flex-direction:column; gap:12px; }}

            /* Style form inputs and buttons to look modern */
            input[type='text'], input[type='password'], textarea {{
                width:100%; padding:12px 14px; border-radius:10px; border:1px solid #e6eef7; box-shadow:inset 0 1px 0 rgba(16,24,40,0.02); outline:none; font-size:14px; color: var(--brand-primary);
            }}
            input::placeholder {{ color:#9aa7bd; }}
            .stButton>button {{ background: linear-gradient(90deg,var(--grad-a),var(--grad-b)); color: white; border: none; padding:10px 14px; border-radius:10px; font-weight:600; box-shadow:0 8px 24px rgba(37,99,235,0.16); cursor:pointer; }}
            .stButton>button:hover {{ transform: translateY(-1px); box-shadow:0 12px 36px rgba(37,99,235,0.18); }}
            .muted-note {{ color:var(--muted); font-size:13px; margin-top:6px; }}
        </style>
        <div class='login-hero'>
            <div class='login-card'>
                <div class='login-left'>
                    <div class='brand-pill'>EDUSCORE</div>
                    <h2>EduScore Analytics — Beautifully clear results</h2>
                    <p>Sign in to access your school's dashboard, save exams, and communicate results to parents. Your data is stored per account.</p>
                </div>
                <div class='login-right'>
        """, unsafe_allow_html=True)

    # If this session is billing-blocked (expired or no subscription) show
    # prominent login details and remaining time. User cannot access other
    # pages until they confirm payment here.
    if st.session_state.get('billing_block'):
        user_email = st.session_state.get('user_email') or ''
        display_name = st.session_state.get('school_display_name') or user_email.split('@')[0]
        try:
            if billing is not None:
                rem = billing.human_readable_remaining()
                acct = billing.get_account_billing() or {}
                expiry_ts = acct.get('expiry_ts') or 0
                from datetime import datetime
                expiry_str = datetime.fromtimestamp(expiry_ts).strftime('%Y-%m-%d %H:%M') if expiry_ts and expiry_ts > 0 else 'No active subscription'
            else:
                rem = 'Not configured'
                expiry_str = 'N/A'
        except Exception:
            rem = 'Not available'
            expiry_str = 'N/A'

        st.markdown('### Login details & subscription status')
        st.info(f"Logged in as: {display_name} ({user_email})")
        st.write(f"Subscription remaining: {rem} — Expires: {expiry_str}")
        st.write('You cannot access other pages until you confirm payment below. Use the MPESA payment form on this page to activate your account for the configured period.')

    st.markdown('### Local account sign-in')
    st.write('Create or sign in with a username/password stored locally on this machine.')
    main_user = st.text_input('Username', value='', key='main_local_username', placeholder='e.g. oakridge_high')
    main_pass = st.text_input('Password', value='', type='password', key='main_local_password', placeholder='Your secure password')
    if st.button('Sign in with local account'):
        ok, info = authenticate_local_user(main_user, main_pass)
        if ok:
            email_like = f"{main_user}@local"
            _handle_post_signin(email_like, prefer_empty=False, display_name=info)
            st.success(f'Signed in as {email_like}')
            _safe_rerun()
        else:
            st.error(info)

    st.markdown('#### Register new local account')
    reg_user = st.text_input('New username', value='', key='main_reg_username', placeholder='choose a username')
    reg_pass = st.text_input('New password', value='', type='password', key='main_reg_password', placeholder='create a strong password')
    reg_pass2 = st.text_input('Confirm password', value='', type='password', key='main_reg_password2', placeholder='repeat password')
    if st.button('Register new local account'):
        if not reg_user or not reg_pass:
            st.error('Please provide a username and password.')
        elif reg_pass != reg_pass2:
            st.error('Passwords do not match.')
        else:
            ok, msg = create_local_user(reg_user, reg_pass, display_name=reg_user)
            if ok:
                email_like = f"{reg_user}@local"
                _handle_post_signin(email_like, prefer_empty=True, display_name=reg_user)
                st.success('Account created and signed in.')
                _safe_rerun()
            else:
                st.error(msg)

    # Password reset UI moved into the profile editor in home.py (appears in the profile box)

    # --- Payment guidance (MPESA) - actual receipt submission is handled on the main auth page ---
    try:
        st.markdown('---')
        st.markdown('### Payment / Subscription')
        global_cfg = billing.get_global_billing_config() if billing is not None else {'price_ksh': 500, 'period_days': 30, 'receiver_phone': '0793975959'}
        default_receiver = global_cfg.get('receiver_phone', '0793975959')
        st.info(f"Please send payment of KSH {global_cfg.get('price_ksh', 500)} to {default_receiver}. After making the payment, paste the MPESA SMS message in the box on the sign-in screen to submit it for admin review.")
    except Exception:
        pass

    # Guest access disabled when billing is enforced
    st.info('Guest access is disabled. Please sign in or register a local account.')

    st.markdown("""
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Developer/emergency sign-in removed.

    # If billing_block is set, stop further rendering so user cannot access other pages.
    if st.session_state.get('billing_block'):
        # Keep the user on this page until they have confirmed payment.
        try:
            st.warning('Account access is blocked until payment is confirmed on this page.')
        except Exception:
            pass
        st.stop()


def verify_id_token(id_token: str):
    """Deprecated stub; Firebase removed."""
    return None
    


def safe_email_to_schoolid(email: str) -> str:
    if not email:
        return ''
    s = email.strip().lower()
    safe = ''.join([c if c.isalnum() or c in ('@', '.') else '_' for c in s])
    return safe.replace('@', '_at_').replace('.', '_')


def get_current_school_id():
    if 'user_email' in st.session_state and st.session_state.get('user_email'):
        return safe_email_to_schoolid(st.session_state.get('user_email'))
    return None


# --- Local user store ---
def _load_users():
    try:
        if not USERS_FILE.exists():
            return {}
        with USERS_FILE.open('r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_users(users: dict):
    try:
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = USERS_FILE.with_suffix('.tmp')
        with tmp.open('w', encoding='utf-8') as fh:
            json.dump(users, fh, indent=2, ensure_ascii=False)
        tmp.replace(USERS_FILE)
        return True
    except Exception:
        return False


# The rich create_local_user implementation is defined earlier in this file.
# Duplicate definitions were removed to avoid accidental recursion.




def show_login_ui():
    st.sidebar.markdown('### School sign-in (local)')
    st.sidebar.write('Sign in with a local username/password stored on this machine.')
    st.sidebar.markdown('')
    st.sidebar.markdown('**Sign in**')
    sidebar_username = st.sidebar.text_input('Username', value='', key='sidebar_local_username')
    sidebar_password = st.sidebar.text_input('Password', value='', type='password', key='sidebar_local_password')
    if st.sidebar.button('Sign in with local account'):
        ok, info = authenticate_local_user(sidebar_username, sidebar_password)
        if ok:
            email_like = f"{sidebar_username}@local"
            _handle_post_signin(email_like, prefer_empty=False, display_name=info)
            st.sidebar.success(f'Signed in as {email_like}')
            _safe_rerun()
        else:
            st.sidebar.error(info)

    st.sidebar.markdown('')
    st.sidebar.markdown('**Register new local account**')
    reg_user = st.sidebar.text_input('New username', value='', key='sidebar_reg_username')
    reg_pass = st.sidebar.text_input('New password', value='', type='password', key='sidebar_reg_password')
    reg_pass2 = st.sidebar.text_input('Confirm password', value='', type='password', key='sidebar_reg_password2')
    if st.sidebar.button('Register new local account'):
        if not reg_user or not reg_pass:
            st.sidebar.error('Please provide a username and password.')
        elif reg_pass != reg_pass2:
            st.sidebar.error('Passwords do not match.')
        else:
            ok, msg = create_local_user(reg_user, reg_pass, display_name=reg_user)
            if ok:
                email_like = f"{reg_user}@local"
                _handle_post_signin(email_like, prefer_empty=True, display_name=reg_user)
                st.sidebar.success('Account created and signed in.')
                _safe_rerun()
            else:
                st.sidebar.error(msg)

    if st.sidebar.button('Sign out'):
        _sign_out_all()
        st.sidebar.info('Signed out')
        _safe_rerun()



def require_login_overlay(blocking: bool = True):
    if st.session_state.get('user_uid') and st.session_state.get('user_email'):
        return

    overlay_css = """
    <style>
     .auth-overlay { position: fixed; left:0; top:0; right:0; bottom:0; background: linear-gradient(90deg, rgba(0,0,0,0.6), rgba(0,0,0,0.5)); z-index: 9999; display:flex; align-items:center; justify-content:center; pointer-events: none; }
     .auth-card { background: linear-gradient(180deg, #ffffff, #fbfbfe); padding: 28px; border-radius:12px; max-width:520px; width:92%; box-shadow:0 12px 40px rgba(3,20,55,0.18); pointer-events: auto; position: relative; z-index: 10001; font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial; }
     .auth-card h3 { margin: 0 0 8px 0; color: #03204a; }
     .auth-card p { margin: 0 0 12px 0; color: #2b3a55; }
     .auth-hr { height:1px; background: linear-gradient(90deg,#e6eefb,#ffffff); margin:14px 0; border-radius:4px; }
    </style>
    """
    st.markdown(overlay_css, unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 0.8, 1])
    with col2:
        st.markdown("""
        <div class='auth-overlay'>
          <div class='auth-card'>
            <h3>Welcome back</h3>
            <p>Sign in to access your school's dashboard.</p>
            <div class='auth-hr'></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('---')
        st.markdown('**Local account (username/password)**')
        ov_user = st.text_input('Username', value='', key='overlay_local_username')
        ov_pass = st.text_input('Password', value='', type='password', key='overlay_local_password')
        if st.button('Sign in with local account', key='overlay_local_signin'):
            ok, info = authenticate_local_user(ov_user, ov_pass)
            if ok:
                email_like = f"{ov_user}@local"
                _handle_post_signin(email_like, prefer_empty=False, display_name=info)
                st.success(f'Signed in as {email_like}')
                _safe_rerun()
            else:
                st.error(info)

        st.markdown('Register new local account')
        reg_user = st.text_input('New username', value='', key='overlay_reg_username')
        reg_pass = st.text_input('New password', value='', type='password', key='overlay_reg_password')
        reg_pass2 = st.text_input('Confirm password', value='', type='password', key='overlay_reg_password2')
        if st.button('Register new local account', key='overlay_reg_create'):
            if not reg_user or not reg_pass:
                st.error('Please provide a username and password.')
            elif reg_pass != reg_pass2:
                st.error('Passwords do not match.')
            else:
                ok, msg = create_local_user(reg_user, reg_pass, display_name=reg_user)
                if ok:
                    email_like = f"{reg_user}@local"
                    _handle_post_signin(email_like, prefer_empty=True, display_name=reg_user)
                    st.success('Account created and signed in.')
                    _safe_rerun()
                else:
                    st.error(msg)

    if blocking and not (st.session_state.get('user_uid') and st.session_state.get('user_email')):
        st.stop()


def render_login_page():
    if st.session_state.get('user_uid') and st.session_state.get('user_email'):
        return
        st.markdown("""
        <style>
            .login-hero { display:flex; align-items:center; justify-content:center; min-height:72vh; font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial; }
            .login-card { display:flex; gap:28px; align-items:stretch; max-width:980px; width:94%; background: linear-gradient(180deg,#ffffff,#fbfcff); padding:28px; border-radius:14px; box-shadow:0 18px 60px rgba(2,20,60,0.12); }
            .login-left { flex:1; padding:18px; }
            .login-left h2 { margin:0; color:#04204c; }
            .login-left p { color:#35506d; margin-top:8px; }
            .brand-pill { display:inline-block; background: linear-gradient(90deg,#3b82f6,#60a5fa); color:white; padding:6px 12px; border-radius:999px; font-weight:600; margin-bottom:10px; }
            .login-right { width:420px; padding:6px 12px 18px 12px; }
        </style>
        <div class='login-hero'>
            <div class='login-card'>
                <div class='login-left'>
                    <div class='brand-pill'>EduScore Analytics</div>
                    <h2>Your school's results, analysed beautifully</h2>
                    <p>Secure, local accounts. Sign in to view reports, save exams, and share results with parents.</p>
                </div>
                <div class='login-right'>
        """, unsafe_allow_html=True)

    st.markdown('### Local account sign-in')
    st.write('Create or sign in with a username/password stored locally on this machine.')
    main_user = st.text_input('Username', value='', key='main_local_username')
    main_pass = st.text_input('Password', value='', type='password', key='main_local_password')
    if st.button('Sign in with local account'):
        ok, info = authenticate_local_user(main_user, main_pass)
        if ok:
            email_like = f"{main_user}@local"
            _handle_post_signin(email_like, prefer_empty=False, display_name=info)
            st.success(f'Signed in as {email_like}')
            _safe_rerun()
        else:
            st.error(info)

    st.markdown('#### Register new local account')
    reg_user = st.text_input('New username', value='', key='main_reg_username')
    reg_pass = st.text_input('New password', value='', type='password', key='main_reg_password')
    reg_pass2 = st.text_input('Confirm password', value='', type='password', key='main_reg_password2')
    if st.button('Register new local account'):
        if not reg_user or not reg_pass:
            st.error('Please provide a username and password.')
        elif reg_pass != reg_pass2:
            st.error('Passwords do not match.')
        else:
            ok, msg = create_local_user(reg_user, reg_pass, display_name=reg_user)
            if ok:
                email_like = f"{reg_user}@local"
                _handle_post_signin(email_like, prefer_empty=True, display_name=reg_user)
                st.success('Account created and signed in.')
                _safe_rerun()
            else:
                st.error(msg)

    # Guest access disabled when billing is enforced
    st.info('Guest access is disabled. Please sign in or register a local account.')

    st.markdown("""
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Developer/emergency sign-in removed.

def verify_id_token(id_token: str):
    """Deprecated stub; Firebase removed."""
    return None
