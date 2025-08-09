import streamlit as st
import pickle
import pandas as pd
import os
import pickle, os, hashlib, requests, gzip, shutil
from pathlib import Path

DATA_DIR = Path(".")  # keep current behavior
DATA_DIR.mkdir(exist_ok=True)

# Map your required files to remote sources
# Replace OWNER/REPO/v1 and checksums with your own.
FILE_SOURCES = {
    "user_item.pkl": {
        "url": "https://github.com/OWNER/REPO/releases/download/v1/user_item.pkl.gz",
        "sha256": "PUT_SHA256_OF_FINAL_PKL_HERE",  # optional
        "gz": True
    },
    "item_sim_df.pkl": {
        "url": "https://github.com/OWNER/REPO/releases/download/v1/item_sim_df.pkl.gz",
        "sha256": "PUT_SHA256_HERE",
        "gz": True
    },
    "df_items.pkl": {
        "url": "https://github.com/OWNER/REPO/releases/download/v1/df_items.pkl.gz",
        "sha256": "PUT_SHA256_HERE",
        "gz": True
    },
    "df_customers.pkl": {
        "url": "https://github.com/OWNER/REPO/releases/download/v1/df_customers.pkl.gz",
        "sha256": "PUT_SHA256_HERE",
        "gz": True
    },
    # If you switch to Parquet for df_items:
    # "df_items.parquet": {"url": ".../df_items.parquet", "sha256": "...", "gz": False},
}

def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def download_with_progress(url: str, dest: Path, label: str):
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        progress = st.progress(0, text=f"Downloading {label}...")
        downloaded = 0
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        progress.progress(min(downloaded / total, 1.0), text=f"Downloading {label}...")
        tmp.replace(dest)
        progress.progress(1.0, text=f"Downloaded {label}")

def ensure_file(local_name: str, src: dict):
    local_path = DATA_DIR / local_name
    if local_path.exists():
        return local_path

    st.info(f"Missing {local_name}. Fetching from remote...")
    url = src["url"]
    gz = src.get("gz", False)

    if gz:
        gz_path = local_path.with_suffix(local_path.suffix + ".gz")
        download_with_progress(url, gz_path, local_name)
        st.write(f"Decompressing {local_name}...")
        with gzip.open(gz_path, "rb") as f_in, open(local_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        gz_path.unlink(missing_ok=True)
    else:
        download_with_progress(url, local_path, local_name)

    # Optional integrity check
    expected = src.get("sha256")
    if expected:
        digest = sha256_of_file(local_path)
        if digest.lower() != expected.lower():
            local_path.unlink(missing_ok=True)
            st.error(f"Checksum mismatch for {local_name}. Download aborted.")
            st.stop()

    return local_path

def ensure_artifacts():
    for name, src in FILE_SOURCES.items():
        ensure_file(name, src)

# Call this before load_data()
ensure_artifacts()

@st.cache_resource(show_spinner=True)
def load_data():
    # Now your original code can stay the same, files are present locally.
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
st.title("🛍️ Product Recommender for Alex Customers")
st.write("Enter a customer B2B ID to get personalized product recommendations. This tool uses collaborative filtering to suggest items based on past purchases. Only for Alex Customers.")

# --- Input ---
customer_ids = user_item.index.tolist()
customer_names = df_customers.set_index('id')['name'].to_dict()

# Create a dictionary for customer names
customer_names_dict = {cid: customer_names.get(cid, "Unknown Customer") for cid in customer_ids}

# Dropdown with customer names
selected_customer = st.selectbox(
    "Select Customer B2B ID",
    options=customer_ids,
    format_func=lambda x: f"{x} - {customer_names_dict.get(x, 'Unknown Customer')}",
    index=0
)

# Use selected customer or allow manual entry
if selected_customer:
    customer_id = selected_customer
else:
    customer_id = st.text_input("Enter Customer B2B ID", value="", placeholder="e.g., 12345")

# --- Slider for number of recommendations ---
top_n = st.slider("Number of Recommendations", 1, 20, 5)

# --- Recommendation Function ---
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

# --- Display customer name ---
if customer_id.strip() != "":
    if customer_id in df_customers['id'].values:
        customer_name = df_customers[df_customers['id'] == customer_id]['name'].values[0]
    else:
        customer_name = "Unknown Customer"
    st.write(f"🔍 Recommendations for Customer: `{customer_name}` (ID: `{customer_id}`)")

# --- Show Recommendations ---
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
