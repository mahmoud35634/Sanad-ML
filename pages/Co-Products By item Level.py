import streamlit as st
import pandas as pd
import urllib
from sqlalchemy import create_engine
import datetime


# Function to load and inject CSS
def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Call it at the start of your app
load_css("style.css")
st.set_page_config(page_title="co Purchased items", page_icon="💬", layout="wide")


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

# --- UI ---
st.title("🛍️ Co-Purchased Items by Brand")


BI_PASSWORD = st.secrets["auth"]["BI_PASSWORD"]
BI_KEY = st.secrets["auth"]["BI_KEY"]
 
if BI_KEY not in st.session_state:
    st.session_state[BI_KEY] = False

if not st.session_state[BI_KEY] :
    st.title("🔐 Secure Access to Sanad Chatbot")
    password = st.text_input("Enter password to access", type="password")
    if st.button("Login"):
        if password == BI_PASSWORD:
            st.session_state[BI_KEY] = True
            st.rerun()
        else:
            st.error("Incorrect password ❌")
    st.stop()


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


brand_list = get_brand_list()

@st.cache_data
def get_govermant_list():
    with engine.connect() as conn:
        query = "SELECT DISTINCT GOVERNER_NAME FROM MP_Customers"
        result = pd.read_sql(query, conn)
        return result["GOVERNER_NAME"].dropna().unique().tolist()

governer_list = get_govermant_list()

@st.cache_data
def get_area_list(selected_governerment):
    with engine.connect() as conn:
        query = f"""SELECT DISTINCT AREA_NAME FROM MP_Customers WHERE GOVERNER_NAME = N'{selected_governerment}' """
        result = pd.read_sql(query,conn)
        return result['AREA_NAME'].dropna().unique().tolist()



# Step 2: UI components
selected_brand = st.selectbox("🔍Choose a Brand", options=brand_list)
selected_governerment = st.selectbox("🏙️ (Optional) Choose a Governorate", options=[""] + governer_list)
area_list_df = get_area_list(selected_governerment) if selected_governerment else []
selected_areas = st.multiselect("🏙️ (Optional) Choose an Area", options=[""] + area_list_df)



    # Governorate filter
def get_max_date():
    with engine.connect() as conn:
        query = "SELECT MAX(Date) AS MaxDate FROM MP_Sales"
        result = pd.read_sql(query, conn)
        if not result.empty and result["MaxDate"].iloc[0] is not None:
            return result["MaxDate"].iloc[0].date()
        return datetime.date.today()  # fallback

max_available_date = get_max_date()

