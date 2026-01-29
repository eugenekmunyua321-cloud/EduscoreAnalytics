import os
import runpy
import streamlit as st

# Attempt to execute the canonical home page from repo root or pages/
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
candidates = [
    os.path.join(repo_root, 'home.py'),
    os.path.join(repo_root, 'pages', 'home.py'),
]
for p in candidates:
    if os.path.exists(p):
        try:
            runpy.run_path(p, run_name='__main__')
        except Exception as e:
            st.exception(e)
        break
else:
    st.error('Home page not found. Expected one of: ' + ', '.join(candidates))
