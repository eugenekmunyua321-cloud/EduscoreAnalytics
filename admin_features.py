"""
Admin Features Entry Point
This is a dedicated admin interface for managing school operations and settings.
Run with: streamlit run admin_features.py --server.port 5001
"""
import streamlit as st
import json
from pathlib import Path

# Import authentication module
try:
    from modules import auth
except ImportError:
    st.error("Authentication module not found. Please ensure the modules directory is accessible.")
    st.stop()

# Configure page
st.set_page_config(
    page_title="Admin Features - EdusCore Analytics",
    page_icon="⚙️",
    layout="wide"
)

# Authentication check
if not auth.get_current_school_id():
    try:
        import auth_page
        auth_page.render_auth_page()
    except Exception:
        auth.render_login_page()
    st.stop()

# Check if user is admin
def is_admin_user():
    """Check if current user has admin privileges"""
    try:
        ROOT = Path(__file__).parent / 'saved_exams_storage'
        ADMINS_FILE = ROOT / 'admins.json'
        
        if ADMINS_FILE.exists():
            d = json.loads(ADMINS_FILE.read_text(encoding='utf-8') or '{}')
            admins = d.get('admins', []) if isinstance(d, dict) else []
        else:
            # WARNING: Default admin user for initial setup only
            # In production, create an admins.json file with actual admin users
            # This fallback should NOT be relied upon for production security
            admins = ['admin@local']
        
        current_user = st.session_state.get('username', '')
        email_like = f"{current_user}@local"
        return email_like in admins
    except Exception:
        return False

if not is_admin_user():
    st.error("⛔ Access Denied: Admin privileges required")
    st.info("Please contact your system administrator for access.")
    st.stop()

# Admin Dashboard Header
st.title("⚙️ Admin Features Dashboard")
st.markdown("---")

# Welcome message
st.success(f"Welcome, Administrator: **{st.session_state.get('username', 'Admin')}**")

# Admin Navigation
st.header("🎯 Admin Tools")

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("📊 School Management")
    if st.button("🏫 School Settings", use_container_width=True):
        st.info("School configuration coming soon...")
    if st.button("👥 User Management", use_container_width=True):
        st.info("User management coming soon...")
    if st.button("📚 Subject Configuration", use_container_width=True):
        st.info("Subject management coming soon...")

with col2:
    st.subheader("💬 Communication")
    if st.button("✉️ Messaging Console", use_container_width=True):
        st.info("Navigate to admin_messaging_console.py for messaging configuration")
    if st.button("📢 Announcements", use_container_width=True):
        st.info("Announcement system coming soon...")
    if st.button("📧 Email Templates", use_container_width=True):
        st.info("Email template management coming soon...")

with col3:
    st.subheader("📈 Reports & Analytics")
    if st.button("📊 Admin Reports", use_container_width=True):
        st.info("Admin reports coming soon...")
    if st.button("🔍 System Audit", use_container_width=True):
        st.info("System audit logs coming soon...")
    if st.button("📉 Performance Metrics", use_container_width=True):
        st.info("Performance metrics coming soon...")

st.markdown("---")

# Quick Stats Section
st.header("📊 Quick Statistics")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(label="Total Students", value="--", delta="--")
with col2:
    st.metric(label="Total Teachers", value="--", delta="--")
with col3:
    st.metric(label="Active Exams", value="--", delta="--")
with col4:
    st.metric(label="System Status", value="Active", delta="Normal")

st.markdown("---")

# Recent Activity
st.header("📋 Recent Activity")
st.info("No recent activity to display")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 2rem 1rem 1rem 1rem;'>
    <p style='margin: 0; font-size: 0.9rem;'><strong>EDUSCORE ANALYTICS - ADMIN PANEL</strong></p>
    <p style='margin: 0.3rem 0; font-size: 0.85rem;'>Developed by <strong>Munyua Kamau</strong></p>
    <p style='margin: 0.3rem 0; font-size: 0.75rem; color: #888;'>© 2025 All Rights Reserved</p>
</div>
""", unsafe_allow_html=True)
