
# --- Libraries ---
import streamlit as st
import google.generativeai as genai
import pyodbc
import pandas as pd
from dotenv import load_dotenv
import os
import io
import re
from time import sleep

# =========================
# App Config
# =========================
st.set_page_config(page_title="Sanad BI Chatbot", page_icon="💬", layout="wide")

# --- Load API Key ---
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# =========================
# Authentication
# =========================
BI_PASSWORD = "BI_admin"
BI_KEY = "auth_bi_chat"
TRADE_PASSWORD = "Trade_admin"
TRADE_KEY = "auth_trade_chat"

if BI_KEY not in st.session_state:
    st.session_state[BI_KEY] = False
if TRADE_KEY not in st.session_state:
    st.session_state[TRADE_KEY] = False

if not st.session_state[BI_KEY] and not st.session_state[TRADE_KEY]:
    st.header("🔐 Secure Access to Sanad Chatbot")
    password = st.text_input("Enter password to access", type="password")
    col_login1, col_login2 = st.columns([1,3])
    with col_login1:
        if st.button("Login"):
            if password == BI_PASSWORD:
                st.session_state[BI_KEY] = True
                st.rerun()
            elif password == TRADE_PASSWORD:
                st.session_state[TRADE_KEY] = True
                st.rerun()
            else:
                st.error("Incorrect password ❌")
    st.stop()

# =========================
# Header & Branding
# =========================
if st.session_state[BI_KEY]:
    st.header("💬 BI Chatbot - BI Access")
elif st.session_state[TRADE_KEY]:
    st.title("💬 BI Chatbot - Trade Access")

st.subheader("Welcome! Ask anything about insights, and get answers in real-time.")

# --- Logo ---
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image("logoo.png", width=200)





@st.cache_resource
def connect_db():
    db_config = st.secrets["database"]
    try:
        return pyodbc.connect(
            f"DRIVER={{{db_config['driver']}}};"
            f"SERVER={db_config['server']};"
            f"DATABASE={db_config['database']};"
            f"UID={db_config['username']};"
            f"PWD={db_config['password']};"

        )
    
    except Exception:
        st.error("❌ Could not connect to database.")
        return None

conn = connect_db()
if conn is None:
    st.stop()


# =========================
# Helpers
# =========================
def execute_query_safe(conn, sql, retries=3, delay=1):
    """Run SQL with basic retry for deadlocks; return DataFrame or empty DF."""
    for attempt in range(retries):
        try:
            return pd.read_sql(sql, conn)
        except pyodbc.Error as e:
            # Deadlock or retryable error (40001). Args may vary by driver/version.
            if len(e.args) > 0 and ("40001" in str(e.args[0]) or "deadlock" in str(e).lower()):
                if attempt < retries - 1:
                    sleep(delay)
                    continue
            st.error(f"❌ Database error occurred.")
            return pd.DataFrame()
        except Exception:
            st.error("❌ Unexpected error occurred.")
            return pd.DataFrame()
    return pd.DataFrame()

def is_safe_select(sql: str) -> bool:
    """Allow only a single SELECT statement; block DDL/DML and dangerous keywords."""
    text = sql.strip().rstrip(";")
    # Must start with SELECT (allow WITH CTE too)
    if not re.match(r"(?is)^\s*(with\s+[\s\S]+?\)\s*select|select)\b", text):
        return False
    forbidden = r"(?is)\b(insert|update|delete|merge|alter|drop|create|truncate|grant|revoke|exec|execute|sp_|xp_|bulk\s+insert)\b"
    if re.search(forbidden, text):
        return False
    # crude multi-statement block: additional semicolons followed by non-space text
    # (allow semicolons inside strings/formatting is hard; we keep it strict)
    if re.search(r";\s*\S", sql.strip()):
        return False
    return True

def sanitize_and_extract_sql_from_gemini(response) -> str:
    """
    Robustly extract SQL text from Gemini response across formats.
    """
    raw = ""
    if hasattr(response, "text") and response.text:
        raw = response.text
    elif hasattr(response, "candidates") and response.candidates:
        try:
            parts = response.candidates[0].content.parts
            raw = "".join(getattr(p, "text", "") for p in parts)
        except Exception:
            raw = ""
    # Strip code fences if present
    raw = raw.strip()
    # Handle ```sql ... ``` or ``` ... ```
    m = re.search(r"```sql\s*([\s\S]+?)```", raw, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"```\s*([\s\S]+?)```", raw, flags=re.IGNORECASE)
    sql = (m.group(1) if m else raw).strip()
    return sql

