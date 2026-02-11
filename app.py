import streamlit as st
import warnings
# Suppress Streamlit warning about calling st.rerun() within widget callbacks
warnings.filterwarnings("ignore", message="Calling st.rerun\(\) within a callback is a no-op.")
from modules import auth
# Try to initialize optional Firebase sync helper (controlled by env vars)
fb = None
try:
    from modules import firebase_storage as fb_mod
    try:
        fb_mod.init_from_env()
        fb = fb_mod
    except Exception:
        fb = None
except Exception:
    fb = None
# (Removed legacy 'force_delegate_home' delegation — the app now delegates to the
# Home page using the signed-in check later in the startup flow.)
# Inject a small client-side script to hide Streamlit's multipage missing-page banner
# and any 'Back to home' button that may appear before this app fully renders.
try:
        import streamlit.components.v1 as components
        hide_script = """
        <script>
        (function(){
            function removeByText(text){
                try{
                    Array.from(document.querySelectorAll('body *')).forEach(function(el){
                        try{
                            if(el && el.innerText && el.innerText.indexOf(text) !== -1){
                                el.style.display = 'none';
                            }
                        }catch(e){}
                    });
                }catch(e){}
            }
            function removeBackButtons(){
                try{
                    Array.from(document.querySelectorAll('button')).forEach(function(b){
                        try{
                            var t = (b.innerText||'').trim();
                            if(/back to home/i.test(t) || /back to home/i.test(b.title||'')){
                                b.style.display = 'none';
                            }
                        }catch(e){}
                    });
                }catch(e){}
            }
            function run(){
                removeByText("The page 'login' is not available in this build.");
                // hide Streamlit rerun-in-callback warning if it appears
                removeByText("Calling st.rerun() within a callback is a no-op.");
                removeBackButtons();
            }
            if(document.readyState === 'complete'){
                run();
            } else {
                window.addEventListener('load', run);
            }
            // also run again shortly for dynamically added nodes
            setTimeout(run, 600);
        })();
        </script>
        """
        try:
                components.html(hide_script, height=1)
        except Exception:
                pass
except Exception:
        pass
# If the user is not signed in, render a dedicated login page and stop before any
# other UI (including sidebar) is created. After successful sign-in the app will
# rerun and the rest of the UI will load.
if not auth.get_current_school_id():
    # Use the standalone auth page file as the first page shown. It will hide the sidebar
    # and render the full-screen sign-in UI. Only after sign-in will the app continue.
    try:
        import auth_page
        auth_page.render_auth_page()
    except Exception:
        # fallback to the module-based renderer if the standalone file has issues
        auth.render_login_page()
    # Prevent any further rendering until the user signs in
    st.stop()

# If the user is signed in, show the Home page implementation (home.py) immediately
# instead of running the rest of app.py. This makes the post-login experience match
# `streamlit run home.py` behavior.
if auth.get_current_school_id():
    try:
        import os
        home_path = os.path.join(os.path.dirname(__file__), 'home.py')
        if os.path.exists(home_path):
            with open(home_path, 'r', encoding='utf-8-sig') as f:
                home_code = f.read().lstrip('\ufeff')
            ns = globals().copy()
            ns['__file__'] = home_path
            exec(home_code, ns)
            # stop further execution of this file after delegating to home.py
            st.stop()
    except Exception:
        # If anything goes wrong, continue with the original app.py behavior
        pass

# --- Auto-navigate to analysis view if triggered from Saved Exams page ---
if st.session_state.get('go_to_analysis'):
    st.session_state.view = 'analysis'
    st.session_state.go_to_analysis = False
    st.toast('Exam loaded! Analyzing now…')
    st.rerun()
# app.py
# Defensive import: ensure `st` is defined even if earlier imports fail for some reason
try:
    import streamlit as st
except Exception:
    # give a clearer error message at runtime
    raise ImportError("Streamlit is required to run this application. Install it with: pip install streamlit")
import pandas as pd
import json, os, time, re, unicodedata
from io import StringIO, BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import openpyxl
import pickle
# Central storage adapter (S3 or local fallback)
try:
    from modules import storage
except Exception:
    storage = None

# Import persistence functions from saved_exams page
# Use central storage adapter to determine storage dir and operations.
if storage is not None:
    try:
        STORAGE_DIR = storage.get_storage_dir()
    except Exception:
        STORAGE_DIR = os.path.join(os.path.dirname(__file__), 'saved_exams_storage')
else:
    STORAGE_DIR = os.path.join(os.path.dirname(__file__), 'saved_exams_storage')

METADATA_FILE = os.path.join(STORAGE_DIR, 'exams_metadata.json')
# Optional DB helper for remote storage
try:
    from modules import db as _db
except Exception:
    _db = None
# When true (env var), the app will prefer DB writes and skip local disk writes
USE_DB_STRICT = os.environ.get('USE_DB_STRICT', 'true').lower() in ('1', 'true', 'yes')

def save_exam_to_disk(exam_id, exam_metadata, exam_data, exam_raw_data, exam_config):
    """Save a single exam to disk"""
    try:
        # Initialize DB helper if available
        db_ok = False
        try:
            if _db is not None:
                _db.init_from_env()
                db_ok = _db.enabled()
        except Exception:
            db_ok = False

        # If not in strict DB mode, write files via the storage adapter (S3 or local)
        if not USE_DB_STRICT:
            try:
                # Load existing metadata (adapter will prefer remote when configured)
                all_metadata = {}
                if storage is not None:
                    try:
                        # prefer reading the per-account metadata path via the adapter
                        m = storage.read_json(METADATA_FILE)
                    except Exception:
                        # fallback to legacy bare-key read (adapter may accept keys)
                        m = storage.read_json('exams_metadata.json')
                    if isinstance(m, dict):
                        all_metadata = m
                else:
                    if os.path.exists(METADATA_FILE):
                        with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                            all_metadata = json.load(f)

                all_metadata[exam_id] = exam_metadata

                # Persist metadata
                if storage is not None:
                    try:
                        # write to the per-account metadata path
                        storage.write_json(METADATA_FILE, all_metadata)
                    except Exception:
                        # fallback to legacy bare-key write
                        try:
                            storage.write_json('exams_metadata.json', all_metadata)
                        except Exception:
                            pass
                else:
                    os.makedirs(STORAGE_DIR, exist_ok=True)
                    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
                        json.dump(all_metadata, f, indent=2, ensure_ascii=False)

                # Persist dataframes and config via adapter
                if storage is not None:
                    try:
                        if isinstance(exam_data, pd.DataFrame):
                            storage.write_pickle(f"{exam_id}/data.pkl", exam_data)
                        if isinstance(exam_raw_data, pd.DataFrame):
                            storage.write_pickle(f"{exam_id}/raw_data.pkl", exam_raw_data)
                        try:
                            storage.write_json(f"{exam_id}/config.json", exam_config)
                        except Exception:
                            pass
                    except Exception:
                        pass
                else:
                    exam_dir = os.path.join(STORAGE_DIR, exam_id)
                    os.makedirs(exam_dir, exist_ok=True)
                    if isinstance(exam_data, pd.DataFrame):
                        exam_data.to_pickle(os.path.join(exam_dir, 'data.pkl'))
                    if isinstance(exam_raw_data, pd.DataFrame):
                        exam_raw_data.to_pickle(os.path.join(exam_dir, 'raw_data.pkl'))
                    with open(os.path.join(exam_dir, 'config.json'), 'w', encoding='utf-8') as f:
                        json.dump(exam_config, f, indent=2, ensure_ascii=False)
            except Exception:
                # best-effort only
                pass

        # Save into DB if available
        try:
            sid = auth.get_current_school_id() or 'global'
        except Exception:
            sid = 'global'

        if db_ok:
            try:
                # metadata
                try:
                    _db.save_exam_metadata(sid, exam_id, exam_metadata)
                except Exception:
                    pass
                # pickles and config
                try:
                    from io import BytesIO
                    if isinstance(exam_data, pd.DataFrame):
                        b = BytesIO()
                        exam_data.to_pickle(b)
                        _db.save_exam_file(sid, exam_id, 'data.pkl', b.getvalue(), mimetype='application/octet-stream')
                    if isinstance(exam_raw_data, pd.DataFrame):
                        b = BytesIO()
                        exam_raw_data.to_pickle(b)
                        _db.save_exam_file(sid, exam_id, 'raw_data.pkl', b.getvalue(), mimetype='application/octet-stream')
                    try:
                        cfgb = json.dumps(exam_config, ensure_ascii=False).encode('utf-8')
                        _db.save_exam_file(sid, exam_id, 'config.json', cfgb, mimetype='application/json')
                    except Exception:
                        pass
                except Exception:
                    pass
            except Exception:
                pass
        else:
            # fallback: if Firebase helper exists, upload there as best-effort
            try:
                if fb is not None and getattr(fb, 'is_initialized', lambda: False)():
                    try:
                        base_blob_prefix = f"saved_exams/{sid}"
                        try:
                            # Ensure we have a local copy for the firebase helper
                            if storage is not None:
                                try:
                                    storage.download_file(METADATA_FILE, METADATA_FILE)
                                except Exception:
                                    # fallback to bare-key remote name
                                    try:
                                        storage.download_file('exams_metadata.json', METADATA_FILE)
                                    except Exception:
                                        pass
                            fb.upload_blob(METADATA_FILE, f"{base_blob_prefix}/exams_metadata.json")
                        except Exception:
                            pass
                        for fname in ('data.pkl', 'raw_data.pkl', 'config.json'):
                            lp = os.path.join(STORAGE_DIR, exam_id, fname)
                            try:
                                # If adapter is in use, download remote file into the local cache path
                                if storage is not None:
                                    try:
                                        storage.download_file(f"{exam_id}/{fname}", lp)
                                    except Exception:
                                        pass
                                if os.path.exists(lp):
                                    try:
                                        fb.upload_blob(lp, f"{base_blob_prefix}/{exam_id}/{fname}")
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                    except Exception:
                        pass
            except Exception:
                pass

        return True
    except Exception as e:
        st.error(f"Error saving exam to disk: {e}")
        return False

def load_all_exams_from_disk():
    """Load all saved exams from disk into session state"""
    try:
        # Try DB-first, then fall back to local storage
        db_ok = False
        try:
            if _db is not None:
                _db.init_from_env()
                db_ok = _db.enabled()
        except Exception:
            db_ok = False

        st.session_state.saved_exams = []
        all_metadata = {}
        if db_ok:
            try:
                sid = auth.get_current_school_id() or None
                rows = _db.list_exams(sid)
                for r in rows:
                    mid = r.get('metadata') or {}
                    all_metadata[r.get('exam_id')] = mid
            except Exception:
                all_metadata = {}
        else:
            # Use storage adapter to read metadata (will prefer remote if configured)
            try:
                if storage is not None:
                    try:
                        m = storage.read_json(METADATA_FILE)
                    except Exception:
                        m = storage.read_json('exams_metadata.json')
                    if isinstance(m, dict):
                        all_metadata = m
                else:
                    if not os.path.exists(METADATA_FILE):
                        return
                    with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                        all_metadata = json.load(f)
            except Exception:
                all_metadata = {}

        # Build saved_exams list from metadata
        for exam_id, metadata in all_metadata.items():
            st.session_state.saved_exams.append(metadata)

        # Setup caches
        st.session_state.saved_exam_data = {}
        st.session_state.saved_exam_raw_data = {}
        st.session_state.saved_exam_configs = {}

        # Load data for all exams (try DB files first, else storage adapter)
        for exam_id in list(all_metadata.keys()):
            try:
                loaded = False
                # DB-backed files
                if db_ok:
                    try:
                        files = _db.get_exam_files(exam_id)
                        for fname, data, mimetype in files:
                            if fname == 'data.pkl':
                                try:
                                    from io import BytesIO
                                    st.session_state.saved_exam_data[exam_id] = pd.read_pickle(BytesIO(data))
                                    loaded = True
                                except Exception:
                                    pass
                            elif fname == 'raw_data.pkl':
                                try:
                                    from io import BytesIO
                                    st.session_state.saved_exam_raw_data[exam_id] = pd.read_pickle(BytesIO(data))
                                    loaded = True
                                except Exception:
                                    pass
                            elif fname == 'config.json':
                                try:
                                    st.session_state.saved_exam_configs[exam_id] = json.loads(data.decode('utf-8'))
                                    loaded = True
                                except Exception:
                                    pass
                    except Exception:
                        loaded = False

                if not loaded:
                    # Use storage adapter to load pickles/config (will prefer remote)
                    try:
                        if storage is not None:
                            d = storage.read_pickle(f"{exam_id}/data.pkl")
                            if d is not None:
                                st.session_state.saved_exam_data[exam_id] = d
                                loaded = True
                            rd = storage.read_pickle(f"{exam_id}/raw_data.pkl")
                            if rd is not None:
                                st.session_state.saved_exam_raw_data[exam_id] = rd
                                loaded = True
                            cfg = storage.read_json(f"{exam_id}/config.json")
                            if cfg is not None:
                                st.session_state.saved_exam_configs[exam_id] = cfg
                                loaded = True
                        else:
                            exam_dir = os.path.join(STORAGE_DIR, exam_id)
                            if not os.path.exists(exam_dir):
                                continue
                            data_path = os.path.join(exam_dir, 'data.pkl')
                            raw_data_path = os.path.join(exam_dir, 'raw_data.pkl')
                            config_path = os.path.join(exam_dir, 'config.json')
                            if os.path.exists(data_path):
                                st.session_state.saved_exam_data[exam_id] = pd.read_pickle(data_path)
                                loaded = True
                            if os.path.exists(raw_data_path):
                                st.session_state.saved_exam_raw_data[exam_id] = pd.read_pickle(raw_data_path)
                                loaded = True
                            if os.path.exists(config_path):
                                with open(config_path, 'r', encoding='utf-8') as f:
                                    st.session_state.saved_exam_configs[exam_id] = json.load(f)
                                    loaded = True
                    except Exception:
                        # best-effort; continue to next exam
                        pass
            except Exception:
                continue
    except Exception as e:
        st.error(f"Error loading exams from disk: {e}")

def df_to_pdf_bytes(df, school_name, class_name, title='', orientation='portrait', scale=90, font_size=9, fit_all_rows=False):
    """Convert DataFrame to PDF bytes with better wrapping, alignment, and scaling."""
    buffer = BytesIO()
    pagesize = portrait(A4) if orientation.lower() == 'portrait' else landscape(A4)
    
    # If fit_all_rows is True, calculate appropriate font size based on number of rows
    cell_padding = 3  # Default padding
    if fit_all_rows:
        num_rows = len(df)
        # Available height considering margins and header
        available_height = pagesize[1] - (0.3 + 0.5) * inch - 0.5 * inch  # minus margins and title space
        # Reduce padding for fit all mode
        cell_padding = 1
        # Estimate row height based on font size (approximately font_size + 2*padding)
        target_row_height = available_height / (num_rows + 1)  # +1 for header row
        # Calculate font size (roughly row_height - 2*padding)
        calculated_font_size = max(3, min(9, target_row_height - (2 * cell_padding)))
        font_size = calculated_font_size
    
    # Create the PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=0.3*inch,
        rightMargin=0.3*inch,
        topMargin=0.3*inch,
        bottomMargin=0.5*inch
    )
    
    # Create styles for headers
    styles = getSampleStyleSheet()
    header_style = ParagraphStyle(
        'CustomHeader',
        parent=styles['Normal'],
        fontSize=14,
        spaceAfter=2,
        leading=16,
        textColor=colors.red,                  # red color for titles
        fontName='Helvetica-Bold',             # Algerian not available in ReportLab by default, using Helvetica-Bold
        alignment=1  # center alignment
    )
    
    # Create the content elements
    elements = []
    
    # Add a compact single-line header to save space
    title_parts = [str(school_name).upper().strip()]
    if class_name:
        title_parts.append(str(class_name).strip())
    if title:
        title_parts.append(str(title).strip())
    compact_title = ' • '.join([p for p in title_parts if p])
    elements.append(Paragraph(compact_title, header_style))
    
    # Abbreviate/shorten column headers for better fit
    def shorten_header(header):
        """Shorten column headers intelligently for PDF display"""
        h = str(header).strip()
        
        # Common abbreviations
        abbrev_map = {
            'Admission': 'Adm',
            'Number': 'No',
            'Combined': 'Cmb',
            'Percentage': '%',
            '_Combined%': '',
            'Total': 'Tot',
            'Average': 'Avg',
            'Science': 'Sci',
            'Mathematics': 'Math',
            'English': 'Eng',
            'Kiswahili': 'Kisw',
            'Christian': 'CRE',
            'Islamic': 'IRE',
            'Hindu': 'HRE',
            'Social': 'Soc',
            'Studies': 'Stud',
            'Agriculture': 'Agri',
            'Nutrition': 'Nutr',
            'Computer': 'Comp',
            'Technology': 'Tech',
            'Physical': 'Phys',
            'Education': 'Edu',
            'Business': 'Bus',
            'Integrated': 'Int',
            'Creative': 'Cre',
            'Pre-Technical': 'Pre-Tech',
        }
        
        # Apply abbreviations
        for full, short in abbrev_map.items():
            h = h.replace(full, short)
        
        # Remove common suffixes
        h = h.replace('_Cmb%', '').replace('_Combined', '').replace(' PP1', '1').replace(' PP2', '2')
        
        # Limit to reasonable length
        if len(h) > 15:
            # If still too long, use first letters of words
            words = h.split()
            if len(words) > 1:
                h = ''.join([w[0].upper() for w in words if w])
        
        return h[:15]  # Hard limit
    
    # Format data for table - NO Paragraphs, use plain text for horizontal expansion
    # This prevents vertical stretching and allows horizontal scrolling/scaling

    # Detect numeric columns for alignment
    numeric_cols = set()
    for idx, col in enumerate(df.columns):
        col_series = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
        if col_series.notna().mean() > 0.8:  # mostly numeric
            numeric_cols.add(idx)

    # Build headers row with shortened headers - plain strings, no Paragraph wrapping
    shortened_headers = [shorten_header(h) for h in df.columns.tolist()]
    data = [shortened_headers]
    
    # Build body rows - plain strings to prevent vertical stretching
    df_filled = df.fillna('')
    for _, row in df_filled.iterrows():
        row_cells = []
        for cidx, val in enumerate(row.tolist()):
            text = '' if pd.isna(val) else str(val)
            # For name column, truncate if too long to ensure single line
            col_name = df.columns[cidx].lower()
            if 'name' in col_name and len(text) > 30:
                text = text[:27] + '...'
            row_cells.append(text)
        data.append(row_cells)
    
    # Calculate column widths based on content - allow horizontal extension
    col_widths = []
    scale_factor = scale / 100.0
    available_width = doc.width * scale_factor
    
    # Count how many columns we have to determine appropriate spacing
    num_columns = len(shortened_headers)
    
    # Calculate width for each column based on header text length
    for idx, col in enumerate(shortened_headers):
        col_lower = col.lower()
        
        # Specific column widths for better name display
        if 'name' in col_lower:
            # Name column gets flexible width - will expand to fill remaining space
            width = 2.5 * inch  # Base width, will be adjusted later
        elif 'adm' in col_lower or col_lower in ['rank', 'rnk', '#']:
            # Admission number and rank columns: size based on header length
            header_chars = len(col)
            width = max(0.4 * inch, (header_chars * 0.07 + 0.2) * inch)
        elif 's/rank' in col_lower or 'stream' in col_lower or 'strm' in col_lower or 'class' in col_lower:
            # Stream/class column: size based on header length
            header_chars = len(col)
            width = max(0.35 * inch, (header_chars * 0.07 + 0.15) * inch)
        elif col_lower in ['total', 'mean', 'points']:
            # Total/Mean/Points: size based on header length
            header_chars = len(col)
            width = max(0.45 * inch, (header_chars * 0.08 + 0.2) * inch)
        elif idx in numeric_cols:
            # Subject columns (marks): size based on header length
            header_chars = len(col)
            width = max(0.5 * inch, (header_chars * 0.08 + 0.25) * inch)
        else:
            # Other columns: size based on header length
            header_chars = len(col)
            width = max(0.6 * inch, (header_chars * 0.08 + 0.3) * inch)
        
        col_widths.append(width)
    
    # Calculate total width of non-Name columns
    non_name_width = 0
    name_col_idx = None
    for idx, col in enumerate(shortened_headers):
        if 'name' in col.lower():
            name_col_idx = idx
        else:
            non_name_width += col_widths[idx]
    
    # Auto-scale to fit page width exactly if table is too wide (account for cell padding)
    # Keep these in sync with TableStyle LEFT/RIGHT padding values
    left_pad_pt = 2
    right_pad_pt = 2
    pad_inch_per_col = (left_pad_pt + right_pad_pt) / 72.0
    effective_available_width = max(0.1, available_width - (len(col_widths) * pad_inch_per_col))
    
    # Give remaining space to Name column
    if name_col_idx is not None:
        remaining_width = effective_available_width - non_name_width
        col_widths[name_col_idx] = max(1.5 * inch, remaining_width)  # At least 1.5 inches
    
    # If still too wide, scale everything down proportionally
    total_width = sum(col_widths)
    if total_width > effective_available_width:
        scale_ratio = effective_available_width / total_width
        col_widths = [w * scale_ratio for w in col_widths]
    
    # Create table with calculated widths
    table = Table(data, colWidths=col_widths, repeatRows=1)
    
    # Add style to table
    style = TableStyle([
        # Header row: white background, colored text (smaller font for neatness)
        ('BACKGROUND', (0, 0), (-1, 0), colors.white),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a73e8')),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7 if not fit_all_rows else max(5, font_size - 1)),  # Smaller header font for neatness
        ('BOTTOMPADDING', (0, 0), (-1, 0), cell_padding),
        ('TOPPADDING', (0, 0), (-1, 0), cell_padding),
        # Body: black & white
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), font_size-1 if font_size > 4 else font_size),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        # Subtle alternating greyscale row backgrounds
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        # Use dynamic padding based on fit_all_rows mode
        ('LEFTPADDING', (0, 0), (-1, -1), cell_padding),
        ('RIGHTPADDING', (0, 0), (-1, -1), cell_padding),
        ('BOTTOMPADDING', (0, 1), (-1, -1), cell_padding),
        ('TOPPADDING', (0, 1), (-1, -1), cell_padding),
    ])

    # Align numeric columns to the right
    for ncol in numeric_cols:
        style.add('ALIGN', (ncol, 1), (ncol, -1), 'RIGHT')

    # Highlight the bottom 'Means' row (if present) in red and bold across the entire row
    # Detect by scanning data rows for a cell equal to 'Means'
    for ridx in range(1, len(data)):
        row = data[ridx]
        if any(str(cell).strip().lower() == 'means' for cell in row):
            style.add('TEXTCOLOR', (0, ridx), (-1, ridx), colors.red)
            style.add('FONTNAME', (0, ridx), (-1, ridx), 'Helvetica-Bold')
            style.add('FONTSIZE', (0, ridx), (-1, ridx), font_size)
    
    table.setStyle(style)
    elements.append(table)
    
    # Build PDF
    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes
