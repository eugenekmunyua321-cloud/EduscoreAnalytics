# --- Place all imports and ROOT definition at the very top ---
import streamlit as st
import json
import os
from pathlib import Path
import pandas as pd
import time as _t
import datetime as _dt
from modules.auth import safe_email_to_schoolid

ROOT = Path(__file__).parent / 'saved_exams_storage'
ROOT.mkdir(parents=True, exist_ok=True)

# Load users and account directories early so helper sections can reference them
users_file = ROOT / 'users.json'
try:
    users = json.loads(users_file.read_text(encoding='utf-8') or '{}') if users_file.exists() else {}
except Exception:
    users = {}
acct_dirs = [d for d in os.listdir(ROOT) if os.path.isdir(os.path.join(ROOT, d)) and d.endswith('_at_local')]

# ...existing code...

# After acct_dirs, users, etc. are defined, call the summary sheet
def render_accounts_summary_sheet():
    st.header('Accounts Summary Sheet')
    summary_rows = []
    now = int(_t.time())
    for sid in sorted(acct_dirs):
        uname = sid.replace('_at_local', '')
        display = users.get(uname, {}).get('display_name') if users else uname
        acct_dir = ROOT / sid
        # Exams count
        exams_path = acct_dir / 'exams_metadata.json'
        try:
            exams = json.loads(exams_path.read_text(encoding='utf-8') or '{}') if exams_path.exists() else {}
        except Exception:
            exams = {}
        num_exams = len(exams)
        # Count unique students across all exams for this account (do not double-count the same student)
        unique_student_ids = set()
        try:
            for exam_id in (exams.keys() if isinstance(exams, dict) else []):
                exam_dir = acct_dir / str(exam_id)
                if not exam_dir.exists():
                    # some metadata entries may be stored at root; try nested keys
                    continue
                # prefer raw_data.pkl then data.pkl
                df = None
                for fname in ('raw_data.pkl', 'data.pkl'):
                    p = exam_dir / fname
                    if p.exists():
                        try:
                            df = pd.read_pickle(str(p))
                        except Exception:
                            df = None
                        break
                if df is None:
                    continue
                # Ensure DataFrame
                if not isinstance(df, pd.DataFrame):
                    try:
                        df = pd.DataFrame(df)
                    except Exception:
                        continue
                # Identify admission number column or name column using common variants
                adm_col = None
                name_col = None
                for c in df.columns:
                    cl = str(c).lower().strip()
                    if cl in ['admno','adm no','adm_no','admission number','admission no','admin no','admin number','admno.','adm.no','adm','admission','admin']:
                        adm_col = c
                        break
                if adm_col is None:
                    for c in df.columns:
                        cl = str(c).lower().strip()
                        if cl in ['name','names','student name','student names']:
                            name_col = c
                            break
                ids = []
                try:
                    if adm_col is not None:
                        ids = df[adm_col].dropna().astype(str).str.strip().str.lower().tolist()
                    elif name_col is not None:
                        ids = df[name_col].dropna().astype(str).str.strip().str.lower().tolist()
                    else:
                        # fallback to index values
                        ids = df.index.astype(str).dropna().str.strip().str.lower().tolist()
                except Exception:
                    ids = []
                for v in ids:
                    if v:
                        unique_student_ids.add(v)
        except Exception:
            unique_student_ids = set()
        unique_students_count = len(unique_student_ids)
        # Subscription info
        acct = get_account_billing(str(acct_dir)) or {}
        expiry_ts = int(acct.get('expiry_ts') or 0)
        is_active = expiry_ts > now
        countdown = str(_dt.timedelta(seconds=max(0, expiry_ts-now))) if is_active else 'Expired'
        # Disabled status
        admf = acct_dir / 'admin_meta.json'
        am = {}
        try:
            if admf.exists():
                am = json.loads(admf.read_text(encoding='utf-8') or '{}')
        except Exception:
            am = {}
        disabled = bool(am.get('disabled', False))
        # Messages bought and money spent (from purchases.json)
        purchases_path = acct_dir / 'purchases.json'
        try:
            purchases = json.loads(purchases_path.read_text(encoding='utf-8') or '[]') if purchases_path.exists() else []
        except Exception:
            purchases = []
        messages_bought = sum(int(p.get('quantity',0)) for p in purchases)
        money_spent_messages = 0.0  # If amount per purchase is available, sum it
        for p in purchases:
            amt = p.get('amount')
            if amt is not None:
                try:
                    money_spent_messages += float(amt)
                except Exception:
                    pass
        # Subscription spend (sum of last_payment_amount over time, fallback to 0)
        total_sub_spend = 0.0
        if purchases:
            for p in purchases:
                amt = p.get('amount')
                if amt is not None:
                    try:
                        total_sub_spend += float(amt)
                    except Exception:
                        pass
        # If no amount in purchases, fallback to last_payment_amount
        if not total_sub_spend:
            total_sub_spend = float(acct.get('last_payment_amount') or 0.0)
        summary_rows.append({
            'Account': display,
            'Username': uname,
            'Exams Uploaded': num_exams,
            'Unique Students Uploaded': unique_students_count,
            'Active': 'Yes' if is_active else 'No',
            'Disabled': 'Yes' if disabled else 'No',
            'Subscription Countdown': countdown,
            'Messages Bought': messages_bought,
            'Money Spent on Messages': money_spent_messages,
            'Total Subscription Spend': total_sub_spend
        })
    if summary_rows:
        df = pd.DataFrame(summary_rows)
        # Style: big font, colored badges for Active/Disabled
        def highlight_status(val):
            if val == 'Yes':
                return 'background-color: #22c55e; color: white; font-weight: bold; font-size: 1.1em;'
            elif val == 'No':
                return 'background-color: #ef4444; color: white; font-weight: bold; font-size: 1.1em;'
            return ''
        st.markdown('<style>div[data-testid="stDataFrame"] td {font-size: 1.2em;}</style>', unsafe_allow_html=True)
        st.dataframe(
            df.style.applymap(highlight_status, subset=['Active','Disabled'])
        )
    else:
        st.info('No accounts found to summarize.')