# =========================
# Schema Prompt
# =========================
def Schema_description():
    # >>> Paste your full schema/business-rules prompt here <<<
    return """
You are a SQL expert for an e-commerce database with three main tables: MP_Sales, MP_Customers, and MP_Items.
Your job is to generate valid SQL Server SELECT queries only based on user requests, following these exact rules:

Database Schema Overview:

MP_Sales (Sales Transactions)

Joins:
MP_Sales.CustomerID = MP_Customers.SITE_NUMBER
MP_Sales.ItemId = MP_Items.ITEM_CODE

Important Columns:
Date (YYYY-MM-DD) — transaction date
Netsalesvalue — sales value after tax/discounts
SalesQtyInPieces, SalesQtyInCases, order_Number
ItemId, CustomerID — for joins
Master_brand, sub_brand, brandname, Sales_Channel, itemname
project_id, company, Org_ID, InvoiceId

Rules:

Do not use month column; extract month from Date if needed.

Always Format sales values using  Round(s.Netsalesvalue,0)

if i asked about average for brand over months so the avgerage i need to be calculated Sum(Netsalesvalue/no of months)

MP_Customers (Customer Master)

Joins: MP_Sales.CustomerID = MP_Customers.SITE_NUMBER

Important Columns:
GOVERNER_NAME, CUSTOMER_B2B_ID, CUSTOMER_NAME, SALES_CHANNEL_CODE,
SECTION_TYPE, CUSTOMER_NUMBER, CITY_NAME, AREA_NAME,
LOCATION, ADDRESS1, SITE_NUMBER, ACCOUNT_CREATION_DATE, SITE_CREATION_DATE

Rules:

Valid governorate filter: use GOVERNER_NAME.

If user asks "active customers" → customers with purchases/orders.

If user asks "active net customers" → customers with Netsalesvalue > 1.

If user says "net active" or just "active" in general → return total count only, not list.

If filtered by company or other attribute → return total count per that attribute and use  FORMAT(Count (Distinct CUSTOMER_B2B_ID), 'N0')

if i asked like i want to show customers who made a purchased on specif month dont search with site number search with B2B id 

MP_Items (Product Master)

Joins: MP_Sales.ItemId = MP_Items.ITEM_CODE

Important Columns:
ITEM_CODE, DESCRIPTION, MASTER_BRAND, MG2, MG3, GCOMPANY, GFORM, GSIZE, MSU, CONVERSION_RATE , Supplier

Rules:

MASTER_BRAND format: code|brandname.

Brand name: RIGHT(MASTER_BRAND, LEN(MASTER_BRAND) - CHARINDEX('|', MASTER_BRAND))

Brand code: LEFT(MASTER_BRAND, CHARINDEX('|', MASTER_BRAND) - 1)

MG2 format: code|category. Extract only category name.

To filter by company:

WHERE LEFT(MASTER_BRAND, CHARINDEX('|', MASTER_BRAND) - 1) = '<first 6 digits>'


General Query Requirements:

Always use MP_Sales.Date for date filtering.

Always join to CUSTOMER_B2B_ID when query is about customers.

If a company filter is requested, match on the MASTER_BRAND code.

Extract readable brand/category names when returning them.

and this the lsited companies or MASTER_BRAND

Use LEFT(MASTER_BRAND, CHARINDEX('|', MASTER_BRAND) - 1) to extract brand code

        724046|موندليز
        853046|Zewoo
        692399|abo dawod
        692425|Queen Packaging
        849054|ILOU
        876045|RC
        692376|Coca Cola
        812044|Rehana
        692471|GLLOPAL
        921140|Al Raheeq Al Makhtum
        694044|MP_P&G
        811044|El Sohagy
        692383|EL Masrayia oils
        874044|Mazaq
        827044|Fay
        692381|Mansour
        692561|Sun Bites
        928166|Blu
        945045|ONa
        750045|Soudanco
        692786|Relax
        730044|Haboba
        692405|add me
        892070|Crunchy
        883050|Razz
        692803|Ragon
        897044|Bonz
        787044|lipton
        805046|Maram
        818044|Afandy
        883051|Star Bar
        693045|Halwani Brothers
        707045|Edafco
        892069|Chipsy
        693047|ELMALEKA
        751044|Abo Taleb
        692366|EL Gayar
        969044|Safe
        883046|Halwani Brothers Maamoal
        716045|Boshrt kheir
        790047|Classique coffee
        956044|Sparx
        692652|Pantene
        692428|Ayman Afandy
        731050|Go Mix
        692385|Indomie
        692378|Lamar
        692689|kingo
        799044|Kelloggs Noodels
        921138|Chefy Mix
        692455|Vatika
        692414|Elshamadan
        782044|Soft Rose
        692765|Bebeto
        772044|Mondelez
        752045|Roll Plast
        692446|Pyrosol
        804044|Class A
        731054|Mimco
        692353|TTC
        693049|Shaheen Coffee
        692373|Zeina
        692454|Ahmed El Sheikh Coffee
        692441|Fine
        692469|S2
        692431|Vacakis Cafe
        928165|Clean way
        692612|Hayat
        692704|Haribo
        693053|Sima
        692705|Saula
        951044|Drova
        692559|Rhodes
        747044|Nawara foods
        731047|Coffee break
        692457|Kamara
        796044|Arma soap
        692486|Sun shine
        957045|Hmto
        692359|HABIBCO
        693058|Johnson
        970044|Yes
        692388|Sun Top
        968044|kaline
        692380|Arma
        692375|IFFCO
        692427|Mass Foods
        785044|Al ahlam
        961045|Sparkel
        711376|سيما
        573349|Silo
        847044|Double Dare
        692356|Al Mufaddal
        881044|Larch
        850045|Twevel
        856046|Twist
        692411|Bill Egypt
        722048|Cairo group
        752044|Elshanawany
        692466|alfnar
        844044|4M
        731056|Qutuf
        742044|Xera_FreeGoods
        722047|Elhana
        NULL
        876044|Snaps
        822044|AL Tahhan
        692460|4A Nutrition
        878044|Dilmah
        692461|arfa
        794044|Weals
        888046|Signal
        791044|Aje Group
        849051|Astra
        945044|Carlito
        876046|Double Break
        783046|Reckitt
        6171|Head & Shoulders
        692397|AM Group
        849052|Milka
        842044|Tiba Trade
        692410|Rosso
        875044|Rich Bake
        692416|Edco
        180829|Domty
        693044|Dream
        692456|Al-Shahin
        792044|Milano
        849050|Mousi
        928167|Bashayer
        692569|Bravo
        692394|Obour Land
        692409|Flamenco co
        692386|Regina
        692467|Elasi
        949044|Al Sultan 
        692451|LaRose
        693056|EL Marai
        802044|AL Arabia Oil
        1875|Default
        692370|PEPSICO
        929046|Blanco
        836044|Albader
        724045|إيفرجو
        937044|Yoodles
        966045|Alex
        692354|Green plant
        693051|White
        692587|Karate
        692391|Savola
        722046|Coolest Bottle
        692392|AL SHARQ
        692355|Edita
        745044|Valley Water
        692730|Energizer
        937057|Best
        722051|Green land
        954044|EL Abd
        847045|Magic
        692437|Ulker
        778044|Zeyada
        692418|Hero/Vitrac
        748044|Lana Tex
        951048|Maxi
        736044|United oils
        728047|Elzaeem
        692572|Clorox
        722044|Cairo Oil
        692695|Pringles
        692694|Mentos
        818045|Daima
        731051|Hawaa
        692432|Crush
        728045|ELkhatab
        692384|El Anany
        692412|United Distributors
        692377|El-Zomoroda
        692408|Senyorita
        692439|Evyap
        731048|Emad Effendi
        693054|Aljawhara
        692406|El Bawadi
        711224|الريحان
        820044|AL Kbous Tea
        692660|Tolido
        731055|Pafitos
        692358|Al-Buraq
        711399|غندور
        711332|دامور
        893044|Close Up
        850044|Hatlou
        692413|Egypt Foods
        692458|Ekhnaton
        883045|Fitness
        692401|Al Yemeni Cafe
        718045|Inactive
        824044|Rhone Tech
        692369|Juhayna
        692721|Pretzels
        692372|Nestle
        692423|R.M Trade
        722050|Alporsaideya
        737044|Elkholy
        847046|Magical
        894045|Kit Kat
        692363|Lametna
        808044|Tag Elmelouk
        883049|L'usin
        810044|Mansour Eltiti
        692435|Corona
        711417|قطوف
        692387|El Doha
        795044|Egy Bella
        692393|wapco
        821044|Rabea Tea
        711223|الرشيدى الميزان
        790044|El Ahram
        722045|Gefco
        692422|IMTENAN
        929045|Good Clean
        809044|EL omda
        711420|ايزيس
        883044|Coco Bobs
        692379|Unilever
        731049|Everyday
        692554|Doritos
        692453|Ferrero
        230202|Easy Care
        853095|Varex
        693048|El Marai
        692434|Galaxy
        394351|Queen
        953044|Twitch
        711322|حبة حبة
        692516|Cheetos
        692424|Holw EL-SHAM
        731058|Rose Tea
        752049|Aslan
        692402|Abu Auf
        848044|Cetris
        927059|kyds
        883047|Lambada
        717046|Freezen
        692438|Hyat
        888044|El kamar
        711305|جانو
        254343|Heinz
        731059|Savana
        692407|El Walely
        692509|Bonjorno
        731045|Americana
        849053|Funday
        819044|haroun coffee
        934047|Sesic
        731044|Alearusa Tea
        711398|غصون
        883048|Lotus
        692567|Raw
        711396|عماد افندى
        858044|EAU
        724050|أصالة
        896046|Spuds
        779046|Al karm
        693050|Alkhair
        962044|Tresemme
        929044|Speed
        693052|Sharshar
        733044|Zadna
        693046|iSiS
        923044|River Foods
        829044|Merano
        925051|Haj Arafa
        692429|Wadi Food
        731057|Redbull
        825044|V7
        692436|Egypt Treat
        692371|Rani
        896047|Ponky
        692465|fodo
        805045|Donlopz
        861044|Teeka fun
        879044|Al Moalem
        722052|Labanita
        752048|Puvana
        724044|العميد
        151081|Bisco Misr
        692468|UGO

This is all companies name in [MASTER_BRAND]

MG2 (Category) — Use textual part only:
...
"""

