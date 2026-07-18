#----------------------------Part 1---------------------------
# ---------------- IMPORTS ----------------
from executing import Source
import streamlit as st
import google.generativeai as genai
import requests
import folium
import urllib.parse
import smtplib
import math
from html import escape
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

# ---------------- SESSION STATE ----------------
defaults = {
    "response": "",
    "chat_history": [],
    "logged_in": False,
    "current_user": None,
    "current_user_id": None,
    "access_token": None,
    "refresh_token": None,
    "saved_trips": {},
    "images": [],
    "auth_mode": "Register",
    "route_query": None,
    "route_data": None,
    "chrome_menu_open": False,
    "sidebar_page": "✈ Trip Planner",
    "sidebar_language": "English",
    "sidebar_dark_mode": False
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ---------------- API KEYS ----------------

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Missing SUPABASE_URL or SUPABASE_KEY in your .env file.")
    st.stop()

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

def get_auth_field(obj, field, default=None):
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def clear_auth_state():
    st.session_state.logged_in = False
    st.session_state.current_user = None
    st.session_state.current_user_id = None
    st.session_state.access_token = None
    st.session_state.refresh_token = None


def store_auth_session(auth_response, fallback_email):
    session = get_auth_field(auth_response, "session")
    user = get_auth_field(auth_response, "user")

    if not session:
        raise ValueError("Login succeeded, but Supabase did not return a session. Please verify your email, then log in again.")

    st.session_state.logged_in = True
    st.session_state.current_user = get_auth_field(user, "email", fallback_email)
    st.session_state.current_user_id = get_auth_field(user, "id")
    st.session_state.access_token = get_auth_field(session, "access_token")
    st.session_state.refresh_token = get_auth_field(session, "refresh_token")


def restore_auth_session():
    access_token = st.session_state.get("access_token")
    refresh_token = st.session_state.get("refresh_token")

    if not access_token or not refresh_token:
        if st.session_state.get("logged_in"):
            clear_auth_state()
        return False

    try:
        auth_response = supabase.auth.set_session(access_token, refresh_token)
        session = get_auth_field(auth_response, "session")
        user = get_auth_field(auth_response, "user")

        if session:
            st.session_state.access_token = get_auth_field(session, "access_token", access_token)
            st.session_state.refresh_token = get_auth_field(session, "refresh_token", refresh_token)

        if user:
            st.session_state.current_user = get_auth_field(user, "email", st.session_state.current_user)
            st.session_state.current_user_id = get_auth_field(user, "id", st.session_state.current_user_id)

        return True
    except Exception:
        clear_auth_state()
        return False


def require_auth_session():
    if not st.session_state.get("logged_in") or not restore_auth_session():
        raise PermissionError("Your login session expired. Please log out and log in again.")


restore_auth_session()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_KEY = os.getenv("PEXELS_KEY")
GOOGLE_PLACES_KEY = os.getenv("GOOGLE_PLACES_KEY")
WEATHER_KEY = os.getenv("WEATHER_KEY")
ORS_API_KEY = os.getenv("ORS_API_KEY")

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

section[data-testid="stSidebarNav"]{
    display:none;
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

.sidebar-account{
    display:flex;
    align-items:center;
    height:36px;
    margin:0;
}

.st-key-chrome_menu_trigger button{
    width:32px;
    min-width:32px;
    height:36px;
    min-height:36px;
    padding:0;
    border:0;
    border-radius:50%;
    background:transparent !important;
    color:#f8fafc !important;
    font-size:24px;
    line-height:1;
    box-shadow:none;
}

.st-key-chrome_menu_trigger button:hover{
    background:rgba(255,255,255,.12) !important;
}

.account-avatar{
    width:36px;
    height:36px;
    display:flex;
    align-items:center;
    justify-content:center;
    flex:0 0 36px;
    border-radius:50%;
    background:#ea4335;
    color:white;
    font-size:16px;
    font-weight:700;
    box-shadow:0 4px 12px rgba(0,0,0,.28);
}

.account-name{
    display:none;
}

.account-email{
    display:none;
}

.gmail-mark{
    display:none;
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


def sidebar_account_markup(email):
    email = (email or "").strip()
    if not email:
        return ""

    local_part = email.split("@", 1)[0]
    display_name = " ".join(
        part.capitalize()
        for part in local_part.replace(".", " ").replace("_", " ").replace("-", " ").split()
    ) or "Traveler"
    initial = display_name[0].upper()

    return f'<div class="sidebar-account"><div class="account-avatar">{escape(initial)}</div></div>'

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
    require_auth_session()

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


ROUTE_PROFILES = {
    "Drive": {
        "endpoint": "driving-car",
        "maps_mode": "driving",
        "label": "Best driving route",
        "color": "#2563eb"
    },
    "Cycle": {
        "endpoint": "cycling-regular",
        "maps_mode": "bicycling",
        "label": "Bike-friendly route",
        "color": "#16a34a"
    },
    "Walk": {
        "endpoint": "foot-walking",
        "maps_mode": "walking",
        "label": "Walking route",
        "color": "#d97706"
    }
}


def format_route_duration(seconds):
    total_minutes = max(1, round(seconds / 60))
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours} hr {minutes} min" if hours else f"{minutes} min"


def get_travel_tip(distance_km):
    if distance_km <= 8:
        return "Short trip: walking, cycling, or a local cab will usually be most convenient."
    if distance_km <= 250:
        return "Road trip: a car or intercity bus is usually the most flexible option."
    if distance_km <= 700:
        return "Medium-distance trip: compare train and overnight bus options before driving."
    return "Long-distance trip: compare flights and trains; this road route is best used for planning the airport or station transfer."


@st.cache_data(ttl=3600, show_spinner=False)
def get_route_data(source_city, destination, route_profile):
    source_name = clean_city_name(source_city)
    destination_name = clean_city_name(destination)

    if not ORS_API_KEY:
        return {"error": "Add ORS_API_KEY to your .env file to use detailed routes."}

    try:
        geolocator = Nominatim(user_agent="ai_trip_planner_route")
        source_location = geolocator.geocode(source_name, timeout=10)
        destination_location = geolocator.geocode(destination_name, timeout=10)

        if not source_location or not destination_location:
            return {"error": "We could not find one of those cities. Try adding the state or country."}

        profile = ROUTE_PROFILES[route_profile]
        response = requests.post(
            f"https://api.openrouteservice.org/v2/directions/{profile['endpoint']}/geojson",
            json={
                "coordinates": [
                    [source_location.longitude, source_location.latitude],
                    [destination_location.longitude, destination_location.latitude]
                ]
            },
            headers={
                "Authorization": ORS_API_KEY,
                "Content-Type": "application/json"
            },
            timeout=25
        )
        response.raise_for_status()
        payload = response.json()
        features = payload.get("features", [])

        if not features:
            return {"error": "No route was available for the selected travel type."}

        feature = features[0]
        properties = feature.get("properties", {})
        summary = properties.get("summary", {})
        coordinates = feature.get("geometry", {}).get("coordinates", [])

        if not coordinates or not summary:
            return {"error": "The route service returned incomplete route data. Please try again."}

        steps = []
        for segment in properties.get("segments", []):
            for step in segment.get("steps", []):
                steps.append({
                    "instruction": step.get("instruction", "Continue on the current route"),
                    "distance_km": round(step.get("distance", 0) / 1000, 1)
                })

        maps_url = (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={urllib.parse.quote_plus(source_name)}"
            f"&destination={urllib.parse.quote_plus(destination_name)}"
            f"&travelmode={profile['maps_mode']}"
        )

        return {
            "source_name": source_name,
            "destination_name": destination_name,
            "source_coordinates": [source_location.latitude, source_location.longitude],
            "destination_coordinates": [destination_location.latitude, destination_location.longitude],
            "coordinates": [[coordinate[1], coordinate[0]] for coordinate in coordinates],
            "distance_km": summary["distance"] / 1000,
            "duration_seconds": summary["duration"],
            "steps": steps,
            "maps_url": maps_url,
            "profile": profile
        }
    except requests.RequestException:
        return {"error": "The route service is unavailable right now. Please try again shortly."}
    except Exception:
        return {"error": "We could not build this route. Check the city names and try again."}


def display_route(route_data):
    if route_data.get("error"):
        st.error(route_data["error"])
        return

    distance_km = route_data["distance_km"]
    duration = format_route_duration(route_data["duration_seconds"])
    profile = route_data["profile"]

    st.caption(
        f"{profile['label']} from {route_data['source_name']} to {route_data['destination_name']}"
    )
    distance_col, time_col, advice_col = st.columns([1, 1, 2])
    distance_col.metric("Route distance", f"{distance_km:.1f} km")
    time_col.metric("Estimated time", duration)
    advice_col.info(get_travel_tip(distance_km))

    route_map = folium.Map(
        location=route_data["source_coordinates"],
        zoom_start=6,
        tiles="CartoDB positron"
    )
    folium.Marker(
        route_data["source_coordinates"],
        tooltip=f"Start: {route_data['source_name']}",
        icon=folium.Icon(color="green", icon="play")
    ).add_to(route_map)
    folium.Marker(
        route_data["destination_coordinates"],
        tooltip=f"End: {route_data['destination_name']}",
        icon=folium.Icon(color="red", icon="flag")
    ).add_to(route_map)
    AntPath(
        route_data["coordinates"],
        color=profile["color"],
        weight=5,
        opacity=0.85
    ).add_to(route_map)
    route_map.fit_bounds([
        route_data["source_coordinates"],
        route_data["destination_coordinates"]
    ])

    st_folium(route_map, width=1200, height=520, key="detailed_route_map")
    st.markdown(f"[Open this route in Google Maps]({route_data['maps_url']})")

    if route_data["steps"]:
        with st.expander("View route directions"):
            for number, step in enumerate(route_data["steps"][:10], start=1):
                st.write(f"{number}. {step['instruction']} ({step['distance_km']:.1f} km)")
            if len(route_data["steps"]) > 10:
                st.caption("Showing the first 10 directions. Open Google Maps for the complete journey.")


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


# ---------------- AUTH GATE ----------------
if not st.session_state.logged_in:
    st.markdown("""
    <div class="banner">
        <h1 style="font-size:58px;">AI Trip Planner</h1>
        <p style="font-size:22px;">
        Plan Smart, Travel Better
        </p>
    </div>
    """, unsafe_allow_html=True) 
    
    left_space, auth_col, right_space = st.columns([1, 1.15, 1])

    with auth_col:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)

        if st.session_state.auth_mode == "Register":
            st.subheader("Create Account")

            register_email = st.text_input("Email", key="register_email")
            register_password = st.text_input(
                "Password",
                type="password",
                key="register_password"
            )

            if st.button("Sign Up", key="signup_button"):
                if not register_email or not register_password:
                    st.warning("Please enter email and password")
                else:
                    try:
                        supabase.auth.sign_up({
                            "email": register_email,
                            "password": register_password
                        })
                        st.success("Account created successfully")
                        st.info("Now login with your email and password")
                        st.session_state.auth_mode = "Login"
                        st.rerun()
                    except Exception as e:
                        st.error(e)

            if st.button("Already have an account? Login", key="go_to_login"):
                st.session_state.auth_mode = "Login"
                st.rerun()

        else:
            st.subheader("Login")

            login_email = st.text_input("Email", key="login_email")
            login_password = st.text_input(
                "Password",
                type="password",
                key="login_password"
            )

            if st.button("Login", key="login_button"):
                if not login_email or not login_password:
                    st.warning("Please enter email and password")
                else:
                    try:
                        result = supabase.auth.sign_in_with_password({
                            "email": login_email,
                            "password": login_password
                        })
                        store_auth_session(result, login_email)
                        st.success("Login successful")
                        st.rerun()
                    except Exception:
                        st.error("Invalid Email or Password")

            if st.button("Create a new account", key="go_to_register"):
                st.session_state.auth_mode = "Register"
                st.rerun()

            if st.button("Forgot Password", key="forgot_password"):
                if not login_email:
                    st.warning("Please enter your email first")
                else:
                    try:
                        supabase.auth.reset_password_email(login_email)
                        st.success("Password reset link sent")
                    except Exception as e:
                        st.error(e)

        st.markdown('</div>', unsafe_allow_html=True)

    st.stop()


# ---------------- SIDEBAR ----------------
sidebar_logo_col, sidebar_menu_col, sidebar_spacer_col = st.sidebar.columns([1, 1, 4])
with sidebar_logo_col:
    if st.session_state.logged_in:
        st.markdown(
            sidebar_account_markup(st.session_state.current_user),
            unsafe_allow_html=True
        )

with sidebar_menu_col:
    if st.button("⋮", key="chrome_menu_trigger", help="Open menu"):
        st.session_state.chrome_menu_open = not st.session_state.chrome_menu_open

page = st.session_state.sidebar_page
language = st.session_state.sidebar_language
dark_mode = st.session_state.sidebar_dark_mode

if st.session_state.chrome_menu_open:
    with st.sidebar.container(border=True):
        st.markdown("### AI Trip Planner")
        st.caption("Plan Smart, Travel Better")

        if hasattr(st, "page_link"):
            st.page_link("pages/Dashboard.py", label="Dashboard")
            st.page_link("pages/History.py", label="History")
            st.page_link("pages/Profile.py", label="Profile")

        st.divider()
        dark_mode = st.toggle(
            "Dark Mode",
            value=dark_mode,
            key="chrome_dark_mode_widget"
        )
        st.session_state.sidebar_dark_mode = dark_mode

        language = st.selectbox(
            "Language",
            ["English", "Hindi", "Hinglish", "Punjabi", "French", "Spanish"],
            index=["English", "Hindi", "Hinglish", "Punjabi", "French", "Spanish"].index(language),
            key="chrome_language_widget"
        )
        st.session_state.sidebar_language = language

        page_options = ["✈ Trip Planner", "🕒 History", "⚙ Admin Dashboard"]
        page = st.radio(
            "Menu",
            page_options,
            index=page_options.index(page),
            key="chrome_page_widget"
        )
        st.session_state.sidebar_page = page

        if st.session_state.logged_in:
            st.divider()
            st.caption("Saved Destinations")
            try:
                result = supabase.table("trips").select("destination").eq(
                    "user_email",
                    st.session_state.current_user
                ).execute()
                for trip in result.data or []:
                    st.write(f"📍 {trip['destination']}")
            except Exception:
                st.caption("Saved destinations are unavailable right now.")

            if st.button("Logout", key="menu_logout"):
                try:
                    supabase.auth.sign_out()
                except Exception:
                    pass
                clear_auth_state()
                st.session_state.response = ""
                st.session_state.chat_history = []
                st.session_state.images = []
                st.session_state.auth_mode = "Login"
                st.session_state.chrome_menu_open = False
                st.rerun()

# ---------------- LOGIN / REGISTER ----------------
# ---------------- SUPABASE AUTH ----------------

menu = None

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

            store_auth_session(result, email)

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
#----------------------------Part 3---------------------------------------------
# ---------------- HISTORY PAGE ----------------
if page == "🕒 History":

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
    route_input_col, route_mode_col = st.columns([2, 1])
    with route_input_col:
        source_city = st.text_input(
            "Starting City",
            placeholder="start journey from..."
        )
    with route_mode_col:
        route_profile = st.selectbox(
            "Route Type",
            options=list(ROUTE_PROFILES),
            help="Choose the type of route to show on the map."
        )

    travel_col, stay_col = st.columns(2)
    with travel_col:
        travel_option = st.selectbox(
            "Travel Option",
            ["Bus", "Train", "Flight", "Personal Car", "Bike"]
        )
    with stay_col:
        stay_type = st.selectbox(
            "Stay Type",
            ["Hostel", "Budget Hotel", "Comfort Hotel", "Premium Hotel"]
        )

    if source_city or destination:
        st.markdown('<div class="small-card">', unsafe_allow_html=True)
        if source_city and destination:
            st.write(f"Trip route: {source_city.strip()} → {destination.strip()}")
        elif source_city:
            st.write(f"Starting from: {source_city.strip()}")
        else:
            st.write(f"Destination: {destination.strip()}")
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

                    Starting city: {source_city.strip() if source_city else "Not provided"}
                    Weather: {weather}
                    Duration: {days} days
                    Budget: {budget}
                    Interests: {interests}

                    {language_instruction}

                    Begin with a short "Getting there" section that recommends the most suitable way to travel from the starting city when it is provided.

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
                        save_trip(
                            destination,
                            days,
                            budget,
                            interests,
                            response.text
                        )

                    st.session_state.images = get_destination_images(destination)
                        

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


def format_inr(amount):
    return f"₹{amount:,.0f}"


@st.cache_data(ttl=86400, show_spinner=False)
def estimate_trip_distance(source_city, destination):
    try:
        geolocator = Nominatim(user_agent="ai_trip_planner_budget")
        source = geolocator.geocode(clean_city_name(source_city), timeout=10)
        destination_location = geolocator.geocode(clean_city_name(destination), timeout=10)

        if not source or not destination_location:
            return None

        lat1, lon1 = math.radians(source.latitude), math.radians(source.longitude)
        lat2, lon2 = math.radians(destination_location.latitude), math.radians(destination_location.longitude)
        latitude_difference = lat2 - lat1
        longitude_difference = lon2 - lon1
        haversine = (
            math.sin(latitude_difference / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(longitude_difference / 2) ** 2
        )
        direct_distance = 2 * 6371 * math.asin(math.sqrt(haversine))

        # Road and rail routes are usually longer than the straight-line distance.
        return max(1, round(direct_distance * 1.25))
    except Exception:
        return None


def calculate_trip_budget(source_city, destination, days, members, travel_option, stay_type, budget_level):
    distance_km = estimate_trip_distance(source_city, destination)
    if not distance_km:
        return None

    round_trip_distance = distance_km * 2
    if travel_option == "Bus":
        travel_cost = round(round_trip_distance * 1.5 * members)
        travel_note = "Round-trip intercity bus estimate"
    elif travel_option == "Train":
        travel_cost = round(round_trip_distance * 1.1 * members)
        travel_note = "Round-trip train estimate"
    elif travel_option == "Flight":
        one_way_fare = 3200 if distance_km <= 300 else 5200 if distance_km <= 800 else 8500 if distance_km <= 1500 else 13000
        travel_cost = one_way_fare * 2 * members
        travel_note = "Round-trip flight estimate"
    elif travel_option == "Personal Car":
        travel_cost = round(round_trip_distance * 10.5)
        travel_note = "Fuel and toll estimate for one personal car"
    else:
        travel_cost = round(round_trip_distance * 3.2)
        travel_note = "Fuel and maintenance estimate for one bike"

    nights = max(days - 1, 0)
    stay_rates = {
        "Hostel": (850, "per_person"),
        "Budget Hotel": (1250, "per_room"),
        "Comfort Hotel": (3750, "per_room"),
        "Premium Hotel": (8000, "per_room")
    }
    nightly_rate, pricing_type = stay_rates[stay_type]
    rooms = math.ceil(members / 2)
    stay_cost = nightly_rate * nights * (members if pricing_type == "per_person" else rooms)

    daily_food = {
        "Budget-Friendly": 550,
        "Moderate": 950,
        "Luxury": 1850
    }[budget_level]
    daily_local = {
        "Budget-Friendly": 300,
        "Moderate": 700,
        "Luxury": 1500
    }[budget_level]
    food_cost = daily_food * days * members
    local_cost = daily_local * days * members
    subtotal = travel_cost + stay_cost + food_cost + local_cost
    buffer_cost = round(subtotal * 0.08)
    total_estimate = subtotal + buffer_cost

    return {
        "distance_km": distance_km,
        "nights": nights,
        "travel_note": travel_note,
        "travel": travel_cost,
        "stay": stay_cost,
        "food": food_cost,
        "local": local_cost,
        "buffer": buffer_cost,
        "total": total_estimate
    }


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

    # BUDGET FEASIBILITY
    if total_budget > 0:
        st.markdown(
            '<div class="section-title">💰 Trip Budget Check</div>',
            unsafe_allow_html=True
        )

        st.markdown('<div class="small-card">', unsafe_allow_html=True)

        if source_city and destination:
            trip_budget = calculate_trip_budget(
                source_city,
                destination,
                days,
                members,
                travel_option,
                stay_type,
                budget
            )

            if trip_budget:
                difference = total_budget - trip_budget["total"]
                available_col, estimate_col, per_person_col = st.columns(3)
                available_col.metric("Your total budget", format_inr(total_budget))
                estimate_col.metric("Estimated trip cost", format_inr(trip_budget["total"]))
                per_person_col.metric("Estimated per traveler", format_inr(trip_budget["total"] / members))

                if difference >= 0:
                    st.success(
                        f"Yes, this budget is workable. You should have about {format_inr(difference)} left as extra flexibility."
                    )
                else:
                    st.error(
                        f"This plan is short by about {format_inr(abs(difference))}. Increase the budget or choose a cheaper travel/stay option."
                    )

                breakdown = [
                    {
                        "Category": "Round-trip travel",
                        "Estimated group spend": format_inr(trip_budget["travel"]),
                        "Per traveler": format_inr(trip_budget["travel"] / members)
                    },
                    {
                        "Category": f"{stay_type} stay ({trip_budget['nights']} night(s))",
                        "Estimated group spend": format_inr(trip_budget["stay"]),
                        "Per traveler": format_inr(trip_budget["stay"] / members)
                    },
                    {
                        "Category": "Food",
                        "Estimated group spend": format_inr(trip_budget["food"]),
                        "Per traveler": format_inr(trip_budget["food"] / members)
                    },
                    {
                        "Category": "Local transport and activities",
                        "Estimated group spend": format_inr(trip_budget["local"]),
                        "Per traveler": format_inr(trip_budget["local"] / members)
                    },
                    {
                        "Category": "Emergency buffer",
                        "Estimated group spend": format_inr(trip_budget["buffer"]),
                        "Per traveler": format_inr(trip_budget["buffer"] / members)
                    }
                ]
                st.dataframe(breakdown, hide_index=True, use_container_width=True)
                st.caption(
                    f"Distance used: about {trip_budget['distance_km']} km one way. "
                    f"Travel estimate: {trip_budget['travel_note']}. Prices are planning estimates and can change with dates and bookings."
                )
            else:
                st.warning("We could not calculate this route. Add the district, state, or country to both places and try again.")
        else:
            st.info("Enter both Starting City and Destination to check whether your budget is sufficient.")

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

    # ROUTE PLANNER
    if source_city and destination:
        st.markdown(
            '<div class="section-title">🗺 Route Planner</div>',
            unsafe_allow_html=True
        )
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)

        route_query = (
            clean_city_name(source_city),
            clean_city_name(destination),
            route_profile
        )
        if st.button("Show Detailed Route", key="show_detailed_route"):
            with st.spinner("Finding the best route..."):
                st.session_state.route_data = get_route_data(
                    source_city,
                    destination,
                    route_profile
                )
                st.session_state.route_query = route_query

        if st.session_state.route_query == route_query and st.session_state.route_data:
            display_route(st.session_state.route_data)
        else:
            st.info("Choose a route type, then select Show Detailed Route.")

        st.markdown('</div>', unsafe_allow_html=True)
    elif destination:
        st.info("Add your starting city to view a detailed route to this destination.")
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