# --- Notification for pending confirmations ---
notif_path = ROOT / 'admin_notifications.json'
try:
    notifs = json.loads(notif_path.read_text(encoding='utf-8') or '[]') if notif_path.exists() else []
except Exception:
    notifs = []
pending = [n for n in notifs if n.get('status') == 'pending']
if pending:
    st.warning(f'🔔 {len(pending)} new payment/message confirmation(s) pending review!')
    # Show a table of all pending confirmations with account info
    pending_rows = []
    for n in pending:
        uname = n.get('username', '')
        payer = n.get('payer_phone', '')
        amt = n.get('amount', '')
        txn = n.get('txn', '')
        msg = n.get('message', '')
        # Always show the username provided in the payment form
        display_name = users.get(uname, {}).get('display_name', '') if uname else ''
        if display_name and display_name != uname:
            account_label = f"{display_name} ({uname})"
        elif uname:
            account_label = uname
        else:
            account_label = '(not provided)'
        pending_rows.append({
            'Account': account_label,
            'Username': uname,
            'Payer Phone': payer,
            'Amount': amt,
            'Transaction ID': txn,
            'Message': msg[:120] + ('...' if len(msg) > 120 else '')
        })
    if pending_rows:
        st.dataframe(pending_rows, use_container_width=True)

