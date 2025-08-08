import streamlit as st

# Initialize session state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None
if "role" not in st.session_state:
    st.session_state.role = None

# Function to handle login
def login(username, password):
    users = st.secrets["users"]
    if username in users and users[username]["password"] == password:
        st.session_state.logged_in = True
        st.session_state.username = username
        st.session_state.role = users[username]["role"]
    else:
        st.error("Invalid username or password")

# Show login form if not logged in
if not st.session_state.logged_in:
    st.title("🔐 Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        login(username, password)
    st.stop()

# App content after login
st.sidebar.success(f"Logged in as: {st.session_state.username} ({st.session_state.role})")
st.title("Welcome to Sanad App")

# Role-based content
if st.session_state.role == "admin":
    st.subheader("Admin Dashboard")
    st.write("This is admin-only content.")
    # ... show admin features here ...
elif st.session_state.role == "viewer":
    st.subheader("Viewer Page")
    st.write("This is a limited-access view.")
    # ... show viewer features here ...
else:
    st.warning("Unknown role.")
