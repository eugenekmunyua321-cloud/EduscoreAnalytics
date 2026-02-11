from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import datetime
import os
from io import BytesIO


def generate_analytics_pdf(out_path, df_teach, df_subj, unassigned, title='Assignment Analytics'):
    """Generate a multi-page PDF with per-exam-kind teacher rankings, a combined teacher ranking,
    subject summaries and an unassigned subjects list.

    df_teach: DataFrame with columns ['ExamKind','Teacher','Count','SumMean','AvgMean']
    df_subj: DataFrame with columns ['ExamKind','Subject','Count','SumMean','AvgMean']
    unassigned: list of subject names
    """
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    doc = SimpleDocTemplate(out_path, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    elems = []

    # emphasize title slightly larger for clarity
    title_style = styles['Title']
    try:
        title_style.fontSize = 18
    except Exception:
        pass
    elems.append(Paragraph(title, title_style))
    elems.append(Spacer(1, 8))
    elems.append(Paragraph(f'Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal']))
    elems.append(Spacer(1, 12))

    # Per-exam-kind teacher summaries
    if df_teach is None or df_teach.empty:
        elems.append(Paragraph('No teacher summaries available.', styles['Normal']))
    else:
        kinds = sorted(df_teach['ExamKind'].unique())
        for kind in kinds:
            elems.append(Paragraph(f'Teacher ranking — {kind}', styles['Heading2']))
            sub = df_teach[df_teach['ExamKind'] == kind].copy()
            sub = sub.sort_values('AvgMean', ascending=False)
            data = [list(sub.columns)]
            for _, r in sub.iterrows():
                data.append([r[c] for c in sub.columns])
            tbl = Table(data, repeatRows=1)
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F0F0F0')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (-2, 0), (-1, -1), 'RIGHT'),
            ]))
            elems.append(tbl)
            elems.append(Spacer(1, 12))

        # Combined across kinds: aggregate by Teacher
        elems.append(PageBreak())
        elems.append(Paragraph('Combined teacher ranking (across selected kinds)', styles['Heading2']))
        grp = df_teach.groupby('Teacher').agg({'AvgMean': 'mean', 'SumMean': 'sum', 'Count': 'sum'}).reset_index()
        grp = grp[['Teacher', 'Count', 'SumMean', 'AvgMean']].sort_values('AvgMean', ascending=False)
        data = [list(grp.columns)] + [list(r) for r in grp.values.tolist()]
        tbl = Table(data, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F0F0F0')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (-2, 0), (-1, -1), 'RIGHT'),
        ]))
        elems.append(tbl)
        elems.append(Spacer(1, 12))

    # Per-exam-kind subject summaries removed (user requested only teacher summaries)

    # Unassigned subjects
    if unassigned:
        elems.append(PageBreak())
        elems.append(Paragraph('Subjects not assigned in the selected exams', styles['Heading2']))
        for s in unassigned:
            elems.append(Paragraph(f'- {s}', styles['Normal']))

    doc.build(elems)


