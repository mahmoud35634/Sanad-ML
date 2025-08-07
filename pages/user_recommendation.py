import streamlit as st
import pickle
import pandas as pd

# --- Load precomputed files ---
@st.cache_data
def load_data():
    with open("user_item.pkl", "rb") as f:
        user_item = pickle.load(f)
    with open("item_sim_df.pkl", "rb") as f:
        item_sim_df = pickle.load(f)
    with open("df_items.pkl", "rb") as f:
        df_items = pickle.load(f)
    with open("df_customers.pkl", "rb") as f:
        df_customers = pickle.load(f)
    return user_item, item_sim_df, df_items, df_customers

user_item, item_sim_df, df_items, df_customers = load_data()

# --- Title ---
st.title("🛍️ Product Recommender for Alex Customers")
st.write("Enter a customer B2B ID to get personalized product recommendations. This tool uses collaborative filtering to suggest items based on past purchases. only for Alex Customers")

# --- Input ---
customer_id = st.text_input("🔑 Enter Customer B2B ID", "")

# --- Optional filters ---
# with st.expander("⚙️ Filter by"):
#     filter_by = st.selectbox("Filter by", ["None", "Brand", "Category"])
top_n = st.slider("Number of Recommendations", 1, 20, 5)

# --- Recommendation Function ---
def recommend_for_customer(customer_id, top_n=top_n, item_metadata=None, filter_by=None):
    if customer_id not in user_item.index:
        return []

    customer_purchases = user_item.loc[customer_id]
    purchased_items = customer_purchases[customer_purchases > 0].index.tolist()

    scores = pd.Series(dtype=float)

    for item in purchased_items:
        similar_items = item_sim_df[item].drop(index=purchased_items)

        if item_metadata is not None and filter_by and filter_by != "None":
            item_info = item_metadata.set_index('ItemId')
            if item in item_info.index:
                item_value = item_info.loc[item, filter_by]
                matching_items = item_info[item_info[filter_by] == item_value].index
                similar_items[similar_items.index.isin(matching_items)] *= 1.2  # boost similar category/brand

        scores = scores.add(similar_items, fill_value=0)

    if item_metadata is not None and filter_by and filter_by != "None":
        purchased_info = item_metadata[item_metadata['ItemId'].isin(purchased_items)]
        target_values = purchased_info[filter_by].unique()
        valid_items = item_metadata[item_metadata[filter_by].isin(target_values)]['ItemId']
        scores = scores[scores.index.isin(valid_items)]

    return scores.sort_values(ascending=False).head(top_n).index.tolist()

#show customer name corresponding to the customer_id
if customer_id.strip() != "":
    if customer_id in df_customers['id'].values:
        user_item.name = df_customers[df_customers['id'] == customer_id]['name'].values[0]
    else:
        user_item.name = "Unknown Customer"
# Display Customer Name
st.write(f"🔍 Recommendations for Customer: `{user_item.name}` (ID: `{customer_id}`)")
# --- Display Recommendations ---
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
