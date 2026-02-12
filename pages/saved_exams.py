import streamlit as st
import pandas as pd
import numpy as np
import os
import re
import base64
from datetime import datetime
import uuid
import json
import pickle
import threading
from utils import student_photos as photos
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from numbers import Number
from modules import storage

# ReportLab default styles
styles = getSampleStyleSheet()

# Block access when parents portal mode is active
try:
    if st.session_state.get('parents_portal_mode'):
        st.markdown("<div style='opacity:0.45;padding:18px;border-radius:8px;background:#f3f4f6;color:#111;'>\
            <strong>Restricted:</strong> This page is not available in Parents Portal mode.</div>", unsafe_allow_html=True)
        st.stop()
except Exception:
    pass

# Persistent app config helper (stores small user settings).
# Uses the central storage adapter so configs are saved to S3 when enabled
# and fall back to local filesystem otherwise.
def _persistent_config_path() -> str:
    try:
        base = storage.get_storage_dir()
        return os.path.join(base, 'app_persistent_config.json')
    except Exception:
        # final fallback to repo root
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app_persistent_config.json')


def load_persistent_config():
    try:
        p = _persistent_config_path()
        cfg = storage.read_json(p)
        return cfg or {}
    except Exception:
        return {}


def save_persistent_config(cfg: dict):
    try:
        p = _persistent_config_path()
        return storage.write_json(p, cfg)
    except Exception:
        return False


def create_backup_saved_exams():
    """Create a timestamped backup copy of the saved_exams_storage folder and return the backup path or None."""
    try:
        import shutil
        src = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'saved_exams_storage')
        if not os.path.exists(src):
            return None
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        dst = os.path.join(os.path.dirname(os.path.dirname(__file__)), f'saved_exams_storage_backup_{ts}')
        shutil.copytree(src, dst)
        return dst
    except Exception:
        return None

def _exam_kind_from_label(name: str) -> str:
    """Extract exam kind from an exam label like 'END TERM - TERM 1 - GRADE 6 - 2025'.
    Returns the first segment title-cased, e.g. 'End Term'."""
    try:
        if not name:
            return ''
        parts = [p.strip() for p in str(name).split(' - ') if p.strip()]
        if not parts:
            s = str(name).strip()
        else:
            s = parts[0]
        s_low = re.sub(r'[^a-z0-9]', '', str(s).lower())
        # canonicalize common variants
        if 'endterm' in s_low or ('end' in s_low and 'term' in s_low):
            return 'End Term'
        # term number like term1, termone, firstterm
        if re.search(r'(?:term\s*-?\s*1|term1|termone|first|one|1)', s_low):
            return 'Term 1'
        if re.search(r'(?:term\s*-?\s*2|term2|termtwo|second|two|2)', s_low):
            return 'Term 2'
        if re.search(r'(?:term\s*-?\s*3|term3|termthree|third|three|3)', s_low):
            return 'Term 3'
        # fallback: title-case the original first segment
        return str(s).title()
    except Exception:
        return str(name)

def convert_score_to_numeric(val):
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
        s = str(val).strip()
        import re
        m = re.search(r"[-+]?[0-9]*\.?[0-9]+", s)
        if m:
            return float(m.group())
    except Exception:
        pass
    try:
        v = str(val).upper().strip()
        grade_map = {'A':90.0, 'B':80.0, 'C':70.0, 'D':60.0, 'E':50.0}
        if v and v[0] in grade_map:
            base = grade_map[v[0]]
            if v.endswith('+'):
                base = min(100.0, base + 2.0)
            if v.endswith('-'):
                base = max(0.0, base - 2.0)
            return float(base)
    except Exception:
        pass
    return None

def generate_pdf_stream_table(exam_name, subj_list, streams, table_data, most_improved_info=None, include_subjects=None, stream_total_means=None, most_improved_table=None):
    """Generate a PDF containing a subject × stream mean table, with Average and Rank rows at the bottom.
    include_subjects: list of subject names to include (defaults to subj_list)
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=0.4*inch, rightMargin=0.4*inch, topMargin=0.6*inch, bottomMargin=0.4*inch)
    story = []
    # (Title rendering is handled below after metadata enrichment.)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('title', parent=styles['Heading1'], alignment=1, fontSize=14)
    # Enrich title with metadata if available
    try:
        meta_list = st.session_state.get('saved_exams', [])
        meta_obj = next((m for m in meta_list if m.get('exam_name') == exam_name), None)
    except Exception:
        meta_obj = None
    try:
        exam_year = meta_obj.get('year') if meta_obj else None
    except Exception:
        exam_year = None
    try:
        exam_kind = _exam_kind_from_label(exam_name) if exam_name else ''
    except Exception:
        exam_kind = ''
    title_text = f"Subject-wise Stream Comparison — {exam_name}"
    if exam_year is not None:
        title_text += f" — Year: {exam_year}"
    if exam_kind:
        title_text += f" — Kind: {exam_kind}"
    try:
        story.append(Paragraph(title_text, title_style))
        story.append(Spacer(1, 0.12*inch))
    except Exception:
        pass

    if include_subjects is None:
        include_subjects = list(subj_list)

    # Build rows and compute per-stream averages and per-subject averages/ranks
    # Build header, initialize stream accumulators, then collect subject averages and prepared row cells for each subject
    header = ['Subject'] + list(streams) + ['Average', 'Rank']
    rows = [header]
    stream_sums = {s: 0.0 for s in streams}
    stream_counts = {s: 0 for s in streams}

    # Collect subject averages and prepared row cells for each subject
    subj_avgs = {}
    subject_rows = {}
    for subj in include_subjects:
        cells = [subj]
        vals_for_avg = []
        for s in streams:
            val = table_data.get((subj, s), None)
            if val is None:
                cells.append('-')
            else:
                try:
                    fv = float(val)
                    cells.append(f"{fv:.2f}")
                    vals_for_avg.append(fv)
                    stream_sums[s] += fv
                    stream_counts[s] += 1
                except Exception:
                    cells.append('-')
        if vals_for_avg:
            avg = sum(vals_for_avg) / len(vals_for_avg)
            subj_avgs[subj] = avg
            cells.append(f"{avg:.2f}")
        else:
            subj_avgs[subj] = None
            cells.append('-')
        # placeholder for rank - we'll replace after ranking
        cells.append('-')
        subject_rows[subj] = cells

    # Compute dense ranks for subjects (highest average -> rank 1)
    try:
        valid_avgs = [v for v in subj_avgs.values() if v is not None]
        if valid_avgs:
            unique_sorted = sorted(list({round(x,8) for x in valid_avgs}), reverse=True)
            subj_ranks = {}
            for subj, v in subj_avgs.items():
                if v is None:
                    subj_ranks[subj] = '-'
                else:
                    try:
                        r = unique_sorted.index(round(v,8)) + 1
                    except Exception:
                        r = 1
                    # store numeric rank (int) so we can format consistently later
                    subj_ranks[subj] = r
        else:
            subj_ranks = {s: '-' for s in subj_avgs.keys()}
    except Exception:
        subj_ranks = {s: '-' for s in subj_avgs.keys()}

    # Order subjects by average (highest first), placing subjects with no average at the end
    try:
        def sort_key(s):
            v = subj_avgs.get(s)
            return (v is None, -v if v is not None else 0)
        ordered_subjects = sorted(include_subjects, key=sort_key)
    except Exception:
        ordered_subjects = list(include_subjects)

    # Append ordered subject rows, filling ranks
    for subj in ordered_subjects:
        row = subject_rows.get(subj, [subj] + ['-'] * (len(streams) + 2))
        rnk = subj_ranks.get(subj, '-')
        # Format numeric ranks with 0 decimals (integers), leave '-' as-is
        if isinstance(rnk, (int, float)):
            try:
                row[-1] = f"{float(rnk):.0f}"
            except Exception:
                row[-1] = str(rnk)
        else:
            row[-1] = rnk
        rows.append(row)

    # Average row: use provided stream_total_means (mean of student Total per stream) if available,
    # otherwise fall back to mean of included subject means.
    avg_row = ['Average']
    stream_avg_values = {}
    if stream_total_means:
        for s in streams:
            v = stream_total_means.get(s)
            if v is None:
                avg_row.append('-')
                stream_avg_values[s] = None
            else:
                avg_row.append(f"{float(v):.2f}")
                stream_avg_values[s] = float(v)
    else:
        for s in streams:
            cnt = stream_counts.get(s, 0)
            if cnt > 0:
                avg = stream_sums[s] / cnt
                avg_row.append(f"{avg:.2f}")
                stream_avg_values[s] = avg
            else:
                avg_row.append('-')
                stream_avg_values[s] = None
    # For the Average row, leave the final two columns empty (they refer to per-subject Average/Rank)
    avg_row.append('-')
    avg_row.append('-')
    rows.append(avg_row)

    # Rank row based on descending average (1 = best) for streams
    sorted_avgs = sorted([v for v in stream_avg_values.values() if v is not None], reverse=True)
    rank_row = ['Rank']
    for s in streams:
        v = stream_avg_values.get(s)
        if v is None:
            rank_row.append('-')
        else:
            try:
                rank = sorted_avgs.index(v) + 1
            except Exception:
                rank = 1
            # format stream rank with 0 decimals
            try:
                rank_row.append(f"{float(rank):.0f}")
            except Exception:
                rank_row.append(str(rank))
    # leave last two columns blank for the streams' rank row
    rank_row.append('-')
    rank_row.append('-')
    rows.append(rank_row)

    # Build table
    col_widths = [2.5*inch] + [((A4[0] - 0.8*inch) - 2.5*inch) / max(1, len(streams) + 2)] * (len(streams) + 2)
    t = Table(rows, colWidths=col_widths, hAlign='LEFT')
    tbl_style = TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0E6BA8')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ])
    t.setStyle(tbl_style)
    story.append(t)
    story.append(Spacer(1, 0.2*inch))

    if most_improved_info:
        story.append(Paragraph('Most Improved Student (comparison):', styles['Heading3']))
        mi_text = f"{most_improved_info.get('Name','N/A')} — Adm: {most_improved_info.get('Adm','N/A')} — Improvement: {most_improved_info.get('Improvement',0):.2f}"
        story.append(Paragraph(mi_text, styles['Normal']))

    # If a Most Improved table (top-N) is provided, render it as a simple table in the PDF
    if most_improved_table is not None:
        try:
            story.append(Spacer(1, 0.12*inch))
            story.append(Paragraph('Most Improved — Top Students', styles['Heading3']))
            # most_improved_table may be a pandas DataFrame or list of dicts
            if hasattr(most_improved_table, 'columns'):
                mi_df = most_improved_table.copy()
            else:
                import pandas as _pd
                mi_df = _pd.DataFrame(most_improved_table)

            # Convert DataFrame to rows
            mi_header = list(mi_df.columns)
            mi_rows = [mi_header]
            for _, r in mi_df.iterrows():
                row = []
                # detect if this is the special Rank row by checking the first column value
                first_val = r.get(mi_header[0], '')
                is_rank_row = isinstance(first_val, str) and first_val.strip().lower() == 'rank'
                for c in mi_header:
                    v = r.get(c, '')
                    # treat missing values
                    try:
                        if pd.isna(v):
                            row.append('-')
                            continue
                    except Exception:
                        pass
                    # For the Rank row, render numeric cells as integers (no decimals).
                    try:
                        fv = float(v)
                        if is_rank_row:
                            try:
                                row.append(str(int(fv)))
                            except Exception:
                                row.append(str(fv))
                        else:
                            row.append(f"{fv:.2f}")
                    except Exception:
                        row.append(str(v) if v is not None else '')
                mi_rows.append(row)

            # Add table with a lighter grid
            mi_col_widths = [((A4[0] - 0.8*inch) / max(1, len(mi_header))) ] * len(mi_header)
            mi_table = Table(mi_rows, colWidths=mi_col_widths, hAlign='LEFT')
            mi_style = TableStyle([
                ('GRID', (0,0), (-1,-1), 0.3, colors.grey),
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0E6BA8')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ])
            mi_table.setStyle(mi_style)
            story.append(mi_table)
        except Exception:
            pass

    # Footer drawer: company name and copyright (EDUSCORE ANALYTICS)
    def _draw_footer_stream(canvas, doc_):
        try:
            canvas.saveState()
            company = 'EDUSCORE ANALYTICS'
            year_now = datetime.now().year
            canvas.setFont('Helvetica', 8)
            canvas.setFillColor(colors.grey)
            canvas.drawCentredString(A4[0] / 2.0, 0.35 * inch, company)
            canvas.setFont('Helvetica', 7)
            canvas.drawCentredString(A4[0] / 2.0, 0.18 * inch, f"\u00A9 {year_now} {company}. All rights reserved.")
            canvas.restoreState()
        except Exception:
            pass

    try:
        doc.build(story, onFirstPage=_draw_footer_stream, onLaterPages=_draw_footer_stream)
    except Exception:
        try:
            doc.build(story)
        except Exception:
            pass
    buf.seek(0)
    return buf


def generate_pdf_most_improved(title, mi_df):
    """Generate a simple PDF listing the Most Improved students from a DataFrame `mi_df`.
    Expects `mi_df` to have columns like Identifier, Baseline, Current, Improvement, Rank.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=0.4*inch, rightMargin=0.4*inch, topMargin=0.6*inch, bottomMargin=0.4*inch)
    story = []
    # Prepare and render a cleaned title inside the PDF (main title + optional subtitle after '— Showing:')
    try:
        styles_local = getSampleStyleSheet()
        title_style = ParagraphStyle('title', parent=styles_local['Heading1'], alignment=1, fontSize=14)
        subtitle_style = ParagraphStyle('subtitle', parent=styles_local['Normal'], alignment=1, fontSize=10)

        display_title = str(title) if title is not None else ''
        # Remove Subgroup/Sections fragments (they're not needed in the title body)
        try:
            display_title = re.sub(r"\s*—\s*(?:Subgroup|Sections?)\s*:\s*[^—]+", '', display_title, flags=re.IGNORECASE)
        except Exception:
            pass
        # Normalize accidental 'Term Term 1' repeats -> 'Term 1'
        try:
            display_title = re.sub(r'(?i)\bterm\s+term\b', 'Term', display_title)
        except Exception:
            pass

        # Color the Basis values (e.g. 'Basis: Total' -> show value in green)
        try:
            def _color_basis(m):
                val = m.group(1).strip()
                # wrap the value portion in a font tag ReportLab Paragraph accepts
                return f"Basis: <font color='#1f8f3f'>{val}</font>"
            display_title = re.sub(r'Basis\s*:\s*([^—]+)', _color_basis, display_title, flags=re.IGNORECASE)
        except Exception:
            pass

        if '— Showing:' in display_title:
            main, showing = display_title.split('— Showing:', 1)
            story.append(Paragraph(main.strip(), title_style))
            story.append(Paragraph(f"Showing: {showing.strip()}", subtitle_style))
            story.append(Spacer(1, 0.08 * inch))
        else:
            story.append(Paragraph(display_title, title_style))
            story.append(Spacer(1, 0.12 * inch))
    except Exception:
        pass
    # Footer: fixed company name per user request
    company_name = 'EDUSCORE ANALYTICS'

    def _draw_footer(canvas, doc_):
        try:
            canvas.saveState()
            # Company name (slightly higher) and copyright line below
            year_now = datetime.now().year
            canvas.setFont('Helvetica', 8)
            canvas.setFillColor(colors.grey)
            canvas.drawCentredString(A4[0] / 2.0, 0.35 * inch, str(company_name))
            # Copyright line, smaller font
            canvas.setFont('Helvetica', 7)
            copyright_text = f"\u00A9 {year_now} {company_name}. All rights reserved."
            canvas.drawCentredString(A4[0] / 2.0, 0.18 * inch, copyright_text)
            canvas.restoreState()
        except Exception:
            pass

    def _add_table_from_df(df_local):
        try:
            if hasattr(df_local, 'columns'):
                df = df_local.copy()
            else:
                import pandas as _pd
                df = _pd.DataFrame(df_local)

            header = list(df.columns)
            # detect if first column is a serial/position column so we render integers without decimals
            first_col_is_serial = False
            try:
                if header and isinstance(header[0], str) and header[0].strip().lower() in ('no', 'pos', 'position', '#'):
                    first_col_is_serial = True
            except Exception:
                first_col_is_serial = False

            # Determine stream-like columns by header name
            stream_cols = set(i for i, h in enumerate(header) if isinstance(h, str) and 'stream' in h.lower())
            # Determine class-like columns (named 'Class' or containing 'class') to avoid decimal formatting
            class_cols = set(i for i, h in enumerate(header) if isinstance(h, str) and h.strip().lower() == 'class' or (isinstance(h, str) and 'class' in h.strip().lower()))

            rows = [header]
            for _, r in df.iterrows():
                row = []
                first_val = r.get(header[0], '')
                is_rank_row = isinstance(first_val, str) and first_val.strip().lower() == 'rank'
                for cidx, c in enumerate(header):
                    v = r.get(c, '')
                    try:
                        if pd.isna(v):
                            row.append('-')
                            continue
                    except Exception:
                        pass
                    # If this column is explicitly a stream or class column, render as string (no decimals)
                    if cidx in stream_cols or cidx in class_cols:
                        # If numeric, render without decimals
                        try:
                            fv = float(v)
                            row.append(f"{fv:.0f}")
                        except Exception:
                            row.append(str(v) if v is not None else '')
                        continue
                    try:
                        fv = float(v)
                        if (first_col_is_serial and cidx == 0) or is_rank_row or (isinstance(c, str) and 'rank' in c.lower()):
                            try:
                                row.append(str(int(fv)))
                            except Exception:
                                row.append(str(fv))
                        else:
                            row.append(f"{fv:.2f}")
                    except Exception:
                        row.append(str(v) if v is not None else '')
                rows.append(row)

            col_widths = [((A4[0] - 0.8 * inch) / max(1, len(header)))] * len(header)
            tbl = Table(rows, colWidths=col_widths, hAlign='LEFT')
            tbl_style = TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0E6BA8')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ])

            # Color 'Difference' column values
            try:
                if 'Difference' in header:
                    diff_idx = header.index('Difference')
                    for ridx, rowvals in enumerate(rows[1:], start=1):
                        try:
                            cell = rowvals[diff_idx]
                            if cell is None or (isinstance(cell, str) and (cell.strip() == '' or cell.strip() == '-')):
                                continue
                            val = float(str(cell))
                            if val < 0:
                                tbl_style.add('TEXTCOLOR', (diff_idx, ridx), (diff_idx, ridx), colors.red)
                            elif val > 0:
                                tbl_style.add('TEXTCOLOR', (diff_idx, ridx), (diff_idx, ridx), colors.green)
                        except Exception:
                            continue
            except Exception:
                pass

            tbl.setStyle(tbl_style)
            story.append(tbl)
        except Exception:
            pass

    # If mi_df is a dict of {section_name: DataFrame}, render multiple sections; otherwise render single table
    try:
        if isinstance(mi_df, dict):
            for sec, dfsec in mi_df.items():
                try:
                    story.append(Paragraph(str(sec), ParagraphStyle('section', parent=styles['Heading2'], alignment=0, fontSize=12)))
                    story.append(Spacer(1, 0.08 * inch))
                    _add_table_from_df(dfsec)
                    story.append(Spacer(1, 0.16 * inch))
                except Exception:
                    continue
        else:
            _add_table_from_df(mi_df)
    except Exception:
        pass

    # Build PDF with footer
    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    buf.seek(0)
    return buf


