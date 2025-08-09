import streamlit as st
import pandas as pd
import urllib
from sqlalchemy import create_engine
import datetime
import gspread
from google.oauth2.service_account import Credentials

import json


SALES_CREDENTIALS = st.secrets["SALES_CREDENTIALS"]

# Get column indices (make sure these names exactly match the header)
category_col_name = "Sction SR"  
name_col_name = "SanadID"
salesman_col_name = "SR Name "
# --- Database Connection ---
db_config = st.secrets["database"]
# --- Database Connection ---
connection_string = (
        f"DRIVER={{{db_config['driver']}}};"
        f"SERVER={db_config['server']};"
        f"DATABASE={db_config['database']};"
        f"UID={db_config['username']};"
        f"PWD={db_config['password']}"
)
params = urllib.parse.quote_plus(connection_string)
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")


@st.cache_resource
def connect_to_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    client = gspread.authorize(creds)
    sheet_id = "16IxEZH4goUOiRloFhYayGhRO-K6t_aXMl8nscHdPzhc"
    workbook = client.open_by_key(sheet_id)
    sheet = workbook.get_worksheet(2)  # index 2 = 3rd sheet
    return sheet




# Sidebar login
st.sidebar.title("🔐 Salesman Login")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.salesman = None

if not st.session_state.logged_in:
    username = st.sidebar.text_input("Username")
    password = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        user_data = SALES_CREDENTIALS.get(username)
        if user_data and user_data["password"] == password:
            st.session_state.logged_in = True
            st.session_state.salesman = user_data["salesman"]
            st.sidebar.success(f"Welcome, {st.session_state.salesman}!")
        else:
            st.sidebar.error("Invalid username or password")
    st.stop()

# Use this in your app instead of manual salesman selection:
selected_salesman = st.session_state.salesman

st.title("🛍️ Past History Purchased Orders")
st.write(f"This view is restricted to **{selected_salesman}** only.")
#show the number of customers

# Step 2: Load customer info from database
@st.cache_data
def get_customers_from_salesman(selected_salesman):
    sheet = connect_to_sheet()
    data = sheet.get_all_values()
    header = data[0]
    rows = data[1:]
    sr_name_col = "SR Name "     # Note the trailing space!
    sanad_id_col = "SanadID"
    phone_col = "Phone_Number"
    Customer_Name_col ="Customer_Name"
    Contact_name_col = "Contact_NAME"

    # Check if all columns exist
    if sr_name_col in header and sanad_id_col in header and phone_col in header and Customer_Name_col in header and Contact_name_col in header:
        sr_idx = header.index(sr_name_col)
        sanad_idx = header.index(sanad_id_col)
        phone_idx = header.index(phone_col)
        customer_name_idx = header.index(Customer_Name_col)
        contact_name_idx = header.index(Contact_name_col)

        # Filter and return a list of dicts with SanadID and Phone Number
        filtered = [
            {"SanadID": row[sanad_idx], "Phone_Number": row[phone_idx]," Customer_Name": row[customer_name_idx], "Contact_NAME": row[contact_name_idx]}
            for row in rows
            if row[sr_idx].strip() == selected_salesman
        ]
        return filtered
    else:
        st.error("One or more required columns not found.")
        return []

customer_data = get_customers_from_salesman(selected_salesman)

# --- Fetch customer data ---
customer_data = get_customers_from_salesman(selected_salesman)
customer_df = pd.DataFrame(customer_data)
st.sidebar.write(f"Total Customers: {len(get_customers_from_salesman(selected_salesman))}")

# --- Strip whitespaces from column names ---
customer_df.columns = customer_df.columns.str.strip()

# --- Initialize session state ---
for key in ["selected_sanad", "selected_phone", "selected_customer_name", "selected_contact_name"]:
    if key not in st.session_state:
        st.session_state[key] = ""

# --- Sync callbacks ---
def update_from_sanad():
    sanad = st.session_state.selected_sanad
    match = customer_df[customer_df["SanadID"] == sanad]
    if not match.empty:
        row = match.iloc[0]
        st.session_state.selected_phone = row["Phone_Number"]
        st.session_state.selected_customer_name = row["Customer_Name"]
        st.session_state.selected_contact_name = row["Contact_NAME"]

