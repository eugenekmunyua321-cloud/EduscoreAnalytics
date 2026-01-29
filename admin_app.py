import streamlit as st

# Defensive session-state defaults to avoid StreamlitAPIException where a widget
# later creates a control that owns the same key. Initialize keys before widgets
# are instantiated elsewhere in the app.
if 'open_change_admin' not in st.session_state:
	st.session_state['open_change_admin'] = False

# Admin app entrypoint placeholder. The full admin console UI lives in
# `admin_console.py`. Import or call it from here when wiring the app entry.
try:
	from admin_console import *  # noqa: F401,F403 - intentionally import to execute console
except Exception:
	# If admin_console cannot be imported, show a minimal message so the admin
	# app doesn't crash during development.
	st.write('Admin console not available. Please check admin_console.py')
