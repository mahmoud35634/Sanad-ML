import streamlit as st
import pandas as pd
import pyodbc

st.title("💬 You Can Query here for Sanad Warehouse")

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
