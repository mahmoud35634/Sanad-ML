import streamlit as st
import pandas as pd
import urllib
from sqlalchemy import create_engine
import datetime

# --- Database Connection ---
connection_string = (

        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=web.speed.live;"
        "DATABASE=Sanad1;"
        "UID=gdatastudio;"       # ← Replace with actual username
        "PWD=Z2RhdGFzdHVkaW8=;"       # ← Replace with actual password

)
params = urllib.parse.quote_plus(connection_string)
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")
# --- UI ---
st.title("🛍️ Co-Purchased Items by Brand")

# Step 1: Load brand & governorate lists
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

@st.cache_data
def get_govermant_list():
    with engine.connect() as conn:
        query = "SELECT DISTINCT GOVERNER_NAME FROM MP_Customers"
        result = pd.read_sql(query, conn)
        return result["GOVERNER_NAME"].dropna().unique().tolist()

brand_list = get_brand_list()
governer_list = get_govermant_list()

# Step 2: UI components
selected_brand = st.selectbox("🔍Choose a Brand", options=brand_list)
selected_governerment = st.selectbox("🏙️ (Optional) Choose a Governorate", options=[""] + governer_list)

# Step 3: Date range input (up to today)
date_range = st.date_input(
    "📆 Select Date Range",
    value=(datetime.date(2023, 1, 1), datetime.date.today()),
    min_value=datetime.date(2023, 1, 1),
    max_value=datetime.date.today()
)

# --- Get item list for selected brand ---
def get_items_for_brand(brand):
    with engine.connect() as conn:
        query = f"""
            SELECT DISTINCT ITEM_CODE, DESCRIPTION 
            FROM MP_Items  
            WHERE RIGHT(MASTER_BRAND, LEN(MASTER_BRAND) - CHARINDEX('|', MASTER_BRAND)) = '{brand}'
        """
        return pd.read_sql(query, conn)

# Load items for selected brand
items_list_df = get_items_for_brand(selected_brand) if selected_brand else pd.DataFrame(columns=["ITEM_CODE", "DESCRIPTION"])

# --- Initialize session state ---
if "selected_code" not in st.session_state:
    st.session_state.selected_code = ""
if "selected_description" not in st.session_state:
    st.session_state.selected_description = ""

# --- Sync Callbacks ---
def update_description():
    code = st.session_state.selected_code
    match = items_list_df[items_list_df["ITEM_CODE"] == code]
    if not match.empty:
        st.session_state.selected_description = match["DESCRIPTION"].values[0]
    else:
        st.session_state.selected_description = ""

def update_code():
    desc = st.session_state.selected_description
    match = items_list_df[items_list_df["DESCRIPTION"] == desc]
    if not match.empty:
        st.session_state.selected_code = match["ITEM_CODE"].values[0]
    else:
        st.session_state.selected_code = ""

# --- UI: Two-way selection ---
col1, col2 = st.columns(2)

with col1:
    st.selectbox(
        "🔢 Select by Item Code",
        options=[""] + items_list_df["ITEM_CODE"].tolist(),
        key="selected_code",
        on_change=update_description
    )

with col2:
    st.selectbox(
        "📝 Select by Description",
        options=[""] + items_list_df["DESCRIPTION"].tolist(),
        key="selected_description",
        on_change=update_code
    )

# Show selected item preview
if st.session_state.selected_code and st.session_state.selected_description:
    st.caption(f"✅ Selected: **{st.session_state.selected_description}** (`{st.session_state.selected_code}`)")

# Step 4: Top rows input    
top_rows = st.number_input("🔢 Select Top Rows", min_value=1, max_value=100, value=20, step=1)

