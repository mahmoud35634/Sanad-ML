import streamlit as st
import pandas as pd
import urllib
from sqlalchemy import create_engine
import datetime
import gspread
from google.oauth2.service_account import Credentials
import pickle
import json
import os
import requests

@st.cache_resource
def load_content_model():
    local_path = "models/content_model.pkl"
    url = "https://github.com/mahmoud35634/Sanad-ML/releases/download/v1.0/content_model.pkl"

    if not os.path.exists(local_path):
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    with open(local_path, "rb") as f:
        model_data = pickle.load(f)

    return model_data


model_data = load_content_model()

tfidf = model_data["tfidf"]
cosine_sim = model_data["cosine_sim"]
indices = model_data["indices"]
items_df = model_data["items_df"]



# https://github.com/mahmoud35634/Sanad-ML/releases/download/v1.0/content_model.pkl

def recommend_similar_items(item_code, num_recommendations=5):
    """Recommend items similar to the given item_code using cosine similarity."""
    if item_code not in indices:
        return pd.DataFrame(columns=["ITEM_CODE", "DESCRIPTION", "brand", "category"])
    
    idx = indices[item_code]
    sim_scores = list(enumerate(cosine_sim[idx]))
    sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)
    sim_scores = sim_scores[1:num_recommendations+1]  # skip self

    item_indices = [i[0] for i in sim_scores]
    recs = items_df.iloc[item_indices][["ITEM_CODE", "DESCRIPTION", "brand", "category"]].copy()
    recs["similarity_score"] = [round(i[1], 3) for i in sim_scores]
    return recs


def recommend_for_customer_content(sanad_id, num_recommendations=5):
    df_b2b,summary_df = get_customers_B2B(sanad_id)
    if df_b2b.empty:
        return pd.DataFrame(columns=["ITEM_CODE", "DESCRIPTION", "brand", "category"])
    
    recs = pd.DataFrame()

    for item_code in df_b2b["ITEM_CODE"].unique():
        similar_items = recommend_similar_items(item_code, num_recommendations=10)  # more candidates
        recs = pd.concat([recs, similar_items])

    recs = recs[~recs["ITEM_CODE"].isin(df_b2b["ITEM_CODE"].unique())]
    recs = recs.drop_duplicates(subset=["ITEM_CODE"])

    # Diversification
    diverse_list = []
    seen_categories = set()
    for _, row in recs.iterrows():
        if row["category"] not in seen_categories:
            diverse_list.append(row.to_dict())  # ensure dict format
            seen_categories.add(row["category"])
        if len(diverse_list) >= num_recommendations:
            break
    
    if len(diverse_list) < num_recommendations:
        remaining = recs[~recs["ITEM_CODE"].isin([r["ITEM_CODE"] for r in diverse_list])]
        extra_needed = num_recommendations - len(diverse_list)
        diverse_list.extend(remaining.head(extra_needed).to_dict("records"))

    return pd.DataFrame(diverse_list)


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
    sheet_id = "13YWnjeLIKjno8-klspJoBtgQ9uAOdSFda8nQx0rlINs"
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
            st.rerun()  # <--- This forces the app to jump directly into the main page
        else:
            st.sidebar.error("Invalid username or password")
    
    st.stop()  # Prevents loading the main page until logged in
# Use this in your app instead of manual salesman selection:
selected_salesman = st.session_state.salesman

st.title("🛍️ Past 3 Months History Purchased Orders")
st.write(f"This view is restricted to **{selected_salesman}** only.")
#show the number of customers
@st.cache_data
def get_customers_from_salesman(selected_salesman):
    sheet = connect_to_sheet()
    data = sheet.get_all_values()
    header = [h.strip() for h in data[0]]  # strip all header spaces
    rows = data[1:]

    sr_name_col = "SR Name"
    sanad_id_col = "SanadID"
    phone_col = "Phone_Number"
    customer_name_col = "Customer_Name"
    contact_name_col = "Contact_NAME"
    governer_name_col = "Area"
    city_name_col = "City"

    # Ensure required columns exist
    required_cols = [sr_name_col, sanad_id_col, phone_col, customer_name_col,
                     contact_name_col, governer_name_col, city_name_col]
    if not all(col in header for col in required_cols):
        st.error("One or more required columns not found.")
        return []

    col_idx = {col: header.index(col) for col in required_cols}

    filtered = [
        {
            "SanadID": row[col_idx[sanad_id_col]].strip(),
            "Phone_Number": row[col_idx[phone_col]].strip(),
            "Customer_Name": row[col_idx[customer_name_col]].strip(),
            "Contact_NAME": row[col_idx[contact_name_col]].strip(),
            "Area": row[col_idx[governer_name_col]].strip(),
            "City": row[col_idx[city_name_col]].strip(),
        }
        for row in rows
        if row[col_idx[sr_name_col]].strip() == selected_salesman
    ]
    return filtered



# --- Fetch customer data ---
customer_data = get_customers_from_salesman(selected_salesman)
customer_df = pd.DataFrame(customer_data)
st.sidebar.write(f"Total Customers: {len(get_customers_from_salesman(selected_salesman))}")

# --- Strip whitespaces from column names ---
customer_df.columns = customer_df.columns.str.strip()

# --- Initialize session state ---
for key in ["selected_sanad", "selected_phone", "selected_customer_name", "selected_contact_name","selected_Area","selected_City"]:
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
        st.session_state.selected_Area = row["Area"]
        st.session_state.selected_City = row["City"]