def generate_teacher_table_pdf(out_path, df, title='Teacher Ranking'):
    """Generate a single-page PDF containing the provided teacher dataframe table.

    df: DataFrame or list-of-lists where first row is header.
    """
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    doc = SimpleDocTemplate(out_path, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    elems = []
    # emphasize title slightly larger for clarity
    title_style = styles['Title']
    try:
        title_style.fontSize = 18
    except Exception:
        pass
    elems.append(Paragraph(title, title_style))
    elems.append(Spacer(1, 8))
    elems.append(Paragraph(f'Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal']))
    elems.append(Spacer(1, 12))

    # Normalize df to list of lists and convert Subjects column to vertical paragraphs
    try:
        cols = list(df.columns)
        data = [cols]
        subj_idxs = [i for i, c in enumerate(cols) if 'subject' in str(c).lower()]
        for r in df.values.tolist():
            row = []
            for i, v in enumerate(r):
                if i in subj_idxs and v is not None:
                    # render subjects as a paragraph so they wrap horizontally
                    try:
                        s = str(v)
                        row.append(Paragraph(s, styles['Normal']))
                    except Exception:
                        row.append(str(v))
                else:
                    row.append(v)
            data.append(row)
    except Exception:
        # assume df is already a list-of-lists
        data = df

    # compute column widths to nicely fit the landscape A4 page (respecting margins)
    page_width, _ = landscape(A4)
    left_margin = doc.leftMargin
    right_margin = doc.rightMargin
    avail_width = page_width - left_margin - right_margin
    ncols = len(data[0]) if data and len(data) > 0 else 1

    # Determine content-length based weights for each column to allocate proportional width
    try:
        headers = data[0]
        rows = data[1:]
        max_lens = []
        for ci in range(ncols):
            max_len = len(str(headers[ci]))
            for r in rows:
                try:
                    cell = r[ci]
                    s = '' if cell is None else (getattr(cell, 'text', None) or str(cell))
                except Exception:
                    s = ''
                max_len = max(max_len, len(s))
            max_lens.append(max_len)

        # apply multipliers: shrink numeric/short identifier columns, boost subjects and teacher
        multipliers = []
        for h, ml in zip(headers, max_lens):
            key = str(h).lower()
            if 'subject' in key:
                m = 2.6
            elif 'teacher' in key:
                m = 1.6
            elif key.strip() in ('count', 'avgmean', 'summean') or 'count' in key or 'avgmean' in key:
                m = 1.2
            elif 'exam' in key and 'kind' in key:
                m = 1.2
            elif 'group' in key:
                m = 0.8
            else:
                m = 1.0
            multipliers.append(m)

        raw_weights = [max(1.0, ml) * m for ml, m in zip(max_lens, multipliers)]
        total = sum(raw_weights)
        if total <= 0:
            prelim = [avail_width / max(1, ncols)] * ncols
        else:
            prelim = [avail_width * (w / total) for w in raw_weights]

        # Enforce reasonable minimum widths by column type (fractions of available width)
        min_fracs = []
        for h in headers:
            key = str(h).lower()
            if 'subject' in key:
                min_fracs.append(0.22)
            elif 'teacher' in key:
                min_fracs.append(0.16)
            elif key.strip() in ('count', 'avgmean', 'summean') or 'count' in key or 'avgmean' in key:
                min_fracs.append(0.10)
            elif 'exam' in key and 'kind' in key:
                min_fracs.append(0.12)
            elif 'group' in key:
                min_fracs.append(0.08)
            else:
                min_fracs.append(0.06)

        min_widths = [avail_width * f for f in min_fracs]

        # Start with preliminary widths, then bump to minimums where needed
        widths = [max(p, m) for p, m in zip(prelim, min_widths)]

        total_w = sum(widths)
        if total_w > avail_width:
            # need to reduce widths but not below min_widths
            excess = total_w - avail_width
            reducible = sum((w - m) for w, m in zip(widths, min_widths) if w > m)
            if reducible <= 0:
                # can't reduce without violating minima: normalize min_widths to fit
                s = sum(min_widths)
                if s <= 0:
                    colWidths = [avail_width / max(1, ncols)] * ncols
                else:
                    colWidths = [avail_width * (mw / s) for mw in min_widths]
            else:
                colWidths = []
                for w, m in zip(widths, min_widths):
                    if w <= m:
                        colWidths.append(m)
                    else:
                        reduction = (w - m) / reducible * excess
                        colWidths.append(w - reduction)
        else:
            colWidths = widths
    except Exception:
        colWidths = [avail_width / max(1, ncols)] * ncols

    tbl = Table(data, repeatRows=1, colWidths=colWidths)
    # determine avgmean column index (if any) to increase its font size slightly
    try:
        headers = data[0]
        avg_idx = next((i for i, h in enumerate(headers) if 'avg' in str(h).lower()), None)
    except Exception:
        avg_idx = None

    base_styles = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F0F0F0')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (-2, 0), (-1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]
    if avg_idx is not None:
        try:
            # ensure AvgMean header fits: use same header font or slightly smaller
            base_styles.append(('FONTSIZE', (avg_idx, 0), (avg_idx, 0), 12))
            base_styles.append(('FONTSIZE', (avg_idx, 1), (avg_idx, -1), 12))
            base_styles.append(('ALIGN', (avg_idx, 0), (avg_idx, -1), 'RIGHT'))
        except Exception:
            pass
    tbl.setStyle(TableStyle(base_styles))
    elems.append(tbl)
    doc.build(elems)