# New-account notifications (admins should be aware when new accounts register)
new_accounts = [n for n in notifs if n.get('type') == 'new_account' and n.get('status') == 'pending']
if new_accounts:
    st.warning(f'🔔 {len(new_accounts)} new account registration(s) waiting for admin review')
    na_rows = []
    for n in new_accounts:
        uname = n.get('username')
        accno = n.get('account_number')
        created = n.get('created_at')
        try:
            created_str = _dt.datetime.fromtimestamp(int(created)).strftime('%Y-%m-%d %H:%M') if created else ''
        except Exception:
            created_str = str(created)
        na_rows.append({'Account Number': accno, 'Username': uname, 'Created': created_str})
    st.dataframe(na_rows, use_container_width=True)
    # allow quick mark-as-reviewed
    for i, n in enumerate(new_accounts):
        if st.button(f'Mark new account {n.get("username")} as reviewed', key=f'review_new_{i}'):
            try:
                for x in notifs:
                    if x.get('type') == 'new_account' and x.get('username') == n.get('username') and x.get('status') == 'pending':
                        x['status'] = 'reviewed'
                        x['reviewed_by'] = 'admin'
                        x['reviewed_at'] = int(__import__('time').time())
                notif_path.write_text(json.dumps(notifs, indent=2, ensure_ascii=False), encoding='utf-8')
                st.success('Marked reviewed')
            except Exception as e:
                st.error('Failed to mark reviewed: ' + str(e))

# ...existing code...


# ...existing code...

# Per-account management: list all accounts, adjust days, enable/disable, view billing
users_file = ROOT / 'users.json'
try:
    users = json.loads(users_file.read_text(encoding='utf-8') or '{}') if users_file.exists() else {}
except Exception:
    users = {}
acct_dirs = [d for d in os.listdir(ROOT) if os.path.isdir(os.path.join(ROOT, d)) and d.endswith('_at_local')]


# Now call the summary sheet after acct_dirs and users are defined, and after billing imports
# ...existing code...

# Import billing functions before calling summary
from modules.billing import get_global_billing_config, set_global_billing_config, get_account_billing, set_account_billing

render_accounts_summary_sheet()
import streamlit as st
import json
import os
from pathlib import Path
from modules.auth import safe_email_to_schoolid

ROOT = Path(__file__).parent / 'saved_exams_storage'
ROOT.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title='Admin Features — EduScore', layout='wide')

st.title('Admin Features — EduScore (Standalone)')
st.markdown('This standalone admin page contains billing and subscription controls. Protect access with your admin password below.')

# Simple admin gate: allow unlock if either the session has a valid admin password
# or the user provides the super_admin_password in the page input. This lets
# the main app (which sets st.session_state['admin_password']) open this page
# without an extra prompt.
admf = ROOT / 'admin_meta.json'
# Grant admin features access without requiring super-admin password
# (per request: remove the super password gate)
super_ok = True
try:
    cfg = json.loads(admf.read_text(encoding='utf-8') or '{}') if admf.exists() else {}
except Exception:
    cfg = {}

# First check session_state for pre-existing admin password
ss_pwd = st.session_state.get('admin_password')
try:
    stored = str(cfg.get('super_admin_password') or '').strip()
except Exception:
    stored = ''
if ss_pwd and stored and str(ss_pwd).strip() == stored:
    super_ok = True

# Allow immediate access for the special admin account
if not super_ok:
    if st.session_state.get('user_email', '').strip().lower() == 'admin@local':
        super_ok = True

# If not present in session, prompt for password as standalone page
if not super_ok:
    # allow existing input to persist across reruns
    pwd_default = st.session_state.get('af_pwd', '')
    pwd = st.text_input('Super admin password', type='password', key='af_pwd', value=pwd_default)
    if pwd:
        try:
            # compare stripped values to avoid accidental whitespace mismatches
            if stored and str(pwd).strip() == stored:
                super_ok = True
                # populate session for convenience
                st.session_state['admin_password'] = pwd.strip()
            else:
                st.warning('Password did not match. Please check for typos or extra spaces.')
        except Exception:
            super_ok = False

if not super_ok:
    st.warning('Enter the super admin password to unlock admin features.')
    st.stop()

st.success('Admin unlocked')

from modules.billing import get_global_billing_config, set_global_billing_config, get_account_billing, set_account_billing

# Global billing defaults
st.header('Global billing defaults')
cfg = get_global_billing_config() or {}
col1, col2 = st.columns(2)
with col1:
    period = st.number_input('Subscription period (days)', min_value=1, value=int(cfg.get('period_days', 30)))