# Ensure basic session_state keys exist early to avoid AttributeError on first access
if "raw_marks" not in st.session_state:
    st.session_state.raw_marks = pd.DataFrame()
if "history" not in st.session_state:
    st.session_state.history = []
if "redo_stack" not in st.session_state:
    st.session_state.redo_stack = []
# persistent raw marks filename
RAW_MARKS_FILE = "raw_marks_backup.csv"

def load_raw_marks():
    if os.path.exists(RAW_MARKS_FILE):
        try:
            df = pd.read_csv(RAW_MARKS_FILE)
            df.index = range(1, len(df)+1)
            return df
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def save_raw_marks():
    try:
        if not st.session_state.raw_marks.empty:
            st.session_state.raw_marks.to_csv(RAW_MARKS_FILE, index=False)
        else:
            if os.path.exists(RAW_MARKS_FILE):
                os.remove(RAW_MARKS_FILE)
    except Exception as e:
        try:
            st.warning(f"Could not save raw marks: {e}")
        except Exception:
            pass

st.sidebar.markdown("---")
st.sidebar.markdown("")

def apply_css_from_cfg(cfg):
    ff = cfg.get("font_family","Poppins")
    fs = cfg.get("font_size",14)
    fw = cfg.get("font_weight","normal")
    fc = cfg.get("font_color","#111111")
    pc = cfg.get("primary_color","#0E6BA8")
    apply_to = cfg.get("apply_to", ["whole_app"])

    css = "<style>\n"
    if "whole_app" in apply_to:
        css += f"html, body, .stApp {{ font-family: '{ff}', sans-serif !important; color: {fc} !important; }}\n"
        css += f".stApp {{ font-size: {fs}px !important; font-weight: {fw} !important; }}\n"
    else:
        if "table_only" in apply_to:
            css += f"div[data-testid='stDataFrame'] * {{ font-family: '{ff}', sans-serif !important; color: {fc} !important; font-size: {fs}px !important; font-weight: {fw} !important; }}\n"
        if "headers_only" in apply_to:
            css += f"h1,h2,h3,h4,h5,h6 {{ font-family: '{ff}', sans-serif !important; color: {fc} !important; font-weight: {fw} !important; }}\n"
    css += f"h1, h2, h3, .stButton>button {{ color: {pc} !important; }}\n"

    css += """
    /* Force primary buttons to be green */
    button[kind="primary"], button[data-testid="baseButton-primary"] {
        background-color: #28a745 !important;
        color: white !important;
        border-color: #28a745 !important;
    }
    button[kind="primary"]:hover, button[data-testid="baseButton-primary"]:hover {
        background-color: #218838 !important;
        border-color: #1e7e34 !important;
    }
    .settings-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.45); z-index: 9998; display:flex; align-items:center; justify-content:center; }
    .settings-modal { width:520px; background:white; border-radius:8px; padding:16px; box-shadow:0 8px 30px rgba(0,0,0,0.25); z-index:9999; cursor: default; }
    .drag-handle { cursor: grab; padding:6px 8px; background:#f1f1f1; border-radius:6px; margin-bottom:8px; font-weight:600; }
    .print-only { display:none; }
    /* Streamlit main menu & footer restored */
    """
    css += "</style>"
    try:
        st.markdown(css, unsafe_allow_html=True)
    except Exception:
        pass

DEFAULT_CONFIG = {
    "school_name": "Your School",
    "class_name": "Class",
    "exam_name": "Exam",
    "font_family": "Poppins",
    "font_size": 14,
    "font_weight": "normal",
    "font_color": "#111111",
    "primary_color": "#0E6BA8",
    "apply_to": ["whole_app"],
    "input_mode": "paste",
    "combined_subjects": {},
    "grading_enabled": False,
    "grading_system": [
        {"grade": "A", "min": 80, "max": 100},
        {"grade": "B", "min": 70, "max": 79},
        {"grade": "C", "min": 60, "max": 69},
        {"grade": "D", "min": 50, "max": 59},
        {"grade": "E", "min": 0, "max": 49}
    ]
}

APP_CONFIG = "app_persistent_config.json"

