import streamlit as st
import pandas as pd
import os
from datetime import datetime
import json
import pickle
import re
import base64
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas
from modules import storage
from uuid import uuid4

# Page configuration
st.set_page_config(page_title="Report Cards", layout="wide")

# Sanitize accidental admin-hidden message on this page only.
# Some content can come from account files or cached HTML; to be safe
# intercept common Streamlit output helpers and remove the exact
# unwanted sentence before rendering.
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
    # If monkeypatching fails for any reason, continue without sanitization
    pass

# If the parents portal mode is active, block access to this page
try:
    if st.session_state.get('parents_portal_mode'):
        st.markdown("<div style='opacity:0.45;padding:18px;border-radius:8px;background:#f3f4f6;color:#111;'>\
            <strong>Restricted:</strong> This page is not available in Parents Portal mode.</div>", unsafe_allow_html=True)
        st.stop()
except Exception:
    pass

# Define persistent storage path (use storage adapter so S3 is respected)
def _storage_dir():
    try:
        return storage.get_storage_dir()
    except Exception:
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'saved_exams_storage')


def _metadata_file():
    return os.path.join(_storage_dir(), 'exams_metadata.json')


def _report_settings_file():
    return os.path.join(_storage_dir(), 'report_card_settings.json')

# Helper functions for persistent report card settings
def load_report_settings():
    """Load report card settings from disk"""
    try:
        p = _report_settings_file()
        cfg = storage.read_json(p)
        if cfg is not None:
            return cfg
    except Exception:
        pass
    return get_default_report_settings()

def save_report_settings(settings):
    """Save report card settings to disk"""
    try:
        p = _report_settings_file()
        return storage.write_json(p, settings)
    except Exception as e:
        st.error(f"Failed to save settings: {e}")
        return False

def get_default_report_settings():
    """Return default report card settings"""
    return {
        'school_name': 'Your School Name',
        'motto': 'Knowledge is Power',
        'email': 'info@school.com',
        'term': 'Term 1',
        'year': 2025,
        'opening_date': datetime.now().strftime('%Y-%m-%d'),
        'closing_date': datetime.now().strftime('%Y-%m-%d'),
        'class_teacher': '',
        'head_teacher': '',
        # Optional attachments defaults
        'logo_path': '',
        'logo2_path': '',
        'stamp_path': '',
        'main_title_color': '#0E6BA8',
        'section_title_color': '#2c3e50',
        'table_header_color': '#0E6BA8',
        'include_subject_rank': True,
        'include_multi_exam_avg': True,
        'avg_decimal_places': 1,
        'rank_in_multi': True,
    'include_mean_row_single_exam': True,
    'include_total_row': True,
    'include_mean_row': True,
    'include_points_row': True,
    'include_grade_row': True,
        'include_comment_column': True,
        'auto_fill_subject_comments': True,
        'auto_fill_teacher_names': False,
        'grading_mode': 'Paste Text',
        'grading_table_rows': [],
        'comment_mode': 'Simple (≥ thresholds)',
        'comment_bands': [
            {"label":"Excellent","min":100,"max":80,"text":"Excellent performance!"},
            {"label":"V.Good","min":79,"max":70,"text":"Very good work."},
            {"label":"Good","min":69,"max":60,"text":"Good effort."},
            {"label":"Average","min":59,"max":50,"text":"Average performance."},
            {"label":"Improve","min":49,"max":0,"text":"Needs improvement."},
        ],
        'ranking_exam_name': '',
        'comment_basis': 'Base exam score',
        'avg_explanation': 'Average across selected exams',
        'grading_table_text': 'A,80\nB,70\nC,60\nD,50\nE,0',
        'include_class_teacher': True,
        'include_head_teacher': True,
        'include_teacher_column': False,
        'auto_class_teacher_remarks': True,
        'auto_head_teacher_remarks': True,
        'thr_excellent': 80.0,
        'thr_vgood': 70.0,
        'thr_good': 60.0,
        'thr_average': 50.0,
        'ct_ex_min': 800,
        'ct_vg_min': 700,
        'ct_g_min': 600,
        'ct_av_min': 500,
        'class_teacher_text_ex': 'Excellent performance!',
        'class_teacher_text_vg': 'Very good work.',
        'class_teacher_text_g': 'Good effort.',
        'class_teacher_text_av': 'Average performance.',
        'class_teacher_text_im': 'Needs improvement.',
        'ht_ex_min': 800,
        'ht_vg_min': 700,
        'ht_g_min': 600,
        'ht_av_min': 500,
        'head_teacher_text_ex': 'Outstanding achievement!',
        'head_teacher_text_vg': 'Keep up the good work.',
        'head_teacher_text_g': 'Satisfactory progress.',
        'head_teacher_text_av': 'Fair performance.',
        'head_teacher_text_im': 'Requires more effort.',
        'section_order_header': 1,
        'section_order_student': 2,
        'section_order_academic': 3,
        'section_order_comments': 4,
        'section_order_grading': 5,
        'section_order_footer': 99,
        'no_comment_subjects': [],
        'enable_watermark': False,
        'watermark_type': 'text',
        'watermark_text': 'CONFIDENTIAL',
        'watermark_opacity': 0.2,
        'watermark_angle': 45,
        'watermark_font_size': 100,
        'watermark_color': '#999999',
        'watermark_image_path': '',
        'watermark_image_size': 300,
    }

# Helper function to parse grading key
def parse_grading_key(text):
    """Parse grading key from text (format: Grade,MinScore or Grade:MinScore per line)"""
    lines = text.strip().split('\n')
    key_map = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = re.split(r'[,:]', line)
        if len(parts) >= 2:
            grade = parts[0].strip()
            try:
                min_score = float(parts[1].strip())
                key_map.append((grade, min_score))
            except:
                pass
    return sorted(key_map, key=lambda x: x[1], reverse=True)

