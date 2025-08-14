#import necessary libraries
# This code is for a Streamlit app that uses Google Generative AI to answer SQL queries
import streamlit as st
import google.generativeai as genai
import pyodbc
import pandas as pd
from dotenv import load_dotenv
import os
import base64
from io import BytesIO
from time import time


# Load API key from .env
# API key should be set in a .env file
# load_dotenv()
genai.configure(api_key=st.secrets["API"]["GOOGLE_API_KEY"])
# Load from secrets.toml

Credentials = st.secrets["auth"]
BI_PASSWORD = st.secrets["auth"]["BI_PASSWORD"]
BI_KEY = st.secrets["auth"]["BI_KEY"]
TRADE_PASSWORD = st.secrets["auth"]["TRADE_PASSWORD"]
TRADE_KEY = st.secrets["auth"]["TRADE_KEY"]
# gemini_API = 

# Initialize session states
if BI_KEY not in st.session_state:
    st.session_state[BI_KEY] = False
if TRADE_KEY not in st.session_state:
    st.session_state[TRADE_KEY] = False

# Authentication check
if not st.session_state[BI_KEY] and not st.session_state[TRADE_KEY]:
    st.title("🔐 Secure Access to Sanad Chatbot")
    password = st.text_input("Enter password to access", type="password")
    if st.button("Login"):
        if password == BI_PASSWORD:
            st.session_state[BI_KEY] = True
            st.rerun()
        elif password == TRADE_PASSWORD:
            st.session_state[TRADE_KEY] = True
            st.rerun()
        else:
            st.error("Incorrect password ❌")
    st.stop()

# If authenticated, proceed with the app
if st.session_state[BI_KEY]:
    st.title("💬 BI Chatbot - BI Access")
elif st.session_state[TRADE_KEY]:
    st.title("💬 BI Chatbot - Trade Access")

# Display a welcome message
st.markdown("Welcome to Our Chatbot! Ask your SQL queries and get answers in real-time.")
# Display logo at the top
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image("logoo.png", width=200)


# Function to connect to the SQL Server database

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


def Schema_description ():
# Define schema-aware base prompt
    return """
You are a SQL expert for an e-commerce database with three main tables: MP_Sales, MP_Customers, and MP_Items.
Your job is to generate valid SQL Server SELECT queries only based on user requests, following these exact rules:

Database Schema Overview:

MP_Sales (Sales Transactions)

Joins:
MP_Sales.CustomerID = MP_Customers.SITE_NUMBER
MP_Sales.ItemId = MP_Items.ITEM_CODE

Important Columns:
Date (YYYY-MM-DD) — transaction date
Netsalesvalue — sales value after tax/discounts
SalesQtyInPieces, SalesQtyInCases, order_Number
ItemId, CustomerID — for joins
Master_brand, sub_brand, brandname, Sales_Channel, itemname
project_id, company, Org_ID, InvoiceId

Rules:

Do not use month column; extract month from Date if needed.

Always round sales values using ROUND(Netsalesvalue, 0).

MP_Customers (Customer Master)

Joins: MP_Sales.CustomerID = MP_Customers.SITE_NUMBER

Important Columns:
GOVERNER_NAME, CUSTOMER_B2B_ID, CUSTOMER_NAME, SALES_CHANNEL_CODE,
SECTION_TYPE, CUSTOMER_NUMBER, CITY_NAME, AREA_NAME,
LOCATION, ADDRESS1, SITE_NUMBER, ACCOUNT_CREATION_DATE, SITE_CREATION_DATE

Rules:

Valid governorate filter: use GOVERNER_NAME.

If user asks "active customers" → customers with purchases/orders.

If user asks "active net customers" → customers with Netsalesvalue > 1.

If user says "net active" or just "active" in general → return total count only, not list.

If filtered by company or other attribute → return total count per that attribute.

MP_Items (Product Master)

Joins: MP_Sales.ItemId = MP_Items.ITEM_CODE

Important Columns:
ITEM_CODE, DESCRIPTION, MASTER_BRAND, MG2, MG3, GCOMPANY, GFORM, GSIZE, MSU, CONVERSION_RATE

Rules:

MASTER_BRAND format: code|brandname.

Brand name: RIGHT(MASTER_BRAND, LEN(MASTER_BRAND) - CHARINDEX('|', MASTER_BRAND))

Brand code: LEFT(MASTER_BRAND, CHARINDEX('|', MASTER_BRAND) - 1)

MG2 format: code|category. Extract only category name.

To filter by company:

WHERE LEFT(MASTER_BRAND, CHARINDEX('|', MASTER_BRAND) - 1) = '<first 6 digits>'


General Query Requirements:

Always use MP_Sales.Date for date filtering.

Always join to CUSTOMER_B2B_ID when query is about customers.

If a company filter is requested, match on the MASTER_BRAND code.

Extract readable brand/category names when returning them.

Task:
When I give you a natural language request, return only the SQL Server SELECT query that satisfies it, following all above schema details and business rules. Do not explain unless I ask.
    """



# Initialize session state to hold questions
if "query_boxes" not in st.session_state:
    st.session_state.query_boxes = [""]
if "query_count" not in st.session_state:
    st.session_state.query_count = 1

def add_query_box():
    st.session_state.query_boxes.append("")
    st.session_state.query_count += 1

def add_query_box():
    st.session_state.query_boxes.append("")
    st.session_state.query_count += 1
    st.session_state.results.append(None)  # add empty result slot

# Initialize session state for results if not already
if "results" not in st.session_state:
    st.session_state.results = [None] * st.session_state.query_count

# Iterate over each query box
for idx in range(st.session_state.query_count):
    with st.container():
        query_key = f"query_{idx}"
        run_key = f"run_{idx}"

        user_question = st.text_input(f"Query {idx + 1}:", key=query_key, placeholder="قولي عايز تسأل علي أي")

        if st.button(f"جرب كده", key=run_key):
            if not user_question.strip():
                st.warning("جرب شوف عايز تسأل علي أي")
            else:
                with st.spinner("هشوف واقولك..."):
                    try:
                        full_prompt = f"{Schema_description()}\n\n{user_question}"
                        model = genai.GenerativeModel("gemini-2.5-flash")
                        response = model.generate_content(full_prompt)
                        sql_query = response.text.strip().strip("```sql").strip("```")

                        df = pd.read_sql(sql_query, conn)
                        with st.expander(f"✅ Result for Query {idx + 1}"):
                            if st.session_state[BI_KEY]:
                                st.code(sql_query, language="sql")
                            else:
                                "Results are excuted "

                        # Save result in session state
                        if len(st.session_state.results) <= idx:
                            st.session_state.results.append(df)
                        else:
                            st.session_state.results[idx] = df

                    except Exception as e:
                        st.session_state.results[idx] = None
                        st.error(f"❌ Error: {e}")

        # Display previously stored result (if any)

        if idx < len(st.session_state.results) and st.session_state.results[idx] is not None:
            st.dataframe(st.session_state.results[idx])


st.button("➕ Add New Query", on_click=add_query_box)

