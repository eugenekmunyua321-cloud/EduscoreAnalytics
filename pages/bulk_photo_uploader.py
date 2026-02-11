import streamlit as st
if st.button("⬅️ Back to Home", key="back_to_home_bulk_photo"):
    # Ensure the full home header/banner is visible after switching pages
    try:
        st.session_state.show_home_header = True
    except Exception:
        pass
    st.switch_page("home.py")
if 'st' in globals() and hasattr(st, 'session_state') and st.session_state.get('_persistent_photo_rerun', False):
    st.session_state._persistent_photo_rerun = False

import streamlit as st
import pandas as pd
import os
from utils import student_photos as photos_mod
from modules import storage

# --- Ensure session state is initialized (copied from saved_exams.py) ---
def load_all_exams_into_session():
    import json
    # Use storage adapter for metadata and exam files
    base = storage.get_storage_dir()
    METADATA_FILE = os.path.join(base, 'exams_metadata.json')
    all_metadata = storage.read_json(METADATA_FILE) or {}
    st.session_state.saved_exams = []
    for exam_id, metadata in all_metadata.items():
        st.session_state.saved_exams.append(metadata)
    st.session_state.saved_exam_data = {}
    st.session_state.saved_exam_raw_data = {}
    st.session_state.saved_exam_configs = {}
    for exam_id in all_metadata.keys():
        data_key = os.path.join(exam_id, 'data.pkl')
        raw_data_key = os.path.join(exam_id, 'raw_data.pkl')
        config_key = os.path.join(exam_id, 'config.json')
        try:
            df = storage.read_pickle(data_key)
            if df is not None:
                st.session_state.saved_exam_data[exam_id] = df
        except Exception:
            pass
        try:
            rdf = storage.read_pickle(raw_data_key)
            if rdf is not None:
                st.session_state.saved_exam_raw_data[exam_id] = rdf
        except Exception:
            pass
        try:
            cfg = storage.read_json(config_key)
            if cfg is not None:
                st.session_state.saved_exam_configs[exam_id] = cfg
        except Exception:
            pass

# Initialize session state for saved exams if not present
if 'saved_exams' not in st.session_state:
    load_all_exams_into_session()
if 'saved_exam_data' not in st.session_state:
    st.session_state.saved_exam_data = {}
if 'saved_exam_configs' not in st.session_state:
    st.session_state.saved_exam_configs = {}
if 'saved_exam_raw_data' not in st.session_state:
    st.session_state.saved_exam_raw_data = {}

st.set_page_config(page_title="Bulk Photo Uploader", layout="wide")

# Block access when parents portal mode is active
try:
    if st.session_state.get('parents_portal_mode'):
        st.markdown("<div style='opacity:0.45;padding:18px;border-radius:8px;background:#f3f4f6;color:#111;'>\
            <strong>Restricted:</strong> This page is not available in Parents Portal mode.</div>", unsafe_allow_html=True)
        st.stop()
except Exception:
    pass

st.title("📸 Bulk Photo Uploader")

st.markdown("""
This tool allows you to upload and match student photos in bulk, using either your own order list or an existing exam list.
""")

