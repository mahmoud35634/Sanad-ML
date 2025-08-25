import streamlit as st
import pandas as pd
import urllib
from sqlalchemy import create_engine, text
import datetime
import gspread
from google.oauth2.service_account import Credentials
import pickle
import json
import os
import requests
from functools import lru_cache


# Function to load and inject CSS
def load_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass  # Ignore if CSS file doesn't exist

# Call it at the start of your app
load_css("style.css")


@st.cache_resource
def load_content_model():
    """Load content model with caching and auto-download"""
    local_path = "models/content_model.pkl"
    url = "https://github.com/mahmoud35634/Sanad-ML/releases/download/v1.0/content_model.pkl"

    if not os.path.exists(local_path):
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with st.spinner("Downloading content model..."):
            response = requests.get(url, stream=True)
            response.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

    with open(local_path, "rb") as f:
        model_data = pickle.load(f)

    return model_data


@st.cache_resource
def get_database_engine():
    """Create database engine with caching"""
    db_config = st.secrets["database"]
    connection_string = (
        f"DRIVER={{{db_config['driver']}}};"
        f"SERVER={db_config['server']};"
        f"DATABASE={db_config['database']};"
        f"UID={db_config['username']};"
        f"PWD={db_config['password']}"
    )
    params = urllib.parse.quote_plus(connection_string)
    return create_engine(f"mssql+pyodbc:///?odbc_connect={params}")


@st.cache_resource
def connect_to_sheet():
    """Connect to Google Sheet with caching"""
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    client = gspread.authorize(creds)
    sheet_id = "1s4HCBrBf8COtP931iopwK3xICwGQx0R-MM7hYcJyTis"
    workbook = client.open_by_key(sheet_id)
    sheet = workbook.get_worksheet(2)
    return sheet


# Load models and credentials once
model_data = load_content_model()
tfidf = model_data["tfidf"]
cosine_sim = model_data["cosine_sim"]
indices = model_data["indices"]
items_df = model_data["items_df"]
SALES_CREDENTIALS = st.secrets["SALES_CREDENTIALS"]
engine = get_database_engine()


@lru_cache(maxsize=64)
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
    """Generate content-based recommendations"""
    df_b2b, summary_df = get_customers_B2B(sanad_id)
    if df_b2b.empty:
        return pd.DataFrame(columns=["ITEM_CODE", "DESCRIPTION", "brand", "category"])
    
    recs = pd.DataFrame()

    for item_code in df_b2b["ITEM_CODE"].unique():
        similar_items = recommend_similar_items(item_code, num_recommendations=10)
        recs = pd.concat([recs, similar_items])

    recs = recs[~recs["ITEM_CODE"].isin(df_b2b["ITEM_CODE"].unique())]
    recs = recs.drop_duplicates(subset=["ITEM_CODE"])

    # Diversification
    diverse_list = []
    seen_categories = set()
    for _, row in recs.iterrows():
        if row["category"] not in seen_categories:
            diverse_list.append(row.to_dict())
            seen_categories.add(row["category"])
        if len(diverse_list) >= num_recommendations:
            break
    
    if len(diverse_list) < num_recommendations:
        remaining = recs[~recs["ITEM_CODE"].isin([r["ITEM_CODE"] for r in diverse_list])]
        extra_needed = num_recommendations - len(diverse_list)
        diverse_list.extend(remaining.head(extra_needed).to_dict("records"))

    return pd.DataFrame(diverse_list)


@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_customers_from_salesman(selected_salesman):
    """Get customers from Google Sheet with caching"""
    sheet = connect_to_sheet()
    data = sheet.get_all_values()
    header = [h.strip() for h in data[0]]
    rows = data[1:]

    sr_name_col = "SR Name"
    sanad_id_col = "SanadID"
    phone_col = "Phone_Number"
    customer_name_col = "Customer_Name"
    contact_name_col = "Contact_NAME"
    governer_name_col = "Area"
    city_name_col = "City"

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