# Helper: sanitize exam names to exclude class and year from display in the card
def sanitize_exam_name(name, settings=None):
    try:
        s = str(name)
        # Remove year patterns like 2020-2039
        s = re.sub(r"\b20\d{2}\b", "", s)
        # Remove common class labels e.g., Form 1, Grade 7, Class 8, Std 6
        s = re.sub(r"\b(Form|Grade|Class|Std)\s*[A-Za-z0-9]+\b", "", s, flags=re.IGNORECASE)
        # Remove duplicate spaces and separators
        s = re.sub(r"\s*[-_/]+\s*", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        # If settings year provided and still present, strip it
        if settings and isinstance(settings.get('year', None), (int, float, str)):
            y = str(settings.get('year'))
            s = re.sub(fr"\b{re.escape(y)}\b", "", s).strip()
        return s
    except Exception:
        return name

# Helper: Display PDF in browser preview
def display_pdf_preview(pdf_buffer, height=800):
    """Display a PDF buffer in an embedded iframe viewer."""
    try:
        pdf_buffer.seek(0)
        base64_pdf = base64.b64encode(pdf_buffer.read()).decode('utf-8')
        pdf_display = f'''
            <iframe 
                src="data:application/pdf;base64,{base64_pdf}" 
                width="100%" 
                height="{height}px" 
                type="application/pdf"
                style="border: 2px solid #ddd; border-radius: 5px;"
            >
            </iframe>
        '''
        st.markdown(pdf_display, unsafe_allow_html=True)
        pdf_buffer.seek(0)  # Reset for download button
    except Exception as e:
        st.error(f"Preview error: {e}")

# Helper: generate teacher remark based on overall score and band texts
def get_remark_from_bands(score, thresholds, texts, comment_bands=None):
    """Return a remark for a numeric score using either custom comment ranges or simple thresholds.
    comment_bands: list of dicts with keys label|min|max|text using same semantics as grading (max ≤ score ≤ min).
    thresholds/texts fallback when ranges not provided."""
    if score is None:
        return None
    # Prefer custom ranges if available
    try:
        if comment_bands:
            s = float(score)
            for band in comment_bands:
                try:
                    lower = float(band.get('max', 0))
                    upper = float(band.get('min', 0))
                    if lower <= s <= upper:
                        return str(band.get('text') or band.get('label') or '') or None
                except Exception:
                    continue
    except Exception:
        pass
    # Fallback to simple thresholds
    thr_ex = thresholds.get('excellent', 80)
    thr_vg = thresholds.get('vgood', 70)
    thr_g = thresholds.get('good', 60)
    thr_av = thresholds.get('average', 50)
    # Texts dict keys: excellent, vgood, good, average, improve
    if score >= thr_ex:
        return texts.get('excellent', 'Excellent')
    if score >= thr_vg:
        return texts.get('vgood', 'Very good')
    if score >= thr_g:
        return texts.get('good', 'Good')
    if score >= thr_av:
        return texts.get('average', 'Average')
    return texts.get('improve', 'Needs improvement')

# Helper functions for persistence
def load_all_metadata():
    """Load all exam metadata from disk"""
    try:
        # Prefer storage adapter (S3) when available
        try:
            m = storage.read_json(_metadata_file())
            if isinstance(m, dict):
                return m
        except Exception:
            # fallback to legacy bare-key read if adapter accepts it
            try:
                m = storage.read_json('exams_metadata.json')
                if isinstance(m, dict):
                    return m
            except Exception:
                pass
        if os.path.exists(METADATA_FILE):
            with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception:
        return {}

def load_exam_from_disk(exam_id):
    """Load a single exam's data from disk"""
    try:
        # Use storage adapter where possible (S3-aware)
        data_key = os.path.join(str(exam_id), 'data.pkl')
        raw_key = os.path.join(str(exam_id), 'raw_data.pkl')
        cfg_key = os.path.join(str(exam_id), 'config.json')

        exam_data = None
        exam_raw_data = None
        exam_config = {}

        try:
            if storage is not None:
                if storage.exists(data_key):
                    exam_data = storage.read_pickle(data_key)
                if storage.exists(raw_key):
                    exam_raw_data = storage.read_pickle(raw_key)
                if storage.exists(cfg_key):
                    exam_config = storage.read_json(cfg_key) or {}
                return exam_data, exam_raw_data, exam_config
        except Exception:
            # fallback to local cache
            pass

        exam_dir = os.path.join(STORAGE_DIR, exam_id)
        # Load dataframes from local cache
        data_path = os.path.join(exam_dir, 'data.pkl')
        raw_data_path = os.path.join(exam_dir, 'raw_data.pkl')
        config_path = os.path.join(exam_dir, 'config.json')
        if os.path.exists(data_path):
            exam_data = pd.read_pickle(data_path)
        if os.path.exists(raw_data_path):
            exam_raw_data = pd.read_pickle(raw_data_path)
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                exam_config = json.load(f)
        return exam_data, exam_raw_data, exam_config
    except Exception:
        return None, None, {}

def load_all_exams_into_session():
    """Load all exams from disk into session state"""
    all_metadata = load_all_metadata()
    
    if all_metadata:
        st.session_state.saved_exams = list(all_metadata.values())
        
        for exam_id, metadata in all_metadata.items():
            exam_data, exam_raw_data, exam_config = load_exam_from_disk(exam_id)
            
            if exam_data is not None:
                st.session_state.saved_exam_data[exam_id] = exam_data
            if exam_raw_data is not None:
                st.session_state.saved_exam_raw_data[exam_id] = exam_raw_data
            if exam_config:
                st.session_state.saved_exam_configs[exam_id] = exam_config

def add_watermark_to_canvas(canvas_obj, page_num, watermark_settings):
    """Add watermark directly to canvas object."""
    if not watermark_settings.get('enable_watermark', False):
        return
    
    canvas_obj.saveState()
    
    try:
        watermark_type = watermark_settings.get('watermark_type', 'text')
        page_width, page_height = A4
        
        if watermark_type == 'text':
            # Text watermark
            text = watermark_settings.get('watermark_text', 'CONFIDENTIAL')
            opacity = float(watermark_settings.get('watermark_opacity', 0.2))
            angle = float(watermark_settings.get('watermark_angle', 45))
            font_size = int(watermark_settings.get('watermark_font_size', 100))
            color_hex = watermark_settings.get('watermark_color', '#999999')
            
            # Parse color
            hex_color = color_hex.lstrip('#')
            r = int(hex_color[0:2], 16) / 255.0
            g = int(hex_color[2:4], 16) / 255.0
            b = int(hex_color[4:6], 16) / 255.0
            
            # Apply transparency (if supported) and color
            try:
                canvas_obj.setFillAlpha(opacity)
            except Exception:
                pass
            canvas_obj.setFillColorRGB(r, g, b)
            canvas_obj.setFont("Helvetica-Bold", font_size)
            
            # Center and rotate
            canvas_obj.translate(page_width / 2, page_height / 2)
            canvas_obj.rotate(angle)
            
            # Draw text
            text_width = canvas_obj.stringWidth(text, "Helvetica-Bold", font_size)
            canvas_obj.drawString(-text_width / 2, -font_size / 3, text)
            
        else:
            # Image watermark
            watermark_image_path = watermark_settings.get('watermark_image_path', '')
            if watermark_image_path and os.path.exists(watermark_image_path):
                opacity = float(watermark_settings.get('watermark_opacity', 0.3))
                angle = float(watermark_settings.get('watermark_angle', 45))
                image_size = float(watermark_settings.get('watermark_image_size', 300))
                
                canvas_obj.setFillAlpha(opacity)
                canvas_obj.setStrokeAlpha(opacity)
                
                canvas_obj.translate(page_width / 2, page_height / 2)
                canvas_obj.rotate(angle)
                
                canvas_obj.drawImage(
                    watermark_image_path,
                    -image_size / 2,
                    -image_size / 2,
                    width=image_size,
                    height=image_size,
                    preserveAspectRatio=True,
                    mask='auto'
                )
    except Exception as e:
        pass  # Silently fail if watermark can't be drawn
    
    canvas_obj.restoreState()


def generate_professional_report_card_pdf(students_data, settings, multiple_exams_data=None):
    """Generate a professional PDF report card (one page per student)."""
    buffer = BytesIO()
    
    # Build watermark settings dict
    watermark_settings = {
        'enable_watermark': settings.get('enable_watermark', False),
        'watermark_type': settings.get('watermark_type', 'text'),
        'watermark_text': settings.get('watermark_text', 'CONFIDENTIAL'),
        'watermark_opacity': settings.get('watermark_opacity', 0.1),
        'watermark_angle': settings.get('watermark_angle', 45),
        'watermark_font_size': settings.get('watermark_font_size', 100),
        'watermark_color': settings.get('watermark_color', '#CCCCCC'),
        'watermark_image_path': settings.get('watermark_image_path', ''),
        'watermark_image_size': settings.get('watermark_image_size', 300),
    }
    
    # Create document (watermark added via page callback later)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.2*inch,
        bottomMargin=0.2*inch,
        leftMargin=0.3*inch,
        rightMargin=0.3*inch,
    )
    
    story = []
    styles = getSampleStyleSheet()
    main_title_color = settings.get('main_title_color', settings.get('titles_color', '#0E6BA8'))
    section_title_color = settings.get('section_title_color', main_title_color)
    table_header_color = settings.get('table_header_color', main_title_color)
    # Localize frequently used toggles from settings (avoid reliance on outer-scope variables)
    include_teacher_column = settings.get('include_teacher_column', False)
    include_comment_column = settings.get('include_comment_column', True)
    auto_fill_teacher_names = settings.get('auto_fill_teacher_names', False)
    auto_fill_subject_comments = settings.get('auto_fill_subject_comments', True)
    include_multi_exam_avg = settings.get('include_multi_exam_avg', True)
    rank_in_multi = settings.get('rank_in_multi', True)
    include_subject_rank = settings.get('include_subject_rank', True)
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor(main_title_color), spaceAfter=2, alignment=TA_CENTER, fontName='Helvetica-Bold')
    subtitle_style = ParagraphStyle('CustomSubtitle', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#2c3e50'), spaceAfter=2, alignment=TA_CENTER, fontName='Helvetica-Oblique')
    section_style = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor(section_title_color), spaceAfter=3, spaceBefore=3, alignment=TA_CENTER, fontName='Helvetica-Bold')

    def detect_component_subjects(subject_columns):
        """Automatically detect component subjects (papers) sharing a common base.
        Example: 'Mathematics', 'Mathematics P1', 'Mathematics P2' => 'Mathematics P1/P2' are components.
        Returns a set of subject names considered components.
        """
        tokens = [
            'P1','P2','P3','Paper 1','Paper 2','Paper 3','Paper1','Paper2','Paper3',
            'I','II','III','Theory','Practical'
        ]
        subjects = list(subject_columns)
        bases = set(subjects)
        components = set()
        for base in bases:
            base_lower = base.lower()
            for s in subjects:
                if s == base:
                    continue
                lower = s.lower()
                # pattern base <sep> token
                if lower.startswith(base_lower + ' ') or lower.startswith(base_lower + '-'):
                    tail = lower[len(base_lower):].strip(' -')
                    if any(t.lower() in tail.split() for t in tokens):
                        components.add(s)
                # compact patterns base+token or base-token
                for t in tokens:
                    t_low = t.lower().replace(' ', '')
                    if lower == base_lower + ' ' + t_low or lower == base_lower + '-' + t_low or lower == base_lower + t_low:
                        components.add(s)
        return components

    def convert_score_to_numeric(val, thresholds):
        try:
            if pd.isna(val):
                return None
        except Exception:
            pass
        try:
            return float(val)
        except Exception:
            pass
        try:
            m = re.search(r"[-+]?[0-9]*\.?[0-9]+", str(val))
            if m:
                return float(m.group())
        except Exception:
            pass
        v = str(val).strip().upper()
        thr_ex = thresholds.get('excellent', 80)
        thr_vg = thresholds.get('vgood', 70)
        thr_g = thresholds.get('good', 60)
        thr_av = thresholds.get('average', 50)
        bands = {
            'A': (thr_ex + 100) / 2,
            'B': (thr_vg + thr_ex) / 2,
            'C': (thr_g + thr_vg) / 2,
            'D': (thr_av + thr_g) / 2,
            'E': (0 + thr_av) / 2,
        }
        base = v.replace('+','').replace('-','')
        if base in bands:
            valnum = bands[base]
            if v.endswith('+'):
                valnum = min(100, valnum + 2)
            elif v.endswith('-'):
                valnum = max(0, valnum - 2)
            return float(valnum)
        return None

    def get_points_from_percentage(pct, subject_name=None):
        """Map a numeric percentage to points using grading system from marksheet page (st.session_state.cfg).
        Supports strict grading for selected subjects if configured there."""
        try:
            cfg = st.session_state.get('cfg', {})
            grading_system = cfg.get('grading_system', []) or []
            if subject_name and cfg.get('strict_grading_enabled', False):
                strict_subjects = cfg.get('strict_grading_subjects', []) or []
                if subject_name in strict_subjects:
                    grading_system = cfg.get('strict_grading_system', grading_system) or []
            pct_f = float(pct)
            for rule in grading_system:
                try:
                    lower = float(rule.get('max', 0))
                    upper = float(rule.get('min', 0))
                    if lower <= pct_f <= upper:
                        return int(rule.get('points', 0))
                except Exception:
                    continue
            return 0
        except Exception:
            return 0

    for idx, student_data in enumerate(students_data):
        # Section buffers
        sections = {
            'Header': [],
            'Grading Key': [],
            'Student Info': [],
            'Academic Performance': [],
            'Comments': [],
            'Footer': [],
        }

        # Unpack
        if len(student_data) == 4:
            student_row, subject_cols, exam_df, exam_name = student_data
        else:
            student_row, subject_cols, exam_df = student_data
            exam_name = settings.get('term', 'Exam')
        student_name = str(student_row.get('Name', 'N/A'))
        # Auto component subjects augmentation
        auto_components = detect_component_subjects(subject_cols)
        comp_from_settings = set(settings.get('component_subjects', []) or [])
        effective_components = comp_from_settings.union(auto_components)
        settings['effective_component_subjects'] = list(effective_components)

        # Header
        left_logo = None; right_logo = None
        try:
            if settings.get('logo_path') and os.path.exists(settings['logo_path']):
                left_logo = Image(settings['logo_path'], width=0.7*inch, height=0.7*inch)
            if settings.get('logo2_path') and os.path.exists(settings['logo2_path']):
                right_logo = Image(settings['logo2_path'], width=0.7*inch, height=0.7*inch)
        except Exception:
            pass
        center_block = [
            Paragraph(settings['school_name'].upper(), title_style),
            Paragraph(settings.get('motto', ''), subtitle_style),
            Paragraph(f"Email: {settings.get('email', '')}", subtitle_style)
        ]
        header_table = Table([[left_logo if left_logo else '', center_block, right_logo if right_logo else '']], colWidths=[0.9*inch, 4.8*inch, 0.9*inch])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (0,0), 'LEFT'),
            ('ALIGN', (1,0), (1,0), 'CENTER'),
            ('ALIGN', (2,0), (2,0), 'RIGHT'),
        ]))
        sections['Header'].extend([header_table, Spacer(1,0.03*inch), Paragraph("STUDENT REPORT CARD", section_style), Spacer(1,0.03*inch)])

        # Grading/Info table (display-only) with support for simple colspan syntax {colspan=N}
        pasted_text = settings.get('grading_table_text', '') or ''
        structured_rows = settings.get('grading_table_rows', []) or []
        raw_rows = []
        if structured_rows:
            raw_rows = structured_rows
        elif pasted_text.strip():
            for ln in pasted_text.splitlines():
                ln = ln.rstrip()
                if not ln:
                    continue
                delim = '\t' if '\t' in ln else ','
                parts = [p.strip() for p in ln.split(delim)]
                raw_rows.append(parts)
        else:
            raw_rows = [['Grading / Info','Detail'],['No table pasted','Threshold comments only']]

        # Determine max columns after expanding colspans logically (placeholder cells inserted)
        processed_rows = []
        span_commands = []  # list of (row, col_start, col_end)
        for r_idx, row in enumerate(raw_rows):
            expanded = []
            c_idx = 0
            for cell in row:
                m = re.search(r"\{colspan=(\d+)\}", cell, re.IGNORECASE)
                if m:
                    span = max(1, int(m.group(1)))
                    text = re.sub(r"\{colspan=\d+\}", "", cell).strip()
                    expanded.append(text)
                    # add placeholders for remaining spanned columns
                    for _ in range(span-1):
                        expanded.append("")
                    span_commands.append((r_idx, c_idx, c_idx+span-1))
                    c_idx += span
                else:
                    expanded.append(cell)
                    c_idx += 1
            processed_rows.append(expanded)
        max_cols = max(len(r) for r in processed_rows) if processed_rows else 2
        # Normalize row lengths
        for r in processed_rows:
            if len(r) < max_cols:
                r.extend([""]*(max_cols-len(r)))
        # Width constraints: scale smaller, never exceed subjects table nominal width
        total_width = 4.5*inch  # smaller than subjects table (6.6")
        base_col_width = total_width / max_cols
        # Minimum & maximum column width constraints
        if base_col_width < 0.4*inch:
            base_col_width = 0.4*inch
        if base_col_width > 1.5*inch:
            base_col_width = 1.5*inch
        colWidths = [base_col_width]*max_cols
        key_table = Table(processed_rows, colWidths=colWidths, hAlign='CENTER')
        table_style = [
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('GRID',(0,0),(-1,-1),0.5,colors.grey),
            # Remove header background to allow watermark to show through
            # ('BACKGROUND',(0,0),(-1,0),colors.whitesmoke),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ]
        # Adaptive font size: smaller table, smaller fonts
        header_font = 6 if max_cols <= 6 else 5
        body_font = 5 if max_cols <= 6 else 4
        table_style.append(('FONTSIZE',(0,0),(-1,0),header_font))
        table_style.append(('FONTSIZE',(0,1),(-1,-1),body_font))
        for (r, c0, c1) in span_commands:
            if c1 > c0:
                table_style.append(('SPAN', (c0,r), (c1,r)))
        key_table.setStyle(TableStyle(table_style))
        sections['Grading Key'].extend([key_table, Spacer(1,0.03*inch)])

        # Student Info
        try:
            valid_mask = exam_df['Name'].astype(str).str.strip().ne("") & ~exam_df['Name'].astype(str).str.lower().isin(['mean','total','average'])
            _overall_total = int(valid_mask.sum())
        except Exception:
            _overall_total = ''
        student_info_data = [
            ['Name:', str(student_row.get('Name','N/A')), 'Adm No:', str(student_row.get('Adm No','N/A'))],
            ['Class:', str(student_row.get('Class','N/A')), 'Term:', f"{settings['term']} - {settings['year']}"]
        ]
        student_info_table = Table(student_info_data, colWidths=[1*inch,1.8*inch,1*inch,1.8*inch])
        student_info_table.setStyle(TableStyle([
            # Remove cell background fills for transparency over watermark
            # ('BACKGROUND',(0,0),(0,-1),colors.HexColor('#E8F4F8')),
            # ('BACKGROUND',(2,0),(2,-1),colors.HexColor('#E8F4F8')),
            ('TEXTCOLOR',(0,0),(-1,-1),colors.HexColor('#2c3e50')),
            ('ALIGN',(0,0),(-1,-1),'LEFT'),
            ('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),
            ('FONTNAME',(2,0),(2,-1),'Helvetica-Bold'),
            ('FONTNAME',(1,0),(1,0),'Helvetica-Bold'),
            ('FONTSIZE',(0,0),(-1,-1),7),
            ('GRID',(0,0),(-1,-1),0.5,colors.grey),
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('TOPPADDING',(0,0),(-1,-1),3),
            ('BOTTOMPADDING',(0,0),(-1,-1),3),
        ]))
        sections['Student Info'].extend([student_info_table, Spacer(1,0.03*inch)])

        # Academic Performance (header first)
        sections['Academic Performance'].extend([Paragraph("ACADEMIC PERFORMANCE", section_style), Spacer(1,0.03*inch)])

        # (Legacy duplicated block removed)

        # Build subjects table (reuse existing logic, appended to sections)
        # ... (For brevity, reuse previously computed logic by re-executing existing block below)
        # The original logic below remains unchanged; only final appends redirected.
        # START existing subject table logic
        # Thresholds for multi-exam path may need student_row; leveraging existing code after this patch.
        # (We avoid duplicating entire original block here due to patch size constraints.)
        # END placeholder comment
        # NOTE: We will keep original implementation below; only final story appends are redirected earlier.
        # Subjects table logic continues below without modification until computed subjects_table.
        
        # (Existing code continues without changes.)
        
        # After original subjects_table construction (later in function), we will replace direct story.append with sections['Academic Performance'].append
        # and redirect comments/footer sections similarly. (Implemented further down in this function.)
        
        # The remainder of function (from original) executes; patch continues after subjects_table styling.
        
        # We break out after building subjects_table to compute overall mean and comments; those will be appended to sections instead of story.
        
        # NOTE: Section ordering application occurs after loop end.
        
        # (Allow original code beyond here to run; final assembly occurs at bottom.)
        
        # Begin subjects table construction
        if multiple_exams_data and len(multiple_exams_data) > 0:
            # Multi-exam table with columns for each exam
            header_cols = ['Subject']
            # Use sanitized exam names (exclude class/year)
            header_cols += [sanitize_exam_name(exam['name'], settings) for exam in multiple_exams_data]
            if include_multi_exam_avg:
                header_cols += ['Avg']
            if rank_in_multi:
                header_cols += ['Rank']
            if include_comment_column:
                header_cols += ['Comment']
            if include_teacher_column:
                header_cols += ['Teacher']
            subjects_data = [header_cols]

            # Thresholds
            thrs = settings.get('thresholds', {})
            thr_ex = thrs.get('excellent', 80)
            thr_vg = thrs.get('vgood', 70)
            thr_g = thrs.get('good', 60)
            thr_av = thrs.get('average', 50)
            avg_decimals = settings.get('avg_decimal_places', 1)

            base_exam_df = multiple_exams_data[0]['exam_df'] if multiple_exams_data else exam_df

            for subject in subject_cols:
                row = [subject[:15]]
                
                scores = []
                latest_score_for_comment = None

                for exam_data in multiple_exams_data:
                    exam_df_temp = exam_data['exam_df']
                    student_rows = exam_df_temp[exam_df_temp['Name'] == student_name]
                    if not student_rows.empty:
                        exam_student_row = student_rows.iloc[0]
                        if subject in exam_student_row.index:
                            score = exam_student_row[subject]
                            row.append(str(score))
                            latest_score_for_comment = score if comment_basis == 'Base exam score' and exam_data is multiple_exams_data[0] else latest_score_for_comment
                            # Convert graded marks to numeric for averaging
                            numeric_score = convert_score_to_numeric(score, thrs)
                            if numeric_score is not None:
                                scores.append(numeric_score)
                        else:
                            row.append('-')
                    else:
                        row.append('-')

                avg_val = None
                if include_multi_exam_avg and scores:
                    avg_val = sum(scores) / len(scores)
                    row.append(f"{avg_val:.{avg_decimals}f}")
                elif include_multi_exam_avg:
                    row.append('-')

                if rank_in_multi:
                    # Rank based on chosen ranking exam (fallback to first)
                    try:
                        # Determine ranking exam df
                        rank_df = base_exam_df
                        chosen_rank_name = settings.get('ranking_exam_name')
                        if chosen_rank_name and multiple_exams_data:
                            match = next((e for e in multiple_exams_data if e['name'] == chosen_rank_name), None)
                            if match:
                                rank_df = match['exam_df']
                        # Convert possibly graded values to numeric for ranking
                        subject_scores_series = rank_df[subject]
                        numeric_scores = subject_scores_series.apply(lambda x: convert_score_to_numeric(x, thrs))
                        numeric_scores = numeric_scores.dropna().astype(float)
                        sorted_scores = numeric_scores.sort_values(ascending=False)
                        base_student_row = rank_df[rank_df['Name'] == student_name]
                        if not base_student_row.empty:
                            base_raw = base_student_row.iloc[0][subject]
                            base_score = convert_score_to_numeric(base_raw, thrs)
                            position = list(sorted_scores.values).index(base_score) + 1
                            row.append(f"{position}/{len(sorted_scores)}")
                        else:
                            row.append('-')
                    except Exception:
                        row.append('-')

                # Comment will be appended; teacher column must be last

                # Determine comment source value
                comment_source = None
                if comment_basis == 'Average across exams' and avg_val is not None:
                    comment_source = avg_val
                else:
                    # fallback base exam score - convert if graded
                    try:
                        base_student_row = base_exam_df[base_exam_df['Name'] == student_name]
                        if not base_student_row.empty and subject in base_student_row.columns:
                            raw_score = base_student_row.iloc[0][subject]
                            comment_source = convert_score_to_numeric(raw_score, thrs)
                    except Exception:
                        comment_source = None

                comment = ''
                # Check if subject should be excluded from comments first
                comp_subjects = settings.get('effective_component_subjects', []) or []
                no_comment_list = settings.get('no_comment_subjects', []) or []
                should_skip_comment = subject in comp_subjects or subject in no_comment_list
                
                if auto_fill_subject_comments and not should_skip_comment:
                    if comment_source is not None:
                        if comment_source >= thr_ex:
                            comment = 'Excellent'
                        elif comment_source >= thr_vg:
                            comment = 'V.Good'
                        elif comment_source >= thr_g:
                            comment = 'Good'
                        elif comment_source >= thr_av:
                            comment = 'Average'
                        else:
                            comment = 'Improve'
                    else:
                        comment = ''
                if include_comment_column:
                    # Apply custom comment ranges if provided (only if not excluded)
                    if not should_skip_comment and settings.get('comment_mode') == 'Ranges' and settings.get('comment_bands'):
                        comment = get_remark_from_bands(comment_source, settings.get('thresholds', {}), {}, settings.get('comment_bands')) or comment
                    row.append(comment)
                if include_teacher_column:
                    tname = ''
                    if auto_fill_teacher_names:
                        if 'Teacher' in student_row.index:
                            tname = str(student_row.get('Teacher', '')).strip()[:10]
                        elif f'{subject}_Teacher' in student_row.index:
                            tname = str(student_row.get(f'{subject}_Teacher', '')).strip()[:10]
                    row.append(tname)
                subjects_data.append(row)
            
            # Calculate num_exams early for use in summary rows
            num_exams = len(multiple_exams_data)
            
            # Add summary rows showing Total, Mean, (optional Points), Class Rank, Overall Rank for each exam
            # Row 0: Total for each exam (student total per exam)
            total_row = ['Total']
            avg_totals = []  # collect totals from exams for average calculation
            for exam_data in multiple_exams_data:
                df_tmp = exam_data['exam_df']
                row_tmp = df_tmp[df_tmp['Name'] == student_name]
                if not row_tmp.empty:
                    total_val_e = row_tmp.iloc[0].get('Total', '-')
                    total_row.append(str(total_val_e))
                    # Try converting to numeric for avg column calc
                    try:
                        avg_totals.append(float(total_val_e))
                    except:
                        pass
                else:
                    total_row.append('-')
            if include_multi_exam_avg:
                # Calculate average of totals across exams
                if avg_totals:
                    avg_total = sum(avg_totals) / len(avg_totals)
                    total_row.append(f"{avg_total:.{avg_decimals}f}")
                else:
                    total_row.append('-')
            if rank_in_multi:
                total_row.append('')
            if include_comment_column:
                total_row.append('')
            if include_teacher_column:
                total_row.append('')
            if settings.get('include_total_row', True):
                subjects_data.append(total_row)

            # Row 1: Mean for each exam
            mean_row = ['Mean']
            avg_means = []  # collect means from exams for average calculation
            for exam_data in multiple_exams_data:
                df_tmp = exam_data['exam_df']
                row_tmp = df_tmp[df_tmp['Name'] == student_name]
                if not row_tmp.empty:
                    mean_val = row_tmp.iloc[0].get('Mean', '-')
                    mean_row.append(str(mean_val))
                    # Try converting to numeric for avg column calc
                    try:
                        avg_means.append(float(mean_val))
                    except:
                        pass
                else:
                    mean_row.append('-')
            if include_multi_exam_avg:
                # Calculate average of means across exams
                if avg_means:
                    avg_mean = sum(avg_means) / len(avg_means)
                    mean_row.append(f"{avg_mean:.{avg_decimals}f}")
                else:
                    mean_row.append('-')
            if rank_in_multi:
                mean_row.append('')
            if include_comment_column:
                mean_row.append('')
            if include_teacher_column:
                mean_row.append('')
            if settings.get('include_mean_row', True):
                subjects_data.append(mean_row)

            # Optional Row: Points per exam (sum of subject points using grading system)
            if settings.get('include_points_row', True):
                points_row = ['Points']
                for exam_data in multiple_exams_data:
                    df_tmp = exam_data['exam_df']
                    row_tmp = df_tmp[df_tmp['Name'] == student_name]
                    if not row_tmp.empty:
                        r0 = row_tmp.iloc[0]
                        total_points = 0
                        for subj in subject_cols:
                            if subj in r0.index:
                                val = r0.get(subj)
                                nv = convert_score_to_numeric(val, thrs)
                                if nv is not None:
                                    total_points += get_points_from_percentage(nv, subj)
                        points_row.append(str(total_points))
                    else:
                        points_row.append('-')
                if include_multi_exam_avg:
                    # Compute average points across exams
                    try:
                        numeric_pts = [float(x) for x in points_row[1:1+len(multiple_exams_data)] if str(x).replace('.','',1).isdigit()]
                        if numeric_pts:
                            points_row.append(f"{sum(numeric_pts)/len(numeric_pts):.{avg_decimals}f}")
                        else:
                            points_row.append('-')
                    except Exception:
                        points_row.append('-')
                if rank_in_multi:
                    points_row.append('')
                if include_comment_column:
                    points_row.append('')
                if include_teacher_column:
                    points_row.append('')
                subjects_data.append(points_row)
            
            # Row 2: Class Rank for each exam
            class_rank_row = ['Class Rank']
            for exam_data in multiple_exams_data:
                df_tmp = exam_data['exam_df']
                row_tmp = df_tmp[df_tmp['Name'] == student_name]
                if not row_tmp.empty:
                    r = row_tmp.iloc[0]
                    try:
                        valid_mask_e = df_tmp['Name'].astype(str).str.strip().ne("") & ~df_tmp['Name'].astype(str).str.lower().isin(['mean','total','average'])
                        student_class = str(r.get('Class','')).strip()
                        if student_class and 'Class' in df_tmp.columns:
                            class_mask_e = (df_tmp['Class'].astype(str).str.strip() == student_class) & valid_mask_e
                            class_total_e = int(class_mask_e.sum())
                        else:
                            class_total_e = ''
                    except Exception:
                        class_total_e = ''
                    class_rank_val = r.get('S/Rank', r.get('Rank', '-'))
                    class_rank = f"{class_rank_val}/{class_total_e}" if class_total_e != '' else str(class_rank_val)
                    class_rank_row.append(str(class_rank))
                else:
                    class_rank_row.append('-')
            if include_multi_exam_avg:
                # Calculate rank based on average mean across exams for student's class
                if avg_means:
                    try:
                        student_class = str(student_row.get('Class','')).strip()
                        # Collect all students' average means for ranking
                        class_avg_means = {}
                        valid_students = base_exam_df[
                            base_exam_df['Name'].astype(str).str.strip().ne("") & 
                            ~base_exam_df['Name'].astype(str).str.lower().isin(['mean','total','average'])
                        ]
                        if student_class and 'Class' in base_exam_df.columns:
                            valid_students = valid_students[valid_students['Class'].astype(str).str.strip() == student_class]
                        
                        for _, vstud in valid_students.iterrows():
                            vname = vstud['Name']
                            vmeans = []
                            for exam_data in multiple_exams_data:
                                vdf = exam_data['exam_df']
                                vrow = vdf[vdf['Name'] == vname]
                                if not vrow.empty:
                                    try:
                                        vmeans.append(float(vrow.iloc[0].get('Mean', 0)))
                                    except:
                                        pass
                            if vmeans:
                                class_avg_means[vname] = sum(vmeans) / len(vmeans)
                        
                        # Sort and find position
                        sorted_means = sorted(class_avg_means.values(), reverse=True)
                        student_avg_mean = sum(avg_means) / len(avg_means)
                        position = sorted_means.index(student_avg_mean) + 1
                        class_rank_row.append(f"{position}/{len(sorted_means)}")
                    except Exception:
                        class_rank_row.append('-')
                else:
                    class_rank_row.append('-')
            if rank_in_multi:
                class_rank_row.append('')
            if include_comment_column:
                class_rank_row.append('')
            if include_teacher_column:
                class_rank_row.append('')
            subjects_data.append(class_rank_row)
            
            # Row 3: Overall Rank for each exam
            overall_rank_row = ['Overall Rank']
            for exam_data in multiple_exams_data:
                df_tmp = exam_data['exam_df']
                row_tmp = df_tmp[df_tmp['Name'] == student_name]
                if not row_tmp.empty:
                    r = row_tmp.iloc[0]
                    try:
                        valid_mask_e = df_tmp['Name'].astype(str).str.strip().ne("") & ~df_tmp['Name'].astype(str).str.lower().isin(['mean','total','average'])
                        overall_total_e = int(valid_mask_e.sum())
                    except Exception:
                        overall_total_e = ''
                    overall_rank_val = r.get('Rank', '-')
                    overall_rank = f"{overall_rank_val}/{overall_total_e}" if overall_total_e != '' else str(overall_rank_val)
                    overall_rank_row.append(str(overall_rank))
                else:
                    overall_rank_row.append('-')
            if include_multi_exam_avg:
                # Calculate overall rank based on average mean across exams for all students
                if avg_means:
                    try:
                        # Collect all students' average means for ranking
                        overall_avg_means = {}
                        valid_students = base_exam_df[
                            base_exam_df['Name'].astype(str).str.strip().ne("") & 
                            ~base_exam_df['Name'].astype(str).str.lower().isin(['mean','total','average'])
                        ]
                        
                        for _, vstud in valid_students.iterrows():
                            vname = vstud['Name']
                            vmeans = []
                            for exam_data in multiple_exams_data:
                                vdf = exam_data['exam_df']
                                vrow = vdf[vdf['Name'] == vname]
                                if not vrow.empty:
                                    try:
                                        vmeans.append(float(vrow.iloc[0].get('Mean', 0)))
                                    except:
                                        pass
                            if vmeans:
                                overall_avg_means[vname] = sum(vmeans) / len(vmeans)
                        
                        # Sort and find position
                        sorted_means = sorted(overall_avg_means.values(), reverse=True)
                        student_avg_mean = sum(avg_means) / len(avg_means)
                        position = sorted_means.index(student_avg_mean) + 1
                        overall_rank_row.append(f"{position}/{len(sorted_means)}")
                    except Exception:
                        overall_rank_row.append('-')
                else:
                    overall_rank_row.append('-')
            if rank_in_multi:
                overall_rank_row.append('')
            if include_comment_column:
                overall_rank_row.append('')
            if include_teacher_column:
                overall_rank_row.append('')
            subjects_data.append(overall_rank_row)
            
            # Calculate column widths dynamically (num_exams already defined above)
            subject_col_width = 1.2*inch
            teacher_col_width = 0.7*inch if include_teacher_column else 0
            remaining_width = 5.5*inch - teacher_col_width
            # Extra columns: Avg, Rank, Comment (optional), and Teacher (optional)
            extra_cols = (1 if include_multi_exam_avg else 0) + (1 if rank_in_multi else 0) + (1 if include_comment_column else 0) + (1 if include_teacher_column else 0)
            denom = max(1, num_exams + extra_cols)
            exam_col_width = remaining_width / denom
            # Minimum clamp to avoid zero width in extreme cases
            if exam_col_width < 0.35*inch:
                exam_col_width = 0.35*inch
            col_widths = [subject_col_width]
            col_widths.extend([exam_col_width] * num_exams)
            if include_multi_exam_avg:
                col_widths.append(exam_col_width)
            if rank_in_multi:
                col_widths.append(exam_col_width)
            if include_comment_column:
                col_widths.append(exam_col_width)
            if include_teacher_column:
                col_widths.append(teacher_col_width)
            
        else:
            # Single exam table (compact) - teacher column at end before Comment
            header = ['Subject', 'Score']
            if include_subject_rank:
                header.append('Rank')
            if include_comment_column:
                header.append('Comment')
            if include_teacher_column:
                header.append('Teacher')
            subjects_data = [header]
            
            for subject in subject_cols:
                if subject in student_row.index:
                    score = student_row[subject]
                    
                    # Get teacher name if enabled
                    teacher_name = 'N/A'
                    if include_teacher_column:
                        if 'Teacher' in student_row.index:
                            teacher_name = str(student_row.get('Teacher', 'N/A'))[:10]
                        elif f'{subject}_Teacher' in student_row.index:
                            teacher_name = str(student_row.get(f'{subject}_Teacher', 'N/A'))[:10]
                    
                    # Calculate subject rank (optional)
                    subject_rank = '-'
                    if include_subject_rank:
                        try:
                            thrs = settings.get('thresholds', {})
                            subject_scores_series = exam_df[subject]
                            numeric_scores = subject_scores_series.apply(lambda x: convert_score_to_numeric(x, thrs))
                            numeric_scores = numeric_scores.dropna().astype(float)
                            sorted_scores = numeric_scores.sort_values(ascending=False)
                            score_numeric = convert_score_to_numeric(score, thrs)
                            if score_numeric is not None and len(sorted_scores) > 0:
                                position = list(sorted_scores.values).index(score_numeric) + 1
                                subject_rank = f"{position}/{len(sorted_scores)}"
                        except Exception:
                            pass
                    
                    # Generate comment based on score (handle graded marks)
                    thrs = settings.get('thresholds', {})
                    thr_ex = thrs.get('excellent', 80)
                    thr_vg = thrs.get('vgood', 70)
                    thr_g = thrs.get('good', 60)
                    thr_av = thrs.get('average', 50)
                    
                    comment = ''
                    # Check if subject should be excluded from comments first
                    comp_subjects = settings.get('effective_component_subjects', []) or []
                    no_comment_list = settings.get('no_comment_subjects', []) or []
                    should_skip_comment = subject in comp_subjects or subject in no_comment_list
                    
                    if auto_fill_subject_comments and not should_skip_comment:
                        score_numeric = convert_score_to_numeric(score, thrs)
                        if score_numeric is not None:
                            if score_numeric >= thr_ex:
                                comment = "Excellent"
                            elif score_numeric >= thr_vg:
                                comment = "V.Good"
                            elif score_numeric >= thr_g:
                                comment = "Good"
                            elif score_numeric >= thr_av:
                                comment = "Average"
                            else:
                                comment = "Improve"
                        else:
                            comment = ""
                        # Apply custom comment ranges if provided (only if not excluded)
                        if settings.get('comment_mode') == 'Ranges' and settings.get('comment_bands') and score_numeric is not None:
                            comment = get_remark_from_bands(score_numeric, thrs, {}, settings.get('comment_bands')) or comment
                    
                    # Build row with teacher at end before Comment
                    base_row = [subject, str(score)]
                    if include_subject_rank:
                        base_row.append(str(subject_rank))
                    if include_comment_column:
                        base_row.append(comment)
                    if include_teacher_column:
                        tname = '' if not auto_fill_teacher_names else teacher_name
                        base_row.append(tname)
                    subjects_data.append(base_row)
            
            # Add single exam summary rows to subjects table respecting toggles
            if settings.get('include_total_row', True):
                total_label_row = ['Total']
                total_label_row.append(str(student_row.get('Total', 'N/A')))
                if include_subject_rank:
                    total_label_row.append('')
                if include_comment_column:
                    total_label_row.append('')
                if include_teacher_column:
                    total_label_row.append('')
                subjects_data.append(total_label_row)

            if settings.get('include_mean_row_single_exam', True) and settings.get('include_mean_row', True):
                mean_label_row = ['Mean']
                mean_label_row.append(str(student_row.get('Mean', 'N/A')))
                if include_subject_rank:
                    mean_label_row.append('')
                if include_comment_column:
                    mean_label_row.append('')
                if include_teacher_column:
                    mean_label_row.append('')
                subjects_data.append(mean_label_row)

            if settings.get('include_points_row', True):
                thrs = settings.get('thresholds', {})
                total_points = 0
                for subj in subject_cols:
                    if subj in student_row.index:
                        nv = convert_score_to_numeric(student_row.get(subj), thrs)
                        if nv is not None:
                            total_points += get_points_from_percentage(nv, subj)
                points_row = ['Points', str(total_points)]
                if include_subject_rank:
                    points_row.append('')
                if include_comment_column:
                    points_row.append('')
                if include_teacher_column:
                    points_row.append('')
                subjects_data.append(points_row)

            if settings.get('include_grade_row', True):
                grade_label_row = ['Grade']
                grade_label_row.append(str(student_row.get('Mean Grade', 'N/A')))
                if include_subject_rank:
                    grade_label_row.append('')
                if include_comment_column:
                    grade_label_row.append('')
                if include_teacher_column:
                    grade_label_row.append('')
                subjects_data.append(grade_label_row)
            
            # Determine column widths based on included columns to ensure Teacher column is always last
            if include_subject_rank and include_teacher_column and include_comment_column:
                col_widths = [2.2*inch, 0.9*inch, 1.0*inch, 0.8*inch, 1.2*inch]
            elif include_subject_rank and include_teacher_column and not include_comment_column:
                col_widths = [2.8*inch, 0.9*inch, 1.0*inch, 1.3*inch]
            elif include_subject_rank and not include_teacher_column and include_comment_column:
                col_widths = [2.4*inch, 0.9*inch, 1.0*inch, 1.7*inch]
            elif include_subject_rank and not include_teacher_column and not include_comment_column:
                col_widths = [3.4*inch, 0.9*inch, 1.2*inch]
            elif not include_subject_rank and include_teacher_column and include_comment_column:
                col_widths = [2.8*inch, 0.9*inch, 1.7*inch, 1.1*inch]
            elif not include_subject_rank and include_teacher_column and not include_comment_column:
                col_widths = [3.3*inch, 0.9*inch, 1.5*inch]
            elif not include_subject_rank and not include_teacher_column and include_comment_column:
                col_widths = [3.0*inch, 0.9*inch, 2.1*inch]
            else:
                col_widths = [3.6*inch, 0.9*inch]
        
        # Build final subjects table
        subjects_table = Table(subjects_data, colWidths=col_widths)
        header_color = colors.HexColor(table_header_color)
        header_font = 9 if len(subjects_data[0]) <= 10 else 8
        body_font = 8 if len(subjects_data[0]) <= 10 else 7
        # Determine how many subject rows (for alternating background)
        num_rows = len(subjects_data)
        num_subject_rows = len(subject_cols)
        base_style = [
            ('TEXTCOLOR', (0, 0), (-1, 0), header_color),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), header_font),
            ('FONTSIZE', (0, 1), (-1, -1), body_font),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            # Remove alternating row backgrounds for full transparency
            # ('ROWBACKGROUNDS', (0, 1), (-1, num_subject_rows), [colors.white, colors.HexColor('#F5F5F5')]),
        ]
        if num_subject_rows < num_rows - 1:
            base_style.extend([
                # Remove summary rows background fill for transparency
                # ('BACKGROUND', (0, num_subject_rows + 1), (-1, -1), colors.HexColor('#E8F4F8')),
                ('FONTNAME', (0, num_subject_rows + 1), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, num_subject_rows + 1), (-1, -1), body_font),
            ])
        subjects_table.setStyle(TableStyle(base_style))
        sections['Academic Performance'].extend([subjects_table, Spacer(1,0.03*inch)])

        # Compute student's overall numeric total (single or multi-exam) for teacher remarks
        def _compute_overall_total():
            thrs = settings.get('thresholds', {})
            # Single-exam
            if not (multiple_exams_data and len(multiple_exams_data) > 0):
                try:
                    tot = student_row.get('Total', None)
                    totn = convert_score_to_numeric(tot, thrs)
                    if totn is not None:
                        return float(totn)
                except Exception:
                    pass
                # Fallback compute from subjects
                vals = []
                for s in subject_cols:
                    if s in student_row.index:
                        nv = convert_score_to_numeric(student_row.get(s), thrs)
                        if nv is not None:
                            vals.append(float(nv))
                return sum(vals) if vals else None
            # Multi-exam: average of per-exam totals
            per_exam_totals = []
            for exam_data in multiple_exams_data:
                df_tmp = exam_data['exam_df']
                row_tmp = df_tmp[df_tmp['Name'] == student_name]
                thrs = settings.get('thresholds', {})
                if not row_tmp.empty:
                    tot = row_tmp.iloc[0].get('Total', None)
                    totn = convert_score_to_numeric(tot, thrs)
                    if totn is not None:
                        per_exam_totals.append(float(totn))
                        continue
                # Fallback compute total for that exam
                if not row_tmp.empty:
                    r0 = row_tmp.iloc[0]
                    vals = []
                    for s in subject_cols:
                        if s in r0.index:
                            nv = convert_score_to_numeric(r0.get(s), thrs)
                            if nv is not None:
                                vals.append(float(nv))
                    if vals:
                        per_exam_totals.append(sum(vals))
            return (sum(per_exam_totals)/len(per_exam_totals)) if per_exam_totals else None

        overall_total_numeric = _compute_overall_total()

        # Helper function to get teacher comment based on total marks ranges
        def get_teacher_comment_from_total(total, ranges, texts):
            """Get teacher comment based on total marks ranges."""
            if total is None:
                return ''
            try:
                total_val = float(total)
                # Check ranges in descending order (excellent -> average -> improve)
                if total_val >= ranges.get('excellent', 800):
                    return texts.get('excellent', '')
                elif total_val >= ranges.get('vgood', 700):
                    return texts.get('vgood', '')
                elif total_val >= ranges.get('good', 600):
                    return texts.get('good', '')
                elif total_val >= ranges.get('average', 500):
                    return texts.get('average', '')
                else:
                    return texts.get('improve', '')
            except Exception:
                return ''

        # Teacher Comments Section: horizontal table layout (label beside comment)
        if settings.get('include_class_teacher', True):
            teacher_comment = settings.get('teacher_comment','').strip()
            auto_ct = settings.get('auto_class_teacher_remarks', True)
            ct_ranges = {
                'excellent': settings.get('ct_ex_min', 800),
                'vgood': settings.get('ct_vg_min', 700),
                'good': settings.get('ct_g_min', 600),
                'average': settings.get('ct_av_min', 500),
            }
            ct_texts = settings.get('class_teacher_texts', {})
            auto_text = get_teacher_comment_from_total(overall_total_numeric, ct_ranges, ct_texts) if auto_ct else ''
            chosen_comment = teacher_comment or auto_text or ''
            
            # Build comment table: two rows -> row1 label+comment with underline, row2 empty label + signature below line
            ct_label = "CLASS TEACHER COMMENT:"
            ct_sig = f"Signature: _____________  Name: {settings.get('class_teacher','')}"
            ct_comment_text = chosen_comment if chosen_comment else ''
            
            ct_table = Table([[ct_label, ct_comment_text], ['', ct_sig]], colWidths=[1.8*inch, 4.8*inch])
            ct_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, 1), 'LEFT'),
                ('LINEBELOW', (1, 0), (1, 0), 0.7, colors.black),
                ('TOPPADDING', (0, 0), (-1, 0), 2),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
                ('TOPPADDING', (0, 1), (-1, 1), 2),
                ('BOTTOMPADDING', (0, 1), (-1, 1), 2),
            ]))
            sections['Comments'].append(ct_table)
            sections['Comments'].append(Spacer(1, 0.03*inch))

        if settings.get('include_head_teacher', True):
            head_comment = settings.get('head_teacher_comment','').strip()
            auto_ht = settings.get('auto_head_teacher_remarks', True)
            ht_ranges = {
                'excellent': settings.get('ht_ex_min', 800),
                'vgood': settings.get('ht_vg_min', 700),
                'good': settings.get('ht_g_min', 600),
                'average': settings.get('ht_av_min', 500),
            }
            ht_texts = settings.get('head_teacher_texts', {})
            auto_text_h = get_teacher_comment_from_total(overall_total_numeric, ht_ranges, ht_texts) if auto_ht else ''
            chosen_head_comment = head_comment or auto_text_h or ''
            
            # Build comment table: two rows -> row1 label+comment with underline, row2 empty label + signature below line
            ht_label = "HEAD TEACHER COMMENT:"
            ht_sig = f"Signature: _____________  Name: {settings.get('head_teacher','')}"
            ht_comment_text = chosen_head_comment if chosen_head_comment else ''
            
            ht_table = Table([[ht_label, ht_comment_text], ['', ht_sig]], colWidths=[1.8*inch, 4.8*inch])
            ht_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, 1), 'LEFT'),
                ('LINEBELOW', (1, 0), (1, 0), 0.7, colors.black),
                ('TOPPADDING', (0, 0), (-1, 0), 2),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
                ('TOPPADDING', (0, 1), (-1, 1), 2),
                ('BOTTOMPADDING', (0, 1), (-1, 1), 2),
            ]))
            sections['Comments'].append(ht_table)
            sections['Comments'].append(Spacer(1, 0.03*inch))
        
        # Multi-exam footnote removed per user request (no average explanatory note)

        # Stamp (right-aligned) - image or rectangular placeholder
        from reportlab.graphics.shapes import Drawing, Rect, String
        if settings.get('stamp_path') and os.path.exists(settings['stamp_path']):
            try:
                stamp_flow = Image(settings['stamp_path'], width=1.2*inch, height=0.9*inch)
            except Exception:
                stamp_flow = None
        else:
            d = Drawing(86, 64)  # ~1.2in x 0.9in rectangle
            d.add(Rect(0, 0, 86, 64, strokeColor=colors.grey, fillColor=None, strokeWidth=1))
            d.add(String(43, 32, 'SCHOOL STAMP', textAnchor='middle', fontSize=7))
            stamp_flow = d
        if stamp_flow:
            stamp_wrap = Table([['', stamp_flow]], colWidths=[5.2*inch, 1.2*inch])
            stamp_wrap.setStyle(TableStyle([
                ('ALIGN', (1,0), (1,0), 'RIGHT'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
            ]))
            sections['Footer'].append(stamp_wrap)
        sections['Footer'].append(Spacer(1, 0.05*inch))

        # Bottom section with dates after stamp
        bottom_data = [
            ['Opening Day:', settings.get('opening_date', 'N/A'), 'Closing Day:', settings.get('closing_date', 'N/A')],
        ]
        bottom_table = Table(bottom_data, colWidths=[1*inch, 2*inch, 1*inch, 2*inch])
        bottom_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 6),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ]))
        sections['Footer'].append(bottom_table)
        sections['Footer'].append(Spacer(1,0.05*inch))
        
        # Footer (compact)        sections['Footer'].append(Spacer(1,0.05*inch))
        
        # Footer (compact)
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=5,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
        footer_text = "EDUSCORE ANALYTICS | Developed by Munyua Kamau | © 2025"
        footer_para = Paragraph(footer_text, footer_style)
        sections['Footer'].append(footer_para)

        # Determine order - Updated flow: Header → Student Info → Grading Key → Academic Performance → Comments → Footer
        # Grading Key is placed directly after Student Info per request
        default_order = ['Header', 'Student Info', 'Grading Key', 'Academic Performance', 'Comments', 'Footer']
        order_positions = settings.get('section_order_positions', {}) or {}
        try:
            # Lock Header, Student Info, and Grading Key at top
            fixed_sections = ['Header', 'Student Info', 'Grading Key']
            # Allow customization of remaining middle sections only
            middle_sections = ['Academic Performance', 'Comments']
            middle_sorted = sorted(middle_sections, key=lambda x: order_positions.get(x, default_order.index(x)+1))
            # Footer is always last
            final_order = fixed_sections + middle_sorted + ['Footer']
        except Exception:
            final_order = ['Header', 'Student Info', 'Grading Key', 'Academic Performance', 'Comments', 'Footer']
        if idx > 0:
            story.append(PageBreak())
        for sec_name in final_order:
            story.extend(sections.get(sec_name, []))
    
    # Draw watermark on each page using ReportLab's page callbacks to ensure it appears
    def _draw_on_page(canvas_obj, doc_obj):
        try:
            # Use canvas.getPageNumber() to pass to the watermark helper (if needed)
            page_num = 0
            try:
                page_num = canvas_obj.getPageNumber()
            except Exception:
                page_num = 0
            add_watermark_to_canvas(canvas_obj, page_num, watermark_settings)
        except Exception:
            # Don't fail PDF generation if watermark drawing fails
            pass

    doc.build(story, onFirstPage=_draw_on_page, onLaterPages=_draw_on_page)
    buffer.seek(0)
    return buffer

