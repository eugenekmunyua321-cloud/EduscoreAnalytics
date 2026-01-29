"""
Small Streamlit runner to execute the `modules.home_page.render_home_page()` view directly.
Run with: streamlit run run_home_page.py
"""

import streamlit as st

# Import the module and call the render function
from modules.home_page import render_home_page

# Ensure any required session state keys exist (small safety defaults)
if 'cfg' not in st.session_state:
    st.session_state['cfg'] = {}

# Call the page renderer
render_home_page()