with col2:
    price = st.number_input('Default price (KSH)', min_value=0.0, value=float(cfg.get('price_ksh', 500)))

receiver = st.text_input('Receiver phone (MPESA)', value=str(cfg.get('receiver_phone', '0793975959')))

if st.button('Save global defaults'):
    new = {'period_days': int(period), 'price_ksh': float(price), 'receiver_phone': str(receiver)}
    if set_global_billing_config(new):
        st.success('Saved global billing defaults')
    else:
        st.error('Failed to save')

st.markdown('---')

st.markdown('---')

# Messaging credentials (global)
st.header('Messaging credentials (global)')
msg_cfg_path = ROOT / 'messaging_config.json'
try:
    mg = json.loads(msg_cfg_path.read_text(encoding='utf-8') or '{}') if msg_cfg_path.exists() else {}
except Exception:
    mg = {}

col1, col2 = st.columns(2)
with col1:
    provider = st.text_input('Provider', value=str(mg.get('provider','')))
    api_url = st.text_input('API URL', value=str(mg.get('api_url','')))
    username = st.text_input('Username', value=str(mg.get('username','')))
with col2:
    api_key = st.text_input('API key', value=str(mg.get('api_key','')))
    sender = st.text_input('Sender ID', value=str(mg.get('sender','')))
    http_method = st.selectbox('HTTP method', options=['GET','POST'], index=0 if mg.get('http_method','POST')=='POST' else 1)

if st.button('Save messaging config'):
    try:
        newmg = {'provider': provider, 'api_url': api_url, 'username': username, 'api_key': api_key, 'sender': sender, 'http_method': http_method}
        msg_cfg_path.write_text(json.dumps(newmg, indent=2, ensure_ascii=False), encoding='utf-8')
        st.success('Saved messaging config')
    except Exception as e:
        st.error('Failed to save messaging config: ' + str(e))

st.markdown('---')


# --- New per-account management UI ---
st.header('Manage accounts')
users_file = ROOT / 'users.json'
try:
    users = json.loads(users_file.read_text(encoding='utf-8') or '{}') if users_file.exists() else {}
except Exception:
    users = {}
acct_dirs = [d for d in os.listdir(ROOT) if os.path.isdir(os.path.join(ROOT, d)) and d.endswith('_at_local')]
account_options = []
for sid in sorted(acct_dirs):
    uname = sid.replace('_at_local', '')
    display = users.get(uname, {}).get('display_name') if users else None
    display = display or uname
    account_options.append((f"{display} ({uname})", sid))

if not account_options:
    st.write('No accounts found in storage.')