@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_customers_B2B(sanad_id):
    """Get B2B customer data for last 3 months with caching - Modified to show totals without monthly grouping"""
    if not sanad_id:
        return pd.DataFrame(), pd.DataFrame()

    with engine.connect() as conn:
        # Modified main query - removed FORMAT(S.Date, 'MMM-yyyy') from SELECT and GROUP BY
        query = text(f"""
        SELECT 
            i.ITEM_CODE,
            i.DESCRIPTION,
            RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) AS Company,
            RIGHT(i.MG2, LEN(i.MG2) - CHARINDEX('|', i.MG2)) AS Category,
            ROUND(SUM(s.Netsalesvalue), 0) as sales,
            SUM(s.SalesQtyInCases) AS TotalQty
        FROM MP_Sales s
        LEFT JOIN MP_Customers c ON s.CustomerID = c.SITE_NUMBER
        LEFT JOIN MP_Items i ON s.ItemId = i.ITEM_CODE
        WHERE 
            s.Date >= DATEADD(MONTH, -3, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1))
            AND s.Date < DATEADD(MONTH, 0, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1))
            AND c.CUSTOMER_B2B_ID = '{sanad_id}'
            AND i.ITEM_CODE NOT LIKE '%XE%'
        GROUP BY 
            RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)),
            RIGHT(i.MG2, LEN(i.MG2) - CHARINDEX('|', i.MG2)),
            i.ITEM_CODE,
            i.DESCRIPTION
        ORDER BY sales DESC
        """)

        # Summary query remains the same
        summary_query = text(f"""
        SELECT 
            MAX(CAST(s.Date AS DATE)) AS LastPurchasedDate,
            MIN(CAST(s.Date AS DATE)) AS FirstPurchasedDate,
            FORMAT(SUM(s.Netsalesvalue), 'N0') AS Sales,
            ROUND(SUM(s.SalesQtyInCases), 0) AS TotalQty,
            COUNT(DISTINCT CAST(s.Date AS DATE)) AS PurchaseTimes,
            CASE 
                WHEN COUNT(DISTINCT CAST(s.Date AS DATE)) > 1 
                THEN (DATEDIFF(
                        DAY, 
                        MIN(CAST(s.Date AS DATE)), 
                        MAX(CAST(s.Date AS DATE))
                     ) / COUNT(DISTINCT CAST(s.Date AS DATE)))
                ELSE NULL 
            END AS AvgDaysBetweenPurchases
        FROM MP_Sales s
        LEFT JOIN MP_Customers c ON s.CustomerID = c.SITE_NUMBER
        LEFT JOIN MP_Items i ON s.ItemId = i.ITEM_CODE
        WHERE 
            s.Date >= DATEADD(MONTH, -3, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1))
            AND s.Date < DATEADD(MONTH, 0, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1))
            AND c.CUSTOMER_B2B_ID = '{sanad_id}'
            AND i.ITEM_CODE NOT LIKE '%XE%'
        """)

        df = pd.read_sql(query, conn)
        summary_df = pd.read_sql(summary_query, conn)

    return df, summary_df


