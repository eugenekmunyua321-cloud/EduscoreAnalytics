# home_page.py
# Home dashboard content - separated for cleaner organization

import streamlit as st
import os
import modules.auth as auth
# billing helper
try:
    import modules.billing as billing
except Exception:
    billing = None

# Logo color fallbacks (logo contains blue, green, orange, navy)
LOGO_BLUE = getattr(auth, 'BRAND_GRAD_A', '#0ea5e9')
LOGO_VIOLET = getattr(auth, 'BRAND_GRAD_B', '#6366f1')
LOGO_NAVY = getattr(auth, 'BRAND_PRIMARY', '#0f172a')
LOGO_GREEN = '#22c55e'
LOGO_ORANGE = '#fb923c'
LOGO_LIGHT_GREEN = '#bbf7d0'
LOGO_YELLOW = '#facc15'

def render_home_page():
    """Render the home/dashboard page.

    NOTE: Debug expander removed from the UI. To re-enable temporarily, set
    `st.session_state['show_home_debug'] = True` and restore the debug block.
    """
    # --- Sidebar password-change form (separate from profile form) ---
    try:
        if st.session_state.get('user_email'):
            import modules.auth as auth
            from pathlib import Path
            with st.sidebar.expander('Change password', expanded=False):
                with st.form('sidebar_change_password_form'):
                    sp_old = st.text_input('Current password', value='', type='password', key='sidebar_old_pw')
                    sp_new = st.text_input('New password', value='', type='password', key='sidebar_new_pw')
                    sp_new2 = st.text_input('Confirm new password', value='', type='password', key='sidebar_new_pw2')
                    submitted = st.form_submit_button('Change password')
                    if submitted:
                        try:
                            if not sp_old:
                                st.sidebar.error('Please enter your current password.')
                            elif sp_new != sp_new2:
                                st.sidebar.error('New passwords do not match.')
                            else:
                                # derive username (local accounts are stored as username@local)
                                ue = st.session_state.get('user_email') or ''
                                uname = str(ue).split('@')[0] if ue else ''
                                if not uname:
                                    st.sidebar.error('You must be signed in to change your password.')
                                else:
                                    ok, msg = auth.reset_local_password(uname, sp_old or '', sp_new or '')
                                    if not ok:
                                        st.sidebar.error('Password change failed: ' + (msg or 'Old password incorrect or error'))
                                    else:
                                        # audit log
                                        try:
                                            root = auth.USERS_FILE.parent
                                            audit = root / 'admin_actions.log'
                                            import json, time
                                            prev = []
                                            if audit.exists():
                                                try:
                                                    prev = json.loads(audit.read_text(encoding='utf-8') or '[]')
                                                except Exception:
                                                    prev = []
                                            prev.append({'time': int(time.time()), 'action': 'password_change', 'username': uname})
                                            try:
                                                audit.write_text(json.dumps(prev[-200:], indent=2, ensure_ascii=False), encoding='utf-8')
                                            except Exception:
                                                pass
                                        except Exception:
                                            pass
                                        st.sidebar.success('Password changed — you will be signed out. Please sign in with your new password.')
                                        # clear auth session so user must re-authenticate
                                        for _k in ['user_email', 'user_uid', 'school_display_name']:
                                            try:
                                                if _k in st.session_state:
                                                    del st.session_state[_k]
                                            except Exception:
                                                pass
                                        st.session_state['current_page'] = 'auth'
                                        # navigation will occur on the next rerun; avoid calling rerun() inside the callback
                        except Exception as e:
                            st.sidebar.error('Failed to change password: ' + str(e))
    except Exception:
        pass
    # --- (previous in-function flow continues below) ---

    # Branded welcome banner styled like the authentication page (same colors & layout)
    # Use the same font & banner design as the auth page for visual consistency
    st.markdown("<link href='https://fonts.googleapis.com/css2?family=Montserrat:wght@700;900&family=Poppins:wght@400;600;700&display=swap' rel='stylesheet'>", unsafe_allow_html=True)
    try:
        from pathlib import Path
        import base64
        logo_dir = Path(__file__).parent / 'static'
        logo_path_jpg = logo_dir / 'eduscore_logo.jpg'
        logo_path_jpeg = logo_dir / 'eduscore_logo.jpeg'
        logo_path_png = logo_dir / 'eduscore_logo.png'
        # also accept a user-specified temp image (WhatsApp image path) if present
        external_whatsapp_logo = Path(r"C:\Users\user\AppData\Local\Packages\5319275A.51895FA4EA97F_cv1g1gvanyjgm\TempState\856821BD2B5BC9082EFB1F81F17EA132\WhatsApp Image 2025-12-06 at 03.03.12_bff7b2d8.jpg")
        logo_html = None
        logo_path = None
        # prefer external WhatsApp image if available (user-provided path), else search local static files
        if external_whatsapp_logo.exists():
            logo_path = external_whatsapp_logo
        else:
            for p in (logo_path_png, logo_path_jpg, logo_path_jpeg):
                if p.exists():
                    logo_path = p
                    break
        # Build base64 logo HTML if we found a logo file
        logo_html = None
        if logo_path is not None:
            try:
                data = base64.b64encode(logo_path.read_bytes()).decode('ascii')
                mime = 'image/png' if str(logo_path).lower().endswith('.png') else 'image/jpeg'
                logo_html = f"<img src='data:{mime};base64,{data}' style='width:120px;height:120px;object-fit:contain;border-radius:12px;box-shadow:0 10px 34px rgba(2,6,23,0.22);'/>"
            except Exception:
                logo_html = None

        tile_html = """
            <div style="width:120px; height:120px; border-radius:16px; background: linear-gradient(135deg, rgba(255,255,255,0.12), rgba(255,255,255,0.06)); display:flex; align-items:center; justify-content:center; font-weight:900; font-size:48px; color:#fff; box-shadow: 0 10px 34px rgba(2,6,23,0.22);">E</div>
        """
        # Prefer a per-school logo if present in the school's storage directory.
        logo_fragment = None
        try:
            # try per-school storage first
            from modules import storage as _storage
            school_storage = _storage.get_storage_dir()
            # look for common logo filenames in the school folder
            for name in ('school_logo.png', 'school_logo.jpg', 'logo.png', 'logo.jpg', 'logo.jpeg'):
                cand = Path(school_storage) / name
                if cand.exists():
                    try:
                        data = base64.b64encode(cand.read_bytes()).decode('ascii')
                        mime = 'image/png' if cand.suffix.lower().endswith('png') else 'image/jpeg'
                        logo_fragment = f"<img src='data:{mime};base64,{data}' style='width:120px;height:120px;object-fit:contain;border-radius:12px;box-shadow:0 10px 34px rgba(2,6,23,0.22);'/>"
                        break
                    except Exception:
                        logo_fragment = None
                        break
        except Exception:
            logo_fragment = None

        # fallback to workspace static logo (preferred) or global logo_html or tile
        if not logo_fragment:
            try:
                static_logo_path = Path(__file__).parent / 'static' / 'eduscore_logo.jpg'
                if static_logo_path.exists():
                    data = base64.b64encode(static_logo_path.read_bytes()).decode('ascii')
                    logo_fragment = f"<img src='data:image/jpeg;base64,{data}' style='width:120px;height:120px;object-fit:contain;border-radius:12px;box-shadow:0 10px 34px rgba(2,6,23,0.22);'/>"
                else:
                    logo_fragment = logo_html if logo_html else tile_html
            except Exception:
                logo_fragment = logo_html if logo_html else tile_html

        display_name = st.session_state.get('school_display_name') or (st.session_state.get('user_email', '') or '').split('@')[0] or 'Guest'
        # Prefer the WhatsApp-sourced logo (if present) and embed it as a data URI so it appears inside the banner
        try:
            import streamlit.components.v1 as components
            img_tag = None
            # paths considered (in priority): external_whatsapp_logo, per-school logo, workspace static logo,
            # any discovered logo_path from earlier, and WhatsApp transfers in LocalState sessions
            try_paths = [external_whatsapp_logo, Path(__file__).parent / 'static' / 'eduscore_logo.jpg']
            # include any discovered logo_path from earlier as fallback
            if 'logo_path' in locals() and logo_path is not None:
                try_paths.append(Path(str(logo_path)))

            # Also look for matching WhatsApp transfer files under the user's LocalState sessions transfers directories
            try:
                pkg_root = Path.home() / 'AppData' / 'Local' / 'Packages' / '5319275A.51895FA4EA97F_cv1g1gvanyjgm' / 'LocalState' / 'sessions'
                if pkg_root.exists():
                    # glob for transfers/**/WhatsApp Image 2025-12-06 at 03.03*
                    for cand in pkg_root.rglob('transfers/**/WhatsApp Image 2025-12-06 at 03.03*'):
                        try_paths.insert(0, cand)
                        break
            except Exception:
                pass

            selected_logo_path = None
            for p in try_paths:
                try:
                    if p is None:
                        continue
                    if isinstance(p, str):
                        p = Path(p)
                    if p.exists():
                        mime = 'image/png' if str(p).lower().endswith('.png') else 'image/jpeg'
                        data = base64.b64encode(p.read_bytes()).decode('ascii')
                        img_tag = f"<img src='data:{mime};base64,{data}' style='width:120px;height:120px;object-fit:contain;border-radius:12px;box-shadow:0 10px 34px rgba(2,6,23,0.22);'/>"
                        selected_logo_path = str(p)
                        break
                except Exception:
                    continue

            if not img_tag:
                # last resort: use tile_html
                img_tag = tile_html

            banner_html = f'''
        <div style="width:100%; display:flex; justify-content:center;">
          <div style="max-width:920px; width:100%; padding:18px 20px; border-radius:12px; margin-bottom:12px; background: linear-gradient(90deg, #06243a, #0b4d3e); box-shadow: 0 12px 32px rgba(6,30,60,0.18); color: #fff;">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;">
                <div style="display:flex; align-items:center; gap:12px;">
                    {img_tag}
                    <div>
                        <div style="font-family: 'Montserrat', 'Poppins', 'Segoe UI', sans-serif; font-size:30px; font-weight:900; letter-spacing:0.01em; line-height:1; text-transform:uppercase;">
                            <span style="color: {LOGO_BLUE};">EDUSCORE</span>
                            <span style="margin-left:8px; color: {LOGO_YELLOW};">ANALYTICS</span>
                        </div>
                        <div style="opacity:0.9; margin-top:6px; font-size:12px;">Beautiful analytics, locally hosted — crafted for schools and educators.</div>
                        <div style="margin-top:8px;font-size:32px;font-weight:900;">Welcome, {display_name}</div>
                    </div>
                </div>
                <div style="text-align:right; min-width:120px;">
                    <div style="background: rgba(255,255,255,0.06); padding:8px 12px; border-radius:999px; display:inline-block; font-weight:700; font-size:12px;">Signed in</div>
                </div>
            </div>
          </div>
        </div>
        '''
            components.html(banner_html, height=220, scrolling=False)
            # (no debug hint displayed in production)
        except Exception:
            # if anything fails, fall back to the simple markdown banner without the image
            st.markdown(f"""
            <div style="width:100%; display:flex; justify-content:center;">
              <div style="max-width:920px; width:100%; padding:20px 18px; border-radius:12px; margin-bottom:16px; background: linear-gradient(90deg, #06243a, #0b4d3e); box-shadow: 0 14px 40px rgba(6,30,60,0.20); color: #fff; display:flex; gap:12px; align-items:center;">
                <div>
                    <div style='font-size:26px;font-weight:900;'>EDUSCORE ANALYTICS</div>
                    <div style='opacity:0.95;margin-top:6px;font-size:12px;'>Beautiful analytics, locally hosted — crafted for schools and educators.</div>
                    <div style='margin-top:6px;font-size:28px;font-weight:900;'>Welcome, {display_name}</div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        # (Admin billing controls have been moved to the dedicated Billing Admin page.)
    except Exception:
        # fallback compact banner when logo rendering fails
        try:
            logo_path = 'static/eduscore_logo.jpg'
            display_name = st.session_state.get('school_display_name') or (st.session_state.get('user_email', '') or '').split('@')[0] or 'Guest'
            st.markdown(f"""
        <div style="width:100%; display:flex; justify-content:center;">
          <div style="max-width:920px; width:100%; padding:20px 18px; border-radius:12px; margin-bottom:16px; background: linear-gradient(90deg, #06243a, #0b4d3e); box-shadow: 0 14px 40px rgba(6,30,60,0.20); color: #fff; display:flex; gap:12px; align-items:center;">
            <img src='{logo_path}' style='width:120px;height:120px;border-radius:12px;object-fit:cover;border:1px solid rgba(255,255,255,0.08);box-shadow:0 6px 20px rgba(0,0,0,0.12)' />
            <div>
                <div style='font-size:26px;font-weight:900;'>EDUSCORE ANALYTICS</div>
                <div style='opacity:0.95;margin-top:6px;font-size:12px;'>Beautiful analytics, locally hosted — crafted for schools and educators.</div>
                <div style='margin-top:6px;font-size:28px;font-weight:900;'>Welcome, {display_name}</div>
            </div>
          </div>
        </div>
            """, unsafe_allow_html=True)
        except Exception:
            pass
    # Add New Exam card below the welcome banner (Streamlit-native controls)
    # Central handler for navigating to the new exam (shared by multiple buttons)
    def _do_add_exam():
        try:
            st.session_state['add_exam_clicked'] = True
            st.session_state['current_page'] = 'new_exam'
        except Exception:
            pass
        # Avoid calling rerun() inside the button callback — the top-level code will detect
        # the 'add_exam_clicked' flag and trigger a rerun in a safe, non-callback context.
        return

    # Add New Exam card (banner) — simplified layout without the Quick action button
    with st.container():
        c1, c2 = st.columns([1, 9])
        with c1:
            st.markdown("<div style='font-size:2.4rem'>🆕</div>", unsafe_allow_html=True)
        with c2:
            st.markdown("""
            <div style='font-size:1.1rem; font-weight:800; color:#0f172a; margin-bottom:4px;'>Add New Exam</div>
            <div style='color:#475569;'>Enter marks for a new examination and analyze results</div>
            """, unsafe_allow_html=True)
    # Use a Streamlit button for navigation (no form submit)
    # Primary Add New Exam button (behaves exactly like Quick action)
    st.button("Add New Exam", key="raw_mark_sheet_btn", use_container_width=True, on_click=_do_add_exam)
    # Handle navigation only once per click
    if st.session_state.pop('add_exam_clicked', False):
        st.session_state.current_page = "new_exam"
        st.experimental_rerun()
    # Style the Streamlit button for better visibility (client-side tweak)
    try:
        import streamlit.components.v1 as components
        grad = f"{auth.BRAND_GRAD_A}, {auth.BRAND_GRAD_B}"
        js_template = """
        <script>
        (function(){
            const btnText = 'Add New Exam';
            function styleBtn(){
                const all = Array.from(document.querySelectorAll('button'));
                for(const b of all){
                    if(b.innerText && b.innerText.trim().startsWith(btnText)){
                        b.style.padding = '16px 28px';
                        b.style.fontSize = '1.05rem';
                        b.style.height = '54px';
                        b.style.minHeight = '54px';
                        b.style.borderRadius = '10px';
                        b.style.background = 'linear-gradient(90deg, {GRAD})';
                        b.style.color = '#fff';
                        b.style.boxShadow = '0 12px 36px rgba(37,99,235,0.14)';
                        b.style.border = 'none';
                    }
                }
            }
            setTimeout(styleBtn, 250);
        })();
        </script>
        """
        components.html(js_template.replace('{GRAD}', grad), height=0)
    except Exception:
        pass
    """Render the main home dashboard"""
    # Modern, professional banner/header
    # Arrange all dashboard cards in two columns, flowing downwards

    # --- Dashboard Info Banners ---

    import json
    import os
    from datetime import datetime

    # --- Message and Purchase stats (new) ---
    from modules.storage import get_storage_dir as _get_storage_dir
    STORAGE_DIR = _get_storage_dir()
    LOG_PATH = os.path.join(STORAGE_DIR, 'sent_messages_log.json')
    PURCHASES_PATH = os.path.join(STORAGE_DIR, 'purchases.json')
    CREDITS_PATH = os.path.join(STORAGE_DIR, 'credits.json')

    # ensure files exist (use storage adapter when available)
    try:
        try:
            from modules import storage as _storage
        except Exception:
            _storage = None
        if _storage is not None:
            # ensure keys exist in storage (use per-account paths so adapter targets the correct files)
            if not _storage.exists(LOG_PATH):
                _storage.write_json(LOG_PATH, [])
            if not _storage.exists(PURCHASES_PATH):
                _storage.write_json(PURCHASES_PATH, [])
            if not _storage.exists(CREDITS_PATH):
                _storage.write_json(CREDITS_PATH, {})
        else:
            if not os.path.exists(STORAGE_DIR):
                os.makedirs(STORAGE_DIR, exist_ok=True)
            if not os.path.exists(LOG_PATH):
                open(LOG_PATH, 'w', encoding='utf-8').write('[]')
            if not os.path.exists(PURCHASES_PATH):
                open(PURCHASES_PATH, 'w', encoding='utf-8').write('[]')
            if not os.path.exists(CREDITS_PATH):
                open(CREDITS_PATH, 'w', encoding='utf-8').write('{}')
    except Exception:
        pass

    # load logs and purchases
    try:
        if _storage is not None:
            sent_log = _storage.read_json(LOG_PATH) or []
        else:
            with open(LOG_PATH, 'r', encoding='utf-8') as f:
                sent_log = json.load(f)
    except Exception:
        sent_log = []
    try:
        if _storage is not None:
            purchases = _storage.read_json(PURCHASES_PATH) or []
        else:
            with open(PURCHASES_PATH, 'r', encoding='utf-8') as f:
                purchases = json.load(f)
    except Exception:
        purchases = []
    try:
        if _storage is not None:
            credits = _storage.read_json(CREDITS_PATH) or {}
        else:
            with open(CREDITS_PATH, 'r', encoding='utf-8') as f:
                credits = json.load(f)
    except Exception:
        credits = {}

    now = datetime.now()
    def _is_same_day(ts):
        try:
            t = datetime.fromtimestamp(float(ts))
            return t.date() == now.date()
        except Exception:
            return False
    def _is_same_month(ts):
        try:
            t = datetime.fromtimestamp(float(ts))
            return t.year == now.year and t.month == now.month
        except Exception:
            return False
    def _is_same_year(ts):
        try:
            t = datetime.fromtimestamp(float(ts))
            return t.year == now.year
        except Exception:
            return False

    sent_today = sum(1 for e in sent_log if _is_same_day(e.get('time')))
    sent_month = sum(1 for e in sent_log if _is_same_month(e.get('time')))
    sent_year = sum(1 for e in sent_log if _is_same_year(e.get('time')))

    # messages purchased by account total
    total_purchased = sum((p.get('quantity') or 0) for p in purchases if isinstance(p, dict))

    # credits per school summary
    credits_summary = credits if isinstance(credits, dict) else {}

    # message stats banner removed per user request

    # Manage message purchases / credits: initially show a single button; reveal the form when clicked
    if st.button('Manage message purchases / credits', key='manage_purchases_btn'):
        st.session_state.show_purchase_form = True

    # Enlarge the specific 'Manage message purchases / credits' button using a small JS snippet
    try:
        import streamlit.components.v1 as components
        components.html("""
        <script>
        (function(){
            const btnText = 'Manage message purchases / credits';
            function enlarge(){
                const all = Array.from(document.querySelectorAll('button'));
                for(const b of all){
                    if(b.innerText && b.innerText.trim().startsWith(btnText)){
                        b.style.padding = '18px 28px';
                        b.style.fontSize = '1.05rem';
                        b.style.height = '64px';
                        b.style.minHeight = '64px';
                        b.style.borderRadius = '10px';
                    }
                }
            }
            // Run after short delay to ensure Streamlit has rendered the button
            setTimeout(enlarge, 300);
        })();
        </script>
        """, height=0)
    except Exception:
        pass

    if st.session_state.get('show_purchase_form'):
        # small close control so user can hide the purchase panel when done
        if st.button('Close', key='close_purchase_panel'):
            st.session_state.show_purchase_form = False
                # avoid calling st.experimental_rerun() inside the button callback

        # attempt to load student contacts to populate known school names or class names
        CONTACTS_PATH = os.path.join(STORAGE_DIR, 'student_contacts.json')
        known_schools = set()
        try:
            if _storage is not None:
                contacts = _storage.read_json('student_contacts.json') or []
            else:
                if os.path.exists(CONTACTS_PATH):
                    with open(CONTACTS_PATH, 'r', encoding='utf-8') as f:
                        contacts = json.load(f)
            if isinstance(contacts, list):
                for c in contacts:
                    for key in ('school', 'school_name', 'class', 'class_name', 'institution'):
                        v = c.get(key) if isinstance(c, dict) else None
                        if v:
                            known_schools.add(str(v))
        except Exception:
            contacts = []

        col_a, col_b, col_c = st.columns([2,1,1])
        with col_a:
            school = st.selectbox('Allocate to school (or choose New)', options=['-- New --'] + sorted(list(known_schools)), index=0)
            new_school = st.text_input('If New, enter school identifier (short name)')
        with col_b:
            qty = st.number_input('Quantity (messages)', min_value=1, value=100)
        with col_c:
            ref = st.text_input('Reference / MPESA transaction ID')
        if st.button('Record purchase (backup & allocate)', key='record_purchase_btn'):
            # append to purchases and update credits
            rec = {'time': now.timestamp(), 'school': (new_school.strip() or (school if school != '-- New --' else 'unassigned')), 'quantity': int(qty), 'reference': ref}
            try:
                purchases.append(rec)
                try:
                    if _storage is not None:
                        _storage.write_json('purchases.json', purchases)
                    else:
                        with open(PURCHASES_PATH, 'w', encoding='utf-8') as f:
                            json.dump(purchases, f, indent=2)
                except Exception:
                    pass
                # update credits
                key = rec['school']
                credits_summary[key] = int(credits_summary.get(key, 0)) + rec['quantity']
                try:
                    if _storage is not None:
                        _storage.write_json('credits.json', credits_summary)
                    else:
                        with open(CREDITS_PATH, 'w', encoding='utf-8') as f:
                            json.dump(credits_summary, f, indent=2)
                except Exception:
                    pass
                st.success(f"Recorded purchase for {key}: +{rec['quantity']} messages")
            except Exception as e:
                st.error('Failed to record purchase: ' + str(e))

        # show credits summary (compact)
        try:
            if credits_summary:
                items = ''.join([f"<div style='padding:6px 10px;background:#f8fafc;border-radius:8px;margin:4px;display:inline-block;'> {k}: <strong>{v}</strong></div>" for k,v in credits_summary.items()])
                st.markdown(f"<div style='margin-top:12px'>{items}</div>", unsafe_allow_html=True)
        except Exception:
            pass


    # Load exam metadata from per-school storage so accounts don't overlap
    try:
        from modules.storage import get_storage_dir as _get_storage_dir
        try:
            from modules import storage as _storage
        except Exception:
            _storage = None
        meta_dir = _get_storage_dir()
        meta_path = os.path.join(meta_dir, 'exams_metadata.json')
        meta = {}
        try:
            if _storage is not None:
                    # ask adapter for the canonical metadata key (use full per-account path)
                    try:
                        meta = _storage.read_json(meta_path) or {}
                    except Exception:
                        meta = {}
            else:
                if os.path.exists(meta_path):
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
        except Exception:
            # fallback to local file if adapter read fails
            try:
                if os.path.exists(meta_path):
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
            except Exception:
                meta = {}
    except Exception:
        # Fallback to global storage if anything goes wrong
        meta_path = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage', 'exams_metadata.json')
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
        except Exception:
            meta = {}

    # If the per-account metadata is empty, attempt a tolerant fallback: search for
    # similarly-named storage folders (common when account name variants exist) and
    # try loading metadata from them. This helps when the same user has data under
    # a slightly different school_id folder (for example, extra underscore).
    try:
        if not meta:
            root = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')
            sid = auth.safe_email_to_schoolid(st.session_state.get('user_email',''))
            base = sid.split('_at_')[0] if '_at_' in sid else sid
            candidates = []
            try:
                for name in os.listdir(root):
                    p = os.path.join(root, name)
                    if os.path.isdir(p) and base in name and name != sid:
                        candidates.append(name)
            except Exception:
                candidates = []

            for c in candidates:
                try:
                    # Prefer adapter read when possible (handles S3)
                    alt_meta = None
                    try:
                        if _storage is not None:
                            alt_meta = _storage.read_json(os.path.join(c, 'exams_metadata.json'))
                    except Exception:
                        alt_meta = None
                    if alt_meta is None:
                        try_path = os.path.join(root, c, 'exams_metadata.json')
                        if os.path.exists(try_path):
                            try:
                                with open(try_path, 'r', encoding='utf-8') as fh:
                                    alt_meta = json.load(fh)
                            except Exception:
                                alt_meta = None
                    if alt_meta:
                        meta = alt_meta
                        st.warning(f"Loaded saved exams from similar account folder: {c}")
                        break
                except Exception:
                    continue
    except Exception:
        pass

    # If we still have no meta but there are candidate folders with data, offer a one-click
    # migration tool in the debug expander so mobile users can import the exams into their
    # current account folder. This is safe (non-destructive) and will not overwrite existing
    # files unless the destination lacks them.
    try:
        if not meta:
            root = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')
            sid = auth.safe_email_to_schoolid(st.session_state.get('user_email',''))
            base = sid.split('_at_')[0] if '_at_' in sid else sid
            # find the first non-empty candidate
            candidate = None
            for name in os.listdir(root):
                p = os.path.join(root, name)
                if os.path.isdir(p) and base in name and name != sid:
                    try:
                        mp = os.path.join(p, 'exams_metadata.json')
                        if os.path.exists(mp):
                            with open(mp, 'r', encoding='utf-8') as fh:
                                d = json.load(fh)
                            if d:
                                candidate = name
                                break
                    except Exception:
                        continue

            if candidate:
                with st.expander('Migration helper (one-time)', expanded=False):
                    st.markdown(f"Detected saved exams in a similar account folder: **{candidate}**")
                    st.markdown("If these are your exams, you can import them into your current account folder so they appear on this device.")
                    if st.button(f"Import exams from {candidate}"):
                        try:
                            import shutil
                            src = os.path.join(root, candidate)
                            dst = os.path.join(root, sid)
                            os.makedirs(dst, exist_ok=True)
                            # copy metadata
                            try:
                                shutil.copy2(os.path.join(src, 'exams_metadata.json'), os.path.join(dst, 'exams_metadata.json'))
                            except Exception:
                                pass
                            # copy each exam directory if present
                            for item in os.listdir(src):
                                src_item = os.path.join(src, item)
                                dst_item = os.path.join(dst, item)
                                # copy directories that look like exam ids (uuid-like) or data pickles
                                if os.path.isdir(src_item):
                                    if not os.path.exists(dst_item):
                                        try:
                                            shutil.copytree(src_item, dst_item)
                                        except Exception:
                                            # fallback to copying files inside
                                            try:
                                                os.makedirs(dst_item, exist_ok=True)
                                                for f in os.listdir(src_item):
                                                    try:
                                                        shutil.copy2(os.path.join(src_item, f), os.path.join(dst_item, f))
                                                    except Exception:
                                                        pass
                                            except Exception:
                                                pass
                                else:
                                    # copy top-level files like purchases, credits, etc. (skip users.json)
                                    if item not in ('users.json',):
                                        try:
                                            shutil.copy2(src_item, dst_item)
                                        except Exception:
                                            pass
                            st.success('Imported exams. Reloading...')
                            # avoid calling st.experimental_rerun() inside the import handler; rely on session state changes
                        except Exception as e:
                            st.error(f'Import failed: {e}')
    except Exception:
        pass

    # Tolerant fallback (controlled): Do NOT auto-load other accounts' metadata
    # when a user is signed in. Auto-loading caused a new account to display
    # someone else's exam counts (confusing/incorrect). Instead, show a short
    # informational hint inviting the user to import exams via the Migration helper
    # (which is safer and explicit). We still allow auto-fallback for anonymous or
    # non-signed sessions where showing any available data is desirable.
    try:
        if not meta:
            signed_in = bool(st.session_state.get('user_email'))
            if signed_in:
                # Signed-in user has no saved exams. UI message removed per request.
                pass
            else:
                # Allow auto-fallback when not signed-in (read-only preview mode)
                root = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')
                for dirpath, dirnames, filenames in os.walk(root):
                    if 'exams_metadata.json' in filenames:
                        candidate_path = os.path.join(dirpath, 'exams_metadata.json')
                        try:
                            # Try to load JSON; prefer the storage adapter when available
                            if _storage is not None:
                                cand = _storage.read_json(candidate_path) or {}
                            else:
                                with open(candidate_path, 'r', encoding='utf-8') as fh:
                                    import json as _json
                                    cand = _json.load(fh) or {}
                            if cand:
                                meta = cand
                                try:
                                    st.info(f"Loaded exams metadata from {os.path.relpath(candidate_path)} (read-only fallback)")
                                except Exception:
                                    pass
                                break
                        except Exception:
                            # ignore and continue searching
                            continue
    except Exception:
        pass

    

    # All exams saved
    all_exams = len(meta)

    # main-page saved exam selector removed to avoid appearing on the sign-in page

    # Exams done this year
    current_year = datetime.now().year
    exams_this_year = 0
    for v in meta.values():
        if str(v.get('year', '')).strip() == str(current_year):
            exams_this_year += 1

    # Get last uploaded exam info
    if meta:
        last_exam_id = max(meta, key=lambda k: meta[k].get('date_saved', ''))
        last_exam = meta[last_exam_id].get('exam_name', 'N/A')
        last_exam_date = meta[last_exam_id].get('date_saved', 'N/A')
    else:
        last_exam = 'N/A'
        last_exam_date = 'N/A'

    # Last active = now (for demo, could use real user activity)
    last_active = datetime.now().strftime('%Y-%m-%d %H:%M')

    # Number of unique classes (normalize names)
    import re
    def normalize_class_name(name):
        name = name.lower().replace(' ', '')
        name = re.sub(r'grade ?(nine|9)', 'grade9', name)
        return name

    classes = set()
    for v in meta.values():
        if 'class_name' in v:
            norm = normalize_class_name(v['class_name'])
            classes.add(norm)
    num_classes = len(classes)

    # Cards — each with a solid color and consistent, modern layout. Also add message metric banners.
    total_sent = len(sent_log)
    remaining_messages = max(int(total_purchased) - int(total_sent), 0)


    # --- Dashboard Cards ---
    st.markdown("""
        <style>
        .dash-grid { display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:1.2rem; align-items:flex-start; }
        .dash-card { flex:1; min-width:180px; height:120px; border-radius:12px; padding:14px; box-shadow:0 8px 26px rgba(2,6,23,0.08); color: #fff; display:flex; flex-direction:column; justify-content:center; }
        .dash-label { font-size:0.92rem; opacity:0.95; font-weight:600; margin-bottom:6px; }
        .dash-value { font-size:1.6rem; font-weight:900; line-height:1; }
        .dash-sub { font-size:0.95rem; opacity:0.9; font-weight:600; margin-top:6px; }
        /* Staggered but same-size layout for a unique arrangement */
        .dash-grid .dash-card:nth-child(odd) { transform: translateY(6px); }
        .dash-grid .dash-card:nth-child(even) { transform: translateY(-6px); }
        .eduscore-footer { margin-top:20px; padding:18px 8px; text-align:center; background:#000; color:#fff; font-size:0.9rem; border-radius:8px; }
        </style>
    """, unsafe_allow_html=True)

    # Main stats row
    st.markdown("""
        <div class='dash-grid'>
            <div class='dash-card' style='background: linear-gradient(135deg, #06b6d4, rgba(255,255,255,0.03));'>
                <div class='dash-label'>Exams Done This Year</div>
                <div class='dash-value'>{exams_this_year}</div>
            </div>
            <div class='dash-card' style='background: linear-gradient(135deg, #0f172a, rgba(255,255,255,0.02));'>
                <div class='dash-label'>All Exams Saved</div>
                <div class='dash-value'>{all_exams}</div>
            </div>
            <div class='dash-card' style='background: linear-gradient(135deg, #22c55e, rgba(255,255,255,0.03));'>
                <div class='dash-label'>Last Uploaded Exam</div>
                <div class='dash-value' style='font-size:1.05rem;font-weight:800'>{last_exam}</div>
                <div class='dash-sub'>{last_exam_date}</div>
            </div>
            <div class='dash-card' style='background: linear-gradient(135deg, #fb923c, rgba(255,255,255,0.03));'>
                <div class='dash-label'>Last Active</div>
                <div class='dash-value' style='font-size:1.05rem;font-weight:800'>{last_active}</div>
            </div>
            <div class='dash-card' style='background: linear-gradient(135deg, #06b6d4, #0f172a);'>
                <div class='dash-label'>Number of Classes</div>
                <div class='dash-value'>{num_classes}</div>
            </div>
        </div>
    """.format(
        exams_this_year=exams_this_year,
        all_exams=all_exams,
        last_exam=last_exam,
        last_exam_date=last_exam_date,
        last_active=last_active,
        num_classes=num_classes
    ), unsafe_allow_html=True)

    # Message metrics row
    st.markdown("""
        <div class='dash-grid'>
            <div class='dash-card' style='background: linear-gradient(135deg, #22c55e, rgba(255,255,255,0.02)); color:#042014;'>
                <div class='dash-label'>Messages Purchased (Total)</div>
                <div class='dash-value'>{total_purchased}</div>
            </div>
            <div class='dash-card' style='background: linear-gradient(135deg, #06b6d4, rgba(255,255,255,0.02));'>
                <div class='dash-label'>Messages Sent Today</div>
                <div class='dash-value'>{sent_today}</div>
            </div>
            <div class='dash-card' style='background: linear-gradient(135deg, #0f172a, rgba(255,255,255,0.02));'>
                <div class='dash-label'>Messages Sent This Month</div>
                <div class='dash-value'>{sent_month}</div>
            </div>
            <div class='dash-card' style='background: linear-gradient(135deg, #fb923c, rgba(255,255,255,0.02));'>
                <div class='dash-label'>Messages Sent This Year</div>
                <div class='dash-value'>{sent_year}</div>
            </div>
            <div class='dash-card' style='background: linear-gradient(135deg, #06b6d4, #22c55e);'>
                <div class='dash-label'>Remaining Messages</div>
                <div class='dash-value'>{remaining_messages}</div>
            </div>
        </div>
    """.format(
        total_purchased=total_purchased,
        sent_today=sent_today,
        sent_month=sent_month,
        sent_year=sent_year,
        remaining_messages=remaining_messages
    ), unsafe_allow_html=True)

    # --- Subscription countdown banner (inserted below Remaining Messages) ---
    import modules.billing as billing
    import time as _t, datetime as _dt
    storage_dir = auth.get_storage_dir() if hasattr(auth, 'get_storage_dir') else None
    if not storage_dir:
        from modules import storage as storage_mod
        storage_dir = storage_mod.get_storage_dir()
    acct_billing = billing.get_account_billing(storage_dir)
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

    # Footer
    st.markdown("""
        <div style='text-align:center; font-size:12px; margin-top:18px;'>
            Thank you for choosing <b>Eduscore Analytics</b><br>
            For more of our services contact us on: <b>0793975959</b>
        </div>
    """, unsafe_allow_html=True)