else:
    selected_label = st.selectbox('Select account', [x[0] for x in account_options])
    selected_sid = dict(account_options)[selected_label]
    acct_dir = ROOT / selected_sid
    uname = selected_sid.replace('_at_local', '')
    display = users.get(uname, {}).get('display_name') if users else uname
    st.markdown('---')
    st.subheader(f'Account: {display} ({uname})')

    # --- Subscription Info Table ---
    acct = get_account_billing(str(acct_dir)) or {}
    expiry_ts = int(acct.get('expiry_ts') or 0)
    import datetime as _dt
    expiry_str = _dt.datetime.fromtimestamp(expiry_ts).strftime('%Y-%m-%d %H:%M') if expiry_ts and expiry_ts > 0 else 'None/Expired'
    # compute remaining seconds and a human readable countdown (zero when expired)
    now_ts = int(_t.time())
    remaining_secs = max(0, expiry_ts - now_ts) if expiry_ts else 0
    try:
        # format as 'Nd HH:MM:SS' only when >= 1 day, otherwise 'HH:MM:SS'
        if remaining_secs > 0:
            if remaining_secs >= 86400:
                days = remaining_secs // 86400
                rem = remaining_secs % 86400
                hours = rem // 3600
                rem2 = rem % 3600
                minutes = rem2 // 60
                seconds = rem2 % 60
                remaining_str = f"{days}d {hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                hours = remaining_secs // 3600
                rem = remaining_secs % 3600
                minutes = rem // 60
                seconds = rem % 60
                remaining_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            remaining_str = '0'
    except Exception:
        remaining_str = str(remaining_secs)

    st.markdown('**Subscription Info**')
    sub_cols = st.columns(3)
    sub_cols[0].metric('Expiry', expiry_str)
    sub_cols[1].metric('Last payment', acct.get('last_payment_amount'))
    # show a live-like remaining countdown (updated on rerun)
    sub_cols[2].metric('Remaining', remaining_str)

    col1, col2 = st.columns(2)
    with col1:
        add_days = st.number_input('Days to add', min_value=0, value=0, key=f'days_add_{selected_sid}')
        add_hours = st.number_input('Hours to add', min_value=0, max_value=23, value=0, key=f'hours_add_{selected_sid}')
        add_minutes = st.number_input('Minutes to add', min_value=0, max_value=59, value=0, key=f'mins_add_{selected_sid}')
        if st.button('Apply time', key=f'apply_time_{selected_sid}'):
            try:
                now = int(__import__('time').time())
                cur = int(acct.get('expiry_ts') or 0)
                base = cur if cur and cur > now else now
                total_add = int(add_days) * 86400 + int(add_hours) * 3600 + int(add_minutes) * 60
                acct['expiry_ts'] = int(base + total_add)
                acct['period_days'] = int(add_days) if add_days > 0 else acct.get('period_days')
                acct['period_hours'] = int(add_hours)
                acct['period_minutes'] = int(add_minutes)
                set_account_billing(acct, str(acct_dir))
                st.success(f'Added {add_days} day(s), {add_hours} hour(s), {add_minutes} minute(s)')
            except Exception as e:
                st.error('Failed to apply time: ' + str(e))
    with col2:
        # enable/disable account via per-account admin_meta.json
        admf = acct_dir / 'admin_meta.json'
        am = {}
        try:
            if admf.exists():
                am = json.loads(admf.read_text(encoding='utf-8') or '{}')
        except Exception:
            am = {}
        disabled = bool(am.get('disabled', False))
        # Profile fields
        phone_val = am.get('phone', '')
        school_name_val = am.get('school_name', '')
        email_val = am.get('email', '')
        location_val = am.get('location', '')
        country_val = am.get('country', '')

        st.markdown('**Profile information (read-only)**')
        try:
            cols = st.columns([1, 1])
            with cols[0]:
                st.markdown(f"**Account number:** {am.get('account_number', '(not set)')}")
                st.markdown(f"**School name:** {am.get('school_name', '')}")
                st.markdown(f"**Contact email:** {am.get('email', '')}")
            with cols[1]:
                st.markdown(f"**Phone:** {am.get('phone', '')}")
                st.markdown(f"**Location:** {am.get('location', '')}")
                st.markdown(f"**Country:** {am.get('country', '')}")
        except Exception:
            st.write('Profile information not available')

        new_disabled = st.checkbox('Disabled', value=disabled, key=f'disabled_{selected_sid}')
        # Buttons: Save disabled state, Enable account, Delete account
        if st.button('Save disabled state', key=f'save_disabled_{selected_sid}'):
            try:
                # Only update the disabled flag so we don't overwrite profile fields.
                try:
                    from modules import storage as _storage
                    sid = acct_dir.name
                    ok, err = _storage.write_admin_meta(sid, {'disabled': bool(new_disabled)}, backup=True, force_replace=False)
                    if not ok:
                        raise Exception(err or 'Failed to write admin_meta')
                except Exception:
                    # fallback: write merged am atomically
                    try:
                        am['disabled'] = bool(new_disabled)
                        tmp = admf.with_suffix('.tmp')
                        tmp.write_text(json.dumps(am, indent=2, ensure_ascii=False), encoding='utf-8')
                        tmp.replace(admf)
                    except Exception:
                        try:
                            admf.write_text(json.dumps(am, indent=2, ensure_ascii=False), encoding='utf-8')
                        except Exception:
                            pass
                st.success('Saved disabled state')
            except Exception as e:
                st.error('Failed to save disabled state: ' + str(e))

        if st.button('Enable account', key=f'enable_{selected_sid}'):
            try:
                try:
                    from modules import storage as _storage
                    sid = acct_dir.name
                    ok, err = _storage.write_admin_meta(sid, {'disabled': False}, backup=True, force_replace=False)
                    if not ok:
                        raise Exception(err or 'Failed to write admin_meta')
                except Exception:
                    try:
                        am['disabled'] = False
                        tmp = admf.with_suffix('.tmp')
                        tmp.write_text(json.dumps(am, indent=2, ensure_ascii=False), encoding='utf-8')
                        tmp.replace(admf)
                    except Exception:
                        try:
                            admf.write_text(json.dumps(am, indent=2, ensure_ascii=False), encoding='utf-8')
                        except Exception:
                            pass
                st.success('Account enabled')
            except Exception as e:
                st.error('Failed to enable account: ' + str(e))

        # Deletion flow: require typing the username to confirm
        if st.button('Delete account (show confirmation)', key=f'del_show_{selected_sid}'):
            st.session_state[f'delete_confirm_{selected_sid}'] = True
        if st.session_state.get(f'delete_confirm_{selected_sid}'):
            confirm_text = st.text_input('Type the username to confirm deletion', key=f'del_confirm_input_{selected_sid}')
            if st.button('Confirm delete', key=f'confirm_del_{selected_sid}'):
                try:
                    if str(confirm_text).strip() == uname:
                        import shutil
                        # remove the account folder entirely
                        shutil.rmtree(str(acct_dir))
                        # attempt to remove from users.json
                        try:
                            udata = users if isinstance(users, dict) else {}
                            if uname in udata:
                                del udata[uname]
                                users_file.write_text(json.dumps(udata, indent=2, ensure_ascii=False), encoding='utf-8')
                        except Exception:
                            pass
                        st.success(f'Account {uname} deleted. Refresh the page.')
                    else:
                        st.error('Confirmation text did not match username. Deletion aborted.')
                except Exception as e:
                    st.error('Failed to delete account: ' + str(e))

        # Reset password flow: require typing username to confirm reset to default
        if st.button('Reset password to default (show confirmation)', key=f'reset_show_{selected_sid}'):
            st.session_state[f'reset_confirm_{selected_sid}'] = True
        if st.session_state.get(f'reset_confirm_{selected_sid}'):
            confirm_text = st.text_input('Type the username to confirm password reset', key=f'reset_confirm_input_{selected_sid}')
            if st.button('Confirm reset to default (eduscore003)', key=f'confirm_reset_{selected_sid}'):
                try:
                    if str(confirm_text).strip() == uname:
                        try:
                            import modules.auth as auth
                            ok, msg = auth.admin_reset_password(uname, 'eduscore003')
                            if ok:
                                st.success('Password reset to default "eduscore003". Advise the user to sign in and change it immediately.')
                                # clear the confirmation flag so it doesn't persist
                                try:
                                    del st.session_state[f'reset_confirm_{selected_sid}']
                                except Exception:
                                    pass
                            else:
                                st.error('Failed to reset password: ' + (msg or 'unknown error'))
                        except Exception as e:
                            st.error('Reset failed: ' + str(e))
                    else:
                        st.error('Confirmation text did not match username. Password reset aborted.')
                except Exception as e:
                    st.error('Failed to perform reset: ' + str(e))

    st.markdown('---')


