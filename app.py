#----------------------------Part 1---------------------------
# ---------------- IMPORTS ----------------
from executing import Source
import streamlit as st
import google.generativeai as genai
import requests
import folium
import urllib.parse
import smtplib
from folium.plugins import AntPath
from email.mime.text import MIMEText
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from streamlit_mic_recorder import mic_recorder
from supabase import create_client, Client
from dotenv import load_dotenv
import os


# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="AI Trip Planner",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------- DATABASE ----------------
db_path = os.path.join(os.getcwd(), "trip_planner.db")


SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_KEY = "YOUR_ANON_KEY"

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

# ---------------- SESSION STATE ----------------
defaults = {
    "response": "",
    "chat_history": [],
    "logged_in": False,
    "current_user": None,
    "saved_trips": {},
    "images": []
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ---------------- API KEYS ----------------

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_KEY = os.getenv("PEXELS_KEY")
GOOGLE_PLACES_KEY = os.getenv("GOOGLE_PLACES_KEY")
WEATHER_KEY = os.getenv("WEATHER_KEY")
ORS_API_KEY = os.getenv("ORS_API_KEY")


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

genai.configure(api_key=GEMINI_API_KEY)

genai.configure(api_key=GEMINI_API_KEY)

# ---------------- PREMIUM CSS ----------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');

html, body, [class*="css"]{
    font-family:'Inter',sans-serif;
}

.stApp{
    background:
    radial-gradient(circle at top right,#312e81 0%,#0b1120 35%,#020617 100%);
    color:white;
}

.block-container{
    max-width:1500px;
    padding-top:1rem;
}

section[data-testid="stSidebar"]{
    background:linear-gradient(180deg,#020617,#111827);
    border-right:1px solid rgba(255,255,255,.08);
}

.banner{
    background-image:url('https://images.pexels.com/photos/358319/pexels-photo-358319.jpeg');
    background-size:cover;
    background-position:center;
    min-height:240px;
    border-radius:24px;
    padding:50px;
    margin-bottom:25px;
}

.glass-card{
    background:rgba(255,255,255,0.05);
    backdrop-filter:blur(18px);
    border:1px solid rgba(255,255,255,.08);
    border-radius:22px;
    padding:22px;
    box-shadow:0 8px 40px rgba(0,0,0,.35);
    margin-bottom:20px;
}

.metric-box{
    background:linear-gradient(135deg,rgba(124,58,237,.18),rgba(59,130,246,.08));
    padding:20px;
    border-radius:20px;
    border:1px solid rgba(255,255,255,.1);
    min-height:140px;
}

.small-card{
    background:rgba(255,255,255,.05);
    border-radius:18px;
    padding:18px;
    border:1px solid rgba(255,255,255,.08);
}

.poster-card{
    border-radius:24px;
    overflow:hidden;
    box-shadow:0 12px 40px rgba(0,0,0,.4);
}

.flight-card{
    background:linear-gradient(135deg,#1d4ed8,#7c3aed);
    border-radius:24px;
    padding:28px;
    color:white;
}

.plan-card{
    background:rgba(255,255,255,.05);
    border-left:5px solid #8b5cf6;
    padding:25px;
    border-radius:20px;
}

.section-title{
    font-size:32px;
    font-weight:700;
    background:linear-gradient(90deg,#60a5fa,#c084fc);
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
}

.stTextInput input,
.stNumberInput input{
    background:#111827 !important;
    color:white !important;
    border-radius:14px !important;
}

.stButton button{
    background:linear-gradient(90deg,#7c3aed,#c026d3);
    color:white;
    border:none;
    border-radius:14px;
    font-size:18px;
    font-weight:700;
    height:52px;
    width:100%;
}

.stButton button:hover{
    transform:scale(1.02);
    transition:.3s;
}
</style>
""", unsafe_allow_html=True)

#--------------------------------Part 2--------------------------------------------------------------
# ---------------- FUNCTIONS ----------------
def clean_city_name(destination):
    words_to_remove = ["trip", "tour", "travel", "beach"]
    
    city = destination.lower()
    
    for word in words_to_remove:
        city = city.replace(word, "")
    
    return city.strip().title()

def packing_list(weather):
    items = ["Phone Charger", "ID Proof", "Cash"]
    weather = weather.lower()

    if "cold" in weather or "snow" in weather:
        items += ["Jacket", "Gloves", "Wool Socks"]
    elif "hot" in weather:
        items += ["Sunscreen", "Cap", "Water Bottle"]
    elif "rain" in weather:
        items += ["Umbrella", "Raincoat"]
    else:
        items += ["Comfortable Clothes", "Shoes"]

    return items


def get_weather(city_name):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_KEY}&units=metric"

    try:
        response = requests.get(url)
        data = response.json()

       # st.write("DEBUG WEATHER:", data)   # temporary

        if response.status_code == 200:
            temp = data["main"]["temp"]
            desc = data["weather"][0]["description"]
            return f"{temp}°C, {desc.title()}"
        else:
            return f"City not found: {data}"

    except Exception as e:
        return f"Error: {e}"

def get_destination_images(destination):

    destination = clean_city_name(destination)

    headers = {
        "Authorization": PEXELS_KEY
    }

    params = {
        "query": f"{destination} tourist place",
        "per_page": 9
    }

    response = requests.get(
        "https://api.pexels.com/v1/search",
        headers=headers,
        params=params
    ).json()

    images = []

    if response.get("photos"):

        for photo in response["photos"]:

            images.append(photo["src"]["large2x"])

    return images


def save_trip(destination, days, budget, interests, trip_plan):
    data = {
        "user_email": st.session_state.current_user,
        "destination": destination,
        "days": days,
        "budget": budget,
        "interests": interests,
        "trip_plan": trip_plan
    }

    supabase.table("trips").insert(data).execute()


def get_poster(destination):
    headers = {"Authorization": PEXELS_KEY}
    url = f"https://api.pexels.com/v1/search?query={destination}&per_page=1"
    response = requests.get(url, headers=headers).json()

    if "photos" in response and len(response["photos"]) > 0:
        return response["photos"][0]["src"]["large"]
    return None


def display_route(source_city, destination):
    source_city = clean_city_name(source_city)
    destination = clean_city_name(destination)
    st.write("Source_city :", source_city)
    st.write("Destination :", destination)
    geolocator = Nominatim(user_agent="tripplanner")
    
    

    src = geolocator.geocode(source_city)
    dest = geolocator.geocode(destination)
    
    st.write("Source Result:", src)
    st.write("Destination Result:", dest)

    if not src or not dest:
        st.error("City not found")
        return

    start = [src.longitude, src.latitude]
    end = [dest.longitude, dest.latitude]

    headers = {
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json"
    }

    body = {
        "coordinates": [start, end]
    }

    response = requests.post(
        "https://api.openrouteservice.org/v2/directions/driving-car/geojson",
        json=body,
        headers=headers
    )

    data = response.json()
     
    

    m = folium.Map(
        location=[src.latitude, src.longitude],
        zoom_start=6
    )

    folium.Marker(
        [src.latitude, src.longitude],
        tooltip="Source",
        icon=folium.Icon(color="green")
    ).add_to(m)

    folium.Marker(
        [dest.latitude, dest.longitude],
        tooltip="Destination",
        icon=folium.Icon(color="red")
    ).add_to(m)

    if "features" in data:

      coords = data["features"][0]["geometry"]["coordinates"]

    route = [
            [c[1], c[0]]
            for c in coords
        ]

    AntPath(
            route,
            color="blue",
            weight=6
        ).add_to(m)

    summary = data["features"][0]["properties"]["summary"]

    distance = summary["distance"]/1000
    duration = summary["duration"]/3600

    st.success(
        f"Distance : {distance:.1f} KM"
    )

    st.success(
        f"Estimated Time : {duration:.1f} Hours"
    )

    st_folium(
        m,
        width=1000,
            height=600
    )


def generate_pdf(text):
    file_name = "trip_plan.pdf"
    doc = SimpleDocTemplate(file_name)
    styles = getSampleStyleSheet()
    story = [Paragraph(text.replace("\n", "<br/>"), styles["Normal"])]
    doc.build(story)
    return file_name


def send_email(receiver_email, trip_text):
    sender_email = "yourgmail@gmail.com"
    sender_password = "your_app_password"

    msg = MIMEText(trip_text)
    msg["Subject"] = "Your AI Trip Plan"
    msg["From"] = sender_email
    msg["To"] = receiver_email

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(sender_email, sender_password)
    server.sendmail(sender_email, receiver_email, msg.as_string())
    server.quit()


# ---------------- SIDEBAR ----------------
st.sidebar.markdown("""
# ✈ AI Trip Planner
### Plan Smart, Travel Better
---
""")

dark_mode = st.sidebar.toggle("🌙 Dark Mode")

language = st.sidebar.selectbox(
    "🌐 Language",
    ["English", "Hindi", "Hinglish", "Punjabi", "French", "Spanish"]
)

page = st.sidebar.radio(
    "MENU",
    ["✈ Trip Planner", "🕒 History", "⚙ Admin Dashboard"]
)

# ---------------- LOGIN / REGISTER ----------------
# ---------------- SUPABASE AUTH ----------------

menu = st.sidebar.radio(
    "Account",
    ["Login", "Register"]
)

# ---------------- REGISTER ----------------

if menu == "Register":

    email = st.sidebar.text_input("Email")

    password = st.sidebar.text_input(
        "Password",
        type="password"
    )

    if st.sidebar.button("Register"):

        try:

            result = supabase.auth.sign_up({

                "email": email,

                "password": password

            })

            st.sidebar.success(
                "Registration Successful ✔"
            )

            st.sidebar.info(
                "Please verify your email."
            )

        except Exception as e:

            st.sidebar.error(e)

# ---------------- LOGIN ----------------

if menu == "Login":

    email = st.sidebar.text_input("Email")

    password = st.sidebar.text_input(
        "Password",
        type="password"
    )

    if st.sidebar.button("Login"):

        try:

            result = supabase.auth.sign_in_with_password({

                "email": email,

                "password": password

            })

            st.session_state.logged_in = True

            st.session_state.current_user = email

            st.sidebar.success("Login Successful ✔")
            st.sidebar.success("Email Verified")
            st.rerun()

        except Exception as e:

            st.sidebar.error("Invalid Email or Password")

    if st.sidebar.button("Forgot Password"):

        try:

           supabase.auth.reset_password_email(email)

           st.success(
            "Password Reset Link Sent"
           )

        except Exception as e:

            st.error(e)
# ---------------- AFTER LOGIN ----------------
if st.session_state.logged_in:
    st.sidebar.success(f"Welcome {st.session_state.current_user}")

    if st.sidebar.button("Logout"):
     supabase.auth.sign_out()
     st.session_state.logged_in = False
     st.session_state.current_user = None
     st.success("Logged Out Successfully")
     st.rerun()


# ---------------- SAVED DESTINATIONS ----------------
if st.session_state.logged_in:

     result = supabase.table("trips").select("destination").eq(
     "user_email",
     st.session_state.current_user
     ).execute()

     if result.data:
         for trip in result.data:
             st.sidebar.write("📍", trip["destination"])
#----------------------------Part 3---------------------------------------------
# ---------------- HISTORY PAGE ----------------
if page == "History":

    st.title("📜 Trip History")

    if st.session_state.logged_in:

        result = supabase.table("trips").select("*").eq(
            "user_email",
            st.session_state.current_user
        ).execute()

        if result.data:

            for trip in result.data:

                st.write("📍", trip["destination"])
                st.write("📅", trip["days"])
                st.write("💰", trip["budget"])
                st.write("---")

        else:

            st.info("No Trips Found")
    else:

        st.warning("Please Login")


# ---------------- ADMIN DASHBOARD ----------------
elif page == "⚙ Admin Dashboard":
    st.title("👨‍💻 Admin Dashboard")

    admin_password = st.text_input("Admin Password", type="password")

    if admin_password == "admin123":
        # Total Users
           users_data = supabase.table("users").select("*").execute()
           total_users = len(users_data.data)

        # Total Trips
           trips_data = supabase.table("trips").select("*").execute()
           total_trips = len(trips_data.data)

        # Users List
           users = users_data.data
        
           c1, c2 = st.columns(2)
           with c1:
            st.metric("Total Users", total_users)
           with c2:
            st.metric("Total Trips", total_trips)
            st.subheader("Users")
            for user in users:
             st.write("👤", user[0])
 
    else:
        st.info("Enter admin password to continue")


# ---------------- TRIP PLANNER PAGE ----------------
elif page == "✈ Trip Planner":

    # HERO BANNER
    st.markdown("""
    <div class="banner">
        <h1 style="font-size:58px;">Explore The World With AI ✈</h1>
        <p style="font-size:22px;">
        Luxury planning • Smart recommendations • Real-time travel insights
        </p>
    </div>
    """, unsafe_allow_html=True)

    # TOP STATS
    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("Trips Planned", "10K+")

    with c2:
        st.metric("Destinations", "500+")

    with c3:
        st.metric("Happy Travelers", "98%")

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        destination = st.text_input("📍 Destination")

    with col2:
        days = st.number_input("📅 Days", 1, 30)

    with col3:
        budget = st.selectbox(
            "💰 Budget",
            ["Budget-Friendly", "Moderate", "Luxury"]
        )

    with col4:
        interests = st.text_input("🎯 Interests")

    total_budget = st.number_input("Total Budget (₹)", min_value=0)
    members = st.number_input("Number of Travelers", min_value=1)
    currency = st.selectbox("Currency", ["INR", "USD", "EUR"])
    source_city = st.text_input("Source City")

    if source_city or destination:
        st.markdown('<div class="small-card">', unsafe_allow_html=True)
        if source_city:
            st.write("Source :", source_city)
        if destination:
            st.write("Destination :", destination)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # METRICS
    m1, m2, m3, m4 = st.columns(4)

    clean_destination = clean_city_name(destination)
    weather = get_weather(clean_destination) if destination else "N/A"
    

    with m1:
        st.markdown(f"""
        <div class="metric-box">
        <h4>📍 Destination</h4>
        <h2>{destination if destination else '--'}</h2>
        </div>
        """, unsafe_allow_html=True)

    with m2:
        st.markdown(f"""
        <div class="metric-box">
        <h4>📅 Duration</h4>
        <h2>{days} Days</h2>
        </div>
        """, unsafe_allow_html=True)

    with m3:
        st.markdown(f"""
        <div class="metric-box">
        <h4>💰 Budget</h4>
        <h2>{budget}</h2>
        </div>
        """, unsafe_allow_html=True)

    with m4:
        st.markdown(f"""
        <div class="metric-box">
        <h4>🌤 Weather</h4>
        <h2>{weather}</h2>
        </div>
        """, unsafe_allow_html=True)

    # VOICE INPUT
    st.subheader("🎤 Voice Input")
    voice = mic_recorder(
        start_prompt="Start Recording",
        stop_prompt="Stop Recording",
        just_once=True
    )

    if voice:
        st.success("Voice recorded successfully!")

    # AI PLAN GENERATION
    if st.button("Make My Plan 🚀"):
        destination = destination.strip().title()
        
        if destination:
            with st.spinner("Generating your plan..."):
                try:
                    model = genai.GenerativeModel("gemini-2.5-flash")
                    weather = get_weather(destination)

                    if language == "Hinglish":
                        language_instruction = """
                        Generate response in Hinglish.
                        Use Roman script only.
                        Mix Hindi and English naturally.
                        """
                    else:
                        language_instruction = f"Generate response in {language}"

                    prompt = f"""
                    You are an expert travel planner.

                    Create a detailed trip plan for {destination}

                    Weather: {weather}
                    Duration: {days} days
                    Budget: {budget}
                    Interests: {interests}

                    {language_instruction}

                    Format:
                    # Overview
                    # Day 1
                    - Morning
                    - Afternoon
                    - Evening
                    # Budget Tips
                    # Foods to Try
                    """

                    response = model.generate_content(prompt)
                    st.session_state.response = response.text
                    if st.session_state.logged_in:
                        supabase.table("trips").insert({
                        "user_email": st.session_state.current_user,
                        "destination": destination,
                        "days": days,
                        "budget": budget,
                        "interests": interests,
                        "trip_plan": response.text
                        }).execute()
                    
                    if st.session_state.logged_in:
                      save_trip(
                         destination,
                         days,
                         budget,
                         interests,
                         response.text
                         )

                    st.session_state.images = get_destination_images(destination)

                    if st.session_state.logged_in:
                        supabase.table("trips").insert({
                            "user_email": st.session_state.current_user,
                            "destination": destination
                        }).execute() 
                        

                except Exception as e:
                    st.error(f"Error: {e}")

        else:
            st.warning("Please enter destination")

    # CHATBOT
    st.subheader("💬 Trip Assistant Chatbot")

    user_query = st.text_input("Ask anything about your trip")

    if st.button("Ask AI"):
        if user_query:
            try:
                model = genai.GenerativeModel("gemini-2.5-flash")

                prompt = f"""
                User planned a trip to {destination}.
                Question: {user_query}
                Answer briefly and helpfully.
                """

                reply = model.generate_content(prompt).text

                st.session_state.chat_history.append(("You", user_query))
                st.session_state.chat_history.append(("AI", reply))

            except Exception as e:
                st.error(e)

    for sender, msg in st.session_state.chat_history:
        st.write(f"**{sender}:** {msg}")
        
#----------------------------Part 4---------------------------------------------
# ---------------- EXTRA FUNCTIONS ----------------
def get_real_hotels(destination):
    return [
        {"name": "Grand Palace Hotel", "rating": 4.5, "address": "City Center"},
        {"name": "Luxury Inn", "rating": 4.2, "address": "Downtown"},
        {"name": "Budget Stay", "rating": 4.0, "address": "Near Market"}
    ]


def get_real_attractions(destination):
    return [
        "Main City Museum",
        "Historic Fort",
        "Central Park",
        "River Front",
        "Shopping Street"
    ]


def estimate_flight(source, destination):
    indian_cities = [
        "Delhi", "Mumbai", "Goa", "Jaipur",
        "Bangalore", "Chennai", "Kolkata",
        "Hyderabad", "Pune"
    ]

    international_budget = [
        "Dubai", "Bangkok", "Singapore",
        "Kuala Lumpur", "Doha"
    ]

    if source in indian_cities and destination in indian_cities:
        return "₹4,000 - ₹12,000"
    elif destination in international_budget:
        return "₹15,000 - ₹40,000"
    else:
        return "₹35,000 - ₹90,000"
    
def save_trip(destination, days, budget, interests, trip_plan):

    data = {

        "user_email": st.session_state.current_user,

        "destination": destination,

        "days": days,

        "budget": budget,

        "interests": interests,

        "trip_plan": trip_plan

    }

    supabase.table("trips").insert(data).execute()   


# ---------------- OUTPUT ----------------
if page == "✈ Trip Planner":

    if st.session_state.response:
        st.success("🎉 Your plan is ready!")

        st.markdown('<div class="plan-card">', unsafe_allow_html=True)
        st.markdown("## ✨ Your AI Generated Trip Plan")
        st.markdown(st.session_state.response)
        st.markdown('</div>', unsafe_allow_html=True)

        # PDF DOWNLOAD
        pdf_file = generate_pdf(st.session_state.response)

        with open(pdf_file, "rb") as f:
            st.download_button(
                "📄 Download PDF",
                f,
                file_name="trip_plan.pdf"
            )

        # EMAIL SHARE
        st.subheader("📧 Send Plan via Email")
        email = st.text_input("Receiver Email")

        if st.button("Send Email"):
            try:
                send_email(email, st.session_state.response)
                st.success("Email sent successfully!")
            except Exception as e:
                st.error(e)

        # WHATSAPP SHARE
        st.subheader("📲 Share on WhatsApp")
        encoded = urllib.parse.quote(st.session_state.response)
        whatsapp_link = f"https://wa.me/?text={encoded}"
        st.markdown(f"[Open WhatsApp Share Link]({whatsapp_link})")

    # DESTINATION PHOTOS
    if st.session_state.images:
        st.markdown(
            '<div class="section-title">📸 Destination Photos</div>',
            unsafe_allow_html=True
        )

        cols = st.columns(3)

        for i, img in enumerate(st.session_state.images[:9]):
            with cols[i % 3]:
                st.image(img, use_container_width=True)

    # POSTER
    if destination:
        st.markdown(
            '<div class="section-title">🖼 Travel Poster</div>',
            unsafe_allow_html=True
        )

        poster = get_poster(destination)

        if poster:
            st.markdown('<div class="poster-card">', unsafe_allow_html=True)
            st.image(poster, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

    # WEATHER
    if destination:
        weather = get_weather(destination)

        st.markdown(
            '<div class="section-title">🌤 Weather</div>',
            unsafe_allow_html=True
        )

        st.info(weather)

    # PACKING LIST
    if destination:
        st.markdown(
            '<div class="section-title">🎒 Packing Checklist</div>',
            unsafe_allow_html=True
        )

        items = packing_list(weather)

        st.markdown('<div class="small-card">', unsafe_allow_html=True)

        for item in items:
            st.checkbox(item)

        st.markdown('</div>', unsafe_allow_html=True)

    # EXPENSE SPLIT
    if total_budget > 0:
        st.markdown(
            '<div class="section-title">💰 Expense Split</div>',
            unsafe_allow_html=True
        )

        st.markdown('<div class="small-card">', unsafe_allow_html=True)

        per_person = total_budget / members
        st.write(f"Each traveler pays: ₹{per_person:.2f}")

        if currency == "USD":
            st.write(f"Approx: ${total_budget/86:.2f}")
        elif currency == "EUR":
            st.write(f"Approx: €{total_budget/95:.2f}")

        st.markdown('</div>', unsafe_allow_html=True)

    # HOTELS + ATTRACTIONS
    if destination:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown('<div class="small-card">', unsafe_allow_html=True)
            st.subheader("🏨 Top Hotels")

            hotels = get_real_hotels(destination)

            for hotel in hotels:
                st.write(f"🏨 {hotel['name']}")
                st.write(f"⭐ {hotel['rating']}")
                st.write(f"📍 {hotel['address']}")
                st.write("---")

            st.markdown('</div>', unsafe_allow_html=True)

        with col2:
            st.markdown('<div class="small-card">', unsafe_allow_html=True)
            st.subheader("🏛 Top Attractions")

            attractions = get_real_attractions(destination)

            for place in attractions:
                st.write("📍", place)

            st.markdown('</div>', unsafe_allow_html=True)

    # FLIGHT COST
    if source_city and destination:
        price = estimate_flight(source_city, destination)

        st.markdown(f"""
        <div class="flight-card">
        <h2>✈ Estimated Flight Cost</h2>
        <h1>{price}</h1>
        <p>{source_city} → {destination}</p>
        </div>
        """, unsafe_allow_html=True)

    # MAP
    if destination:
        st.markdown(
            '<div class="section-title">🗺 Destination Map</div>',
            unsafe_allow_html=True
        )
        
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        display_route(
            source_city,
            destination
        )
        st.markdown('</div>', unsafe_allow_html=True)        
#------------------------------FOOTER---------------------     
        
    st.markdown("""
    ---
    <center>

    🚀 AI Trip Planner

   Gemini AI • Supabase • Streamlit

   Version 3.0

   © 2026

   </center>
   """,unsafe_allow_html=True)