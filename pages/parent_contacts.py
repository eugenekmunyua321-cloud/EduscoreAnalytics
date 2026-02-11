import streamlit as st
import pandas as pd
import io
import json
import os
from pathlib import Path
try:
    import phonenumbers
    _HAS_PHONENUM = True
except Exception:
    phonenumbers = None
    _HAS_PHONENUM = False
from modules import storage

# Use per-school storage dir (or global) from storage helper to match other pages
def _contacts_key():
    try:
        base = storage.get_storage_dir()
        return os.path.join(base, 'student_contacts.json')
    except Exception:
        return os.path.join(get_storage_dir(), 'student_contacts.json')

# Block access when parents portal mode is active
try:
    if st.session_state.get('parents_portal_mode'):
        st.set_page_config(page_title="Parent Contacts", layout="wide")
        st.markdown("<div style='opacity:0.45;padding:18px;border-radius:8px;background:#f3f4f6;color:#111;'>\
            <strong>Restricted:</strong> This page is not available in Parents Portal mode.</div>", unsafe_allow_html=True)
        st.stop()
except Exception:
    pass

def ensure_storage():
    # ensure per-school container exists (adapter will create dirs in local fallback)
    try:
        k = _contacts_key()
        if not storage.exists(k):
            storage.write_json(k, [])
    except Exception:
        pass

def load_contacts():
    ensure_storage()
    try:
        k = _contacts_key()
        data = storage.read_json(k)
        return data or []
    except Exception:
        return []

def save_contacts(contacts):
    ensure_storage()
    k = _contacts_key()
    storage.write_json(k, contacts)

def normalize_number(raw, default_country='KE'):
    if not raw or str(raw).strip() == '':
        return ''
    s = str(raw).strip()
    # Remove common formatting
    # Prefer using the phonenumbers library when available for robust parsing.
    if _HAS_PHONENUM and phonenumbers is not None:
        try:
            if s.startswith('+'):
                pn = phonenumbers.parse(s, None)
            else:
                pn = phonenumbers.parse(s, default_country)
            if phonenumbers.is_valid_number(pn):
                return phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)
        except Exception:
            pass

    # Fallback heuristics (digits only, assume KE local numbers if starting with 0)
    digits = ''.join(ch for ch in s if ch.isdigit())
    if not digits:
        return ''
    if digits.startswith('0'):
        # assume Kenya local -> +254
        return '+254' + digits.lstrip('0')
    if digits.startswith('254'):
        return '+' + digits
    if digits.startswith('7') and len(digits) in (9,10):
        # common mobile start in KE without leading zero
        return '+254' + digits[-9:]
    # last resort, return digits as-is
    return digits

st.set_page_config(page_title="Parent Contacts", layout="wide")

st.title("Parent / Guardian Contacts")

if not _HAS_PHONENUM:
    st.warning("The optional package 'phonenumbers' is not installed. Phone normalization will use simple heuristics. To enable robust parsing install it: `pip install phonenumbers`.")

st.markdown(
    "Use this page to import, normalize and maintain parent/guardian phone numbers used for messaging students' results. Mobitech will be used to send messages from the Send Messages page."
)

ensure_storage()
contacts = load_contacts()
df = pd.DataFrame(contacts)

with st.expander("Upload contacts CSV", expanded=True):
    st.markdown("CSV should contain at least: student_id, student_name, grade, stream, parent_name, phone")
    uploaded = st.file_uploader("Upload CSV file", type=["csv"]) 
    if uploaded is not None:
        try:
            new_df = pd.read_csv(uploaded)
            st.write("Preview uploaded file:")
            st.dataframe(new_df.head())
            if st.button("Normalize and add to contacts"):
                # normalize phones and append
                added = 0
                for _, row in new_df.iterrows():
                    rec = {
                        'student_id': str(row.get('student_id', '')).strip(),
                        'student_name': str(row.get('student_name', '')).strip(),
                        'grade': str(row.get('grade', '')).strip(),
                        'stream': str(row.get('stream', '')).strip(),
                        'parent_name': str(row.get('parent_name', '')).strip(),
                        'phone_raw': str(row.get('phone', '')).strip(),
                    }
                    rec['phone'] = normalize_number(rec['phone_raw'])
                    contacts.append(rec)
                    added += 1
                save_contacts(contacts)
                st.success(f"Added {added} contacts and normalized phone numbers.")
                df = pd.DataFrame(contacts)
        except Exception as e:
            st.error(f"Failed to read CSV: {e}")

