import streamlit as st
import pandas as pd
import pyodbc

st.title("💬 You Can Query here for Sanad Warehouse")

# Authentication for BI and Trade access
# This is for the BI access
BI_PASSWORD = "BI_admin"  
BI_key = "auth_bi"


if BI_key not in st.session_state:
    st.session_state[BI_key] = False

if not st.session_state[BI_key] :
    password = st.text_input("Enter password to access", type="password")
    if st.button("Login"):
        if password == BI_PASSWORD:
            st.session_state[BI_key] = True
            st.rerun()
        else:
            st.error("Incorrect password ❌")
    st.stop()

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
