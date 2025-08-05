# app.py
import streamlit as st



st.set_page_config(page_title="Sanad Analytics", layout="centered")
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image("logo.png", width=200)
st.title("📊 Sanad Analytics Toolkit")
st.subheader("Welcome to the Sanad Analytics Toolkit! Choose a tool from the sidebar to get started.")
st.markdown(
    "<div style='font-size:22px;'> - 💬<b>SQL Server </b> if you want to query here<br>- 💬 <b>SQL Chatbot</b> to ask database questions using natural language.<br>- 🛒 <b>Product Recommender</b> for item-based recommendations.</div>",
    unsafe_allow_html=True
)

