
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

# Function to load and inject CSS
def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Call it at the start of your app
load_css("style.css")


st.set_page_config(page_title="Sanad BI Chatbot", page_icon="💬", layout="wide")

# --- Load API Key ---
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# =========================
# Authentication
# =========================
BI_PASSWORD = st.secrets["auth"]["BI_PASSWORD"]
BI_KEY = st.secrets["auth"]["BI_KEY"]
TRADE_PASSWORD = st.secrets["auth"]["TRADE_PASSWORD "]
TRADE_KEY =st.secrets["auth"]["TRADE_KEY"]


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

    # --- Case 1: response.text exists ---
    if getattr(response, "text", None):
        raw = response.text

    # --- Case 2: fallback to candidates.parts ---
    elif hasattr(response, "candidates") and response.candidates:
        try:
            parts = response.candidates[0].content.parts
            raw = "".join(getattr(p, "text", "") for p in parts if getattr(p, "text", None))
        except Exception:
            raw = ""

    # --- Case 3: ultimate fallback ---
    if not raw:
        raw = str(response)

    # --- Clean fences like ```sql ... ``` ---
    raw = raw.strip()
    match = re.search(r"```sql\s*([\s\S]+?)```", raw, flags=re.IGNORECASE)
    if not match:
        match = re.search(r"```\s*([\s\S]+?)```", raw, flags=re.IGNORECASE)

    sql = (match.group(1) if match else raw).strip()
    return sql

def get_previous_results_summary():
    """Generate a summary of previous results available for reference."""
    if not st.session_state.chat_history:
        return ""
    
    summary = "\n=== PREVIOUS QUERY RESULTS AVAILABLE FOR REFERENCE ===\n"
    result_count = 0
    
    for i, msg in enumerate(st.session_state.chat_history):
        if msg.get("role") == "assistant" and isinstance(msg.get("df"), pd.DataFrame) and not msg["df"].empty:
            result_count += 1
            df = msg["df"]
            
            # Get the previous user question for context
            user_question = ""
            if i > 0 and st.session_state.chat_history[i-1].get("role") == "user":
                user_question = st.session_state.chat_history[i-1]["content"]
            
            summary += f"\nResult #{result_count}:\n"
            summary += f"- User Question: {user_question}\n"
            summary += f"- Columns: {', '.join(df.columns.tolist())}\n"
            summary += f"- Row Count: {len(df)}\n"
            summary += f"- Sample Data (first 2 rows):\n{df.head(2).to_string()}\n"
            
            if msg.get("sql"):
                summary += f"- SQL Used: {msg['sql']}\n"
    
    if result_count == 0:
        return ""
    
    summary += f"\n=== END PREVIOUS RESULTS (Total: {result_count} datasets available) ===\n"
    summary += "\nIMPORTANT: If the user asks to analyze, filter, or work with 'previous results', 'last results', or 'the data above', you should reference the most recent result dataset. You can perform operations like filtering, grouping, calculations on the previous results by understanding their structure from the summary above.\n"
    
    return summary

def create_analysis_query_from_previous_results(user_request, previous_df, previous_sql, previous_question):
    """
    Generate a new SQL query that builds upon previous results.
    This function helps create queries that reference or analyze previous data.
    """
    if previous_df is None or previous_df.empty:
        return None
    
    # Create a summary of the previous results
    cols_info = ", ".join([f"{col} ({previous_df[col].dtype})" for col in previous_df.columns])
    
    analysis_prompt = f"""
Based on the user's new request: "{user_request}"

The user wants to work with previous results that have these characteristics:
- Previous Question: {previous_question}
- Previous SQL: {previous_sql}
- Columns Available: {cols_info}
- Row Count: {len(previous_df)}
- Sample Data:
{previous_df.head(3).to_string()}

Generate a NEW SQL query that would produce similar results to what the user is asking for based on the previous data structure and their new request. 


"""
    
    return analysis_prompt

