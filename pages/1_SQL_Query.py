import streamlit as st
import pandas as pd
import pyodbc



def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Call it at the start of your app
load_css("style.css")
# This is for the BI access
BI_PASSWORD = st.secrets["auth"]["BI_PASSWORD"]
BI_KEY = st.secrets["auth"]["BI_KEY"]


if BI_KEY not in st.session_state:
    st.session_state[BI_KEY] = False

if not st.session_state[BI_KEY] :
    password = st.text_input("Enter password to access", type="password")
    if st.button("Login"):
        if password == BI_PASSWORD:
            st.session_state[BI_KEY] = True
            st.rerun()
        else:
            st.error("Incorrect password ❌")
    st.stop()

st.title("💬 You Can Query here for Sanad Warehouse")


# Display a welcome message
# SQL Server connection
@st.cache_resource
def connect_db():
    db_config = st.secrets["database"]
    connection_string = (
        f"DRIVER={{{db_config['driver']}}};"
        f"SERVER={db_config['server']};"
        f"DATABASE={db_config['database']};"
        f"UID={db_config['username']};"
        f"PWD={db_config['password']}"
    )
    return pyodbc.connect(connection_string)

# Usage
conn = connect_db()


query = st.text_area("Enter your SQL query:", height=150)

if st.button("Run Query"):
    if not query.strip().lower().startswith("select"):
        st.warning("❗ Only SELECT queries are allowed.")
    else:
        try:
            df = pd.read_sql(query, conn)
            st.dataframe(df)
        except Exception as e:
            st.error(f"Query failed: {e}")