st.markdown("---")

st.subheader("Current contacts")
if df.empty:
    st.info("No contacts found. Use the CSV uploader above or add manually below.")
else:
    # Use the interactive data editor when available (Streamlit >= some versions).
    if hasattr(st, 'experimental_data_editor'):
        edited = st.experimental_data_editor(df, num_rows="dynamic")
        if st.button("Save edited contacts"):
            # convert back to list of dicts, ensure phone normalization
            saved = []
            for _, row in edited.fillna('').iterrows():
                rec = {
                    'student_id': str(row.get('student_id', '')).strip(),
                    'student_name': str(row.get('student_name', '')).strip(),
                    'grade': str(row.get('grade', '')).strip(),
                    'stream': str(row.get('stream', '')).strip(),
                    'parent_name': str(row.get('parent_name', '')).strip(),
                    'phone_raw': str(row.get('phone', '')).strip(),
                }
                rec['phone'] = normalize_number(rec['phone_raw'])
                saved.append(rec)
            save_contacts(saved)
            st.success("Contacts saved.")
    else:
        # Fallback for older Streamlit versions that don't have the editable grid.
        st.warning("Your Streamlit version does not support the interactive data editor. Use the CSV editor below to edit contacts.")
        csv_val = df.to_csv(index=False)
        edited_csv = st.text_area("Edit contacts as CSV (header row required). After editing click Parse and save.", value=csv_val, height=300)
        if st.button("Parse and save CSV edits"):
            try:
                new_df = pd.read_csv(io.StringIO(edited_csv))
                # convert back to list of dicts, ensure phone normalization
                saved = []
                for _, row in new_df.fillna('').iterrows():
                    rec = {
                        'student_id': str(row.get('student_id', '')).strip(),
                        'student_name': str(row.get('student_name', '')).strip(),
                        'grade': str(row.get('grade', '')).strip(),
                        'stream': str(row.get('stream', '')).strip(),
                        'parent_name': str(row.get('parent_name', '')).strip(),
                        'phone_raw': str(row.get('phone', '')).strip(),
                    }
                    rec['phone'] = normalize_number(rec['phone_raw'])
                    saved.append(rec)
                save_contacts(saved)
                st.success("Contacts saved from CSV edits.")
            except Exception as e:
                st.error(f"Failed to parse CSV: {e}")

st.markdown("---")

st.subheader("Add a single contact")
with st.form("single_contact"):
    sid = st.text_input("Student ID")
    sname = st.text_input("Student name")
    grade = st.text_input("Grade")
    stream = st.text_input("Stream")
    pname = st.text_input("Parent / Guardian name")
    phone = st.text_input("Phone number")
    submitted = st.form_submit_button("Add contact")
    if submitted:
        rec = {
            'student_id': str(sid).strip(),
            'student_name': str(sname).strip(),
            'grade': str(grade).strip(),
            'stream': str(stream).strip(),
            'parent_name': str(pname).strip(),
            'phone_raw': str(phone).strip(),
        }
        rec['phone'] = normalize_number(rec['phone_raw'])
        contacts.append(rec)
        save_contacts(contacts)
        st.success("Contact added.")

st.info(f"Contacts are stored in `{CONTACTS_FILE}`. The Send Messages page will use these when composing messages.")