# =========================
# Session State (Chat)
# =========================
if "chat_history" not in st.session_state:
    # Each entry: {"role": "user"/"assistant", "content": str, "sql": Optional[str], "df": Optional[pd.DataFrame], "raw": Optional[str]}
    st.session_state.chat_history = []

# Sidebar: tools
with st.sidebar:
    st.markdown("### Tools")
    clear = st.button("🧹 Clear Conversation")
    if clear:
        st.session_state.chat_history = []
        st.rerun()

    debug_mode = False
    if st.session_state[BI_KEY]:
        debug_mode = st.toggle("🔎 BI Debug Mode (show raw LLM output)", value=False, help="BI only")

# =========================
# Replay History
# =========================
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if st.session_state[BI_KEY] and msg.get("sql"):
            with st.expander("View SQL"):
                st.code(msg["sql"], language="sql")
        if isinstance(msg.get("df"), pd.DataFrame) and not msg["df"].empty:
            # Export buttons
            with st.container():
                col_a, col_b = st.columns([1, 1])
                csv = msg["df"].to_csv(index=False).encode("utf-8-sig")
                with col_a:
                    st.download_button("⬇️ Download CSV", data=csv, file_name="results.csv", mime="text/csv", key=f"csv_{id(msg)}")
                # XLSX
                with io.BytesIO() as output:
                    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                        msg["df"].to_excel(writer, index=False, sheet_name="Results")
                    xlsx_data = output.getvalue()
                with col_b:
                    st.download_button("⬇️ Download Excel", data=xlsx_data, file_name="results.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"xlsx_{id(msg)}")

            st.dataframe(msg["df"])

        if st.session_state[BI_KEY] and debug_mode and msg.get("raw"):
            with st.expander("LLM Raw Output (Debug)"):
                st.text(msg["raw"])

# =========================
# Chat Input & Handling
# =========================
user_input = st.chat_input("Ask your question in Arabic or English")
if user_input:
    # Show user message immediately
    st.chat_message("user").markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Generating SQL and executing... ⏳"):
            try:
                # Build prompt
                full_prompt = f"{Schema_description()}\n\n{user_input}"

                # Call Gemini
                model = genai.GenerativeModel("gemini-2.5-flash")
                response = model.generate_content(full_prompt)

                # Extract SQL robustly
                raw_output = ""
                try:
                    raw_output = response.text if hasattr(response, "text") and response.text else str(response)
                except Exception:
                    raw_output = str(response)

                sql_query = sanitize_and_extract_sql_from_gemini(response)

                if not sql_query:
                    raise ValueError("Empty SQL returned from model.")

                # Safety check: SELECT only
                if not is_safe_select(sql_query):
                    raise ValueError("Generated SQL failed safety check (SELECT-only policy).")

                # Execute SQL
                df = execute_query_safe(conn, sql_query)

                # Prepare assistant reply
                reply_text = "Here are your results:"
                st.markdown(reply_text)

                if st.session_state[BI_KEY]:
                    with st.expander("View SQL"):
                        st.code(sql_query, language="sql")

                if not df.empty:
                    # Quick exports for fresh result
                    col_a, col_b = st.columns([1, 1])
                    csv = df.to_csv(index=False).encode("utf-8-sig")
                    with col_a:
                        st.download_button("⬇️ Download CSV", data=csv, file_name="results.csv", mime="text/csv")
                    with io.BytesIO() as output:
                        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                            df.to_excel(writer, index=False, sheet_name="Results")
                        xlsx_data = output.getvalue()
                    with col_b:
                        st.download_button("⬇️ Download Excel", data=xlsx_data, file_name="results.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                    st.dataframe(df)
                else:
                    st.info("No data returned for this query.")

                # Save to history (user + assistant)
                st.session_state.chat_history.append({"role": "user", "content": user_input})
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": reply_text,
                    "sql": sql_query if st.session_state[BI_KEY] else None,
                    "df": df,
                    "raw": raw_output if (st.session_state[BI_KEY] and debug_mode) else None
                })

            except Exception as e:
                error_text = f"❌ Failed to generate SQL. Reason: {str(e)}"
                st.error(error_text)
                st.session_state.chat_history.append({"role": "assistant", "content": error_text})

