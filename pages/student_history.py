# student_history.py
# EDUSCORE ANALYTICS - Student History & Progress Tracking
# Search for students, view performance across exams, track progress over time

import streamlit as st
import pandas as pd
import os
from modules import storage as storage_mod
import json
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from utils import student_photos as photos

# Try to import plotly, fallback to basic charts if not available
try:
    import plotly.graph_objects as go
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# Page configuration
st.set_page_config(page_title="Student History", layout="wide")

# Block access when parents portal mode is active
try:
    if st.session_state.get('parents_portal_mode'):
        st.markdown("<div style='opacity:0.45;padding:18px;border-radius:8px;background:#f3f4f6;color:#111;'>\
            <strong>Restricted:</strong> This page is not available in Parents Portal mode.</div>", unsafe_allow_html=True)
        st.stop()
except Exception:
    pass

# Define persistent storage path (use centralized storage helper which supports per-account dirs)
STORAGE_DIR = storage_mod.get_storage_dir()
METADATA_FILE = os.path.join(STORAGE_DIR, 'exams_metadata.json')

# Helper function to normalize class names
def normalize_class_name(class_name):
    """Normalize class names to standard format (e.g., 'Grade 9')"""
    if not class_name or pd.isna(class_name):
        return "Unknown"
    
    class_str = str(class_name).strip().lower()
    
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
    import re
    match = re.search(r'\d+', class_str)
    
    if match:
        grade_num = match.group()
        return f"Grade {grade_num}"
    
    # If no number found, capitalize first letter of each word
    return ' '.join(word.capitalize() for word in class_str.split())

# Helper functions for loading exam data
def load_all_metadata():
    """Load all exam metadata from disk"""
    try:
        data = storage_mod.read_json(METADATA_FILE)
        return data or {}
    except Exception:
        return {}

def load_exam_from_disk(exam_id):
    """Load a single exam's data from disk"""
    try:
        data_key = os.path.join(str(exam_id), 'data.pkl')
        df = storage_mod.read_pickle(data_key)
        return df
    except Exception:
        return None

def generate_student_history_pdf(student_name, adm_no, records, orientation='landscape', 
                                include_columns=None, chart_type='none', chart_image=None):
    """Generate PDF report of student's exam history with customization options
    
    Args:
        student_name: Student's full name
        adm_no: Admission number
        records: List of exam records
        orientation: 'portrait' or 'landscape'
        include_columns: List of columns to include (e.g., ['Total', 'Mean', 'Points', 'Rank'])
        chart_type: 'bar', 'line', or 'none'
        chart_image: BytesIO object containing chart image (if chart_type != 'none')
    """
    buffer = BytesIO()
    
    # Set page size based on orientation
    pagesize = landscape(A4) if orientation == 'landscape' else A4
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=0.5*inch,
        rightMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#0E6BA8'),
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    elements.append(Paragraph(f"STUDENT EXAM HISTORY", title_style))
    elements.append(Paragraph(f"Name: {student_name} | Admission No: {adm_no}", styles['Normal']))
    elements.append(Spacer(1, 0.2*inch))
    
    # Default columns if none specified
    if include_columns is None:
        include_columns = ['Total', 'Mean', 'Points', 'S/Rank', 'Rank']
    
    # Build table headers dynamically
    table_headers = ['Exam Name', 'Year', 'Class']
    column_map = {
        'Total': 'Total Marks',
        'Mean': 'Mean %',
        'Points': 'Points',
        'S/Rank': 'Class Rank',
        'Rank': 'Overall Rank'
    }
    
    for col in include_columns:
        if col in column_map:
            table_headers.append(column_map[col])
    
    table_data = [table_headers]
    
    # Build table rows
    for rec in sorted(records, key=lambda x: (x.get('year', 0), x.get('date', '')), reverse=True):
        student_row = rec['student_data']
        
        # Basic columns
        row = [
            str(rec.get('exam_name', 'N/A')),
            str(rec.get('year', 'N/A')),
            normalize_class_name(rec.get('class_name', 'N/A'))
        ]
        
        # Add selected columns
        for col in include_columns:
            if col == 'Points':
                val = student_row.get('Points')
                row.append(str(val) if pd.notna(val) and str(val).strip() else 'N/A')
            else:
                row.append(str(student_row.get(col, 'N/A')))
        
        table_data.append(row)
    
    # Calculate column widths dynamically
    num_cols = len(table_headers)
    available_width = (pagesize[0] - 1*inch) if orientation == 'landscape' else (pagesize[0] - 1*inch)
    
    # Allocate widths: Exam Name gets more space
    exam_name_width = 2.5*inch if num_cols <= 6 else 2*inch
    remaining_width = available_width - exam_name_width
    other_col_width = remaining_width / (num_cols - 1)
    
    col_widths = [exam_name_width] + [other_col_width] * (num_cols - 1)
    
    # Create table
    table = Table(table_data, colWidths=col_widths)
    
    # Style table
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0E6BA8')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Add chart if provided
    if chart_type != 'none' and chart_image is not None:
        from reportlab.platypus import Image as RLImage
        try:
            chart_image.seek(0)
            img = RLImage(chart_image, width=6*inch, height=3.5*inch)
            elements.append(Spacer(1, 0.2*inch))
            elements.append(Paragraph(f"Performance Chart ({chart_type.capitalize()})", styles['Heading2']))
            elements.append(Spacer(1, 0.1*inch))
            elements.append(img)
        except Exception as e:
            elements.append(Paragraph(f"Chart could not be embedded: {str(e)}", styles['Normal']))
    
    # Footer
    footer_text = f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} | EDUSCORE ANALYTICS"
    elements.append(Paragraph(footer_text, styles['Normal']))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