# Step 5: Action button
if st.button("Show Co-Purchased Items") and selected_brand:
    if len(date_range) != 2:
        st.warning("Please select a valid start and end date.")
    else:
        start_date = date_range[0].strftime('%Y-%m-%d')
        end_date = date_range[1].strftime('%Y-%m-%d')

        with engine.connect() as conn:
            gov_condition = f" AND c.GOVERNER_NAME = N'{selected_governerment}'" if selected_governerment else ""
            brand_item_filter = f" AND i.ITEM_CODE = '{st.session_state.selected_code}'" if st.session_state.selected_code else ""

            # Subquery: Orders that include the selected brand
            brand_orders_query = f"""
                SELECT DISTINCT s.Order_Number
                FROM MP_Sales s
                LEFT JOIN MP_Items i ON s.ItemId = i.ITEM_CODE 
                LEFT JOIN MP_Customers c ON s.CustomerId = c.SITE_NUMBER
                WHERE RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) = '{selected_brand}'
                  AND s.Date BETWEEN '{start_date}' AND '{end_date}' 
                  {gov_condition} {brand_item_filter}
            """

            # Main query: Co-purchased items
            main_query = f"""
                SELECT TOP {int(top_rows)}
                    i.DESCRIPTION AS Item_Description,
                    RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) AS Brand,
                    COUNT(DISTINCT s.Order_Number) AS Distinct_Orders,
                    Round(SUM(s.NetSalesValue),0) AS Total_Sales,
                    SUM(s.SalesQtyInCases) AS Total_Cases
                FROM MP_Sales s
                LEFT JOIN MP_Items i ON s.ItemId = i.ITEM_CODE
                LEFT JOIN MP_Customers c ON s.CustomerId = c.SITE_NUMBER
                WHERE s.Order_Number IN ({brand_orders_query})
                  AND RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) <> '{selected_brand}'
                  AND s.Date BETWEEN '{start_date}' AND '{end_date}' 
                  {gov_condition} 
                GROUP BY i.DESCRIPTION, i.MASTER_BRAND
                ORDER BY Distinct_Orders DESC
            """

            df = pd.read_sql(main_query, conn)

        # Display results
        if df.empty:
            st.info("No co-purchased items found for the selected criteria.")
        else:
            st.subheader(f"📦 Items frequently bought with **{selected_brand}**")
            st.dataframe(df)

            # Show SQL
            st.code(main_query, language='sql')
            st.write("Total Sales Value:", df["Total_Sales"].sum().round(0))

        # 🔍 Show Order Numbers
        with engine.connect() as conn:
            orders_df = pd.read_sql(brand_orders_query, conn)

        if not orders_df.empty:
            with st.expander("🧾 View Orders That Included Selected Brand"):
                st.dataframe(orders_df)

            selected_order = st.selectbox("🔢 Select an Order to Inspect", options=orders_df["Order_Number"].unique())
            st.session_state["selected_order_number"] = selected_order

# Show Order Details
if "selected_order_number" in st.session_state:
    if st.button("🔍 Show Order Details"):
        order_num = st.session_state["selected_order_number"]

        with engine.connect() as conn:
            detail_query = f"""
                SELECT 
                    s.Order_Number,
                    FORMAT(s.Date, 'yyyy-MM-dd') AS Date,
                    i.DESCRIPTION AS Item_Description,
                    RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) AS Brand,
                    s.SalesQtyInCases AS Cases,
                    s.NetSalesValue AS NetSalesValue
                FROM MP_Sales s
                LEFT JOIN MP_Items i ON s.ItemId = i.ITEM_CODE
                WHERE s.Order_Number = '{order_num}'
            """
            detail_df = pd.read_sql(detail_query, conn)
            detail_df["Selected"] = detail_df["Brand"] == selected_brand

        st.write(f"🧾 **Items in Order {order_num}**")

        # Highlight selected brand items
        def highlight_selected(val):
            return 'background-color: lightgreen' if val else ''

        st.dataframe(
            detail_df.style.applymap(highlight_selected, subset=['Selected'])
        )
        st.write("📊 **Order Details**")
        st.bar_chart(detail_df.set_index("Item_Description")["NetSalesValue"])
        st.write("net_sales_value", detail_df["NetSalesValue"].sum().round(0))