# #import necessary libraries
# # This code is for a Streamlit app that uses Google Generative AI to answer SQL queries
# import streamlit as st
# import google.generativeai as genai
# import pyodbc
# import pandas as pd
# from dotenv import load_dotenv
# import os
# import base64
# from io import BytesIO
# from time import time


# # Load API key from .env
# # API key should be set in a .env file
# # load_dotenv()
# genai.configure(api_key=st.secrets["API"]["GOOGLE_API_KEY"])
# # Load from secrets.toml

# Credentials = st.secrets["auth"]
# BI_PASSWORD = st.secrets["auth"]["BI_PASSWORD"]
# BI_KEY = st.secrets["auth"]["BI_KEY"]
# TRADE_PASSWORD = st.secrets["auth"]["TRADE_PASSWORD"]
# TRADE_KEY = st.secrets["auth"]["TRADE_KEY"]
# # gemini_API = 

# # Initialize session states
# if BI_KEY not in st.session_state:
#     st.session_state[BI_KEY] = False
# if TRADE_KEY not in st.session_state:
#     st.session_state[TRADE_KEY] = False

# # Authentication check
# if not st.session_state[BI_KEY] and not st.session_state[TRADE_KEY]:
#     st.title("🔐 Secure Access to Sanad Chatbot")
#     password = st.text_input("Enter password to access", type="password")
#     if st.button("Login"):
#         if password == BI_PASSWORD:
#             st.session_state[BI_KEY] = True
#             st.rerun()
#         elif password == TRADE_PASSWORD:
#             st.session_state[TRADE_KEY] = True
#             st.rerun()
#         else:
#             st.error("Incorrect password ❌")
#     st.stop()