@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_current_month_data(sanad_id):
    """Get current month data"""
    if not sanad_id:
        return pd.DataFrame(), pd.DataFrame()

    with engine.connect() as conn:
        # Current month query
        query = text(f"""
        SELECT 
            cast(S.Date as date) as Date,
            i.ITEM_CODE,
            i.DESCRIPTION,
            RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) AS Company,
            RIGHT(i.MG2, LEN(i.MG2) - CHARINDEX('|', i.MG2)) AS Category,
            ROUND(SUM(s.Netsalesvalue), 0) as sales,
            SUM(s.SalesQtyInCases) AS TotalQty
        FROM MP_Sales s
        LEFT JOIN MP_Customers c ON s.CustomerID = c.SITE_NUMBER
        LEFT JOIN MP_Items i ON s.ItemId = i.ITEM_CODE
        WHERE 
            s.Date >= DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)
            AND s.Date < DATEADD(MONTH, 1, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1))
            AND c.CUSTOMER_B2B_ID = '{sanad_id}'
            AND i.ITEM_CODE NOT LIKE '%XE%'
        GROUP BY 
            cast(S.Date as date),
            RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)),
            RIGHT(i.MG2, LEN(i.MG2) - CHARINDEX('|', i.MG2)),
            i.ITEM_CODE,
            i.DESCRIPTION
        ORDER BY Date DESC, sales DESC
        """)

        # Current month summary
        summary_query = text(f"""
        SELECT 
            FORMAT(DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1), 'MMM-yyyy') AS Month,
            FORMAT(SUM(s.Netsalesvalue), 'N0') AS Sales,
            ROUND(SUM(s.SalesQtyInCases), 0) AS TotalQty,
            COUNT(DISTINCT CAST(s.Date AS DATE)) AS PurchaseDays,
            COUNT(DISTINCT i.ITEM_CODE) AS UniqueItems
        FROM MP_Sales s
        LEFT JOIN MP_Customers c ON s.CustomerID = c.SITE_NUMBER
        LEFT JOIN MP_Items i ON s.ItemId = i.ITEM_CODE
        WHERE 
            s.Date >= DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)
            AND s.Date < DATEADD(MONTH, 1, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1))
            AND c.CUSTOMER_B2B_ID = '{sanad_id}'
            AND i.ITEM_CODE NOT LIKE '%XE%'
        """)

        df = pd.read_sql(query, conn)
        summary_df = pd.read_sql(summary_query, conn)

    return df, summary_df


@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_last_month_data(sanad_id):
    """Get last month data"""
    if not sanad_id:
        return pd.DataFrame(), pd.DataFrame()

    with engine.connect() as conn:
        # Last month query
        query = text(f"""
        SELECT 
            cast(S.Date as date) as Date,
            i.ITEM_CODE,
            i.DESCRIPTION,
            RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) AS Company,
            RIGHT(i.MG2, LEN(i.MG2) - CHARINDEX('|', i.MG2)) AS Category,
            ROUND(SUM(s.Netsalesvalue), 0) as sales,
            SUM(s.SalesQtyInCases) AS TotalQty
        FROM MP_Sales s
        LEFT JOIN MP_Customers c ON s.CustomerID = c.SITE_NUMBER
        LEFT JOIN MP_Items i ON s.ItemId = i.ITEM_CODE
        WHERE 
            s.Date >= DATEADD(MONTH, -1, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1))
            AND s.Date < DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)
            AND c.CUSTOMER_B2B_ID = '{sanad_id}'
            AND i.ITEM_CODE NOT LIKE '%XE%'
        GROUP BY 
            cast(S.Date as date),
            RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)),
            RIGHT(i.MG2, LEN(i.MG2) - CHARINDEX('|', i.MG2)),
            i.ITEM_CODE,
            i.DESCRIPTION
        ORDER BY Date  DESC, sales DESC
        """)

        # Last month summary
        summary_query = text(f"""
        SELECT 
            FORMAT(DATEADD(MONTH, -1, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)), 'MMM-yyyy') AS Month,
            FORMAT(SUM(s.Netsalesvalue), 'N0') AS Sales,
            ROUND(SUM(s.SalesQtyInCases), 0) AS TotalQty,
            COUNT(DISTINCT CAST(s.Date AS DATE)) AS PurchaseDays,
            COUNT(DISTINCT i.ITEM_CODE) AS UniqueItems
        FROM MP_Sales s
        LEFT JOIN MP_Customers c ON s.CustomerID = c.SITE_NUMBER
        LEFT JOIN MP_Items i ON s.ItemId = i.ITEM_CODE
        WHERE 
            s.Date >= DATEADD(MONTH, -1, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1))
            AND s.Date < DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)
            AND c.CUSTOMER_B2B_ID = '{sanad_id}'
            AND i.ITEM_CODE NOT LIKE '%XE%'
        """)

        df = pd.read_sql(query, conn)
        summary_df = pd.read_sql(summary_query, conn)

    return df, summary_df


