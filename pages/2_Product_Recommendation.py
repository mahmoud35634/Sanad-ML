import streamlit as st
import joblib

st.title("🛒 Product Recommender")
if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.warning("🔒 Please login first from the Home page.")
    st.stop()
@st.cache_resource
def load_models():
    sim_df = joblib.load("item_similarity.pkl")
    name_map = joblib.load("item_name_map.pkl")
    return sim_df, name_map

def get_recommendations(item_id, sim_df, name_map, top_n=5):
    if item_id not in sim_df.columns:
        return []
    similar_items = sim_df[item_id].sort_values(ascending=False).drop(item_id)
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
