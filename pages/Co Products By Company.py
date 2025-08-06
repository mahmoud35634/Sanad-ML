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
selected_brand = st.selectbox("🔍 Choose a Brand", options=brand_list)
selected_governerment = st.selectbox("🏙️ (Optional) Choose a Governorate", options=[""] + governer_list)

# Step 3: Date range input (up to today)
date_range = st.date_input(
    "📆 Select Date Range",
    value=(datetime.date(2023, 1, 1), datetime.date.today()),
    min_value=datetime.date(2023, 1, 1),
    max_value=datetime.date.today()
)

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

            # Subquery: Orders that include the selected brand
            brand_orders_query = f"""
                SELECT DISTINCT s.Order_Number
                FROM MP_Sales s
                LEFT JOIN MP_Items i ON s.ItemId = i.ITEM_CODE 
                LEFT JOIN MP_Customers c ON s.CustomerId = c.SITE_NUMBER
                WHERE RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) = '{selected_brand}'
                  AND s.Date BETWEEN '{start_date}' AND '{end_date}'
                  {gov_condition}
            """

            # Main query: Co-purchased items
            main_query = f"""
                SELECT TOP {int(top_rows)}
                    i.DESCRIPTION AS Item_Description,
                    RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) AS Brand,
                    COUNT(DISTINCT s.Order_Number) AS Distinct_Orders,
                    SUM(s.NetSalesValue) AS Total_Sales,
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

            st.subheader(f"📊 Top {min(10, len(df))} Co-Purchased Items")
            st.bar_chart(df.head(10).set_index("Item_Description")["Distinct_Orders"])
            st.write("Total Sales Value:", df["Total_Sales"].sum().round(0))

        # 🔍 Show Order Numbers
        with engine.connect() as conn:
            orders_df = pd.read_sql(brand_orders_query, conn)

        if not orders_df.empty:
            with st.expander("🧾 View Orders That Included Selected Brand"):
                st.dataframe(orders_df)

            selected_order = st.selectbox("🔢 Select an Order to Inspect", options=orders_df["Order_Number"].unique())
            st.session_state["selected_order_number"] = selected_order

# Button to load order details
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