def update_from_phone():
    phone = st.session_state.selected_phone
    match = customer_df[customer_df["Phone_Number"] == phone]
    if not match.empty:
        row = match.iloc[0]
        st.session_state.selected_sanad = row["SanadID"]
        st.session_state.selected_customer_name = row["Customer_Name"]
        st.session_state.selected_contact_name = row["Contact_NAME"]
        st.session_state.selected_Area = row["Area"]
        st.session_state.selected_City = row["City"]

def update_from_contact_name():
    contact = st.session_state.selected_contact_name
    match = customer_df[customer_df["Contact_NAME"] == contact]
    if not match.empty:
        row = match.iloc[0]
        st.session_state.selected_sanad = row["SanadID"]
        st.session_state.selected_phone = row["Phone_Number"]
        st.session_state.selected_customer_name = row["Customer_Name"]
        st.session_state.selected_Area = row["Area"]
        st.session_state.selected_City = row["City"]



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
        st.session_state.selected_contact_name,
        st.session_state.selected_Area,
        st.session_state.selected_City
        
    ]):
        st.success(
            f"✅ Selected: **SanadID = {st.session_state.selected_sanad}**, "
            f"**Phone = {st.session_state.selected_phone}**, "
            f"**Customer = {st.session_state.selected_customer_name}**, "
            f"**Contact = {st.session_state.selected_contact_name}**," 
            f"**Contact = {st.session_state.selected_Area}**," 
            f"**Contact = {st.session_state.selected_City}**," 


        )
else:
    st.warning("No customers found for selected salesman.")


# Step 1: Load customer info from database
@st.cache_data

def get_customers_B2B(sanad_id):
    if not sanad_id:
        st.warning("No SanadID selected. Please select a SanadID to view B2B details.")
        return pd.DataFrame()

    with engine.connect() as conn:
        query = f"""
        SELECT 
            FORMAT(S.Date , 'MMM-yyyy') as Date,
             i.ITEM_CODE,
            i.DESCRIPTION,
            RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) AS Company,
            RIGHT(i.MG2, LEN(i.MG2) - CHARINDEX('|', i.MG2)) AS Category,
            ROUND(sum(s.Netsalesvalue),0) as sales,
            SUM(s.SalesQtyInCases) AS TotalQty
        FROM MP_Sales s
        LEFT JOIN MP_Customers c
            ON s.CustomerID = c.SITE_NUMBER
        LEFT JOIN MP_Items i
            ON s.ItemId = i.ITEM_CODE
        WHERE 
    s.Date >= DATEADD(MONTH, -3, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1))
    AND s.Date < DATEADD(MONTH, 1, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1))
            AND c.CUSTOMER_B2B_ID = '{sanad_id}'
            AND i.ITEM_CODE NOT LIKE '%XE%'
        GROUP BY 
             FORMAT(S.Date , 'MMM-yyyy') ,
            RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)),
            RIGHT(i.MG2, LEN(i.MG2) - CHARINDEX('|', i.MG2)),
            i.ITEM_CODE,
            i.DESCRIPTION
        ORDER BY 
        sales DESC
        """


        summary_query  = f"""

SELECT 
    MAX(CAST(s.Date AS DATE)) AS LastPurchasedDate,
    MIN(CAST(s.Date AS DATE)) AS FirstPurchasedDate,
    FORMAT(SUM(s.Netsalesvalue), 'N0') AS Sales,
    SUM(s.SalesQtyInCases) AS TotalQty,
    COUNT(DISTINCT CAST(s.Date AS DATE)) AS PurchaseTimes,
    CASE 
        WHEN COUNT(DISTINCT CAST(s.Date AS DATE)) > 1 
        THEN DATEDIFF(
                DAY, 
                MIN(CAST(s.Date AS DATE)), 
                MAX(CAST(s.Date AS DATE))
             ) 
        ELSE NULL 
    END AS AvgDaysBetweenPurchases
FROM MP_Sales s
LEFT JOIN MP_Customers c
    ON s.CustomerID = c.SITE_NUMBER
LEFT JOIN MP_Items i
    ON s.ItemId = i.ITEM_CODE
WHERE 
    s.Date >= DATEADD(MONTH, -3, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1))
    AND s.Date < DATEADD(MONTH, 1, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1))
    AND c.CUSTOMER_B2B_ID = '{sanad_id}'
    AND i.ITEM_CODE NOT LIKE '%XE%'

        """

        df = pd.read_sql(query, conn)
        summary_df = pd.read_sql(summary_query, conn)

    if df.empty:
        st.warning("No data for this customer in the last 3 months.")
    return df , summary_df


st.sidebar.subheader("B2B Customer Details")

if st.session_state.selected_sanad:
    df_b2b,df_summary = get_customers_B2B(st.session_state.selected_sanad)
    if not df_b2b.empty:
        st.dataframe(df_b2b, use_container_width=True)
        st.subheader("There is summary details")
        st.dataframe(df_summary, use_container_width=True)
    else:
        st.info("Please select a SanadID to view B2B details.")

    


# --- Sidebar logout ---
if st.sidebar.button("🚪 Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

st.header("There is the Recommendation Section")
top_n = st.slider("Number of Recommendations", 1, 20, 5)


if st.button("📄 Show Content-Based Recommendations") and st.session_state.selected_sanad.strip() != "":
    content_recs = recommend_for_customer_content(st.session_state.selected_sanad, num_recommendations=top_n)
    if not content_recs.empty:
        st.success(f"Top {top_n} Content-Based Recommendations for Customer ID: {st.session_state.selected_sanad}")
        st.dataframe(content_recs.reset_index(drop=True))
    else:
        st.warning("No content-based recommendations found.")