# =========================
# Schema Prompt
# =========================
def Schema_description():
    # >>> Paste your full schema/business-rules prompt here <<<
    return """
You are a SQL expert... Your job is to generate valid SQL Server SELECT queries.

## Database Schema Overview

### MP_Sales (Sales Transactions)
- **Joins**: `MP_Sales.CustomerID = MP_Customers.SITE_NUMBER` and `MP_Sales.ItemId = MP_Items.ITEM_CODE`
- **Important Columns**: `Date`, `Netsalesvalue`, `SalesQtyInPieces`, `ItemId`, `CustomerID` ,  `SalesQtyInCases`. `Order_Number`
- **Rules**:
  1. Do not use the `month` column; extract month from `Date` if needed (e.g., `MONTH(Date)`).
  2. Always format sales values using `ROUND(s.Netsalesvalue, 0)`.
  3. For brand information, always join with the `MP_Items` table; do not use `Master_brand` from `mp_sales`.
  4. use SalesQtyInCases if i asked on cases or asked in arabic علي كراتين

### MP_Customers (Customer Master)
- **Joins**: `MP_Sales.CustomerID = MP_Customers.SITE_NUMBER`
- **Important Columns**: `GOVERNER_NAME`, `CUSTOMER_B2B_ID`, `CUSTOMER_NAME`.
- **Rules**:
  1. For "active customers", count customers with purchases.
  2. For "net active customers", count customers with `Netsalesvalue > 1`.
  3. When filtering by an attribute, format the count like this: `FORMAT(COUNT(DISTINCT CUSTOMER_B2B_ID), 'N0')`.


Rules:

Valid governorate filter: use GOVERNER_NAME.

### MP_Items (Product Master)

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

720046|البسكويت والحلويات
841044|بقوليات و توابل
720048|منتجات العناية الشخصية
720050|المنتجات التموينية (البقالة)
NULL
718047|المياه
1875|Default
720044|المشروبات الباردة
720049|الشييسي و المقرمشات
711054|منتجات البان
720047|المعلبات و المأكولات
934046|الورقيات و الحفاضات
718049|المنظفات و أدوات المنزل
720045|المشروبات الساخنة

this is listed MG3


786044|مزيل بقع
719050|شوكولاتة
719056|مشروبات سريعة الذوبان
719067|خل وماء ورد
719044|حليب خالي الدسم
851045|عسل و طحينة
711146|مسحوق غسيل
719061|فول ومعلبات
826045|بادى سبلاش
719075|معطر جو
859044|العناية بالجسم
719062|مخللات
711121|قهوة
846045|مرقات و خلطات
711067|بطاريات
711066|بسكويت
719068|زيت وسمن
719080|جل معقم
711073|تونة
719086|مستحضرات تجميل
711094|سحلب
846047|كاكاو و فرابيه
820045|صوص طعام
711178|دقيق
719049|مشروب زبادي
711101|شاي
711173|نسكافية
948044|قهوه مثلجه
719083|فوط صحية
719074|مطهر
719048|لبن بودر
NULL
718047|المياه
719077|منظف اطباق
711165|ملمع
711151|مشروبات غازية
719054|مخبوزات مقرمشة
711102|شرائح بطاطس
1875|Default
719071|فويل المونيوم
719076|منظف
851044|مستلزمات حلويات
804045|وافل
719073|مستلزمات المطبخ
711084|رايب
711090|زيت
711164|ملح
711097|سكر
711064|اكياس
711079|حلاوة
846048|اسبرسو
711150|مشروبات طاقة
719053|مصاصة
711176|نودلز
711141|مربي
711163|مكرونة
719078|حفاضات
711108|صلصة
875045|حبوب و مخبوزات
719051|لبان و بونبون
711057|اجبان
711124|كرواسون
711107|صابون
719052|جيلي مارشيملو
711112|عصائر
888045|العنايه بالاسنان
711058|ارز
719079|العناية بالشعر
936045|مناديل مبلله
936046|الحفاضات
846046|صوص حلو
719084|كريم مرطب
711162|مقرمشات
711098|سمن
719082|غسول للايدي
846044|توابل
719072|مبيد حشري
711062|اعشاب
719047|حليب نكهات
711087|زبادي
820046|كاتشب ومايونيز
711159|معمول
719045|حليب كامل الدسم
845044|البقوليات
719085|ماسك للوجه
852047|تمور
719070|جل منظف
936044|المناديل
711132|كيك
719057|مشروبات شعير
719060|سبريد
719046|حليب نصف دسم
719055|شربات

use it if i asked in arabic on one of them 
and use N before in arabic filter


AND USE MASTER_BRAND in items for compaines
...
"""

