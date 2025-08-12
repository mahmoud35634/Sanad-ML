import streamlit as st
import joblib
import os
import requests

st.title("🛒 Product Recommender")

BI_PASSWORD = st.secrets["auth"]["BI_PASSWORD"]
BI_KEY = st.secrets["auth"]["BI_KEY"]

if BI_KEY not in st.session_state:
    st.session_state[BI_KEY] = False

if not st.session_state[BI_KEY]:
    st.title("🔐 Secure Access to Sanad Chatbot")
    password = st.text_input("Enter password to access", type="password")
    if st.button("Login"):
        if password == BI_PASSWORD:
            st.session_state[BI_KEY] = True
            st.experimental_rerun()
        else:
            st.error("Incorrect password ❌")
    st.stop()

def download_file(url, local_path):
    if not os.path.exists(local_path):
        dirname = os.path.dirname(local_path)
        if dirname != '':
            os.makedirs(dirname, exist_ok=True)
        st.info(f"Downloading {os.path.basename(local_path)} from GitHub Releases...")
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        st.success(f"{os.path.basename(local_path)} downloaded successfully.")

@st.cache_resource
def load_models():
    sim_url = "https://github.com/mahmoud35634/Sanad-ML/releases/download/v1.0/item_similarity.pkl"
    name_map_url = "https://github.com/mahmoud35634/Sanad-ML/releases/download/v1.0/item_name_map.pkl"

    # Save files in a models/ folder to keep organized
    sim_path = "models/item_similarity.pkl"
    name_map_path = "models/item_name_map.pkl"

    download_file(sim_url, sim_path)
    download_file(name_map_url, name_map_path)

    sim_df = joblib.load(sim_path)
    name_map = joblib.load(name_map_path)

    return sim_df, name_map

def get_recommendations(item_id, sim_df, name_map, top_n=5):
    if item_id not in sim_df.columns:
        return []
    similar_items = sim_df[item_id].sort_values(ascending=False).drop(item_id, errors='ignore')
    return [(i, name_map.get(i, "Unknown Name")) for i in similar_items.head(top_n).index]

# Load model and mappings
similarity_df, item_name_map = load_models()

# Reverse map for dropdown
item_list = [(name, code) for code, name in item_name_map.items()]
item_names = [name for name, code in item_list]

st.radio("Choose input method:", ["Select by name", "Enter Item ID"], key="input_mode")

# Method 1: Select from dropdown
if st.session_state.input_mode == "Select by name":
    selected_name = st.selectbox("Select an item:", item_names)
    selected_id = next((code for name, code in item_list if name == selected_name), None)

# Method 2: Enter Item ID manually
else:
    selected_id = st.text_input("Enter Item ID:")
    selected_name = item_name_map.get(selected_id, "Unknown Item")

if selected_id:
    recs = get_recommendations(selected_id, similarity_df, item_name_map)
    if recs:
        st.subheader(f"🔁 Recommended for: {selected_name} ({selected_id})")
        for code, name in recs:
            st.write(f"- **{code}**: {name}")
    else:
        st.warning("No recommendations found for this Item ID.")