# Custom CSS
st.markdown("""
    <style>
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
    
    .student-card {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        margin: 1rem 0;
    }
    
    .metric-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem;
        border-radius: 8px;
        text-align: center;
        margin: 0.5rem 0;
    }
    
    .exam-row {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        border-left: 4px solid #0E6BA8;
    }
    </style>
""", unsafe_allow_html=True)

# Header
st.markdown('<div class="main-header">👤 Student History & Progress Tracking</div>', unsafe_allow_html=True)

# Back button
if st.button("⬅ Back to Home", type="secondary"):
    # Ensure the full home header (with banners) is shown when returning
    st.session_state.current_page = 'home'
    st.session_state.show_home_header = True
    # Streamlit will rerun after the button interaction; avoid calling st.rerun() inside the callback.

st.markdown("---")

# Load all exam metadata
all_metadata = load_all_metadata()

if not all_metadata:
    st.info("📋 No saved exams found. Save some exams first to track student history.")
else:
    # Convert metadata to list for easier filtering
    exams_list = list(all_metadata.values())

    # --- Filters ---
    # Get unique years and normalized classes from metadata
    years = sorted(set([e.get('year') for e in exams_list if e.get('year')]), reverse=True)

    normalized_classes = {}
    for e in exams_list:
        if e.get('class_name'):
            normalized_classes[e.get('class_name')] = normalize_class_name(e.get('class_name'))

    unique_classes = sorted(set(normalized_classes.values()))

    st.markdown("### 🎯 Filters")
    fcol1, fcol2 = st.columns(2)
    with fcol1:
        year_filter = st.selectbox("📅 Year", options=["All Years"] + [str(y) for y in years])
    with fcol2:
        class_filter = st.selectbox("📚 Class", options=["All Classes"] + unique_classes)

    st.markdown("---")

    # Build a list of exam_ids that match the selected filters so student lists are filtered
    filtered_exam_ids = []
    for exam_id, metadata in all_metadata.items():
        if year_filter != "All Years" and str(metadata.get('year')) != str(year_filter):
            continue
        if class_filter != "All Classes":
            if normalize_class_name(metadata.get('class_name')) != class_filter:
                continue
        filtered_exam_ids.append(exam_id)

    # Pre-load student names and admission numbers from the filtered exams
    all_students = {}  # key: (name, adm_no) -> list of exam_ids
    with st.spinner("Loading student database..."):
        for exam_id in filtered_exam_ids:
            metadata = all_metadata.get(exam_id, {})
            exam_df = load_exam_from_disk(exam_id)
            if exam_df is not None and 'Name' in exam_df.columns:
                for _, row in exam_df.iterrows():
                    name = str(row.get('Name', '')).strip()
                    adm = str(row.get('Adm No', '')).strip()
                    if not name or name.lower() in ['totals', 'means', 'total', 'mean', 'average']:
                        continue
                    key = (name, adm)
                    if key not in all_students:
                        all_students[key] = []
                    all_students[key].append(exam_id)

    # Build autocomplete options from the filtered student set
    student_names = sorted(set([name for name, _ in all_students.keys()]))
    student_adm_nos = sorted(set([adm for _, adm in all_students.keys() if adm]))

    # Search controls (built after filters so options reflect selected filters)
    st.markdown("### 🔍 Search Student")
    # If there are no students in the filtered exams, show a helpful message
    if not student_names and not student_adm_nos:
        # No students available for the selected filters — do not display a persistent info box here.
        selected_name = ""
        selected_adm = ""
    else:
        scol1, scol2 = st.columns([3, 2])
        with scol1:
            # Allow free-text search so users can type partial names (more flexible than selectbox)
            selected_name = st.text_input(
                "🔎 Search by Name",
                value="",
                placeholder="Type full or partial student name (filtered by Year/Class)",
                help="Type a name to search across the filtered exams"
            )
            if not selected_name and student_names:
                # show a small hint of available names (first 6) to help the user
                hint = ', '.join(student_names[:6]) + (', ...' if len(student_names) > 6 else '')
                st.caption(f"Examples: {hint}")
        with scol2:
            selected_adm = st.text_input(
                "🔢 Search by Admission Number",
                value="",
                placeholder="Type admission number (optional)",
                help="Type admission number to search across the filtered exams"
            )
            if not selected_adm and student_adm_nos:
                st.caption(f"Examples: {', '.join(student_adm_nos[:6])}{', ...' if len(student_adm_nos) > 6 else ''}")

    # Determine search term from either name or adm no
    search_term = selected_name if selected_name else selected_adm
    
    # Search for student
    if search_term:
        st.markdown(f"### 📊 Results for: **{search_term}**")
        
        # Filter exams based on year/class
        filtered_exams = []
        for exam_id, metadata in all_metadata.items():
            if year_filter != "All Years" and str(metadata.get('year')) != year_filter:
                continue
            if class_filter != "All Classes":
                # Normalize and compare
                exam_class_normalized = normalize_class_name(metadata.get('class_name'))
                if exam_class_normalized != class_filter:
                    continue
            filtered_exams.append((exam_id, metadata))
        
        if not filtered_exams:
            st.warning("No exams found matching the selected filters.")
        else:
            # Search across all filtered exams
            student_records = []
            
            for exam_id, metadata in filtered_exams:
                exam_df = load_exam_from_disk(exam_id)
                if exam_df is not None and 'Name' in exam_df.columns:
                    # Search by name or admission number
                    search_lower = search_term.lower()
                    matches = exam_df[
                        exam_df['Name'].astype(str).str.lower().str.contains(search_lower, na=False) |
                        (exam_df.get('Adm No', pd.Series(['']*len(exam_df))).astype(str).str.lower().str.contains(search_lower, na=False))
                    ]
                    
                    for _, row in matches.iterrows():
                        student_records.append({
                            'exam_id': exam_id,
                            'exam_name': metadata.get('exam_name'),
                            'year': metadata.get('year'),
                            'class_name': normalize_class_name(metadata.get('class_name')),
                            'date': metadata.get('date_saved'),
                            'student_data': row
                        })
            
            if not student_records:
                st.warning(f"No students found matching '{search_term}' in the selected filters.")
            else:
                # Group records by student (using name + adm no)
                students_dict = {}
                for record in student_records:
                    name = str(record['student_data'].get('Name', '')).strip()
                    adm = str(record['student_data'].get('Adm No', '')).strip()
                    key = f"{name}_{adm}"
                    
                    if key not in students_dict:
                        students_dict[key] = {
                            'name': name,
                            'adm_no': adm,
                            'records': []
                        }
                    students_dict[key]['records'].append(record)
                
                # Display each student
                for student_key, student_info in students_dict.items():
                    with st.expander(f"**{student_info['name']}** (Adm: {student_info['adm_no']}) - {len(student_info['records'])} exam(s)", expanded=True):
                        records = sorted(student_info['records'], 
                                       key=lambda x: (x.get('year', 0), x.get('date', '')), 
                                       reverse=True)
                        
                        # Photo + Summary metrics
                        mcol1, mcol2, mcol3, mcol4 = st.columns(4)

                        # Show student photo if available
                        try:
                            sname = student_info['name']
                            sadm = student_info['adm_no']
                            p_path = photos.get_photo_path(name=sname, adm_no=sadm)
                            if p_path and os.path.exists(p_path):
                                st.image(p_path, caption="Student Photo", width=140)
                        except Exception:
                            pass
                        
                        # Calculate stats
                        totals = []
                        means = []
                        ranks = []
                        
                        for rec in records:
                            try:
                                if 'Total' in rec['student_data'].index:
                                    total = rec['student_data'].get('Total')
                                    if pd.notna(total):
                                        totals.append(float(total))
                            except: pass
                            
                            try:
                                if 'Mean' in rec['student_data'].index:
                                    mean = rec['student_data'].get('Mean')
                                    if pd.notna(mean):
                                        means.append(float(mean))
                            except: pass
                            
                            try:
                                if 'Rank' in rec['student_data'].index:
                                    rank = rec['student_data'].get('Rank')
                                    if pd.notna(rank) and str(rank).strip():
                                        ranks.append(int(float(rank)))
                            except: pass
                        
                        with mcol1:
                            st.markdown(f"""
                                <div class='metric-box'>
                                    <div style='font-size: 2rem;'>{len(records)}</div>
                                    <div>Total Exams</div>
                                </div>
                            """, unsafe_allow_html=True)
                        
                        with mcol2:
                            avg_total = sum(totals) / len(totals) if totals else 0
                            st.markdown(f"""
                                <div class='metric-box'>
                                    <div style='font-size: 2rem;'>{avg_total:.1f}</div>
                                    <div>Avg Total</div>
                                </div>
                            """, unsafe_allow_html=True)
                        
                        with mcol3:
                            avg_mean = sum(means) / len(means) if means else 0
                            st.markdown(f"""
                                <div class='metric-box'>
                                    <div style='font-size: 2rem;'>{avg_mean:.1f}%</div>
                                    <div>Avg Mean</div>
                                </div>
                            """, unsafe_allow_html=True)
                        
                        with mcol4:
                            best_rank = min(ranks) if ranks else 'N/A'
                            st.markdown(f"""
                                <div class='metric-box'>
                                    <div style='font-size: 2rem;'>{best_rank}</div>
                                    <div>Best Rank</div>
                                </div>
                            """, unsafe_allow_html=True)
                        
                        st.markdown("---")
                        
                        # PDF Customization Options
                        st.markdown("**⚙️ PDF Export Options**")
                        
                        pdf_col1, pdf_col2 = st.columns(2)
                        
                        with pdf_col1:
                            st.markdown("**Include Columns:**")
                            include_total = st.checkbox("Total Marks", value=True, key=f"total_{student_key}")
                            include_mean = st.checkbox("Mean %", value=True, key=f"mean_{student_key}")
                            include_points = st.checkbox("Points", value=True, key=f"points_{student_key}")
                            include_srank = st.checkbox("Class Rank (S/Rank)", value=True, key=f"srank_{student_key}")
                            include_rank = st.checkbox("Overall Rank", value=True, key=f"rank_{student_key}")
                        
                        with pdf_col2:
                            st.markdown("**Page Layout:**")
                            pdf_orientation = st.radio(
                                "Orientation",
                                options=["landscape", "portrait"],
                                format_func=lambda x: "📄 Landscape (Wide)" if x == "landscape" else "📄 Portrait (Tall)",
                                key=f"orient_{student_key}"
                            )
                            
                            st.markdown("**Chart Type:**")
                            chart_type = st.radio(
                                "Include Chart",
                                options=["none", "line", "bar"],
                                format_func=lambda x: {"none": "❌ No Chart", "line": "📈 Line Chart", "bar": "📊 Bar Chart"}[x],
                                key=f"chart_{student_key}"
                            )
                        
                        # Build selected columns list
                        selected_columns = []
                        if include_total:
                            selected_columns.append('Total')
                        if include_mean:
                            selected_columns.append('Mean')
                        if include_points:
                            selected_columns.append('Points')
                        if include_srank:
                            selected_columns.append('S/Rank')
                        if include_rank:
                            selected_columns.append('Rank')
                        
                        # Generate chart image if needed
                        chart_image = None
                        if chart_type != 'none' and PLOTLY_AVAILABLE and (means or totals):
                            try:
                                import plotly.io as pio
                                
                                # Prepare data for chart
                                chart_records = sorted(records, key=lambda x: (x.get('year', 0), x.get('date', '')))
                                exam_labels = [f"{r['exam_name']} ({r['year']})" for r in chart_records]
                                
                                if chart_type == 'line':
                                    fig = go.Figure()
                                    if means:
                                        fig.add_trace(go.Scatter(
                                            x=exam_labels[-len(means):], 
                                            y=means,
                                            mode='lines+markers',
                                            name='Mean %',
                                            line=dict(color='#667eea', width=3),
                                            marker=dict(size=10)
                                        ))
                                    fig.update_layout(
                                        title='Performance Trend',
                                        xaxis_title='Exam',
                                        yaxis_title='Mean %',
                                        height=400,
                                        template='plotly_white'
                                    )
                                else:  # bar chart
                                    fig = go.Figure()
                                    if means:
                                        fig.add_trace(go.Bar(
                                            x=exam_labels[-len(means):],
                                            y=means,
                                            name='Mean %',
                                            marker_color='#667eea'
                                        ))
                                    fig.update_layout(
                                        title='Performance Overview',
                                        xaxis_title='Exam',
                                        yaxis_title='Mean %',
                                        height=400,
                                        template='plotly_white'
                                    )
                                
                                # Convert to image
                                img_bytes = pio.to_image(fig, format='png', width=1200, height=600)
                                chart_image = BytesIO(img_bytes)
                                
                            except Exception as e:
                                st.warning(f"Could not generate chart: {str(e)}")
                        
                        # PDF Download button
                        if selected_columns:
                            pdf_buffer = generate_student_history_pdf(
                                student_name=student_info['name'],
                                adm_no=student_info['adm_no'],
                                records=records,
                                orientation=pdf_orientation,
                                include_columns=selected_columns,
                                chart_type=chart_type,
                                chart_image=chart_image
                            )
                            
                            safe_filename = "".join(c if c.isalnum() or c in (' ', '_') else '_' for c in student_info['name'])
                            
                            st.download_button(
                                label="📄 Download Complete History (PDF)",
                                data=pdf_buffer,
                                file_name=f"{safe_filename}_exam_history.pdf",
                                mime="application/pdf",
                                use_container_width=True,
                                type="primary"
                            )
                        else:
                            st.warning("⚠️ Please select at least one column to include in the PDF")
                        
                        st.markdown("---")
                        
                        # Performance chart (if we have data)
                        if means or totals:
                            chart_col1, chart_col2 = st.columns(2)
                            
                            if PLOTLY_AVAILABLE:
                                with chart_col1:
                                    st.markdown("**📈 Mean Performance Trend**")
                                    if means:
                                        # Create trend chart
                                        chart_data = pd.DataFrame({
                                            'Exam': [rec['exam_name'] for rec in records[-len(means):]],
                                            'Mean': means
                                        })
                                        fig = px.line(chart_data, x='Exam', y='Mean', 
                                                    markers=True, 
                                                    title='Mean % Across Exams',
                                                    labels={'Mean': 'Mean %', 'Exam': 'Exam Name'})
                                        fig.update_traces(line_color='#667eea', marker=dict(size=10))
                                        fig.update_layout(height=300)
                                        st.plotly_chart(fig, use_container_width=True)
                                    else:
                                        st.caption("No mean data available")
                                
                                with chart_col2:
                                    st.markdown("**📊 Total Marks Trend**")
                                    if totals:
                                        chart_data = pd.DataFrame({
                                            'Exam': [rec['exam_name'] for rec in records[-len(totals):]],
                                            'Total': totals
                                        })
                                        fig = px.bar(chart_data, x='Exam', y='Total',
                                                   title='Total Marks Across Exams',
                                                   labels={'Total': 'Total Marks', 'Exam': 'Exam Name'})
                                        fig.update_traces(marker_color='#764ba2')
                                        fig.update_layout(height=300)
                                        st.plotly_chart(fig, use_container_width=True)
                                    else:
                                        st.caption("No total data available")
                            else:
                                # Fallback: display as tables (Plotly not installed)
                                with chart_col1:
                                    st.markdown("**📈 Mean Performance Trend**")
                                    if means:
                                        chart_data = pd.DataFrame({
                                            'Exam': [rec['exam_name'] for rec in records[-len(means):]],
                                            'Mean %': [f"{m:.1f}" for m in means]
                                        })
                                        st.dataframe(chart_data, use_container_width=True, hide_index=True)
                                    else:
                                        st.caption("No mean data available")
                                
                                with chart_col2:
                                    st.markdown("**📊 Total Marks Trend**")
                                    if totals:
                                        chart_data = pd.DataFrame({
                                            'Exam': [rec['exam_name'] for rec in records[-len(totals):]],
                                            'Total': [f"{t:.0f}" for t in totals]
                                        })
                                        st.dataframe(chart_data, use_container_width=True, hide_index=True)
                                    else:
                                        st.caption("No total data available")
                                
                                st.info("💡 Install Plotly for interactive charts: pip install plotly")
                        
                        st.markdown("---")
                        
                        # Detailed exam records
                        st.markdown("**📋 Exam Records**")
                        for rec in records:
                            st.markdown(f"""
                                <div class='exam-row'>
                                    <strong>{rec['exam_name']}</strong> 
                                    ({rec['year']}, {rec['class_name']})
                                </div>
                            """, unsafe_allow_html=True)
                            
                            # Display key metrics
                            ecol1, ecol2, ecol3, ecol4, ecol5 = st.columns(5)
                            student_row = rec['student_data']
                            
                            with ecol1:
                                st.metric("Total", student_row.get('Total', 'N/A'))
                            with ecol2:
                                st.metric("Mean", student_row.get('Mean', 'N/A'))
                            with ecol3:
                                st.metric("Rank", student_row.get('Rank', 'N/A'))
                            with ecol4:
                                st.metric("S/Rank", student_row.get('S/Rank', 'N/A'))
                            with ecol5:
                                points = student_row.get('Points', 'N/A')
                                st.metric("Points", points if pd.notna(points) and str(points).strip() else 'N/A')
                            
                            # Subject scores
                            with st.expander("📚 View Subject Scores"):
                                # Get all subject columns (exclude standard columns)
                                exclude_cols = {'Name', 'Adm No', 'Class', 'Total', 'Mean', 'Rank', 'S/Rank', 'Points', 'Mean Grade'}
                                subject_cols = [col for col in student_row.index if col not in exclude_cols]
                                
                                if subject_cols:
                                    # Display subjects in a grid
                                    num_cols = 4
                                    for i in range(0, len(subject_cols), num_cols):
                                        cols = st.columns(num_cols)
                                        for j, col_obj in enumerate(cols):
                                            if i + j < len(subject_cols):
                                                subj = subject_cols[i + j]
                                                score = student_row.get(subj, 'N/A')
                                                with col_obj:
                                                    st.caption(f"**{subj}**")
                                                    st.write(score)
                                else:
                                    st.caption("No subject scores available")
    
    else:
        # Prompt removed to reduce UI noise; users should interact with the filters/search controls.
        pass

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 1rem;'>
    <p style='margin: 0; font-size: 0.9rem;'><strong>EDUSCORE ANALYTICS</strong></p>
    <p style='margin: 0.3rem 0; font-size: 0.85rem;'>Developed by <strong>Munyua Kamau</strong></p>
    <p style='margin: 0.3rem 0; font-size: 0.75rem; color: #888;'>© 2025 All Rights Reserved</p>
</div>
""", unsafe_allow_html=True)
