# If the user is signed in, show the Home page immediately
if auth.get_current_school_id():
    from modules.home_page import render_home_page
    render_home_page()
    st.stop()