def generate_teacher_table_bytes(df, title='Teacher Ranking'):
    """Return PDF bytes for the given dataframe/table title without writing to disk."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    elems = []
    # emphasize title slightly larger for clarity (match other generators)
    title_style = styles['Title']
    try:
        title_style.fontSize = 18
    except Exception:
        pass
    elems.append(Paragraph(title, title_style))
    elems.append(Spacer(1, 8))
    elems.append(Paragraph(f'Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal']))
    elems.append(Spacer(1, 12))

    try:
        cols = list(df.columns)
        data = [cols]
        subj_idxs = [i for i, c in enumerate(cols) if 'subject' in str(c).lower()]
        for r in df.values.tolist():
            row = []
            for i, v in enumerate(r):
                if i in subj_idxs and v is not None:
                    try:
                        s = str(v)
                        row.append(Paragraph(s, styles['Normal']))
                    except Exception:
                        row.append(str(v))
                else:
                    row.append(v)
            data.append(row)
    except Exception:
        data = df

    # compute column widths to nicely fit the landscape A4 page
    page_width, _ = landscape(A4)
    left_margin = doc.leftMargin
    right_margin = doc.rightMargin
    avail_width = page_width - left_margin - right_margin
    ncols = len(data[0]) if data and len(data) > 0 else 1

    # Determine content-length based weights for each column to allocate proportional width
    try:
        headers = data[0]
        rows = data[1:]
        max_lens = []
        for ci in range(ncols):
            max_len = len(str(headers[ci]))
            for r in rows:
                try:
                    cell = r[ci]
                    s = '' if cell is None else (getattr(cell, 'text', None) or str(cell))
                except Exception:
                    s = ''
                max_len = max(max_len, len(s))
            max_lens.append(max_len)

        multipliers = []
        for h, ml in zip(headers, max_lens):
            key = str(h).lower()
            if 'subject' in key:
                m = 3.0
            elif 'teacher' in key:
                m = 1.6
            elif key.strip() in ('count', 'avgmean', 'summean') or 'count' in key or 'avgmean' in key:
                m = 0.5
            elif 'exam' in key and 'kind' in key:
                m = 0.6
            elif 'group' in key:
                m = 0.6
            else:
                m = 1.0
            multipliers.append(m)

        raw_weights = [max(1.0, ml) * m for ml, m in zip(max_lens, multipliers)]
        total = sum(raw_weights)
        if total <= 0:
            prelim = [avail_width / max(1, ncols)] * ncols
        else:
            prelim = [avail_width * (w / total) for w in raw_weights]

        # Enforce reasonable minimum widths by column type (fractions of available width)
        min_fracs = []
        for h in headers:
            key = str(h).lower()
            if 'subject' in key:
                min_fracs.append(0.28)
            elif 'teacher' in key:
                min_fracs.append(0.18)
            elif key.strip() in ('count', 'avgmean', 'summean') or 'count' in key or 'avgmean' in key:
                min_fracs.append(0.06)
            elif 'exam' in key and 'kind' in key:
                min_fracs.append(0.07)
            elif 'group' in key:
                min_fracs.append(0.07)
            else:
                min_fracs.append(0.08)

        min_widths = [avail_width * f for f in min_fracs]

        # Start with preliminary widths, then bump to minimums where needed
        widths = [max(p, m) for p, m in zip(prelim, min_widths)]

        total_w = sum(widths)
        if total_w > avail_width:
            # need to reduce widths but not below min_widths
            excess = total_w - avail_width
            reducible = sum((w - m) for w, m in zip(widths, min_widths) if w > m)
            if reducible <= 0:
                # can't reduce without violating minima: normalize min_widths to fit
                s = sum(min_widths)
                if s <= 0:
                    colWidths = [avail_width / max(1, ncols)] * ncols
                else:
                    colWidths = [avail_width * (mw / s) for mw in min_widths]
            else:
                colWidths = []
                for w, m in zip(widths, min_widths):
                    if w <= m:
                        colWidths.append(m)
                    else:
                        reduction = (w - m) / reducible * excess
                        colWidths.append(w - reduction)
        else:
            colWidths = widths
    except Exception:
        colWidths = [avail_width / max(1, ncols)] * ncols

    tbl = Table(data, repeatRows=1, colWidths=colWidths)
    # determine avgmean column index (if any) to increase its font size slightly
    try:
        headers = data[0]
        avg_idx = next((i for i, h in enumerate(headers) if 'avg' in str(h).lower()), None)
    except Exception:
        avg_idx = None

    base_styles = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F0F0F0')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (-2, 0), (-1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]
    if avg_idx is not None:
        try:
            base_styles.append(('FONTSIZE', (avg_idx, 0), (avg_idx, 0), 12))
            base_styles.append(('FONTSIZE', (avg_idx, 1), (avg_idx, -1), 11))
            base_styles.append(('ALIGN', (avg_idx, 0), (avg_idx, -1), 'RIGHT'))
        except Exception:
            pass
    tbl.setStyle(TableStyle(base_styles))
    elems.append(tbl)
    doc.build(elems)
    buf.seek(0)
    return buf.read()