# # If authenticated, proceed with the app
# if st.session_state[BI_KEY]:
#     st.title("💬 BI Chatbot - BI Access")
# elif st.session_state[TRADE_KEY]:
#     st.title("💬 BI Chatbot - Trade Access")

# # Display a welcome message
# st.markdown("Welcome to Our Chatbot! Ask your SQL queries and get answers in real-time.")
# # Display logo at the top
# col1, col2, col3 = st.columns([1, 2, 1])
# with col2:
#     st.image("logoo.png", width=200)


# # Function to connect to the SQL Server database

# @st.cache_resource
# def connect_db():
#     db_config = st.secrets["database"]
#     connection_string = (
#         f"DRIVER={{{db_config['driver']}}};"
#         f"SERVER={db_config['server']};"
#         f"DATABASE={db_config['database']};"
#         f"UID={db_config['username']};"
#         f"PWD={db_config['password']}"
#     )
#     return pyodbc.connect(connection_string)

# # Usage
# conn = connect_db()







# def Schema_description ():
# # Define schema-aware base prompt
#     return """
# You are a SQL expert for an e-commerce database with three main tables: MP_Sales, MP_Customers, and MP_Items.
# Your job is to generate valid SQL Server SELECT queries only based on user requests, following these exact rules:

# Database Schema Overview:

# MP_Sales (Sales Transactions)

# Joins:
# MP_Sales.CustomerID = MP_Customers.SITE_NUMBER
# MP_Sales.ItemId = MP_Items.ITEM_CODE