def load_config():
    # Prefer per-account config when available (so each signed-in school can have its own defaults)
    try:
        from modules import storage as _storage
        from modules import auth as _auth
        sid = None
        try:
            sid = _auth.get_current_school_id()
        except Exception:
            sid = None
        per_account_dir = _storage.get_storage_dir()
        per_account_cfg = os.path.join(per_account_dir, APP_CONFIG)
        # If a signed-in user exists but per-account config is missing, initialize the account skeleton
        try:
            if sid and not os.path.exists(per_account_cfg):
                try:
                    _storage.initialize_account(sid)
                except Exception:
                    pass
        except Exception:
            pass

        # Try storage adapter per-account key first (handles S3)
        try:
            data = None
            if sid and storage is not None and hasattr(storage, 'read_json'):
                try:
                    data = storage.read_json(f"{sid}/{APP_CONFIG}")
                except Exception:
                    data = None
            # fallback to local per-account file
            if data is None and os.path.exists(per_account_cfg):
                try:
                    with open(per_account_cfg, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = None
            if data is not None:
                for k, v in DEFAULT_CONFIG.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            pass
    except Exception:
        pass

    # Try global config via adapter if available
    try:
        if storage is not None and hasattr(storage, 'read_json'):
            try:
                data = storage.read_json(APP_CONFIG)
                if isinstance(data, dict):
                    for k, v in DEFAULT_CONFIG.items():
                        if k not in data:
                            data[k] = v
                    return data
            except Exception:
                pass
    except Exception:
        pass

    if os.path.exists(APP_CONFIG):
        try:
            with open(APP_CONFIG, "r", encoding="utf-8") as f:
                data = json.load(f)
                # ensure keys
                for k, v in DEFAULT_CONFIG.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        # Prefer per-account storage when signed in
        try:
            sid = None
            try:
                sid = auth.get_current_school_id()
            except Exception:
                sid = None
            if sid and storage is not None and hasattr(storage, 'write_json'):
                try:
                    storage.write_json(f"{sid}/{APP_CONFIG}", cfg)
                    return
                except Exception:
                    pass
        except Exception:
            pass

        # global adapter fallback
        if storage is not None and hasattr(storage, 'write_json'):
            try:
                storage.write_json(APP_CONFIG, cfg)
                return
            except Exception:
                pass

        with open(APP_CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        try:
            st.warning(f"Could not save config: {e}")
        except Exception:
            pass

def get_grade(percentage, grading_system, subject_name=None):
    """Convert percentage to grade based on grading system.
    If subject_name is provided, checks if it should use strict grading."""
    if pd.isna(percentage) or percentage == '':
        return ''
    
    # Check if this subject uses strict grading
    if subject_name and st.session_state.cfg.get('strict_grading_enabled', False):
        strict_subjects = st.session_state.cfg.get('strict_grading_subjects', [])
        if subject_name in strict_subjects:
            grading_system = st.session_state.cfg.get('strict_grading_system', grading_system)
    
    try:
        pct = float(percentage)
        for grade_rule in grading_system:
            # Swap min and max: use max as lower bound, min as upper bound
            if grade_rule['max'] <= pct <= grade_rule['min']:
                return grade_rule['grade']
        return ''
    except (ValueError, TypeError):
        return ''

def get_points(percentage, grading_system, subject_name=None):
    """Convert percentage to points based on grading system.
    If subject_name is provided, checks if it should use strict grading."""
    if pd.isna(percentage) or percentage == '':
        return 0
    
    # Check if this subject uses strict grading
    if subject_name and st.session_state.cfg.get('strict_grading_enabled', False):
        strict_subjects = st.session_state.cfg.get('strict_grading_subjects', [])
        if subject_name in strict_subjects:
            grading_system = st.session_state.cfg.get('strict_grading_system', grading_system)
    
    try:
        pct = float(percentage)
        for grade_rule in grading_system:
            # Swap min and max: use max as lower bound, min as upper bound
            if grade_rule['max'] <= pct <= grade_rule['min']:
                return int(grade_rule.get('points', 0))
        return 0
    except (ValueError, TypeError):
        return 0

# Session initialization
if "cfg" not in st.session_state:
    st.session_state.cfg = load_config()
    # Ensure default ranking basis exists
    if 'ranking_basis' not in st.session_state.cfg:
        st.session_state.cfg['ranking_basis'] = 'Totals'

if "raw_marks" not in st.session_state:
    st.session_state.raw_marks = pd.DataFrame()

if "view" not in st.session_state:
    st.session_state.view = "main"

if "history" not in st.session_state:
    st.session_state.history = []
if "redo_stack" not in st.session_state:
    st.session_state.redo_stack = []

# Initialize saved exam storage structures
if "saved_exams" not in st.session_state:
    # Ensure backing stores exist before we attempt to load from disk
    if "saved_exam_data" not in st.session_state:
        st.session_state.saved_exam_data = {}
    if "saved_exam_raw_data" not in st.session_state:
        st.session_state.saved_exam_raw_data = {}
    if "saved_exam_configs" not in st.session_state:
        st.session_state.saved_exam_configs = {}

    st.session_state.saved_exams = []
    # Load from disk on first initialization
    load_all_exams_from_disk()
# Ensure backing stores exist for data/configs (idempotent)
if "saved_exam_data" not in st.session_state:
    st.session_state.saved_exam_data = {}
if "saved_exam_raw_data" not in st.session_state:
    st.session_state.saved_exam_raw_data = {}
if "saved_exam_configs" not in st.session_state:
    st.session_state.saved_exam_configs = {}

apply_css_from_cfg(st.session_state.cfg)

# Temporary debug display: show where raw data was loaded from (if set)
if st.session_state.get('debug_loaded_info'):
    info = st.session_state.pop('debug_loaded_info')
    try:
        src = info.get('loaded_from')
        rows = info.get('raw_rows', 0)
        sel = info.get('selected_id')
        st.info(f"Debug: selected_id={sel} | loaded_from={src} | rows={rows}")
    except Exception:
        pass

# ---------------------------
# Small helper: push history for undo
# ---------------------------
def push_history():
    try:
        st.session_state.history.append(st.session_state.raw_marks.copy())
        if len(st.session_state.history) > 40:
            st.session_state.history = st.session_state.history[-40:]
        # clear redo
        st.session_state.redo_stack = []
    except Exception:
        pass

def undo():
    if st.session_state.history:
        st.session_state.redo_stack.append(st.session_state.raw_marks.copy())
        st.session_state.raw_marks = st.session_state.history.pop()
        # persist the undone state
        try:
            save_raw_marks()
        except Exception:
            pass

def redo():
    if st.session_state.redo_stack:
        st.session_state.history.append(st.session_state.raw_marks.copy())
        st.session_state.raw_marks = st.session_state.redo_stack.pop()
        try:
            save_raw_marks()
        except Exception:
            pass

# ---------------------------
# Helper: Build export marksheet from raw data
# ---------------------------
def build_export_from_raw(raw_df: pd.DataFrame) -> tuple:
    """Build an export-ready marksheet (students + Totals/Means) from raw dataframe"""
    df_full = raw_df.copy()
    # Remove any columns whose name matches a combined subject name (combined group keys)
    cfg_combined = st.session_state.cfg.get('combined_subjects', {}) or {}
    cfg_combined_names = set([str(k).lower().strip() for k in cfg_combined.keys()])
    cols_to_drop = [c for c in df_full.columns if str(c).lower().strip() in cfg_combined_names]
    if cols_to_drop:
        df_full = df_full.drop(columns=cols_to_drop)
    df_full = df_full.reset_index(drop=True)

    # determine name column
    name_col = None
    for c in df_full.columns:
        if str(c).lower().strip() == 'name':
            name_col = c
            break
    if name_col is None:
        for c in df_full.columns:
            if not pd.api.types.is_numeric_dtype(df_full[c]):
                name_col = c
                break
    if name_col is None:
        return df_full.copy(), list(df_full.columns)

    # identify subject columns (exclude common non-subjects)
    non_subjects = {"admno","adm no","adm_no","name","names","stream","class","term","year","rank","total","mean","form","stream/class","admission number","admission no","admin no","admin number","admno.","adm.no","adm","admission","admin","student name","student names"}
    cols = list(df_full.columns)
    subject_cols = []
    seen_lower = set()
    for c in cols:
        cl = str(c).lower().strip()
        if cl in non_subjects:
            continue
        if cl in seen_lower:
            continue
        subject_cols.append(c)
        seen_lower.add(cl)

    # include combined subjects
    combined_cfg = st.session_state.cfg.get('combined_subjects', {}) or {}
    combined_list = []
    used_lower = set([str(c).lower().strip() for c in subject_cols])
    for cname, parts in combined_cfg.items():
        base = str(cname).strip()
        candidate = base
        suffix = 1
        while candidate.lower().strip() in used_lower:
            candidate = f"{base}_{suffix}"
            suffix += 1
        used_lower.add(candidate.lower().strip())
        combined_list.append((candidate, parts))
    combined_names = [c for c, _ in combined_list]

    marksheet = pd.DataFrame()
    marksheet['Rank'] = ['']*len(df_full)
    for col in df_full.columns:
        col_lower = str(col).lower().strip()
        if col_lower in ['admno','adm no','adm_no','admission number','admission no','admin no','admin number','admno.','adm.no','adm','admission','admin']:
            marksheet['Adm No'] = df_full[col]
        elif col_lower in ['name','names','student name','student names']:
            marksheet['Name'] = df_full[col]
        elif col_lower in ['stream','class','form','stream/class']:
            marksheet['Class'] = df_full[col]

    numeric_cols_for_total = []
    subject_cols_order = []
    combined_parts = set()
    for _, parts in combined_list:
        for p in parts:
            combined_parts.add(p)

    # Get list of subjects to exclude from totals/points
    excluded_subjects = st.session_state.cfg.get('excluded_subjects', [])
    
    grading_enabled = st.session_state.cfg.get('grading_enabled', False)
    grading_system = st.session_state.cfg.get('grading_system', [])

    # Track all percentage values for points calculation
    all_subject_percentages = []
    all_subject_names = []  # Track subject names for points calculation

    for subj in subject_cols:
        try:
            scores = pd.to_numeric(df_full[subj], errors='coerce')
        except Exception:
            scores = pd.Series([pd.NA]*len(df_full))
        out_of = float(st.session_state.cfg.get(f'out_{subj}', 100))
        pct = (scores / out_of) * 100
        
        if subj not in combined_parts:
            # Format with subject-specific grading
            def format_pct_for_subject(pct_value, subject=subj):
                if pd.notna(pct_value):
                    pct_int = int(round(pct_value))
                    if grading_enabled and grading_system:
                        grade = get_grade(pct_int, grading_system, subject)
                        return f"{pct_int} {grade}" if grade else str(pct_int)
                    return str(pct_int)
                return ''
            
            marksheet[subj] = pct.apply(format_pct_for_subject).astype(object)
            
            # Only add to totals if not excluded
            if subj not in excluded_subjects:
                numeric_cols_for_total.append((subj, pct.fillna(0)))
                all_subject_percentages.append(pct)  # Track for points
                all_subject_names.append(subj)  # Track subject name
        else:
            marksheet[subj] = scores.fillna('').astype(object)
        subject_cols_order.append(subj)

    combined_display_cols = []
    for cname, parts in combined_list:
        for p in parts:
            if p not in marksheet.columns:
                try:
                    scores = pd.to_numeric(df_full[p], errors='coerce')
                except Exception:
                    scores = pd.Series([pd.NA]*len(df_full))
                marksheet[p] = scores.fillna('').astype(object)
        total_raw = pd.Series([0]*len(df_full), dtype=float)
        total_out_of = 0.0
        for p in parts:
            scores = pd.to_numeric(df_full.get(p, pd.Series([pd.NA]*len(df_full))), errors='coerce').fillna(0)
            total_raw = total_raw + scores
            total_out_of += float(st.session_state.cfg.get(f'out_{p}', 100))
        combined_pct = (total_raw / total_out_of) * 100 if total_out_of > 0 else pd.Series([pd.NA]*len(df_full))
        combined_header_map = st.session_state.cfg.get('combined_headers', {})
        combined_col_name = combined_header_map.get(cname, f"{cname}_Combined%")
        
        # Format combined subject with its name
        def format_combined_pct(pct_value, combined_name=cname):
            if pd.notna(pct_value):
                pct_int = int(round(pct_value))
                if grading_enabled and grading_system:
                    grade = get_grade(pct_int, grading_system, combined_name)
                    return f"{pct_int} {grade}" if grade else str(pct_int)
                return str(pct_int)
            return ''
        
        marksheet[combined_col_name] = combined_pct.apply(format_combined_pct).astype(object)
        combined_display_cols.append(combined_col_name)
        
        # Only add to totals if not excluded
        if cname not in excluded_subjects:
            numeric_cols_for_total.append((combined_col_name, combined_pct.fillna(0)))
            all_subject_percentages.append(combined_pct)  # Track for points
            all_subject_names.append(cname)  # Track combined subject name

    # Check if we should exclude lowest grade per student
    exclude_lowest = st.session_state.cfg.get('exclude_lowest_grade', False)
    
    # Calculate totals and points
    if exclude_lowest and numeric_cols_for_total:
        # For each student, exclude their lowest scoring subject
        total_numeric = pd.Series([0.0] * len(df_full))
        points_series = pd.Series([0] * len(df_full), dtype=int) if (grading_enabled and grading_system) else None
        
        for idx in range(len(df_full)):
            # Get all subject scores for this student
            subject_scores = []
            for col_name, pct_series in numeric_cols_for_total:
                score = pct_series.iloc[idx]
                if pd.notna(score):
                    subject_scores.append((col_name, score))
            
            # Sort by score and exclude the lowest (if there's a tie, picks the first one)
            if len(subject_scores) > 1:
                subject_scores.sort(key=lambda x: x[1])  # Stable sort: ties keep original order
                subject_scores = subject_scores[1:]  # Remove the lowest scoring subject
            
            # Sum the remaining scores
            student_total = sum(score for _, score in subject_scores)
            total_numeric.iloc[idx] = student_total
            
            # Calculate points for remaining subjects
            if points_series is not None:
                student_points = 0
                for col_name, score in subject_scores:
                    # Find the subject name from our tracking lists
                    for i, (tracked_col, _) in enumerate(numeric_cols_for_total):
                        if tracked_col == col_name and i < len(all_subject_names):
                            subj_name = all_subject_names[i]
                            student_points += get_points(score, grading_system, subj_name)
                            break
                points_series.iloc[idx] = student_points
        
        # Calculate mean based on number of subjects counted (all subjects - 1)
        n_counted = max(1, len(numeric_cols_for_total) - 1) if len(numeric_cols_for_total) > 1 else 1
        mean_numeric = total_numeric / n_counted
    else:
        # Normal calculation (include all subjects)
        total_numeric = None
        for _, s in numeric_cols_for_total:
            if total_numeric is None:
                total_numeric = s.copy()
            else:
                total_numeric = total_numeric + s.fillna(0)
        if total_numeric is None:
            total_numeric = pd.Series([pd.NA] * len(df_full))
        n_single = max(1, len([col for col, _ in numeric_cols_for_total]))
        mean_numeric = (total_numeric / n_single)
        
        # Calculate Points column (sum of points for all subjects)
        if grading_enabled and grading_system and all_subject_percentages:
            points_series = pd.Series([0] * len(marksheet), dtype=int)
            for pct_col, subj_name in zip(all_subject_percentages, all_subject_names):
                subject_points = pct_col.apply(lambda x: get_points(x, grading_system, subj_name))
                points_series = points_series + subject_points
        else:
            points_series = None
    
    def fmt_total(x):
        return int(round(x)) if pd.notna(x) else ''
    def fmt_mean(x):
        return f"{x:.2f}" if pd.notna(x) else ''
    marksheet['Total'] = total_numeric.apply(fmt_total).astype(object)
    marksheet['Mean'] = mean_numeric.apply(fmt_mean).astype(object)
    
    if points_series is not None:
        marksheet['Points'] = points_series.astype(object)
        # Empty for Totals/Means rows
        marksheet.loc[marksheet['Name'].isin(['Totals', 'Means']), 'Points'] = ''
    else:
        marksheet['Points'] = ''

    valid_student_mask = (
        (~marksheet['Name'].isin(['Totals', 'Means'])) &
        (marksheet['Name'].notna()) &
        (marksheet['Name'].astype(str).str.strip() != '')
    )
    # Determine ranking metric: Totals (default) or Points
    ranking_basis = st.session_state.cfg.get('ranking_basis', 'Totals')
    metric_series = None
    if ranking_basis == 'Points' and 'Points' in marksheet.columns:
        try:
            metric_series = pd.to_numeric(marksheet['Points'].replace('', pd.NA), errors='coerce')
        except Exception:
            metric_series = None
    if metric_series is None:
        metric_series = total_numeric

    try:
        ranks_numeric = pd.Series([pd.NA] * len(marksheet))
        valid_metric = metric_series[valid_student_mask]
        ranks_numeric[valid_student_mask] = valid_metric.rank(method='min', ascending=False, na_option='bottom')
    except TypeError:
        ranks_numeric = pd.Series([pd.NA] * len(marksheet))
        valid_metric = metric_series[valid_student_mask]
        ranks_numeric[valid_student_mask] = valid_metric.rank(method='min', ascending=False)
    marksheet['Rank'] = ranks_numeric.apply(lambda x: int(x) if pd.notna(x) else '').astype(object)

    # Calculate Stream Rank (rank within each class/stream)
    marksheet['S/Rank'] = ''
    if 'Class' in marksheet.columns:
        # Group by Class and calculate rank within each group
        for class_val in marksheet['Class'].unique():
            if pd.isna(class_val) or str(class_val).strip() in ['', 'Totals', 'Means']:
                continue
            class_mask = (marksheet['Class'] == class_val) & valid_student_mask
            if class_mask.any():
                # Use same metric for stream ranking
                class_totals = metric_series[class_mask]
                try:
                    class_ranks = class_totals.rank(method='min', ascending=False, na_option='bottom')
                except TypeError:
                    class_ranks = class_totals.rank(method='min', ascending=False)
                # Assign ranks to the class_mask positions
                marksheet.loc[class_mask, 'S/Rank'] = class_ranks.apply(lambda x: int(x) if pd.notna(x) else '').astype(object)
    else:
        # If no Class column, Stream Rank is same as overall Rank
        marksheet['S/Rank'] = marksheet['Rank']

    ordered = ['Rank']
    if 'Adm No' in marksheet.columns:
        ordered.append('Adm No')
    if 'Name' in marksheet.columns:
        ordered.append('Name')
    if 'Class' in marksheet.columns:
        ordered.append('Class')
    insert_map = {}
    for (cname, parts), combined_col in zip(combined_list, combined_display_cols):
        indices = [i for i, s in enumerate(subject_cols_order) if s in parts]
        pos = max(indices) if indices else len(subject_cols_order)-1
        insert_map.setdefault(pos, []).append(combined_col)
    for idx, subj in enumerate(subject_cols_order):
        if subj in marksheet.columns:
            ordered.append(subj)
        if idx in insert_map:
            for cc in insert_map[idx]:
                if cc in marksheet.columns:
                    ordered.append(cc)
    ordered.extend(['Total', 'Mean', 'Points', 'S/Rank'])
    ordered = [c for c in ordered if c in marksheet.columns]
    marksheet = marksheet[ordered]
    student_rows = marksheet[valid_student_mask].copy()
    try:
        student_rows['_RankSort'] = student_rows['Rank'].replace('', pd.NA)
        student_rows['_RankSort'] = pd.to_numeric(student_rows['_RankSort'], errors='coerce').fillna(1e9)
        sort_keys = ['_RankSort']
        if 'Class' in student_rows.columns:
            sort_keys.append('Class')
        if 'Name' in student_rows.columns:
            sort_keys.append('Name')
        student_rows = student_rows.sort_values(by=sort_keys)
        student_rows = student_rows.drop(columns=['_RankSort'])
    except Exception:
        pass
    footer_totals = {'Name': 'Totals', 'Rank': '', 'S/Rank': '', 'Points': ''}
    footer_means = {'Name': 'Means', 'Rank': '', 'S/Rank': '', 'Points': ''}
    if 'Adm No' in marksheet.columns:
        footer_totals['Adm No'] = ''
        footer_means['Adm No'] = ''
    for col in marksheet.columns:
        if col in ('Rank','Name','Adm No','S/Rank','Points'):
            continue
        # Extract numeric values from columns (handle grades like "85 A")
        try:
            # First try to extract numbers from strings (handles "85 A" format)
            col_str = marksheet[col].astype(str).str.strip()
            # Extract first numeric value from each cell
            col_numeric = col_str.str.extract(r'(\d+\.?\d*)')[0]
            col_values = pd.to_numeric(col_numeric, errors='coerce')
        except Exception:
            col_values = pd.Series([pd.NA]*len(marksheet))
        
        # Calculate totals and means (excluding marked students from both)
        if col_values.notna().any():
            # For both totals and means, exclude students from the exclusion list
            excluded_students = st.session_state.cfg.get('excluded_students_from_means', [])
            if excluded_students and 'Name' in df_full.columns:
                # Get student names
                student_names = df_full['Name'].astype(str).str.strip()
                # Create mask for students NOT in exclusion list
                include_mask = ~student_names.isin(excluded_students)
                col_values_for_calc = col_values[include_mask]
            else:
                col_values_for_calc = col_values
            
            if col_values_for_calc.notna().any():
                footer_totals[col] = int(col_values_for_calc.sum(skipna=True))
                footer_means[col] = f"{col_values_for_calc.mean(skipna=True):.2f}"
            else:
                footer_totals[col] = ''
                footer_means[col] = ''
        else:
            footer_totals[col] = ''
            footer_means[col] = ''
    footer_df = pd.DataFrame([footer_totals, footer_means])
    export_df = pd.concat([student_rows.astype(object), footer_df[ordered].astype(object)], ignore_index=True)
    return export_df, ordered

# ---------------------------
# Page layout core
# ---------------------------
st.set_page_config(page_title="EDUSCORE ANALYTICS", layout="wide")
# Build tag to help verify the app reloaded the latest code
BUILD_TAG = "Build: 2025-11-02 12:00"

# If the session was placed into a parents-only mode, do not render the main
# application navigation or sidebar items. This prevents parents from seeing
# other pages when the portal is being used inside the same Streamlit process.
try:
    if st.session_state.get('parents_portal_mode'):
        # remove any existing sidebar widgets and hide main menu/header/footer
        try:
            st.sidebar.empty()
        except Exception:
            pass
        hide = """
        <style>
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
        </style>
        """
        try:
            st.markdown(hide, unsafe_allow_html=True)
        except Exception:
            pass
        # Stop rendering the rest of the main app UI
        st.stop()
except Exception:
    pass

# Sidebar order EXACTLY as requested - no spacing between app name and author

# --- Modern Sidebar Navigation ---

# Top navigation quick selector (includes Authentication as a sidebar file/page)
nav_opts = [
    ('Authentication', 'auth'),
    ("Director's Lounge", 'directors_lounge'),
    # Home is intentionally reachable from the app root; remove duplicate sidebar entry
    ('New Exam', 'new_exam'),
    ('Teacher Analysis', 'teacher_analysis'),
    # Removed additional feature pages per admin preference to keep the UI minimal
    # ('Saved Exams', 'saved_exams'),
    # ('Report Cards', 'report_cards'),
    # ('Student History', 'student_history'),
    # ('Bulk Photo Uploader', 'bulk_photo_uploader')
]
nav_labels = [n for n,_ in nav_opts]
nav_map = {n:k for n,k in nav_opts}
try:
    # The top 'Navigate' selectbox has been removed per user request.
    # Preserve logic that determines the current page label without rendering UI.
    default_label = None
    cur = st.session_state.get('current_page', 'home')
    for lbl, key in nav_opts:
        if key == cur:
            default_label = lbl
            break
    # Keep existing session value; no sidebar selector shown to the user.
    st.session_state.show_home_header = (cur == 'home')
except Exception:
    pass

# Saved exams dropdown (appears above school name)
# Filter to show only current year's exams
from datetime import datetime
current_year = datetime.now().year
all_saved = st.session_state.get('saved_exams', []) or []
saved_list = [e for e in all_saved if e.get('year') == current_year]
if saved_list:
    st.sidebar.markdown("### Saved Exams")
    
    # Check if there are unsaved changes that should block the dropdown
    should_disable_dropdown = False
    current_id = st.session_state.get('selected_saved_exam_id')
    
    # Check for unsaved changes in main view (editing raw data)
    if st.session_state.get('view') != 'analysis' and not st.session_state.raw_marks.empty:
        if current_id is None:
            # User has fresh unsaved data
            should_disable_dropdown = True
            st.session_state['exam_save_confirmed'] = False
            st.sidebar.warning("💾 Save your data first to access saved exams")
        elif st.session_state.get('exam_save_confirmed', False):
            should_disable_dropdown = False
        elif current_id in st.session_state.get('saved_exam_raw_data', {}):
            # Check if editing a saved exam with changes
            saved_raw = st.session_state.saved_exam_raw_data[current_id]
            current_raw = st.session_state.raw_marks
            try:
                has_changes = not saved_raw.equals(current_raw)
                if has_changes:
                    should_disable_dropdown = True
                    st.session_state['exam_save_confirmed'] = False
                    st.sidebar.warning("💾 Update current exam before switching")
                else:
                    should_disable_dropdown = False
                    st.session_state['exam_save_confirmed'] = True
            except:
                pass
    
    # Check for any unsaved work that blocks dropdown
    has_unsaved_work = False
    
    # Check 1: Unsaved changes in analysis view (generated but not saved)
    if st.session_state.get('view') == 'analysis' and st.session_state.get('rebuild_from_raw'):
        has_unsaved_work = True
    
    # Check 2: Save dialog is open (confirming save details)
    if st.session_state.get('pending_save_friendly_name'):
        has_unsaved_work = True
    
    # Check 3: Explicit unsaved exam flag (set when generating, cleared only on actual save)
    if st.session_state.get('has_unsaved_exam', False):
        has_unsaved_work = True
    
    # Disable dropdown if any unsaved work exists

    # Only enable dropdown if save is confirmed
    if has_unsaved_work or not st.session_state.get('exam_save_confirmed', False):
        should_disable_dropdown = True
        st.sidebar.warning("💾 Save your exam before switching")
    
    labels = ["📋 Paste New Exam"] + [f"{e.get('exam_name','(unnamed)')}" for e in saved_list]
    # Keep a parallel list of ids with a None for the placeholder
    ids = [None] + [e.get('exam_id') for e in saved_list]
    # Determine current selection index if any
    try:
        default_idx = ids.index(current_id) if current_id in ids else 0
    except ValueError:
        default_idx = 0
    
    sel_label = st.sidebar.selectbox(
        "Load a saved exam", 
        options=labels, 
        index=default_idx, 
        key="saved_exam_select",
        disabled=should_disable_dropdown
    )
    
    # Only process selection change if dropdown is enabled
    if not should_disable_dropdown:
        # Map back to id by index
        try:
            new_id = ids[labels.index(sel_label)]
        except ValueError:
            new_id = None
        
        if new_id != current_id:
            st.session_state['selected_saved_exam_id'] = new_id
            st.session_state.rebuild_from_raw = False  # Clear rebuild flag when selecting saved exam
            # If selecting a saved exam, switch to Analysis view automatically
            if new_id:
                # Update class/exam display using metadata when available
                match = next((e for e in saved_list if e.get('exam_id') == new_id), None)
                if match:
                    if match.get('class_name'):
                        st.session_state.cfg['class_name'] = match.get('class_name')
                    # Set exam_name to saved friendly name so titles show it
                    if match.get('exam_name'):
                        st.session_state.cfg['exam_name'] = match.get('exam_name')
                
                # Restore saved config (out_of values and combined_subjects)
                if 'saved_exam_configs' in st.session_state and new_id in st.session_state.saved_exam_configs:
                    saved_config = st.session_state.saved_exam_configs[new_id]
                    # Restore out_of values
                    for key, value in saved_config.items():
                        if key.startswith('out_'):
                            st.session_state.cfg[key] = value
                    # Restore combined_subjects
                    if 'combined_subjects' in saved_config:
                        st.session_state.cfg['combined_subjects'] = saved_config['combined_subjects']
                    # Restore grading system configuration
                    if 'grading_enabled' in saved_config:
                        st.session_state.cfg['grading_enabled'] = saved_config['grading_enabled']
                    if 'grading_system' in saved_config:
                        st.session_state.cfg['grading_system'] = saved_config['grading_system']
                    if 'strict_grading_enabled' in saved_config:
                        st.session_state.cfg['strict_grading_enabled'] = saved_config['strict_grading_enabled']
                    if 'strict_grading_system' in saved_config:
                        st.session_state.cfg['strict_grading_system'] = saved_config['strict_grading_system']
                    if 'strict_grading_subjects' in saved_config:
                        st.session_state.cfg['strict_grading_subjects'] = saved_config['strict_grading_subjects']
                    # Restore excluded subjects configuration
                    if 'excluded_subjects' in saved_config:
                        st.session_state.cfg['excluded_subjects'] = saved_config['excluded_subjects']
                    else:
                        st.session_state.cfg['excluded_subjects'] = []
                    # Restore exclude lowest grade configuration
                    if 'exclude_lowest_grade' in saved_config:
                        st.session_state.cfg['exclude_lowest_grade'] = saved_config['exclude_lowest_grade']
                    else:
                        st.session_state.cfg['exclude_lowest_grade'] = False
                    # Restore excluded students from means
                    if 'excluded_students_from_means' in saved_config:
                        st.session_state.cfg['excluded_students_from_means'] = saved_config['excluded_students_from_means']
                    else:
                        st.session_state.cfg['excluded_students_from_means'] = []
                    # Restore ranking basis
                    if 'ranking_basis' in saved_config:
                        st.session_state.cfg['ranking_basis'] = saved_config['ranking_basis']
                    else:
                        st.session_state.cfg['ranking_basis'] = 'Totals'
                
                # Persist the updated config so the sidebar inputs reflect the change
                save_config(st.session_state.cfg)
                st.session_state.view = 'analysis'
            else:
                # Paste New Exam selected - clear data and go to entry view
                st.session_state.raw_marks = pd.DataFrame()  # Clear raw marks
                st.session_state.cfg['class_name'] = ''  # Clear class name
                st.session_state.cfg['exam_name'] = 'Exam Name'  # Reset exam name
                save_config(st.session_state.cfg)
                st.session_state.view = 'entry'  # Go to raw sheet page
            st.rerun()

# School name, class and exam (persistent)
# Use unique widget keys and sync with cfg
if 'school_name_widget' not in st.session_state:
    # default widget value should be empty for new accounts; cfg may contain per-account values
    st.session_state.school_name_widget = st.session_state.cfg.get("school_name", "")
if 'class_name_widget' not in st.session_state:
    st.session_state.class_name_widget = st.session_state.cfg.get("class_name","Class")
if 'exam_name_widget' not in st.session_state:
    st.session_state.exam_name_widget = st.session_state.cfg.get("exam_name","Exam")
if 'term_widget' not in st.session_state:
    st.session_state.term_widget = st.session_state.cfg.get("term","")

# Update widget values when config changes (e.g., from saved exam selection)
if st.session_state.cfg.get("school_name") != st.session_state.get("school_name_widget"):
    st.session_state.school_name_widget = st.session_state.cfg.get("school_name","Your School")
if st.session_state.cfg.get("class_name") != st.session_state.get("class_name_widget"):
    st.session_state.class_name_widget = st.session_state.cfg.get("class_name","Class")
if st.session_state.cfg.get("exam_name") != st.session_state.get("exam_name_widget"):
    st.session_state.exam_name_widget = st.session_state.cfg.get("exam_name","Exam")
if st.session_state.cfg.get("term") != st.session_state.get("term_widget"):
    st.session_state.term_widget = st.session_state.cfg.get("term","")

# Use a user-scoped key so duplicate widget keys across pages/sessions don't collide
uid_key = st.session_state.get('user_uid') or 'guest'
school_widget_key = f"school_name_{uid_key}"
school_input = st.sidebar.text_input("School Name", value=st.session_state.school_name_widget, key=school_widget_key)

# Only show Class/Stream and Exam Name when NOT viewing a saved exam
viewing_saved_exam = st.session_state.get('selected_saved_exam_id') is not None
if not viewing_saved_exam:
    class_input = st.sidebar.text_input(
        "Class / Stream (optional)", 
        value=st.session_state.class_name_widget if st.session_state.class_name_widget != "Class" else "", 
        key="class_name",
        placeholder="Leave empty or enter class name"
    )
    exam_input = st.sidebar.text_input("Exam Name", value=st.session_state.exam_name_widget, key="exam_name")
    term_input = st.sidebar.text_input("Term (optional)", value=st.session_state.term_widget if st.session_state.term_widget else "", key="term_input", placeholder="e.g. Opener, Mid Term, End Term")
else:
    # Keep the values in sync but don't show the inputs
    class_input = st.session_state.cfg.get("class_name", "")
    exam_input = st.session_state.cfg.get("exam_name", "Exam")
    term_input = st.session_state.cfg.get("term", "")

# Save when edited (persist permanently)
if (school_input != st.session_state.cfg.get("school_name") or
    class_input != st.session_state.cfg.get("class_name") or
    exam_input != st.session_state.cfg.get("exam_name")):
    st.session_state.cfg["school_name"] = school_input
    st.session_state.cfg["class_name"] = class_input
    st.session_state.cfg["exam_name"] = exam_input
    st.session_state.cfg["term"] = term_input
    st.session_state.school_name_widget = school_input
    st.session_state.class_name_widget = class_input
    st.session_state.exam_name_widget = exam_input
    st.session_state.term_widget = term_input
    save_config(st.session_state.cfg)

st.sidebar.markdown("---")
# Input mode selection (single choice; toggles visible UI)
input_mode = st.sidebar.radio("Input mode", ("Paste Raw Marks","Manual Entry"))
# remember selection
selected_mode = "paste" if input_mode == "Paste Raw Marks" else "manual"
if st.session_state.cfg.get("input_mode") != selected_mode:
    st.session_state.cfg["input_mode"] = selected_mode
    save_config(st.session_state.cfg)

# Buttons area (below) - simplified
st.sidebar.markdown("#### Actions")
selected_saved_id = st.session_state.get('selected_saved_exam_id')
show_update_generate = selected_saved_id and selected_saved_id in st.session_state.get('saved_exam_data', {})
if not show_update_generate:
    if st.sidebar.button("Generate Marksheet", key="generate_marksheet_sidebar", type="primary"):
        st.session_state.view = "analysis"
        st.rerun()

selected_saved_id = st.session_state.get('selected_saved_exam_id')
if selected_saved_id and selected_saved_id in st.session_state.get('saved_exam_data', {}):
    pass
st.sidebar.markdown("### Actions")

# If editing a saved exam, show combined "Update & Generate" button
selected_saved_id = st.session_state.get('selected_saved_exam_id')
if selected_saved_id and selected_saved_id in st.session_state.get('saved_exam_data', {}):
    if st.sidebar.button("💾 Update & Generate", type="primary"):
        if not st.session_state.raw_marks.empty:
            try:
                from datetime import datetime
                # Build the full export from current raw marks
                full_export_df, _ord = build_export_from_raw(st.session_state.raw_marks)
                
                # Save current config (out_of values and combined_subjects)
                config_to_save = {}
                for key, value in st.session_state.cfg.items():
                    if key.startswith('out_'):
                        config_to_save[key] = value
                config_to_save['combined_subjects'] = st.session_state.cfg.get('combined_subjects', {})
                
                # Update the saved exam data
                st.session_state.saved_exam_data[selected_saved_id] = full_export_df.copy()
                st.session_state.saved_exam_raw_data[selected_saved_id] = st.session_state.raw_marks.copy()
                if 'saved_exam_configs' not in st.session_state:
                    st.session_state.saved_exam_configs = {}
                st.session_state.saved_exam_configs[selected_saved_id] = config_to_save.copy()
                
                # Update metadata
                for exam_meta in st.session_state.saved_exams:
                    if exam_meta.get('exam_id') == selected_saved_id:
                        exam_meta['date_saved'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                        exam_meta['total_students'] = int(len(full_export_df) - 2) if len(full_export_df) >= 2 else int(len(full_export_df))
                        exam_meta['num_subjects'] = int(len([c for c in full_export_df.columns if c not in ['Rank','Adm No','Name','Class','Total','Mean']]))
                        break
                # Now switch to analysis view
                push_history()
                st.session_state.rebuild_from_raw = False  # Load the saved exam we just updated
                st.session_state.view = "analysis"
                st.sidebar.success("✓ Exam updated!")
                st.rerun()

            except Exception as e:
                pass

# Sidebar Settings (expander) - replaces modal popup
with st.sidebar.expander("Settings", expanded=False):
    families = ["Poppins", "Roboto", "Arial", "Verdana", "Times New Roman", "Courier New"]
    current = st.session_state.cfg
    fam_idx = families.index(current.get("font_family","Poppins")) if current.get("font_family") in families else 0
    fam = st.selectbox("Font Family", families, index=fam_idx)
    fsize = st.slider("Font Size (px)", 10, 30, int(current.get("font_size",14)))
    fw = st.radio("Font Weight", ["normal","500","bold"], index=["normal","500","bold"].index(str(current.get("font_weight","normal"))))
    fcolor = st.color_picker("Font Color", value=current.get("font_color","#111111"))
    pcolor = st.color_picker("Primary Color", value=current.get("primary_color","#0E6BA8"))

    colA, colB, colC = st.columns(3)
    with colA:
        whole_cb = st.checkbox("Apply to Whole App", value=("whole_app" in current.get("apply_to",["whole_app"])))
    with colB:
        table_cb = st.checkbox("Apply to Table Only", value=("table_only" in current.get("apply_to",[])))
    with colC:
        headers_cb = st.checkbox("Apply to Headers Only", value=("headers_only" in current.get("apply_to",[])))

    col1, col2 = st.columns([1,1])
    if col1.button("Restore Default"):
        st.session_state.cfg = DEFAULT_CONFIG.copy()
        save_config(st.session_state.cfg)
        apply_css_from_cfg(st.session_state.cfg)
        st.rerun()
    if col2.button("Save Settings"):
        new_apply = []
        if whole_cb: new_apply.append("whole_app")
        if table_cb: new_apply.append("table_only")
        if headers_cb: new_apply.append("headers_only")
        if not new_apply:
            new_apply = ["whole_app"]
        st.session_state.cfg.update({
            "font_family": fam,
            "font_size": fsize,
            "font_weight": fw,
            "font_color": fcolor,
            "primary_color": pcolor,
            "apply_to": new_apply
        })
        save_config(st.session_state.cfg)
        apply_css_from_cfg(st.session_state.cfg)
        st.success("Settings saved.")

st.sidebar.markdown("---")
st.sidebar.markdown("")

# ---------------------------
# SETTINGS MODAL (draggable)
# ---------------------------
if st.session_state.get("show_settings_modal"):
    placeholder = st.empty()
    with placeholder.container():
        st.markdown("<div class='settings-overlay'>", unsafe_allow_html=True)
        st.markdown("<div class='settings-modal' id='settingsModal'>", unsafe_allow_html=True)

        # Use a form to collect settings to avoid partial rerun issues
        with st.form(key="settings_form"):
            families = ["Poppins", "Roboto", "Arial", "Verdana", "Times New Roman", "Courier New"]
            current = st.session_state.cfg
            fam_idx = families.index(current.get("font_family","Poppins")) if current.get("font_family") in families else 0
            fam = st.selectbox("Font Family", families, index=fam_idx)
            fsize = st.slider("Font Size (px)", 10, 30, int(current.get("font_size",14)))
            fw = st.radio("Font Weight", ["normal","500","bold"], index=["normal","500","bold"].index(str(current.get("font_weight","normal"))))
            fcolor = st.color_picker("Font Color", value=current.get("font_color","#111111"))
            pcolor = st.color_picker("Primary Color", value=current.get("primary_color","#0E6BA8"))

            colA, colB, colC = st.columns(3)
            with colA:
                whole_cb = st.checkbox("Apply to Whole App", value=("whole_app" in current.get("apply_to",["whole_app"])))
            with colB:
                table_cb = st.checkbox("Apply to Table Only", value=("table_only" in current.get("apply_to",[])))
            with colC:
                headers_cb = st.checkbox("Apply to Headers Only", value=("headers_only" in current.get("apply_to",[])))

            st.markdown("---")
            col1, col2, col3 = st.columns([1,1,1])
            with col1:
                restore = st.form_submit_button("Restore Default")
            with col2:
                cancel = st.form_submit_button("Cancel")
            with col3:
                save = st.form_submit_button("Save")

        st.markdown("</div></div>", unsafe_allow_html=True)

        # React to form buttons
        if restore:
            st.session_state.cfg = DEFAULT_CONFIG.copy()
            save_config(st.session_state.cfg)
            apply_css_from_cfg(st.session_state.cfg)
            st.session_state.show_settings_modal = False
            placeholder.empty()
            st.rerun()
        elif cancel:
            st.session_state.show_settings_modal = False
            placeholder.empty()
            st.rerun()
        elif save:
            new_apply = []
            if whole_cb: new_apply.append("whole_app")
            if table_cb: new_apply.append("table_only")
            if headers_cb: new_apply.append("headers_only")
            if not new_apply:
                new_apply = ["whole_app"]
            st.session_state.cfg.update({
                "font_family": fam,
                "font_size": fsize,
                "font_weight": fw,
                "font_color": fcolor,
                "primary_color": pcolor,
                "apply_to": new_apply
            })
            save_config(st.session_state.cfg)
            apply_css_from_cfg(st.session_state.cfg)
            st.success("Settings saved.")
            st.session_state.show_settings_modal = False
            placeholder.empty()
            st.rerun()

# ---------------------------
# VIEW: Preview page (same tab) or Main page
# ---------------------------
if st.session_state.view == "preview":
    # --- PREVIEW PAGE: show only table with school/class header and print controls ---
    st.markdown("<div style='display:flex; justify-content:space-between; align-items:center;'>", unsafe_allow_html=True)
    st.markdown(f"<div></div>", unsafe_allow_html=True)
    if st.button("⬅ Back to Raw Sheet"):
        st.session_state.view = "main"
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # Display school and class from config (non-editable)
    school = st.session_state.cfg.get("school_name", "Your School")
    cls = st.session_state.cfg.get("class_name", "Class")
    
    st.markdown(f"""
        <div class='school-header'>
            <h2 style='text-align:center; color:{st.session_state.cfg.get('primary_color','#0E6BA8')}; margin-bottom:4px;'>{school.upper()}</h2>
            <h4 style='text-align:center; color:gray; margin-top:0px;'>{cls}</h4>
            <hr>
        </div>
    """, unsafe_allow_html=True)

    # prepare preview dataframe (optionally allow filtering by class/stream column)
    # Hide any combined-group-name columns from preview
    df_preview = st.session_state.raw_marks.copy()
    cfg_combined_preview = st.session_state.cfg.get('combined_subjects', {}) or {}
    cfg_combined_preview_names = set([str(k).lower().strip() for k in cfg_combined_preview.keys()])
    preview_cols_to_drop = [c for c in df_preview.columns if str(c).lower().strip() in cfg_combined_preview_names]
    if preview_cols_to_drop:
        df_preview = df_preview.drop(columns=preview_cols_to_drop)
    if df_preview.empty:
        st.warning("No data to preview. Return and populate the raw mark sheet first.")
    else:
        # allow user to pick which column is the stream/class column (so they can filter to a specific class)
        st.markdown("*Select stream/class column (optional)* — pick column that identifies student's class/stream, then choose value to print for only that class.")
        col_choices = [None] + list(df_preview.columns)
        stream_col = st.selectbox("Stream/Class column", options=col_choices, index=0)
        if stream_col:
            values = sorted(df_preview[stream_col].dropna().astype(str).unique().tolist())
            values.insert(0, "ALL")
            chosen_val = st.selectbox("Select class/stream to preview (ALL shows everyone)", options=values, index=0)
            if chosen_val != "ALL":
                df_show = df_preview[df_preview[stream_col].astype(str) == chosen_val]
            else:
                df_show = df_preview.copy()
        else:
            df_show = df_preview.copy()

        # controls for page scaling / column width / rows per page (approximate page breaks)
        c1, c2 = st.columns([1,1])
        with c1:
            orientation = st.selectbox("Orientation", ["Portrait","Landscape"])
        with c2:
            scale = st.slider("Scale (%)", 50, 120, 107)
            
        # Page estimation directly below scaling
        fit_all_preview = st.checkbox("Fit all rows on one page", value=False, key="preview_fit_all")
        if not fit_all_preview:
            rows_per_page = st.number_input("Rows per page (approx)", min_value=5, max_value=200, value=20)
        else:
            rows_per_page = 999  # Large number to fit all rows
        # Calculate and show page estimate immediately
        total_rows = len(df_show)
        if not fit_all_preview:
            pages_est = (total_rows + rows_per_page - 1) // rows_per_page
            st.markdown(f"*Estimated pages:* {pages_est} (based on {rows_per_page} rows per page)")
        else:
            st.markdown(f"*All {total_rows} rows will fit on one page*")

        # show table only (non-editable here)
        # Add print-optimized table styles
        table_css = f"""
        <style>
        .preview-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 1em;
            font-family: {st.session_state.cfg.get('font_family', 'Arial')};
        }}
        .preview-table th, .preview-table td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }}
        .preview-table th {{
            background-color: {st.session_state.cfg.get('primary_color','#0E6BA8')}20;
        }}
        @media print {{
            .preview-table {{ page-break-inside: auto; }}
            .preview-table tr {{ page-break-inside: avoid; page-break-after: auto; }}
            .preview-table thead {{ display: table-header-group; }}
        }}
        </style>
        """
        st.markdown(table_css, unsafe_allow_html=True)
        
        st.markdown("### Preview table (non-editable)")
        # Convert DataFrame to paginated HTML tables with page-break markers
        def build_paginated_tables_html(df, rows_per_page):
            # Format numeric columns to remove decimal places
            df_formatted = df.copy()
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    df_formatted[col] = df[col].apply(lambda x: f"{int(x)}" if pd.notnull(x) and float(x).is_integer() else x)
            
            if rows_per_page <= 0:
                return df_formatted.to_html(classes='preview-table', index=False)
            parts = []
            total = len(df_formatted)
            for start in range(0, total, rows_per_page):
                chunk = df_formatted.iloc[start:start+rows_per_page]
                html = chunk.to_html(classes='preview-table', index=False)
                if start > 0:
                    # insert a visible dashed separator representing page break
                    parts.append("<div style='width:100%; border-top:3px dashed #c0392b; margin:8px 0; text-align:center; color:#c0392b;'>-- Page break --</div>")
                parts.append(html)
            return '\n'.join(parts)

        table_html = build_paginated_tables_html(df_show, int(rows_per_page))
        st.markdown(table_html, unsafe_allow_html=True)
        
        # show page count estimate
        total_rows = len(df_show)
        pages_est = (total_rows + rows_per_page - 1) // rows_per_page
        st.markdown(f"*Estimated pages:* {pages_est} (based on {rows_per_page} rows per page)")

        # Download PDF action: generate a strict PDF document (server-side)
        if not df_show.empty:
            st.markdown("#### Download PDF of this view")
            try:
                title = f"{st.session_state.cfg.get('exam_name','Exam')} - CORRECTIONS SHEET"
                pdf_bytes = df_to_pdf_bytes(df_show, st.session_state.cfg.get('school_name','Your School'), st.session_state.cfg.get('class_name','Class'), title, orientation=orientation, scale=scale, fit_all_rows=fit_all_preview)
                pdf_filename = f"{st.session_state.cfg.get('school_name','School')}_RawMarks.pdf"
                st.download_button('⬇ Download PDF (Raw Sheet)', data=pdf_bytes, file_name=pdf_filename, mime='application/pdf')
            except Exception as e:
                st.error(f"Could not generate PDF (install reportlab): {e}")
                st.info("Install reportlab: pip install reportlab and refresh the app")
            

    # footer
    st.markdown(
        "<div style='text-align:center; font-size:12px; margin-top:18px;'>"
        "Thank you for choosing <b>Eduscore Analytics</b><br>"
        "For more of our services contact us on: <b>0793975959</b>"
        "</div>",
        unsafe_allow_html=True
    )

# ---------------------------
# GENERATED SHEET VIEW: Marksheet generation (students, percentages, combined subjects, ranking)
# ---------------------------
elif st.session_state.view == "analysis":
    # Helper: Build an export-ready marksheet (students + Totals/Means) from a full raw dataframe
    def _build_export_from_raw(raw_df: pd.DataFrame) -> tuple:
        """Local wrapper for the global build_export_from_raw function"""
        return build_export_from_raw(raw_df)
    
    # Add sticky Back button with high visibility
    st.markdown("""
        <style>
        .back-button-container {
            position: fixed;
            top: 70px;
            right: 20px;
            z-index: 999;
        }
        .back-button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            font-weight: 700;
            font-size: 16px;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
            text-decoration: none;
            display: inline-block;
            transition: all 0.3s ease;
        }
        .back-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(102, 126, 234, 0.6);
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Add sidebar branding
    st.sidebar.markdown("<div style='text-align:center; font-weight:900; font-size:16px; margin-bottom:0; padding-bottom:0;'>EDUSCORE ANALYTICS</div>", unsafe_allow_html=True)
    st.sidebar.markdown("<div style='text-align:center; color:gray; font-weight:600; margin-top:0; padding-top:0;'>by Munyua Kamau</div>", unsafe_allow_html=True)
    st.sidebar.markdown("---")
    
    # Main content header
    st.markdown(f"""
        <div style='text-align:center'>
            <h2 style='color:{st.session_state.cfg.get("primary_color","#0E6BA8")};'>Generated Marksheet</h2>
            <h4 style='color:gray; margin: 0'>{st.session_state.cfg.get('school_name')}</h4>
            <div style='color:gray; font-size: 0.95rem;'>Class: {st.session_state.cfg.get('class_name')} &nbsp; | &nbsp; Exam: {st.session_state.cfg.get('exam_name')}</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Back to Raw Sheet button - green for visibility
    if st.button("⬅ Back to Raw Sheet", type="primary", key="back_to_raw_analysis", help="Return to the raw data sheet"):
        # Check if we're viewing a saved exam
        selected_id = st.session_state.get('selected_saved_exam_id')
        if selected_id and 'saved_exam_raw_data' in st.session_state and selected_id in st.session_state.saved_exam_raw_data:
            # Load the raw data for this saved exam
            st.session_state.raw_marks = st.session_state.saved_exam_raw_data[selected_id].copy()
            st.success("Loaded raw data for editing. Click 'Generate Marksheet' when ready.")
        # Don't clear selected_saved_exam_id so we can update the same exam
        st.session_state.view = 'main'
        st.rerun()
    
    # Controls section as popover - overlays instead of pushing content down
    with st.popover("⚙️ Marksheet Controls", use_container_width=True):
        grading_enabled_local = st.session_state.cfg.get('grading_enabled', False)
        # Ranking Basis Selection (always visible; disabled if grading off)
        st.markdown("#### Ranking Basis")
        current_basis = st.session_state.cfg.get('ranking_basis', 'Totals')
        if not grading_enabled_local:
            # Force totals and show disabled control
            if current_basis != 'Totals':
                st.session_state.cfg['ranking_basis'] = 'Totals'
                save_config(st.session_state.cfg)
            try:
                basis = st.radio(
                    "Rank students by:",
                    options=["Totals", "Points"],
                    index=0,
                    horizontal=True,
                    key="ranking_basis_selector",
                    disabled=True
                )
            except TypeError:
                # Fallback if Streamlit version lacks disabled param: show static text instead
                st.write("Totals  |  Points (locked)")
        else:
            basis = st.radio(
                "Rank students by:",
                options=["Totals", "Points"],
                index=0 if current_basis not in ["Totals","Points"] else ["Totals","Points"].index(current_basis),
                horizontal=True,
                key="ranking_basis_selector"
            )
            if basis != current_basis:
                st.session_state.cfg['ranking_basis'] = basis
                save_config(st.session_state.cfg)
                # Force rebuild so ranks immediately recalc using new basis
                st.session_state.rebuild_from_raw = True
                st.info(f"Ranking now uses {basis}; regenerating sheet…")
                st.rerun()
        st.markdown("---")
        # Combined subject header editor
        combined_cfg = st.session_state.cfg.get('combined_subjects', {}) or {}
        if combined_cfg:
            st.markdown("#### Edit Combined Subject Column Headers")
            st.markdown("*Rename how combined subjects appear in the marksheet columns*")
            combined_header_map = st.session_state.cfg.get('combined_headers', {})
            updated_headers = {}
            
            for cname in combined_cfg.keys():
                default_header = combined_header_map.get(cname, f"{cname}_Combined%")
                col1, col2 = st.columns([3, 1])
                with col1:
                    new_header = st.text_input(f"Column header for '{cname}':", value=default_header, key=f"header_{cname}")
                    updated_headers[cname] = new_header
                with col2:
                    st.markdown("<div style='padding-top: 1.8rem;'></div>", unsafe_allow_html=True)
                    if st.button("💾", key=f"save_header_{cname}"):
                        st.session_state.cfg['combined_headers'] = updated_headers
                        save_config(st.session_state.cfg)
                        st.success(f"Saved header: {new_header}")
                        st.rerun()
            st.markdown("---")
        
        # Print/Export settings
        st.markdown("#### Print & Export Settings")
        pcol1, pcol2, pcol3 = st.columns(3)
        with pcol1:
            orientation = st.selectbox("Page Orientation", ["Portrait", "Landscape"], key="analysis_orientation")
        with pcol2:
            scale = st.slider("Scale (%)", 50, 120, 107, key="analysis_scale")
        with pcol3:
            fit_all = st.checkbox("Fit all rows on one page", value=False, key="analysis_fit_all")
            if not fit_all:
                rows_per_page = st.number_input("Rows per page", min_value=5, max_value=200, value=20, key="analysis_rows")
            else:
                rows_per_page = 999  # Large number to fit all rows
        
        st.markdown("---")
        # Total Column Scaling
        st.markdown("#### Total Column Scaling")
        st.markdown("*Convert the Total column to a different scale (e.g., 500 marks)*")
        scale_col1, scale_col2 = st.columns([1, 1])
        with scale_col1:
            enable_cross = st.checkbox("📊 Enable Total scaling", key="enable_total_cross_multiply")
        with scale_col2:
            if enable_cross:
                target_total = st.number_input("Target total:", min_value=1, max_value=10000, value=500, step=50, key="target_total_value")
        
        st.markdown("---")
        # Grading System
        st.markdown("#### Grading System")
        st.markdown("*Show grades alongside marks (e.g., 85 → 85 (A))*")
        grading_enabled = st.checkbox("📝 Enable Grading", value=st.session_state.cfg.get('grading_enabled', False), key="grading_enabled")
        
        if grading_enabled:
            st.markdown("**Edit Grade Bands (table)**")
            grading_system = st.session_state.cfg.get('grading_system', [
                {"grade": "A", "min": 100, "max": 80},
                {"grade": "B", "min": 79, "max": 70},
                {"grade": "C", "min": 69, "max": 60},
                {"grade": "D", "min": 59, "max": 50},
                {"grade": "E", "min": 49, "max": 0}
            ])

            # Build an editable table view: Grade | Min % (upper bound) | Max % (lower bound) | Points
            import pandas as _pd
            table_df = _pd.DataFrame([
                {"Grade": r.get("grade",""), "Min %": int(r.get("min", 0)), "Max %": int(r.get("max", 0)), "Points": int(r.get("points", 12))}
                for r in grading_system
            ])

            # Column configurations for better UX
            col_cfg = {
                "Grade": st.column_config.TextColumn(
                    "Grade",
                    help="Grade label e.g., A, A-, B+",
                    width="small",
                    required=True,
                ),
                "Min %": st.column_config.NumberColumn(
                    "Max %",
                    help="Upper bound of the range",
                    min_value=0,
                    max_value=100,
                    step=1,
                    format="%d",
                ),
                "Max %": st.column_config.NumberColumn(
                    "Min %",
                    help="Lower bound of the range",
                    min_value=0,
                    max_value=100,
                    step=1,
                    format="%d",
                ),
                "Points": st.column_config.NumberColumn(
                    "Points",
                    help="Points awarded for this grade",
                    min_value=0,
                    max_value=100,
                    step=1,
                    format="%d",
                ),
            }

            st.caption("Tip: Add/remove rows directly in the table. Min is the upper bound; Max is the lower bound. Assign points for each grade.")
            edited_df = st.data_editor(
                table_df,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                column_config=col_cfg,
                key="grading_table_editor",
            )

            bcol1, bcol2, bcol3 = st.columns([1,1,2])
            with bcol1:
                if st.button("Sort by Max % ⬇", key="sort_grades_by_max"):
                    try:
                        edited_df = edited_df.sort_values(by=["Max %", "Min %"], ascending=[False, False])
                    except Exception:
                        pass
            with bcol2:
                reset_default = st.button("Reset to Defaults", key="reset_grades_default")
            if reset_default:
                # Simple 5-band default in current semantics with points (12,10,8,6,4)
                edited_df = _pd.DataFrame([
                    {"Grade":"A","Min %":100,"Max %":80,"Points":12},
                    {"Grade":"B","Min %":79,"Max %":70,"Points":10},
                    {"Grade":"C","Min %":69,"Max %":60,"Points":8},
                    {"Grade":"D","Min %":59,"Max %":50,"Points":6},
                    {"Grade":"E","Min %":49,"Max %":0,"Points":4},
                ])
                st.session_state["grading_table_editor"] = edited_df

            # Validate & Save
            save_col1, save_col2 = st.columns([1,3])
            with save_col1:
                do_save_grades = st.button("💾 Save Grading System", key="save_grading_table")
            with save_col2:
                st.caption("We’ll validate ranges (0-100) and ensure Max ≤ Min. Rows with empty Grade are ignored.")

            if do_save_grades:
                # Clean and validate
                cleaned = []
                warnings = []
                try:
                    tmp_df = edited_df.copy()
                except Exception:
                    tmp_df = table_df.copy()

                for _, row in tmp_df.iterrows():
                    g = str(row.get("Grade", "")).strip()
                    if not g:
                        continue
                    try:
                        lower = int(row.get("Max %", 0))
                    except Exception:
                        lower = 0
                    try:
                        upper = int(row.get("Min %", 0))
                    except Exception:
                        upper = 0
                    try:
                        pts = int(row.get("Points", 0))
                    except Exception:
                        pts = 0

                    # Clamp to 0-100
                    lower = max(0, min(100, lower))
                    upper = max(0, min(100, upper))
                    pts = max(0, pts)

                    # Ensure lower <= upper (Max % <= Min % under our semantics)
                    if lower > upper:
                        # Auto-fix by swapping
                        lower, upper = upper, lower
                        warnings.append(f"Swapped bounds for grade {g} to keep Max ≤ Min.")

                    cleaned.append({"grade": g, "max": lower, "min": upper, "points": pts})

                # Sort by lower bound descending by default
                try:
                    cleaned = sorted(cleaned, key=lambda r: (r["max"], r["min"]), reverse=True)
                except Exception:
                    pass

                if warnings:
                    for w in warnings:
                        st.warning(w)

                st.session_state.cfg['grading_system'] = cleaned
                st.session_state.cfg['grading_enabled'] = True
                save_config(st.session_state.cfg)
                st.success("Grading system saved!")
                st.rerun()
            
            # Subject-specific grading system override
            st.markdown("---")
            st.markdown("**📚 Strict Grading for Specific Subjects**")
            st.caption("Some subjects may require stricter grading. Define a stricter scale below and assign subjects to it.")
            
            # Check if strict grading system exists
            strict_enabled = st.checkbox("Enable Strict Grading for Selected Subjects", 
                                        value=st.session_state.cfg.get('strict_grading_enabled', False), 
                                        key="strict_grading_checkbox")
            
            if strict_enabled:
                # Load or create strict grading system
                strict_system = st.session_state.cfg.get('strict_grading_system', [
                    {"grade": "A", "min": 100, "max": 90, "points": 12},
                    {"grade": "B", "min": 89, "max": 80, "points": 10},
                    {"grade": "C", "min": 79, "max": 70, "points": 8},
                    {"grade": "D", "min": 69, "max": 60, "points": 6},
                    {"grade": "E", "min": 59, "max": 0, "points": 4},
                ])
                
                st.markdown("**Strict Grading Scale:**")
                strict_df = _pd.DataFrame([
                    {"Grade": r.get("grade",""), "Min %": int(r.get("min", 0)), "Max %": int(r.get("max", 0)), "Points": int(r.get("points", 12))}
                    for r in strict_system
                ])
                
                edited_strict_df = st.data_editor(
                    strict_df,
                    use_container_width=True,
                    hide_index=True,
                    num_rows="dynamic",
                    column_config=col_cfg,
                    key="strict_grading_table_editor",
                )
                
                # Subject assignment
                st.markdown("**Assign Subjects to Strict Grading:**")
                # Get subjects from the current raw marks sheet
                all_subjects = []
                if not st.session_state.raw_marks.empty:
                    # Get columns from raw marks, excluding common non-subject columns
                    non_subjects = {"admno","adm no","adm_no","name","names","stream","class","term","year","rank","total","mean"}
                    # Get combined subjects parts to exclude them
                    combined_cfg = st.session_state.cfg.get('combined_subjects', {}) or {}
                    combined_parts = set()
                    for parts_list in combined_cfg.values():
                        for part in parts_list:
                            combined_parts.add(part)
                    
                    # Add individual subjects (exclude combined parts and non-subjects)
                    for col in st.session_state.raw_marks.columns:
                        col_lower = str(col).lower().strip()
                        if col_lower not in non_subjects and col not in combined_parts:
                            all_subjects.append(col)
                    
                    # Add combined subject names (not their parts)
                    for combined_name in combined_cfg.keys():
                        all_subjects.append(combined_name)
                else:
                    # Fallback to config keys if no raw marks loaded
                    for key in st.session_state.cfg.keys():
                        if key.startswith('out_') and key != 'out_NAMES':
                            subj = key[4:]  # Remove 'out_' prefix
                            all_subjects.append(subj)
                
                strict_subjects = st.session_state.cfg.get('strict_grading_subjects', [])
                # Filter strict_subjects to only include subjects currently in the sheet
                valid_strict = [s for s in strict_subjects if s in all_subjects]
                
                if all_subjects:
                    selected_strict = st.multiselect(
                        "Select subjects that use strict grading:",
                        options=sorted(all_subjects),
                        default=valid_strict,
                        key="strict_subject_selector"
                    )
                else:
                    st.info("No subjects found in raw marks sheet. Load exam data first.")
                    selected_strict = []
                
                # Save strict grading
                scol1, scol2 = st.columns([1,3])
                with scol1:
                    if st.button("💾 Save Strict Grading", key="save_strict_grading"):
                        # Clean and validate strict system
                        strict_cleaned = []
                        try:
                            tmp_strict = edited_strict_df.copy()
                        except Exception:
                            tmp_strict = strict_df.copy()
                        
                        for _, row in tmp_strict.iterrows():
                            g = str(row.get("Grade", "")).strip()
                            if not g:
                                continue
                            try:
                                lower = int(row.get("Max %", 0))
                                upper = int(row.get("Min %", 0))
                                pts = int(row.get("Points", 0))
                            except Exception:
                                lower, upper, pts = 0, 0, 0
                            
                            lower = max(0, min(100, lower))
                            upper = max(0, min(100, upper))
                            pts = max(0, pts)
                            
                            if lower > upper:
                                lower, upper = upper, lower
                            
                            strict_cleaned.append({"grade": g, "max": lower, "min": upper, "points": pts})
                        
                        st.session_state.cfg['strict_grading_enabled'] = True
                        st.session_state.cfg['strict_grading_system'] = strict_cleaned
                        st.session_state.cfg['strict_grading_subjects'] = selected_strict
                        save_config(st.session_state.cfg)
                        st.success(f"Strict grading saved for {len(selected_strict)} subjects!")
                        st.rerun()
                with scol2:
                    st.caption(f"{len(selected_strict)} subject(s) will use strict grading")
            else:
                # Disable strict grading
                if st.session_state.cfg.get('strict_grading_enabled', False):
                    st.session_state.cfg['strict_grading_enabled'] = False
                    save_config(st.session_state.cfg)
        
        else:
            # Save disabled state
            if st.session_state.cfg.get('grading_enabled', False):
                st.session_state.cfg['grading_enabled'] = False
                save_config(st.session_state.cfg)
        
        st.markdown("---")
        
        # Exclude Subjects from Totals/Points
        st.markdown("### 🚫 Exclude Subjects from Totals & Points")
        
        # Get subjects from current raw marks sheet (similar to strict grading)
        exclude_all_subjects = []
        if not st.session_state.raw_marks.empty:
            non_subjects = {"admno","adm no","adm_no","name","names","stream","class","term","year","rank","total","mean"}
            # Get combined subjects parts to exclude them
            combined_cfg = st.session_state.cfg.get('combined_subjects', {}) or {}
            combined_parts = set()
            for parts_list in combined_cfg.values():
                for part in parts_list:
                    combined_parts.add(part)
            
            # Add individual subjects (exclude combined parts and non-subjects)
            for col in st.session_state.raw_marks.columns:
                col_lower = str(col).lower().strip()
                if col_lower not in non_subjects and col not in combined_parts:
                    exclude_all_subjects.append(col)
            
            # Add combined subject names (not their parts)
            for combined_name in combined_cfg.keys():
                exclude_all_subjects.append(combined_name)
        else:
            # Fallback to config keys if no raw marks loaded
            for key in st.session_state.cfg.keys():
                if key.startswith('out_') and key != 'out_NAMES':
                    subj = key[4:]  # Remove 'out_' prefix
                    exclude_all_subjects.append(subj)
        
        # Button to open exclusion dialog
        if st.button("⚙️ Configure Subject Exclusions", key="open_exclusion_dialog", use_container_width=True):
            st.session_state.show_exclusion_dialog = True
        
        # Show current exclusion status
        excluded_subjects = st.session_state.cfg.get('excluded_subjects', [])
        exclude_lowest = st.session_state.cfg.get('exclude_lowest_grade', False)
        
        status_parts = []
        if exclude_lowest:
            status_parts.append("✓ Excluding lowest grade per student")
        if excluded_subjects:
            status_parts.append(f"✓ {len(excluded_subjects)} subject(s) manually excluded")
        
        if status_parts:
            st.info(" • ".join(status_parts))
        else:
            st.caption("No exclusions configured. All subjects count toward Total & Points.")
        
        # Exclusion Dialog (Popup Overlay)
        if st.session_state.get('show_exclusion_dialog', False):
            # Create overlay effect
            st.markdown("""
                <style>
                .exclusion-overlay {
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background: rgba(0,0,0,0.5);
                    z-index: 9998;
                    pointer-events: all;
                }
                .exclusion-dialog {
                    position: fixed;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                    background: white;
                    border-radius: 12px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.3);
                    padding: 24px;
                    max-width: 600px;
                    width: 90%;
                    max-height: 80vh;
                    overflow-y: auto;
                    z-index: 9999;
                }
                .dialog-title {
                    font-size: 22px;
                    font-weight: 600;
                    margin-bottom: 16px;
                    color: #1f2937;
                }
                .dialog-section {
                    margin: 16px 0;
                    padding: 12px;
                    background: #f9fafb;
                    border-radius: 8px;
                }
                </style>
            """, unsafe_allow_html=True)
            
            with st.container():
                st.markdown('<div class="exclusion-overlay"></div>', unsafe_allow_html=True)
                
                # Dialog content
                st.markdown("### ⚙️ Configure Subject Exclusions")
                st.caption("Choose how to exclude subjects from Total and Points calculations")
                
                st.markdown("---")
                
                # Option 1: Exclude lowest grade per student
                st.markdown("#### 📉 Automatic Exclusion")
                exclude_lowest_option = st.checkbox(
                    "Exclude each student's lowest performing subject",
                    value=st.session_state.cfg.get('exclude_lowest_grade', False),
                    key="exclude_lowest_checkbox",
                    help="Automatically drops the worst subject score for each student when calculating totals"
                )
                
                if exclude_lowest_option:
                    st.success("✓ The lowest scoring subject will be excluded for each student")
                
                st.markdown("---")
                
                # Option 2: Manual subject exclusion
                st.markdown("#### 📝 Manual Exclusion")
                st.caption("Select specific subjects to exclude for ALL students")
                
                valid_excluded = [s for s in excluded_subjects if s in exclude_all_subjects]
                
                if exclude_all_subjects:
                    selected_excluded = st.multiselect(
                        "Select subjects to exclude:",
                        options=sorted(exclude_all_subjects),
                        default=valid_excluded,
                        key="exclude_subjects_dialog_selector",
                        help="These subjects will be excluded from totals for all students"
                    )
                else:
                    st.info("No subjects found. Load exam data first.")
                    selected_excluded = []
                
                st.markdown("---")
                
                # Action buttons
                col1, col2, col3 = st.columns([1, 1, 1])
                
                with col1:
                    if st.button("💾 Save", key="save_exclusion_dialog", use_container_width=True):
                        st.session_state.cfg['exclude_lowest_grade'] = exclude_lowest_option
                        st.session_state.cfg['excluded_subjects'] = selected_excluded
                        save_config(st.session_state.cfg)
                        st.session_state.show_exclusion_dialog = False
                        st.success("Exclusion settings saved!")
                        st.rerun()
                
                with col2:
                    if st.button("🔄 Reset", key="reset_exclusion_dialog", use_container_width=True):
                        st.session_state.cfg['exclude_lowest_grade'] = False
                        st.session_state.cfg['excluded_subjects'] = []
                        save_config(st.session_state.cfg)
                        st.session_state.show_exclusion_dialog = False
                        st.success("Reset to default (no exclusions)")
                        st.rerun()
                
                with col3:
                    if st.button("✖ Cancel", key="cancel_exclusion_dialog", use_container_width=True):
                        st.session_state.show_exclusion_dialog = False
                        st.rerun()
        
        st.markdown("---")
        
        # Exclude Students from Means
        st.markdown("### 👥 Exclude Students from Totals & Means")
        st.caption("Select students who should not be included in Totals and Means calculations")
        
        # Get list of students from raw marks
        student_list = []
        if not st.session_state.raw_marks.empty:
            name_col = None
            for col in st.session_state.raw_marks.columns:
                if str(col).lower().strip() in ['name', 'names', 'student', 'student name']:
                    name_col = col
                    break
            
            if name_col:
                students_data = st.session_state.raw_marks[name_col].dropna()
                # Filter out Totals/Means if they accidentally got in
                students_data = students_data[~students_data.astype(str).str.strip().isin(['Totals', 'Means', '', 'Total', 'Mean'])]
                student_list = students_data.astype(str).str.strip().tolist()
        
        # Get currently excluded students
        excluded_students = st.session_state.cfg.get('excluded_students_from_means', [])
        # Filter to only include students currently in the sheet
        valid_excluded_students = [s for s in excluded_students if s in student_list]
        
        if student_list:
            st.markdown(f"**{len(student_list)} students** found in current exam")
            
            selected_excluded_students = st.multiselect(
                "Select students to exclude:",
                options=sorted(student_list),
                default=valid_excluded_students,
                key="exclude_students_means_selector",
                help="These students will appear in the marksheet but won't be counted in Totals or Means footer rows"
            )
            
            excol1, excol2 = st.columns([1, 3])
            with excol1:
                if st.button("💾 Save Student Exclusions", key="save_excluded_students_means"):
                    # Explicitly save even if empty list
                    st.session_state.cfg['excluded_students_from_means'] = list(selected_excluded_students) if selected_excluded_students else []
                    save_config(st.session_state.cfg)
                    if selected_excluded_students:
                        st.success(f"Excluded {len(selected_excluded_students)} student(s)!")
                    else:
                        st.success("All students included in calculations!")
                    st.rerun()
            with excol2:
                if selected_excluded_students:
                    st.caption(f"⚠️ {len(selected_excluded_students)} student(s) excluded from Totals & Means")
                else:
                    st.caption("✓ All students included")
        else:
            st.info("No students found. Load exam data first.")
        
        st.markdown("---")
        # Placeholder for PDF column selection - will be filled after data processing
        download_placeholder = st.empty()

    # Check if we should rebuild from raw marks or load saved exam
    # If rebuild_from_raw flag is set, prioritize rebuilding from raw_marks
    rebuild_from_raw = st.session_state.get('rebuild_from_raw', False)
    selected_id = st.session_state.get('selected_saved_exam_id')
    
    # Check if we need to rebuild due to ranking basis change
    # If viewing a saved exam and raw data exists, check if ranking basis differs from saved config
    if selected_id and not rebuild_from_raw:
        saved_config = st.session_state.saved_exam_configs.get(selected_id, {})
        current_ranking_basis = st.session_state.cfg.get('ranking_basis', 'Totals')
        saved_ranking_basis = saved_config.get('ranking_basis', 'Totals')
        
        # If ranking basis changed and we have raw data, force rebuild
        if current_ranking_basis != saved_ranking_basis and selected_id in st.session_state.saved_exam_raw_data:
            rebuild_from_raw = True
    
    # If a saved exam is selected AND we're not explicitly rebuilding, render saved exam
    if selected_id and 'saved_exam_data' in st.session_state and selected_id in st.session_state.saved_exam_data and not rebuild_from_raw:
        saved_df = st.session_state.saved_exam_data[selected_id].copy()
        
        # If user wants Points but Points are missing/empty in saved sheet, rebuild from raw to compute Points
        current_basis_check = st.session_state.cfg.get('ranking_basis', 'Totals')
        if current_basis_check == 'Points':
            needs_points = ('Points' not in saved_df.columns)
            if not needs_points:
                try:
                    pts_numeric = pd.to_numeric(saved_df['Points'].replace('', pd.NA), errors='coerce')
                    needs_points = pts_numeric.isna().all()
                except Exception:
                    needs_points = True
            if needs_points and selected_id in st.session_state.get('saved_exam_raw_data', {}):
                st.session_state.rebuild_from_raw = True
                st.rerun()

        # Recompute Rank and S/Rank according to current ranking basis (Totals/Points)
        name_col_check = next((c for c in saved_df.columns if str(c).lower().strip() == 'name'), None)
        if name_col_check is not None:
            valid_mask = (
                (~saved_df[name_col_check].astype(str).str.strip().isin(['Totals', 'Means'])) &
                (saved_df[name_col_check].notna()) &
                (saved_df[name_col_check].astype(str).str.strip() != '')
            )
            # Choose metric
            ranking_basis = st.session_state.cfg.get('ranking_basis', 'Totals')
            metric_series = None
            if ranking_basis == 'Points' and 'Points' in saved_df.columns:
                try:
                    metric_series = pd.to_numeric(saved_df['Points'].replace('', pd.NA), errors='coerce')
                except Exception:
                    metric_series = None
            if metric_series is None:
                # fallback to Total
                total_numeric = pd.to_numeric(saved_df.get('Total', pd.Series([pd.NA]*len(saved_df))).replace('', pd.NA), errors='coerce')
                metric_series = total_numeric

            # Overall Rank
            try:
                ranks_numeric = pd.Series([pd.NA] * len(saved_df))
                valid_metric = metric_series[valid_mask]
                ranks_numeric[valid_mask] = valid_metric.rank(method='min', ascending=False, na_option='bottom')
            except TypeError:
                ranks_numeric = pd.Series([pd.NA] * len(saved_df))
                valid_metric = metric_series[valid_mask]
                ranks_numeric[valid_mask] = valid_metric.rank(method='min', ascending=False)
            saved_df['Rank'] = ranks_numeric.apply(lambda x: int(x) if pd.notna(x) else '').astype(object)

            # Stream Rank
            saved_df['S/Rank'] = ''
            class_col = next((c for c in saved_df.columns if str(c).lower().strip() in ['class','stream','form','stream/class']), None)
            if class_col is not None:
                for class_val in saved_df[class_col].unique():
                    if pd.isna(class_val) or str(class_val).strip() in ['', 'Totals', 'Means']:
                        continue
                    class_mask = (saved_df[class_col] == class_val) & valid_mask
                    if class_mask.any():
                        class_vals = metric_series[class_mask]
                        try:
                            class_ranks = class_vals.rank(method='min', ascending=False, na_option='bottom')
                        except TypeError:
                            class_ranks = class_vals.rank(method='min', ascending=False)
                        saved_df.loc[class_mask, 'S/Rank'] = class_ranks.apply(lambda x: int(x) if pd.notna(x) else '').astype(object)
            else:
                saved_df['S/Rank'] = saved_df['Rank']
        
        # Determine ordered columns
        ordered = list(saved_df.columns)

        # Split student rows and footer (Totals/Means)
        name_col = next((c for c in saved_df.columns if str(c).lower().strip() == 'name'), None)
        if name_col is not None:
            is_footer = saved_df[name_col].astype(str).str.strip().isin(['Totals', 'Means'])
            footer_df = saved_df[is_footer].copy()
            student_rows = saved_df[~is_footer].copy()
            if footer_df.shape[0] < 2 and saved_df.shape[0] >= 2:
                footer_df = saved_df.tail(2)
        else:
            footer_df = saved_df.tail(2)
            student_rows = saved_df.iloc[:-2].copy() if saved_df.shape[0] > 2 else saved_df.copy()

        # Build and apply stream/class filter for saved exams as well
        stream_col = next((c for c in saved_df.columns if str(c).lower().strip() in ['class','stream','form','stream/class']), None)
        if stream_col is not None:
            import unicodedata, re
            def norm_key(x: str):
                s = unicodedata.normalize('NFKC', str(x))
                s = re.sub(r"\s+", "", s)
                s = re.sub(r"[^0-9A-Za-z]", "", s)
                return s.upper()

            # Build labels/keys from saved student rows
            sr = student_rows.copy()
            sr['_stream_key'] = sr[stream_col].astype(str).apply(norm_key)
            orig_trim = sr[stream_col].astype(str).str.strip()
            display_map = {}
            counts = {}
            for k, v in zip(sr['_stream_key'], orig_trim):
                if not k:
                    continue
                if k not in display_map:
                    display_map[k] = v
                counts[k] = counts.get(k, 0) + 1
            labeled_keys = sorted(display_map.keys(), key=lambda x: display_map[x])
            labels = ["ALL"] + [f"{display_map[k]} ({counts.get(k,0)})" for k in labeled_keys]
            keys = [None] + labeled_keys

            # Persist labels/keys for UI and selection (UI will render below table)
            st.session_state['analysis_filter_labels'] = labels
            st.session_state['analysis_filter_keys'] = keys

            # Apply current selection (no UI yet, render it below table)
            sel_key = st.session_state.get('analysis_stream_key')
            if sel_key:
                sr = sr[sr['_stream_key'] == sel_key].drop(columns=['_stream_key']).reset_index(drop=True)
                
                # Recalculate ranks for this stream only (1 to N with ties)
                if 'Total' in sr.columns and len(sr) > 0:
                    try:
                        # Get total values as numeric
                        stream_totals = pd.to_numeric(sr['Total'].replace('', pd.NA), errors='coerce')
                        # Calculate ranks for this stream (competition ranking with ties)
                        stream_ranks = stream_totals.rank(method='min', ascending=False, na_option='bottom')
                        # Update the Rank column
                        sr['Rank'] = stream_ranks.apply(lambda x: int(x) if pd.notna(x) else '').astype(object)
                    except Exception:
                        pass
            else:
                sr = sr.drop(columns=['_stream_key'])
            student_rows = sr

        # Recalculate footer (Totals/Means) based on currently filtered student_rows
        footer_totals = {'Name': 'Totals', 'Rank': '', 'S/Rank': '', 'Points': ''}
        footer_means = {'Name': 'Means', 'Rank': '', 'S/Rank': '', 'Points': ''}
        if 'Adm No' in ordered:
            footer_totals['Adm No'] = ''
            footer_means['Adm No'] = ''
        for col in ordered:
            if col in ('Rank','Name','Adm No','S/Rank','Points'):
                continue
            # Extract numeric values from columns (handle grades like "85 A")
            try:
                # First try to extract numbers from strings (handles "85 A" format)
                col_str = student_rows[col].astype(str).str.strip()
                # Extract first numeric value from each cell
                col_numeric = col_str.str.extract(r'(\d+\.?\d*)')[0]
                col_values = pd.to_numeric(col_numeric, errors='coerce')
            except Exception:
                col_values = pd.Series([pd.NA]*len(student_rows))
            
            # Calculate totals and means (excluding marked students from both)
            if col_values.notna().any():
                # For both totals and means, exclude students from the exclusion list
                excluded_students = st.session_state.cfg.get('excluded_students_from_means', [])
                if excluded_students and 'Name' in student_rows.columns:
                    # Get student names
                    student_names = student_rows['Name'].astype(str).str.strip()
                    # Create mask for students NOT in exclusion list
                    include_mask = ~student_names.isin(excluded_students)
                    col_values_for_calc = col_values[include_mask]
                else:
                    col_values_for_calc = col_values
                
                if col_values_for_calc.notna().any():
                    footer_totals[col] = int(col_values_for_calc.sum(skipna=True))
                    footer_means[col] = f"{col_values_for_calc.mean(skipna=True):.2f}"
                else:
                    footer_totals[col] = ''
                    footer_means[col] = ''
            else:
                footer_totals[col] = ''
                footer_means[col] = ''
        footer_df = pd.DataFrame([footer_totals, footer_means])

        # Export df is exactly the saved df
        export_df = saved_df

        # ---- Shared rendering: downloads, table, summary ----
        st.markdown("---")
        st.markdown("### 📥 Download Marksheet")

        # Initialize column selection
        saved_selection = st.session_state.get("pdf_columns_selected", ordered)
        selected_cols = [c for c in ordered if c in saved_selection]

        # Page estimate (based on current filtered rows + footer)
        try:
            total_rows = len(student_rows) + max(0, len(footer_df))
            pages_est = (total_rows + rows_per_page - 1) // rows_per_page
            st.success(f"📄 Estimated pages: **{pages_est}** (based on {rows_per_page} rows per page)")
        except Exception:
            pass

        # Excel and PDF buttons
        from io import BytesIO
        excel_buffer = BytesIO()
        export_subset = pd.concat([student_rows.astype(object), footer_df.astype(object)], ignore_index=True)
        export_subset.to_excel(excel_buffer, index=False, engine='openpyxl')
        excel_data = excel_buffer.getvalue()
        excel_filename = f"{st.session_state.cfg.get('school_name')}_Marksheet.xlsx"

        dcol1, dcol2 = st.columns(2)
        with dcol1:
            st.download_button("⬇ Download Excel", data=excel_data, file_name=excel_filename,
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
        with dcol2:
            try:
                # Use default stream label fallback as overall
                title = f"{st.session_state.cfg.get('exam_name','Exam')}"
                chosen_orientation = 'portrait' if orientation == 'Portrait' else 'landscape'
                export_pdf_df = export_subset[selected_cols]
                pdf_bytes = df_to_pdf_bytes(
                    export_pdf_df,
                    st.session_state.cfg.get('school_name','Your School'),
                    st.session_state.cfg.get('class_name','Class'),
                    title,
                    orientation=chosen_orientation,
                    scale=scale,
                    font_size=9,
                    fit_all_rows=fit_all
                )
                pdf_filename = f"{st.session_state.cfg.get('school_name')}_Marksheet.pdf"
                st.download_button('⬇ Download PDF', data=pdf_bytes, file_name=pdf_filename, mime='application/pdf',
                                   use_container_width=True, disabled=(len(selected_cols)==0))
            except Exception as e:
                st.error(f"PDF error: {e}")

        st.markdown("---")
        
        # Show banner indicating current saved exam with prominent styling
        try:
            meta = next((e for e in st.session_state.get('saved_exams', []) if e.get('exam_id') == selected_id), None)
            if meta:
                exam_display_name = meta.get('exam_name','(unnamed)')
                
                # Banner and Edit button in columns
                banner_col, edit_col = st.columns([4, 1])
                
                with banner_col:
                    st.markdown(f"""
                        <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                    color: white; 
                                    padding: 1.2rem 2rem; 
                                    border-radius: 12px; 
                                    margin-bottom: 1.5rem;
                                    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
                                    text-align: center;'>
                            <div style='font-size: 0.9rem; font-weight: 600; opacity: 0.9; margin-bottom: 0.3rem;'>📂 VIEWING SAVED EXAM</div>
                            <div style='font-size: 1.4rem; font-weight: 800; letter-spacing: 0.5px;'>{exam_display_name}</div>
                            <div style='font-size: 0.85rem; opacity: 0.85; margin-top: 0.3rem;'>Saved on: {meta.get('date_saved','N/A')} • {meta.get('total_students',0)} students</div>
                        </div>
                    """, unsafe_allow_html=True)
                
                with edit_col:
                    st.markdown("<div style='padding-top: 1.5rem;'></div>", unsafe_allow_html=True)
                    if st.button("✏️ Edit Raw Data", key="edit_saved_exam_raw", use_container_width=True):
                        # Load raw data back and switch to entry view
                        if 'saved_exam_raw_data' in st.session_state and selected_id in st.session_state.saved_exam_raw_data:
                            st.session_state.raw_marks = st.session_state.saved_exam_raw_data[selected_id].copy()
                            
                            # Restore saved config (out_of values and combined_subjects)
                            if 'saved_exam_configs' in st.session_state and selected_id in st.session_state.saved_exam_configs:
                                saved_config = st.session_state.saved_exam_configs[selected_id]
                                # Restore out_of values
                                for key, value in saved_config.items():
                                    if key.startswith('out_'):
                                        st.session_state.cfg[key] = value
                                # Restore combined_subjects
                                if 'combined_subjects' in saved_config:
                                    st.session_state.cfg['combined_subjects'] = saved_config['combined_subjects']
                                # Persist config
                                save_config(st.session_state.cfg)
                            
                            # Keep the selected exam ID so "Update & Generate" will work
                            # st.session_state.selected_saved_exam_id stays as selected_id
                            st.session_state.view = 'entry'
                            st.success("Raw data loaded! You can now edit and regenerate the marksheet.")
                            st.rerun()
                        else:
                            st.error("Raw data not available for this exam.")
                    
                    # Delete button with confirmation
                    if st.button("🗑️ Delete", key="delete_saved_exam", type="secondary", use_container_width=True):
                        st.session_state.pending_delete_exam_id = selected_id
                        st.rerun()
                
                # Show confirmation dialog if delete is pending
                if st.session_state.get('pending_delete_exam_id') == selected_id:
                    st.warning("⚠️ **Are you sure you want to delete this exam?**")
                    st.markdown(f"**{exam_display_name}** will be permanently removed from memory.")
                    del1, del2, del3 = st.columns([1, 1, 2])
                    with del1:
                        if st.button("✅ Yes, delete", key="confirm_delete_exam"):
                            try:
                                # Remove from all storage structures
                                st.session_state.saved_exams = [e for e in st.session_state.saved_exams if e.get('exam_id') != selected_id]
                                st.session_state.saved_exam_data.pop(selected_id, None)
                                st.session_state.saved_exam_raw_data.pop(selected_id, None)
                                st.session_state.selected_saved_exam_id = None
                                st.session_state.pop('pending_delete_exam_id', None)
                                st.session_state.view = 'entry'
                                st.success(f"Deleted '{exam_display_name}'")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error deleting exam: {e}")
                    with del2:
                        if st.button("✖ Cancel", key="cancel_delete_exam"):
                            st.session_state.pop('pending_delete_exam_id', None)
                            st.rerun()
        except Exception:
            pass
        
        st.markdown("### Marksheet (percentages)")
        
        # Apply cross multiplication if enabled (from controls)
        display_student_rows_saved = student_rows.copy()
        if enable_cross and 'Total' in display_student_rows_saved.columns:
            try:
                # Get current total numeric values
                total_vals_saved = pd.to_numeric(display_student_rows_saved['Total'].replace('', pd.NA), errors='coerce')
                # Find the maximum total to determine current scale
                max_total_saved = total_vals_saved.max()
                if pd.notna(max_total_saved) and max_total_saved > 0:
                    # Cross multiply: (current_total / max_total) * target_total
                    cross_multiplied_saved = (total_vals_saved / max_total_saved) * target_total
                    # Update Total column with cross-multiplied values (as integers)
                    display_student_rows_saved['Total'] = cross_multiplied_saved.apply(lambda x: int(round(x)) if pd.notna(x) else '').astype(object)
                    st.info(f"📊 Total scaled from 0-{int(max_total_saved)} to 0-{target_total}")
            except Exception as e:
                st.error(f"Error converting Total: {e}")
        
        st.dataframe(display_student_rows_saved.astype(object), use_container_width=True, hide_index=True)

        # Render stream filter UI BELOW the marksheet table
        if stream_col is not None and 'analysis_filter_labels' in st.session_state:
            labels = st.session_state.get('analysis_filter_labels', ['ALL'])
            keys = st.session_state.get('analysis_filter_keys', [None])
            current_key = st.session_state.get('analysis_stream_key')
            try:
                default_index = keys.index(current_key) if current_key in keys else 0
            except ValueError:
                default_index = 0
            st.markdown("---")
            f1, f2 = st.columns([1,3])
            with f1:
                st.markdown("**Filter:**")
            with f2:
                sel_label = st.selectbox("Class/Stream", options=labels, index=default_index,
                                         key='analysis_stream_filter_ui_saved', label_visibility='collapsed')
            try:
                new_key = keys[labels.index(sel_label)]
            except ValueError:
                new_key = None
            if new_key != st.session_state.get('analysis_stream_key'):
                st.session_state['analysis_stream_key'] = new_key
                st.rerun()

        # Column selection inside placeholder (shared UI)
        with download_placeholder.container():
            st.markdown("#### Columns to include in PDF")
            if "pdf_columns_selected" not in st.session_state:
                st.session_state["pdf_columns_selected"] = ordered
            with st.form(key="pdf_column_selector_form_saved"):
                st.markdown("**Select columns:**")
                btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
                select_all = btn_col1.form_submit_button("✅ All")
                deselect_all = btn_col2.form_submit_button("❌ None")
                core_only = btn_col3.form_submit_button("📌 Core")
                subjects_only = btn_col4.form_submit_button("📚 Subjects")
                if select_all:
                    st.session_state["pdf_columns_selected"] = ordered.copy()
                elif deselect_all:
                    st.session_state["pdf_columns_selected"] = []
                elif core_only:
                    core_cols = ['Rank', 'Adm No', 'Name', 'Class', 'Total', 'Mean']
                    st.session_state["pdf_columns_selected"] = [c for c in ordered if c in core_cols]
                elif subjects_only:
                    skip_cols = ['Rank', 'Adm No', 'Name', 'Class', 'Total', 'Mean']
                    st.session_state["pdf_columns_selected"] = [c for c in ordered if c not in skip_cols]
                current_selection = st.session_state.get("pdf_columns_selected", ordered)
                num_cols = 3
                cols_per_row = st.columns(num_cols)
                selected_cols_tmp = []
                for idx, col in enumerate(ordered):
                    col_idx = idx % num_cols
                    is_checked = col in current_selection
                    if cols_per_row[col_idx].checkbox(col, value=is_checked, key=f"pdf_col_saved_{col}"):
                        selected_cols_tmp.append(col)
                submitted = st.form_submit_button("💾 Apply Selection", type="primary")
                if submitted:
                    st.session_state["pdf_columns_selected"] = selected_cols_tmp if selected_cols_tmp else ordered
            current_selection = st.session_state.get("pdf_columns_selected", ordered)
            st.caption(f"✓ {len(current_selection)} of {len(ordered)} columns selected")

        # Summary statistics from footer
        st.markdown("### 📊 Summary Statistics")
        
        # Determine which stream is being shown for saved exams
        stream_display = "OVERALL"
        if stream_col is not None and 'analysis_filter_labels' in st.session_state:
            sel_key = st.session_state.get('analysis_stream_key')
            labels = st.session_state.get('analysis_filter_labels', ['ALL'])
            keys = st.session_state.get('analysis_filter_keys', [None])
            try:
                idx = keys.index(sel_key)
                selected_label = labels[idx]
            except (ValueError, IndexError):
                selected_label = 'ALL'
            if selected_label and selected_label != 'ALL':
                # Strip count suffix " (n)" for display
                stream_display = selected_label.rsplit(" (", 1)[0]
        
        try:
            means_row = None
            if name_col is not None:
                m = footer_df[footer_df[name_col].astype(str).str.strip().str.lower() == 'means']
                if not m.empty:
                    means_row = m.iloc[0]
            if means_row is None:
                means_row = footer_df.iloc[-1]
        except Exception:
            means_row = footer_df.iloc[-1] if not footer_df.empty else None

        if means_row is not None:
            overall_mean = means_row.get('Total', '')
            if overall_mean:
                st.markdown(
                    f"""
                    <div style='text-align:center; padding: 1rem 0; margin-bottom: 1.5rem;'>
                        <div style='font-size: 1.8rem; font-weight: 700; color: #111; text-transform: uppercase; letter-spacing: 1px;'>{stream_display}</div>
                        <div style='font-size: 1.2rem; color: #111; font-weight: 600;'>Overall Mean Score</div>
                        <div style='font-size: 3.5rem; font-weight: 800; color: #d32f2f;'>{overall_mean}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            c1, c2 = st.columns([2,1])
            with c1:
                st.markdown("<span style='font-size: 1.3rem; font-weight: 700;'>Subject</span>", unsafe_allow_html=True)
            with c2:
                st.markdown("<span style='font-size: 1.3rem; font-weight: 700;'>Mean Score</span>", unsafe_allow_html=True)
            st.markdown("---")
            skip_cols = ['Rank', 'Adm No', 'Class', 'Total', 'Mean', 'Name', '']
            for col in ordered:
                col_str = str(col).strip()
                if col_str in skip_cols or col_str == '':
                    continue
                mean_val = means_row.get(col, '')
                if str(mean_val).strip() == '':
                    continue
                c1, c2 = st.columns([2,1])
                with c1:
                    st.markdown(f"<span style='font-size: 1.15rem; font-weight: 600;'>{col}</span>", unsafe_allow_html=True)
                with c2:
                    st.markdown(f"<span style='font-size: 1.4rem; font-weight: 700; color: #d32f2f;'>{mean_val}</span>", unsafe_allow_html=True)

        st.stop()

    # If we're rebuilding and have a selected saved exam, use its raw data
    if rebuild_from_raw and selected_id and selected_id in st.session_state.saved_exam_raw_data:
        st.session_state.raw_marks = st.session_state.saved_exam_raw_data[selected_id].copy()

    # Save the current raw_marks for later use (in case it gets modified during processing)
    current_raw_marks_for_save = st.session_state.raw_marks.copy()
    
    df = st.session_state.raw_marks.copy()

    
    # Store original df and build filter options once (from full dataset)
    stream_col = None
    for col in df.columns:
        if col.lower().strip() in ['stream', 'class', 'form', 'stream/class']:
            stream_col = col
            break
    if stream_col:
        # Build normalized keys and labels from FULL dataset (not yet filtered)
        def norm_key(x: str):
            s = unicodedata.normalize('NFKC', str(x))
            s = re.sub(r"\s+", "", s)
            s = re.sub(r"[^0-9A-Za-z]", "", s)
            return s.upper()
        full_df = st.session_state.raw_marks.copy()
        full_df['_stream_key'] = full_df[stream_col].astype(str).apply(norm_key)
        orig_trim = full_df[stream_col].astype(str).str.strip()
        display_map = {}
        counts = {}
        for k, v in zip(full_df['_stream_key'], orig_trim):
            if not k:
                continue
            if k not in display_map:
                display_map[k] = v
            counts[k] = counts.get(k, 0) + 1
        labeled_keys = sorted(display_map.keys(), key=lambda x: display_map[x])
        labels = ["ALL"] + [f"{display_map[k]} ({counts.get(k,0)})" for k in labeled_keys]
        keys = [None] + labeled_keys
        st.session_state['analysis_filter_labels'] = labels
        st.session_state['analysis_filter_keys'] = keys
    # Apply persisted stream filter (selected near summary) to the analysis sheet
    if stream_col:
        # Apply persisted selection (by key) to DF
        def norm_key(x: str):
            s = unicodedata.normalize('NFKC', str(x))
            s = re.sub(r"\s+", "", s)
            s = re.sub(r"[^0-9A-Za-z]", "", s)
            return s.upper()
        df['_stream_key'] = df[stream_col].astype(str).apply(norm_key)
        sel_key = st.session_state.get('analysis_stream_key')
        if sel_key:
            df = df[df['_stream_key'] == sel_key].reset_index(drop=True)
        else:
            df = df.reset_index(drop=True)
        df = df.drop(columns=['_stream_key'])
    else:
        # Reset index even if no stream filtering to ensure clean indices
        df = df.reset_index(drop=True)
    
    # Remove any columns whose name matches a combined subject name (combined group keys)
    cfg_combined = st.session_state.cfg.get('combined_subjects', {}) or {}
    cfg_combined_names = set([str(k).lower().strip() for k in cfg_combined.keys()])
    # drop exact name matches (case-insensitive)
    cols_to_drop = [c for c in df.columns if str(c).lower().strip() in cfg_combined_names]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)
    if df.empty:
        st.warning("No data available. Please populate the raw mark sheet first.")
    else:
        # determine name column (case-insensitive)
        name_col = None
        for c in df.columns:
            if c.lower() == 'name':
                name_col = c
                break
        if name_col is None:
            # fallback: try first non-numeric column
            for c in df.columns:
                if not pd.api.types.is_numeric_dtype(df[c]):
                    name_col = c
                    break
        if name_col is None:
            st.error("Could not find a Name column in the raw marks. Ensure there's a column with student names.")
        else:
            # identify subject columns (exclude common non-subjects)
            # treat names case-insensitively and strip whitespace to avoid duplicates
            non_subjects = {"admno","adm no","adm_no","name","names","stream","class","term","year","rank","total","mean"}
            cols = list(df.columns)
            subject_cols = []
            seen_lower = set()
            for c in cols:
                cl = str(c).lower().strip()
                if cl in non_subjects:
                    continue
                if cl in seen_lower:
                    # skip duplicate subject (case/space-insensitive)
                    continue
                subject_cols.append(c)
                seen_lower.add(cl)

            # include combined subjects from config (they will be calculated)
            combined_cfg = st.session_state.cfg.get('combined_subjects', {}) or {}
            # produce unique combined names (avoid conflicts with subject names)
            combined_list = []
            used_lower = set([c.lower().strip() for c in subject_cols])
            for cname, parts in combined_cfg.items():
                base = str(cname).strip()
                candidate = base
                suffix = 1
                while candidate.lower().strip() in used_lower:
                    candidate = f"{base}_{suffix}"
                    suffix += 1
                used_lower.add(candidate.lower().strip())
                combined_list.append((candidate, parts))
            combined_names = [c for c, _ in combined_list]

            # Build marksheet dataframe
            marksheet = pd.DataFrame()
            marksheet['Rank'] = ['']*len(df)  # Will be filled after computing totals
            
            # Add AdmNo, Name, and Stream/Class columns if they exist (case-insensitive search)
            for col in df.columns:
                col_lower = col.lower().strip()
                if col_lower in ['admno', 'adm no', 'adm_no', 'admission number', 'admission no', 'admin no', 'admin number', 'admno.', 'adm.no', 'adm', 'admission', 'admin']:
                    marksheet['Adm No'] = df[col]
                elif col_lower in ['name', 'names', 'student name', 'student names']:
                    marksheet['Name'] = df[col]
                elif col_lower in ['stream', 'class', 'form', 'stream/class']:
                    marksheet['Class'] = df[col]

            numeric_cols_for_total = []
            subject_cols_order = []

            # Determine which subjects are parts of combined groups
            combined_parts = set()
            for _, parts in combined_list:
                for p in parts:
                    combined_parts.add(p)

            # For each uncombined subject: convert to percent for display and include in totals
            grading_enabled = st.session_state.cfg.get('grading_enabled', False)
            grading_system = st.session_state.cfg.get('grading_system', [])
            
            # Track all percentage values for points calculation
            all_subject_percentages = []
            all_subject_names = []  # Track subject names for points calculation
            
            for subj in subject_cols:
                try:
                    scores = pd.to_numeric(df[subj], errors='coerce')
                except Exception:
                    scores = pd.Series([pd.NA]*len(df))
                out_of = float(st.session_state.cfg.get(f'out_{subj}', 100))
                pct = (scores / out_of) * 100
                
                if subj not in combined_parts:
                    # Format with subject-specific grading
                    def format_for_subject(pct_value, subject=subj):
                        if pd.notna(pct_value):
                            pct_int = int(round(pct_value))
                            if grading_enabled and grading_system:
                                grade = get_grade(pct_int, grading_system, subject)
                                return f"{pct_int} {grade}" if grade else str(pct_int)
                            return str(pct_int)
                        return ''
                    
                    marksheet[subj] = pct.apply(format_for_subject).astype(object)
                    # include this subject's numeric pct in totals
                    numeric_cols_for_total.append((subj, pct.fillna(0)))
                    all_subject_percentages.append(pct)  # Track for points
                    all_subject_names.append(subj)  # Track subject name
                else:
                    # keep combined-part subjects as raw scores (do not convert)
                    marksheet[subj] = scores.fillna('').astype(object)
                subject_cols_order.append(subj)

            # Handle combined groups:
            combined_display_cols = []
            for cname, parts in combined_list:
                # Ensure component raw marks are present (not converted)
                for p in parts:
                    if p not in marksheet.columns:
                        try:
                            scores = pd.to_numeric(df[p], errors='coerce')
                        except Exception:
                            scores = pd.Series([pd.NA]*len(df))
                        marksheet[p] = scores.fillna('').astype(object)

                # Calculate total raw and out_of for combined
                total_raw = pd.Series([0]*len(df), dtype=float)
                total_out_of = 0.0
                for p in parts:
                    scores = pd.to_numeric(df.get(p, pd.Series([pd.NA]*len(df))), errors='coerce').fillna(0)
                    total_raw = total_raw + scores
                    total_out_of += float(st.session_state.cfg.get(f'out_{p}', 100))

                # Combined percentage as specified: (sum raw) / (sum outs) * 100
                combined_pct = (total_raw / total_out_of) * 100 if total_out_of > 0 else pd.Series([pd.NA]*len(df))
                # Display combined percentage as integer (no decimals) and include in totals
                # Use custom header if defined, otherwise default to "{cname}_Combined%"
                combined_header_map = st.session_state.cfg.get('combined_headers', {})
                combined_col_name = combined_header_map.get(cname, f"{cname}_Combined%")
                
                # Format combined with subject name
                def format_combined_for_subject(pct_value, combined_name=cname):
                    if pd.notna(pct_value):
                        pct_int = int(round(pct_value))
                        if grading_enabled and grading_system:
                            grade = get_grade(pct_int, grading_system, combined_name)
                            return f"{pct_int} {grade}" if grade else str(pct_int)
                        return str(pct_int)
                    return ''
                
                marksheet[combined_col_name] = combined_pct.apply(format_combined_for_subject).astype(object)
                combined_display_cols.append(combined_col_name)
                # Add combined percentage to totals (but not the component subjects)
                numeric_cols_for_total.append((combined_col_name, combined_pct.fillna(0)))
                all_subject_percentages.append(combined_pct)  # Track for points
                all_subject_names.append(cname)  # Track combined subject name

            # Total and Mean (Total is last column)
            # Sum numeric columns per student (single subjects and combined percentages)
            total_numeric = None
            for _, s in numeric_cols_for_total:
                if total_numeric is None:
                    total_numeric = s.copy()
                else:
                    # replace NaN with 0 when accumulating totals
                    total_numeric = total_numeric + s.fillna(0)
            if total_numeric is None:
                total_numeric = pd.Series([pd.NA] * len(df))

            # Number of contributing subjects (single subjects + combined percentages)
            n_single = max(1, len([col for col, _ in numeric_cols_for_total]))
            mean_numeric = (total_numeric / n_single)
            # Prepare display values
            # Totals: no decimals (integer display). Means: 2 decimals.
            def fmt_total(x):
                return int(round(x)) if pd.notna(x) else ''
            def fmt_mean(x):
                return f"{x:.2f}" if pd.notna(x) else ''

            # Fill Total and Mean columns, but leave them empty for Totals/Means rows
            # (they'll be filled with proper totals/means later)
            marksheet['Total'] = total_numeric.apply(fmt_total).astype(object)
            marksheet['Mean'] = mean_numeric.apply(fmt_mean).astype(object)

            # Calculate Points column (sum of points for all subjects)
            if grading_enabled and grading_system and all_subject_percentages:
                points_series = pd.Series([0] * len(marksheet), dtype=int)
                for pct_col, subj_name in zip(all_subject_percentages, all_subject_names):
                    subject_points = pct_col.apply(lambda x: get_points(x, grading_system, subj_name))
                    points_series = points_series + subject_points
                marksheet['Points'] = points_series.astype(object)
                # Empty for Totals/Means rows
                marksheet.loc[marksheet['Name'].isin(['Totals', 'Means']), 'Points'] = ''
            else:
                marksheet['Points'] = ''

            # First, identify valid student rows (exclude blanks and totals/means) BEFORE ranking
            valid_student_mask = (
                (~marksheet['Name'].isin(['Totals', 'Means'])) & 
                (marksheet['Name'].notna()) & 
                (marksheet['Name'].astype(str).str.strip() != '')
            )
            
            # Compute global ranks ONLY on valid students using competition style (min) to create gaps on ties
            # Example: two students at rank 28 -> next rank is 30
            # Since df was reset_index, total_numeric and marksheet should have matching indices
            try:
                ranks_numeric = pd.Series([pd.NA] * len(marksheet))
                valid_totals = total_numeric[valid_student_mask]
                ranks_numeric[valid_student_mask] = valid_totals.rank(method='min', ascending=False, na_option='bottom')
            except TypeError:
                # Fallback if pandas does not support na_option
                ranks_numeric = pd.Series([pd.NA] * len(marksheet))
                valid_totals = total_numeric[valid_student_mask]
                ranks_numeric[valid_student_mask] = valid_totals.rank(method='min', ascending=False)
            
            marksheet['Rank'] = ranks_numeric.apply(lambda x: int(x) if pd.notna(x) else '').astype(object)

            # Calculate Stream Rank (rank within each class/stream)
            marksheet['S/Rank'] = ''
            if 'Class' in marksheet.columns:
                # Group by Class and calculate rank within each group
                for class_val in marksheet['Class'].unique():
                    if pd.isna(class_val) or str(class_val).strip() in ['', 'Totals', 'Means']:
                        continue
                    class_mask = (marksheet['Class'] == class_val) & valid_student_mask
                    if class_mask.any():
                        class_totals = total_numeric[class_mask]
                        try:
                            class_ranks = class_totals.rank(method='min', ascending=False, na_option='bottom')
                        except TypeError:
                            class_ranks = class_totals.rank(method='min', ascending=False)
                        # Assign ranks to the class_mask positions
                        marksheet.loc[class_mask, 'S/Rank'] = class_ranks.apply(lambda x: int(x) if pd.notna(x) else '').astype(object)
            else:
                # If no Class column, Stream Rank is same as overall Rank
                marksheet['S/Rank'] = marksheet['Rank']

            # Build final column order: Rank, AdmNo, Name, subjects with combined pct columns
            ordered = ['Rank']
            if 'Adm No' in marksheet.columns:
                ordered.append('Adm No')
            if 'Name' in marksheet.columns:
                ordered.append('Name')
            if 'Class' in marksheet.columns:
                ordered.append('Class')

            # Insert combined percentage columns immediately to the right of the right-most component subject
            # Build insertion map: position in subject_cols_order -> list of combined cols to insert after that position
            insert_map = {}
            if 'combined_display_cols' in locals():
                for (cname, parts), combined_col in zip(combined_list, combined_display_cols):
                    # find indices of parts in subject_cols_order
                    indices = [i for i, s in enumerate(subject_cols_order) if s in parts]
                    if indices:
                        pos = max(indices)
                    else:
                        # if none of the parts present, append at end
                        pos = len(subject_cols_order) - 1
                    insert_map.setdefault(pos, []).append(combined_col)

            # Build ordered list by walking subjects and inserting combined cols after the right-most part
            for idx, subj in enumerate(subject_cols_order):
                if subj in marksheet.columns:
                    ordered.append(subj)
                # insert any combined cols that should appear after this subject
                if idx in insert_map:
                    for cc in insert_map[idx]:
                        if cc in marksheet.columns:
                            ordered.append(cc)

            ordered.extend(['Total', 'Mean', 'Points', 'S/Rank'])
            ordered = [c for c in ordered if c in marksheet.columns]
            # First put columns in desired order
            marksheet = marksheet[ordered]
            
            # Extract valid student rows (already identified earlier with valid_student_mask)
            student_rows = marksheet[valid_student_mask].copy()
            
            # Sort student rows globally by Rank, then optionally by Class and Name for stable ordering
            try:
                student_rows['_RankSort'] = student_rows['Rank'].replace('', pd.NA)
                student_rows['_RankSort'] = pd.to_numeric(student_rows['_RankSort'], errors='coerce').fillna(1e9)
                sort_keys = ['_RankSort']
                if 'Class' in student_rows.columns:
                    sort_keys.append('Class')
                if 'Name' in student_rows.columns:
                    sort_keys.append('Name')
                student_rows = student_rows.sort_values(by=sort_keys)
                student_rows = student_rows.drop(columns=['_RankSort'])
            except Exception:
                pass
            
            
            # Prepare fresh Totals and Means rows
            footer_totals = {}
            footer_means = {}
            footer_totals['Name'] = 'Totals'
            footer_means['Name'] = 'Means'
            footer_totals['Rank'] = ''
            footer_means['Rank'] = ''
            footer_totals['S/Rank'] = ''
            footer_means['S/Rank'] = ''
            footer_totals['Points'] = ''
            footer_means['Points'] = ''
            # Add Adm No as empty (don't calculate totals/means for it)
            if 'Adm No' in marksheet.columns:
                footer_totals['Adm No'] = ''
                footer_means['Adm No'] = ''
            for col in marksheet.columns:
                if col in ('Rank', 'Name', 'Adm No', 'S/Rank', 'Points'):
                    continue
                # Extract numeric values from columns (handle grades like "85 A")
                try:
                    # First try to extract numbers from strings (handles "85 A" format)
                    col_str = marksheet[col].astype(str).str.strip()
                    # Extract first numeric value from each cell
                    col_numeric = col_str.str.extract(r'(\d+\.?\d*)')[0]
                    col_values = pd.to_numeric(col_numeric, errors='coerce')
                except Exception:
                    col_values = pd.Series([pd.NA]*len(marksheet))
                
                # Calculate totals and means (excluding marked students from both)
                if col_values.notna().any():
                    # For both totals and means, exclude students from the exclusion list
                    excluded_students = st.session_state.cfg.get('excluded_students_from_means', [])
                    if excluded_students and 'Name' in marksheet.columns:
                        # Get student names (only valid students, not Totals/Means rows)
                        student_names = marksheet.loc[valid_student_mask, 'Name'].astype(str).str.strip()
                        # Create mask for students NOT in exclusion list
                        include_mask = ~student_names.isin(excluded_students)
                        # Apply mask to the corresponding values
                        col_values_for_calc = col_values[valid_student_mask][include_mask.values]
                    else:
                        col_values_for_calc = col_values
                    
                    if col_values_for_calc.notna().any():
                        footer_totals[col] = int(col_values_for_calc.sum(skipna=True))
                        footer_means[col] = f"{col_values_for_calc.mean(skipna=True):.2f}"
                    else:
                        footer_totals[col] = ''
                        footer_means[col] = ''
                else:
                    footer_totals[col] = ''
                    footer_means[col] = ''

            # Create footer DataFrame with Totals and Means
            footer_df = pd.DataFrame([footer_totals, footer_means])
            
            # Prepare export dataframe for downloads
            export_df = pd.concat([student_rows.astype(object), footer_df[ordered].astype(object)], ignore_index=True)
            
            # Show downloads above the sheet (outside expander, visible inline)
            st.markdown("---")
            st.markdown("### 📥 Download Marksheet")
            
            # Use saved selection for PDF generation, but maintain analysis sheet order
            saved_selection = st.session_state.get("pdf_columns_selected", ordered)
            # Filter to only selected columns, but keep them in the original 'ordered' sequence
            selected_cols = [c for c in ordered if c in saved_selection]
            
            # Page estimate
            try:
                total_rows = export_df.shape[0]
                pages_est = (total_rows + rows_per_page - 1) // rows_per_page
                st.success(f"📄 Estimated pages: **{pages_est}** (based on {rows_per_page} rows per page)")
            except Exception:
                pass
            
            # Excel and PDF download buttons side-by-side
            excel_buffer = BytesIO()
            export_df.to_excel(excel_buffer, index=False, engine='openpyxl')
            excel_data = excel_buffer.getvalue()
            excel_filename = f"{st.session_state.cfg.get('school_name')}_Marksheet.xlsx"
            
            dcol1, dcol2 = st.columns(2)
            with dcol1:
                st.download_button("⬇ Download Excel", data=excel_data, file_name=excel_filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            
            with dcol2:
                # PDF download using chosen orientation and scale
                try:
                    # Determine stream for PDF title
                    sel_key = st.session_state.get('analysis_stream_key')
                    labels = st.session_state.get('analysis_filter_labels', ['ALL'])
                    keys = st.session_state.get('analysis_filter_keys', [None])
                    try:
                        idx = keys.index(sel_key)
                        selected_label = labels[idx]
                    except ValueError:
                        selected_label = 'ALL'
                    
                    # Extract stream display (remove count if present)
                    if selected_label and selected_label != 'ALL':
                        stream_for_title = selected_label.rsplit(" (", 1)[0]  # e.g., "9G" or "9B"
                    else:
                        stream_for_title = "9 OVERALL"  # Overall
                    
                    title = f"{st.session_state.cfg.get('exam_name','Exam')} - {stream_for_title}"
                    chosen_orientation = 'portrait' if orientation == 'Portrait' else 'landscape'
                    # Apply column selection (preserve order)
                    export_pdf_df = export_df[selected_cols]
                    pdf_bytes = df_to_pdf_bytes(
                        export_pdf_df,
                        st.session_state.cfg.get('school_name','Your School'),
                        st.session_state.cfg.get('class_name','Class'),
                        title,
                        orientation=chosen_orientation,
                        scale=scale,
                        font_size=9,
                        fit_all_rows=fit_all
                    )
                    pdf_filename = f"{st.session_state.cfg.get('school_name')}_Marksheet.pdf"
                    st.download_button('⬇ Download PDF', data=pdf_bytes, file_name=pdf_filename, mime='application/pdf', use_container_width=True, disabled=(len(selected_cols)==0))
                except Exception as e:
                    st.error(f"PDF error: {e}")
            
            st.markdown("---")
            
            # Clear the rebuild flag now that we've processed the raw marks
            st.session_state.rebuild_from_raw = False
            
            st.markdown("### Marksheet (percentages)")

            # Save button at the side of the sheet (session-only, no local files)
            side_l, side_r = st.columns([7, 1])
            with side_r:
                if st.button("💾 Save Sheet", key="save_analysis_sheet_side"):
                    # Prepare a friendly name and ask for confirmation
                    from datetime import datetime
                    exam_name = str(st.session_state.cfg.get('exam_name', 'Exam')).strip()
                    class_name = str(st.session_state.cfg.get('class_name', '')).strip()
                    year = datetime.now().year
                    # Initialize editable values
                    st.session_state.save_edit_exam_name = exam_name
                    st.session_state.save_edit_class_name = class_name
                    # Include term if available in session state or cfg
                    term_val = st.session_state.get('term_widget') or st.session_state.cfg.get('term','')
                    # Only include class name if it's not empty; include term if provided
                    if class_name and term_val:
                        st.session_state['pending_save_friendly_name'] = f"{exam_name} - {term_val} - {class_name} - {year}"
                    elif class_name:
                        st.session_state['pending_save_friendly_name'] = f"{exam_name} - {class_name} - {year}"
                    elif term_val:
                        st.session_state['pending_save_friendly_name'] = f"{exam_name} - {term_val} - {year}"
                    else:
                        st.session_state['pending_save_friendly_name'] = f"{exam_name} - {year}"
                    st.rerun()  # Rerun to update sidebar and show dialog

            # Present save confirmation as compact dialog
            pending_name = st.session_state.get('pending_save_friendly_name')
            if pending_name:
                # Use dialog decorator to create modal
                @st.dialog("💾 Save Exam")
                def save_dialog():
                    # Initialize editable values if not already set
                    if 'save_edit_exam_name' not in st.session_state:
                        st.session_state.save_edit_exam_name = st.session_state.cfg.get('exam_name', 'Exam')
                    if 'save_edit_class_name' not in st.session_state:
                        st.session_state.save_edit_class_name = st.session_state.cfg.get('class_name', '')
                    
                    # Editable fields
                    edit_exam = st.text_input("Exam Name:", value=st.session_state.save_edit_exam_name, key="edit_exam_save")
                    edit_class = st.text_input("Class/Stream (optional):", value=st.session_state.save_edit_class_name, key="edit_class_save")
                    # Term field shown in save confirmation overlay (optional)
                    # Prefill from session term_widget or cfg
                    default_term = st.session_state.get('term_widget') or st.session_state.cfg.get('term','')
                    edit_term = st.text_input("Term (optional):", value=default_term, key="save_dialog_term")
                    
                    # Build final name from edited values
                    from datetime import datetime
                    year = datetime.now().year
                    # Include term from the dialog input if provided
                    term_val = edit_term.strip() if 'edit_term' in locals() and edit_term else (st.session_state.get('term_widget') or st.session_state.cfg.get('term',''))
                    if edit_class.strip() and term_val:
                        final_name = f"{edit_exam} - {term_val} - {edit_class} - {year}"
                    elif edit_class.strip():
                        final_name = f"{edit_exam} - {edit_class} - {year}"
                    elif term_val:
                        final_name = f"{edit_exam} - {term_val} - {year}"
                    else:
                        final_name = f"{edit_exam} - {year}"
                    
                    st.info(f"📋 Will save as: **{final_name}**")
                    if edit_term and str(edit_term).strip():
                        st.caption(f"Term: {edit_term}")
                    # expose term_input variable so later save logic can persist it
                    term_input = edit_term
                    
                    col1, col2 = st.columns([1, 1])
                    with col1:
                        if st.button("✅ Save", key="confirm_save_sheet"):
                            try:
                                import uuid
                                # Ensure session storage structures
                                if 'saved_exams' not in st.session_state:
                                    st.session_state.saved_exams = []
                                if 'saved_exam_data' not in st.session_state:
                                    st.session_state.saved_exam_data = {}
                                if 'saved_exam_raw_data' not in st.session_state:
                                    st.session_state.saved_exam_raw_data = {}
                                if 'saved_exam_configs' not in st.session_state:
                                    st.session_state.saved_exam_configs = {}

                                # Check if we're updating an existing saved exam
                                selected_id = st.session_state.get('selected_saved_exam_id')
                                
                                # Check for duplicate name within the same year (since final_name includes year)
                                # Now consider term as well: allow same final_name if term differs
                                existing_pairs = [(e.get('exam_name'), e.get('term','')) for e in st.session_state.saved_exams if e.get('year') == year]
                                if selected_id and selected_id in st.session_state.saved_exam_data:
                                    # Updating existing - allow same name/term only if it's this exam's current metadata
                                    current_exam = next((e for e in st.session_state.saved_exams if e.get('exam_id') == selected_id), None)
                                    if current_exam:
                                        # Remove current exam's pair from the check list
                                        pair = (current_exam.get('exam_name'), current_exam.get('term',''))
                                        existing_pairs = [p for p in existing_pairs if p != pair]

                                # Use edit_term (from dialog) if available, else fall back to cfg term
                                check_term = edit_term if 'edit_term' in locals() else st.session_state.cfg.get('term','')
                                if (final_name, check_term) in existing_pairs:
                                    st.error(f"❌ Exam '{final_name}' with term '{check_term}' already exists for year {year}. Please choose a different name or term.")
                                    st.stop()

                                # Use the saved copy of raw marks from the beginning of analysis processing
                                raw_to_save = st.session_state.get('current_raw_marks_for_save', st.session_state.raw_marks)
                                
                                # Save current config (out_of values and combined_subjects)
                                config_to_save = {}
                                # Save all out_of values for each subject
                                for key, value in st.session_state.cfg.items():
                                    if key.startswith('out_'):
                                        config_to_save[key] = value
                                # Save combined_subjects configuration
                                config_to_save['combined_subjects'] = st.session_state.cfg.get('combined_subjects', {})
                                # Save grading system configuration
                                config_to_save['grading_enabled'] = st.session_state.cfg.get('grading_enabled', False)
                                config_to_save['grading_system'] = st.session_state.cfg.get('grading_system', [])
                                config_to_save['strict_grading_enabled'] = st.session_state.cfg.get('strict_grading_enabled', False)
                                config_to_save['strict_grading_system'] = st.session_state.cfg.get('strict_grading_system', [])
                                config_to_save['strict_grading_subjects'] = st.session_state.cfg.get('strict_grading_subjects', [])
                                # Save excluded subjects configuration
                                config_to_save['excluded_subjects'] = st.session_state.cfg.get('excluded_subjects', [])
                                config_to_save['exclude_lowest_grade'] = st.session_state.cfg.get('exclude_lowest_grade', False)
                                # Save excluded students from means
                                config_to_save['excluded_students_from_means'] = st.session_state.cfg.get('excluded_students_from_means', [])
                                config_to_save['ranking_basis'] = st.session_state.cfg.get('ranking_basis', 'Totals')
                                
                                # Always save ALL students regardless of current filter
                                full_export_df, _ord = _build_export_from_raw(raw_to_save)
                                
                                if selected_id and selected_id in st.session_state.saved_exam_data:
                                    # Update existing exam
                                    exam_id = selected_id
                                    st.session_state.saved_exam_data[exam_id] = full_export_df.copy()
                                    st.session_state.saved_exam_raw_data[exam_id] = raw_to_save.copy()
                                    st.session_state.saved_exam_configs[exam_id] = config_to_save.copy()
                                    # Update metadata
                                    for exam_meta in st.session_state.saved_exams:
                                        if exam_meta.get('exam_id') == exam_id:
                                            exam_meta['exam_name'] = final_name
                                            exam_meta['date_saved'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                                            exam_meta['year'] = year
                                            exam_meta['class_name'] = edit_class.strip()
                                            # Persist the term (if provided in sidebar)
                                            exam_meta['term'] = term_input if 'term_input' in locals() else st.session_state.cfg.get('term','')
                                            exam_meta['total_students'] = int(len(full_export_df) - 2) if len(full_export_df) >= 2 else int(len(full_export_df))
                                            exam_meta['num_subjects'] = int(len([c for c in full_export_df.columns if c not in ['Rank','Adm No','Name','Class','Total','Mean']]))
                                            exam_meta['storage'] = 'persistent'
                                            
                                            # Save to disk
                                            save_exam_to_disk(exam_id, exam_meta, full_export_df.copy(), raw_to_save.copy(), config_to_save.copy())
                                            break
                                    st.session_state.pop('pending_save_friendly_name', None)
                                    st.session_state.pop('save_edit_exam_name', None)
                                    st.session_state.pop('save_edit_class_name', None)
                                    st.session_state.rebuild_from_raw = False  # Load saved exam, don't rebuild
                                    st.session_state.has_unsaved_exam = False  # Clear unsaved flag
                                    st.session_state['exam_save_confirmed'] = True  # Enable dropdown after confirmation
                                    st.session_state.view = 'analysis'  # Switch to analysis view to show updated exam
                                    st.success(f"Updated '{final_name}' permanently.")
                                    st.toast("Sheet updated and saved to disk!")
                                    st.rerun()  # Rerun to show the updated analysis
                                else:
                                    # Create new exam
                                    exam_id = str(uuid.uuid4())
                                    st.session_state.saved_exam_data[exam_id] = full_export_df.copy()
                                    st.session_state.saved_exam_raw_data[exam_id] = raw_to_save.copy()
                                    st.session_state.saved_exam_configs[exam_id] = config_to_save.copy()
                                    exam_metadata = {
                                        'exam_id': exam_id,
                                        'exam_name': final_name,
                                        'term': term_input if 'term_input' in locals() else st.session_state.cfg.get('term',''),
                                        'date_saved': datetime.now().strftime('%Y-%m-%d %H:%M'),
                                        'year': year,
                                        'class_name': edit_class.strip(),
                                        'total_students': int(len(full_export_df) - 2) if len(full_export_df) >= 2 else int(len(full_export_df)),
                                        'num_subjects': int(len([c for c in full_export_df.columns if c not in ['Rank','Adm No','Name','Class','Total','Mean']])),
                                        'storage': 'persistent'
                                    }
                                    st.session_state.saved_exams.append(exam_metadata)
                                    
                                    # Save to disk
                                    save_exam_to_disk(exam_id, exam_metadata, full_export_df.copy(), raw_to_save.copy(), config_to_save.copy())
                                    
                                    st.session_state.selected_saved_exam_id = exam_id  # Auto-select the new exam
                                    st.session_state.pop('pending_save_friendly_name', None)
                                    st.session_state.pop('save_edit_exam_name', None)
                                    st.session_state.pop('save_edit_class_name', None)
                                    st.session_state.rebuild_from_raw = False  # Load saved exam, don't rebuild
                                    st.session_state.has_unsaved_exam = False  # Clear unsaved flag
                                    st.session_state['exam_save_confirmed'] = True  # Enable dropdown after confirmation
                                    st.session_state.view = 'analysis'  # Switch to analysis view
                                    st.success(f"Saved '{final_name}' (all students) permanently.")
                                    st.toast("Sheet saved to disk!")
                                    st.rerun()  # Rerun to show the analysis
                                
                            except Exception as e:
                                st.error(f"Could not save sheet: {e}")
                    with col2:
                        if st.button("Cancel", key="cancel_save_sheet", use_container_width=True):
                            st.session_state.pop('pending_save_friendly_name', None)
                            st.session_state.pop('save_edit_exam_name', None)
                            st.session_state.pop('save_edit_class_name', None)
                            # Don't clear rebuild_from_raw or has_unsaved_exam flags
                            st.rerun()
                
                # Open the dialog
                save_dialog()
            
            # Keep rows even if Name is blank so counts per class/stream remain accurate
            # Optionally, you could highlight blanks later instead of dropping them.

            # Apply cross multiplication if enabled (from controls)
            display_student_rows = student_rows.copy()
            if enable_cross and 'Total' in display_student_rows.columns:
                try:
                    # Get current total numeric values
                    total_vals = pd.to_numeric(display_student_rows['Total'].replace('', pd.NA), errors='coerce')
                    # Find the maximum total to determine current scale
                    max_total = total_vals.max()
                    if pd.notna(max_total) and max_total > 0:
                        # Cross multiply: (current_total / max_total) * target_total
                        cross_multiplied = (total_vals / max_total) * target_total
                        # Update Total column with cross-multiplied values (as integers)
                        display_student_rows['Total'] = cross_multiplied.apply(lambda x: int(round(x)) if pd.notna(x) else '').astype(object)
                        st.info(f"📊 Total scaled from 0-{int(max_total)} to 0-{target_total}")
                except Exception as e:
                    st.error(f"Error converting Total: {e}")

            # Display student rows in sortable dataframe
            st.dataframe(
                display_student_rows.astype(object), 
                use_container_width=True, 
                hide_index=True
            )

            # Diagnostics: show count of students and how many have blank names
            try:
                total_filtered = len(student_rows)
                blank_names = int((student_rows['Name'].astype(str).str.strip() == '').sum()) if 'Name' in student_rows.columns else 0
                st.caption(f"Students shown: {total_filtered}  •  Blank names: {blank_names}")
            except Exception:
                pass
            
            # Column selection for PDF - moved to the controls expander
            with download_placeholder.container():
                # Column selection for PDF export using a compact form
                st.markdown("#### Columns to include in PDF")
                
                # Initialize saved selection if needed
                if "pdf_columns_selected" not in st.session_state:
                    st.session_state["pdf_columns_selected"] = ordered
                
                # Use a form to prevent rerun on each checkbox click
                with st.form(key="pdf_column_selector_form"):
                    st.markdown("**Select columns:**")
                    
                    # Quick action buttons in columns
                    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
                    select_all = btn_col1.form_submit_button("✅ All")
                    deselect_all = btn_col2.form_submit_button("❌ None")
                    core_only = btn_col3.form_submit_button("📌 Core")
                    subjects_only = btn_col4.form_submit_button("📚 Subjects")
                    
                    # Handle quick actions
                    if select_all:
                        st.session_state["pdf_columns_selected"] = ordered.copy()
                    elif deselect_all:
                        st.session_state["pdf_columns_selected"] = []
                    elif core_only:
                        core_cols = ['Rank', 'Adm No', 'Name', 'Class', 'Total', 'Mean']
                        st.session_state["pdf_columns_selected"] = [c for c in ordered if c in core_cols]
                    elif subjects_only:
                        skip_cols = ['Rank', 'Adm No', 'Name', 'Class', 'Total', 'Mean']
                        st.session_state["pdf_columns_selected"] = [c for c in ordered if c not in skip_cols]
                    
                    # Display checkboxes in a compact grid layout (3 columns)
                    current_selection = st.session_state.get("pdf_columns_selected", ordered)
                    num_cols = 3
                    cols_per_row = st.columns(num_cols)
                    
                    selected_cols = []
                    for idx, col in enumerate(ordered):
                        col_idx = idx % num_cols
                        is_checked = col in current_selection
                        if cols_per_row[col_idx].checkbox(col, value=is_checked, key=f"pdf_col_{col}"):
                            selected_cols.append(col)
                    
                    # Save button
                    submitted = st.form_submit_button("💾 Apply Selection", type="primary")
                    if submitted:
                        st.session_state["pdf_columns_selected"] = selected_cols if selected_cols else ordered
                
                # Show selection summary
                current_selection = st.session_state.get("pdf_columns_selected", ordered)
                st.caption(f"✓ {len(current_selection)} of {len(ordered)} columns selected")
            
            # Display Totals and Means as a professional styled footer
            st.markdown("<div style='margin-top: 2rem;'></div>", unsafe_allow_html=True)
            
            # Compact filter control immediately above Summary Statistics
            if stream_col and 'analysis_filter_labels' in st.session_state:
                labels = st.session_state.get('analysis_filter_labels', ['ALL'])
                keys = st.session_state.get('analysis_filter_keys', [None])
                current_key = st.session_state.get('analysis_stream_key')
                # Compute default index based on current key
                try:
                    default_index = keys.index(current_key)
                except ValueError:
                    default_index = 0
                st.markdown("---")
                f1, f2 = st.columns([1,3])
                with f1:
                    st.markdown("**Filter:**")
                with f2:
                    sel_label = st.selectbox("Class/Stream", options=labels, index=default_index, key='analysis_stream_filter_ui', label_visibility='collapsed')
                # Map label -> key by index and persist, then re-run to apply immediately
                try:
                    new_key = keys[labels.index(sel_label)]
                except ValueError:
                    new_key = None
                if new_key != current_key:
                    st.session_state['analysis_stream_key'] = new_key
                    st.rerun()

            # Display summary statistics - means only, with overall mean first
            st.markdown("### 📊 Summary Statistics")
            
            # Get means row
            means_row = footer_df.iloc[1]
            
            # Determine which stream is being shown (single-select)
            # Derive stream display from selected key using stored labels/keys
            sel_key = st.session_state.get('analysis_stream_key')
            labels = st.session_state.get('analysis_filter_labels', ['ALL'])
            keys = st.session_state.get('analysis_filter_keys', [None])
            try:
                idx = keys.index(sel_key)
                selected_label = labels[idx]
            except ValueError:
                selected_label = 'ALL'
            try:
                stream_display = "OVERALL"
                if selected_label and selected_label != 'ALL':
                    # Strip count suffix " (n)" for display
                    stream_display = selected_label.rsplit(" (", 1)[0]
            except Exception:
                stream_display = "OVERALL"
            
            # Display overall mean first (from Total column) in compact, B/W layout with red mean value
            overall_mean = means_row.get('Total', '')
            if overall_mean:
                st.markdown(
                    f"""
                    <div style='text-align:center; padding: 1rem 0; margin-bottom: 1.5rem;'>
                        <div style='font-size: 1.8rem; font-weight: 700; color: #111; text-transform: uppercase; letter-spacing: 1px;'>{stream_display}</div>
                        <div style='font-size: 1.2rem; color: #111; font-weight: 600;'>Overall Mean Score</div>
                        <div style='font-size: 3.5rem; font-weight: 800; color: #d32f2f;'>{overall_mean}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            
            # Create header
            col1, col2 = st.columns([2, 1])
            with col1:
                st.markdown("<span style='font-size: 1.3rem; font-weight: 700;'>Subject</span>", unsafe_allow_html=True)
            with col2:
                st.markdown("<span style='font-size: 1.3rem; font-weight: 700;'>Mean Score</span>", unsafe_allow_html=True)
            
            st.markdown("---")
            
            # Display each subject mean
            skip_cols = ['Rank', 'Adm No', 'Class', 'Total', 'Mean', 'Name', '']
            for col in ordered:
                col_str = str(col).strip()
                if col_str in skip_cols or col_str == '':
                    continue
                
                mean_val = means_row.get(col, '')
                
                # Skip if no data
                if str(mean_val).strip() == '':
                    continue
                
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.markdown(f"<span style='font-size: 1.15rem; font-weight: 600;'>{col}</span>", unsafe_allow_html=True)
                with col2:
                    st.markdown(f"<span style='font-size: 1.4rem; font-weight: 700; color: #d32f2f;'>{mean_val}</span>", unsafe_allow_html=True)
            
            # Footer for Analysis page
            st.markdown("<div style='margin-top: 3rem;'></div>", unsafe_allow_html=True)
            st.markdown(
                "<div style='text-align:center; font-size:14px; color:#666; padding: 2rem 1rem; border-top: 2px solid #e0e0e0;'>"
                "Thank you for choosing <b>Eduscore Analytics</b><br>"
                "For more of our services contact us on: <b>0793975959</b>"
                "</div>",
                unsafe_allow_html=True
            )


# ---------------------------
# MAIN VIEW: raw marks entry and tools
# ---------------------------
else:
    st.markdown("### Paste Raw Mark Sheet")

    # Prepare a display copy of the raw sheet that hides any combined-group name columns
    combined_cfg = st.session_state.cfg.get("combined_subjects", {}) or {}
    combined_names_set = set([str(k).lower().strip() for k in combined_cfg.keys()])
    raw_full = st.session_state.raw_marks.copy()
    cols_to_drop = [c for c in raw_full.columns if str(c).lower().strip() in combined_names_set]
    if cols_to_drop:
        display_df = raw_full.drop(columns=cols_to_drop)
    else:
        display_df = raw_full.copy()

    # input mode toggling (only show the chosen input method)
    mode = st.session_state.cfg.get("input_mode","paste")
    # if user toggles input mode in sidebar it already saved to cfg; reflect here
    if mode == "paste":
        st.info("Mode: Paste Raw Marks (paste from Excel)")
        pasted = st.text_area("Paste Excel data (tab-separated):", height=220, placeholder="AdmNo\tName\tClass\tMath\tEng\tSci\tSST", key="paste_area")
        # Auto-load when pasted data changes
        if pasted and pasted.strip():
            try:
                loaded = pd.read_csv(StringIO(pasted), sep="\t")
                loaded.index = range(1, len(loaded)+1)
                if not loaded.equals(st.session_state.raw_marks):
                    push_history()
                    st.session_state.raw_marks = loaded.copy()
                    save_raw_marks()
                    # Clear class name for fresh data
                    if st.session_state.cfg.get('class_name') == 'Class':
                        st.session_state.cfg['class_name'] = ""
                    st.session_state.class_name_widget = ""
                    # Clear any selected saved exam
                    st.session_state.selected_saved_exam_id = None
                    save_config(st.session_state.cfg)
                    st.success("✓ Pasted data loaded into sheet.")
                    # Force a rerun so the Current Raw Mark Sheet (editable) reflects the pasted data immediately
                    st.rerun()
            except Exception as e:
                st.error(f"Could not parse pasted data: {e}")
    else:
        st.info("Mode: Manual Entry (type or edit directly)")
        if st.session_state.raw_marks.empty:
            # create a minimal starter sheet if empty
            st.session_state.raw_marks = pd.DataFrame(columns=["AdmNo","Name","Class"])
        # Show the display_df (which hides combined-group name columns)
        st.info("💡 **Tip:** After pasting from Excel, press Ctrl+Enter or click outside the table to finalize, then click 'Save Changes'.")
        manual = st.data_editor(display_df, num_rows="dynamic", use_container_width=True, key="manual_editor_main", hide_index=True)
        if st.button("💾 Save Changes", type="primary"):
            # Only update the visible columns in the underlying raw_marks so hidden combined columns are preserved
            try:
                if not manual.equals(display_df):
                    push_history()
                    # start from the current full raw marks
                    new_full = st.session_state.raw_marks.copy()
                    # ensure index alignment
                    manual_idx = manual.index
                    # For each column present in the visible editor, update or add to the full dataframe
                    for col in manual.columns:
                        new_full[col] = manual[col].values
                    # If the user removed a visible column, keep it removed from the stored df as well
                    for col in list(new_full.columns):
                        if col not in manual.columns and str(col).lower().strip() not in combined_names_set:
                            # drop any visible (non-combined) columns that the user removed in the editor
                            # but preserve combined-group name columns
                            try:
                                new_full = new_full.drop(columns=[col])
                            except Exception:
                                pass
                    st.session_state.raw_marks = new_full.copy()
                    save_raw_marks()
                    st.success("✅ Changes saved successfully!")
                    st.rerun()
            except Exception:
                st.error("Could not save changes. Please try again.")

    st.markdown("---")
    st.markdown("### Current Raw Mark Sheet (editable)")
    st.info("💡 **After pasting from Excel:** Press Ctrl+Enter or click outside the table, then click 'Save Sheet Changes' below to commit your data.")
    # Show editor with combined-group name columns hidden and no row numbers
    edited_table = st.data_editor(display_df, use_container_width=True, num_rows="dynamic", key="main_table_editor", hide_index=True)
    if st.button("💾 Save Sheet Changes", type="primary", use_container_width=True):
        try:
            if not edited_table.equals(display_df):
                push_history()
                new_full = st.session_state.raw_marks.copy()
                for col in edited_table.columns:
                    new_full[col] = edited_table[col].values
                # Drop any visible (non-combined) columns that were removed by the user
                for col in list(new_full.columns):
                    if col not in edited_table.columns and str(col).lower().strip() not in combined_names_set:
                        try:
                            new_full = new_full.drop(columns=[col])
                        except Exception:
                            pass
                st.session_state.raw_marks = new_full.copy()
                save_raw_marks()
                st.success("✅ Changes saved successfully!")
                st.rerun()
        except Exception:
            st.error("Could not save changes. Please try again.")

    # Out-of inputs and combine (compact)
    st.markdown("### Subjects: Out-of values and Combine")
    non_subjects = {"admno","adm no","adm_no","name","names","stream","class","term","year","form","stream/class","admission number","admission no","admin no","admin number","admno.","adm.no","adm","admission","admin","student name","student names"}
    cols = list(st.session_state.raw_marks.columns)
    # Exclude combined SUBJECT NAMES (group names) from appearing as subjects here
    combined_cfg = st.session_state.cfg.get("combined_subjects", {})
    combined_names = set([str(k).lower().strip() for k in combined_cfg.keys()])
    subject_cols = [c for c in cols if c.lower().strip() not in non_subjects and c.lower().strip() not in combined_names]
    subject_out_of = {}
    # Out-of inputs should appear for all visible subject columns (we already excluded combined group names above)
    subject_cols_for_out = subject_cols
    if subject_cols_for_out:
        for i in range(0, len(subject_cols_for_out), 2):
            a = subject_cols_for_out[i]
            b = subject_cols_for_out[i+1] if i+1 < len(subject_cols_for_out) else None
            ca, cb = st.columns(2)
            with ca:
                subject_out_of[a] = st.number_input(f"{a} Out of", min_value=1, max_value=1000, value=st.session_state.cfg.get(f"out_{a}",100), key=f"out_{a}")
                st.session_state.cfg[f"out_{a}"] = subject_out_of[a]
            with cb:
                if b:
                    subject_out_of[b] = st.number_input(f"{b} Out of", min_value=1, max_value=1000, value=st.session_state.cfg.get(f"out_{b}",100), key=f"out_{b}")
                    st.session_state.cfg[f"out_{b}"] = subject_out_of[b]
        # persist any out_of changes
        save_config(st.session_state.cfg)

    # combine groups: load from config and allow editing
    st.markdown("#### ➕ Combined Subjects")
    
    # Get existing combined subjects from config
    combined_groups = st.session_state.cfg.get("combined_subjects", {})
    
    # Edit existing combinations (including editable headers)
    st.markdown("**Current Combined Subjects (click to rename header):**")
    to_delete = []
    to_rename = []
    for cname, cols_list in list(combined_groups.items()):
        col1, col2, col3, col4 = st.columns([3, 3, 1, 1])
        with col1:
            new_cname = st.text_input("Combined Header", value=cname, key=f"cname_edit_{cname}")
        with col2:
            st.caption("Parts: " + ", ".join(cols_list))
        with col3:
            if st.button("Save", key=f"save_{cname}"):
                if new_cname.strip() and new_cname.strip() != cname:
                    to_rename.append((cname, new_cname.strip()))
        with col4:
            if st.button("🗑️", key=f"del_{cname}"):
                to_delete.append(cname)
    
    # Apply renames first (handle conflicts by appending suffix)
    if to_rename:
        for old, new in to_rename:
            if old in combined_groups:
                final_name = new
                suffix = 1
                while final_name in combined_groups and final_name != old:
                    final_name = f"{new}_{suffix}"
                    suffix += 1
                if final_name != old:
                    combined_groups[final_name] = combined_groups.pop(old)
        st.session_state.cfg["combined_subjects"] = combined_groups
        save_config(st.session_state.cfg)
        st.rerun()

    # Remove any marked for deletion
    for cname in to_delete:
        if cname in combined_groups:
            del combined_groups[cname]
            st.session_state.cfg["combined_subjects"] = combined_groups
            save_config(st.session_state.cfg)
            st.rerun()
    
    # Add new combination
    st.markdown("**Add New Combined Subject:**")
    new_name = st.text_input("New combined subject name", key="new_combined_name")
    new_choices = st.multiselect("Select subjects to combine", options=subject_cols, key="new_combined_cols")
    
    if new_name and new_choices:
        if st.button("➕ Add Combined Subject"):
            combined_groups[new_name] = new_choices
            st.session_state.cfg["combined_subjects"] = combined_groups
            save_config(st.session_state.cfg)
            st.success(f"Added new combined subject: {new_name}")
            st.rerun()
    
    # Compute button for all combined subjects
    if combined_groups:
        if st.button("🔄 Compute All Combined Subjects"):
            dfw = st.session_state.raw_marks.copy()
            for cname, cols_list in combined_groups.items():
                nums = []
                for col in cols_list:
                    out_val = st.session_state.cfg.get(f"out_{col}", 100)
                    nums.append((pd.to_numeric(dfw[col], errors="coerce") / float(out_val)) * 100)
                if nums:
                    dfw[cname] = pd.concat(nums, axis=1).mean(axis=1, skipna=True)
                else:
                    dfw[cname] = None
            # commit combined subjects back to the raw sheet
            push_history()
            st.session_state.raw_marks = dfw.copy()
            save_raw_marks()
            st.success("All combined subjects computed and added to the sheet.")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 2rem 1rem 1rem 1rem;'>
    <p style='margin: 0; font-size: 0.9rem;'><strong>EDUSCORE ANALYTICS</strong></p>
    <p style='margin: 0.3rem 0; font-size: 0.85rem;'>Developed by <strong>Munyua Kamau</strong></p>
    <p style='margin: 0.3rem 0; font-size: 0.75rem; color: #888;'>© 2025 All Rights Reserved</p>
</div>
""", unsafe_allow_html=True)
