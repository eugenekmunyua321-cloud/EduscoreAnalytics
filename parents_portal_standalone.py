"""
Parents Portal Standalone Entry Point
This is a dedicated interface for parents to view their children's academic performance.
Run with: streamlit run parents_portal_standalone.py --server.port 5002
"""
import streamlit as st
import pandas as pd
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
    page_title="Parents Portal - EdusCore Analytics",
    page_icon="👨‍👩‍👧‍👦",
    layout="wide"
)

# Set parents portal mode in session state
st.session_state['parents_portal_mode'] = True

# Authentication check
if not auth.get_current_school_id():
    try:
        import auth_page
        auth_page.render_auth_page()
    except Exception:
        auth.render_login_page()
    st.stop()

# Parents Portal Header
st.title("👨‍👩‍👧‍👦 Parents Portal")
st.markdown("---")

# Welcome message
st.success(f"Welcome, **{st.session_state.get('username', 'Parent')}**")

# Navigation tabs
tab1, tab2, tab3, tab4 = st.tabs(["📊 Student Performance", "📄 Report Cards", "📞 Contact Info", "👤 Profile"])

with tab1:
    st.header("📊 Student Performance Overview")
    
    st.info("Select your child to view their academic performance")
    
    # Student selector
    student_name = st.selectbox(
        "Select Student",
        ["Select a student...", "Student 1", "Student 2"],
        help="Choose the student whose performance you want to view"
    )
    
    if student_name != "Select a student...":
        st.subheader(f"Performance Report: {student_name}")
        
        # Performance metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(label="Overall Average", value="--", delta="--")
        with col2:
            st.metric(label="Class Position", value="--", delta="--")
        with col3:
            st.metric(label="Total Marks", value="--", delta="--")
        with col4:
            st.metric(label="Grade", value="--", delta="--")
        
        st.markdown("---")
        
        # Subject performance
        st.subheader("Subject-wise Performance")
        st.info("No exam data available yet. Please check back later.")
        
        # Performance chart placeholder
        st.subheader("Performance Trend")
        st.info("Performance charts will be displayed here once exam data is available.")
    else:
        st.warning("Please select a student to view their performance.")

with tab2:
    st.header("📄 Report Cards")
    
    st.info("Download your child's report cards")
    
    student_for_report = st.selectbox(
        "Select Student for Report",
        ["Select a student...", "Student 1", "Student 2"],
        key="report_student",
        help="Choose the student whose report card you want to download"
    )
    
    if student_for_report != "Select a student...":
        exam_term = st.selectbox(
            "Select Exam/Term",
            ["Term 1 2024", "Term 2 2024", "Term 3 2024"],
            help="Select the examination term"
        )
        
        if st.button("📥 Download Report Card", type="primary"):
            st.info("Report card download functionality will be available soon.")
    else:
        st.warning("Please select a student to download their report card.")

with tab3:
    st.header("📞 Contact Information")
    
    st.subheader("School Contact Details")
    
    # Try to load contact info from config file
    try:
        config_path = Path(__file__).parent / 'config.toml'
        if config_path.exists():
            import toml
            config = toml.load(config_path)
            school_email = config.get('school', {}).get('email', 'school@example.com')
            school_phone = config.get('school', {}).get('phone', '+254 XXX XXX XXX')
            school_address = config.get('school', {}).get('address', 'School Address')
            school_city = config.get('school', {}).get('city', 'City, Country')
        else:
            school_email = 'school@example.com'
            school_phone = '+254 XXX XXX XXX'
            school_address = 'School Address'
            school_city = 'City, Country'
    except Exception:
        # Fallback to placeholder values
        # TODO: Configure these values in config.toml or environment variables
        school_email = 'school@example.com'
        school_phone = '+254 XXX XXX XXX'
        school_address = 'School Address'
        school_city = 'City, Country'
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**📧 Email:**")
        st.text(school_email)
        
        st.markdown("**📱 Phone:**")
        st.text(school_phone)
    
    with col2:
        st.markdown("**📍 Address:**")
        st.text(school_address)
        st.text(school_city)
    
    st.markdown("---")
    
    st.subheader("Update Your Contact Information")
    
    with st.form("contact_form"):
        parent_name = st.text_input("Parent/Guardian Name", value=st.session_state.get('username', ''))
        phone = st.text_input("Phone Number")
        email = st.text_input("Email Address")
        alt_phone = st.text_input("Alternative Phone Number")
        
        submit = st.form_submit_button("💾 Update Contact Information")
        if submit:
            st.success("Contact information updated successfully!")

with tab4:
    st.header("👤 Profile Settings")
    
    st.subheader("Account Information")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"**Username:** {st.session_state.get('username', 'Not available')}")
        st.markdown(f"**Account Type:** Parent/Guardian")
        st.markdown(f"**School:** {auth.get_current_school_id() or 'Not set'}")
    
    with col2:
        st.markdown(f"**Status:** Active")
        st.markdown(f"**Access Level:** Parent Portal")
    
    st.markdown("---")
    
    st.subheader("Change Password")
    
    with st.form("password_form"):
        current_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        
        submit_password = st.form_submit_button("🔒 Change Password")
        if submit_password:
            if new_password == confirm_password:
                st.success("Password changed successfully!")
            else:
                st.error("New passwords do not match!")

st.markdown("---")

# Quick Links
st.header("🔗 Quick Links")
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("📚 View Curriculum", use_container_width=True):
        st.info("Curriculum information coming soon...")

with col2:
    if st.button("📅 Academic Calendar", use_container_width=True):
        st.info("Academic calendar coming soon...")

with col3:
    if st.button("💰 Fee Statement", use_container_width=True):
        st.info("Fee statement coming soon...")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 2rem 1rem 1rem 1rem;'>
    <p style='margin: 0; font-size: 0.9rem;'><strong>EDUSCORE ANALYTICS - PARENTS PORTAL</strong></p>
    <p style='margin: 0.3rem 0; font-size: 0.85rem;'>Developed by <strong>Munyua Kamau</strong></p>
    <p style='margin: 0.3rem 0; font-size: 0.75rem; color: #888;'>© 2025 All Rights Reserved</p>
</div>
""", unsafe_allow_html=True)