# Important Columns:
# Date (YYYY-MM-DD) — transaction date
# Netsalesvalue — sales value after tax/discounts
# SalesQtyInPieces, SalesQtyInCases, order_Number
# ItemId, CustomerID — for joins
# Master_brand, sub_brand, brandname, Sales_Channel, itemname
# project_id, company, Org_ID, InvoiceId

# Rules:

# Do not use month column; extract month from Date if needed.

# Always round sales values using ROUND(Netsalesvalue, 0).

# MP_Customers (Customer Master)

# Joins: MP_Sales.CustomerID = MP_Customers.SITE_NUMBER

# Important Columns:
# GOVERNER_NAME, CUSTOMER_B2B_ID, CUSTOMER_NAME, SALES_CHANNEL_CODE,
# SECTION_TYPE, CUSTOMER_NUMBER, CITY_NAME, AREA_NAME,
# LOCATION, ADDRESS1, SITE_NUMBER, ACCOUNT_CREATION_DATE, SITE_CREATION_DATE

# Rules:

# Valid governorate filter: use GOVERNER_NAME.

# If user asks "active customers" → customers with purchases/orders.

# If user asks "active net customers" → customers with Netsalesvalue > 1.

# If user says "net active" or just "active" in general → return total count only, not list.

# If filtered by company or other attribute → return total count per that attribute.

# MP_Items (Product Master)

# Joins: MP_Sales.ItemId = MP_Items.ITEM_CODE

# Important Columns:
# ITEM_CODE, DESCRIPTION, MASTER_BRAND, MG2, MG3, GCOMPANY, GFORM, GSIZE, MSU, CONVERSION_RATE

# Rules:

# MASTER_BRAND format: code|brandname.

# Brand name: RIGHT(MASTER_BRAND, LEN(MASTER_BRAND) - CHARINDEX('|', MASTER_BRAND))

# Brand code: LEFT(MASTER_BRAND, CHARINDEX('|', MASTER_BRAND) - 1)

# MG2 format: code|category. Extract only category name.

# To filter by company:

# WHERE LEFT(MASTER_BRAND, CHARINDEX('|', MASTER_BRAND) - 1) = '<first 6 digits>'


# General Query Requirements:

# Always use MP_Sales.Date for date filtering.

# Always join to CUSTOMER_B2B_ID when query is about customers.

# If a company filter is requested, match on the MASTER_BRAND code.

# Extract readable brand/category names when returning them.

# and this the lsited companies or MASTER_BRAND

# Use LEFT(MASTER_BRAND, CHARINDEX('|', MASTER_BRAND) - 1) to extract brand code