st.markdown('---')


# Revenue summary (monthly/yearly breakdown)
st.header('Revenue summary (aggregated)')
import datetime
now_ts = int(__import__('time').time())
now_dt = datetime.datetime.fromtimestamp(now_ts)
this_month = now_dt.month
this_year = now_dt.year
subs_month = 0.0
subs_year = 0.0
subs_total = 0.0
msgs_month = 0.0
msgs_year = 0.0
msgs_total = 0.0
for name in os.listdir(ROOT):
    p = os.path.join(ROOT, name)
    if not os.path.isdir(p):
        continue
    purch = os.path.join(p, 'purchases.json')
    if not os.path.exists(purch):
        continue
    try:
        with open(purch, 'r', encoding='utf-8') as fh:
            items = json.load(fh)
        for it in items:
            amt = float(it.get('amount', 0.0) or 0.0)
            t = it.get('time')
            # If time is float, convert to int
            try:
                t = int(float(t))
            except Exception:
                t = None
            dt = datetime.datetime.fromtimestamp(t) if t else None
            # Heuristic: if 'quantity' in item, treat as message purchase, else subscription
            if 'quantity' in it:
                msgs_total += amt
                if dt and dt.year == this_year:
                    msgs_year += amt
                    if dt.month == this_month:
                        msgs_month += amt
            else:
                subs_total += amt
                if dt and dt.year == this_year:
                    subs_year += amt
                    if dt.month == this_month:
                        subs_month += amt
    except Exception:
        continue