@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_two_months_ago_data(sanad_id):
    """Get two months ago data"""
    if not sanad_id:
        return pd.DataFrame(), pd.DataFrame()

    with engine.connect() as conn:
        # Two months ago query
        query = text(f"""
SELECT 
    cast(S.Date as date)  as Date,
    i.ITEM_CODE,
    i.DESCRIPTION,
    RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) AS Company,
    RIGHT(i.MG2, LEN(i.MG2) - CHARINDEX('|', i.MG2)) AS Category,
    ROUND(SUM(s.Netsalesvalue), 0) as sales,
    SUM(s.SalesQtyInCases) AS TotalQty
FROM MP_Sales s
LEFT JOIN MP_Customers c ON s.CustomerID = c.SITE_NUMBER
LEFT JOIN MP_Items i ON s.ItemId = i.ITEM_CODE
WHERE 
    s.Date >= DATEADD(MONTH, -3, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)) -- May 1
    AND s.Date < DATEADD(MONTH, -1, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)) -- before July 1
    AND c.CUSTOMER_B2B_ID = '{sanad_id}'
    AND i.ITEM_CODE NOT LIKE '%XE%'
GROUP BY 
    cast(S.Date as date) ,
    RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)),
    RIGHT(i.MG2, LEN(i.MG2) - CHARINDEX('|', i.MG2)),
    i.ITEM_CODE,
    i.DESCRIPTION
ORDER BY Date DESC, sales DESC;

        """)

        # Two months ago summary
        summary_query = text(f"""
SELECT 
    Format(s.Date , 'MMM-yyyy') as  Month,
    FORMAT(SUM(s.Netsalesvalue), 'N0') AS Sales,
    ROUND(SUM(s.SalesQtyInCases), 0) AS TotalQty,
    COUNT(DISTINCT CAST(s.Date AS DATE)) AS PurchaseDays,
    COUNT(DISTINCT i.ITEM_CODE) AS UniqueItems
FROM MP_Sales s
LEFT JOIN MP_Customers c ON s.CustomerID = c.SITE_NUMBER
LEFT JOIN MP_Items i ON s.ItemId = i.ITEM_CODE
WHERE 
    s.Date >= DATEADD(MONTH, -3, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)) -- May 1
    AND s.Date < DATEADD(MONTH, -1, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)) -- before July 1
    AND c.CUSTOMER_B2B_ID = '{sanad_id}'
    AND i.ITEM_CODE NOT LIKE '%XE%'
GROUP BY Format(s.Date , 'MMM-yyyy') 
ORDER BY MAX(S.Date);

        """)

        df = pd.read_sql(query, conn)
        summary_df = pd.read_sql(summary_query, conn)

    return df, summary_df


def get_month_name(offset):
    """Get month name based on offset"""
    current_date = datetime.datetime.now()
    target_date = current_date + datetime.timedelta(days=30 * offset)
    return target_date.strftime("%B %Y")


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
            st.rerun()
        else:
            st.sidebar.error("Invalid username or password")
    
    st.stop()

# Main app
selected_salesman = st.session_state.salesman

st.title("🛍️ Customer Sales History & Recommendations")
st.write(f"This view is restricted to **{selected_salesman}** only.")

# Fetch customer data
customer_data = get_customers_from_salesman(selected_salesman)
customer_df = pd.DataFrame(customer_data)
st.sidebar.write(f"Total Customers: {len(customer_data)}")

if not customer_df.empty:
    customer_df.columns = customer_df.columns.str.strip()

# Initialize session state
for key in ["selected_sanad", "selected_phone", "selected_customer_name", 
            "selected_contact_name", "selected_Area", "selected_City"]:
    if key not in st.session_state:
        st.session_state[key] = ""

# Sync callbacks
def update_from_sanad():
    sanad = st.session_state.selected_sanad
    if not customer_df.empty:
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
    if not customer_df.empty:
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
    if not customer_df.empty:
        match = customer_df[customer_df["Contact_NAME"] == contact]
        if not match.empty:
            row = match.iloc[0]
            st.session_state.selected_sanad = row["SanadID"]
            st.session_state.selected_phone = row["Phone_Number"]
            st.session_state.selected_customer_name = row["Customer_Name"]
            st.session_state.selected_Area = row["Area"]
            st.session_state.selected_City = row["City"]