#         724046|موندليز
#         853046|Zewoo
#         692399|abo dawod
#         692425|Queen Packaging
#         849054|ILOU
#         876045|RC
#         692376|Coca Cola
#         812044|Rehana
#         692471|GLLOPAL
#         921140|Al Raheeq Al Makhtum
#         694044|MP_P&G
#         811044|El Sohagy
#         692383|EL Masrayia oils
#         874044|Mazaq
#         827044|Fay
#         692381|Mansour
#         692561|Sun Bites
#         928166|Blu
#         945045|ONa
#         750045|Soudanco
#         692786|Relax
#         730044|Haboba
#         692405|add me
#         892070|Crunchy
#         883050|Razz
#         692803|Ragon
#         897044|Bonz
#         787044|lipton
#         805046|Maram
#         818044|Afandy
#         883051|Star Bar
#         693045|Halwani Brothers
#         707045|Edafco
#         892069|Chipsy
#         693047|ELMALEKA
#         751044|Abo Taleb
#         692366|EL Gayar
#         969044|Safe
#         883046|Halwani Brothers Maamoal
#         716045|Boshrt kheir
#         790047|Classique coffee
#         956044|Sparx
#         692652|Pantene
#         692428|Ayman Afandy
#         731050|Go Mix
#         692385|Indomie
#         692378|Lamar
#         692689|kingo
#         799044|Kelloggs Noodels
#         921138|Chefy Mix
#         692455|Vatika
#         692414|Elshamadan
#         782044|Soft Rose
#         692765|Bebeto
#         772044|Mondelez
#         752045|Roll Plast
#         692446|Pyrosol
#         804044|Class A
#         731054|Mimco
#         692353|TTC
#         693049|Shaheen Coffee
#         692373|Zeina
#         692454|Ahmed El Sheikh Coffee
#         692441|Fine
#         692469|S2
#         692431|Vacakis Cafe
#         928165|Clean way
#         692612|Hayat
#         692704|Haribo
#         693053|Sima
#         692705|Saula
#         951044|Drova
#         692559|Rhodes
#         747044|Nawara foods
#         731047|Coffee break
#         692457|Kamara
#         796044|Arma soap
#         692486|Sun shine
#         957045|Hmto
#         692359|HABIBCO
#         693058|Johnson
#         970044|Yes
#         692388|Sun Top
#         968044|kaline
#         692380|Arma
#         692375|IFFCO
#         692427|Mass Foods
#         785044|Al ahlam
#         961045|Sparkel
#         711376|سيما
#         573349|Silo
#         847044|Double Dare
#         692356|Al Mufaddal
#         881044|Larch
#         850045|Twevel
#         856046|Twist
#         692411|Bill Egypt
#         722048|Cairo group
#         752044|Elshanawany
#         692466|alfnar
#         844044|4M
#         731056|Qutuf
#         742044|Xera_FreeGoods
#         722047|Elhana
#         NULL
#         876044|Snaps
#         822044|AL Tahhan
#         692460|4A Nutrition
#         878044|Dilmah
#         692461|arfa
#         794044|Weals
#         888046|Signal
#         791044|Aje Group
#         849051|Astra
#         945044|Carlito
#         876046|Double Break
#         783046|Reckitt
#         6171|Head & Shoulders
#         692397|AM Group
#         849052|Milka
#         842044|Tiba Trade
#         692410|Rosso
#         875044|Rich Bake
#         692416|Edco
#         180829|Domty
#         693044|Dream
#         692456|Al-Shahin
#         792044|Milano
#         849050|Mousi
#         928167|Bashayer
#         692569|Bravo
#         692394|Obour Land
#         692409|Flamenco co
#         692386|Regina
#         692467|Elasi
#         949044|Al Sultan 
#         692451|LaRose
#         693056|EL Marai
#         802044|AL Arabia Oil
#         1875|Default
#         692370|PEPSICO
#         929046|Blanco
#         836044|Albader
#         724045|إيفرجو
#         937044|Yoodles
#         966045|Alex
#         692354|Green plant
#         693051|White
#         692587|Karate
#         692391|Savola
#         722046|Coolest Bottle
#         692392|AL SHARQ
#         692355|Edita
#         745044|Valley Water
#         692730|Energizer
#         937057|Best
#         722051|Green land
#         954044|EL Abd
#         847045|Magic
#         692437|Ulker
#         778044|Zeyada
#         692418|Hero/Vitrac
#         748044|Lana Tex
#         951048|Maxi
#         736044|United oils
#         728047|Elzaeem
#         692572|Clorox
#         722044|Cairo Oil
#         692695|Pringles
#         692694|Mentos
#         818045|Daima
#         731051|Hawaa
#         692432|Crush
#         728045|ELkhatab
#         692384|El Anany
#         692412|United Distributors
#         692377|El-Zomoroda
#         692408|Senyorita
#         692439|Evyap
#         731048|Emad Effendi
#         693054|Aljawhara
#         692406|El Bawadi
#         711224|الريحان
#         820044|AL Kbous Tea
#         692660|Tolido
#         731055|Pafitos
#         692358|Al-Buraq
#         711399|غندور
#         711332|دامور
#         893044|Close Up
#         850044|Hatlou
#         692413|Egypt Foods
#         692458|Ekhnaton
#         883045|Fitness
#         692401|Al Yemeni Cafe
#         718045|Inactive
#         824044|Rhone Tech
#         692369|Juhayna
#         692721|Pretzels
#         692372|Nestle
#         692423|R.M Trade
#         722050|Alporsaideya
#         737044|Elkholy
#         847046|Magical
#         894045|Kit Kat
#         692363|Lametna
#         808044|Tag Elmelouk
#         883049|L'usin
#         810044|Mansour Eltiti
#         692435|Corona
#         711417|قطوف
#         692387|El Doha
#         795044|Egy Bella
#         692393|wapco
#         821044|Rabea Tea
#         711223|الرشيدى الميزان
#         790044|El Ahram
#         722045|Gefco
#         692422|IMTENAN
#         929045|Good Clean
#         809044|EL omda
#         711420|ايزيس
#         883044|Coco Bobs
#         692379|Unilever
#         731049|Everyday
#         692554|Doritos
#         692453|Ferrero
#         230202|Easy Care
#         853095|Varex
#         693048|El Marai
#         692434|Galaxy
#         394351|Queen
#         953044|Twitch
#         711322|حبة حبة
#         692516|Cheetos
#         692424|Holw EL-SHAM
#         731058|Rose Tea
#         752049|Aslan
#         692402|Abu Auf
#         848044|Cetris
#         927059|kyds
#         883047|Lambada
#         717046|Freezen
#         692438|Hyat
#         888044|El kamar
#         711305|جانو
#         254343|Heinz
#         731059|Savana
#         692407|El Walely
#         692509|Bonjorno
#         731045|Americana
#         849053|Funday
#         819044|haroun coffee
#         934047|Sesic
#         731044|Alearusa Tea
#         711398|غصون
#         883048|Lotus
#         692567|Raw
#         711396|عماد افندى
#         858044|EAU
#         724050|أصالة
#         896046|Spuds
#         779046|Al karm
#         693050|Alkhair
#         962044|Tresemme
#         929044|Speed
#         693052|Sharshar
#         733044|Zadna
#         693046|iSiS
#         923044|River Foods
#         829044|Merano
#         925051|Haj Arafa
#         692429|Wadi Food
#         731057|Redbull
#         825044|V7
#         692436|Egypt Treat
#         692371|Rani
#         896047|Ponky
#         692465|fodo
#         805045|Donlopz
#         861044|Teeka fun
#         879044|Al Moalem
#         722052|Labanita
#         752048|Puvana
#         724044|العميد
#         151081|Bisco Misr
#         692468|UGO