# Page configuration
st.set_page_config(page_title="Exam Analytics", layout="wide")

# Define persistent storage path
from modules.storage import get_storage_dir as _get_storage_dir
STORAGE_DIR = _get_storage_dir()
METADATA_FILE = os.path.join(STORAGE_DIR, 'exams_metadata.json')
# Optional DB helper
try:
    from modules import db as _db
except Exception:
    _db = None

# Create storage directory if it doesn't exist
os.makedirs(STORAGE_DIR, exist_ok=True)

# Helper functions for persistence
def save_exam_to_disk(exam_id, exam_metadata, exam_data, exam_raw_data, exam_config):
    """Save a single exam ONLY to S3 storage (no local fallback)"""
    try:
        # Get school ID for namespacing
        try:
            from modules import auth as _auth
            sid = _auth.get_current_school_id() or 'global'
        except Exception:
            sid = 'global'

        # CRITICAL: Force S3-only mode
        if storage is None:
            st.error("❌ Storage adapter not available. Cannot save exam.")
            return False
        
        # Verify S3 is actually configured
        if not hasattr(storage, 'is_s3_enabled') or not storage.is_s3_enabled():
            st.error("❌ S3 storage not configured. Please set AWS credentials.")
            return False

        # Save metadata to S3
        try:
            all_metadata = storage.read_json(f"{sid}/exams_metadata.json") or {}
            all_metadata[exam_id] = exam_metadata
            if not storage.write_json(f"{sid}/exams_metadata.json", all_metadata):
                st.error("Failed to write metadata to S3")
                return False
        except Exception as e:
            st.error(f"Failed to save metadata to S3: {e}")
            return False

        # Save exam dataframes to S3 as pickles
        try:
            if isinstance(exam_data, pd.DataFrame):
                if not storage.write_pickle(f"{sid}/{exam_id}/data.pkl", exam_data):
                    st.error("Failed to write exam data to S3")
                    return False
            if isinstance(exam_raw_data, pd.DataFrame):
                if not storage.write_pickle(f"{sid}/{exam_id}/raw_data.pkl", exam_raw_data):
                    st.error("Failed to write raw data to S3")
                    return False
            if not storage.write_json(f"{sid}/{exam_id}/config.json", exam_config):
                st.error("Failed to write config to S3")
                return False
        except Exception as e:
            st.error(f"Failed to save exam files to S3: {e}")
            return False

        st.success(f"✅ Exam saved to S3: {exam_id}")
        return True
        
    except Exception as e:
        st.error(f"Error saving exam to S3: {e}")
        return False

def load_all_metadata():
    """Load all exam metadata from S3 storage"""
    try:
        # Get school ID
        try:
            from modules import auth as _auth
            sid = _auth.get_current_school_id() or 'global'
        except Exception:
            sid = 'global'
        
        # Load from S3
        if storage is None or not hasattr(storage, 'is_s3_enabled') or not storage.is_s3_enabled():
            st.warning("⚠️ S3 storage not configured")
            return {}
        
        data = storage.read_json(f"{sid}/exams_metadata.json")
        return data or {}
    except Exception as e:
        st.error(f"Error loading metadata: {e}")
        return {}

def load_exam_from_disk(exam_id):
    """Load a single exam from S3 storage"""
    try:
        # Get school ID
        try:
            from modules import auth as _auth
            sid = _auth.get_current_school_id() or 'global'
        except Exception:
            sid = 'global'
        
        # Try reading via storage adapter from S3
        exam_data = storage.read_pickle(f"{sid}/{exam_id}/data.pkl")
        exam_raw_data = storage.read_pickle(f"{sid}/{exam_id}/raw_data.pkl")
        exam_config = storage.read_json(f"{sid}/{exam_id}/config.json") or {}
        return exam_data, exam_raw_data, exam_config
    except Exception as e:
        st.error(f"Error loading exam {exam_id}: {e}")
        return None, None, None

def delete_exam_from_disk(exam_id):
    """Delete an exam from S3 storage"""
    try:
        # Get school ID
        try:
            from modules import auth as _auth
            sid = _auth.get_current_school_id() or 'global'
        except Exception:
            sid = 'global'
        
        # Remove from metadata via storage adapter
        try:
            all_metadata = storage.read_json(f"{sid}/exams_metadata.json") or {}
            all_metadata.pop(exam_id, None)
            storage.write_json(f"{sid}/exams_metadata.json", all_metadata)
        except Exception:
            pass

        # Remove all objects under the exam prefix
        try:
            objs = storage.list_objects(prefix=f"{sid}/{exam_id}")
            for o in objs:
                try:
                    # Reconstruct full path with prefix
                    storage.delete(f"{sid}/{exam_id}/{o}")
                except Exception:
                    pass
        except Exception:
            pass

        return True
    except Exception as e:
        st.error(f"Error deleting exam from disk: {e}")
        return False

def load_all_exams_into_session():
    """Load all saved exams from disk into session state"""
    all_metadata = load_all_metadata()
    
    # Build saved_exams list from metadata
    st.session_state.saved_exams = []
    for exam_id, metadata in all_metadata.items():
        st.session_state.saved_exams.append(metadata)
    
    # Load data on demand (lazy loading to avoid memory issues)
    # We'll load individual exams when needed
    st.session_state.saved_exam_data = {}
    st.session_state.saved_exam_raw_data = {}
    st.session_state.saved_exam_configs = {}
    
    # Optionally preload all (for small datasets)
    for exam_id in all_metadata.keys():
        data, raw_data, config = load_exam_from_disk(exam_id)
        if data is not None:
            st.session_state.saved_exam_data[exam_id] = data
        if raw_data is not None:
            st.session_state.saved_exam_raw_data[exam_id] = raw_data
        if config:
            st.session_state.saved_exam_configs[exam_id] = config

# Custom CSS for modern design
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 2rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
    }
    
    .section-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #2c3e50;
        margin-top: 2rem;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #667eea;
    }
    
    .info-card {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    }
    
    .metric-container {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #667eea;
        margin: 0.5rem 0;
    }
    
    .stButton>button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 0.5rem 2rem;
        font-weight: 600;
        border-radius: 5px;
        transition: all 0.3s;
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state for saved exams
# Ensure saved exams are loaded from disk when session state is missing or empty
if 'saved_exams' not in st.session_state or not st.session_state.get('saved_exams'):
    # Populate session state from on-disk metadata (safe to call repeatedly)
    try:
        load_all_exams_into_session()
    except Exception:
        # Ensure keys exist to avoid downstream KeyError
        st.session_state.saved_exams = st.session_state.get('saved_exams', [])
        st.session_state.saved_exam_data = st.session_state.get('saved_exam_data', {})
        st.session_state.saved_exam_raw_data = st.session_state.get('saved_exam_raw_data', {})
        st.session_state.saved_exam_configs = st.session_state.get('saved_exam_configs', {})
# Ensure backing stores exist for data/configs
if 'saved_exam_data' not in st.session_state:
    st.session_state.saved_exam_data = {}
if 'saved_exam_configs' not in st.session_state:
    st.session_state.saved_exam_configs = {}
if 'saved_exam_raw_data' not in st.session_state:
    st.session_state.saved_exam_raw_data = {}

# Header
st.markdown('<div class="main-header">📁 Access Saved Exams</div>', unsafe_allow_html=True)

# Back to home button with better styling
col1, col2, col3 = st.columns([2, 6, 2])
with col1:
    if st.button("🏠 Back to Home", use_container_width=True, type="primary"):
        st.session_state.current_page = 'home'
        st.session_state.show_home_header = True
        # avoid calling st.rerun() inside the button callback

# Main content
st.markdown('<div class="section-header">Saved Exams</div>', unsafe_allow_html=True)