st.write(f"**Subscriptions:** This month: KSH {subs_month:.2f} | This year: KSH {subs_year:.2f} | Total: KSH {subs_total:.2f}")
st.write(f"**Messages:** This month: KSH {msgs_month:.2f} | This year: KSH {msgs_year:.2f} | Total: KSH {msgs_total:.2f}")

st.markdown('---')

# Pending confirmations
st.header('Pending payment confirmations')
notif_path = ROOT / 'admin_notifications.json'
try:
    notifs = json.loads(notif_path.read_text(encoding='utf-8') or '[]') if notif_path.exists() else []
except Exception:
    notifs = []

pending = [n for n in notifs if n.get('status') == 'pending']
if not pending:
    st.write('No pending confirmations')
else:
    for i, n in enumerate(pending):
        st.markdown('---')
        st.write('Username:', n.get('username'))
        st.write('Payer phone:', n.get('payer_phone'))
        st.write('Txn:', n.get('txn'))
        st.code(n.get('message') or '')
        days = st.number_input(f'Days to credit #{i}', min_value=0, value=30, key=f'af_days_{i}')
        if st.button(f'Confirm #{i}'):
            try:
                # apply to account
                from modules.billing import record_payment_confirmation
                sid = safe_email_to_schoolid(f"{n.get('username')}@local")
                acct_dir = ROOT / sid
                acct_dir.mkdir(parents=True, exist_ok=True)
                ok, msg = record_payment_confirmation(n.get('txn'), n.get('payer_phone'), float(n.get('amount') or 0.0), storage_dir=str(acct_dir))
                # additionally adjust by days if provided
                if ok and days:
                    acct = get_account_billing(str(acct_dir)) or {}
                    now = int(__import__('time').time())
                    cur = int(acct.get('expiry_ts') or 0)
                    base = cur if cur and cur > now else now
                    acct['expiry_ts'] = int(base + int(days) * 86400)
                    acct['period_days'] = int(days)
                    set_account_billing(acct, str(acct_dir))

                # mark notif
                for x in notifs:
                    if x.get('txn') == n.get('txn') and x.get('username') == n.get('username') and x.get('status') == 'pending':
                        x['status'] = 'confirmed'
                        x['confirmed_by'] = 'admin'
                        x['confirmed_at'] = int(__import__('time').time())
                        x['days_added'] = int(days)
                notif_path.write_text(json.dumps(notifs, indent=2, ensure_ascii=False), encoding='utf-8')
                st.success('Confirmed and applied')
            except Exception as e:
                st.error('Failed to confirm: ' + str(e))
        if st.button(f'Reject #{i}'):
            for x in notifs:
                if x.get('txn') == n.get('txn') and x.get('username') == n.get('username') and x.get('status') == 'pending':
                    x['status'] = 'rejected'
                    x['rejected_by'] = 'admin'
                    x['rejected_at'] = int(__import__('time').time())
            notif_path.write_text(json.dumps(notifs, indent=2, ensure_ascii=False), encoding='utf-8')
            st.info('Rejected')

st.markdown('---')
st.info('This standalone file can be uploaded and run separately with `streamlit run admin_features.py`.')