# --- Bulk Photo Uploader: Copied from saved_exams.py ---
with st.expander("🔄 Interactive Bulk Photo Matcher", expanded=False):
    st.caption("Upload a ZIP file or select multiple images. We'll show previews, auto-match by order, let you edit, then save.")
    # STEP 1: Choose order list source FIRST
    st.markdown("#### Step 1: Choose Student List Source")
    order_list_source = st.radio(
        "Which student list do you want to use?",
        options=["Use My Own Order List (Upload CSV/Excel)", "Use Existing Exam List"],
        horizontal=False,
        key="order_list_source"
    )
    # Initialize variables
    match_exam = None
    match_class = None
    order_list_file = None
    # STEP 2: Show relevant options based on choice
    if order_list_source == "Use My Own Order List (Upload CSV/Excel)":
        st.markdown("#### Step 2: Upload Your Order List & Photos")
        st.caption("Upload a CSV/Excel with Name and Adm No columns. Row order will match photo order (1st photo → 1st row).")
        order_list_file = st.file_uploader(
            "Upload Order List (CSV/Excel)", 
            type=["csv", "xlsx", "xls"], 
            key="order_list",
            help="Upload a list with Name and Adm No columns. Row order = photo order."
        )
        if order_list_file:
            st.success("✅ Order list uploaded. Photos will match in exact row order from your file.")
    else:  # Use Existing Exam List
        st.markdown("#### Step 2: Select Exam & Class")
        select_col1, select_col2 = st.columns([2, 2])
        with select_col1:
            exam_names2 = [exam.get('exam_name', f"Exam {i+1}") for i, exam in enumerate(st.session_state.saved_exams)]
            match_exam = st.selectbox("Select Exam", options=exam_names2 if exam_names2 else ["No exams available"], key="match_exam_sel")
        with select_col2:
            match_class_options = ["All Classes"]
            if match_exam and match_exam != "No exams available":
                match_exam_obj = next((e for e in st.session_state.saved_exams if e.get('exam_name') == match_exam), None)
                if match_exam_obj:
                    match_df = st.session_state.saved_exam_data.get(match_exam_obj.get('exam_id'))
                    if isinstance(match_df, pd.DataFrame) and 'Class' in match_df.columns:
                        # Filter out invalid classes (totals, means, numbers only, empty)
                        valid_classes = []
                        for cls in match_df['Class'].dropna().unique():
                            cls_str = str(cls).strip()
                            # Skip empty
                            if not cls_str:
                                continue
                            # Skip summary words
                            if cls_str.lower() in ['mean', 'total', 'average', 'sum', 'grand total']:
                                continue
                            # Skip pure numbers
                            try:
                                float(cls_str)
                                continue
                            except ValueError:
                                # Check if it has at least one letter (like 9G, 9B)
                                if any(c.isalpha() for c in cls_str):
                                    valid_classes.append(cls_str)
                        match_class_options = ["All Classes"] + sorted(valid_classes)
        match_class = st.selectbox("Filter by Class", options=match_class_options, key="match_class_sel")
    # --- STEP 3: Upload Photos ---
    st.markdown("#### Step 3: Upload Photos")
    st.caption("Upload a ZIP file or a folder of images. We recommend using a ZIP file for bulk uploads.")
    photo_uploads = st.file_uploader(
        "Upload Photos (ZIP or Images)",
        type=["zip", "jpg", "jpeg", "png"],
        key="photo_upload",
        help="Upload a ZIP file for bulk, or select multiple images.",
        accept_multiple_files=True
    )
    # --- Logic for handling uploaded photos ---
    photos_to_preview = []
    if photo_uploads:
        # If a single ZIP file is uploaded
        if len(photo_uploads) == 1 and photo_uploads[0].name.lower().endswith('.zip'):
            with st.spinner("📦 Extracting ZIP file..."):
                try:
                    zip_bytes = photo_uploads[0].read()
                    photos_to_preview = photos_mod.extract_zip(zip_bytes)
                    st.success("✅ ZIP file extracted.")
                except Exception as e:
                    st.error(f"❌ Error extracting ZIP file: {e}")
        else:
            # Multiple image files
            photos_to_preview = photo_uploads
    
    # --- Show photo previews in editable table/grid ---
    if photos_to_preview:
        st.markdown("#### Photo Previews (Editable)")

        def build_photo_match_entries():
            entries = []
            student_rows = []
            name_col = None
            adm_col = None
            def find_col(cols, targets):
                for t in targets:
                    for c in cols:
                        if c.strip().lower() == t:
                            return c
                return None
            if order_list_source == "Use My Own Order List (Upload CSV/Excel)" and order_list_file is not None:
                try:
                    if order_list_file.name.endswith('.csv'):
                        df_students = pd.read_csv(order_list_file)
                    else:
                        df_students = pd.read_excel(order_list_file)
                    name_col = find_col(df_students.columns, ['name'])
                    adm_col = find_col(df_students.columns, ['adm no','admno','adm_no','admission'])
                    if name_col and adm_col:
                        student_rows = df_students.to_dict('records')
                    else:
                        st.warning("Order list is missing required columns: Name and Adm No.")
                except Exception:
                    student_rows = []
            elif order_list_source == "Use Existing Exam List" and match_exam and match_exam != "No exams available":
                match_exam_obj = next((e for e in st.session_state.saved_exams if e.get('exam_name') == match_exam), None)
                if match_exam_obj:
                    match_df = st.session_state.saved_exam_data.get(match_exam_obj.get('exam_id'))
                    if isinstance(match_df, pd.DataFrame):
                        if match_class and match_class != "All Classes" and 'Class' in match_df.columns:
                            match_df = match_df[match_df['Class'] == match_class]
                        name_col = find_col(match_df.columns, ['name'])
                        adm_col = find_col(match_df.columns, ['adm no','admno','adm_no','admission'])
                        if name_col and adm_col:
                            student_rows = match_df.to_dict('records')
                        else:
                            st.warning("Exam data is missing required columns: Name and Adm No.")
            # Build student label list for dropdowns
            student_labels = []
            student_keys = []
            if name_col and adm_col:
                for row in student_rows:
                    name = str(row.get(name_col, '')).strip()
                    adm = str(row.get(adm_col, '')).strip()
                    label = f"{name} (Adm No: {adm})" if adm else name
                    student_labels.append(label)
                    student_keys.append((name, adm))
            for i, photo in enumerate(photos_to_preview):
                fname = getattr(photo, 'name', None) or (os.path.basename(photo) if isinstance(photo, str) else f"Image_{i+1}")
                # Default to i-th student if available
                sel_idx = i if i < len(student_labels) else 0
                entries.append({'photo': photo, 'student_idx': sel_idx, 'student_labels': student_labels, 'student_keys': student_keys})
            return entries

        # Always rebuild entries if user clicks match or changes selection
        if 'photo_match_entries' not in st.session_state:
            st.session_state.photo_match_entries = build_photo_match_entries()


        if st.button("🔍 Match Photos to Students", key="match_photos_btn"):
            st.session_state.photo_match_entries = build_photo_match_entries()
            st.session_state.photo_match_entries_reset = False

        # Improved editable grid with modern card design
        cols = st.columns(4)
        for i, entry in enumerate(st.session_state.photo_match_entries):
            with cols[i % 4]:
                photo = entry['photo']
                student_labels = entry.get('student_labels', [])
                student_keys = entry.get('student_keys', [])
                sel_idx = entry.get('student_idx', 0)
                # Generate a unique key for each photo input based on filename and index
                if hasattr(photo, 'name'):
                    unique_id = f"{i}_{getattr(photo, 'name', '')}"
                elif isinstance(photo, str):
                    unique_id = f"{i}_{os.path.basename(photo)}"
                else:
                    unique_id = f"{i}_photo"
                with st.container():
                    st.markdown(
                        f"""
                        <div style='background: #f8f9fa; border-radius: 12px; box-shadow: 0 2px 8px rgba(102,126,234,0.08); padding: 1rem; margin-bottom: 1.2rem; text-align: center;'>
                        """,
                        unsafe_allow_html=True
                    )
                    st.image(photo, use_container_width=True, caption=f"Photo {i+1}")
                    if student_labels:
                        entry['student_idx'] = st.selectbox(f"Student {i+1}", options=list(range(len(student_labels))), format_func=lambda x: student_labels[x], key=f"photo_student_{unique_id}", index=sel_idx)
                        name, adm = student_keys[entry['student_idx']]
                        st.markdown(f"**Name:** {name}")
                        st.markdown(f"**Adm No:** {adm}")
                    else:
                        st.markdown("<span style='color:#888'>No student list available</span>", unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)

        # Improved editable grid with modern card design
        cols = st.columns(4)
        for i, entry in enumerate(st.session_state.photo_match_entries):
            with cols[i % 4]:
                photo = entry['photo']
                with st.container():
                    st.markdown(
                        f"""
                        <div style='background: #f8f9fa; border-radius: 12px; box-shadow: 0 2px 8px rgba(102,126,234,0.08); padding: 1rem; margin-bottom: 1.2rem; text-align: center;'>
                        """,
                        unsafe_allow_html=True
                    )
                    st.image(photo, use_container_width=True, caption=f"Photo {i+1}")
                    entry['name'] = st.text_input(f"Name {i+1}", value=entry['name'], key=f"photo_name_{i}")
                    entry['adm_no'] = st.text_input(f"Adm No {i+1}", value=entry['adm_no'], key=f"photo_adm_{i}")
                    st.markdown("</div>", unsafe_allow_html=True)

        # --- Matching and saving logic ---
        st.markdown("#### Match & Save")
        if st.button("🔍 Match Photos to Students"):
            with st.spinner("🔄 Matching photos..."):
                try:
                    # Here you could implement auto-matching logic if needed
                    st.success("✅ Photos matched successfully. You can now edit names/Adm No and save.")
                except Exception as e:
                    st.error(f"❌ Error matching photos: {e}")
        if st.button("💾 Save Matched Photos", key="save_matched_photos_btn"):
            with st.spinner("💾 Saving photos..."):
                try:
                    # Save each photo with the entered name and Adm No
                    for i, entry in enumerate(st.session_state.photo_match_entries):
                        photo = entry['photo']
                        student_keys = entry.get('student_keys', [])
                        student_idx = entry.get('student_idx', 0)
                        if student_keys and 0 <= student_idx < len(student_keys):
                            name, adm_no = student_keys[student_idx]
                        else:
                            name, adm_no = '', ''
                        if hasattr(photo, 'read'):
                            file_bytes = photo.read()
                            fname = getattr(photo, 'name', f"Image_{i+1}.jpg")
                        elif isinstance(photo, str) and os.path.exists(photo):
                            with open(photo, 'rb') as f:
                                file_bytes = f.read()
                            fname = os.path.basename(photo)
                        else:
                            continue
                        saved = photos_mod.save_photo(file_bytes, fname, name=name, adm_no=adm_no)
                    st.success("✅ Matched photos saved successfully.")
                    st.session_state.photo_match_entries_reset = True
                    # avoid calling st.rerun() inside the callback; Streamlit will rerun after the interaction
                except Exception as e:
                    st.error(f"❌ Error saving photos: {e}")