if len(st.session_state.saved_exams) == 0:
    st.markdown("""
    <div class="info-card">
        <h3>📂 No Exams Saved Yet</h3>
        <p>You haven't saved any exam data yet. To save your first exam:</p>
        <ol>
            <li>Go to <strong>Home</strong> page</li>
            <li>Click on <strong>📋 Paste New Exam</strong></li>
            <li>Enter or paste your exam data</li>
            <li>Click <strong>Generate Sheet</strong> to process the data</li>
            <li>Review and click <strong>💾 Save Exam</strong> to save permanently</li>
        </ol>
        <p>Once you save exams, you'll be able to:</p>
        <ul>
            <li>Access saved exams anytime from this page</li>
            <li>Compare performance across multiple exams</li>
            <li>Track student progress over time</li>
            <li>Analyze subject-wise trends</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"**Total Exams Saved:** {len(st.session_state.saved_exams)}")

    # Display saved exams in a table
    exam_data = []
    for idx, exam in enumerate(st.session_state.saved_exams):
        eid = exam.get('exam_id')
        exam_dir = os.path.join(STORAGE_DIR, eid) if eid else None
        data_path = os.path.join(exam_dir, 'data.pkl') if exam_dir else None
        raw_path = os.path.join(exam_dir, 'raw_data.pkl') if exam_dir else None

        # If we have in-memory processed data for this exam but it's not saved on disk,
        # persist it now so the Data Status won't be 'Missing' after restart.
        try:
            data_df = st.session_state.get('saved_exam_data', {}).get(eid)
            raw_df = st.session_state.get('saved_exam_raw_data', {}).get(eid)
            cfg = st.session_state.get('saved_exam_configs', {}).get(eid, {})
            # Only attempt to save when we have a DataFrame in memory and no data file on disk
            if data_df is not None and exam_dir and not os.path.exists(data_path):
                # save using existing helper to keep metadata consistent
                save_exam_to_disk(eid, exam, data_df, raw_df, cfg)
        except Exception:
            pass

        # Consider data present if it's either in-memory or on-disk
        data_present = (eid in st.session_state.get('saved_exam_data', {})) or (exam_dir and os.path.exists(data_path))
        raw_present = (eid in st.session_state.get('saved_exam_raw_data', {})) or (exam_dir and os.path.exists(raw_path))

        if data_present:
            status = 'Full'
        elif raw_present:
            status = 'Raw only'
        else:
            status = 'Missing'

        exam_data.append({
            'No.': idx + 1,
            'Exam Name': exam.get('exam_name', 'Unnamed Exam'),
            'Date Saved': exam.get('date_saved', 'N/A'),
            'Class': exam.get('class_name', 'N/A'),
            'Total Students': exam.get('total_students', 0),
            'Subjects': exam.get('num_subjects', 0),
            'Storage': exam.get('storage', 'in-memory'),
            'Data Status': status
        })

    df_exams = pd.DataFrame(exam_data)
    st.dataframe(df_exams, use_container_width=True, hide_index=True)

    # Grouped view: Year -> Class
    st.markdown('<div class="section-header">Browse by Year and Class</div>', unsafe_allow_html=True)

    # Helper to normalize class names
    import re
    def normalize_class_name(cls_raw: str) -> str:
        """Normalize class names to standard format (e.g., 'Grade 9')"""
        if not cls_raw or pd.isna(cls_raw):
            return "Unknown"
        import re
        class_str = str(cls_raw).strip().lower()
        class_str = re.sub(r'[^a-z0-9]+', ' ', class_str)  # replace non-alphanum with space
        class_str = re.sub(r'\s+', ' ', class_str).strip()
        # Map number words to digits
        number_words = {
            'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5',
            'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10',
            'eleven': '11', 'twelve': '12'
        }
        for word, digit in number_words.items():
            class_str = re.sub(rf'\b{word}\b', digit, class_str)
        # Look for 'grade' or 'form' followed by a number
        match = re.search(r'(grade|form)\s*([0-9]{1,2})', class_str)
        if match:
            return f"Grade {match.group(2)}"
        # Look for just a number (e.g., '9')
        match2 = re.search(r'\b([0-9]{1,2})\b', class_str)
        if match2:
            return f"Grade {match2.group(1)}"
        return class_str.title()

    # Load all_metadata once for use in both main and expander logic
    all_metadata = load_all_metadata()
                                    

    # Detailed cards with actions per saved exam - grouped by year and normalized class
    st.markdown('<div class="section-header">Manage Saved Exams</div>', unsafe_allow_html=True)

    # Group exams by year and normalized class name
    grouped = {}
    class_display_map = {}

    for exam in st.session_state.saved_exams:
        # Use date_saved to extract year if available, else fallback to 'year' field
        date_saved = exam.get('date_saved', None)
        if date_saved and isinstance(date_saved, str) and '-' in date_saved:
            year = date_saved.split('-')[0]
        else:
            year = exam.get('year', 'Unknown')
        cls_raw = exam.get('class_name', 'Unspecified')
        cls_normalized = normalize_class_name(cls_raw)

        # Always use the normalized display name (e.g., 'Grade 9')
        class_display_map[cls_normalized] = cls_normalized

        if year not in grouped:
            grouped[year] = {}
        if cls_normalized not in grouped[year]:
            grouped[year][cls_normalized] = []
        grouped[year][cls_normalized].append(exam)
    
    # Display grouped structure
    for year in sorted(grouped.keys(), reverse=True, key=lambda x: (x=='Unknown', x)):
        with st.expander(f"📅 {year}", expanded=False):
            for cls_norm in sorted(grouped[year].keys(), key=lambda x: (x=='unspecified', x)):
                cls_display = class_display_map.get(cls_norm, cls_norm)
                with st.expander(f"🏷️ Class: {cls_display}"):
                    exams_in_group = grouped[year][cls_norm]
                    for exam in exams_in_group:
                        exam_id = exam.get('exam_id')
                        exam_name = exam.get('exam_name', 'Unnamed Exam')
                        with st.expander(f"🗂️ {exam_name}"):
                            m1, m2, m3 = st.columns(3)
                            with m1:
                                st.write(f"Date Saved: {exam.get('date_saved','N/A')}")
                                st.write(f"Class: {exam.get('class_name','N/A')}")
                            with m2:
                                st.write(f"Students: {exam.get('total_students',0)}")
                                st.write(f"Subjects: {exam.get('num_subjects',0)}")
                            with m3:
                                cfg = st.session_state.saved_exam_configs.get(exam_id, {})
                                grading_on = cfg.get('grading_enabled', False)
                                rank_basis = cfg.get('ranking_basis', 'Totals')
                                st.write(f"Grading: {'On' if grading_on else 'Off'}")
                                st.write(f"Rank by: {rank_basis}")

                            # Optional preview
                            if st.checkbox(f"Preview first 10 rows", key=f"prev_manage_{exam_id}"):
                                # Try to get data from session; if missing, attempt to load from disk on-demand
                                data_df = st.session_state.saved_exam_data.get(exam_id)
                                if data_df is None:
                                    try:
                                        disk_data, disk_raw, disk_cfg = load_exam_from_disk(exam_id)
                                        if isinstance(disk_data, pd.DataFrame):
                                            st.session_state.saved_exam_data[exam_id] = disk_data
                                            data_df = disk_data
                                        if isinstance(disk_raw, pd.DataFrame):
                                            st.session_state.saved_exam_raw_data[exam_id] = disk_raw
                                        if isinstance(disk_cfg, dict) and disk_cfg:
                                            st.session_state.saved_exam_configs[exam_id] = disk_cfg
                                    except Exception:
                                        data_df = None

                                if isinstance(data_df, pd.DataFrame):
                                    st.dataframe(data_df.head(10), use_container_width=True)
                                else:
                                    st.info("No data available for this exam.")
                                    # Show helpful diagnostics: whether raw data or files exist on disk
                                    exam_dir = os.path.join(STORAGE_DIR, exam_id)
                                    files = []
                                    try:
                                        if os.path.exists(exam_dir):
                                            files = os.listdir(exam_dir)
                                    except Exception:
                                        files = []
                                    raw_exists = 'raw_data.pkl' in files
                                    data_exists = 'data.pkl' in files
                                    st.write(f"Data file present: {data_exists}")
                                    st.write(f"Raw file present: {raw_exists}")
                                    if files:
                                        st.write('Files in exam folder:')
                                        for f in files:
                                            st.write('-', f)
                                    else:
                                        st.write('No files found in the exam folder.')

                            a1, a2, a3 = st.columns([1,1,3])
                            with a1:
                                if st.button("Open Generated Sheet", key=f"open_manage_{exam_id}"):
                                    st.session_state.selected_saved_exam_id = exam_id
                                    st.session_state.rebuild_from_raw = False
                                    st.session_state.go_to_analysis = True
                                    with st.popover("Exam Loaded!", use_container_width=True):
                                        st.markdown("""
                                        ### ✅ Exam Loaded!
                                        To analyze this marksheet:
                                        1. **Click 'Home' in the sidebar**
                                        2. The app will load the saved exam into the Raw Mark Sheet page
                                        3. Click **Generate Marksheet** to view the generated analysis
                                        """)
                                        st.button("OK", key=f"ok_popover_{exam_id}")
                            with a2:
                                if st.button("Delete", key=f"del_manage_{exam_id}"):
                                    # Remove from lists and dicts
                                    st.session_state.saved_exams = [e for e in st.session_state.saved_exams if e.get('exam_id') != exam_id]
                                    st.session_state.saved_exam_data.pop(exam_id, None)
                                    st.session_state.saved_exam_raw_data.pop(exam_id, None)
                                    st.session_state.saved_exam_configs.pop(exam_id, None)
                                    
                                    # Delete from disk
                                    delete_exam_from_disk(exam_id)
                                    
                                    st.success(f"Deleted '{exam_name}' permanently.")
                                    # avoid calling st.rerun() inside the button callback

                            # If generated data is missing but raw data exists, offer a rebuild action
                            if (exam_id not in st.session_state.get('saved_exam_data', {})) and (exam_id in st.session_state.get('saved_exam_raw_data', {})):
                                if st.button("🔧 Rebuild from raw & Generate", key=f"rebuild_{exam_id}"):
                                    # Set flags so app prioritizes rebuilding from raw and opens analysis view
                                    st.session_state.selected_saved_exam_id = exam_id
                                    st.session_state.rebuild_from_raw = True
                                    st.session_state.view = 'analysis'
                                    st.success('Rebuilding from raw data and opening analysis...')
                                    # avoid calling st.rerun() inside the button callback

    st.markdown('<div class="section-header">📊 Exam Analysis</div>', unsafe_allow_html=True)
    
    # Analysis mode selector
    analysis_mode = st.radio(
        "Select Analysis Mode:",
        options=["Single Exam Stream Analysis", "Multi-Exam Comparison"],
        horizontal=True
    )
    
    if analysis_mode == "Single Exam Stream Analysis":
        # Single exam detailed stream comparison
        st.markdown("#### Select Exam to Analyze")

        # Build filter selectors: Year, Term, Exam Kind (derived from exam_name first segment)
        all_meta = st.session_state.get('saved_exams', [])
        years = sorted({str(m.get('year')) for m in all_meta if m.get('year')})
        raw_terms = sorted({str(m.get('term')).strip() for m in all_meta if m.get('term')})
        kinds = sorted({_exam_kind_from_label(m.get('exam_name') or '') for m in all_meta if m.get('exam_name')})

        # Normalizer for term labels (simple): map common patterns to Term 1/2/3
        def _normalize_term_label_local(t):
            if not t:
                return ''
            s = str(t).strip().lower()
            # canonicalize common 'end term' variants
            s_n = re.sub(r'[^a-z0-9\s-]', '', s)
            if 'end' in s_n and 'term' in s_n:
                return 'End Term'
            # term number variants: term1, term 1, term-one, term one, first term, etc.
            if re.search(r'(?:term[\s\-]*1|term1|term[\s\-]*one|\bfirst\b|\bone\b|\b1\b)', s_n):
                return 'Term 1'
            if re.search(r'(?:term[\s\-]*2|term2|term[\s\-]*two|\bsecond\b|\btwo\b|\b2\b)', s_n):
                return 'Term 2'
            if re.search(r'(?:term[\s\-]*3|term3|term[\s\-]*three|\bthird\b|\bthree\b|\b3\b)', s_n):
                return 'Term 3'
            return str(t).strip()

        norm_terms = sorted({_normalize_term_label_local(t) for t in raw_terms if t})

        col_y, col_t, col_k = st.columns([1,1,2])
        with col_y:
            year_choice = st.selectbox('Year', options=['All'] + years, index=0)
        with col_t:
            term_choice = st.selectbox('Term', options=['All'] + norm_terms, index=0)
        with col_k:
            kind_choice = st.selectbox('Exam Kind', options=['All'] + kinds, index=0)

        # Filter exams according to selections
        def _matches_filters(meta):
            if year_choice != 'All' and str(meta.get('year')) != str(year_choice):
                return False
            if term_choice != 'All':
                if _normalize_term_label_local(meta.get('term')) != term_choice:
                    return False
            if kind_choice != 'All' and _exam_kind_from_label(meta.get('exam_name')) != kind_choice:
                return False
            return True

        filtered = [m for m in all_meta if _matches_filters(m)]

        if not filtered:
            st.info('No exams match the selected Year/Term/Kind filters.')
            selected_exam_name = None
        else:
            exam_names = [m.get('exam_name', f"Exam") for m in filtered]
            selected_exam_name = st.selectbox('Choose an exam:', options=exam_names)
            
            if selected_exam_name:
                # Get exam data
                selected_exam_obj = next((e for e in st.session_state.saved_exams if e.get('exam_name') == selected_exam_name), None)
                
                if selected_exam_obj:
                    exam_id = selected_exam_obj.get('exam_id')
                    exam_df = st.session_state.saved_exam_data.get(exam_id)
                    
                    if isinstance(exam_df, pd.DataFrame) and not exam_df.empty:
                        st.markdown(f"### 📋 Analysis: {selected_exam_name}")
                        st.markdown("---")
                        
                        # Check if Class column exists
                        if 'Class' not in exam_df.columns:
                            st.warning("This exam doesn't have a 'Class' column for stream analysis.")
                        else:
                            # Get all streams/classes - filter out numeric values and summary rows
                            streams = exam_df['Class'].dropna().unique()
                            
                            # Filter valid streams: must contain at least one letter, exclude summary words
                            valid_streams = []
                            for s in streams:
                                s_str = str(s).strip()
                                # Skip if empty
                                if not s_str:
                                    continue
                                # Skip summary words
                                if s_str.lower() in ['mean', 'total', 'average', 'sum']:
                                    continue
                                # Skip pure numbers (like 1296, 9.00, 9)
                                try:
                                    float(s_str)
                                    continue  # It's a number, skip it
                                except ValueError:
                                    # Not a pure number, check if it has at least one letter
                                    if any(c.isalpha() for c in s_str):
                                        valid_streams.append(s)
                            
                            streams = valid_streams
                            
                            if len(streams) == 0:
                                st.info("No streams/classes found in this exam.")
                            else:
                                st.markdown(f"**Streams Found:** {', '.join(map(str, streams))}")
                                st.markdown("---")
                                
                                # Stream comparison metrics
                                st.markdown("### 🔍 Stream Performance Comparison")
                                
                                stream_stats = []
                                
                                for stream in streams:
                                    # Filter data for this stream
                                    stream_data = exam_df[exam_df['Class'] == stream].copy()
                                    
                                    if not stream_data.empty and 'Total' in stream_data.columns:
                                        totals = pd.to_numeric(stream_data['Total'], errors='coerce')
                                        valid_totals = totals.dropna()
                                        
                                        if len(valid_totals) > 0:
                                            stream_stats.append({
                                                'Stream': str(stream),
                                                'Students': len(stream_data),
                                                'Average': round(valid_totals.mean(), 2),
                                                'Highest': round(valid_totals.max(), 2),
                                                'Lowest': round(valid_totals.min(), 2),
                                                'Std Dev': round(valid_totals.std(), 2)
                                            })
                                
                                if stream_stats:
                                    # Display metrics in columns
                                    cols = st.columns(len(stream_stats))
                                    for idx, (col, stat) in enumerate(zip(cols, stream_stats)):
                                        with col:
                                            st.markdown(f"#### {stat['Stream']}")
                                            st.metric("Students", stat['Students'])
                                            st.metric("Average", f"{stat['Average']:.1f}")
                                            st.metric("Highest", f"{stat['Highest']:.1f}")
                                            st.metric("Lowest", f"{stat['Lowest']:.1f}")
                                    
                                    # Detailed comparison table
                                    st.markdown("#### 📊 Detailed Statistics")
                                    stats_df = pd.DataFrame(stream_stats)
                                    st.dataframe(stats_df, use_container_width=True, hide_index=True)
                                    
                                    # Stream rankings
                                    st.markdown("#### 🏆 Stream Rankings")
                                    ranked = stats_df.sort_values('Average', ascending=False).reset_index(drop=True)
                                    ranked.insert(0, 'Rank', range(1, len(ranked) + 1))
                                    
                                    # Color code the rankings
                                    for idx, row in ranked.iterrows():
                                        rank = row['Rank']
                                        if rank == 1:
                                            emoji = "🥇"
                                            color = "#FFD700"
                                        elif rank == 2:
                                            emoji = "🥈"
                                            color = "#C0C0C0"
                                        elif rank == 3:
                                            emoji = "🥉"
                                            color = "#CD7F32"
                                        else:
                                            emoji = f"{rank}."
                                            color = "#E0E0E0"
                                        
                                        st.markdown(f"""
                                        <div style='padding: 1rem; margin: 0.5rem 0; background: {color}; border-radius: 8px;'>
                                            <strong>{emoji} {row['Stream']}</strong> - 
                                            Average: <strong>{row['Average']:.1f}</strong> | 
                                            Students: {row['Students']} | 
                                            Range: {row['Lowest']:.1f} - {row['Highest']:.1f}
                                        </div>
                                        """, unsafe_allow_html=True)
                                    
                                    # Subject-wise stream comparison (single table)
                                    st.markdown("#### 📚 Subject-wise Stream Comparison (single table)")

                                    # Identify subject columns (exclude meta)
                                    exclude_cols = {'name', 'adm no', 'admno', 'adm_no', 'class', 'total', 'mean', 
                                                   'rank', 's/rank', 'points', 'grade', 'mean grade'}
                                    # Use columns that contain at least one numeric-like value
                                    subject_cols = []
                                    for col in exam_df.columns:
                                        if col.lower() in exclude_cols:
                                            continue
                                        # try to find at least one numeric-like entry
                                        sample = exam_df[col].head(50)
                                        found = False
                                        for v in sample:
                                            if convert_score_to_numeric(v) is not None:
                                                found = True
                                                break
                                        if found:
                                            subject_cols.append(col)

                                    if not subject_cols:
                                        st.info("No subject columns detected for this exam.")
                                    else:
                                        # Build mean table: subjects x streams
                                        table_data = {}
                                        for subj in subject_cols:
                                            for stream in streams:
                                                subset = exam_df[exam_df['Class'] == stream]
                                                vals = subset[subj].apply(convert_score_to_numeric).dropna().tolist()
                                                if vals:
                                                    table_data[(subj, stream)] = sum(vals) / len(vals)
                                                else:
                                                    table_data[(subj, stream)] = None

                                        # Interactive subject × stream mean table with Include checkbox (editable in-place)
                                        rows = []
                                        for subj in subject_cols:
                                            r = {'Subject': subj}
                                            for s in streams:
                                                v = table_data.get((subj, s))
                                                r[s] = round(v, 2) if v is not None else None
                                            r['Include'] = True
                                            rows.append(r)
                                        subject_select_df = pd.DataFrame(rows)

                                        # Manage included subjects state so selection persists across reruns
                                        included_key = f"included_subjects_{exam_id}"
                                        if included_key not in st.session_state:
                                            st.session_state[included_key] = list(subject_cols)

                                        # Show/Hide the editable subject table via buttons
                                        show_key = f"show_subj_table_{exam_id}"
                                        if show_key not in st.session_state:
                                            st.session_state[show_key] = False

                                        # Render toggle buttons (show/hide subject editor). Labels indicate action on the table.
                                        col_toggle, _ = st.columns([1, 4])
                                        with col_toggle:
                                            if not st.session_state[show_key]:
                                                if st.button("Show subjects in table", key=f"show_btn_{exam_id}"):
                                                    st.session_state[show_key] = True
                                                # Provide a greyed-out explanation while the editor is hidden
                                                st.caption("Subjects marked 'Include' will appear in the table and exported PDF. Click 'Show subjects in table' to edit which subjects are included.")
                                            else:
                                                if st.button("Hide subjects in table", key=f"hide_btn_{exam_id}"):
                                                    st.session_state[show_key] = False

                                        # If visible, allow editing (data_editor preferred)
                                        included_subjects = list(st.session_state[included_key])
                                        if st.session_state[show_key]:
                                            try:
                                                if hasattr(st, 'data_editor'):
                                                    edited = st.data_editor(subject_select_df, use_container_width=True, hide_index=True, key=f"subj_editor_{exam_id}")
                                                    if isinstance(edited, pd.DataFrame) and 'Include' in edited.columns:
                                                        included_subjects = edited[edited['Include'] == True]['Subject'].tolist()
                                                        st.session_state[included_key] = included_subjects
                                                else:
                                                    st.dataframe(subject_select_df.set_index('Subject')[streams].style.format("{:.2f}", na_rep='-'), use_container_width=True)
                                                    excluded = st.multiselect('Select subjects to exclude from PDF', options=subject_cols, key=f'subj_exclude_{exam_id}')
                                                    included_subjects = [s for s in subject_cols if s not in excluded]
                                                    st.session_state[included_key] = included_subjects
                                            except Exception:
                                                excluded = st.multiselect('Select subjects to exclude from PDF (fallback)', options=subject_cols, key=f'subj_exclude_{exam_id}')
                                                included_subjects = [s for s in subject_cols if s not in excluded]
                                                st.session_state[included_key] = included_subjects

                                        # Display included subjects table (2 decimal places) and include Average & Rank columns
                                        disp = {s: [] for s in streams}
                                        included_list = list(st.session_state[included_key])
                                        for subj in included_list:
                                            for s in streams:
                                                v = table_data.get((subj, s))
                                                disp[s].append(round(v,2) if v is not None else None)
                                        df_out = pd.DataFrame(disp, index=included_list)

                                        # Compute per-subject average across streams (ignore NaNs)
                                        try:
                                            subj_avgs = df_out.mean(axis=1, skipna=True)
                                            # Dense rank: highest average -> rank 1
                                            subj_rank = subj_avgs.rank(method='dense', ascending=False).astype(int)

                                            # Build display frame: streams... Average, Rank
                                            df_display = df_out.copy()
                                            df_display['Average'] = subj_avgs.round(2)
                                            df_display['Rank'] = subj_rank

                                            # Sort by Rank then Average (best first)
                                            df_display = df_display.sort_values(['Rank','Average'], ascending=[True, False])

                                            # Format numeric columns to 2 decimals for display (Rank stays integer)
                                            fmt_cols = [c for c in df_display.columns if c != 'Rank']
                                            st.dataframe(df_display.style.format("{:.2f}", subset=fmt_cols, na_rep='-'), use_container_width=True, height=500)

                                            # Provide CSV download of the displayed table (subjects as first column)
                                            try:
                                                export_df = df_display.reset_index()
                                                # Ensure first column is named 'Subject'
                                                if export_df.columns[0] != 'Subject':
                                                    export_df.rename(columns={export_df.columns[0]: 'Subject'}, inplace=True)
                                                csv_bytes = export_df.to_csv(index=False).encode('utf-8')
                                                st.download_button(label="Download table (CSV)", data=csv_bytes, file_name=f"{selected_exam_name.replace(' ','_')}_subject_stream_table.csv", mime='text/csv', key=f"download_table_{exam_id}")
                                            except Exception:
                                                pass
                                        except Exception:
                                            # Fallback: show the plain table if averaging/ranking fails
                                            st.dataframe(df_out.style.format("{:.2f}", na_rep='-'), use_container_width=True, height=400)

                                        # Compute per-stream Total means (exact mean of 'Total' column for each stream)
                                        stream_total_means = {}
                                        if 'Total' in exam_df.columns:
                                            for s in streams:
                                                subset = exam_df[exam_df['Class'] == s]
                                                totals = pd.to_numeric(subset['Total'], errors='coerce').dropna()
                                                stream_total_means[s] = float(totals.mean()) if len(totals) > 0 else None
                                        else:
                                            stream_total_means = None

                                        # PDF export using reportlab (respect included_subjects and use stream_total_means for Average row)
                                        if st.button("📄 Download PDF (subject × stream table)", key=f"pdf_subj_{exam_id}"):
                                            try:
                                                buf = generate_pdf_stream_table(selected_exam_name, subject_cols, streams, table_data, include_subjects=included_subjects, stream_total_means=stream_total_means)
                                                pdf_bytes = buf.getvalue() if hasattr(buf, 'getvalue') else buf
                                                st.download_button("Download PDF", data=pdf_bytes, file_name=f"{selected_exam_name.replace(' ','_')}_stream_table.pdf", mime='application/pdf')
                                            except Exception as e:
                                                st.error(f"Failed to generate PDF: {e}")

                                        # Offer Most Improved calculation vs another exam
                                        st.markdown("---")
                                        st.markdown("### 🔁 Most Improved Student (compare with another exam)")
                                        other_exam_names = [n for n in [e.get('exam_name') for e in st.session_state.saved_exams] if n != selected_exam_name]
                                        if not other_exam_names:
                                            st.info("No other exams available to compare against.")
                                        else:
                                            compare_exam = st.selectbox("Select baseline exam:", options=other_exam_names, key=f"cmp_{exam_id}")
                                            # Automatically compute most improved when a baseline exam is selected
                                            if compare_exam:
                                                comp_obj = next((e for e in st.session_state.saved_exams if e.get('exam_name') == compare_exam), None)
                                                if comp_obj:
                                                    comp_id = comp_obj.get('exam_id')
                                                    # load comp df if needed
                                                    comp_df = st.session_state.saved_exam_data.get(comp_id)
                                                    if comp_df is None:
                                                        try:
                                                            comp_df = pd.read_pickle(os.path.join(STORAGE_DIR, comp_id, 'data.pkl'))
                                                            st.session_state.saved_exam_data[comp_id] = comp_df
                                                        except Exception as e:
                                                            st.error(f"Failed to load comparison exam data: {e}")
                                                            comp_df = None

                                                    if isinstance(comp_df, pd.DataFrame):
                                                        # determine matching key
                                                        id_cols = ['Adm No','AdmNo','Adm_No','Admission No','IndexNo']
                                                        match_col = None
                                                        for c in id_cols:
                                                            if c in exam_df.columns and c in comp_df.columns:
                                                                match_col = c
                                                                break
                                                        if not match_col and 'Name' in exam_df.columns and 'Name' in comp_df.columns:
                                                            match_col = 'Name'

                                                        if not match_col:
                                                            st.error('No matching identifier found between exams (Adm No or Name).')
                                                        else:
                                                            def overall_numeric_from_row(row, cols_to_check):
                                                                # Prefer explicit Mean/Total if present, otherwise aggregate subject cols
                                                                for k in ['Mean', 'Total']:
                                                                    if k in row.index:
                                                                        v = convert_score_to_numeric(row.get(k))
                                                                        if v is not None:
                                                                            return v
                                                                vals = []
                                                                for s in cols_to_check:
                                                                    if s in row.index:
                                                                        nv = convert_score_to_numeric(row.get(s))
                                                                        if nv is not None:
                                                                            vals.append(nv)
                                                                return sum(vals) if vals else None

                                                            # Build mapping from this exam's subject names to comparison exam column names
                                                            comp_cols_available = list(comp_df.columns)
                                                            # Normalization helper
                                                            def _norm(x):
                                                                if x is None:
                                                                    return ''
                                                                return re.sub(r"\s+"," ", str(x).strip()).lower()

                                                            comp_norm_map = { _norm(c): c for c in comp_cols_available }

                                                            subj_to_compcol = {}
                                                            missing_subjects = []
                                                            for subj in subject_cols:
                                                                n = _norm(subj)
                                                                match = None
                                                                # exact normalized match
                                                                if n in comp_norm_map:
                                                                    match = comp_norm_map[n]
                                                                else:
                                                                    # try startswith/contains
                                                                    for k_norm, orig in comp_norm_map.items():
                                                                        if n and (k_norm.startswith(n) or n.startswith(k_norm) or n in k_norm or k_norm in n):
                                                                            match = orig
                                                                            break
                                                                # fuzzy fallback
                                                                if match is None:
                                                                    try:
                                                                        import difflib
                                                                        candidates = difflib.get_close_matches(n, comp_norm_map.keys(), n=1, cutoff=0.7)
                                                                        if candidates:
                                                                            match = comp_norm_map[candidates[0]]
                                                                    except Exception:
                                                                        match = None

                                                                if match:
                                                                    subj_to_compcol[subj] = match
                                                                else:
                                                                    subj_to_compcol[subj] = None
                                                                    missing_subjects.append(subj)

                                                            # Select columns safely for left and right; only include existing match_col
                                                            left_cols = [c for c in [match_col] + subject_cols if c in exam_df.columns]
                                                            right_cols = [match_col] if match_col in comp_df.columns else []
                                                            # append matched comp columns in the same order as subject_cols where available
                                                            for subj in subject_cols:
                                                                compc = subj_to_compcol.get(subj)
                                                                if compc and compc not in right_cols:
                                                                    right_cols.append(compc)

                                                            if missing_subjects:
                                                                st.warning(f"Some subjects not found in comparison exam and will be skipped: {missing_subjects}")

                                                            # Subset safely
                                                            left = exam_df[left_cols].copy()
                                                            right = comp_df[right_cols].copy()

                                                            # Compute overall using appropriate subject columns per side
                                                            left_subjects_for_overall = [c for c in subject_cols if c in left.columns]
                                                            right_subjects_for_overall = [subj_to_compcol[s] for s in subject_cols if subj_to_compcol.get(s) and subj_to_compcol[s] in right.columns]

                                                            left['_overall_'] = left.apply(lambda r: overall_numeric_from_row(r, left_subjects_for_overall), axis=1)
                                                            right['_overall_'] = right.apply(lambda r: overall_numeric_from_row(r, right_subjects_for_overall), axis=1)

                                                            # Rename the computed overall columns before merging so their names are predictable
                                                            left_small = left[[match_col, '_overall_']].rename(columns={'_overall_': '_overall_new'})
                                                            right_small = right[[match_col, '_overall_']].rename(columns={'_overall_': '_overall_old'})
                                                            # Filter out aggregate/summary rows from both sides (e.g., 'Total', 'Totals', 'Mean')
                                                            def is_aggregate_label(x):
                                                                try:
                                                                    s = str(x).strip().lower()
                                                                    if not s:
                                                                        return True
                                                                    # common summary words
                                                                    if any(word in s for word in ['total', 'totals', 'mean', 'average', 'sum', 'summary']):
                                                                        return True
                                                                    return False
                                                                except Exception:
                                                                    return True

                                                            try:
                                                                left_small = left_small[~left_small[match_col].apply(is_aggregate_label)]
                                                            except Exception:
                                                                pass
                                                            try:
                                                                right_small = right_small[~right_small[match_col].apply(is_aggregate_label)]
                                                            except Exception:
                                                                pass

                                                            merged = pd.merge(left_small, right_small, on=match_col, how='inner')
                                                            if merged.empty:
                                                                st.warning('No matched students between the two exams.')
                                                            else:
                                                                # Ensure the columns exist and compute improvement safely
                                                                if '_overall_new' not in merged.columns or '_overall_old' not in merged.columns:
                                                                    st.error('Unexpected data format after merging exams. Cannot compute improvement.')
                                                                else:
                                                                    merged['_improve_'] = merged['_overall_new'].fillna(0) - merged['_overall_old'].fillna(0)
                                                                    # Sort by improvement descending and compute dense ranks
                                                                    merged_sorted = merged.sort_values('_improve_', ascending=False).reset_index(drop=True)
                                                                    try:
                                                                        merged_sorted['Rank'] = merged_sorted['_improve_'].rank(method='dense', ascending=False).astype(int)
                                                                    except Exception:
                                                                        merged_sorted['Rank'] = 1

                                                                    # Persist merged results in session state so UI can use them after reruns
                                                                    st.session_state[f'mi_merged_{exam_id}'] = merged_sorted
                                                                    # Also persist the exam names used for _overall_old (baseline) and _overall_new (current)
                                                                    try:
                                                                        # store only the exam kind (e.g., 'End Term') rather than full exam name
                                                                        baseline_label = comp_obj.get('exam_name') if comp_obj is not None else ''
                                                                        current_label = selected_exam_name if selected_exam_name is not None else ''
                                                                        st.session_state[f'mi_merged_names_{exam_id}'] = {
                                                                            'baseline': _exam_kind_from_label(baseline_label) or 'Baseline',
                                                                            'current': _exam_kind_from_label(current_label) or 'Current'
                                                                        }
                                                                    except Exception:
                                                                        pass
                                                                    st.session_state[f'mi_computed_{exam_id}'] = True
                                                                    # Inform the user briefly that the comparison ran and how many matched students were found
                                                                    try:
                                                                        st.info(f"Most Improved computed: {len(merged_sorted)} matched students.")
                                                                    except Exception:
                                                                        pass

                                                                    # Determine default top_k for exports (no UI input shown)
                                                                    max_k = len(merged_sorted)
                                                                    default_k = min(10, max_k) if max_k > 0 else 1
                                                                    top_k = default_k

                                                                    # Prepare top_df for downloads (but do not display it as a table)
                                                                    display_cols = [match_col, '_overall_old', '_overall_new', '_improve_', 'Rank']
                                                                    safe_cols = [c for c in display_cols if c in merged_sorted.columns]
                                                                    top_df = merged_sorted.loc[:, safe_cols].head(int(top_k)).copy()
                                                                    # Use exam names instead of generic 'Baseline'/'Current'
                                                                    names_key = f'mi_merged_names_{exam_id}'
                                                                    names = st.session_state.get(names_key, {}) if isinstance(st.session_state, dict) else {}
                                                                    baseline_name = names.get('baseline', 'Baseline')
                                                                    current_name = names.get('current', 'Current')
                                                                    rename_map = {match_col: 'Identifier', '_overall_old': baseline_name, '_overall_new': current_name, '_improve_': 'Improvement', 'Rank': 'Rank'}
                                                                    top_df = top_df.rename(columns=rename_map)
                                                                    for nc in [baseline_name, current_name, 'Improvement']:
                                                                        if nc in top_df.columns:
                                                                            top_df[nc] = top_df[nc].apply(lambda x: round(float(x),2) if pd.notna(x) else None)

                                                                    # Most Improved exports prepared (no on-screen top-N controls per user request)

                                                                    # Most Improved downloads removed per user request
                                
                                else:
                                    st.warning("Could not calculate statistics for the streams.")
                            # If Most Improved was previously computed and stored in session, render its UI here
                            mi_key = f'mi_merged_{exam_id}'
                            mi_flag = st.session_state.get(f'mi_computed_{exam_id}', False)
                            if mi_flag and mi_key in st.session_state:
                                try:
                                    merged_st = st.session_state.get(mi_key)
                                    if merged_st is not None and not merged_st.empty:
                                        # Inform the user briefly that results exist
                                        try:
                                            st.caption(f"Most Improved results available: {len(merged_st)} matched students.")
                                        except Exception:
                                            pass

                                        # Safely infer the identifier column name from the merged frame
                                        id_candidates = [c for c in merged_st.columns if c not in ['_overall_old', '_overall_new', '_improve_', 'Rank']]
                                        id_col = id_candidates[0] if id_candidates else merged_st.columns[0]

                                        # Build a clean display DataFrame (top 10 by improvement by default)
                                        display_cols = [id_col, '_overall_old', '_overall_new', '_improve_', 'Rank']
                                        safe_cols = [c for c in display_cols if c in merged_st.columns]
                                        max_k = len(merged_st)
                                        top_k = min(10, max_k) if max_k > 0 else max_k
                                        top_df = merged_st.loc[:, safe_cols].copy()

                                        # Rename columns to user-friendly names using persisted exam names (if available)
                                        names = st.session_state.get(f'mi_merged_names_{exam_id}', {})
                                        baseline_name = names.get('baseline', 'Baseline')
                                        current_name = names.get('current', 'Current')
                                        rename_map = {id_col: 'Identifier', '_overall_old': baseline_name, '_overall_new': current_name, '_improve_': 'Improvement', 'Rank': 'Rank'}
                                        top_df = top_df.rename(columns=rename_map)

                                        # Round numeric columns for neat display
                                        for nc in [baseline_name, current_name, 'Improvement']:
                                            if nc in top_df.columns:
                                                top_df[nc] = top_df[nc].apply(lambda x: round(float(x),2) if pd.notna(x) else None)

                                        # Sort by Improvement desc, then Rank asc
                                        sort_cols = []
                                        if 'Improvement' in top_df.columns:
                                            sort_cols.append('Improvement')
                                        if 'Rank' in top_df.columns:
                                            sort_cols.append('Rank')
                                        if sort_cols:
                                            ascending = [False if c == 'Improvement' else True for c in sort_cols]
                                            try:
                                                top_df = top_df.sort_values(by=sort_cols, ascending=ascending)
                                            except Exception:
                                                pass

                                        # Allow the user to choose how many top students to view and download
                                        max_k = len(merged_st)
                                        default_k = min(10, max_k) if max_k > 0 else 1
                                        top_k_key = f"mi_topk_{exam_id}"
                                        try:
                                            top_k = st.number_input("Top N Most Improved to show", min_value=1, max_value=max_k if max_k>0 else 1, value=default_k, step=1, key=top_k_key)
                                        except Exception:
                                            top_k = default_k

                                        # Rebuild display frame for the chosen top_k
                                        try:
                                            display_df = top_df.copy()
                                            # Use the requested top_k
                                            display_k = int(top_k) if top_k is not None else default_k
                                            display_slice = display_df.head(display_k).reset_index(drop=True)

                                            with st.expander(f"Most Improved — Top {display_k}", expanded=True):
                                                if len(display_slice) > 0:
                                                    st.dataframe(display_slice, use_container_width=True, height=400)
                                                    # PDF download for the Most Improved top-N (immediately below the table)
                                                    try:
                                                        # Include year and exam kind in the title where possible
                                                        try:
                                                            exam_year = selected_exam_obj.get('year') if selected_exam_obj else None
                                                        except Exception:
                                                            exam_year = None
                                                        try:
                                                            exam_kind = _exam_kind_from_label(selected_exam_name)
                                                        except Exception:
                                                            exam_kind = ''
                                                        title_mi = (
                                                            f"Most Improved — Top {display_k} students for {selected_exam_name}"
                                                            f" — Year: {exam_year if exam_year is not None else 'N/A'} — Kind: {exam_kind}"
                                                            f" — Baseline: {baseline_name} — Current: {current_name}"
                                                            f" — Showing: Identifier, {baseline_name}, {current_name}, Improvement"
                                                        )
                                                        pdf_buf = generate_pdf_most_improved(title_mi, display_slice)
                                                        pdf_bytes = pdf_buf.getvalue() if hasattr(pdf_buf, 'getvalue') else pdf_buf
                                                        st.download_button(label=f"📄 Download Most Improved PDF (Top {display_k})", data=pdf_bytes, file_name=f"{selected_exam_name.replace(' ','_')}_most_improved_top{display_k}.pdf", mime='application/pdf', key=f"download_mi_pdf_{exam_id}")
                                                    except Exception as e:
                                                        st.error(f"Failed to generate Most Improved PDF: {e}")
                                                else:
                                                    st.info("No matched students to display.")
                                        except Exception:
                                            # Fallback display
                                            try:
                                                st.table(top_df.head(int(top_k)).reset_index(drop=True))
                                            except Exception:
                                                pass
                                except Exception:
                                    pass
                    else:
                        st.error("No data found for this exam.")
    
    else:
        # Multi-exam comparison (existing code)
        st.markdown("#### Select Exams to Compare")

        # Provide Year / Term / Exam Kind filters similar to Single Exam flow
        all_meta = st.session_state.get('saved_exams', [])
        years = sorted({str(m.get('year')) for m in all_meta if m.get('year')})
        raw_terms = sorted({str(m.get('term')).strip() for m in all_meta if m.get('term')})
        kinds = sorted({_exam_kind_from_label(m.get('exam_name') or '') for m in all_meta if m.get('exam_name')})

        def _normalize_term_label_local(t):
            if not t:
                return ''
            s = str(t).strip().lower()
            s_n = re.sub(r'[^a-z0-9\s-]', '', s)
            if 'end' in s_n and 'term' in s_n:
                return 'End Term'
            if re.search(r'(?:term[\s\-]*1|term1|term[\s\-]*one|\bfirst\b|\bone\b|\b1\b)', s_n):
                return 'Term 1'
            if re.search(r'(?:term[\s\-]*2|term2|term[\s\-]*two|\bsecond\b|\btwo\b|\b2\b)', s_n):
                return 'Term 2'
            if re.search(r'(?:term[\s\-]*3|term3|term[\s\-]*three|\bthird\b|\bthree\b|\b3\b)', s_n):
                return 'Term 3'
            return str(t).strip()

        norm_terms = sorted({_normalize_term_label_local(t) for t in raw_terms if t})

        col_y, col_t, col_k = st.columns([1,1,2])
        with col_y:
            year_choice = st.selectbox('Year', options=['All'] + years, index=0)
        with col_t:
            term_choice = st.selectbox('Term', options=['All'] + norm_terms, index=0)
        with col_k:
            kind_choice = st.selectbox('Exam Kind', options=['All'] + kinds, index=0)

        def _matches_filters(meta):
            if year_choice != 'All' and str(meta.get('year')) != str(year_choice):
                return False
            if term_choice != 'All':
                if _normalize_term_label_local(meta.get('term')) != term_choice:
                    return False
            if kind_choice != 'All' and _exam_kind_from_label(meta.get('exam_name')) != kind_choice:
                return False
            return True

        filtered = [m for m in all_meta if _matches_filters(m)]
        exam_names = [m.get('exam_name', f"Exam") for m in filtered]

        selected_exams = st.multiselect(
            "Choose exams:",
            options=exam_names,
            default=exam_names[:2] if len(exam_names) >= 2 else exam_names
        )
        
        if len(selected_exams) >= 2:
            st.info(f"📊 Comparing {len(selected_exams)} exams")
            
            # Get exam data for selected exams
            selected_exam_objects = [e for e in st.session_state.saved_exams if e.get('exam_name') in selected_exams]
            
            # Performance Comparison
            st.markdown('<div class="section-header">Performance Comparison</div>', unsafe_allow_html=True)
            
            # Create comparison metrics
            col1, col2, col3 = st.columns(3)
            
            comparison_data = []
            for exam_obj in selected_exam_objects:
                exam_id = exam_obj.get('exam_id')
                exam_name = exam_obj.get('exam_name')
                exam_df = st.session_state.saved_exam_data.get(exam_id)
                
                if isinstance(exam_df, pd.DataFrame) and 'Total' in exam_df.columns:
                    # Calculate average total (excluding summary rows) — use same logic as PDF
                    def compute_exam_total_mean_local(df):
                        try:
                            # try to find a name-like column to filter out aggregate rows
                            name_candidates = [c for c in df.columns if str(c).strip().lower() in ('name','adm no','admno','adm_no','student','student name')]
                            def is_aggregate_label_local(x):
                                try:
                                    s = str(x).strip().lower()
                                    if not s:
                                        return True
                                    if any(word in s for word in ['total', 'totals', 'mean', 'average', 'sum', 'summary']):
                                        return True
                                    return False
                                except Exception:
                                    return True

                            if name_candidates:
                                name_col_local = name_candidates[0]
                                mask = ~df[name_col_local].apply(is_aggregate_label_local)
                                totals = pd.to_numeric(df.loc[mask, 'Total'], errors='coerce')
                            else:
                                totals = pd.to_numeric(df['Total'], errors='coerce')
                            totals = totals.dropna()
                            avg_total = float(totals.mean()) if len(totals) > 0 else None
                            max_total = float(totals.max()) if len(totals) > 0 else None
                            min_total = float(totals.min()) if len(totals) > 0 else None
                            return avg_total, max_total, min_total
                        except Exception:
                            return None, None, None

                    avg_total, max_total, min_total = compute_exam_total_mean_local(exam_df)
                    
                    comparison_data.append({
                        'Exam': exam_name,
                        'Students': exam_obj.get('total_students', 0),
                        'Avg Total': round(avg_total, 1) if avg_total is not None else 0,
                        'Max Total': round(max_total, 1) if max_total is not None else 0,
                        'Min Total': round(min_total, 1) if min_total is not None else 0,
                        'Subjects': exam_obj.get('num_subjects', 0)
                    })
            
            if comparison_data:
                # Display metrics
                with col1:
                    st.markdown("#### Average Performance")
                    for data in comparison_data:
                        st.metric(
                            label=data['Exam'][:30] + '...' if len(data['Exam']) > 30 else data['Exam'],
                            value=f"{data['Avg Total']:.1f}",
                            delta=None
                        )
                
                with col2:
                    st.markdown("#### Top Performance")
                    for data in comparison_data:
                        st.metric(
                            label=data['Exam'][:30] + '...' if len(data['Exam']) > 30 else data['Exam'],
                            value=f"{data['Max Total']:.1f}",
                            delta=None
                        )
                
                with col3:
                    st.markdown("#### Student Count")
                    for data in comparison_data:
                        st.metric(
                            label=data['Exam'][:30] + '...' if len(data['Exam']) > 30 else data['Exam'],
                            value=data['Students'],
                            delta=None
                        )
                
                # Detailed comparison table
                st.markdown("#### Detailed Comparison")
                comparison_df = pd.DataFrame(comparison_data)
                st.dataframe(comparison_df, use_container_width=True, hide_index=True)

                # === Per-subject exam comparison (CSV / PDF) and per-stream comparison ===
                st.markdown('---')
                st.markdown('#### Compare Two Exams (per-subject means)')
                # Allow picking exactly two exams from the filtered selection
                if not exam_names:
                    st.info('No exams available to compare.')
                else:
                    # Prefer the exams the user already selected in the top multiselect (`selected_exams`)
                    exam_options = selected_exams if (isinstance(selected_exams, list) and len(selected_exams) > 0) else exam_names

                    # Determine defaults: if user picked 2+ exams in the main selector, default to those
                    default_a = None
                    default_b = None
                    if isinstance(selected_exams, list) and len(selected_exams) >= 2:
                        default_a = selected_exams[0]
                        default_b = selected_exams[1]
                    elif isinstance(selected_exams, list) and len(selected_exams) == 1:
                        default_a = selected_exams[0]

                    # Ensure defaults exist in exam_options
                    try:
                        idx_a = exam_options.index(default_a) if default_a in exam_options else 0
                    except Exception:
                        idx_a = 0
                    try:
                        idx_b = exam_options.index(default_b) if default_b in exam_options else (1 if len(exam_options) > 1 else 0)
                    except Exception:
                        idx_b = (1 if len(exam_options) > 1 else 0)

                    col_a, col_b = st.columns(2)
                    with col_a:
                        ea = st.selectbox('Exam A', options=exam_options, index=idx_a, key='multi_cmp_a')
                    with col_b:
                        eb = st.selectbox('Exam B', options=exam_options, index=idx_b, key='multi_cmp_b')

                    if ea and eb:
                        # load exam objects and dataframes
                        a_obj = next((e for e in st.session_state.saved_exams if e.get('exam_name') == ea), None)
                        b_obj = next((e for e in st.session_state.saved_exams if e.get('exam_name') == eb), None)
                        a_df = st.session_state.saved_exam_data.get(a_obj.get('exam_id')) if a_obj else None
                        b_df = st.session_state.saved_exam_data.get(b_obj.get('exam_id')) if b_obj else None

                        if not (isinstance(a_df, pd.DataFrame) and isinstance(b_df, pd.DataFrame)):
                            st.warning('One or both selected exams do not have processed data available.')
                        else:
                            # infer subject columns (shared or union)
                            exclude_cols = {'name', 'adm no', 'admno', 'adm_no', 'class', 'total', 'mean', 'rank', 'grade', 'points', 's/rank', 'mean grade'}
                            def infer_subjects(df):
                                subs = []
                                for c in df.columns:
                                    lc = str(c).lower()
                                    if lc in exclude_cols:
                                        continue
                                    # detect numeric-like entries
                                    sample = df[c].head(200)
                                    found = False
                                    for v in sample:
                                        if convert_score_to_numeric(v) is not None:
                                            found = True
                                            break
                                    if found:
                                        subs.append(c)
                                return subs

                            subs_a = infer_subjects(a_df)
                            subs_b = infer_subjects(b_df)
                            raw_subjects = sorted(list(set(subs_a) | set(subs_b)))

                            # Build canonical mapping so variants like 'KISW', 'KISW_Combined%',
                            # 'KISWA' are treated as the same subject. We'll strip common
                            # suffixes and non-letter characters to form a canonical key.
                            import re
                            def canonical_key(s):
                                if s is None:
                                    return ''
                                t = str(s).lower()
                                # remove the word 'combined' and percent signs, underscores and non-letters
                                t = re.sub(r'combined', '', t)
                                t = re.sub(r'[%_\W]+', '', t)
                                return t

                            canonical_map = {}
                            for subj in raw_subjects:
                                key = canonical_key(subj)
                                if not key:
                                    continue
                                canonical_map.setdefault(key, []).append(subj)

                            # Exclude keys that are clearly not subjects (like 'srank', 'rank')
                            bad_keys = {'', 'rank', 'srank', 'points', 'grade', 'meangrade', 'mean'}
                            for bk in list(canonical_map.keys()):
                                if bk in bad_keys:
                                    canonical_map.pop(bk, None)

                            # Display subjects as the uppercase canonical key (or prettified)
                            display_subjects = [k.upper() for k in canonical_map.keys()]
                            display_subjects = sorted(display_subjects)

                            if not display_subjects:
                                st.info('No subject columns detected in the selected exams.')
                            else:
                                # Stream selector for per-stream comparison
                                # Build stream list but exclude pure-numeric streams; keep streams with letters like '9G','7D'
                                raw_streams = set()
                                if 'Class' in a_df.columns:
                                    raw_streams.update([str(x).strip() for x in a_df['Class'].dropna().unique()])
                                if 'Class' in b_df.columns:
                                    raw_streams.update([str(x).strip() for x in b_df['Class'].dropna().unique()])
                                all_streams = sorted([s for s in raw_streams if any(c.isalpha() for c in s)])
                                stream_choice = st.selectbox('Compare Stream (choose All (average) for overall):', options=['All (average)'] + all_streams, index=0, key='multi_cmp_stream')

                                def compute_grouped_means(df, stream=None):
                                    # Compute means for each canonical subject group represented
                                    # by multiple original columns in canonical_map.
                                    res = {}
                                    if df is None:
                                        return {ds: None for ds in display_subjects}
                                    # helper to get numeric values from a list of columns for a subset
                                    def gather_vals(subset, cols):
                                        vals = []
                                        for c in cols:
                                            if c in subset.columns:
                                                vals.extend(subset[c].apply(convert_score_to_numeric).dropna().tolist())
                                        return vals

                                    if stream is None or str(stream).lower().startswith('all'):
                                        if 'Class' not in df.columns:
                                            # fallback: compute simple column means across all students
                                            for key, cols in canonical_map.items():
                                                all_vals = gather_vals(df, cols)
                                                res[key.upper()] = float(pd.Series(all_vals).mean()) if len(all_vals) > 0 else None
                                            return res

                                        raw_streams_local = [str(x).strip() for x in df['Class'].dropna().unique()]
                                        letter_streams_local = [ss for ss in raw_streams_local if any(c.isalpha() for c in ss)]
                                        for key, cols in canonical_map.items():
                                            per_stream_means = []
                                            for stc in letter_streams_local:
                                                subset = df[df['Class'].astype(str) == stc]
                                                vals = gather_vals(subset, cols)
                                                if len(vals) > 0:
                                                    per_stream_means.append(float(pd.Series(vals).mean()))
                                            res[key.upper()] = float(pd.Series(per_stream_means).mean()) if len(per_stream_means) > 0 else None
                                        return res
                                    else:
                                        # specific stream: gather values across all grouped columns for that stream
                                        if 'Class' not in df.columns:
                                            return {ds: None for ds in display_subjects}
                                        subset = df[df['Class'].astype(str) == str(stream)]
                                        for key, cols in canonical_map.items():
                                            vals = gather_vals(subset, cols)
                                            res[key.upper()] = float(pd.Series(vals).mean()) if len(vals) > 0 else None
                                        return res

                                # Compute grouped means for the selected stream (or overall)
                                if str(stream_choice).lower().startswith('all'):
                                    a_means = compute_grouped_means(a_df, None)
                                    b_means = compute_grouped_means(b_df, None)
                                else:
                                    a_means = compute_grouped_means(a_df, stream_choice)
                                    b_means = compute_grouped_means(b_df, stream_choice)

                                # Use exam kind labels for column headers (e.g., 'End Term', 'Mid Term')
                                a_label = _exam_kind_from_label(a_obj.get('exam_name')) if a_obj else 'Exam A'
                                b_label = _exam_kind_from_label(b_obj.get('exam_name')) if b_obj else 'Exam B'

                                rows = []
                                for s in display_subjects:
                                    va = a_means.get(s)
                                    vb = b_means.get(s)
                                    diff = (vb - va) if (va is not None and vb is not None) else None
                                    rows.append({'Subject': s, a_label: va, b_label: vb, 'Difference': diff})

                                comp_df = pd.DataFrame(rows).set_index('Subject')

                                # compute averages (mean of subject means) using the exam-kind labeled columns
                                try:
                                    avg_a = comp_df[a_label].dropna().mean()
                                    avg_b = comp_df[b_label].dropna().mean()
                                except Exception:
                                    avg_a = avg_b = None

                                avg_row = {c: '-' for c in comp_df.columns}
                                avg_row[a_label] = avg_a if avg_a is not None else None
                                avg_row[b_label] = avg_b if avg_b is not None else None
                                avg_row['Difference'] = (avg_b - avg_a) if (avg_a is not None and avg_b is not None) else None

                                # Rank row: higher average -> rank 1
                                ranks = {}
                                try:
                                    if avg_a is None and avg_b is None:
                                        ranks[a_label] = ranks[b_label] = '-'
                                    else:
                                        if (avg_a is None):
                                            ranks[a_label] = '-'
                                        if (avg_b is None):
                                            ranks[b_label] = '-'
                                        if avg_a is not None and avg_b is not None:
                                            if avg_a > avg_b:
                                                ranks[a_label], ranks[b_label] = 1, 2
                                            elif avg_b > avg_a:
                                                ranks[a_label], ranks[b_label] = 2, 1
                                            else:
                                                ranks[a_label], ranks[b_label] = 1, 1
                                except Exception:
                                    ranks[a_label] = ranks[b_label] = '-'

                                # Show display with formatted numbers (2 decimals)
                                display_df = comp_df.copy()
                                # Coerce comparison columns to numeric and round to 2 decimals so missing values
                                # become NaN (displayed as blank) rather than the string 'None'. This mirrors
                                # how the Subject × Stream sheet displays averages.
                                for col in [a_label, b_label]:
                                    if col in display_df.columns:
                                        display_df[col] = pd.to_numeric(display_df[col], errors='coerce').round(2)
                                display_df['Difference'] = pd.to_numeric(display_df['Difference'], errors='coerce').round(2)

                                with st.expander('Subject-wise Comparison (preview)', expanded=True):
                                    st.dataframe(display_df, use_container_width=True, height=400)

                                # CSV download
                                try:
                                    export_df = display_df.reset_index()
                                    export_df.rename(columns={'index':'Subject'}, inplace=True)
                                    csv_bytes = export_df.to_csv(index=False).encode('utf-8')
                                    st.download_button('Download comparison (CSV)', data=csv_bytes, file_name=f'{ea.replace(" ","_")}_vs_{eb.replace(" ","_")}_comparison.csv', mime='text/csv')
                                except Exception:
                                    pass

                                # PDF download: include averages and rank row at the bottom and a descriptive title
                                try:
                                    pdf_df = display_df.reset_index().rename(columns={'index':'Subject'})

                                    # compute averages for PDF using the exam Total mean from the marksheet
                                    def compute_exam_total_mean(df):
                                        try:
                                            if df is None or 'Total' not in df.columns:
                                                return None
                                            # try to find a name-like column to filter out aggregate rows
                                            name_candidates = [c for c in df.columns if str(c).strip().lower() in ('name','adm no','admno','adm_no','student','student name')]
                                            def is_aggregate_label_local(x):
                                                try:
                                                    s = str(x).strip().lower()
                                                    if not s:
                                                        return True
                                                    if any(word in s for word in ['total', 'totals', 'mean', 'average', 'sum', 'summary']):
                                                        return True
                                                    return False
                                                except Exception:
                                                    return True

                                            if name_candidates:
                                                name_col_local = name_candidates[0]
                                                mask = ~df[name_col_local].apply(is_aggregate_label_local)
                                                totals = pd.to_numeric(df.loc[mask, 'Total'], errors='coerce').dropna()
                                            else:
                                                totals = pd.to_numeric(df['Total'], errors='coerce').dropna()
                                            return float(totals.mean()) if len(totals) > 0 else None
                                        except Exception:
                                            return None

                                    avg_a = compute_exam_total_mean(a_df)
                                    avg_b = compute_exam_total_mean(b_df)

                                    avg_row_pdf = {'Subject': 'Average'}
                                    avg_row_pdf[a_label] = round(float(avg_a), 2) if avg_a is not None else None
                                    avg_row_pdf[b_label] = round(float(avg_b), 2) if avg_b is not None else None
                                    avg_row_pdf['Difference'] = round(float(avg_b - avg_a), 2) if (avg_a is not None and avg_b is not None) else None

                                    # ranking: 1 = best (higher average)
                                    try:
                                        if avg_a is None and avg_b is None:
                                            rank_a = rank_b = None
                                        else:
                                            if avg_a is None:
                                                rank_a = None
                                            if avg_b is None:
                                                rank_b = None
                                            if avg_a is not None and avg_b is not None:
                                                if avg_a > avg_b:
                                                    rank_a, rank_b = 1, 2
                                                elif avg_b > avg_a:
                                                    rank_a, rank_b = 2, 1
                                                else:
                                                    rank_a = rank_b = 1
                                    except Exception:
                                        rank_a = rank_b = None

                                    # Append only the Average row to the PDF dataframe (remove Rank row as requested)
                                    pdf_rows = pdf_df.to_dict(orient='records')
                                    pdf_rows.append(avg_row_pdf)
                                    pdf_out_df = pd.DataFrame(pdf_rows)

                                    # Build title with year, term, grade and exams being compared
                                    try:
                                        a_year = str(a_obj.get('date_saved', '')).split('-')[0] if a_obj else ''
                                    except Exception:
                                        a_year = ''
                                    # Prefer explicit term metadata (normalized); fallback to exam kind extraction
                                    try:
                                        a_term = _normalize_term_label_local(a_obj.get('term')) if a_obj and a_obj.get('term') else _exam_kind_from_label(a_obj.get('exam_name'))
                                    except Exception:
                                        a_term = _exam_kind_from_label(a_obj.get('exam_name')) if a_obj else a_label
                                    try:
                                        b_term = _normalize_term_label_local(b_obj.get('term')) if b_obj and b_obj.get('term') else _exam_kind_from_label(b_obj.get('exam_name'))
                                    except Exception:
                                        b_term = _exam_kind_from_label(b_obj.get('exam_name')) if b_obj else b_label
                                    a_grade = a_obj.get('class_name', '') if a_obj else ''
                                    title = (
                                        f"Subject Comparison — {a_label} vs {b_label} — Year {a_year} — Term {a_term} "
                                        f"— Grade {a_grade} — Showing: Subject, {a_label} mean, {b_label} mean, Difference"
                                    )
                                    # If a specific stream was selected, append the stream name to the title
                                    try:
                                        if 'stream_choice' in locals() and not str(stream_choice).lower().startswith('all'):
                                            title = f"{title} — Stream {stream_choice}"
                                    except Exception:
                                        pass

                                    pdf_buf = generate_pdf_most_improved(title, pdf_out_df)
                                    st.download_button(label=f'📄 Download Comparison PDF ({a_label} vs {b_label})', data=pdf_buf, file_name=f'{a_label.replace(" ","_")}_vs_{b_label.replace(" ","_")}_comparison.pdf', mime='application/pdf')
                                except Exception as e:
                                    st.error(f'Failed to prepare comparison PDF: {e}')
                
                # Performance trend analysis
                if len(comparison_data) >= 2:
                    st.markdown("#### Performance Trend")
                    avg_changes = []
                    for i in range(1, len(comparison_data)):
                        prev_avg = comparison_data[i-1]['Avg Total']
                        curr_avg = comparison_data[i]['Avg Total']
                        change = curr_avg - prev_avg
                        change_pct = (change / prev_avg * 100) if prev_avg > 0 else 0
                        
                        if change > 0:
                            trend_emoji = "📈"
                            trend_color = "green"
                        elif change < 0:
                            trend_emoji = "📉"
                            trend_color = "red"
                        else:
                            trend_emoji = "➡️"
                            trend_color = "gray"
                        
                        st.markdown(f"""
                        <div style='padding: 0.5rem; margin: 0.5rem 0; border-left: 4px solid {trend_color}; background: #f8f9fa;'>
                            {trend_emoji} <strong>{comparison_data[i-1]['Exam']}</strong> → <strong>{comparison_data[i]['Exam']}</strong>: 
                            <span style='color: {trend_color}; font-weight: bold;'>{change:+.1f} points ({change_pct:+.1f}%)</span>
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.warning("No valid data found for selected exams.")
        
        elif len(selected_exams) == 1:
            st.warning("Please select at least 2 exams to compare.")
    
    # Class Rankings feature
    st.markdown('<div class="section-header">Class Rankings</div>', unsafe_allow_html=True)
    st.write("Rank classes by subject means and totals for selected exam kinds, or by average across chosen exams.")

    # Helper: find a reasonable class column in a dataframe
    def _find_class_col(df):
        candidates = ['Class', 'class', 'class_name', 'Class Name', 'class name', 'ClassName']
        for c in candidates:
            if c in df.columns:
                return c
        for c in df.columns:
            if 'class' in str(c).lower():
                return c
        return None

    def _is_valid_stream(val):
        """Return True if val looks like a stream code (contains letters), and is not purely numeric."""
        try:
            if val is None:
                return False
            s = str(val).strip()
            if s == '':
                return False
            # reject pure numbers like '534' or '5.00'
            if re.fullmatch(r"\d+(?:\.\d+)?", s):
                return False
            # require at least one letter (A-Z)
            if re.search(r"[A-Za-z]", s):
                return True
            return False
        except Exception:
            return False

    def _compute_class_means(df, class_col, subject_cols):
        # Ensure numeric conversion
        src = df.copy()
        for c in subject_cols:
            if c in src.columns:
                src[c] = pd.to_numeric(src[c], errors='coerce')
        grp = src.groupby(class_col)
        means = grp[subject_cols].mean()
        counts = grp.size().rename('N')
        out = means.reset_index().merge(counts.reset_index(), on=class_col)
        return out

    def _add_serial_column(df, col_name='No'):
        """Return a new DataFrame with a serial column inserted at position 0 labelled col_name (1..N)."""
        try:
            out = df.copy()
            out = out.reset_index(drop=True)
            out.insert(0, col_name, range(1, len(out) + 1))
            return out
        except Exception:
            return df

    # UI: choose exams to base rankings on
    all_meta = load_all_metadata()
    exam_items = []
    exam_map = {}
    for eid, meta in all_meta.items():
        label = f"{meta.get('date_saved','')[:10]} — {meta.get('exam_name','')} — {meta.get('class_name','') or meta.get('grade','') }"
        exam_items.append(label)
        exam_map[label] = eid

    # Cleanup helper: remove numeric-only stream values from saved exams (permanent)
    def _clean_streams_in_exam(exam_id):
        """Aggressively scan saved exam data and raw data for columns that look like they contain stream codes
        and permanently remove numeric-only entries (set to None) where mixed values exist or where the column
        name suggests it is a stream. Returns number of cells changed.
        """
        try:
            data, raw_data, cfg = load_exam_from_disk(exam_id)
            if data is None and raw_data is None:
                return 0
            removed = 0

            for df_name, df in (('data', data), ('raw', raw_data)):
                if df is None:
                    continue

                # Consider candidate columns: any column whose name suggests stream/class OR any column that contains
                # a mixture of letter-containing and numeric-only values.
                candidates = []
                for c in df.columns:
                    colname = str(c).strip().lower()
                    # name-based heuristic
                    if any(k in colname for k in ('stream', 'streamcode', 'stream_code', 'stream code')) or 'str' == colname:
                        candidates.append(c)
                        continue
                    # value-based heuristic: check sample of non-null values
                    vals = df[c].dropna().astype(str).str.strip()
                    if len(vals) == 0:
                        continue
                    # counts
                    letter_count = vals.apply(lambda v: bool(re.search(r'[A-Za-z]', v))).sum()
                    numeric_only_count = vals.apply(lambda v: bool(re.fullmatch(r"\d+(?:\.\d+)?", v))).sum()
                    # if column has both types present, it's a good candidate
                    if letter_count > 0 and numeric_only_count > 0:
                        candidates.append(c)

                # For each candidate column, remove numeric-only entries
                for sc in candidates:
                    try:
                        mask_numeric = df[sc].notna() & df[sc].astype(str).str.strip().apply(lambda v: bool(re.fullmatch(r"\d+(?:\.\d+)?", v)))
                        # Only remove numeric-only entries when there exists at least one letter-containing value in the column
                        if mask_numeric.any():
                            # verify presence of letter-containing values
                            has_letter = df[sc].dropna().astype(str).str.strip().apply(lambda v: bool(re.search(r'[A-Za-z]', v))).any()
                            if has_letter:
                                count = int(mask_numeric.sum())
                                df.loc[mask_numeric, sc] = None
                                removed += count
                    except Exception:
                        continue

            # persist back to disk if we changed anything
            if removed > 0:
                meta = all_meta.get(exam_id, {})
                save_exam_to_disk(exam_id, meta, data if data is not None else pd.DataFrame(), raw_data if raw_data is not None else pd.DataFrame(), cfg if cfg is not None else {})
                # update session cache
                try:
                    st.session_state.saved_exam_data[exam_id] = data
                except Exception:
                    pass
                try:
                    st.session_state.saved_exam_raw_data[exam_id] = raw_data
                except Exception:
                    pass
            return removed
        except Exception:
            return 0

    if exam_items:
        # Background cleaner: remove the maintenance UI and run the cleaner in the background once per session.
        # The cleaner will create a backup, scan saved exams and remove numeric-only stream values where mixed values exist.
        if 'background_stream_cleaner_started' not in st.session_state:
            st.session_state['background_stream_cleaner_started'] = True

            def _background_clean_all():
                try:
                    # create a backup before making any permanent changes
                    bpath = create_backup_saved_exams()
                    total_removed = 0
                    for eid in list(all_meta.keys()):
                        try:
                            removed = _clean_streams_in_exam(eid)
                            if removed:
                                total_removed += int(removed)
                        except Exception:
                            continue
                    # write a small summary file with results for auditing
                    try:
                        summary = {'timestamp': datetime.now().isoformat(), 'backup_path': bpath, 'total_removed': total_removed}
                        try:
                            # write summary via storage adapter when available
                            try:
                                from modules import storage
                            except Exception:
                                storage = None
                            if storage is not None:
                                storage.write_json('saved_exams_clean_summary.json', summary)
                            else:
                                out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'saved_exams_clean_summary.json')
                                with open(out_path, 'w', encoding='utf-8') as sf:
                                    json.dump(summary, sf, indent=2, ensure_ascii=False)
                        except Exception:
                            pass
                    except Exception:
                        pass
                except Exception:
                    pass

            t = threading.Thread(target=_background_clean_all, daemon=True)
            t.start()
        # Let the user filter exams by Year, Term and Exam Kind (explicit selection)
        years = sorted({str(m.get('date_saved',''))[:4] for m in all_meta.values() if m.get('date_saved')})
        years = [y for y in years if y and y != 'None']
        selected_year = st.selectbox('Select Year', options=years, index=0 if years else None, key='class_rank_year')

        # Gather normalized term labels from metadata
        term_set = set()
        kind_set = set()
        for meta in all_meta.values():
            try:
                t = meta.get('term')
                if t:
                    tn = _normalize_term_label_local(t)
                else:
                    tn = _exam_kind_from_label(meta.get('exam_name'))
            except Exception:
                tn = _exam_kind_from_label(meta.get('exam_name'))
            if tn:
                term_set.add(tn)
            # exam kind canonical
            try:
                k = _exam_kind_from_label(meta.get('exam_name'))
                if k:
                    kind_set.add(k)
            except Exception:
                pass

        term_list = sorted(list(term_set))
        kind_list = sorted(list(kind_set))

        selected_term = st.selectbox('Select Term', options=term_list, index=0 if term_list else None, key='class_rank_term')
        # Allow selecting one or two exam kinds to include
        selected_kinds = st.multiselect('Select Exam Kind(s) (choose up to 2)', options=kind_list, default=[kind_list[0]] if kind_list else [], key='class_rank_kinds')

        # Find exams matching the selected Year, Term and Kind
        sel_labels = []
        for label in exam_items:
            eid = exam_map.get(label)
            meta = all_meta.get(eid, {})
            # year
            my = str(meta.get('date_saved',''))[:4]
            try:
                mterm = _normalize_term_label_local(meta.get('term')) if meta.get('term') else _exam_kind_from_label(meta.get('exam_name'))
            except Exception:
                mterm = _exam_kind_from_label(meta.get('exam_name'))
            mkind = _exam_kind_from_label(meta.get('exam_name'))
            # match year, term and any of the selected kinds
            try:
                kind_match = (mkind in selected_kinds) if selected_kinds else False
            except Exception:
                kind_match = False
            if my == selected_year and mterm == selected_term and kind_match:
                sel_labels.append(label)

        selected_ids = [exam_map[l] for l in sel_labels]

        if selected_ids:
            # Option: group by grade only (ignore streams / section suffixes)
            group_by_grade = st.checkbox('Group by Grade only (ignore streams)', value=False, key='class_rank_group_by_grade')

            # Determine union of subject columns across selected exams
            subj_union = set()
            exam_dfs = {}
            for eid in selected_ids:
                df_e = None
                try:
                    df_e = st.session_state.get('saved_exam_data', {}).get(eid)
                except Exception:
                    df_e = None
                if df_e is None:
                    try:
                        df_e, _, _ = load_exam_from_disk(eid)
                    except Exception:
                        df_e = None
                if df_e is None:
                    continue
                exam_dfs[eid] = df_e
                # pick subject-like columns (exclude name/class/adm/total/rank)
                exclude = {'name','adm no','admno','adm_no','class','total','mean','rank','grade','points','s/rank','mean grade'}
                for c in df_e.columns:
                    if isinstance(c, str) and c.strip():
                        key = c.strip().lower()
                        if key not in exclude and len(key) > 1 and not any(x in key for x in ['date','id','adm']):
                            subj_union.add(c)

            subj_list = sorted(list(subj_union))
            # Allow ranking by one or more columns (composite = mean of selected columns)
            basis_list = st.multiselect('Rank by (choose one or more columns)', options=['Total'] + subj_list, default=['Total'], key='class_rank_basis')

            # Automatically compute class rankings for the selected Year/Term/Kind(s)
            results = {}
            # For each selected exam compute class means
            for eid, df_e in exam_dfs.items():
                # Determine the original class/stream column name (may return None)
                guessed = _find_class_col(df_e)
                orig_class_col = guessed or 'Class'

                # Ensure we operate on a local copy so we can add fallback columns if needed
                df_e = df_e.copy()

                # Resolve to an actual existing column name in the dataframe. If the guessed
                # name is not present, try common alternatives (stream, form, class, arm).
                actual_class_col = None
                common_names = ['class', 'stream', 'form', 'stream/class', 'class/stream', 'arm', 'arm_code']
                # prefer the guessed name if it exists
                if orig_class_col in df_e.columns:
                    actual_class_col = orig_class_col
                else:
                    # search for common alternatives (case-insensitive)
                    for c in df_e.columns:
                        if isinstance(c, str) and str(c).lower().strip() in common_names:
                            actual_class_col = c
                            break

                # If still not found, create a fallback 'Class' column with a single group so
                # downstream grouping logic can run without KeyError.
                if actual_class_col is None:
                    df_e['Class'] = 'All'
                    actual_class_col = 'Class'

                # create a working copy for grouping if grouping by grade
                df_work = df_e.copy()
                # class_col is the resolved column present in the working df
                class_col = actual_class_col
                orig_class_col = actual_class_col
                if group_by_grade:
                    # derive a Group label from the class name: prefer numeric grade, else normalize other labels
                    def _derive_group_label(s):
                        try:
                            if pd.isna(s):
                                return None
                            stxt = str(s).strip()
                            s_low = stxt.lower()
                            # direct patterns: Grade N, Form N
                            m = re.search(r'grade\s*-?\s*(\d+)', s_low)
                            if m:
                                return f"Grade {m.group(1)}"
                            m = re.search(r'form\s*-?\s*(\d+)', s_low)
                            if m:
                                return f"Form {m.group(1)}"
                            # PP (pre-primary) patterns: pp1, pp2, pp 1
                            m = re.search(r'\bpp\s*-?\s*(\d+)\b', s_low)
                            if m:
                                return f"PP{m.group(1)}"
                            if re.search(r'play', s_low):
                                return 'Playgroup'

                            # If string ends with a stream suffix like '6C' or 'PP1A', try stripping trailing letters
                            m2 = re.match(r'^(.*?)([A-Za-z]{1,2})$', stxt)
                            if m2:
                                left = m2.group(1).strip()
                                # only strip if left part contains digits or known tokens
                                if re.search(r'\d', left) or re.search(r'\bpp\b', left.lower()) or re.search(r'\bform\b', left.lower()):
                                    stxt = left
                                    s_low = stxt.lower()
                                    m = re.search(r'grade\s*-?\s*(\d+)', s_low)
                                    if m:
                                        return f"Grade {m.group(1)}"
                                    m = re.search(r'form\s*-?\s*(\d+)', s_low)
                                    if m:
                                        return f"Form {m.group(1)}"
                                    m = re.search(r'\bpp\s*-?\s*(\d+)\b', s_low)
                                    if m:
                                        return f"PP{m.group(1)}"
                                    if re.search(r'play', s_low):
                                        return 'Playgroup'
                                    return stxt.title()

                            # fallback: title-case the original label
                            return stxt.title()
                        except Exception:
                            return str(s)

                    # Instead of pooling student rows (which weights by stream size),
                    # compute per-stream means first then average those stream means equally
                    # to produce an unweighted grade-level mean (one stream = one unit).
                    try:
                        # per-stream means from the original dataframe
                        per_stream = _compute_class_means(df_e, orig_class_col, subj_cols)
                        # derive group label for each stream
                        per_stream['Group'] = per_stream[orig_class_col].apply(_derive_group_label)
                        # now group by Group and take the simple mean of the per-stream means
                        grp_means = per_stream.groupby('Group')[subj_cols].mean().reset_index()
                        grp_means.rename(columns={'Group': 'Class'}, inplace=True)
                        means = grp_means
                        # mark that we've already computed means for this exam
                        # skip the later call to _compute_class_means
                        computed_means_here = True
                    except Exception:
                        # fallback to original approach if anything fails
                        df_work['Group'] = df_work[orig_class_col].apply(_derive_group_label)
                        class_col = 'Group'
                        computed_means_here = False

                cols = [c for c in df_work.columns if c not in [class_col] and c is not None]
                # form basis columns list from basis_list selection
                subj_cols = []
                for c in cols:
                    if c in subj_list or c.lower() == 'total':
                        subj_cols.append(c)
                # also ensure any explicitly selected basis columns are included
                for b in basis_list:
                    # only include explicitly selected basis columns if they exist in this exam dataframe
                    if b is not None and b in df_work.columns and b not in subj_cols:
                        subj_cols.append(b)
                # ensure Total included
                if 'Total' in df_work.columns and 'Total' not in subj_cols:
                    subj_cols.append('Total')
                # if no subject/basis columns found for this exam, skip it
                if not subj_cols:
                    # nothing to compute for this exam
                    continue
                try:
                    if not ('computed_means_here' in locals() and computed_means_here):
                        means = _compute_class_means(df_work, class_col, subj_cols)
                        # normalize class column name to 'Class'
                        means.rename(columns={class_col: 'Class'}, inplace=True)
                    # drop blank/null classes
                    means = means[means['Class'].notna() & means['Class'].astype(str).str.strip().ne('')]
                    results[eid] = means
                except Exception as e:
                    st.error(f'Failed to compute class means for exam {eid}: {e}')

            if not results:
                st.warning('No valid exam data to compute rankings.')
            else:
                # Compute average across the selected exams (show this even when only one kind is selected)
                series_list = []
                for eid, mdf in results.items():
                    try:
                        m = mdf.set_index('Class')
                        # pick columns present in this exam from basis_list
                        cols_for_score = [b for b in basis_list if b in m.columns]
                        if cols_for_score:
                            score = m[cols_for_score].mean(axis=1, skipna=True)
                        elif 'Total' in m.columns:
                            score = m['Total']
                        else:
                            score = pd.Series(index=m.index, dtype='float64')
                    except Exception:
                        continue
                    series_list.append(score)

                if series_list:
                    # concat aligned by Class and average across exams
                    df_concat = pd.concat(series_list, axis=1)
                    df_avg_series = df_concat.mean(axis=1, skipna=True)
                    df_avg = df_avg_series.reset_index()
                    df_avg.columns = ['Class', 'Score']
                    # include non-numeric class labels and drop blanks
                    df_avg = df_avg[df_avg['Class'].notna() & df_avg['Class'].astype(str).str.strip().ne('')]
                    # sort by Score descending and prepare simple table (no Rank column)
                    try:
                        df_avg = df_avg.sort_values('Score', ascending=False).reset_index(drop=True)
                        df_simple = df_avg[['Class', 'Score']]
                    except Exception:
                        # fallback: keep whatever columns are available
                        try:
                            df_simple = df_avg[['Class', 'Score']]
                        except Exception:
                            df_simple = df_avg
                    st.subheader('Average Rankings across selected kinds')
                    # Allow the user to define Upper and Lower class groups for separate ranking
                    classes_all = sorted(df_simple['Class'].astype(str).unique()) if 'Class' in df_simple.columns else []
                    # Load persisted subgroup selections if available
                    try:
                        _cfg_tmp = load_persistent_config() or {}
                    except Exception:
                        _cfg_tmp = {}
                    default_upper = _cfg_tmp.get('class_rank_last_upper', []) if isinstance(_cfg_tmp, dict) else []
                    default_lower = _cfg_tmp.get('class_rank_last_lower', []) if isinstance(_cfg_tmp, dict) else []
                    # Ensure defaults are lists and only contain values present in options
                    try:
                        if not isinstance(default_upper, (list, tuple)):
                            default_upper = [default_upper] if default_upper is not None else []
                    except Exception:
                        default_upper = []
                    try:
                        if not isinstance(default_lower, (list, tuple)):
                            default_lower = [default_lower] if default_lower is not None else []
                    except Exception:
                        default_lower = []
                    try:
                        default_upper = [d for d in default_upper if d in classes_all]
                    except Exception:
                        default_upper = []
                    try:
                        default_lower = [d for d in default_lower if d in classes_all and d not in default_upper]
                    except Exception:
                        default_lower = []
                    upper_sel = st.multiselect('Select Upper classes (optional)', options=classes_all, default=default_upper, key='class_rank_upper_avg')
                    lower_sel = st.multiselect('Select Lower classes (optional)', options=classes_all, default=default_lower, key='class_rank_lower_avg')

                    if upper_sel or lower_sel:
                        # Ensure exclusivity: remove overlaps from lower if present in upper
                        upper_set = set(upper_sel)
                        lower_set = [c for c in lower_sel if c not in upper_set]

                        if upper_set:
                            df_upper = df_simple[df_simple['Class'].astype(str).isin(upper_set)].copy()
                            st.markdown('**Upper classes**')
                            # add serial numbers starting at 1 for this subgroup
                            df_up_disp = _add_serial_column(df_upper, col_name='No')
                            st.dataframe(df_up_disp, use_container_width=True)
                            try:
                                csvb_up = df_up_disp.to_csv(index=False).encode('utf-8')
                                st.download_button('Download Upper classes (CSV)', data=csvb_up, file_name='class_rankings_average_upper.csv', mime='text/csv')
                            except Exception:
                                pass
                            # PDF download for this subgroup (immediately below the table)
                            try:
                                title_up = (
                                    f"Class Rankings — Average score per class ({', '.join(selected_kinds)}) — Year {selected_year} "
                                    f"— Term {str(selected_term).title()} — Basis: {', '.join(basis_list)} "
                                    f"— Upper"
                                )
                                pdf_up = generate_pdf_most_improved(title_up, df_up_disp)
                                st.download_button('Download Upper classes (PDF)', data=pdf_up, file_name='class_rankings_average_upper.pdf', mime='application/pdf')
                            except Exception:
                                pass

                        # If either subgroup exists, offer a combined PDF that contains each subgroup as its own section
                        try:
                            sections = {}
                            if upper_set:
                                sections['Upper classes'] = _add_serial_column(df_upper, col_name='No')
                            if lower_set:
                                sections['Lower classes'] = _add_serial_column(df_lower, col_name='No')
                            if sections:
                                try:
                                    sections_list = ', '.join([str(s) for s in sections.keys()])
                                except Exception:
                                    sections_list = ''
                                try:
                                    sections_clean = ', '.join([s.replace(' classes','').replace(' Classes','').replace('classes','').strip() for s in sections.keys()])
                                except Exception:
                                    sections_clean = sections_list
                                title_pdf = (
                                    f"Class Rankings by Subgroup — Year {selected_year} — Term {str(selected_term).title()} "
                                    f"— Kinds: {', '.join(selected_kinds)} — Basis: {', '.join(basis_list)} "
                                    f"— {sections_clean}"
                                )
                                pdfb_sec = generate_pdf_most_improved(title_pdf, sections)
                                st.download_button('Download Upper/Lower class rankings (PDF)', data=pdfb_sec, file_name='class_rankings_average_upper_lower.pdf', mime='application/pdf')
                        except Exception:
                            pass

                        if lower_set:
                            df_lower = df_simple[df_simple['Class'].astype(str).isin(lower_set)].copy()
                            st.markdown('**Lower classes**')
                            df_lo_disp = _add_serial_column(df_lower, col_name='No')
                            st.dataframe(df_lo_disp, use_container_width=True)
                            try:
                                csvb_lo = df_lo_disp.to_csv(index=False).encode('utf-8')
                                st.download_button('Download Lower classes (CSV)', data=csvb_lo, file_name='class_rankings_average_lower.csv', mime='text/csv')
                            except Exception:
                                pass
                            # PDF download for this subgroup (immediately below the table)
                            try:
                                title_lo = (
                                    f"Class Rankings — Average score per class ({', '.join(selected_kinds)}) — Year {selected_year} "
                                    f"— Term {str(selected_term).title()} — Basis: {', '.join(basis_list)} "
                                    f"— Lower"
                                )
                                pdf_lo = generate_pdf_most_improved(title_lo, df_lo_disp)
                                st.download_button('Download Lower classes (PDF)', data=pdf_lo, file_name='class_rankings_average_lower.pdf', mime='application/pdf')
                            except Exception:
                                pass
                    else:
                        # add serial numbers for the main averaged table
                        df_display = _add_serial_column(df_simple, col_name='No')
                        st.dataframe(df_display, use_container_width=True)
                    try:
                                csvb = _add_serial_column(df_simple, col_name='No').to_csv(index=False).encode('utf-8')
                                st.download_button('Download class rankings (CSV)', data=csvb, file_name='class_rankings_average.csv', mime='text/csv')
                    except Exception:
                        pass
                    # Persist the user's subgroup choices so they survive app restarts
                    try:
                        cfgp = load_persistent_config() or {}
                        cfgp['class_rank_last_upper'] = upper_sel
                        cfgp['class_rank_last_lower'] = lower_sel
                        save_persistent_config(cfgp)
                    except Exception:
                        pass
                    try:
                        title = (
                            f"Class Rankings — Average score per class across selected kinds ({', '.join(selected_kinds)}) "
                            f"— Year {selected_year} — Term {str(selected_term).title()} — Basis: {', '.join(basis_list)}"
                        )
                        pdfb = generate_pdf_most_improved(title, _add_serial_column(df_simple, col_name='No'))
                        st.download_button('Download class rankings (PDF)', data=pdfb, file_name='class_rankings_average.pdf', mime='application/pdf')
                    except Exception:
                        pass
                else:
                    # per-exam rankings: build a single consolidated table containing Exam, Class, Score, Rank
                    combined_rows = []
                    for eid, mdf in results.items():
                        meta = all_meta.get(eid, {})
                        # Show only the exam name (omit the leading saved-date to keep labels compact)
                        exam_label = f"{meta.get('exam_name','')}"
                        df_r = mdf.copy()
                        # compute composite Score across selected basis_list for this exam
                        try:
                            cols_for_score = [b for b in basis_list if b in df_r.columns]
                            if cols_for_score:
                                score_ser = df_r[cols_for_score].mean(axis=1, skipna=True)
                            elif 'Total' in df_r.columns:
                                score_ser = df_r['Total']
                            else:
                                score_ser = pd.Series([pd.NA] * len(df_r), index=df_r.index)
                            df_r['Score'] = score_ser
                            # order rows by Score descending; do not create a Rank column (user requested simple serial ordering without a Rank column)
                            try:
                                df_r = df_r.sort_values('Score', ascending=False).reset_index(drop=True)
                            except Exception:
                                pass
                        except Exception:
                            df_r['Score'] = pd.Series([pd.NA] * len(df_r), index=df_r.index)
                            df_r['Rank'] = pd.Series([pd.NA] * len(df_r), index=df_r.index)

                        # Build simple table rows, skipping blank classes
                        for _, row in df_r.iterrows():
                            cls = row.get('Class')
                            if cls is None or (isinstance(cls, str) and cls.strip() == ''):
                                continue
                            row_dict = {
                                'Exam': exam_label,
                                'Class': cls,
                                'Score': row.get('Score')
                            }
                            # include Rank only if this exam's dataframe actually has a Rank column
                            if 'Rank' in df_r.columns:
                                row_dict['Rank'] = row.get('Rank')
                            combined_rows.append(row_dict)

                    if not combined_rows:
                        st.warning('No per-exam class ranking rows to display.')
                    else:
                        df_combined = pd.DataFrame(combined_rows)
                        # sort by Exam then Rank (ascending ranks: 1 is top)
                        try:
                            if 'Rank' in df_combined.columns:
                                df_combined = df_combined.sort_values(['Exam','Rank'], ascending=[True, True])
                            else:
                                df_combined = df_combined.sort_values(['Exam','Score'], ascending=[True, False])
                        except Exception:
                            pass

                        # reset index to provide clean row numbers
                        df_combined = df_combined.reset_index(drop=True)

                        st.subheader('Class Rankings — per exam (consolidated)')
                        # Add serial numbers to the consolidated table and show it
                        df_combined = _add_serial_column(df_combined, col_name='No')
                        st.dataframe(df_combined, use_container_width=True)
                        try:
                            csv_all = df_combined.to_csv(index=False).encode('utf-8')
                            st.download_button('Download per-exam class rankings (CSV)', data=csv_all, file_name='class_rankings_per_exam.csv', mime='text/csv')
                        except Exception:
                            pass
                        try:
                            title_con = (
                                f"Class Rankings — Per-exam consolidated listing for Year {selected_year} — Term {str(selected_term).title()} "
                                f"— Kinds: {', '.join(selected_kinds)} — Basis: {', '.join(basis_list)}"
                            )
                            pdfb_con = generate_pdf_most_improved(title_con, df_combined)
                            st.download_button('Download per-exam class rankings (PDF)', data=pdfb_con, file_name='class_rankings_per_exam.pdf', mime='application/pdf')
                        except Exception:
                            pass

                        # Optional categorization tools below the sheet (collapsed by default)
                        with st.expander('Categorize & export (optional)', expanded=False):
                            # Category manager: create named categories and assign classes to them (does not alter data)
                            classes_all = sorted(df_combined['Class'].astype(str).unique()) if 'Class' in df_combined.columns else []
                            # Load persisted categories into session if not present
                            if 'class_rank_categories' not in st.session_state:
                                try:
                                    cfg = load_persistent_config()
                                    persisted = cfg.get('class_rank_categories', {}) if isinstance(cfg, dict) else {}
                                    st.session_state['class_rank_categories'] = persisted if persisted is not None else {}
                                except Exception:
                                    st.session_state['class_rank_categories'] = {}

                            col1, col2 = st.columns([3,1])
                            with col1:
                                new_name = st.text_input('New category name (leave blank to skip)', key='class_rank_new_name')
                                new_members = st.multiselect('Select classes for the new category', options=classes_all, key='class_rank_new_members')
                            with col2:
                                if st.button('Add category', key='class_rank_add_btn') and new_name:
                                    # add/replace category and persist
                                    st.session_state['class_rank_categories'][new_name] = list(new_members)
                                    # persist to config
                                    try:
                                        cfg = load_persistent_config() or {}
                                        cfg['class_rank_categories'] = st.session_state['class_rank_categories']
                                        save_persistent_config(cfg)
                                    except Exception:
                                        pass
                                    # clear input field
                                    st.session_state['class_rank_new_name'] = ''

                            # show existing categories with delete buttons
                            if st.session_state.get('class_rank_categories'):
                                st.markdown('**Defined categories**')
                                for cname, members in list(st.session_state['class_rank_categories'].items()):
                                    c1, c2 = st.columns([8,1])
                                    with c1:
                                        st.write(f"**{cname}**: {', '.join(members)}")
                                    with c2:
                                        if st.button('Delete', key=f'class_rank_del_{cname}'):
                                            try:
                                                del st.session_state['class_rank_categories'][cname]
                                            except Exception:
                                                pass
                                            # persist removal
                                            try:
                                                cfg = load_persistent_config() or {}
                                                cfg['class_rank_categories'] = st.session_state.get('class_rank_categories', {})
                                                save_persistent_config(cfg)
                                            except Exception:
                                                pass
                                            # avoid calling st.experimental_rerun() inside the button callback

                            # Build grouped export from session categories if any
                            cats = st.session_state.get('class_rank_categories', {})
                            if cats:
                                grouped = {}
                                assigned_idx = set()
                                for cat, members in cats.items():
                                    mask = df_combined['Class'].astype(str).isin(members)
                                    grouped[cat] = df_combined[mask].copy()
                                    assigned_idx.update(df_combined[mask].index.tolist())
                                unassigned = df_combined.loc[~df_combined.index.isin(assigned_idx)].copy()
                                if len(unassigned):
                                    grouped['Unassigned'] = unassigned

                                # Try to create an Excel workbook in-memory with a sheet per category
                                try:
                                    from io import BytesIO
                                    bio = BytesIO()
                                    # prefer openpyxl/xlsxwriter if available
                                    try:
                                                with pd.ExcelWriter(bio, engine='openpyxl') as writer:
                                                    for cat, gdf in grouped.items():
                                                        sheet = str(cat)[:31]
                                                        gdf_out = _add_serial_column(gdf, col_name='No')
                                                        gdf_out.to_excel(writer, sheet_name=sheet, index=False)
                                    except Exception:
                                        with pd.ExcelWriter(bio, engine='xlsxwriter') as writer:
                                            for cat, gdf in grouped.items():
                                                sheet = str(cat)[:31]
                                                gdf_out = _add_serial_column(gdf, col_name='No')
                                                gdf_out.to_excel(writer, sheet_name=sheet, index=False)
                                    bio.seek(0)
                                    st.download_button('Download per-exam class rankings (Excel by category)', data=bio.getvalue(), file_name='class_rankings_per_exam_by_category.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                                except Exception:
                                    # fallback: create a zip of CSVs
                                    try:
                                        import zipfile
                                        from io import BytesIO
                                        zip_b = BytesIO()
                                        with zipfile.ZipFile(zip_b, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                                            for cat, gdf in grouped.items():
                                                gdf_out = _add_serial_column(gdf, col_name='No')
                                                csvdata = gdf_out.to_csv(index=False).encode('utf-8')
                                                name = f"{cat.replace(' ','_')}.csv"
                                                zf.writestr(name, csvdata)
                                        zip_b.seek(0)
                                        st.download_button('Download per-exam class rankings (ZIP of CSVs by category)', data=zip_b.getvalue(), file_name='class_rankings_per_exam_by_category.zip', mime='application/zip')
                                    except Exception:
                                        st.warning('Failed to prepare categorized export.')
                                # Also offer a combined PDF that contains one section per category (each section starts numbering at 1)
                                try:
                                    grouped_for_pdf = {str(cat): _add_serial_column(gdf, col_name='No') for cat, gdf in grouped.items()}
                                    try:
                                        cats_list = ', '.join([str(c) for c in grouped_for_pdf.keys()])
                                    except Exception:
                                        cats_list = ''
                                    title_cat_pdf = (
                                        f"Class Rankings — Per-exam by Category — Year {selected_year} — Term {str(selected_term).title()} "
                                        f"— Kinds: {', '.join(selected_kinds)} — {cats_list}"
                                    )
                                    pdfb_cat = generate_pdf_most_improved(title_cat_pdf, grouped_for_pdf)
                                    st.download_button('Download per-exam class rankings (PDF by category)', data=pdfb_cat, file_name='class_rankings_per_exam_by_category.pdf', mime='application/pdf')
                                except Exception:
                                    pass
                        try:
                            title = f"Class Rankings — Per exam (consolidated) — Year {selected_year} — Term {str(selected_term).title()} — Kinds: {', '.join(selected_kinds)} — Basis: {', '.join(basis_list)}"
                            pdfb = generate_pdf_most_improved(title, df_combined)
                            st.download_button('Download per-exam class rankings (PDF)', data=pdfb, file_name='class_rankings_per_exam.pdf', mime='application/pdf')
                        except Exception:
                            pass

    else:
        st.info('No saved exams found to compute class rankings.')

    # Export options
    st.markdown('<div class="section-header">Export & Reports</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.button("📥 Export All Data", disabled=True, help="Feature coming soon")
    
    with col2:
        st.button("📊 Generate Report", disabled=True, help="Feature coming soon")
    
    with col3:
        st.button("🗑️ Manage Exams", disabled=True, help="Feature coming soon")


    # Student Photos Management
    with st.expander("📚 Saved Student Photos Preview (click to show/hide)", expanded=False):
        # Show the photo preview grid only when the expander is open, filtered by year and class
        photo_map = photos.list_all_photos()
        if not photo_map:
            st.info("No student photos saved yet.")
        else:
            # Gather all years and classes from saved exams metadata
            import base64, os
            all_metadata = load_all_metadata()
            year_class_map = {}
            for exam in all_metadata.values():
                year = str(exam.get('date_saved', '')).split('-')[0]
                cls = exam.get('class_name', 'Unknown')
                if year not in year_class_map:
                    year_class_map[year] = set()
                year_class_map[year].add(cls)
            years = sorted([y for y in year_class_map if y and y != ''])
            selected_year = st.selectbox("Select Year", years, index=0 if years else None)
            classes = sorted(list(year_class_map[selected_year])) if selected_year else []
            selected_class = st.selectbox("Select Class", classes, index=0 if classes else None)

            # Filter photo_map by students in the selected year/class
            # Find all Adm Nos for the selected year/class
            adm_nos = set()
            for exam in all_metadata.values():
                year = str(exam.get('date_saved', '')).split('-')[0]
                cls = exam.get('class_name', 'Unknown')
                if year == selected_year and cls == selected_class:
                    # Try to get all Adm Nos from exam data
                    exam_id = exam.get('exam_id')
                    data, _, _ = load_exam_from_disk(exam_id) if exam_id else (None, None, None)
                    if data is not None and 'Adm No' in data.columns:
                        adm_nos.update(str(adm).strip() for adm in data['Adm No'].unique())
            # Now filter photo_map
            filtered_photos = {sid: entry for sid, entry in photo_map.items() if entry.get('adm_no','').strip() in adm_nos}
            if not filtered_photos:
                st.info("No student photos found for this class and year.")
            else:
                cols = st.columns(4)
                for idx, (sid, entry) in enumerate(filtered_photos.items()):
                    with cols[idx % 4]:
                        st.markdown(f"**Name:** {entry.get('name','')}  ")
                        st.markdown(f"**Adm No:** {entry.get('adm_no','')}")
                        img_path = entry.get('path')
                        displayed = False
                        try:
                            try:
                                from modules import storage
                            except Exception:
                                storage = None
                            if img_path:
                                if storage is not None and storage.exists(img_path):
                                    b = storage.read_bytes(img_path)
                                    if b:
                                        b64 = base64.b64encode(b).decode()
                                        st.markdown(f'<img src="data:image/png;base64,{b64}" style="width:100%;max-width:120px;border-radius:8px;box-shadow:0 2px 8px #aaa;">', unsafe_allow_html=True)
                                        displayed = True
                                elif os.path.exists(img_path):
                                    with open(img_path, 'rb') as img_file:
                                        img_bytes = img_file.read()
                                    b64 = base64.b64encode(img_bytes).decode()
                                    st.markdown(f'<img src="data:image/png;base64,{b64}" style="width:100%;max-width:120px;border-radius:8px;box-shadow:0 2px 8px #aaa;">', unsafe_allow_html=True)
                                    displayed = True
                        except Exception:
                            displayed = False
                        if not displayed:
                            st.markdown("<span style='color:#aaa;'>No Image</span>", unsafe_allow_html=True)


