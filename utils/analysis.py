import pandas as pd

def read_marks(file):
    """
    Read an Excel file into a DataFrame.
    Expected minimal columns: Name, AdmNo, Class, Subject, Marks
    """
    df = pd.read_excel(file)
    return df

def compute_results(df):
    """
    Example processing:
    - If input is "long" format (one row per student-per-subject), we will
      pivot to wide, compute total and mean across subjects, and return a wide table.
    """
    # If the file is in long form (Student, Subject, Marks), pivot it.
    expected_cols = set(df.columns.str.lower())
    # Try to detect long format
    if {'subject', 'marks'}.issubset(expected_cols):
        # Normalize column names to lower for safe access
        df_cols = {c.lower(): c for c in df.columns}
        name_col = df_cols.get('name', df.columns[0])
        adm_col = df_cols.get('admno', df.columns[0])
        class_col = df_cols.get('class', df.columns[0])
        subj_col = df_cols.get('subject')
        marks_col = df_cols.get('marks')

        pivot = df.pivot_table(index=[adm_col, name_col, class_col],
                               columns=subj_col,
                               values=marks_col,
                               aggfunc='first').reset_index()
    else:
        # assume data already wide (Name, AdmNo, Class, subject columns...)
        pivot = df.copy()

    # identify subject columns (exclude AdmNo, Name, Class, Term, Year if present)
    non_subjects = {'admno', 'name', 'class', 'term', 'year'}
    subj_cols = [c for c in pivot.columns if c.lower() not in non_subjects]

    # compute totals and mean
    pivot['Total'] = pivot[subj_cols].sum(axis=1, skipna=True)
    pivot['Mean'] = pivot['Total'] / len(subj_cols)

    # grading function (example)
    def grade(mean):
        try:
            m = float(mean)
        except:
            return ''
        if m >= 80: return 'A'
        if m >= 75: return 'A-'
        if m >= 70: return 'B+'
        if m >= 65: return 'B'
        if m >= 60: return 'B-'
        if m >= 55: return 'C+'
        if m >= 50: return 'C'
        if m >= 45: return 'C-'
        if m >= 40: return 'D+'
        if m >= 35: return 'D'
        return 'E'

    pivot['Grade'] = pivot['Mean'].apply(grade)
    return pivot