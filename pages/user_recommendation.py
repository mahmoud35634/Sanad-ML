import streamlit as st
import pickle
import pandas as pd
import requests
import io

# ==== Google Drive File IDs ====
# Replace these with the file IDs from your Google Drive share links
GDRIVE_FILES = {
    "user_item.pkl": "1why2DyO-hSdRyCVOyDZjelsBCu8B7mP2",      # Example: after /d/ in the Google Drive link
    "item_sim_df.pkl": "13TMwmZYNbmXD6AnviPpdWWpeP9IqDhHZ",
    "df_items.pkl": "1XGBoEE6gQKL4NSvzD8yeeeb8_xr9Gw5f",
    "df_customers.pkl": "1kQxVeNCbwD-5wDgdTywKw6eY7cZ_iKvP"
}

@st.cache_resource(show_spinner=True)
def download_from_gdrive(file_id: str):
    """Download and load a pickle file from Google Drive."""
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = requests.get(url)
    response.raise_for_status()
    return pickle.load(io.BytesIO(response.content))

@st.cache_resource(show_spinner=True)
def load_data():
    user_item = download_from_gdrive(GDRIVE_FILES["user_item.pkl"])
    item_sim_df = download_from_gdrive(GDRIVE_FILES["item_sim_df.pkl"])
    df_items = download_from_gdrive(GDRIVE_FILES["df_items.pkl"])
    df_customers = download_from_gdrive(GDRIVE_FILES["df_customers.pkl"])
    return user_item, item_sim_df, df_items, df_customers

# === Load all data once ===
user_item, item_sim_df, df_items, df_customers = load_data()

# === UI ===
st.title("🛍️ Product Recommender for Alex Customers")
st.write("Enter a customer B2B ID to get personalized product recommendations. This tool uses collaborative filtering to suggest items based on past purchases. Only for Alex Customers.")

customer_ids = user_item.index.tolist()
customer_names = df_customers.set_index('id')['name'].to_dict()
customer_names_dict = {cid: customer_names.get(cid, "Unknown Customer") for cid in customer_ids}

selected_customer = st.selectbox(
    "Select Customer B2B ID",
    options=customer_ids,
    format_func=lambda x: f"{x} - {customer_names_dict.get(x, 'Unknown Customer')}",
    index=0
)

customer_id = selected_customer if selected_customer else st.text_input("Enter Customer B2B ID", value="", placeholder="e.g., 12345")
top_n = st.slider("Number of Recommendations", 1, 20, 5)

def recommend_for_customer(customer_id, top_n=5, item_metadata=None):
    if customer_id not in user_item.index:
        return []
    customer_purchases = user_item.loc[customer_id]
    purchased_items = customer_purchases[customer_purchases > 0].index.tolist()
    scores = pd.Series(dtype=float)

    for item in purchased_items:
        similar_items = item_sim_df[item].drop(index=purchased_items)
        if item_metadata is not None:
            item_info = item_metadata.set_index('ItemId')
            if item in item_info.index:
                item_row = item_info.loc[item]
                mask = (item_info['Brand'] == item_row['Brand']) | (item_info['Category'] == item_row['Category'])
                boost_ids = item_info[mask].index
                similar_items[similar_items.index.isin(boost_ids)] *= 1.2
        scores = scores.add(similar_items, fill_value=0)

    if item_metadata is not None:
        purchased_info = item_metadata[item_metadata['ItemId'].isin(purchased_items)]
        target_values = purchased_info[['Brand', 'Category']].drop_duplicates()
        valid_items = item_metadata.merge(target_values, on=['Brand', 'Category'])['ItemId']
        scores = scores[scores.index.isin(valid_items)]

    return scores.sort_values(ascending=False).head(top_n).index.tolist()

if customer_id.strip() != "":
    if customer_id in df_customers['id'].values:
        customer_name = df_customers[df_customers['id'] == customer_id]['name'].values[0]
    else:
        customer_name = "Unknown Customer"
    st.write(f"🔍 Recommendations for Customer: `{customer_name}` (ID: `{customer_id}`)")

if st.button("🔍 Show Recommendations") and customer_id.strip() != "":
    recommendations = recommend_for_customer(
        customer_id=customer_id.strip(),
        top_n=top_n,
        item_metadata=df_items,
    )
    if recommendations:
        st.success(f"Top {top_n} recommendations for Customer ID: `{customer_id}`")
        rec_df = df_items[df_items["ItemId"].isin(recommendations)][["ItemId", "itemname", "Brand", "Category"]]
        st.dataframe(rec_df.reset_index(drop=True))
    else:
        st.warning("No recommendations found. Make sure the ID exists and has purchases.")
