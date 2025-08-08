#import necessary libraries
# This code is for a Streamlit app that uses Google Generative AI to answer SQL queries
import streamlit as st
import google.generativeai as genai
import pyodbc
import pandas as pd
from dotenv import load_dotenv
import os
import base64
from io import BytesIO
from time import time

if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.warning("🔒 Please login first from the Home page.")
    st.stop()
# Load API key from .env
# API key should be set in a .env file
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

st.header("This is a Sanad BI Chatbot , only for BI developers and Trade users if access is granted")
# Authentication for BI and Trade access
# This is for the BI access
BI_PASSWORD = "BI_admin"  
BI_key = "auth_bi"
# Trade password and key
# This is for the Trade access
Trade_password = "Trade_admin" 
TRADE_key = "auth_trade"

if BI_key not in st.session_state:
    st.session_state[BI_key] = False
if TRADE_key not in st.session_state:
    st.session_state[TRADE_key] = False

if not st.session_state[BI_key] and not st.session_state[TRADE_key]:
    st.title("🔐 Secure Access to Sanad Chatbot")
    password = st.text_input("Enter password to access", type="password")
    if st.button("Login"):
        if password == BI_PASSWORD:
            st.session_state[BI_key] = True
            st.rerun()
        elif password == Trade_password:
            st.session_state[TRADE_key] = True
            st.rerun()
        else:
            st.error("Incorrect password ❌")
    st.stop()
# If authenticated, proceed with the app
if st.session_state[BI_key]:
    st.title("💬 BI Chatbot - BI Access")
elif st.session_state[TRADE_key]:
    st.title("💬 BI Chatbot - Trade Access")
# Display a welcome message
st.markdown("Welcome to Our Chatbot! Ask your SQL queries and get answers in real-time.")







# Display logo at the top
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image("logoo.png", width=200)


# Function to connect to the SQL Server database
# This function uses pyodbc to connect to the database using ODBC Driver 17 for

@st.cache_resource
def connect_db():
    secrets = st.secrets["database"]
    conn = pyodbc.connect(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={secrets['server']};"
        f"DATABASE={secrets['database']};"
        f"UID={secrets['username']};"
        f"PWD={secrets['password']};"
    )
    return conn

conn = connect_db()

def Schema_description ():
# Define schema-aware base prompt
    return """
Database Schema Overview
1. MP_Sales (Sales Transactions)
Joins:

MP_Sales.CustomerID = MP_Customers.SITE_NUMBER

MP_Sales.ItemId = MP_Items.ITEM_CODE

Important Columns:

Date (YYYY-MM-DD) — transaction date

Netsalesvalue — sales value after tax and discounts

SalesQtyInPieces — quantity sold in pieces

SalesQtyInCases — quantity sold in cases

order_Number — order number

ItemId, CustomerID — for joins

Master_brand — format: code|brand, extract the brand name part

sub_brand, brandname, Sales_Channel, itemname

project_id, company, Org_ID, InvoiceId, etc.

Note:

Do not use the month column — always extract month from Date.
always round the sales value to 0 decimal places using ROUND(Netsalesvalue, 0) 

2. MP_Customers (Customer Master)
Joins:

MP_Sales.CustomerID = MP_Customers.SITE_NUMBER

Important Columns:

GOVERNER_NAME — used to filter by governorate

CUSTOMER_B2B_ID, CUSTOMER_NAME, SALES_CHANNEL_CODE, SECTION_TYPE, CUSTOMER_NUMBER

CITY_NAME, AREA_NAME, LOCATION, ADDRESS1

SITE_NUMBER — key to join

ACCOUNT_CREATION_DATE, SITE_CREATION_DATE

Valid Governorate Values:

(examples) القاهرة, الجيزة, الإسكندرية, أسوان, الأقصر, المنيا, القليوبية...
***USE Customer_B2B_ID for customer-related queries*** 


3. MP_Items (Product Master)
Joins:

MP_Sales.ItemId = MP_Items.ITEM_CODE

Important Columns:

ITEM_CODE — unique identifier

DESCRIPTION — item name

MASTER_BRAND — format: code|brand, extract brand name

MG2, MG3 — category & subcategory names

GCOMPANY, GFORM, GSIZE, MSU, CONVERSION_RATE

MASTER_BRAND:

Format is code|brandname, e.g., 692408|Senyorita

Use RIGHT(MASTER_BRAND, LEN(MASTER_BRAND) - CHARINDEX('|', MASTER_BRAND)) to extract brand name

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

    720044|المشروبات الباردة, 720046|البسكويت والحلويات, 718049|المنظفات و أدوات المنزل, etc.
        MG2 values are:
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


Query Requirements
Use only valid SQL Server SELECT queries

Use MP_Sales.Date for time-based filtering (not month column)

Extract text values from MASTER_BRAND, MG2, and MG3

use join to extract ids of customers of CUSTOMER_B2B_ID if ask anything about customers

To filter by company:

Input will be the first 6 digits of MASTER_BRAND

Use:

WHERE LEFT(MASTER_BRAND, CHARINDEX('|', MASTER_BRAND) - 1) = '692408'
    """



# Initialize session state to hold questions
if "query_boxes" not in st.session_state:
    st.session_state.query_boxes = [""]
if "query_count" not in st.session_state:
    st.session_state.query_count = 1

def add_query_box():
    st.session_state.query_boxes.append("")
    st.session_state.query_count += 1

def add_query_box():
    st.session_state.query_boxes.append("")
    st.session_state.query_count += 1
    st.session_state.results.append(None)  # add empty result slot

# Initialize session state for results if not already
if "results" not in st.session_state:
    st.session_state.results = [None] * st.session_state.query_count

# Iterate over each query box
for idx in range(st.session_state.query_count):
    with st.container():
        query_key = f"query_{idx}"
        run_key = f"run_{idx}"

        user_question = st.text_input(f"Query {idx + 1}:", key=query_key, placeholder="قولي عايز تسأل علي أي")

        if st.button(f"جرب كده", key=run_key):
            if not user_question.strip():
                st.warning("جرب شوف عايز تسأل علي أي")
            else:
                with st.spinner("هشوف واقولك..."):
                    try:
                        full_prompt = f"{Schema_description()}\n\n{user_question}"
                        model = genai.GenerativeModel("gemini-2.5-flash")
                        response = model.generate_content(full_prompt)
                        sql_query = response.text.strip().strip("```sql").strip("```")

                        df = pd.read_sql(sql_query, conn)
                        with st.expander(f"✅ Result for Query {idx + 1}"):
                            if st.session_state[BI_key]:
                                st.code(sql_query, language="sql")
                            else:
                                "Results are excuted "

                        # Save result in session state
                        if len(st.session_state.results) <= idx:
                            st.session_state.results.append(df)
                        else:
                            st.session_state.results[idx] = df

                    except Exception as e:
                        st.session_state.results[idx] = None
                        st.error(f"❌ Error: {e}")

        # Display previously stored result (if any)
        if idx < len(st.session_state.results) and st.session_state.results[idx] is not None:
            st.dataframe(st.session_state.results[idx])


st.button("➕ Add New Query", on_click=add_query_box)