# --- Student Photos (Persistent) and Bulk Photo Matcher: moved from saved_exams.py ---

# --- Persistent Photo Preview Section ---

# Only show photo preview if an exam is selected
exam_names2 = [exam.get('exam_name', f"Exam {i+1}") for i, exam in enumerate(st.session_state.saved_exams)]
sel_exam_name2 = st.session_state.get('photo_exam_sel') if 'photo_exam_sel' in st.session_state else None
if sel_exam_name2:
    st.markdown('<div class="section-header">📚 Saved Student Photos Preview</div>', unsafe_allow_html=True)
    photos_map = photos_mod.list_all_photos()
    if photos_map:
        preview_cols = st.columns(4)
        for idx, (sid, entry) in enumerate(photos_map.items()):
            with preview_cols[idx % 4]:
                path = entry.get('path')
                name = entry.get('name', '')
                adm = entry.get('adm_no', '')
                if path and os.path.exists(path):
                    st.image(path, use_container_width=True, caption=f"{name} (Adm No: {adm})")
                else:
                    st.markdown(f"<span style='color:#888'>No photo for {name} (Adm No: {adm})</span>", unsafe_allow_html=True)
    else:
        st.info("No student photos have been saved yet.")

st.markdown('<div class="section-header">🖼️ Student Photos (Persistent)</div>', unsafe_allow_html=True)
st.caption("Attach a photo to a student. Photos are stored persistently and can be used in reports.")

