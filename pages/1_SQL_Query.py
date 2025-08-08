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
def connect_to_sql():
    conn = pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=web.speed.live;"
        "DATABASE=Sanad1;"
        "Trusted_Connection=yes;"
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