date_range = st.date_input(
    "📆 Select Date Range",
    value=(datetime.date(2025, 1, 1), max_available_date),
    min_value=datetime.date(2025, 1, 1),
    max_value=max_available_date
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


def get_category_list():
    with engine.connect() as conn:
        query = f"""
            SELECT DisTinct Right(MG2, LEN(MG2) - CHARINDEX('|', MG2)) AS Category
            FROM MP_Items  
        """
        result = pd.read_sql(query, conn)
        return result["Category"].dropna().unique().tolist() 
    
category_list_df = get_category_list() 
selected_category = st.selectbox("🏙️ (Optional) Choose a Category", options=[""] + category_list_df)

    
# --- Initialize session state ---
if "selected_code" not in st.session_state:
    st.session_state.selected_code = []
if "selected_description" not in st.session_state:
    st.session_state.selected_description = []

def update_description():
    codes = st.session_state.selected_code
    descs = items_list_df[items_list_df["ITEM_CODE"].isin(codes)]["DESCRIPTION"].tolist()
    st.session_state.selected_description = descs

def update_code():
    descs = st.session_state.selected_description
    codes = items_list_df[items_list_df["DESCRIPTION"].isin(descs)]["ITEM_CODE"].tolist()
    st.session_state.selected_code = codes

col1, col2 = st.columns(2)

with col1:
    st.multiselect(
        "🔢 Select by Item Code",
        options=items_list_df["ITEM_CODE"].tolist(),
        key="selected_code",
        on_change=update_description
    )

with col2:
    st.multiselect(
        "📝 Select by Description",
        options=items_list_df["DESCRIPTION"].tolist(),
        key="selected_description",
        on_change=update_code
    )


# Show selected item preview
if st.session_state.selected_code and st.session_state.selected_description:
    preview = ", ".join([f"**{d}** (`{c}`)" 
                         for c, d in zip(st.session_state.selected_code, st.session_state.selected_description)])
    st.caption(f"✅ Selected: {preview}")

# Step 4: Top rows input    
top_rows = st.number_input("🔢 Select Top Rows", min_value=1, max_value=100, value=20, step=1)
gov_condition = f" AND c.GOVERNER_NAME = N'{selected_governerment}'" if selected_governerment else ""

# Area filter
area_item_filter = ""
if selected_areas:
    selected_areas_clean = [a for a in selected_areas if a]
    if selected_areas_clean:
        areas_str = ",".join([f"N'{a}'" for a in selected_areas_clean])
        area_item_filter = f" AND c.AREA_NAME IN ({areas_str})"

# Brand filter
brand_item_filter = ""
if st.session_state.selected_code:
    codes_str = ",".join([f"'{c}'" for c in st.session_state.selected_code if c])
    if codes_str:
        brand_item_filter = f" AND i.ITEM_CODE IN ({codes_str})"

# Category filter
category_item_filter = f" AND Right(i.MG2, LEN(i.MG2) - CHARINDEX('|', i.MG2)) = N'{selected_category}'" if selected_category else ""
# Step 5: Action button
if "show_results" not in st.session_state:
    st.session_state.show_results = False

if st.button("Show Co-Purchased Items") and selected_brand:
    st.session_state.show_results = True




if st.session_state.show_results:
    start_date = date_range[0].strftime('%Y-%m-%d')
    end_date = (
        date_range[1].strftime('%Y-%m-%d') 
        if len(date_range) > 1 and date_range[1] else 
        max_available_date.strftime('%Y-%m-%d')) 
    with engine.connect() as conn:
        max_order_query = f"""
            SELECT TOP 1 
                s.Order_Number,
                SUM(s.NetSalesValue) AS OrderValue
            FROM MP_Sales s
            LEFT JOIN MP_Items i ON s.ItemId = i.ITEM_CODE 
            LEFT JOIN MP_Customers c ON s.CustomerId = c.SITE_NUMBER
            WHERE RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) = '{selected_brand}'
            AND s.Date BETWEEN '{start_date}' AND '{end_date}'
            {gov_condition} {area_item_filter} {brand_item_filter}
            GROUP BY s.Order_Number
            ORDER BY OrderValue DESC
        """
        result = pd.read_sql(max_order_query, conn)
        if not result.empty:
            max_order_number = int(result["Order_Number"].iloc[0])
            max_order_value = int(result["OrderValue"].iloc[0])
        else:
            max_order_number = None
            max_order_value = 20000

    # --- Dynamic slider ---
    order_min, order_max = st.slider(
        "💰 Order Value Range",
        min_value=0,
        max_value=max_order_value + 1,
        value=(0, max_order_value+1),   # default range uses max order value
        step=100
    )

    # Show the order with max sales
    if max_order_number:
        st.info(f"🏆 Highest order for **{selected_brand}** is **{max_order_number}** "
                f"with value: {max_order_value:,}")



    # Save queries
    st.session_state.brand_orders_query = f"""
        SELECT DISTINCT s.Order_Number
        FROM MP_Sales s
        LEFT JOIN MP_Items i ON s.ItemId = i.ITEM_CODE 
        LEFT JOIN MP_Customers c ON s.CustomerId = c.SITE_NUMBER
        WHERE RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) = '{selected_brand}'
          AND s.Date BETWEEN '{start_date}' AND '{end_date}'
          {gov_condition} {brand_item_filter} {area_item_filter}
        GROUP BY s.Order_Number
        HAVING SUM(s.NetSalesValue) BETWEEN {order_min} AND {order_max}
    """

    st.session_state.main_query = f"""
        WITH BrandOrders AS (
            {st.session_state.brand_orders_query}
        )
        SELECT TOP {int(top_rows)}
        i.ITEM_CODE,
            i.DESCRIPTION AS Item_Description,
            RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) AS Brand,
            RIGHT(i.MG2, LEN(i.MG2) - CHARINDEX('|', i.MG2)) AS category,
            RIGHT(i.MG3, LEN(i.MG3) - CHARINDEX('|', i.MG3)) AS subcategory,
            COUNT(DISTINCT s.Order_Number) AS Distinct_Orders,
            ROUND(SUM(s.NetSalesValue),0) AS Total_Sales,
            SUM(s.SalesQtyInCases) AS Total_Cases
        FROM MP_Sales s
        LEFT JOIN MP_Items i ON s.ItemId = i.ITEM_CODE
        LEFT JOIN MP_Customers c ON s.CustomerId = c.SITE_NUMBER
        INNER JOIN BrandOrders bo ON s.Order_Number = bo.Order_Number
        WHERE RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)) <> '{selected_brand}'
          AND s.Date BETWEEN '{start_date}' AND '{end_date}'  AND i.ITEM_CODE NOT LIKE '%XE%'
          {gov_condition} {category_item_filter} {area_item_filter}
        GROUP BY  
        i.ITEM_CODE,
            i.DESCRIPTION,
            RIGHT(i.MASTER_BRAND, LEN(i.MASTER_BRAND) - CHARINDEX('|', i.MASTER_BRAND)),
            RIGHT(i.MG2, LEN(i.MG2) - CHARINDEX('|', i.MG2)) ,
            RIGHT(i.MG3, LEN(i.MG3) - CHARINDEX('|', i.MG3))
        ORDER BY Distinct_Orders DESC
    """
    with engine.connect() as conn:
        st.session_state.df = pd.read_sql(st.session_state.main_query, conn)

# Now show the results, even after rerun
if st.session_state.get("df") is not None:
    df = st.session_state.df

    st.subheader(f"📦 Items frequently bought with **{selected_brand}**")
    st.dataframe(df)

    # Password protection for SQL
    if "power_bi_pass" not in st.session_state and "user_password" not in st.session_state:
        st.session_state.power_bi_pass = False
        st.session_state.user_password = False

    if not st.session_state.power_bi_pass and not st.session_state.user_password:
        st.subheader("🔒 If you are the one of developers of the app enter password for developers if not continue")
        password_input = st.text_input("Enter password to view SQL", type="password", key="sql_password_input")
        if password_input == "2392000":
            st.session_state.power_bi_pass = True
            st.success("✅ Password correct! Showing SQL query:")
        elif password_input == "trade_pass":
            st.session_state.user_password = True
            st.success("✅ Password correct! Showing SQL query:")
        elif password_input:
            st.error("❌ Incorrect password.")

    if st.session_state.power_bi_pass:
        st.write("🔍 **SQL Query Used**")
        with st.expander("🧾 View Sql used"):

            st.code(st.session_state.main_query, language='sql')
        if df.empty:

            st.write("There is no results")
        else :
            st.write("💰 Total Sales Value:", df["Total_Sales"].sum().round(0))

    if st.session_state.user_password:

        st.write("💰 Total Sales Value:", df["Total_Sales"].sum().round(0))

    # Show brand orders
    with engine.connect() as conn:
        orders_df = pd.read_sql(st.session_state.brand_orders_query, conn)

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