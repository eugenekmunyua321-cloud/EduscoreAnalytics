"""
Home page - main dashboard and entry point after authentication.
This file delegates to the modular home_page renderer.
"""

import streamlit as st

# Check authentication first
try:
    from modules import auth
    if not auth.get_current_school_id():
        # Not authenticated - redirect to auth page
        try:
            st.switch_page("pages/auth.py")
        except Exception:
            st.warning("Please sign in to continue.")
        st.stop()
except Exception:
    pass

# Import and render the home page module
try:
    from modules.home_page import render_home_page
    
    # Ensure session state is initialized
    if 'cfg' not in st.session_state:
        st.session_state['cfg'] = {}
    
    # Show the home header by default
    if 'show_home_header' not in st.session_state:
        st.session_state.show_home_header = True
    
    # Render the home page
    render_home_page()
    
except Exception as e:
    st.error(f"Error loading home page: {e}")
    st.info("Please contact support if this issue persists.")