# =========================
# Initialize session state for chat history and result tracking
if "chat_history" not in st.session_state:
    # Each entry: {"role": "user"/"assistant", "content": str, "sql": Optional[str], "df": Optional[pd.DataFrame], "query_id": Optional[str]}
    st.session_state.chat_history = []

if "query_counter" not in st.session_state:
    st.session_state.query_counter = 0

# Sidebar: tools and previous results info
with st.sidebar:
    st.markdown("### Tools")
    clear = st.button("🧹 Clear Conversation")
    if clear:
        st.session_state.chat_history = []
        st.session_state.query_counter = 0
        st.rerun()

    # 🧠 Enable/Disable memory
    use_memory = st.toggle("🧠 Enable Chat Memory", value=True)
    
    # Show available previous results
    st.markdown("### 📊 Previous Results")
    result_datasets = []
    for i, msg in enumerate(st.session_state.chat_history):
        if msg.get("role") == "assistant" and isinstance(msg.get("df"), pd.DataFrame) and not msg["df"].empty:
            # Get the previous user question for context
            user_question = ""
            if i > 0 and st.session_state.chat_history[i-1].get("role") == "user":
                user_question = st.session_state.chat_history[i-1]["content"][:50] + "..."
            result_datasets.append({
                "index": len(result_datasets) + 1,
                "question": user_question,
                "rows": len(msg["df"]),
                "columns": len(msg["df"].columns)
            })
    
    if result_datasets:
        for dataset in result_datasets:
            st.markdown(f"""
            <div class="previous-results-info">
                <strong>Dataset #{dataset['index']}</strong><br>
                <small>{dataset['question']}</small><br>
                📊 {dataset['rows']} rows, {dataset['columns']} columns
            </div>
            """, unsafe_allow_html=True)
        st.markdown("💡 **Tip:** You can reference these results in new queries by saying things like 'filter the last results', 'group the previous data', or 'show me more details about the data above'.")
    else:
        st.markdown("*No previous results available*")

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
            st.dataframe(msg["df"])

# =========================
# Chat Input & Handling
# =========================
user_input = st.chat_input("Ask your question in Arabic or English, or reference previous results")

