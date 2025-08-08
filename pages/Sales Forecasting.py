import streamlit as st
import pickle
import pandas as pd




# Future work
#display Coming Soon for sales forecasting model based time series
st.set_page_config(
    page_title="Sales Forecasting Model",
    page_icon="📈",
    layout="centered"
)
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image("logo.png", width=300)
st.title("📈 Sales Forecasting Model")
st.subheader("This page is under construction. Stay tuned for updates on our sales forecasting model based on time series analysis.")
st.write("For now, you can explore the [Product Recommender for Alex Customers](./user_recommendation) page for personalized product recommendations.")
