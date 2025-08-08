import streamlit as st
import pandas as pd
import pyodbc


if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.warning("🔒 Please login first from the Home page.")
    st.stop()
st.title("💬 You Can Query here for Sanad Warehouse")

# SQL Server connection
@st.cache_resource
def connect_to_sql():

    secrets = st.secrets["database"]
    conn = pyodbc.connect(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={secrets['server']};"
        f"DATABASE={secrets['database']};"
        f"UID={secrets['username']};"
        f"PWD={secrets['password']};"
    )
    return conn

conn = connect_to_sql()

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