def update_from_phone():
    phone = st.session_state.selected_phone
    match = customer_df[customer_df["Phone_Number"] == phone]
    if not match.empty:
        row = match.iloc[0]
        st.session_state.selected_sanad = row["SanadID"]
        st.session_state.selected_customer_name = row["Customer_Name"]
        st.session_state.selected_contact_name = row["Contact_NAME"]

def update_from_contact_name():
    contact = st.session_state.selected_contact_name
    match = customer_df[customer_df["Contact_NAME"] == contact]
    if not match.empty:
        row = match.iloc[0]
        st.session_state.selected_sanad = row["SanadID"]
        st.session_state.selected_phone = row["Phone_Number"]
        st.session_state.selected_customer_name = row["Customer_Name"]

# --- UI: Two-way selection ---
if not customer_df.empty:
    col1, col2, col3 = st.columns(3)

    with col1:
        st.selectbox(
            "🔢 Select by SanadID",
            options=[""] + customer_df["SanadID"].dropna().unique().tolist(),
            key="selected_sanad",
            on_change=update_from_sanad,
        )

    with col2:
        st.selectbox(
            "📞 Select by Phone Number",
            options=[""] + customer_df["Phone_Number"].dropna().unique().tolist(),
            key="selected_phone",
            on_change=update_from_phone,
        )

    with col3:
        st.selectbox(
            "👤 Select by Contact Name",
            options=[""] + customer_df["Contact_NAME"].dropna().unique().tolist(),
            key="selected_contact_name",
            on_change=update_from_contact_name,
        )

    # --- Show current selection ---
    if all([
        st.session_state.selected_sanad,
        st.session_state.selected_phone,
        st.session_state.selected_customer_name,
        st.session_state.selected_contact_name
    ]):
        st.success(
            f"✅ Selected: **SanadID = {st.session_state.selected_sanad}**, "
            f"**Phone = {st.session_state.selected_phone}**, "
            f"**Customer = {st.session_state.selected_customer_name}**, "
            f"**Contact = {st.session_state.selected_contact_name}**" 

        )
else:
    st.warning("No customers found for selected salesman.")


# Step 1: Load customer info from database
@st.cache_data
def get_customers_B2B(sanad_id):
    if not sanad_id:
        st.warning("No SanadID selected. Please select a SanadID to view B2B details.")

        return pd.DataFrame()  # No selection yet
    with engine.connect() as conn:
        query = f"""
        SELECT 
            c.CUSTOMER_B2B_ID as sanad_id,
            CAST(s.date AS date) AS Date,
            RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) AS Company,
            RIGHT(i.MG2, LEN(i.MG2) - CHARINDEX('|', i.MG2)) AS Category,
            i.ITEM_CODE,
            i.DESCRIPTION,
            SUM(s.Netsalesvalue) AS Sales,
            SUM(s.SalesQtyInCases) AS TotalQty
        FROM MP_Sales s
        LEFT JOIN MP_Customers c
            ON s.CustomerID = c.SITE_NUMBER
        LEFT JOIN MP_Items i
            ON s.ItemId = i.ITEM_CODE
        WHERE 
            s.Date >= '2025-05-01'
            AND c.CUSTOMER_B2B_ID = '{sanad_id}'
            AND i.ITEM_CODE NOT LIKE '%XE%'
        GROUP BY 
            c.CUSTOMER_B2B_ID,
            CAST(s.date AS date),
            RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)),
            RIGHT(i.MG2, LEN(i.MG2) - CHARINDEX('|', i.MG2)),
            i.ITEM_CODE,
            i.DESCRIPTION
        ORDER BY Sales DESC, TotalQty DESC
        """
        return pd.read_sql(query, conn)

st.sidebar.subheader("B2B Customer Details")

if st.session_state.selected_sanad:
    df_b2b = get_customers_B2B(st.session_state.selected_sanad)
    st.dataframe(df_b2b, use_container_width=True)


