import streamlit as st
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).parent / 'saved_exams_storage'
USERS_FILE = ROOT / 'users.json'
ADMINS_FILE = ROOT / 'admins.json'

st.set_page_config(page_title='Admin — Messaging config (console)', layout='centered')
st.title('Admin: Messaging configuration (console)')

# Simple login: require a local user + password and membership in admins.json
st.markdown('Sign in with your admin local account')
username = st.text_input('Admin username')
password = st.text_input('Admin password', type='password')

if 'am_authed' not in st.session_state:
    st.session_state['am_authed'] = False

if not st.session_state['am_authed']:
    if st.button('Sign in'):
        try:
            from modules.auth import authenticate_local_user
            ok, info = authenticate_local_user(username, password)
        except Exception:
            ok, info = False, 'Authentication backend missing.'
        if not ok:
            st.error(f'Auth failed: {info}')
            st.stop()

        # verify admin list
        try:
            if ADMINS_FILE.exists():
                d = json.loads(ADMINS_FILE.read_text(encoding='utf-8') or '{}')
                admins = d.get('admins', []) if isinstance(d, dict) else []
            else:
                admins = ['admin@local']
        except Exception:
            admins = ['admin@local']

        email_like = f"{username}@local"
        if email_like not in admins:
            st.error('This user is not in admins.json')
            st.stop()

        st.session_state['am_authed'] = True
        st.session_state['am_user'] = username
        st.experimental_rerun()

st.markdown(f"Signed in as: **{st.session_state.get('am_user')}**")

# Load global config
GLOBAL_CFG = ROOT / 'messaging_config.json'
if GLOBAL_CFG.exists():
    try:
        cfg = json.loads(GLOBAL_CFG.read_text(encoding='utf-8') or '{}')
    except Exception:
        cfg = {}
else:
    cfg = {}

provider = st.selectbox('Provider', options=['mobitech', 'africastalking', 'infobip'], index=0 if cfg.get('provider','mobitech')=='mobitech' else (1 if cfg.get('provider')=='africastalking' else 2))
api_url = st.text_input('API URL', value=cfg.get('api_url',''))
username = st.text_input('Username', value=cfg.get('username',''))
api_key = st.text_input('API key / Password', value=cfg.get('api_key', cfg.get('password','')), type='password')
sender = st.text_input('Sender ID', value=cfg.get('sender',''))
http_method = st.selectbox('HTTP method', ['POST','GET'], index=0 if cfg.get('http_method','POST').upper()=='POST' else 1)
content_type = st.selectbox('Content type', ['application/json', 'application/x-www-form-urlencoded'], index=0 if cfg.get('content_type','application/json')=='application/json' else 1)

if st.button('Save and apply to all accounts'):
    newcfg = {
        'provider': provider,
        'api_url': api_url,
        'username': username,
        'api_key': api_key,
        'password': api_key,
        'sender': sender,
        'http_method': http_method,
        'content_type': content_type,
        'extra_params': {}
    }
    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        GLOBAL_CFG.write_text(json.dumps(newcfg, indent=2), encoding='utf-8')
    except Exception as e:
        st.error(f'Failed to write global config: {e}')
    else:
        applied = 0
        failed = []
        # only apply to directories that look like accounts
        ACCOUNT_MARKERS = {'exams_metadata.json', 'student_contacts.json', 'messaging_config.json', 'app_persistent_config.json'}
        SKIP_DIRS = {'student_photos', 'watermarks', 'exports', 'attachments', 'static'}
        for child in sorted(ROOT.iterdir()):
            if not child.is_dir():
                continue
            if child.name.startswith('saved_exams_storage_backup') or child.name in SKIP_DIRS:
                continue
            try:
                files = {f.name for f in child.iterdir() if f.is_file()}
                if not ACCOUNT_MARKERS.intersection(files):
                    continue
            except Exception:
                continue
            cfg_file = child / 'messaging_config.json'
            try:
                if cfg_file.exists():
                    bak = child / 'messaging_config.json.bak'
                    try:
                        shutil.copyfile(str(cfg_file), str(bak))
                    except Exception:
                        pass
                cfg_file.write_text(json.dumps(newcfg, indent=2), encoding='utf-8')
                applied += 1
            except Exception as e:
                failed.append((child.name, str(e)))
        st.success(f'Applied config to {applied} account folders.')
        if failed:
            st.error(f'Failed for {len(failed)} accounts. See logs.')
        else:
            st.info('All account messaging_config.json files were updated (backups created where applicable).')

st.markdown('---')
st.write('Administration notes:')
st.write('- Run this console with `streamlit run admin_messaging_console.py`.')
st.write('- Only administrators listed in `saved_exams_storage/admins.json` can sign in.')
