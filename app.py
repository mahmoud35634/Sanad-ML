import streamlit as st

# Page setup
st.set_page_config(page_title="Sanad Analytics", layout="centered")

# --- Logo and Title ---
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image("logo.png", width=200)

st.markdown("<h1 style='text-align: center; margin-bottom: 0;'>Sanad Analytics Toolkit</h1>", unsafe_allow_html=True)
st.markdown("<h4 style='text-align: center; color: gray;'>Welcome! Choose a tool from the sidebar to get started.</h4>", unsafe_allow_html=True)
st.markdown("---")

# --- Style for cards ---
st.markdown("""
<style>
.tool-card {
    background-color: #f9f9f9;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
    transition: box-shadow 0.3s ease;
    cursor: pointer;
    text-decoration: none;
    display: block;
}
.tool-card:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    background-color: #f0f0f0;
}
.tool-title {
    font-size: 18px;
    font-weight: 600;
    color: #0e1117;
    margin-bottom: 5px;
    display: flex;
    align-items: center;
}
.tool-icon {
    font-size: 22px;
    margin-right: 10px;
}
.tool-desc {
    font-size: 15px;
    color: #5c5c5c;
    margin-left: 32px;
}
a {
    text-decoration: none;
}
</style>
""", unsafe_allow_html=True)

# --- Tools: (icon, title, description, page_name)
tools = [
    ("🧮", "SQL Server", "Query the database using SQL directly.", "SQL_Server"),
    ("🧠", "SQL Chatbot", "Ask questions using natural language and get data-driven answers.", "3_SQL_Chatbot"),
    ("🛍️", "Product Recommender", "Discover frequently co-purchased items.", "2_Product_Recommender"),
    ("🔄", "Co-Products by Brand", "View co-purchased products by brand over time.", "4_CoProducts_By_Brand"),
    ("📦", "Co-Products by Brand & Items", "Explore brand, item, category, and more with filters.", "5_CoProducts_By_Brand_Items"),
    ("📉", "Sales Forecasting", "Page under deployment. Stay tuned.", "6_Sales_Forecasting"),
    ("🎯", "ALX Product Recommender", "Recommend products for specific ALX customers.", "7_ALX_Recommender"),
]

# --- Render clickable cards ---
for icon, title, description, page in tools:
    st.markdown(f"""
        <div class="tool-card">
            <div class="tool-title"><span class="tool-icon">{icon}</span>{title}</div>
            <div class="tool-desc">{description}</div>
        </div>
 
    """, unsafe_allow_html=True)

st.markdown("---")
st.markdown(
    "<p style='text-align:center; color: #999;'>© 2025 BI Team | Analytics & ML Team</p>",
    unsafe_allow_html=True
)