# UI: Customer selection
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

    # Show current selection
    if all([st.session_state.selected_sanad, st.session_state.selected_phone, 
            st.session_state.selected_customer_name, st.session_state.selected_contact_name,
            st.session_state.selected_Area, st.session_state.selected_City]):
        st.success(
            f"✅ Selected: **SanadID = {st.session_state.selected_sanad}**, "
            f"**Phone = {st.session_state.selected_phone}**, "
            f"**Customer = {st.session_state.selected_customer_name}**, "
            f"**Contact = {st.session_state.selected_contact_name}**, "
            f"**Area = {st.session_state.selected_Area}**, "
            f"**City = {st.session_state.selected_City}**"
        )
else:
    st.warning("No customers found for selected salesman.")

# Main data display
if st.session_state.selected_sanad:
    # Create two columns for main view and monthly details
    main_col, detail_col = st.columns([2, 1])
    
    with main_col:
        st.subheader("📊 Last 3 Months Summary (Total by Items)")
        with st.spinner("Loading customer data..."):
            df_b2b, df_summary = get_customers_B2B(st.session_state.selected_sanad)
            
        if not df_b2b.empty:
            st.dataframe(df_b2b, use_container_width=True)
            st.subheader("📈 Summary Details")
            st.dataframe(df_summary, use_container_width=True)
        else:
            st.info("No data found for the last 3 months.")
    
    with detail_col:
        st.subheader("🗓️ Monthly Details")
        
        # Three independent buttons for monthly data
        if st.button("📅 Current Month", key="current_month_btn"):
            with st.spinner("Loading current month data..."):
                monthly_df, monthly_summary = get_current_month_data(st.session_state.selected_sanad)
                
            if not monthly_df.empty:
                st.subheader("📋 Current Month Data")
                st.dataframe(monthly_df, use_container_width=True, height=300)
                
                st.subheader("📊 Current Month Summary")
                st.dataframe(monthly_summary, use_container_width=True)
            else:
                st.warning("No data found for current month.")
        
        if st.button("📅 Last Month", key="last_month_btn"):
            with st.spinner("Loading last month data..."):
                monthly_df, monthly_summary = get_last_month_data(st.session_state.selected_sanad)
                
            if not monthly_df.empty:
                st.subheader("📋 Last Month Data")
                st.dataframe(monthly_df, use_container_width=True, height=300)
                
                st.subheader("📊 Last Month Summary")
                st.dataframe(monthly_summary, use_container_width=True)
            else:
                st.warning("No data found for last month.")
        
        if st.button("📅 2 Months Ago", key="two_months_ago_btn"):
            with st.spinner("Loading 2 months ago data..."):
                monthly_df, monthly_summary = get_two_months_ago_data(st.session_state.selected_sanad)
                
            if not monthly_df.empty:
                st.subheader("📋 2 Months Ago Data")
                st.dataframe(monthly_df, use_container_width=True, height=300)
                
                st.subheader("📊 2 Months Ago Summary")
                st.dataframe(monthly_summary, use_container_width=True)
            else:
                st.warning("No data found for 2 months ago.")

else:
    st.info("Please select a customer to view sales data.")

# Sidebar logout
if st.sidebar.button("🚪 Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# Recommendations Section
st.header("🎯 Recommendation Section")

if st.session_state.selected_sanad:
    
    top_n = st.slider("Number of Recommendations", 1, 20, 5)

    if st.button("📄 Show Content-Based Recommendations", type="primary"):
        with st.spinner("Generating recommendations..."):
            try:
                content_recs = recommend_for_customer_content(
                    st.session_state.selected_sanad, 
                    num_recommendations=top_n
                )
                if not content_recs.empty:
                    st.success(f"Top {top_n} Content-Based Recommendations for Customer ID: {st.session_state.selected_sanad}")
                    st.dataframe(content_recs.reset_index(drop=True), use_container_width=True)
                else:
                    st.warning("No content-based recommendations found.")
            except Exception as e:
                st.error(f"Error generating recommendations: {str(e)}")
else:
    st.info("Please select a customer to view recommendations.")