if user_input:
    # Save user message immediately
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    st.chat_message("user").markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Generating SQL and executing... ⏳"):
            try:
                # Check if user is referencing previous results
                reference_keywords = [
                    "previous", "last", "above", "earlier", "before", "that data", "those results",
                    "the data", "this data", "same data", "filter", "group", "analyze",
                    "السابق", "البيانات", "النتائج", "المعلومات"
                ]
                
                is_referencing_previous = any(keyword.lower() in user_input.lower() for keyword in reference_keywords)
                
                # Get the most recent result dataset
                last_result_df = None
                last_result_sql = None
                last_user_question = None
                
                for i in range(len(st.session_state.chat_history) - 2, -1, -1):  # Start from second-to-last (skip current user message)
                    msg = st.session_state.chat_history[i]
                    if msg.get("role") == "assistant" and isinstance(msg.get("df"), pd.DataFrame) and not msg["df"].empty:
                        last_result_df = msg["df"]
                        last_result_sql = msg.get("sql", "")
                        # Find the corresponding user question
                        if i > 0 and st.session_state.chat_history[i-1].get("role") == "user":
                            last_user_question = st.session_state.chat_history[i-1]["content"]
                        break

                # ---- Build conversational prompt ----
                if use_memory:
                    history_text = ""
                    for msg in st.session_state.chat_history:
                        history_text += f"{msg['role'].upper()}: {msg['content']}\n"
                        if msg.get("sql"):
                            history_text += f"SQL_USED: {msg['sql']}\n"
                    conversation_context = history_text
                else:
                    # Only last message
                    conversation_context = f"USER: {user_input}\n"

                # Add previous results summary if memory is enabled or user is referencing previous data
                previous_results_info = ""
                if use_memory or is_referencing_previous:
                    previous_results_info = get_previous_results_summary()

                # Special handling for queries that reference previous results
                if is_referencing_previous and last_result_df is not None:
                    # Create a specialized prompt for analyzing previous results
                    analysis_prompt = create_analysis_query_from_previous_results(
                        user_input, last_result_df, last_result_sql, last_user_question
                    )
                    
                    full_prompt = f"""
You are a SQL assistant with access to previous query results.

Database Schema & Business Rules:
{Schema_description()}

{previous_results_info}

{analysis_prompt}

The user is asking: "{user_input}"

Based on the previous results structure and the user's request, generate a NEW SQL query that addresses what they're asking for.

Write ONLY the SQL query (no explanation).
"""
                else:
                    # Regular prompt
                    full_prompt = f"""
You are a SQL assistant with memory.
Your job is to generate valid SQL Server SELECT queries based on user requests.

If the user refers to something from the past (like 'same as before', 'previous query', 'change month', 'for brand X instead'), 
use the chat history below to understand the context.

Database Schema & Business Rules:
{Schema_description()}

{previous_results_info}

Conversation Context:
{conversation_context}

Now write ONLY the SQL query (no explanation) that answers the last USER question.
"""

                # Call Gemini
                model = genai.GenerativeModel("gemini-2.5-flash")
                response = model.generate_content(full_prompt)

                # Extract SQL
                sql_query = sanitize_and_extract_sql_from_gemini(response)
                if not sql_query:
                    raise ValueError("Empty SQL returned from model.")
                if not is_safe_select(sql_query):
                    raise ValueError("Generated SQL failed safety check (SELECT-only policy).")
                conn =connect_db()
                # Execute SQL
                df = execute_query_safe(conn, sql_query)

                # Increment query counter
                st.session_state.query_counter += 1
                query_id = f"query_{st.session_state.query_counter}"

                # Assistant reply with context about previous results if applicable
                if is_referencing_previous and last_result_df is not None:
                    reply_text = f"Here are your results based on the previous data analysis:"
                else:
                    reply_text = "Here are your results:"
                
                st.markdown(reply_text)

                if st.session_state[BI_KEY]:
                    with st.expander("View SQL"):
                        st.code(sql_query, language="sql")

                if not df.empty:
                    # Show comparison info if referencing previous results
                    if is_referencing_previous and last_result_df is not None:
                        col_info1, col_info2 = st.columns(2)
                        with col_info1:
                            st.info(f"📊 **Current Results:** {len(df)} rows, {len(df.columns)} columns")
                        with col_info2:
                            st.info(f"📋 **Previous Results:** {len(last_result_df)} rows, {len(last_result_df.columns)} columns")

                    # Export buttons
                    col_a, col_b = st.columns([1, 1])
                    csv = df.to_csv(index=False).encode("utf-8-sig")
                    with col_a:
                        st.download_button("⬇️ Download CSV", data=csv,
                                           file_name=f"results_{query_id}.csv", mime="text/csv")
                    with io.BytesIO() as output:
                        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                            df.to_excel(writer, index=False, sheet_name="Results")
                        xlsx_data = output.getvalue()
                    with col_b:
                        st.download_button("⬇️ Download Excel", data=xlsx_data,
                                           file_name=f"results_{query_id}.xlsx", 
                                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                    st.dataframe(df)
                    
                    # Show helpful suggestions for further analysis
                    # if len(df) > 0:
                    #     st.markdown("---")
                    #     st.markdown("💡 **What you can do next:**")
                    #     suggestions = [
                    #         "Filter these results by a specific criteria",
                    #         "Group this data differently", 
                    #         "Show trends over time from this data",
                    #         "Find the top performers in these results",
                    #         "Compare these results with a different time period"
                    #     ]
                    #     for i, suggestion in enumerate(suggestions, 1):
                    #         st.markdown(f"{i}. {suggestion}")
                else:
                    st.info("No data returned for this query.")

                # Save assistant response to history with query ID
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": reply_text,
                    "sql": sql_query if st.session_state[BI_KEY] else None,
                    "df": df,
                    "query_id": query_id,
                })

            except Exception as e:
                error_text = f"❌ Failed to generate SQL. Reason: {str(e)}"
                st.error(error_text)
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": error_text,
                    "sql": None,
                    "df": pd.DataFrame(),
                    "query_id": None,
                })