# Custom CSS for report cards
st.markdown("""
    <style>
    /* Modern gradient background */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }
    
    /* Header styling */
    .main-header {
        text-align: center;
        font-size: 2.5rem;
        font-weight: 900;
        color: #0E6BA8;
        margin: 2rem 0;
        padding: 1rem;
        background: white;
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    
    /* Section headers */
    .section-header {
        font-size: 1.5rem;
        font-weight: 700;
        color: #2c3e50;
        margin: 1.5rem 0 1rem 0;
        padding: 0.5rem;
        border-left: 5px solid #0E6BA8;
        background: white;
        border-radius: 5px;
    }
    
    /* Report card styling */
    .report-card {
        background: white;
        padding: 2rem;
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        margin: 1rem 0;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize session state
if 'saved_exams' not in st.session_state:
    st.session_state.saved_exams = []
if 'saved_exam_data' not in st.session_state:
    st.session_state.saved_exam_data = {}
if 'saved_exam_raw_data' not in st.session_state:
    st.session_state.saved_exam_raw_data = {}
if 'saved_exam_configs' not in st.session_state:
    st.session_state.saved_exam_configs = {}

# Load exams from disk on first run
if 'report_cards_loaded' not in st.session_state:
    load_all_exams_into_session()
    st.session_state.report_cards_loaded = True

# Load report card settings into session state
if 'report_settings' not in st.session_state:
    st.session_state.report_settings = load_report_settings()
else:
    # Ensure any newly added default keys exist
    _defaults = get_default_report_settings()
    for _k, _v in _defaults.items():
        if _k not in st.session_state.report_settings:
            st.session_state.report_settings[_k] = _v

# Header
st.markdown('<div class="main-header">📄 Student Report Cards</div>', unsafe_allow_html=True)

# Back to home button
col1, col2, col3 = st.columns([2, 6, 2])
with col1:
    if st.button("🏠 Back to Home", use_container_width=True, type="primary"):
        st.session_state.current_page = 'home'
        st.session_state.show_home_header = True
        # avoid calling st.rerun() inside the button callback


# Main content
st.markdown('<div class="section-header">Generate Report Cards</div>', unsafe_allow_html=True)

if len(st.session_state.saved_exams) == 0:
    st.info("📋 No exams available. Please save an exam first before generating report cards.")
else:
    # Multi-exam feature
    st.markdown("#### 📊 Report Card Mode")
    report_mode_options = ["Single Exam Report", "Multi-Exam Report (Compare multiple exams)"]
    _saved_report_mode = st.session_state.report_settings.get('report_mode', report_mode_options[0])
    _report_mode_index = report_mode_options.index(_saved_report_mode) if _saved_report_mode in report_mode_options else 0
    report_mode = st.radio(
        "Select mode:",
        options=report_mode_options,
        index=_report_mode_index,
        horizontal=True
    )
    
    if report_mode == "Single Exam Report":
        # Select single exam
        st.markdown("#### Select Exam")
        exam_names = [exam.get('exam_name', f"Exam {i+1}") for i, exam in enumerate(st.session_state.saved_exams)]
        selected_exam_name = st.selectbox("Choose exam for report cards:", options=exam_names)
        
        if selected_exam_name:
            # Get exam data
            selected_exam_obj = next((e for e in st.session_state.saved_exams if e.get('exam_name') == selected_exam_name), None)
            
            if selected_exam_obj:
                exam_id = selected_exam_obj.get('exam_id')
                exam_df = st.session_state.saved_exam_data.get(exam_id)
                
                if isinstance(exam_df, pd.DataFrame) and not exam_df.empty:
                    st.success(f"✅ Loaded: {selected_exam_name}")
                    multiple_exams_data = None  # Single exam mode
    
    else:  # Multi-Exam Report
        st.markdown("#### Select Multiple Exams")
        st.info("💡 Select 2 or more exams to compare student performance across different exams. More columns will auto-shrink to fit.")

        # Ask for Year and Class, then filter available exams
        all_meta = st.session_state.get('saved_exams', []) or []
        # Collect unique years from metadata; fallback to current year if missing
        from datetime import datetime as _dt
        years = sorted({m.get('year', _dt.now().year) for m in all_meta}, reverse=True)
        sel_year = st.selectbox("Year:", options=years, index=0)

        # Helper: canonicalize class names (collapse variants like 'Grade 9', 'GRADE NINE', 'gr 9')
        def _canonical_class(raw):
            """Normalize class names to standard format (e.g., 'Grade 9')"""
            if not raw:
                return 'Unknown'
            
            class_str = str(raw).strip().lower()
            
            # Number word mappings
            number_words = {
                'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5',
                'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10',
                'eleven': '11', 'twelve': '12'
            }
            
            # Replace number words with digits
            for word, digit in number_words.items():
                class_str = class_str.replace(word, digit)
            
            # Extract grade number (look for digits)
            match = re.search(r'\d+', class_str)
            
            if match:
                grade_num = match.group()
                return f"Grade {grade_num}"
            
            # If no number found, capitalize first letter of each word
            return ' '.join(word.capitalize() for word in class_str.split())

        # Filter classes by selected year using canonical form
        classes_for_year_raw = [m.get('class_name', '').strip() for m in all_meta if m.get('year', None) == sel_year and str(m.get('class_name','')).strip()]
        canonical_map = {}
        for c in classes_for_year_raw:
            canon = _canonical_class(c)
            canonical_map.setdefault(canon, set()).add(c)
        classes_for_year = sorted(canonical_map.keys())
        class_options = ["All Classes"] + classes_for_year if classes_for_year else ["All Classes"]
        sel_class = st.selectbox("Class:", options=class_options, index=0)

        # Build filtered exam list
        filtered = [m for m in all_meta if m.get('year', None) == sel_year]
        if sel_class != "All Classes":
            # Match any raw variant mapping to selected canonical class
            raw_variants = canonical_map.get(sel_class, set())
            filtered = [m for m in filtered if _canonical_class(m.get('class_name','').strip()) == sel_class or m.get('class_name','').strip() in raw_variants]
        exam_names = [m.get('exam_name', f"Exam {i+1}") for i, m in enumerate(filtered)]

        selected_exam_names = st.multiselect(
            "Choose exams to include in report card:",
            options=exam_names
        )
        
        if len(selected_exam_names) >= 2:
            st.success(f"✅ Selected {len(selected_exam_names)} exams for comparison")
            
            # Load all selected exams
            multiple_exams_data = []
            selected_exam_name = selected_exam_names[0]  # Use first exam as base
            
            for exam_name in selected_exam_names:
                # search within filtered set first, then fallback
                exam_obj = next((e for e in filtered if e.get('exam_name') == exam_name), None)
                if exam_obj is None:
                    exam_obj = next((e for e in st.session_state.saved_exams if e.get('exam_name') == exam_name), None)
                if exam_obj:
                    exam_id = exam_obj.get('exam_id')
                    exam_df_temp = st.session_state.saved_exam_data.get(exam_id)
                    if isinstance(exam_df_temp, pd.DataFrame) and not exam_df_temp.empty:
                        multiple_exams_data.append({
                            'name': exam_name,
                            'exam_df': exam_df_temp,
                            'exam_id': exam_id
                        })
            
            # Use first exam as base for student list
            selected_exam_obj = next((e for e in st.session_state.saved_exams if e.get('exam_name') == selected_exam_names[0]), None)
            exam_id = selected_exam_obj.get('exam_id')
            exam_df = st.session_state.saved_exam_data.get(exam_id)
            
        elif len(selected_exam_names) == 1:
            st.warning("⚠️ Please select at least 2 exams for multi-exam report")
            selected_exam_name = None
            exam_df = None
            multiple_exams_data = None
        else:
            selected_exam_name = None
            exam_df = None
            multiple_exams_data = None
    
    if 'selected_exam_name' in locals() and selected_exam_name and isinstance(exam_df, pd.DataFrame) and not exam_df.empty:
        
        # Extract settings from session state (excluding school info which is now on the page)
        settings = st.session_state.report_settings
        class_teacher = settings.get('class_teacher', '')
        head_teacher = settings.get('head_teacher', '')
        main_title_color = settings.get('main_title_color', '#0E6BA8')
        section_title_color = settings.get('section_title_color', '#2c3e50')
        table_header_color = settings.get('table_header_color', '#0E6BA8')
        include_subject_rank = settings.get('include_subject_rank', True)
        include_multi_exam_avg = settings.get('include_multi_exam_avg', True)
        avg_decimal_places = settings.get('avg_decimal_places', 1)
        rank_in_multi = settings.get('rank_in_multi', True)
        ranking_exam_name = settings.get('ranking_exam_name', '')
        comment_basis = settings.get('comment_basis', 'Base exam score')
        avg_explanation = settings.get('avg_explanation', '')
        grading_table_text = settings.get('grading_table_text', '')
        include_class_teacher = settings.get('include_class_teacher', True)
        include_head_teacher = settings.get('include_head_teacher', True)
        include_teacher_column = settings.get('include_teacher_column', False)
        auto_class_teacher_remarks = settings.get('auto_class_teacher_remarks', True)
        auto_head_teacher_remarks = settings.get('auto_head_teacher_remarks', True)
        thr_excellent = settings.get('thr_excellent', 80.0)
        thr_vgood = settings.get('thr_vgood', 70.0)
        thr_good = settings.get('thr_good', 60.0)
        thr_average = settings.get('thr_average', 50.0)
        class_teacher_text_ex = settings.get('class_teacher_text_ex', 'Excellent!')
        class_teacher_text_vg = settings.get('class_teacher_text_vg', 'Very good.')
        class_teacher_text_g = settings.get('class_teacher_text_g', 'Good.')
        class_teacher_text_av = settings.get('class_teacher_text_av', 'Average.')
        class_teacher_text_im = settings.get('class_teacher_text_im', 'Improve.')
        head_teacher_text_ex = settings.get('head_teacher_text_ex', 'Outstanding!')
        head_teacher_text_vg = settings.get('head_teacher_text_vg', 'Very good.')
        head_teacher_text_g = settings.get('head_teacher_text_g', 'Good.')
        head_teacher_text_av = settings.get('head_teacher_text_av', 'Average.')
        head_teacher_text_im = settings.get('head_teacher_text_im', 'Improve.')
        order_header = settings.get('section_order_header', 1)
        order_key = settings.get('section_order_grading', 2)
        order_info = settings.get('section_order_student', 3)
        order_academic = settings.get('section_order_academic', 4)
        order_comments = settings.get('section_order_comments', 5)
        order_footer = settings.get('section_order_footer', 6)
        no_comment_subjects = settings.get('no_comment_subjects', [])
        
        # Multi-exam specific settings
        if report_mode.startswith("Multi-Exam") and multiple_exams_data:
            available_exam_names = [e['name'] for e in multiple_exams_data]
            if ranking_exam_name not in available_exam_names and available_exam_names:
                ranking_exam_name = available_exam_names[0]
                st.session_state.report_settings['ranking_exam_name'] = ranking_exam_name
        
        # Subjects selector moved to settings modal (no duplication here)
        
    # Optional file uploads
    st.markdown("#### 📸 Optional Attachments")
    col1, col2, col3 = st.columns(3)
    with col1:
        logo_file = st.file_uploader("Left Logo (PNG/JPG):", type=['png', 'jpg', 'jpeg'])
    with col2:
        logo2_file = st.file_uploader("Right Logo (PNG/JPG):", type=['png', 'jpg', 'jpeg'])
    with col3:
        stamp_file = st.file_uploader("School Stamp (PNG/JPG):", type=['png', 'jpg', 'jpeg'])
    
    # Save uploaded files temporarily
    logo_path = None
    logo2_path = None
    stamp_path = None
    
    if logo_file:
        try:
            b = logo_file.getbuffer()
            name = os.path.join('report_cards', f"{uuid4().hex}_{logo_file.name}")
            storage.write_bytes(name, bytes(b), content_type='image/png')
            logo_path = name
        except Exception:
            logo_path = None
    
    if logo2_file:
        try:
            b = logo2_file.getbuffer()
            name = os.path.join('report_cards', f"{uuid4().hex}_{logo2_file.name}")
            storage.write_bytes(name, bytes(b), content_type='image/png')
            logo2_path = name
        except Exception:
            logo2_path = None
    
    if stamp_file:
        try:
            b = stamp_file.getbuffer()
            name = os.path.join('report_cards', f"{uuid4().hex}_{stamp_file.name}")
            storage.write_bytes(name, bytes(b), content_type='image/png')
            stamp_path = name
        except Exception:
            stamp_path = None

    # Fallback to previously saved attachments when no new upload occurred
    try:
        saved = st.session_state.get('report_settings', {}) or {}
        used_saved = []
        if not logo_path:
            sp = saved.get('logo_path', '')
            try:
                if sp and storage.exists(sp):
                    logo_path = sp
                    used_saved.append(f"Left Logo: {os.path.basename(sp)}")
                elif sp and os.path.exists(sp):
                    logo_path = sp
                    used_saved.append(f"Left Logo: {os.path.basename(sp)}")
            except Exception:
                # fallback to local path check
                try:
                    if sp and os.path.exists(sp):
                        logo_path = sp
                        used_saved.append(f"Left Logo: {os.path.basename(sp)}")
                except Exception:
                    pass
        if not logo2_path:
            sp2 = saved.get('logo2_path', '')
            try:
                if sp2 and storage.exists(sp2):
                    logo2_path = sp2
                    used_saved.append(f"Right Logo: {os.path.basename(sp2)}")
                elif sp2 and os.path.exists(sp2):
                    logo2_path = sp2
                    used_saved.append(f"Right Logo: {os.path.basename(sp2)}")
            except Exception:
                try:
                    if sp2 and os.path.exists(sp2):
                        logo2_path = sp2
                        used_saved.append(f"Right Logo: {os.path.basename(sp2)}")
                except Exception:
                    pass
        if not stamp_path:
            sps = saved.get('stamp_path', '')
            try:
                if sps and storage.exists(sps):
                    stamp_path = sps
                    used_saved.append(f"Stamp: {os.path.basename(sps)}")
                elif sps and os.path.exists(sps):
                    stamp_path = sps
                    used_saved.append(f"Stamp: {os.path.basename(sps)}")
            except Exception:
                try:
                    if sps and os.path.exists(sps):
                        stamp_path = sps
                        used_saved.append(f"Stamp: {os.path.basename(sps)}")
                except Exception:
                    pass
        if used_saved:
            st.caption("Using saved attachments • " + " | ".join(used_saved))
    except Exception:
        pass

    # Show small previews of the attachments currently in use + quick remove actions
    with st.container():
        st.markdown("###### Current attachments in use")
        pcol1, pcol2, pcol3 = st.columns(3)
        def _preview_img(col, path, label, remove_key, settings_key):
            with col:
                try:
                    displayed = False
                    try:
                        if path:
                            if storage is not None and storage.exists(path):
                                b = storage.read_bytes(path)
                                if b:
                                    st.image(b, caption=f"{label}", width=120)
                                    displayed = True
                            elif os.path.exists(path):
                                st.image(path, caption=f"{label}", width=120)
                                displayed = True
                    except Exception:
                        displayed = False
                    if displayed:
                        if st.button(f"Remove {label}", key=remove_key):
                            try:
                                st.session_state.report_settings[settings_key] = ''
                            except Exception:
                                pass
                            return ''
                    else:
                        st.caption(f"{label}: none")
                except Exception:
                    st.caption(f"{label}: (unavailable)")
            return path
        # Apply previews and allow user to clear
        logo_path = _preview_img(pcol1, logo_path, 'Left Logo', 'rm_left_logo', 'logo_path')
        logo2_path = _preview_img(pcol2, logo2_path, 'Right Logo', 'rm_right_logo', 'logo2_path')
        stamp_path = _preview_img(pcol3, stamp_path, 'Stamp', 'rm_stamp', 'stamp_path')
    
    # School Information (persisted)
    st.markdown("#### 🏫 School Information")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        school_name = st.text_input("School Name:", value=st.session_state.report_settings.get('school_name','Your School Name'))
        motto = st.text_input("School Motto:", value=st.session_state.report_settings.get('motto','Knowledge is Power'))
        email = st.text_input("School Email:", value=st.session_state.report_settings.get('email','info@school.com'))
    with col_s2:
        term = st.text_input("Term:", value=st.session_state.report_settings.get('term','Term 1'))
        year = st.number_input("Year:", min_value=2020, max_value=2030, value=int(st.session_state.report_settings.get('year', 2025)), step=1)
        col_date1, col_date2 = st.columns(2)
        with col_date1:
            # parse stored date if present
            _od = st.session_state.report_settings.get('opening_date')
            try:
                _od_val = datetime.strptime(_od, '%d/%m/%Y').date() if isinstance(_od, str) else datetime.now().date()
            except Exception:
                _od_val = datetime.now().date()
            opening_date = st.date_input("Opening Date:", value=_od_val)
        with col_date2:
            _cd = st.session_state.report_settings.get('closing_date')
            try:
                _cd_val = datetime.strptime(_cd, '%d/%m/%Y').date() if isinstance(_cd, str) else datetime.now().date()
            except Exception:
                _cd_val = datetime.now().date()
            closing_date = st.date_input("Closing Date:", value=_cd_val)
    
    # Teacher comments UI removed (per request); keep empty defaults
    teacher_comment = ""
    head_teacher_comment = ""

    # Configuration options - Always visible regardless of report type
    st.markdown("#### 🏷️ Comment Thresholds")
    mode_options = ["Simple (≥ thresholds)", "Ranges (min/max per band)"]
    _saved_mode = st.session_state.report_settings.get('comment_mode', mode_options[0])
    mode_index = mode_options.index(_saved_mode) if _saved_mode in mode_options else 0
    mode_choice = st.radio("Mode:", mode_options, index=mode_index, horizontal=True)
    comment_bands = []
    if mode_choice == "Simple (≥ thresholds)":
        colt1, colt2, colt3, colt4 = st.columns(4)
        with colt1:
            thr_excellent = st.number_input("Excellent ≥", min_value=0.0, max_value=100.0, value=float(st.session_state.report_settings.get('thr_excellent',80.0)), step=1.0)
        with colt2:
            thr_vgood = st.number_input("V.Good ≥", min_value=0.0, max_value=100.0, value=float(st.session_state.report_settings.get('thr_vgood',70.0)), step=1.0)
        with colt3:
            thr_good = st.number_input("Good ≥", min_value=0.0, max_value=100.0, value=float(st.session_state.report_settings.get('thr_good',60.0)), step=1.0)
        with colt4:
            thr_average = st.number_input("Average ≥", min_value=0.0, max_value=100.0, value=float(st.session_state.report_settings.get('thr_average',50.0)), step=1.0)
    else:
        st.caption("Define custom comment bands. Use Max as lower bound and Min as upper bound (e.g., Max=80, Min=100 → 80-100).")
        import pandas as _pd
        saved_bands = st.session_state.report_settings.get('comment_bands', [])
        if saved_bands:
            default_bands = _pd.DataFrame([
                {"Label": b.get('label',''), "Min": int(b.get('min',0)), "Max": int(b.get('max',0)), "Text": b.get('text','')}
                for b in saved_bands
            ])
        else:
            default_bands = _pd.DataFrame([
                {"Label":"Excellent","Min":100,"Max":80,"Text":"Excellent performance!"},
                {"Label":"V.Good","Min":79,"Max":70,"Text":"Very good work."},
                {"Label":"Good","Min":69,"Max":60,"Text":"Good effort."},
                {"Label":"Average","Min":59,"Max":50,"Text":"Average performance."},
                {"Label":"Improve","Min":49,"Max":0,"Text":"Needs improvement."},
            ])
        band_cfg = {
            "Label": st.column_config.TextColumn("Label", width="small"),
            "Min": st.column_config.NumberColumn("Min % (upper)", min_value=0, max_value=100, step=1, format="%d"),
            "Max": st.column_config.NumberColumn("Max % (lower)", min_value=0, max_value=100, step=1, format="%d"),
            "Text": st.column_config.TextColumn("Comment Text", width="large"),
        }
        edited_bands = st.data_editor(default_bands, use_container_width=True, hide_index=True, num_rows="dynamic", column_config=band_cfg, key="comment_bands_builder")
        # Clean into list of dicts following grading semantics
        try:
            for _, r in edited_bands.iterrows():
                label = str(r.get("Label"," ")).strip()
                if not label:
                    continue
                try:
                    upper = float(r.get("Min", 0))
                    lower = float(r.get("Max", 0))
                except Exception:
                    upper, lower = 0.0, 0.0
                text_val = str(r.get("Text"," ")).strip()
                # Ensure lower <= upper
                if lower > upper:
                    lower, upper = upper, lower
                comment_bands.append({"label":label, "min":upper, "max":lower, "text":text_val})
        except Exception:
            comment_bands = []

    # Teacher Comments Configuration - Collapsible
    with st.expander("👨‍🏫 Teacher Comments (Auto-Generated)", expanded=False):
        st.caption("Configure automatic comments based on total marks ranges. Enter ranges and corresponding comment text.")
        
        tcol1, tcol2 = st.columns(2)
        with tcol1:
            st.markdown("**Class Teacher Comment Ranges:**")
            ct_ex_min = st.number_input("Excellent - Min Total:", min_value=0, max_value=10000, value=int(st.session_state.report_settings.get('ct_ex_min', 800)), step=10, key="ct_ex_min")
            class_teacher_text_ex = st.text_input("Excellent Comment:", value=st.session_state.report_settings.get('class_teacher_text_ex', 'Excellent performance!'), key="ct_ex")
            
            ct_vg_min = st.number_input("V.Good - Min Total:", min_value=0, max_value=10000, value=int(st.session_state.report_settings.get('ct_vg_min', 700)), step=10, key="ct_vg_min")
            class_teacher_text_vg = st.text_input("V.Good Comment:", value=st.session_state.report_settings.get('class_teacher_text_vg', 'Very good work.'), key="ct_vg")
            
            ct_g_min = st.number_input("Good - Min Total:", min_value=0, max_value=10000, value=int(st.session_state.report_settings.get('ct_g_min', 600)), step=10, key="ct_g_min")
            class_teacher_text_g = st.text_input("Good Comment:", value=st.session_state.report_settings.get('class_teacher_text_g', 'Good effort.'), key="ct_g")
            
            ct_av_min = st.number_input("Average - Min Total:", min_value=0, max_value=10000, value=int(st.session_state.report_settings.get('ct_av_min', 500)), step=10, key="ct_av_min")
            class_teacher_text_av = st.text_input("Average Comment:", value=st.session_state.report_settings.get('class_teacher_text_av', 'Average performance.'), key="ct_av")
            
            class_teacher_text_im = st.text_input("Below Average Comment:", value=st.session_state.report_settings.get('class_teacher_text_im', 'Needs improvement.'), key="ct_im")
        
        with tcol2:
            st.markdown("**Head Teacher Comment Ranges:**")
            ht_ex_min = st.number_input("Excellent - Min Total:", min_value=0, max_value=10000, value=int(st.session_state.report_settings.get('ht_ex_min', 800)), step=10, key="ht_ex_min")
            head_teacher_text_ex = st.text_input("Excellent Comment:", value=st.session_state.report_settings.get('head_teacher_text_ex', 'Outstanding achievement!'), key="ht_ex")
            
            ht_vg_min = st.number_input("V.Good - Min Total:", min_value=0, max_value=10000, value=int(st.session_state.report_settings.get('ht_vg_min', 700)), step=10, key="ht_vg_min")
            head_teacher_text_vg = st.text_input("V.Good Comment:", value=st.session_state.report_settings.get('head_teacher_text_vg', 'Keep up the good work.'), key="ht_vg")
            
            ht_g_min = st.number_input("Good - Min Total:", min_value=0, max_value=10000, value=int(st.session_state.report_settings.get('ht_g_min', 600)), step=10, key="ht_g_min")
            head_teacher_text_g = st.text_input("Good Comment:", value=st.session_state.report_settings.get('head_teacher_text_g', 'Satisfactory progress.'), key="ht_g")
            
            ht_av_min = st.number_input("Average - Min Total:", min_value=0, max_value=10000, value=int(st.session_state.report_settings.get('ht_av_min', 500)), step=10, key="ht_av_min")
            head_teacher_text_av = st.text_input("Average Comment:", value=st.session_state.report_settings.get('head_teacher_text_av', 'Fair performance.'), key="ht_av")
            
            head_teacher_text_im = st.text_input("Below Average Comment:", value=st.session_state.report_settings.get('head_teacher_text_im', 'Requires more effort.'), key="ht_im")

    # Appearance & Table configuration
    st.markdown("#### 🎨 Card Appearance")
    acol1, acol2, acol3 = st.columns(3)
    with acol1:
        main_title_color = st.color_picker("Main Title Color", value=st.session_state.report_settings.get('main_title_color','#0E6BA8'))
    with acol2:
        section_title_color = st.color_picker("Section Title Color", value=st.session_state.report_settings.get('section_title_color','#2c3e50'))
    with acol3:
        table_header_color = st.color_picker("Table Header Color", value=st.session_state.report_settings.get('table_header_color','#0E6BA8'))

    # Watermark configuration
    with st.expander("💧 Watermark Configuration", expanded=False):
        st.caption("Add a diagonal watermark across the entire page")
        enable_watermark = st.checkbox("Enable Watermark", value=st.session_state.report_settings.get('enable_watermark', False))
        
        if enable_watermark:
            # Watermark type selection
            watermark_type = st.radio(
                "Watermark Type:",
                options=["text", "image"],
                index=0 if st.session_state.report_settings.get('watermark_type', 'text') == 'text' else 1,
                horizontal=True
            )
            
            st.markdown("---")
            
            if watermark_type == "text":
                # Text watermark settings
                wcol1, wcol2 = st.columns(2)
                with wcol1:
                    watermark_text = st.text_input("Watermark Text", value=st.session_state.report_settings.get('watermark_text', 'CONFIDENTIAL'))
                    watermark_font_size = st.slider("Font Size", min_value=30, max_value=200, value=st.session_state.report_settings.get('watermark_font_size', 100))
                    watermark_angle = st.slider("Rotation Angle", min_value=0, max_value=90, value=st.session_state.report_settings.get('watermark_angle', 45))
                with wcol2:
                    watermark_color = st.color_picker("Color", value=st.session_state.report_settings.get('watermark_color', '#999999'))
                    watermark_opacity = st.slider("Opacity", min_value=0.05, max_value=0.5, value=st.session_state.report_settings.get('watermark_opacity', 0.2), step=0.05)
                # Set defaults for unused image settings
                watermark_image_path = ''
                watermark_image_size = 300
                
            else:  # image watermark
                # Image watermark settings
                wcol1, wcol2 = st.columns(2)
                with wcol1:
                    watermark_image = st.file_uploader("Upload Image (PNG/JPG)", type=['png', 'jpg', 'jpeg'])
                    
                    # Handle image upload
                    watermark_image_path = st.session_state.report_settings.get('watermark_image_path', '')
                    if watermark_image is not None:
                        # Save uploaded image temporarily
                        try:
                            b = watermark_image.getbuffer()
                            key = os.path.join('report_cards', f"watermark_{uuid4().hex}_{watermark_image.name}")
                            storage.write_bytes(key, bytes(b), content_type='image/png')
                            watermark_image_path = key
                            st.success(f"✅ Image loaded: {watermark_image.name}")
                        except Exception:
                            import tempfile
                            temp_dir = tempfile.gettempdir()
                            watermark_image_path = os.path.join(temp_dir, f"watermark_{watermark_image.name}")
                            try:
                                with open(watermark_image_path, 'wb') as f:
                                    f.write(watermark_image.getbuffer())
                                st.success(f"✅ Image loaded: {watermark_image.name}")
                            except Exception:
                                st.error('Failed to store watermark image')
                    elif watermark_image_path and os.path.exists(watermark_image_path):
                        st.info(f"📁 Using: {os.path.basename(watermark_image_path)}")
                    
                    watermark_image_size = st.slider("Image Size", min_value=100, max_value=600, value=int(st.session_state.report_settings.get('watermark_image_size', 300)), step=50)
                    
                with wcol2:
                    watermark_angle = st.slider("Rotation Angle", min_value=0, max_value=90, value=st.session_state.report_settings.get('watermark_angle', 45))
                    watermark_opacity = st.slider("Opacity", min_value=0.1, max_value=0.8, value=st.session_state.report_settings.get('watermark_opacity', 0.3), step=0.05)
                
                # Set defaults for unused text settings
                watermark_text = 'CONFIDENTIAL'
                watermark_font_size = 100
                watermark_color = '#999999'
        else:
            # Set all defaults when watermark is disabled
            watermark_type = 'text'
            watermark_text = 'CONFIDENTIAL'
            watermark_font_size = 100
            watermark_angle = 45
            watermark_color = '#999999'
            watermark_opacity = 0.2
            watermark_image_path = ''
            watermark_image_size = 300
    
    # Debug watermark status
    if enable_watermark:
        st.info(f"✅ Watermark enabled: {watermark_type.upper()} | Text: '{watermark_text}' | Opacity: {watermark_opacity} | Angle: {watermark_angle}°")

    st.markdown("#### 📋 Grading / Info Table Mode")
    _gm_opts = ["Paste Text", "Build Table"]
    _gm_saved = st.session_state.report_settings.get('grading_mode', _gm_opts[0])
    _gm_idx = _gm_opts.index(_gm_saved) if _gm_saved in _gm_opts else 0
    grading_mode = st.radio("Choose input mode:", _gm_opts, index=_gm_idx, horizontal=True)
    grading_table_text = ""
    grading_table_rows = []
    if grading_mode == "Paste Text":
        grading_table_text = st.text_area(
            "Paste table text (comma or tab separated; each line is a row)",
            value=st.session_state.report_settings.get('grading_table_text',''),
            height=120,
            help="Example:\nPERFORMANCE LEVEL,ACTUAL LEVEL,RAW MARKS,POINTS\nEXCEEDING EXPECTATION,EE,90-100,8"
        )
    else:
        st.caption("Add rows to build a custom grading/info table. Empty rows ignored.")
        import pandas as _pd
        _saved_rows = st.session_state.report_settings.get('grading_table_rows', [])
        if _saved_rows:
            # Normalize to 4 columns max for display
            norm_rows = []
            for r in _saved_rows:
                rr = list(r)
                if len(rr) < 4:
                    rr += [""]*(4-len(rr))
                norm_rows.append({"Col1": rr[0], "Col2": rr[1], "Col3": rr[2], "Col4": rr[3]})
            default_rows = _pd.DataFrame(norm_rows)
        else:
            default_rows = _pd.DataFrame([
                {"Col1": "PERFORMANCE LEVEL", "Col2": "ACTUAL LEVEL", "Col3": "RAW MARKS", "Col4": "POINTS"},
            ])
        edited_table = st.data_editor(
            default_rows,
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="grading_info_builder"
        )
        try:
            for _, r in edited_table.iterrows():
                vals = [str(r.get(c, "")).strip() for c in edited_table.columns]
                if any(vals):
                    grading_table_rows.append([v for v in vals if v])
        except Exception:
            pass
    grading_key_parsed = []  # compatibility placeholder

    st.markdown("#### ➕ Summary Rows in Cards")
    srow1, srow2, srow3, srow4 = st.columns(4)
    with srow1:
        include_total_row = st.checkbox("Include Total Row", value=st.session_state.report_settings.get('include_total_row', True))
    with srow2:
        include_mean_row = st.checkbox("Include Mean Row", value=st.session_state.report_settings.get('include_mean_row', True))
    with srow3:
        include_points_row = st.checkbox("Include Points Row", value=st.session_state.report_settings.get('include_points_row', True), help="Uses grading system from marksheet page if available")
    with srow4:
        include_grade_row = st.checkbox("Include Mean Grade Row", value=st.session_state.report_settings.get('include_grade_row', True), help="Shows the overall letter grade")

    st.markdown("#### 🧩 Subject Table Columns")
    ccol1, ccol2, ccol3 = st.columns(3)
    with ccol1:
        include_comment_column = st.checkbox("Show Comment Column", value=st.session_state.report_settings.get('include_comment_column', True), help="If unchecked, column omitted entirely.")
    with ccol2:
        auto_fill_subject_comments = st.checkbox("Auto-Fill Comments", value=st.session_state.report_settings.get('auto_fill_subject_comments', True), help="Generate comments from thresholds; leave blank for manual entry.")
    with ccol3:
        include_teacher_column = st.checkbox("Show Teacher Column", value=st.session_state.report_settings.get('include_teacher_column', False), help="Adds a last column for subject teacher names")
    ccol4, ccol5 = st.columns(2)
    with ccol4:
        auto_fill_teacher_names = st.checkbox("Auto-Fill Teacher Names", value=st.session_state.report_settings.get('auto_fill_teacher_names', False), help="Attempts to pull 'Teacher' or '<Subject>_Teacher' from data; blank if missing.")
    with ccol5:
        st.caption("Teacher column will always appear last when enabled.")

    # Exclude specific subjects from comments
    st.markdown("#### 🚫 Exclude Subjects from Comments")
    st.caption("Select subjects that should NOT have auto-generated comments (e.g., component subjects like Math P1, Math P2)")
    if 'selected_exam_name' in locals() and selected_exam_name and isinstance(exam_df, pd.DataFrame) and not exam_df.empty:
        exclude_cols = {'name', 'adm no', 'admno', 'adm_no', 'class', 'total', 'mean', 'rank', 's/rank', 'points', 'mean grade'}
        available_subjects = [col for col in exam_df.columns if col.lower() not in exclude_cols]
        no_comment_subjects = st.multiselect(
            "Subjects to exclude from comments:",
            options=available_subjects,
            default=st.session_state.report_settings.get('no_comment_subjects', []),
            help="Component subjects (e.g., Math P1, Math P2) are also auto-detected and excluded"
        )
    else:
        no_comment_subjects = st.session_state.report_settings.get('no_comment_subjects', [])
        st.info("💡 Select an exam first to choose subjects to exclude from comments")

    # Report card type
    st.markdown("#### 📄 Report Card Type")
    report_type = st.radio(
        "Select type:",
        options=["Individual Student", "Bulk - All Students", "Bulk - By Class"],
        horizontal=True
    )

    # Compose section order from saved settings
    # Note: Header and Student Info positions are locked, only middle sections can be reordered
    # Ensure ordering variables exist even if no exam is selected or settings are not yet loaded
    _rs = st.session_state.get('report_settings', {}) if 'report_settings' in st.session_state else {}
    order_header = _rs.get('section_order_header', 1)
    order_key = _rs.get('section_order_grading', 2)
    order_info = _rs.get('section_order_student', 3)
    order_academic = _rs.get('section_order_academic', 4)
    order_comments = _rs.get('section_order_comments', 5)
    order_footer = _rs.get('section_order_footer', 6)
    no_comment_subjects = _rs.get('no_comment_subjects', [])

    section_order_positions = {
        'Header': 1,  # Always first
        'Student Info': 2,  # Always second
        'Academic Performance': order_academic,
        'Comments': order_comments,
        'Grading Key': order_key,
        'Footer': 99,  # Always last
    }
    
    if report_type == "Individual Student":
        # Select individual student
        if 'Name' in exam_df.columns:
            col_avg1, col_avg2 = st.columns(2)
            with col_avg1:
                include_multi_exam_avg = st.checkbox("Show per-subject average (across selected exams)", value=True)
            with col_avg2:
                avg_decimal_places = st.number_input("Average decimal places", min_value=0, max_value=3, value=1, step=1)
            # Choose ranking exam for multi-exam mode
            rank_in_multi = st.checkbox("Show subject rank", value=True)
            ranking_exam_name = None
            if rank_in_multi and multiple_exams_data:
                available_exam_names = [e['name'] for e in multiple_exams_data]
                ranking_exam_name = st.selectbox("Rank subjects using which exam?", options=available_exam_names, index=0)
            comment_basis = st.selectbox("Comment based on:", ["Base exam score", "Average across exams"] if include_multi_exam_avg else ["Base exam score"])  
            # Average explanation note removed per user request
            avg_explanation = ""
        else:
            include_multi_exam_avg = False
            avg_decimal_places = 1
            rank_in_multi = False
            comment_basis = "Base exam score"
            avg_explanation = ""
        
        # Student selection and PDF generation
        student_names = exam_df['Name'].dropna().tolist()
        # Filter out summary rows
        student_names = [str(name).strip() for name in student_names 
                       if str(name).strip() and str(name).lower() not in ['mean', 'total', 'average']]
        
        if student_names:
            selected_student = st.selectbox("Select Student:", options=student_names)
            
            # Preview and Generate buttons side by side
            pcol1, pcol2 = st.columns(2)
            with pcol1:
                preview_btn = st.button("�️ Preview Report Card", type="secondary", use_container_width=True)
            with pcol2:
                generate_btn = st.button("📄 Generate & Download", type="primary", use_container_width=True)
            
            # Handle both preview and generate
            if preview_btn or generate_btn:
                with st.spinner(f"🔄 Generating report card for {selected_student}..."):
                    try:
                        # Get subject columns
                        exclude_cols = {'name', 'adm no', 'admno', 'adm_no', 'class', 'total', 'mean', 
                                       'rank', 's/rank', 'points', 'mean grade'}
                        subject_cols = [col for col in exam_df.columns 
                                       if col.lower() not in exclude_cols]
                        
                        # Get the student's row - use str.strip() to match cleaned names
                        student_rows = exam_df[exam_df['Name'].astype(str).str.strip() == selected_student]
                        if len(student_rows) == 0:
                            st.error(f"Could not find student: {selected_student}")
                            st.stop()
                        student_row = student_rows.iloc[0]
                        
                        # Prepare settings
                        settings = {
                            'school_name': school_name,
                            'motto': motto,
                            'email': email,
                            'term': term,
                            'year': year,
                            'opening_date': opening_date.strftime('%d/%m/%Y'),
                            'closing_date': closing_date.strftime('%d/%m/%Y'),
                            'class_teacher': class_teacher,
                            'head_teacher': head_teacher,
                            'teacher_comment': teacher_comment,
                            'head_teacher_comment': head_teacher_comment,
                            'logo_path': logo_path,
                            'logo2_path': logo2_path,
                            'stamp_path': stamp_path,
                            'main_title_color': main_title_color,
                            'section_title_color': section_title_color,
                            'table_header_color': table_header_color,
                            'include_subject_rank': include_subject_rank,
                            'include_multi_exam_avg': include_multi_exam_avg,
                            'avg_decimal_places': avg_decimal_places,
                            'include_mean_row_single_exam': include_mean_row,
                            'include_total_row': include_total_row,
                            'include_mean_row': include_mean_row,
                            'include_points_row': include_points_row,
                            'include_grade_row': include_grade_row,
                            'include_comment_column': include_comment_column,
                            'auto_fill_subject_comments': auto_fill_subject_comments,
                            'include_teacher_column': include_teacher_column,
                            'auto_fill_teacher_names': auto_fill_teacher_names,
                            'comment_bands': comment_bands,
                            'comment_mode': mode_choice,
                            'rank_in_multi': rank_in_multi,
                            'ranking_exam_name': ranking_exam_name,
                            'comment_basis': comment_basis,
                            'avg_explanation': avg_explanation,
                            'grading_table_text': grading_table_text,
                            'grading_table_rows': grading_table_rows,
                            'include_class_teacher': include_class_teacher,
                            'include_head_teacher': include_head_teacher,
                            'include_teacher_column': include_teacher_column,
                            'auto_class_teacher_remarks': auto_class_teacher_remarks,
                            'auto_head_teacher_remarks': auto_head_teacher_remarks,
                            'ct_ex_min': ct_ex_min,
                            'ct_vg_min': ct_vg_min,
                            'ct_g_min': ct_g_min,
                            'ct_av_min': ct_av_min,
                            'class_teacher_texts': {
                                'excellent': class_teacher_text_ex,
                                'vgood': class_teacher_text_vg,
                                'good': class_teacher_text_g,
                                'average': class_teacher_text_av,
                                'improve': class_teacher_text_im,
                            },
                            'ht_ex_min': ht_ex_min,
                            'ht_vg_min': ht_vg_min,
                            'ht_g_min': ht_g_min,
                            'ht_av_min': ht_av_min,
                            'head_teacher_texts': {
                                'excellent': head_teacher_text_ex,
                                'vgood': head_teacher_text_vg,
                                'good': head_teacher_text_g,
                                'average': head_teacher_text_av,
                                'improve': head_teacher_text_im,
                            },
                            'section_order_positions': section_order_positions,
                            'grading_key_parsed': grading_key_parsed,
                            'thresholds': {
                                'excellent': thr_excellent,
                                'vgood': thr_vgood,
                                'good': thr_good,
                                'average': thr_average
                            },
                            'enable_watermark': enable_watermark,
                            'watermark_type': watermark_type,
                            'watermark_text': watermark_text,
                            'watermark_opacity': watermark_opacity,
                            'watermark_angle': watermark_angle,
                            'watermark_font_size': watermark_font_size,
                            'watermark_color': watermark_color,
                            'watermark_image_path': watermark_image_path,
                            'watermark_image_size': watermark_image_size,
                        }
                        
                        # Prepare student data (single student)
                        students_data = [(student_row, subject_cols, exam_df, selected_exam_name)]
                        
                        # Generate PDF
                        multi_data = multiple_exams_data if 'multiple_exams_data' in locals() else None
                        pdf_buffer = generate_professional_report_card_pdf(students_data, settings, multi_data)
                        
                        if preview_btn:
                            st.success(f"👁️ Preview for {selected_student}")
                            display_pdf_preview(pdf_buffer, height=800)
                        
                        if generate_btn:
                            st.success(f"✅ Generated report card for {selected_student}!")
                        
                        # Always show download button after generation
                        st.download_button(
                            label=f"📥 Download {selected_student}'s Report Card (PDF)",
                            data=pdf_buffer,
                            file_name=f"report_card_{selected_student.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                        
                    except Exception as e:
                        st.error(f"Error generating report card: {e}")
                        import traceback
                        st.error(traceback.format_exc())
        else:
            st.warning("No valid student names found in the exam data.")
    
    elif report_type == "Bulk - All Students":
        grading_key_parsed = []  # Initialize for bulk operations
        
        bcol1, bcol2 = st.columns(2)
        with bcol1:
            preview_bulk_btn = st.button("👁️ Preview First 3 Cards", type="secondary", use_container_width=True)
        with bcol2:
            generate_bulk_btn = st.button("📄 Generate All Report Cards PDF", type="primary", use_container_width=True)
        
        if preview_bulk_btn or generate_bulk_btn:
            with st.spinner("🔄 Generating professional PDF with all report cards..."):
                try:
                    # Get subject columns
                    exclude_cols = {'name', 'adm no', 'admno', 'adm_no', 'class', 'total', 'mean', 
                                   'rank', 's/rank', 'points', 'mean grade'}
                    subject_cols = [col for col in exam_df.columns 
                                   if col.lower() not in exclude_cols]
                    
                    # Prepare student data list
                    students_data = []
                    for idx, row in exam_df.iterrows():
                        student_name = str(row.get('Name', 'N/A'))
                        
                        # Skip empty names or summary rows
                        if not student_name.strip() or student_name.lower() in ['mean', 'total', 'average']:
                            continue
                        
                        students_data.append((row, subject_cols, exam_df, selected_exam_name))
                    
                    # Prepare settings
                    settings = {
                        'school_name': school_name,
                        'motto': motto,
                        'email': email,
                        'term': term,
                        'year': year,
                        'opening_date': opening_date.strftime('%d/%m/%Y'),
                        'closing_date': closing_date.strftime('%d/%m/%Y'),
                        'class_teacher': class_teacher,
                        'head_teacher': head_teacher,
                        'teacher_comment': teacher_comment,
                        'head_teacher_comment': head_teacher_comment,
                        'logo_path': logo_path,
                        'logo2_path': logo2_path,
                        'stamp_path': stamp_path,
                        'main_title_color': main_title_color,
                        'section_title_color': section_title_color,
                        'table_header_color': table_header_color,
                        'include_subject_rank': include_subject_rank,
                        'include_multi_exam_avg': include_multi_exam_avg,
                        'avg_decimal_places': avg_decimal_places,
                        'include_mean_row_single_exam': include_mean_row,
                        'include_total_row': include_total_row,
                        'include_mean_row': include_mean_row,
                        'include_points_row': include_points_row,
                        'include_grade_row': include_grade_row,
                        'include_comment_column': include_comment_column,
                        'auto_fill_subject_comments': auto_fill_subject_comments,
                        'include_teacher_column': include_teacher_column,
                        'auto_fill_teacher_names': auto_fill_teacher_names,
                        'comment_bands': comment_bands,
                        'comment_mode': mode_choice,
                        'rank_in_multi': rank_in_multi,
                        'ranking_exam_name': ranking_exam_name,
                        'comment_basis': comment_basis,
                        'avg_explanation': avg_explanation,
                        'grading_table_text': grading_table_text,
                        'grading_table_rows': grading_table_rows,
                        # component_subjects removed; now auto-detected in PDF
                        'include_class_teacher': include_class_teacher,
                        'include_head_teacher': include_head_teacher,
                        'include_teacher_column': include_teacher_column,
                        'auto_class_teacher_remarks': auto_class_teacher_remarks,
                        'auto_head_teacher_remarks': auto_head_teacher_remarks,
                        'ct_ex_min': ct_ex_min,
                        'ct_vg_min': ct_vg_min,
                        'ct_g_min': ct_g_min,
                        'ct_av_min': ct_av_min,
                        'class_teacher_texts': {
                            'excellent': class_teacher_text_ex,
                            'vgood': class_teacher_text_vg,
                            'good': class_teacher_text_g,
                            'average': class_teacher_text_av,
                            'improve': class_teacher_text_im,
                        },
                        'ht_ex_min': ht_ex_min,
                        'ht_vg_min': ht_vg_min,
                        'ht_g_min': ht_g_min,
                        'ht_av_min': ht_av_min,
                        'head_teacher_texts': {
                            'excellent': head_teacher_text_ex,
                            'vgood': head_teacher_text_vg,
                            'good': head_teacher_text_g,
                            'average': head_teacher_text_av,
                            'improve': head_teacher_text_im,
                        },
                        'section_order_positions': section_order_positions,
                        'grading_key_parsed': grading_key_parsed,
                        'thresholds': {
                            'excellent': thr_excellent,
                            'vgood': thr_vgood,
                            'good': thr_good,
                            'average': thr_average
                        },
                        'no_comment_subjects': no_comment_subjects,
                        'enable_watermark': enable_watermark,
                        'watermark_type': watermark_type,
                        'watermark_text': watermark_text,
                        'watermark_opacity': watermark_opacity,
                        'watermark_angle': watermark_angle,
                        'watermark_font_size': watermark_font_size,
                        'watermark_color': watermark_color,
                        'watermark_image_path': watermark_image_path,
                        'watermark_image_size': watermark_image_size,
                    }
                    
                    # Optional: sort students by rank using selected ranking exam
                    if 'multiple_exams_data' in locals() and multiple_exams_data and ranking_exam_name:
                        rank_exam = next((e for e in multiple_exams_data if e['name'] == ranking_exam_name), None)
                        if rank_exam is None:
                            rank_exam = multiple_exams_data[0]
                        rank_df = rank_exam['exam_df']
                        # create mapping name -> numeric rank
                        def parse_rank(val):
                            try:
                                # handle formats like '3/45'
                                s = str(val)
                                if '/' in s:
                                    s = s.split('/')[0]
                                return float(s)
                            except Exception:
                                return float('inf')
                        rank_map = {}
                        if 'Name' in rank_df.columns and ('Rank' in rank_df.columns or 'S/Rank' in rank_df.columns):
                            rcol = 'Rank' if 'Rank' in rank_df.columns else 'S/Rank'
                            for _, r in rank_df.iterrows():
                                nm = str(r.get('Name','')).strip()
                                if nm:
                                    rank_map[nm] = parse_rank(r.get(rcol))
                        students_data.sort(key=lambda tup: rank_map.get(str(tup[0].get('Name','')).strip(), float('inf')))

                    # Generate PDF - pass multiple_exams_data if in multi-exam mode
                    multi_data = multiple_exams_data if 'multiple_exams_data' in locals() else None
                    
                    # For preview, limit to first 3 students
                    if preview_bulk_btn:
                        preview_data = students_data[:3]
                        pdf_buffer = generate_professional_report_card_pdf(preview_data, settings, multi_data)
                        st.info(f"👁️ Previewing first {len(preview_data)} student(s) out of {len(students_data)} total")
                        display_pdf_preview(pdf_buffer, height=800)
                    else:
                        pdf_buffer = generate_professional_report_card_pdf(students_data, settings, multi_data)
                        mode_text = f"{len(multiple_exams_data)} exams" if multi_data else "single exam"
                        st.success(f"✅ Generated professional report cards for {len(students_data)} students ({mode_text})!")
                    
                    st.download_button(
                        label="📥 Download All Report Cards (PDF)",
                        data=pdf_buffer,
                        file_name=f"report_cards_all_{selected_exam_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                    
                except Exception as e:
                    st.error(f"Error generating report cards: {e}")
                    import traceback
                    st.error(traceback.format_exc())
    
    else:  # Bulk - By Class
        grading_key_parsed = []
        
        if 'Class' in exam_df.columns:
            # Canonicalize class names for consistency (matches multi-exam normalization)
            def _canonical_class(raw):
                if not raw:
                    return ''
                s = str(raw).strip().lower()
                s = s.replace('grade', 'grade ').replace('gr ', 'grade ').replace('form', 'form ').replace('class', 'class ')
                s = re.sub(r"\s+", " ", s)
                word_to_digit = {
                    'one':'1','two':'2','three':'3','four':'4','five':'5','six':'6','seven':'7','eight':'8','nine':'9','ten':'10'
                }
                tokens = s.split(' ')
                converted = [word_to_digit.get(t, t) for t in tokens]
                s = ' '.join(converted)
                s = re.sub(r"\s+", " ", s).strip()
                m = re.search(r"grade\s*(\d+)", s)
                if m:
                    return f"Grade {m.group(1)}"
                m2 = re.search(r"form\s*(\d+)", s)
                if m2:
                    return f"Form {m2.group(1)}"
                m3 = re.search(r"class\s*(\d+)", s)
                if m3:
                    return f"Class {m3.group(1)}"
                return s.title()

            # Filter out summary rows, empty and non-alpha classes, then map to canonical
            base_class_series = exam_df['Class'].dropna().astype(str).str.strip()
            candidate_classes = []
            for cls in base_class_series.unique().tolist():
                cls_str = str(cls).strip()
                if not cls_str or cls_str.lower() in ['mean', 'total', 'average']:
                    continue
                if not any(c.isalpha() for c in cls_str):
                    continue
                candidate_classes.append(cls_str)

            # Build canonical mapping
            canonical_map = {}
            for raw_cls in candidate_classes:
                canon = _canonical_class(raw_cls)
                canonical_map.setdefault(canon, set()).add(raw_cls)

            canonical_classes = sorted(canonical_map.keys())
            if canonical_classes:
                selected_class = st.selectbox("Select Class:", options=["All Classes"] + canonical_classes)

                ccol1, ccol2 = st.columns(2)
                with ccol1:
                    preview_class_btn = st.button("👁️ Preview First 3 Cards", type="secondary", use_container_width=True)
                with ccol2:
                    generate_class_btn = st.button("📄 Generate Class Report Cards PDF", type="primary", use_container_width=True)

                if preview_class_btn or generate_class_btn:
                    # Create a canonicalized copy of exam_df for consistent class rank calculations
                    exam_df_canon = exam_df.copy()
                    exam_df_canon['Class'] = exam_df_canon['Class'].apply(_canonical_class)

                    if selected_class == "All Classes":
                        target_classes = canonical_classes
                        display_class_label = "All Classes"
                    else:
                        target_classes = [selected_class]
                        display_class_label = selected_class

                    # Get subject columns (from canonicalized df)
                    exclude_cols = {'name', 'adm no', 'admno', 'adm_no', 'class', 'total', 'mean', 'rank', 's/rank', 'points', 'mean grade'}
                    subject_cols = [col for col in exam_df_canon.columns if col.lower() not in exclude_cols]

                    # Build students_data list across selected canonical classes
                    students_data = []
                    for canon_cls in target_classes:
                        class_mask = exam_df_canon['Class'] == canon_cls
                        class_students = exam_df_canon[class_mask]
                        for _, row in class_students.iterrows():
                            student_name = str(row.get('Name', 'N/A')).strip()
                            if not student_name or student_name.lower() in ['mean', 'total', 'average']:
                                continue
                            # Pass canonicalized exam_df for proper within-class ranking
                            students_data.append((row, subject_cols, exam_df_canon, selected_exam_name))

                    with st.spinner(f"🔄 Generating professional PDF for {len(students_data)} students in {display_class_label} ..."):
                        try:
                            settings = {
                                'school_name': school_name,
                                'motto': motto,
                                'email': email,
                                'term': term,
                                'year': year,
                                'opening_date': opening_date.strftime('%d/%m/%Y'),
                                'closing_date': closing_date.strftime('%d/%m/%Y'),
                                'class_teacher': class_teacher,
                                'head_teacher': head_teacher,
                                'teacher_comment': teacher_comment,
                                'head_teacher_comment': head_teacher_comment,
                                'logo_path': logo_path,
                                'logo2_path': logo2_path,
                                'stamp_path': stamp_path,
                                'main_title_color': main_title_color,
                                'section_title_color': section_title_color,
                                'table_header_color': table_header_color,
                                'include_subject_rank': include_subject_rank,
                                'include_multi_exam_avg': include_multi_exam_avg,
                                'avg_decimal_places': avg_decimal_places,
                                'include_mean_row_single_exam': include_mean_row,
                                'include_total_row': include_total_row,
                                'include_mean_row': include_mean_row,
                                'include_points_row': include_points_row,
                                'include_grade_row': include_grade_row,
                                'include_comment_column': include_comment_column,
                                'auto_fill_subject_comments': auto_fill_subject_comments,
                                'include_teacher_column': include_teacher_column,
                                'auto_fill_teacher_names': auto_fill_teacher_names,
                                'comment_bands': comment_bands,
                                'comment_mode': mode_choice,
                                'rank_in_multi': rank_in_multi,
                                'ranking_exam_name': ranking_exam_name,
                                'comment_basis': comment_basis,
                                'avg_explanation': avg_explanation,
                                'grading_table_text': grading_table_text,
                                'grading_table_rows': grading_table_rows,
                                'include_class_teacher': include_class_teacher,
                                'include_head_teacher': include_head_teacher,
                                'include_teacher_column': include_teacher_column,
                                'auto_class_teacher_remarks': auto_class_teacher_remarks,
                                'auto_head_teacher_remarks': auto_head_teacher_remarks,
                                'ct_ex_min': ct_ex_min,
                                'ct_vg_min': ct_vg_min,
                                'ct_g_min': ct_g_min,
                                'ct_av_min': ct_av_min,
                                'class_teacher_texts': {
                                    'excellent': class_teacher_text_ex,
                                    'vgood': class_teacher_text_vg,
                                    'good': class_teacher_text_g,
                                    'average': class_teacher_text_av,
                                    'improve': class_teacher_text_im,
                                },
                                'ht_ex_min': ht_ex_min,
                                'ht_vg_min': ht_vg_min,
                                'ht_g_min': ht_g_min,
                                'ht_av_min': ht_av_min,
                                'head_teacher_texts': {
                                    'excellent': head_teacher_text_ex,
                                    'vgood': head_teacher_text_vg,
                                    'good': head_teacher_text_g,
                                    'average': head_teacher_text_av,
                                    'improve': head_teacher_text_im,
                                },
                                'section_order_positions': section_order_positions,
                                'grading_key_parsed': grading_key_parsed,
                                'thresholds': {
                                    'excellent': thr_excellent,
                                    'vgood': thr_vgood,
                                    'good': thr_good,
                                    'average': thr_average
                                },
                                'no_comment_subjects': no_comment_subjects,
                                'enable_watermark': enable_watermark,
                                'watermark_type': watermark_type,
                                'watermark_text': watermark_text,
                                'watermark_opacity': watermark_opacity,
                                'watermark_angle': watermark_angle,
                                'watermark_font_size': watermark_font_size,
                                'watermark_color': watermark_color,
                                'watermark_image_path': watermark_image_path,
                                'watermark_image_size': watermark_image_size,
                            }

                            multi_data = multiple_exams_data if 'multiple_exams_data' in locals() else None
                            
                            # For preview, limit to first 3 students
                            if preview_class_btn:
                                preview_data = students_data[:3]
                                pdf_buffer = generate_professional_report_card_pdf(preview_data, settings, multi_data)
                                st.info(f"👁️ Previewing first {len(preview_data)} student(s) from {display_class_label} (total: {len(students_data)})")
                                display_pdf_preview(pdf_buffer, height=800)
                            else:
                                pdf_buffer = generate_professional_report_card_pdf(students_data, settings, multi_data)
                                st.success(f"✅ Generated professional report cards for {len(students_data)} students in {display_class_label}!")

                            output_label = display_class_label.replace(' ', '_')
                            st.download_button(
                                label=f"📥 Download {display_class_label} Report Cards (PDF)",
                                data=pdf_buffer,
                                file_name=f"report_cards_{output_label}_{datetime.now().strftime('%Y%m%d')}.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )

                        except Exception as e:
                            st.error(f"Error generating report cards: {e}")
                            import traceback
                            st.error(traceback.format_exc())
            else:
                st.warning("No valid classes found in exam data.")
        else:
            st.error("'Class' column not found in exam data.")

# Persist settings controls - At end of page before footer
st.markdown("---")
st.markdown("#### 💾 Save Settings")
st.info("💡 Save everything on this page: school info, dates, logos/stamp, colors, thresholds, grading table, exclusions, watermark (text/image), and all toggles.")
save_col, reset_col = st.columns([1,1])
with save_col:
    if st.button("💾 Save All Settings", use_container_width=True, type="primary"):
        # Persist any uploaded watermark image to app storage (so it survives reruns)
        try:
            if 'watermark_type' in locals() and watermark_type == 'image' and 'watermark_image_path' in locals() and watermark_image_path:
                import shutil, time
                if os.path.exists(watermark_image_path):
                    # If file is not already under STORAGE_DIR, copy it
                    if os.path.commonpath([os.path.abspath(watermark_image_path), os.path.abspath(STORAGE_DIR)]) != os.path.abspath(STORAGE_DIR):
                        wm_dir = os.path.join(STORAGE_DIR, 'watermarks')
                        os.makedirs(wm_dir, exist_ok=True)
                        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                        base = os.path.basename(watermark_image_path)
                        dest = os.path.join(wm_dir, f"{ts}_{base}")
                        shutil.copy2(watermark_image_path, dest)
                        watermark_image_path = dest  # update to persisted path
        except Exception as _e:
            st.warning(f"Could not persist watermark image: {_e}")

        # Persist optional attachments (logos/stamp) into a stable attachments directory
        try:
            import shutil
            attach_dir = os.path.join(STORAGE_DIR, 'attachments')
            os.makedirs(attach_dir, exist_ok=True)
            def _persist_attachment(temp_path, label):
                if not temp_path:
                    return ''
                try:
                    # If temp_path is a storage key, copy bytes within storage to attachments prefix
                    try:
                        if storage is not None and storage.exists(temp_path):
                            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                            base = os.path.basename(temp_path)
                            dest_key = os.path.join('report_cards_attachments', f"{label}_{ts}_{base}")
                            b = storage.read_bytes(temp_path)
                            if b:
                                storage.write_bytes(dest_key, b, content_type='image/png')
                                return dest_key
                            return ''
                    except Exception:
                        # fall through to local handling
                        pass

                    # Local filesystem handling
                    if os.path.exists(temp_path):
                        # If already inside attach_dir keep path
                        try:
                            if os.path.commonpath([os.path.abspath(temp_path), os.path.abspath(attach_dir)]) == os.path.abspath(attach_dir):
                                return temp_path
                        except Exception:
                            pass
                        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                        base = os.path.basename(temp_path)
                        dest = os.path.join(attach_dir, f"{label}_{ts}_{base}")
                        try:
                            shutil.copy2(temp_path, dest)
                            return dest
                        except Exception:
                            return temp_path
                except Exception:
                    return ''
                return ''
            if logo_path:
                logo_path = _persist_attachment(logo_path, 'logo')
            if logo2_path:
                logo2_path = _persist_attachment(logo2_path, 'logo2')
            if stamp_path:
                stamp_path = _persist_attachment(stamp_path, 'stamp')
        except Exception as _e:
            st.warning(f"Could not persist attachments: {_e}")

        # Update session settings and save to disk
        st.session_state.report_settings.update({
            'report_mode': report_mode,
            'school_name': school_name,
            'motto': motto,
            'email': email,
            'term': term,
            'year': int(year),
            'opening_date': opening_date.strftime('%d/%m/%Y'),
            'closing_date': closing_date.strftime('%d/%m/%Y'),
            # Persist attachments (paths already saved in STORAGE_DIR during upload)
            'logo_path': logo_path or st.session_state.report_settings.get('logo_path',''),
            'logo2_path': logo2_path or st.session_state.report_settings.get('logo2_path',''),
            'stamp_path': stamp_path or st.session_state.report_settings.get('stamp_path',''),
            'main_title_color': main_title_color,
            'section_title_color': section_title_color,
            'table_header_color': table_header_color,
            'grading_mode': grading_mode,
            'grading_table_text': grading_table_text,
            'grading_table_rows': grading_table_rows,
            'include_total_row': include_total_row,
            'include_mean_row': include_mean_row,
            'include_points_row': include_points_row,
            'include_grade_row': include_grade_row,
            'include_comment_column': include_comment_column,
            'auto_fill_subject_comments': auto_fill_subject_comments,
            'include_teacher_column': include_teacher_column,
            'auto_fill_teacher_names': auto_fill_teacher_names,
            'no_comment_subjects': no_comment_subjects,
            'comment_mode': mode_choice,
            'thr_excellent': float(thr_excellent) if 'thr_excellent' in locals() else st.session_state.report_settings.get('thr_excellent', 80.0),
            'thr_vgood': float(thr_vgood) if 'thr_vgood' in locals() else st.session_state.report_settings.get('thr_vgood', 70.0),
            'thr_good': float(thr_good) if 'thr_good' in locals() else st.session_state.report_settings.get('thr_good', 60.0),
            'thr_average': float(thr_average) if 'thr_average' in locals() else st.session_state.report_settings.get('thr_average', 50.0),
            'comment_bands': comment_bands,
            'ct_ex_min': int(ct_ex_min),
            'ct_vg_min': int(ct_vg_min),
            'ct_g_min': int(ct_g_min),
            'ct_av_min': int(ct_av_min),
            'class_teacher_text_ex': class_teacher_text_ex,
            'class_teacher_text_vg': class_teacher_text_vg,
            'class_teacher_text_g': class_teacher_text_g,
            'class_teacher_text_av': class_teacher_text_av,
            'class_teacher_text_im': class_teacher_text_im,
            'ht_ex_min': int(ht_ex_min),
            'ht_vg_min': int(ht_vg_min),
            'ht_g_min': int(ht_g_min),
            'ht_av_min': int(ht_av_min),
            'head_teacher_text_ex': head_teacher_text_ex,
            'head_teacher_text_vg': head_teacher_text_vg,
            'head_teacher_text_g': head_teacher_text_g,
            'head_teacher_text_av': head_teacher_text_av,
            'head_teacher_text_im': head_teacher_text_im,
            # Multi-exam and ranking controls
            'include_multi_exam_avg': bool(include_multi_exam_avg) if 'include_multi_exam_avg' in locals() else st.session_state.report_settings.get('include_multi_exam_avg', True),
            'avg_decimal_places': int(avg_decimal_places) if 'avg_decimal_places' in locals() else st.session_state.report_settings.get('avg_decimal_places', 1),
            'rank_in_multi': bool(rank_in_multi) if 'rank_in_multi' in locals() else st.session_state.report_settings.get('rank_in_multi', True),
            'ranking_exam_name': ranking_exam_name if 'ranking_exam_name' in locals() and ranking_exam_name else st.session_state.report_settings.get('ranking_exam_name', ''),
            'comment_basis': comment_basis if 'comment_basis' in locals() else st.session_state.report_settings.get('comment_basis', 'Base exam score'),
            'enable_watermark': enable_watermark,
            'watermark_type': watermark_type,
            'watermark_text': watermark_text,
            'watermark_opacity': float(watermark_opacity),
            'watermark_angle': int(watermark_angle),
            'watermark_font_size': int(watermark_font_size),
            'watermark_color': watermark_color,
            'watermark_image_path': watermark_image_path,
            'watermark_image_size': int(watermark_image_size),
        })
        if save_report_settings(st.session_state.report_settings):
            st.success("✅ Settings saved successfully!")
with reset_col:
    if st.button("↩ Reset to Defaults", use_container_width=True):
        st.session_state.report_settings = get_default_report_settings()
        save_report_settings(st.session_state.report_settings)
        st.success("✅ Defaults restored. Please reload the page.")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 2rem 1rem 1rem 1rem;'>
    <p style='margin: 0; font-size: 0.9rem;'><strong>EDUSCORE ANALYTICS</strong></p>
    <p style='margin: 0.3rem 0; font-size: 0.85rem;'>Developed by <strong>Munyua Kamau</strong></p>
    <p style='margin: 0.3rem 0; font-size: 0.75rem; color: #888;'>© 2025 All Rights Reserved</p>
</div>
""", unsafe_allow_html=True)