#         This is all companies name in [MASTER_BRAND]

#     MG2 (Category) — Use textual part only:

#     720044|المشروبات الباردة, 720046|البسكويت والحلويات, 718049|المنظفات و أدوات المنزل, etc.
#         MG2 values are:
#     720046|البسكويت والحلويات
#     841044|بقوليات و توابل
#     720048|منتجات العناية الشخصية
#     720050|المنتجات التموينية (البقالة)
#     NULL
#     718047|المياه
#     1875|Default
#     720044|المشروبات الباردة
#     720049|الشييسي و المقرمشات
#     711054|منتجات البان
#     720047|المعلبات و المأكولات
#     934046|الورقيات و الحفاضات
#     718049|المنظفات و أدوات المنزل
#     720045|المشروبات الساخنة


# Task:
# When I give you a natural language request, return only the SQL Server SELECT query that satisfies it, following all above schema details and business rules. Do not explain unless I ask.
#     """



# # Initialize session state to hold questions
# if "query_boxes" not in st.session_state:
#     st.session_state.query_boxes = [""]
# if "query_count" not in st.session_state:
#     st.session_state.query_count = 1

# def add_query_box():
#     st.session_state.query_boxes.append("")
#     st.session_state.query_count += 1

# def add_query_box():
#     st.session_state.query_boxes.append("")
#     st.session_state.query_count += 1
#     st.session_state.results.append(None)  # add empty result slot

# # Initialize session state for results if not already
# if "results" not in st.session_state:
#     st.session_state.results = [None] * st.session_state.query_count

# # Iterate over each query box
# for idx in range(st.session_state.query_count):
#     with st.container():
#         query_key = f"query_{idx}"
#         run_key = f"run_{idx}"

#         user_question = st.text_input(f"Query {idx + 1}:", key=query_key, placeholder="قولي عايز تسأل علي أي")

#         if st.button(f"جرب كده", key=run_key):
#             if not user_question.strip():
#                 st.warning("جرب شوف عايز تسأل علي أي")
#             else:
#                 with st.spinner("هشوف واقولك..."):
#                     try:
#                         full_prompt = f"{Schema_description()}\n\n{user_question}"
#                         model = genai.GenerativeModel("gemini-2.5-flash")
#                         response = model.generate_content(full_prompt)
#                         sql_query = response.text.strip().strip("```sql").strip("```")

#                         df = pd.read_sql(sql_query, conn)
#                         with st.expander(f"✅ Result for Query {idx + 1}"):
#                             if st.session_state[BI_KEY]:
#                                 st.code(sql_query, language="sql")
#                             else:
#                                 "Results are excuted "

#                         # Save result in session state
#                         if len(st.session_state.results) <= idx:
#                             st.session_state.results.append(df)
#                         else:
#                             st.session_state.results[idx] = df

#                     except Exception as e:
#                         st.session_state.results[idx] = None
#                         st.error(f"❌ Error: {e}")

#         # Display previously stored result (if any)

#         if idx < len(st.session_state.results) and st.session_state.results[idx] is not None:
#             st.dataframe(st.session_state.results[idx])


# st.button("➕ Add New Query", on_click=add_query_box)

