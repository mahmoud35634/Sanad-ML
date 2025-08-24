import streamlit as st
import streamlit as st
import pandas as pd
import urllib
from sqlalchemy import create_engine
import gspread
from google.oauth2.service_account import Credentials


def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Call it at the start of your app
load_css("style.css")


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


BI_PASSWORD = "BI_admin"
BI_key = "auth_bi_co_item"
if BI_key not in st.session_state:
    st.session_state[BI_key] = False

if not st.session_state[BI_key]:
    st.title("🔐 Secure Access to Sanad Chatbot")
    password = st.text_input("Enter password to access", type="password")
    if st.button("Login"):
        if password == BI_PASSWORD:
            st.session_state[BI_key] = True
            st.rerun()
        else:
            st.error("Incorrect password ❌")
    st.stop()

# --- Connect to Google Sheet ---
@st.cache_resource
def connect_to_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(
        "secrets/credentials (2).json", scopes=scopes
    )
    client = gspread.authorize(creds)
    sheet_id = "1s4HCBrBf8COtP931iopwK3xICwGQx0R-MM7hYcJyTis"
    workbook = client.open_by_key(sheet_id)
    return workbook.get_worksheet(2)  # third sheet

# --- Brand list from DB ---
@st.cache_data
def get_brand_list():
    with engine.connect() as conn:
        query = """
            SELECT DISTINCT 
                RIGHT(MASTER_BRAND, LEN(MASTER_BRAND) - CHARINDEX('|', MASTER_BRAND)) AS Brand
            FROM MP_Items
            WHERE MASTER_BRAND LIKE '%|%' AND MASTER_BRAND IS NOT NULL
            ORDER BY Brand 
        """
        result = pd.read_sql(query, conn)
        return result["Brand"].dropna().unique().tolist()

brand_list = get_brand_list()
selected_brand = st.selectbox("🔍 Choose a Brand", options=brand_list)

# --- Sections from Google Sheet ---
@st.cache_data
def get_sections():
    sheet = connect_to_sheet()
    data = sheet.get_all_values()
    header = [h.strip() for h in data[0]]
    section_col = "Sction SR"
    if section_col not in header:
        st.error(f"Column '{section_col}' not found in sheet")
        return []
    col_idx = header.index(section_col)
    rows = data[1:]
    sections = sorted(set(row[col_idx].strip() for row in rows if row[col_idx].strip()))
    return sections

sections = get_sections()
selected_section = st.selectbox("📌 Select Section SR", sections)

# --- Customers for selected section ---
@st.cache_data
def get_customers_from_section(selected_section):
    sheet = connect_to_sheet()
    data = sheet.get_all_values()
    header = [h.strip() for h in data[0]]
    rows = data[1:]

    col_map = {
        "SR Name": "Sction SR",
        "SanadID": "SanadID",
        "Phone_Number": "Phone_Number",
        "Customer_Name": "Customer_Name",
        "Contact_NAME": "Contact_NAME",
        "Area": "Area",
        "City": "City",
    }

    if not all(col_map[col] in header for col in col_map):
        st.error("One or more required columns not found in sheet")
        return []

    idx = {col: header.index(col_map[col]) for col in col_map}

    filtered = [
        {
            "SanadID": row[idx["SanadID"]].strip(),
            "Phone_Number": row[idx["Phone_Number"]].strip(),
            "Customer_Name": row[idx["Customer_Name"]].strip(),
            "Contact_NAME": row[idx["Contact_NAME"]].strip(),
            "Area": row[idx["Area"]].strip(),
            "City": row[idx["City"]].strip(),
        }
        for row in rows
        if row[idx["SR Name"]].strip() == selected_section
    ]
    return filtered

customer_data = get_customers_from_section(selected_section)
customer_df = pd.DataFrame(customer_data)

st.write(f"Customers in **{selected_section}**:")
st.sidebar.write(f"Total Customers: {len(customer_df)}")

customer_df.columns = customer_df.columns.str.strip()
customer_ids = tuple(customer_df["SanadID"])

# --- Sales data for customers & brand ---
@st.cache_data
def get_customers_B2B(customer_ids, selected_brand):
    if not customer_ids:
        st.warning("No SanadID selected. Please select a SanadID to view B2B details.")
        return pd.DataFrame()

    id_list_sql = ",".join(f"'{id_}'" for id_ in customer_ids)

    with engine.connect() as conn:
        query = f"""
        SELECT 
            COUNT(DISTINCT c.Customer_B2B_ID) AS Active,
            FORMAT(SUM(s.Netsalesvalue),'N0') AS Sales,
            SUM(s.SalesQtyInCases) AS TotalQty
        FROM MP_Sales s
        LEFT JOIN MP_Customers c
            ON s.CustomerID = c.SITE_NUMBER
        LEFT JOIN MP_Items i
            ON s.ItemId = i.ITEM_CODE
        WHERE 
            s.Date >= '2025-08-01' AND s.Date < '2025-09-01'
            AND c.CUSTOMER_B2B_ID IN ({id_list_sql})
            AND i.ITEM_CODE NOT LIKE '%XE%'
            AND RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) = '{selected_brand}'
        ORDER BY Sales DESC, TotalQty DESC
        """
        df = pd.read_sql(query, conn)
        st.code(query, language="sql")

    if df.empty:
        st.warning("No data for this customer in the last 3 months.")
    return df

df_b2b = get_customers_B2B(customer_ids, selected_brand)
if not df_b2b.empty:
    st.dataframe(df_b2b, use_container_width=True)