# Choose an exam to derive student list
exam_names2 = [exam.get('exam_name', f"Exam {i+1}") for i, exam in enumerate(st.session_state.saved_exams)]
if not exam_names2:
    st.info("No exams to derive students from yet.")
else:
    sel_exam_name2 = st.selectbox("Select exam to pick students from:", options=exam_names2, key="photo_exam_sel")
    sel_exam_obj2 = next((e for e in st.session_state.saved_exams if e.get('exam_name') == sel_exam_name2), None)
    if sel_exam_obj2:
        ex_id = sel_exam_obj2.get('exam_id')
        ex_df = st.session_state.saved_exam_data.get(ex_id)
        if isinstance(ex_df, pd.DataFrame) and not ex_df.empty:
            # Build student choices (exclude summary rows and blanks)
            def _valid_name(s):
                try:
                    ss = str(s).strip()
                    if not ss:
                        return False
                    return ss.lower() not in ['mean','average','total']
                except Exception:
                    return False
            df_valid = ex_df[ex_df['Name'].apply(_valid_name)] if 'Name' in ex_df.columns else ex_df.copy()
            # Prepare display labels with Adm No if available
            name_series = df_valid['Name'].astype(str) if 'Name' in df_valid.columns else pd.Series([], dtype=str)
            adm_series = None
            for cand in ['Adm No', 'AdmNo', 'Adm_No', 'admno', 'adm_no']:
                if cand in df_valid.columns:
                    adm_series = df_valid[cand].astype(str)
                    break
            labels = []
            keys = []
            for i, row in df_valid.iterrows():
                name = str(row.get('Name','')).strip()
                adm = ''
                for cand in ['Adm No', 'AdmNo', 'Adm_No', 'admno', 'adm_no']:
                    if cand in df_valid.columns:
                        adm = str(row.get(cand,'')).strip()
                        break
                sid, _, _ = photos_mod.get_student_id_from_row(row)
                lbl = f"{name} (Adm No: {adm})" if adm else name
                labels.append(lbl)
                keys.append((sid, name, adm))

            if labels:
                sel_idx = st.selectbox("Select student:", options=list(range(len(labels))), format_func=lambda i: labels[i], key="photo_student_sel")
                sid, sname, sadm = keys[sel_idx]

                # Show existing photo
                current_path = photos_mod.get_photo_path_by_id(sid)
                c1, c2 = st.columns([1,2])
                with c1:
                    if current_path and os.path.exists(current_path):
                        st.image(current_path, caption="Current photo", width=160)
                    else:
                        st.info("No photo yet")

                with c2:
                    # Use a session state counter to force file_uploader to reset after save/delete
                    if '_photo_upl_counter' not in st.session_state:
                        st.session_state._photo_upl_counter = 0
                    up = st.file_uploader("Upload new photo (PNG/JPG)", type=['png','jpg','jpeg'], key=f"photo_upl_{st.session_state._photo_upl_counter}")
                    if up is not None:
                        saved = photos_mod.save_photo(up.getbuffer(), up.name, name=sname, adm_no=sadm)
                        if saved:
                            st.success("Photo saved persistently.")
                            st.session_state._photo_upl_counter += 1
                            # avoid calling st.rerun() inside the upload handler
                        else:
                            st.error("Failed to save photo. Try a different image.")

                    col_del1, col_del2 = st.columns([1,4])
                    with col_del1:
                        if st.button("Remove Photo", key="photo_del_btn"):
                            if photos_mod.delete_photo(name=sname, adm_no=sadm):
                                st.success("Photo removed.")
                                st.session_state._photo_upl_counter += 1
                                # avoid calling st.rerun() inside the button callback
                            else:
                                st.warning("No photo to remove or deletion failed.")
# --- Persistent Photo Preview Section ---
