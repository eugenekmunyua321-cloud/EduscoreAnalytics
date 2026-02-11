import streamlit as st
from modules import auth


def render_auth_page():
    """Full-screen, modern auth page for local username/password sign-in & register.
    Uses the existing local account store in `modules.auth` (saved to `saved_exams_storage/users.json`).
    """
    try:
        st.set_page_config(page_title='Sign in — EduScore', layout='wide', initial_sidebar_state='collapsed')
    except Exception:
        pass

    # Hide Streamlit sidebar/menu for this page
    hide_css = """
    <style>
    [data-testid="stSidebar"] { display: none !important; }
    .css-1bdtf2p { display: none !important; }
    footer { visibility: hidden; }
    </style>
    """
    st.markdown(hide_css, unsafe_allow_html=True)

    # Branding: modern full-width top banner and centered auth card
    grad_a = getattr(auth, 'BRAND_GRAD_A', '#06b6d4')
    grad_b = getattr(auth, 'BRAND_GRAD_B', '#7c3aed')

    # Top banner (full-width) with stylized company name and short tagline
    # Import nicer web fonts (Montserrat for the brand, Poppins for supporting text)
    st.markdown("<link href='https://fonts.googleapis.com/css2?family=Montserrat:wght@700;900&family=Poppins:wght@400;600;700&display=swap' rel='stylesheet'>", unsafe_allow_html=True)

    # If a project logo exists at ./static/eduscore_logo.(png|jpg), embed it into the banner
    try:
        from pathlib import Path
        import base64
        # look in repo-root ./static where the logo was copied
        logo_dir = Path(__file__).parent / 'static'
        logo_path_jpg = logo_dir / 'eduscore_logo.jpg'
        logo_path_jpeg = logo_dir / 'eduscore_logo.jpeg'
        logo_path_png = logo_dir / 'eduscore_logo.png'
        logo_html = None
        logo_path = None
        for p in (logo_path_png, logo_path_jpg, logo_path_jpeg):
            if p.exists():
                logo_path = p
                break
        if logo_path is not None:
            try:
                data = base64.b64encode(logo_path.read_bytes()).decode('ascii')
                mime = 'image/png' if logo_path.suffix.lower().endswith('png') else 'image/jpeg'
                # restore original larger logo so the banner appears as before
                logo_html = f"<img src='data:{mime};base64,{data}' style='width:140px;height:140px;object-fit:contain;border-radius:12px;box-shadow:0 10px 34px rgba(2,6,23,0.22);'/>"
            except Exception:
                logo_html = None
    except Exception:
        logo_html = None

    # render banner; if logo_html present use it, otherwise fall back to the letter tile
    tile_html = """
        <div style="width:140px; height:140px; border-radius:16px; background: linear-gradient(135deg, rgba(255,255,255,0.12), rgba(255,255,255,0.06)); display:flex; align-items:center; justify-content:center; font-weight:900; font-size:56px; color:#fff; box-shadow: 0 10px 34px rgba(2,6,23,0.22);">E</div>
    """

    logo_fragment = logo_html if logo_html else tile_html

    # Use components.html to render the banner HTML exactly (avoids markdown escaping issues)
    try:
        import streamlit.components.v1 as components

        # Use the same centered, max-width logo banner as the Home page for visual consistency
        banner_html = f'''
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
                        <div style="opacity:0.9; margin-top:6px; font-size:12px;">Beautiful analytics, locally hosted — crafted for schools and educators.</div>
                        <div style="margin-top:8px;font-size:28px;font-weight:900;">Welcome</div>
                    </div>
                </div>
                <div style="text-align:right; min-width:120px;">
                    <div style="background: rgba(255,255,255,0.06); padding:8px 12px; border-radius:999px; display:inline-block; font-weight:700; font-size:12px;">Sign in</div>
                </div>
            </div>
          </div>
        </div>
        '''
        components.html(banner_html, height=220, scrolling=False)
    except Exception:
        # fallback to markdown rendering if components unavailable
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
                        <div style="opacity:0.9; margin-top:6px; font-size:12px;">Beautiful analytics, locally hosted — crafted for schools and educators.</div>
                        <div style="margin-top:8px;font-size:28px;font-weight:900;">Welcome</div>
                    </div>
                </div>
                <div style="text-align:right; min-width:120px;">
                    <div style="background: rgba(255,255,255,0.06); padding:8px 12px; border-radius:999px; display:inline-block; font-weight:700; font-size:12px;">Sign in</div>
                </div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # Centered auth card (styled with a soft gradient and subtle accent so it's not just white)
    col_l, col_m, col_r = st.columns([1, 0.9, 1])
    with col_m:
        st.markdown("""
        <style>
            .auth-card-custom {
                padding:28px;
                border-radius:14px;
                background: linear-gradient(135deg, rgba(255,255,255,0.94) 0%, rgba(235,245,255,0.9) 100%);
                box-shadow: 0 20px 60px rgba(2,20,60,0.10);
                border: 1px solid rgba(99,102,241,0.06);
                backdrop-filter: blur(6px);
            }
            .auth-card-title { font-family: 'Montserrat', 'Poppins', sans-serif; font-weight:800; color:#0f172a; }
            .auth-card-desc { font-family: 'Poppins', sans-serif; color:#475569; }
        </style>
        <div class='auth-card-custom'>
        """, unsafe_allow_html=True)
        # Keep a single clear sign-in heading + paragraph (the plain fallback below)
        st.markdown("<h2 style='margin-top:6px; margin-bottom:6px; color:#0f172a;'>Sign in to your account</h2>", unsafe_allow_html=True)
        st.markdown("<p style='color:#475569; margin-top:0;margin-bottom:12px;'>Sign in with your username and password (local accounts). Each account stores its exams in its own folder on the server.</p>", unsafe_allow_html=True)

        tab = st.radio('', ['Sign in', 'Register'], horizontal=True)

        if tab == 'Sign in':
            uname = st.text_input('Username', key='auth_uname', placeholder='yourschool')
            pwd = st.text_input('Password', type='password', key='auth_pwd')
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button('Sign in', key='auth_signin'):
                    ok, info = auth.authenticate_local_user(uname, pwd)
                    if ok:
                        email_like = f"{uname}@local"
                        # Prefer internal helper to keep consistent session clearing
                        try:
                            auth._handle_post_signin(email_like, prefer_empty=False, display_name=info)
                        except Exception:
                            # Ensure essential auth keys are present even if helper fails
                            st.session_state['user_email'] = email_like
                            st.session_state['user_uid'] = auth.safe_email_to_schoolid(email_like)
                            st.session_state['school_display_name'] = info
                        # Always set navigation to Home and request delegation to Home
                        try:
                            st.session_state['current_page'] = 'home'
                        except Exception:
                            pass
                        try:
                            st.session_state['show_home_header'] = True
                        except Exception:
                            pass
                        # do not set legacy 'force_delegate_home' flag here

                        # Ensure the app delegates to Home on next rerun.
                        try:
                            auth._safe_rerun()
                        except Exception:
                            try:
                                st.experimental_rerun()
                            except Exception:
                                pass
                    else:
                        st.error(info)
            # DEBUG PANEL: Show debug_auth_check and debug_auth_error if present
            with st.expander('DEBUG: Auth Check', expanded=False):
                dbg = st.session_state.get('debug_auth_check')
                if dbg:
                    st.write('debug_auth_check:', dbg)
                dbgerr = st.session_state.get('debug_auth_error')
                if dbgerr:
                    st.write('debug_auth_error:', dbgerr)

            with col2:
                # Guest access disabled when billing is enforced
                st.info('Guest access disabled. Please sign in with your account or register.')

        else:
            st.markdown('<div style="margin-bottom:6px; color:#0f172a; font-weight:600;">Create a new local account</div>', unsafe_allow_html=True)
            runame = st.text_input('Choose a username', key='reg_uname')
            rpass = st.text_input('Choose a password', type='password', key='reg_pass')
            rpass2 = st.text_input('Confirm password', type='password', key='reg_pass2')
            if st.button('Register'):
                if not runame or not rpass:
                    st.error('Please provide both username and password.')
                elif rpass != rpass2:
                    st.error('Passwords do not match.')
                else:
                    ok, msg = auth.create_local_user(runame, rpass, display_name=runame)
                    if ok:
                        email_like = f"{runame}@local"
                        try:
                            auth._handle_post_signin(email_like, prefer_empty=True, display_name=runame)
                        except Exception:
                            st.session_state['user_email'] = email_like
                            st.session_state['user_uid'] = auth.safe_email_to_schoolid(email_like)
                            st.session_state['school_display_name'] = runame
                        # Always navigate to Home after registration
                        try:
                            st.session_state['current_page'] = 'home'
                        except Exception:
                            pass
                        try:
                            st.session_state['show_home_header'] = True
                        except Exception:
                            pass
                        # do not set legacy 'force_delegate_home' flag here

                        try:
                            auth._safe_rerun()
                        except Exception:
                            try:
                                st.experimental_rerun()
                            except Exception:
                                pass
                    else:
                        st.error(msg)

        # --- Payment options on the sign-in page (MPESA two-step confirm) ---
        try:
            st.markdown('---')
            st.markdown('### Request activation (paste MPESA SMS)')
            # Only collect the username to credit; all payment details must be supplied via pasted SMS
            pay_username = st.text_input('Username to credit (no @local)', value='', key='pay_username')
            # try to load billing defaults from modules.billing if available (for display/amount)
            try:
                import modules.billing as billing
            except Exception:
                billing = None
            global_cfg = billing.get_global_billing_config() if billing is not None else {'price_ksh': 500, 'period_days': 30, 'receiver_phone': '0793975959'}
            default_receiver = global_cfg.get('receiver_phone', '0793975959')
            st.markdown(f"Submit your MPESA SMS/receipt below. Payments should be sent to: **{default_receiver}**")
            # Paste MPESA SMS/receipt for admin verification (user flow)
            pay_msg = st.text_area('Paste full MPESA SMS/receipt here', value='', key='pay_msg', height=150)
            if st.button('Submit receipt for admin review', key='submit_receipt'):
                # Basic validation: receiver number and expected name must be present,
                # and the transaction id must not already exist in any account purchases.
                try:
                    import re, json, os
                    from pathlib import Path
                    root = Path(__file__).parent / 'saved_exams_storage'
                    # normalize receiver
                    def _normalize_phone(n):
                        s = ''.join([c for c in n if c.isdigit()])
                        if s.startswith('254'):
                            s = '0' + s[3:]
                        return s

                    recv_norm = _normalize_phone(default_receiver)
                    found_numbers = re.findall(r"\d{7,15}", pay_msg)

                    # Improved phone extraction: match all common Kenyan formats
                    phone_patterns = [
                        r"07\d{8}",
                        r"01\d{8}",
                        r"\+2547\d{8}",
                        r"2547\d{8}"
                    ]
                    phones = set()
                    for pat in phone_patterns:
                        phones.update(re.findall(pat, pay_msg))
                    # fallback: any 10-12 digit number
                    if not phones:
                        phones.update(re.findall(r"0\d{9,10}", pay_msg))
                    # normalize
                    phones = [_normalize_phone(x) for x in phones]
                    ok_recv = any(p.endswith(recv_norm[-9:]) or p == recv_norm for p in phones)

                    # name check (expects EUGENE KAMAU somewhere in message)
                    nm = pay_msg.upper()
                    ok_name = ('EUGENE' in nm and 'KAMAU' in nm)

                    # Extract MPESA reference number (txn) robustly
                    txn = ''
                    # 1. Try standard pattern
                    m = re.search(r"TRANSACTION(?: ID)?[:\s]*([A-Z0-9-]{8,15})", pay_msg, re.IGNORECASE)
                    if m:
                        txn = m.group(1)
                    # 2. Try to find any standalone uppercase alphanumeric word of length 8-12 (MPESA refs)
                    if not txn:
                        m2 = re.search(r"\b([A-Z0-9]{8,12})\b", pay_msg)
                        if m2:
                            txn = m2.group(1)
                    # 3. Try to find a pattern like 'Confirmed. Ksh... sent ... REF ...'
                    if not txn:
                        m3 = re.search(r"([A-Z0-9]{8,12}) Confirmed", pay_msg)
                        if m3:
                            txn = m3.group(1)

                    # determine payer phone (first phone that's not the receiver)
                    payer_candidates = [p for p in phones if not (p == recv_norm or p.endswith(recv_norm[-9:]))]
                    if payer_candidates:
                        payer_phone = payer_candidates[0]
                    elif phones:
                        # fallback: use receiver phone if that's the only one present
                        payer_phone = recv_norm
                    else:
                        payer_phone = ''

                    if not ok_recv:
                        st.error('Receipt does not appear to be sent to the expected receiver number.')
                    elif not ok_name:
                        st.error('Receipt does not contain the expected receiver name (EUGENE KAMAU).')
                    elif not txn:
                        st.error('Could not determine transaction ID from the message. Please ensure your SMS includes a transaction reference.')
                    elif not payer_phone:
                        st.error('Could not determine the payer phone number from the message.')
                    else:
                        # ensure txn uniqueness across all accounts (case-insensitive)
                        seen = False
                        txn_upper = txn.strip().upper()
                        for name in os.listdir(root):
                            p = os.path.join(root, name)
                            if not os.path.isdir(p):
                                continue
                            purch = os.path.join(p, 'purchases.json')
                            if not os.path.exists(purch):
                                continue
                            try:
                                with open(purch, 'r', encoding='utf-8') as fh:
                                    items = json.load(fh)
                                for it in items:
                                    it_txn = str(it.get('txn') or '').strip().upper()
                                    if it_txn and it_txn == txn_upper:
                                        seen = True
                                        break
                                if seen:
                                    break
                            except Exception:
                                continue

                        if seen:
                            st.error('This transaction ID has already been used for another payment.')
                        else:
                            # append admin notification
                            notif_file = root / 'admin_notifications.json'
                            try:
                                notifs = json.loads(notif_file.read_text(encoding='utf-8') or '[]') if notif_file.exists() else []
                            except Exception:
                                notifs = []
                            amount = float(global_cfg.get('price_ksh', 500))
                            rec = {
                                'time': int(__import__('time').time()),
                                'username': pay_username,
                                'payer_phone': payer_phone,
                                'txn': txn.strip(),
                                'amount': amount,
                                'message': pay_msg,
                                'status': 'pending'
                            }
                            notifs.append(rec)
                            try:
                                notif_file.write_text(json.dumps(notifs, indent=2, ensure_ascii=False), encoding='utf-8')
                                st.success('Receipt submitted for admin review. You will be notified when an admin confirms payment.')
                            except Exception as e:
                                st.error('Failed to save notification: ' + str(e))
                except Exception as e:
                    st.error('Error processing receipt: ' + str(e))
        except Exception:
            pass

        st.markdown('</div>', unsafe_allow_html=True)

        # Admin quick access: allow owner to open Billing Admin from the auth page
        try:
            # Determine if this session has admin privileges (silent check)
            user_email = st.session_state.get('user_email', '').strip().lower()
            admin_allowed = False
            if user_email == 'admin@local':
                admin_allowed = True
            else:
                # check global admin_meta.json for matching admin password in session
                from pathlib import Path
                import json as _json
                root = Path(__file__).parent.parent / 'saved_exams_storage'
                admf = root / 'admin_meta.json'
                try:
                    if admf.exists():
                        am = _json.loads(admf.read_text(encoding='utf-8') or '{}')
                        if am.get('super_admin_password') and st.session_state.get('admin_password') and str(am.get('super_admin_password')) == str(st.session_state.get('admin_password')):
                            admin_allowed = True
                except Exception:
                    admin_allowed = False

            if admin_allowed:
                with st.expander('Admin Panel (owner only)', expanded=False):
                    st.write('Open administrative tools')
                    if st.button('Open Billing Admin (admin only)'):
                        # mark that admin panel flow is active so billing_admin can render
                        st.session_state['admin_panel_access'] = True
                        st.session_state['current_page'] = 'billing_admin'
                        try:
                            st.experimental_rerun()
                        except Exception:
                            pass
        except Exception:
            pass


# convenience name used by app.py
show = render_auth_page
