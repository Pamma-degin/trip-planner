#----------------------------Part 1---------------------------
# ---------------- IMPORTS ----------------
import streamlit as st
import google.generativeai as genai
import requests
import folium
import urllib.parse
import smtplib
import math
import hashlib
import json
import re
import time
from io import BytesIO
from html import escape
from folium.plugins import AntPath
from email.message import EmailMessage
from email.utils import parseaddr
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from streamlit_mic_recorder import mic_recorder
from supabase import create_client, Client
from dotenv import load_dotenv
import os

try:
    from streamlit_cookies_manager import EncryptedCookieManager
except ImportError:
    EncryptedCookieManager = None


# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="AI Trip Planner",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
    "sidebar_dark_mode": True,
    "voice_transcript": "",
    "processed_voice_hash": "",
    "pending_voice_fields": None,
    "last_plan_context": {},
    "trip_destination": "",
    "trip_days": 1,
    "trip_budget_level": "Budget-Friendly",
    "trip_interests": "",
    "trip_total_budget": 0.0,
    "trip_members": 1,
    "trip_currency": "INR",
    "trip_source_city": "",
    "trip_travel_option": "Bus",
    "budget_result": None,
    "budget_query": None,
    "gemini_cooldown_until": 0.0
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ---------------- API KEYS ----------------

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
COOKIE_PASSWORD = os.getenv("COOKIE_PASSWORD")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Missing SUPABASE_URL or SUPABASE_KEY in your .env file.")
    st.stop()

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

auth_cookies = None
if EncryptedCookieManager and COOKIE_PASSWORD:
    auth_cookies = EncryptedCookieManager(
        prefix="ai-trip-planner/auth/",
        password=COOKIE_PASSWORD
    )
    if not auth_cookies.ready():
        st.stop()

REMEMBERED_AUTH_KEYS = (
    "remembered_email",
    "remembered_access_token",
    "remembered_refresh_token"
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


def clear_remembered_auth():
    if auth_cookies is None:
        return
    changed = False
    for cookie_key in REMEMBERED_AUTH_KEYS:
        if auth_cookies.get(cookie_key) is not None:
            del auth_cookies[cookie_key]
            changed = True
    if changed:
        auth_cookies.save()


def save_remembered_auth():
    if auth_cookies is None:
        return False
    access_token = st.session_state.get("access_token")
    refresh_token = st.session_state.get("refresh_token")
    email = st.session_state.get("current_user")
    if not access_token or not refresh_token or not email:
        return False
    auth_cookies["remembered_email"] = str(email)
    auth_cookies["remembered_access_token"] = str(access_token)
    auth_cookies["remembered_refresh_token"] = str(refresh_token)
    auth_cookies.save()
    return True


def store_auth_session(auth_response, fallback_email, remember_me=False):
    session = get_auth_field(auth_response, "session")
    user = get_auth_field(auth_response, "user")

    if not session:
        raise ValueError("Login succeeded, but Supabase did not return a session. Please verify your email, then log in again.")

    st.session_state.logged_in = True
    st.session_state.current_user = get_auth_field(user, "email", fallback_email)
    st.session_state.current_user_id = get_auth_field(user, "id")
    st.session_state.access_token = get_auth_field(session, "access_token")
    st.session_state.refresh_token = get_auth_field(session, "refresh_token")

    if remember_me:
        save_remembered_auth()
    else:
        clear_remembered_auth()


def restore_auth_session():
    access_token = st.session_state.get("access_token")
    refresh_token = st.session_state.get("refresh_token")
    restored_from_cookie = False

    if (not access_token or not refresh_token) and auth_cookies is not None:
        access_token = auth_cookies.get("remembered_access_token")
        refresh_token = auth_cookies.get("remembered_refresh_token")
        remembered_email = auth_cookies.get("remembered_email")
        if access_token and refresh_token:
            st.session_state.access_token = access_token
            st.session_state.refresh_token = refresh_token
            st.session_state.current_user = remembered_email
            restored_from_cookie = True

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

        st.session_state.logged_in = True
        if restored_from_cookie:
            save_remembered_auth()
        return True
    except Exception:
        clear_auth_state()
        if restored_from_cookie:
            clear_remembered_auth()
        return False


def require_auth_session():
    if not st.session_state.get("logged_in") or not restore_auth_session():
        raise PermissionError("Your login session expired. Please log out and log in again.")


restore_auth_session()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
PEXELS_KEY = os.getenv("PEXELS_KEY")
GOOGLE_PLACES_KEY = os.getenv("GOOGLE_PLACES_KEY")
WEATHER_KEY = os.getenv("WEATHER_KEY")
ORS_API_KEY = os.getenv("ORS_API_KEY")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER") or os.getenv("EMAIL_SENDER") or os.getenv("SENDER_EMAIL")
SMTP_PASSWORD = (
    os.getenv("SMTP_PASSWORD")
    or os.getenv("EMAIL_APP_PASSWORD")
    or os.getenv("SENDER_APP_PASSWORD")
)
ADMIN_EMAILS = {
    email.strip().casefold()
    for email in os.getenv("ADMIN_EMAILS", "").split(",")
    if email.strip()
}

genai.configure(api_key=GEMINI_API_KEY)


def gemini_model_candidates():
    candidates = [GEMINI_MODEL, "gemini-3.1-flash-lite"]
    if GEMINI_MODEL not in ("gemini-3.5-flash", "gemini-flash-latest"):
        candidates.append("gemini-flash-latest")
    return list(dict.fromkeys(candidates))


class GeminiQuotaError(RuntimeError):
    pass


def quota_retry_seconds(error_text):
    patterns = (
        r"retry\s+in\s+(\d+(?:\.\d+)?)\s*s",
        r"retry_delay.*?seconds[^0-9]*(\d+(?:\.\d+)?)",
        r"retry after\s+(\d+(?:\.\d+)?)"
    )
    for pattern in patterns:
        match = re.search(pattern, error_text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return max(1, math.ceil(float(match.group(1))))
    return 60


def generate_gemini_content(contents):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to your environment settings.")

    cooldown_remaining = math.ceil(st.session_state.get("gemini_cooldown_until", 0) - time.time())
    if cooldown_remaining > 0:
        raise GeminiQuotaError(
            f"AI request limit reached. Please wait about {cooldown_remaining} seconds, then try again."
        )

    last_error = None
    longest_retry = 0
    quota_was_reached = False
    for model_name in gemini_model_candidates():
        try:
            response = genai.GenerativeModel(model_name).generate_content(contents)
            if not getattr(response, "text", "").strip():
                raise RuntimeError("Gemini returned an empty response. Please try again.")
            return response
        except Exception as error:
            last_error = error
            error_text = str(error).lower()
            quota_error = "429" in error_text or "quota exceeded" in error_text or "resource_exhausted" in error_text
            if quota_error:
                quota_was_reached = True
                longest_retry = max(longest_retry, quota_retry_seconds(str(error)))
                continue

            model_unavailable = any(marker in error_text for marker in (
                "404", "not found", "no longer available", "unsupported model"
            ))
            if not model_unavailable:
                raise

    if quota_was_reached:
        wait_seconds = min(max(longest_retry, 20), 120)
        st.session_state.gemini_cooldown_until = time.time() + wait_seconds
        raise GeminiQuotaError(
            f"Gemini free-tier request limit reached. Please wait about {wait_seconds} seconds and try again. "
            "For frequent usage, enable Gemini API billing or use a project with available quota."
        )

    raise RuntimeError(f"No configured Gemini model is available: {last_error}")

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

section[data-testid="stSidebarNav"],
[data-testid="stSidebarNav"],
[data-testid="stSidebarNavItems"],
[data-testid="stSidebarNavSeparator"]{
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
    city = re.sub(r"\b(?:trip|tour|travel)\b", " ", (destination or ""), flags=re.IGNORECASE)
    city = re.sub(r"\s+", " ", city).strip(" ,-")
    return city.title()


@st.cache_data(ttl=86400, show_spinner=False)
def geocode_place(place_name):
    place_name = clean_city_name(place_name)
    if not place_name:
        return None

    queries = [place_name]
    if "," not in place_name:
        queries.append(f"{place_name}, India")

    try:
        geolocator = Nominatim(user_agent="ai_trip_planner_location_search")
        for query in queries:
            location = geolocator.geocode(
                query,
                exactly_one=True,
                addressdetails=True,
                language="en",
                timeout=12
            )
            if location:
                address = location.raw.get("display_name", location.address)
                return {
                    "name": place_name,
                    "address": address,
                    "latitude": float(location.latitude),
                    "longitude": float(location.longitude),
                    "details": location.raw.get("address", {})
                }
    except Exception:
        return None

    return None


def haversine_distance(first_location, second_location):
    lat1 = math.radians(first_location["latitude"])
    lon1 = math.radians(first_location["longitude"])
    lat2 = math.radians(second_location["latitude"])
    lon2 = math.radians(second_location["longitude"])
    latitude_difference = lat2 - lat1
    longitude_difference = lon2 - lon1
    haversine = (
        math.sin(latitude_difference / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(longitude_difference / 2) ** 2
    )
    return 2 * 6371 * math.asin(math.sqrt(haversine))


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


def automatic_stay_type(budget_level):
    return {
        "Budget-Friendly": "Hostel",
        "Moderate": "Comfort Hotel",
        "Luxury": "Premium Hotel"
    }.get(budget_level, "Hostel")


def packing_list(destination, weather, travel_option, days):
    items = [
        "Phone and charger",
        "Government ID",
        "Cash and payment cards",
        "Medicines and basic first aid",
        "Comfortable clothes and footwear",
        "Reusable water bottle"
    ]
    weather_text = weather.lower()
    destination_text = destination.lower()

    temperature_match = re.search(r"(-?\d+(?:\.\d+)?)\s*°C", weather, re.IGNORECASE)
    temperature = float(temperature_match.group(1)) if temperature_match else None

    if temperature is not None and temperature <= 12:
        items += ["Warm jacket", "Thermal layers", "Gloves and wool socks"]
    elif temperature is not None and temperature >= 28:
        items += ["Sunscreen", "Cap or hat", "Light cotton clothes"]

    if "rain" in weather_text or "drizzle" in weather_text or "storm" in weather_text:
        items += ["Umbrella", "Raincoat", "Waterproof bag cover"]

    mountain_places = ("manali", "shimla", "leh", "ladakh", "kedarnath", "mussoorie", "nainital", "darjeeling", "gangtok")
    coastal_places = ("goa", "puri", "andaman", "pondicherry", "kerala", "lakshadweep", "digha", "beach")
    pilgrimage_places = ("kedarnath", "badrinath", "haridwar", "rishikesh", "varanasi", "amritsar", "tirupati")

    if any(place in destination_text for place in mountain_places):
        items += ["Trekking shoes", "Warm inner layer", "Compact day backpack"]
    if any(place in destination_text for place in coastal_places):
        items += ["Swimwear", "Flip-flops", "Quick-dry towel"]
    if any(place in destination_text for place in pilgrimage_places):
        items += ["Modest clothing", "Small day bag", "Easy slip-on footwear"]

    travel_items = {
        "Bus": ["Bus e-ticket", "Neck pillow", "Light snacks", "Motion-sickness medicine"],
        "Train": ["Train ticket", "Small luggage lock", "Bedsheet or travel blanket", "Snacks"],
        "Flight": ["Boarding pass", "Cabin-size bag", "Travel-size toiletries", "Power bank in cabin baggage"],
        "Personal Car": ["Driving licence", "RC, insurance and PUC", "FASTag balance", "Spare tyre and toolkit", "Phone mount"],
        "Bike": ["Driving licence", "RC, insurance and PUC", "ISI-marked helmet", "Riding gloves and jacket", "Puncture kit", "Rain cover and bungee cords"]
    }
    items += travel_items.get(travel_option, [])

    if days >= 5:
        items += ["Laundry bag", "Extra medicines", "Additional charging cable"]

    return list(dict.fromkeys(items))


@st.cache_data(ttl=900, show_spinner=False)
def get_weather(city_name):
    if not WEATHER_KEY:
        return "Weather unavailable: WEATHER_KEY is not configured"

    location = geocode_place(city_name)
    if not location:
        return "Weather unavailable: place not found; add district, state, or country"

    try:
        response = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "lat": location["latitude"],
                "lon": location["longitude"],
                "appid": WEATHER_KEY,
                "units": "metric"
            },
            timeout=15
        )
        response.raise_for_status()
        data = response.json()
        temp = data["main"]["temp"]
        desc = data["weather"][0]["description"]
        return f"{temp:.1f}°C, {desc.title()}"
    except requests.RequestException:
        return "Weather service is temporarily unavailable"
    except (KeyError, TypeError, ValueError):
        return "Weather service returned incomplete data"


def pexels_images(search_query, limit):
    if not PEXELS_KEY:
        return []

    try:
        response = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_KEY},
            params={"query": search_query, "per_page": min(limit, 15)},
            timeout=15
        )
        response.raise_for_status()
        images = []
        for photo in response.json().get("photos", []):
            source = photo.get("src", {})
            image_url = source.get("large2x") or source.get("large")
            if image_url:
                images.append({
                    "url": image_url,
                    "alt": photo.get("alt") or search_query,
                    "credit": f"Photo by {photo.get('photographer', 'Pexels contributor')}",
                    "credit_url": photo.get("url", "https://www.pexels.com")
                })
        return images
    except requests.RequestException:
        return []


def wikimedia_images(search_query, limit):
    try:
        response = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": search_query,
                "gsrnamespace": 6,
                "gsrlimit": min(limit * 2, 20),
                "prop": "imageinfo",
                "iiprop": "url|mime|extmetadata",
                "iiurlwidth": 1400,
                "format": "json"
            },
            headers={"User-Agent": "AITripPlanner/3.1"},
            timeout=20
        )
        response.raise_for_status()
        images = []
        pages = response.json().get("query", {}).get("pages", {})
        for page in pages.values():
            image_info = (page.get("imageinfo") or [{}])[0]
            if not image_info.get("mime", "").startswith("image/"):
                continue
            image_url = image_info.get("thumburl") or image_info.get("url")
            if not image_url:
                continue
            metadata = image_info.get("extmetadata", {})
            artist = metadata.get("Artist", {}).get("value", "Wikimedia Commons contributor")
            artist = re.sub(r"<[^>]+>", "", artist).strip()
            images.append({
                "url": image_url,
                "alt": page.get("title", search_query).replace("File:", ""),
                "credit": f"Photo: {artist or 'Wikimedia Commons contributor'}",
                "credit_url": image_info.get("descriptionurl", "https://commons.wikimedia.org")
            })
            if len(images) >= limit:
                break
        return images
    except requests.RequestException:
        return []


@st.cache_data(ttl=21600, show_spinner=False)
def get_destination_images(destination):
    destination = clean_city_name(destination)
    if not destination:
        return []

    location = geocode_place(destination)
    search_names = [destination]
    if location:
        details = location.get("details", {})
        nearby_area = details.get("state_district") or details.get("county") or details.get("state")
        if nearby_area and nearby_area.casefold() not in destination.casefold():
            search_names.append(f"{destination} {nearby_area}")

    images = []
    seen_urls = set()
    for search_name in search_names:
        queries = [f"{search_name} landmark", f"{search_name} tourism"]
        for query in queries:
            for image in pexels_images(query, 9):
                if image["url"] not in seen_urls:
                    seen_urls.add(image["url"])
                    images.append(image)
                if len(images) >= 9:
                    return images

    if len(images) < 3:
        for image in wikimedia_images(destination, 9 - len(images)):
            if image["url"] not in seen_urls:
                seen_urls.add(image["url"])
                images.append(image)

    return images[:9]


def save_trip(destination, days, budget, interests, trip_plan, metadata=None):
    local_record = {
        "destination": destination,
        "days": days,
        "budget": budget,
        "interests": interests,
        "trip_plan": trip_plan,
        **(metadata or {})
    }
    st.session_state.saved_trips[destination.casefold()] = local_record

    if not st.session_state.logged_in:
        return False, "Log in to save this trip permanently."

    data = {
        "user_email": st.session_state.current_user,
        "destination": destination,
        "days": days,
        "budget": budget,
        "interests": interests,
        "trip_plan": trip_plan
    }

    try:
        require_auth_session()
        supabase.table("trips").insert(data).execute()
        return True, None
    except Exception as error:
        error_text = str(error).lower()
        if "row-level security" in error_text or "42501" in error_text:
            return False, "Plan is ready, but Supabase blocked saving it. Apply the included trips RLS policy in Supabase."
        if "user id" in error_text and "exist" in error_text:
            return False, "Plan is ready, but the database user link is invalid. Log out, log in again, and retry saving."
        return False, "Plan is ready, but cloud saving is temporarily unavailable."


def get_poster(destination):
    images = get_destination_images(destination)
    return images[0] if images else None


def is_admin_user(email):
    return bool(email and email.casefold() in ADMIN_EMAILS)


def transcribe_voice(voice):
    audio_bytes = voice.get("bytes") if isinstance(voice, dict) else None
    if not audio_bytes:
        raise ValueError("No audio was captured. Please record again.")

    mime_type = voice.get("mime_type") or voice.get("format") or "audio/wav"
    if "/" not in mime_type:
        mime_type = f"audio/{mime_type}"

    response = generate_gemini_content([
        "Transcribe this travel request exactly. Return only the spoken words, without commentary.",
        {"mime_type": mime_type, "data": audio_bytes}
    ])
    return response.text.strip()


def extract_voice_trip_fields(transcript):
    prompt = f"""
    Extract trip planner fields from this voice transcript:
    {transcript}

    Return JSON only with these keys:
    source_city, destination, days, interests, travel_option.
    travel_option must be one of Bus, Train, Flight, Personal Car, Bike.
    Use null when a value was not mentioned.
    """
    text = generate_gemini_content(prompt).text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    values = json.loads(text)

    fields = {}
    for key in ("source_city", "destination", "interests"):
        if values.get(key):
            fields[key] = str(values[key]).strip()

    if values.get("days"):
        fields["days"] = min(30, max(1, int(values["days"])))
    if values.get("travel_option") in ("Bus", "Train", "Flight", "Personal Car", "Bike"):
        fields["travel_option"] = values["travel_option"]
    return fields


ROUTE_PROFILES = {
    "Bus": {
        "endpoint": "driving-car", "maps_mode": "transit",
        "label": "Recommended bus/road route", "color": "#2563eb", "speed": 48
    },
    "Train": {
        "endpoint": None, "maps_mode": "transit",
        "label": "Train connection overview", "color": "#16a34a", "speed": 65
    },
    "Flight": {
        "endpoint": None, "maps_mode": None,
        "label": "Flight connection overview", "color": "#7c3aed", "speed": 700
    },
    "Personal Car": {
        "endpoint": "driving-car", "maps_mode": "driving",
        "label": "Recommended driving route", "color": "#2563eb", "speed": 55
    },
    "Bike": {
        "endpoint": "driving-car", "maps_mode": "driving",
        "label": "Recommended motorbike route", "color": "#ea580c", "speed": 45
    }
}


def format_route_duration(seconds):
    total_minutes = max(1, round(seconds / 60))
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours} hr {minutes} min" if hours else f"{minutes} min"


def get_travel_tip(distance_km, travel_option):
    if travel_option == "Flight":
        return "Flight time includes an estimated three hours for airport check-in and transfers."
    if travel_option == "Train":
        return "Rail distance and time are approximate; confirm the actual train and timetable before booking."
    if distance_km <= 8:
        return "Short trip: walking, cycling, or a local cab will usually be most convenient."
    if distance_km <= 250:
        return "Road trip: a car or intercity bus is usually the most flexible option."
    if distance_km <= 700:
        return "Medium-distance trip: compare train and overnight bus options before driving."
    return "Long-distance trip: compare flights and trains; this road route is best used for planning the airport or station transfer."


@st.cache_data(ttl=3600, show_spinner=False)
def get_route_data(source_city, destination, travel_option):
    source_name = clean_city_name(source_city)
    destination_name = clean_city_name(destination)
    source_location = geocode_place(source_name)
    destination_location = geocode_place(destination_name)

    if not source_location or not destination_location:
        return {"error": "We could not find one of those places. Add the district, state, or country and try again."}

    profile = ROUTE_PROFILES.get(travel_option, ROUTE_PROFILES["Personal Car"])
    source_coordinates = [source_location["latitude"], source_location["longitude"]]
    destination_coordinates = [destination_location["latitude"], destination_location["longitude"]]
    direct_distance = haversine_distance(source_location, destination_location)

    if travel_option == "Flight":
        maps_url = (
            "https://www.google.com/travel/flights?q="
            + urllib.parse.quote_plus(f"Flights from {source_name} to {destination_name}")
        )
    else:
        maps_url = (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={urllib.parse.quote_plus(source_name)}"
            f"&destination={urllib.parse.quote_plus(destination_name)}"
            f"&travelmode={profile['maps_mode']}"
        )

    def direct_route_result():
        distance_factor = 1.0 if travel_option == "Flight" else 1.15 if travel_option == "Train" else 1.25
        distance_km = max(1, direct_distance * distance_factor)
        duration_hours = distance_km / profile["speed"]
        if travel_option == "Flight":
            duration_hours += 3
        return {
            "source_name": source_location["address"],
            "destination_name": destination_location["address"],
            "source_coordinates": source_coordinates,
            "destination_coordinates": destination_coordinates,
            "coordinates": [source_coordinates, destination_coordinates],
            "distance_km": distance_km,
            "duration_seconds": duration_hours * 3600,
            "steps": [],
            "maps_url": maps_url,
            "profile": profile,
            "travel_option": travel_option,
            "is_detailed": False
        }

    if not profile["endpoint"] or not ORS_API_KEY:
        return direct_route_result()

    try:
        response = requests.post(
            f"https://api.openrouteservice.org/v2/directions/{profile['endpoint']}/geojson",
            json={
                "coordinates": [
                    [source_location["longitude"], source_location["latitude"]],
                    [destination_location["longitude"], destination_location["latitude"]]
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
            return direct_route_result()

        feature = features[0]
        properties = feature.get("properties", {})
        summary = properties.get("summary", {})
        coordinates = feature.get("geometry", {}).get("coordinates", [])

        if not coordinates or not summary:
            return direct_route_result()

        steps = []
        for segment in properties.get("segments", []):
            for step in segment.get("steps", []):
                steps.append({
                    "instruction": step.get("instruction", "Continue on the current route"),
                    "distance_km": round(step.get("distance", 0) / 1000, 1)
                })

        return {
            "source_name": source_location["address"],
            "destination_name": destination_location["address"],
            "source_coordinates": source_coordinates,
            "destination_coordinates": destination_coordinates,
            "coordinates": [[coordinate[1], coordinate[0]] for coordinate in coordinates],
            "distance_km": summary["distance"] / 1000,
            "duration_seconds": summary["duration"],
            "steps": steps,
            "maps_url": maps_url,
            "profile": profile,
            "travel_option": travel_option,
            "is_detailed": True
        }
    except requests.RequestException:
        return direct_route_result()
    except Exception:
        return direct_route_result()


@st.cache_data(ttl=86400, show_spinner=False)
def reverse_geocode_stop(latitude, longitude):
    try:
        geolocator = Nominatim(user_agent="ai_trip_planner_overnight_stops")
        location = geolocator.reverse(
            (round(latitude, 5), round(longitude, 5)),
            exactly_one=True,
            addressdetails=True,
            language="en",
            timeout=12
        )
        if not location:
            return None
        address = location.raw.get("address", {})
        place_name = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or address.get("county")
        )
        if not place_name:
            return None
        state = address.get("state")
        return f"{place_name}, {state}" if state and state.casefold() not in place_name.casefold() else place_name
    except Exception:
        return None


def route_overnight_stops(route_data, stop_count):
    if stop_count <= 0 or not route_data.get("is_detailed"):
        return []

    coordinates = route_data.get("coordinates", [])
    if len(coordinates) < 3:
        return []

    stops = []
    seen = set()
    for stop_number in range(1, stop_count + 1):
        coordinate_index = round(stop_number * (len(coordinates) - 1) / (stop_count + 1))
        latitude, longitude = coordinates[coordinate_index]
        stop_name = reverse_geocode_stop(latitude, longitude)
        if stop_name and stop_name.casefold() not in seen:
            seen.add(stop_name.casefold())
            stops.append(stop_name)
    return stops


def build_journey_context(source_city, destination, total_days, travel_option):
    route_data = get_route_data(source_city, destination, travel_option)
    if route_data.get("error"):
        return {
            "total_trip_days": total_days,
            "travel_option": travel_option,
            "route_available": False,
            "overnight_stops": [],
            "guidance": "Route details were unavailable. Keep any suggested stop clearly marked as an estimate."
        }

    travel_hours = max(1, route_data["duration_seconds"] / 3600)
    safe_daily_hours = {
        "Bus": 10,
        "Train": 16,
        "Flight": 12,
        "Personal Car": 8,
        "Bike": 6
    }[travel_option]
    travel_days_required = max(1, math.ceil(travel_hours / safe_daily_hours))
    stop_count = min(max(0, travel_days_required - 1), max(0, total_days - 1), 4)

    overnight_stops = []
    if travel_option in ("Bus", "Personal Car", "Bike"):
        overnight_stops = route_overnight_stops(route_data, stop_count)

    if travel_option == "Flight":
        guidance = "Do not add a road stop. Suggest an overnight layover only when a connection genuinely requires it."
    elif travel_option == "Train":
        guidance = "Prefer an overnight train. Suggest a junction stay only for a realistic train change; do not invent train numbers."
    elif overnight_stops:
        guidance = "Use the route-based stop candidates for safe overnight breaks, and keep each travel day within the safe daily limit."
    else:
        guidance = "No reliable intermediate town was found. Recommend a stop only as an estimate and ask the traveler to verify it on the route map."

    return {
        "total_trip_days": total_days,
        "travel_option": travel_option,
        "route_available": True,
        "distance_km": round(route_data["distance_km"]),
        "estimated_travel_hours": round(travel_hours, 1),
        "safe_daily_travel_hours": safe_daily_hours,
        "travel_days_required": travel_days_required,
        "destination_days_available": max(0, total_days - travel_days_required),
        "duration_feasible": total_days >= travel_days_required,
        "overnight_stops": overnight_stops,
        "guidance": guidance
    }


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
    advice_col.info(get_travel_tip(distance_km, route_data["travel_option"]))

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
    link_label = "Check flights" if route_data["travel_option"] == "Flight" else "Open this route in Google Maps"
    st.markdown(f"[{link_label}]({route_data['maps_url']})")

    if not route_data.get("is_detailed"):
        st.caption("This is a connection overview. Confirm the exact operator route and timetable before booking.")

    if route_data["steps"]:
        with st.expander("View route directions"):
            for number, step in enumerate(route_data["steps"][:10], start=1):
                st.write(f"{number}. {step['instruction']} ({step['distance_km']:.1f} km)")
            if len(route_data["steps"]) > 10:
                st.caption("Showing the first 10 directions. Open Google Maps for the complete journey.")


def generate_pdf(text):
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, title="AI Trip Plan")
    styles = getSampleStyleSheet()
    story = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Paragraph(" ", styles["Normal"]))
            continue
        heading_match = re.match(r"^(#{1,3})\s*(.*)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            style = styles["Title"] if level == 1 else styles["Heading2"]
            line = heading_match.group(2)
        else:
            style = styles["Normal"]
            line = re.sub(r"^[-*]\s+", "• ", line)
        story.append(Paragraph(escape(line), style))
    doc.build(story)
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


def send_email(receiver_email, trip_text):
    receiver_email = (receiver_email or "").strip()
    parsed_receiver = parseaddr(receiver_email)[1]
    if not parsed_receiver or "@" not in parsed_receiver:
        raise ValueError("Enter a valid receiver email address.")
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError("Email is not configured. Add SMTP_USER and SMTP_PASSWORD to your environment settings.")

    msg = EmailMessage()
    msg["Subject"] = "Your AI Trip Plan"
    msg["From"] = SMTP_USER
    msg["To"] = parsed_receiver
    msg.set_content(trip_text)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=25) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


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
    
    auth_col = st.columns([1, 1.15, 1])[1]

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
            remember_me = st.checkbox(
                "Remember me on this device",
                value=False,
                disabled=auth_cookies is None,
                key="remember_me_login"
            )
            if auth_cookies is None:
                st.caption("Remember Me requires COOKIE_PASSWORD in the server environment.")

            if st.button("Login", key="login_button"):
                if not login_email or not login_password:
                    st.warning("Please enter email and password")
                else:
                    try:
                        result = supabase.auth.sign_in_with_password({
                            "email": login_email,
                            "password": login_password
                        })
                        store_auth_session(result, login_email, remember_me=remember_me)
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
sidebar_logo_col, sidebar_menu_col, _ = st.sidebar.columns([1, 1, 4])
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

        page_options = ["✈ Trip Planner", "🕒 History"]
        if is_admin_user(st.session_state.current_user):
            page_options.append("⚙ Admin Dashboard")
        if page not in page_options:
            page = page_options[0]
        page = st.radio(
            "Menu",
            page_options,
            index=page_options.index(page),
            key="chrome_page_widget"
        )
        st.session_state.sidebar_page = page

        if st.session_state.logged_in:
            st.divider()
            with st.expander("Saved Destinations", expanded=False):
                try:
                    result = supabase.table("trips").select("destination").eq(
                        "user_email",
                        st.session_state.current_user
                    ).execute()
                    seen_destinations = set()
                    unique_destinations = []
                    for trip in result.data or []:
                        destination_name = (trip.get("destination") or "").strip()
                        destination_key = destination_name.casefold()
                        if destination_name and destination_key not in seen_destinations:
                            seen_destinations.add(destination_key)
                            unique_destinations.append(destination_name)

                    if unique_destinations:
                        for destination_name in unique_destinations:
                            st.write(f"📍 {destination_name}")
                    else:
                        st.caption("No saved destinations yet.")
                except Exception:
                    st.caption("Saved destinations are unavailable right now.")

            if st.button("Logout", key="menu_logout"):
                try:
                    supabase.auth.sign_out()
                except Exception:
                    pass
                clear_remembered_auth()
                clear_auth_state()
                st.session_state.response = ""
                st.session_state.chat_history = []
                st.session_state.images = []
                st.session_state.auth_mode = "Login"
                st.session_state.chrome_menu_open = False
                st.rerun()

if not dark_mode:
    st.markdown("""
    <style>
    .stApp{background:#f4f7fb;color:#111827;}
    section[data-testid="stSidebar"]{background:#ffffff;border-right:1px solid #dbe3ee;}
    .glass-card,.small-card,.metric-box,.plan-card{background:#ffffff;color:#111827;border-color:#dbe3ee;box-shadow:0 8px 24px rgba(15,23,42,.08);}
    .stTextInput input,.stNumberInput input{background:#ffffff !important;color:#111827 !important;}
    [data-testid="stSelectbox"] > div > div{background:#ffffff;color:#111827;}
    </style>
    """, unsafe_allow_html=True)

#----------------------------Part 3---------------------------------------------
# ---------------- HISTORY PAGE ----------------
if page == "🕒 History":

    st.title("📜 Trip History")

    if st.session_state.logged_in:
        try:
            require_auth_session()
            result = supabase.table("trips").select("*").eq(
                "user_email",
                st.session_state.current_user
            ).execute()
            trips = result.data or []
        except Exception:
            trips = list(st.session_state.saved_trips.values())
            st.warning("Cloud history is unavailable. Showing trips saved in this browser session.")

        if trips:
            for trip in reversed(trips):
                st.write("📍", trip.get("destination", "Unknown destination"))
                st.write("📅", f"{trip.get('days', '--')} day(s)")
                st.write("💰", trip.get("budget", "--"))
                with st.expander("View saved plan"):
                    st.markdown(trip.get("trip_plan", "Plan details are unavailable."))
                st.divider()
        else:
            st.info("No Trips Found")
    else:

        st.warning("Please Login")


# ---------------- ADMIN DASHBOARD ----------------
elif page == "⚙ Admin Dashboard":
    st.title("👨‍💻 Admin Dashboard")

    if not is_admin_user(st.session_state.current_user):
        st.error("You do not have admin access.")
    elif not SUPABASE_SERVICE_ROLE_KEY:
        st.info("Add SUPABASE_SERVICE_ROLE_KEY in the server environment to load admin statistics.")
    else:
        try:
            admin_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
            trips_data = admin_client.table("trips").select("*").execute().data or []
            user_emails = sorted({
                trip.get("user_email", "").strip()
                for trip in trips_data
                if trip.get("user_email")
            })

            c1, c2 = st.columns(2)
            c1.metric("Travelers with saved trips", len(user_emails))
            c2.metric("Total saved trips", len(trips_data))
            st.subheader("Travelers")
            for user_email in user_emails:
                st.write("👤", user_email)
        except Exception:
            st.error("Admin data is unavailable. Check the service-role key and trips table configuration.")


# ---------------- TRIP PLANNER PAGE ----------------
elif page == "✈ Trip Planner":

    pending_voice_fields = st.session_state.pending_voice_fields
    if pending_voice_fields:
        voice_to_widget = {
            "source_city": "trip_source_city",
            "destination": "trip_destination",
            "days": "trip_days",
            "interests": "trip_interests",
            "travel_option": "trip_travel_option"
        }
        for field, value in pending_voice_fields.items():
            if field in voice_to_widget:
                st.session_state[voice_to_widget[field]] = value
        st.session_state.pending_voice_fields = None

    # HERO BANNER
    st.markdown("""
    <div class="banner">
        <h1 style="font-size:58px;">Explore The World With AI ✈</h1>
        <p style="font-size:22px;">
        Luxury planning • Smart recommendations • Real-time travel insights
        </p>
    </div>
    """, unsafe_allow_html=True)

    # SERVICE STATUS
    c1, c2, c3 = st.columns(3)
    c1.metric("AI Planner", "Ready" if GEMINI_API_KEY else "Setup needed")
    c2.metric("Live Weather", "Ready" if WEATHER_KEY else "Setup needed")
    c3.metric("Saved Trips", len(st.session_state.saved_trips))

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        destination = st.text_input("📍 Destination", key="trip_destination")

    with col2:
        days = st.number_input("📅 Total Trip Days", 1, 30, step=1, key="trip_days")

    with col3:
        budget = st.selectbox(
            "💰 Budget",
            ["Budget-Friendly", "Moderate", "Luxury"],
            key="trip_budget_level"
        )

    with col4:
        interests = st.text_input("🎯 Interests", key="trip_interests")

    budget_col, members_col, currency_col = st.columns([2, 1, 1])
    with currency_col:
        currency = st.selectbox("Currency", ["INR", "USD", "EUR"], key="trip_currency")
    with budget_col:
        total_budget = st.number_input(
            f"Total Budget ({currency})",
            min_value=0.0,
            step=500.0 if currency == "INR" else 10.0,
            key="trip_total_budget"
        )
    with members_col:
        members = st.number_input("Travelers", min_value=1, max_value=50, step=1, key="trip_members")
    source_city = st.text_input(
        "Starting City",
        placeholder="Add village/city, district and state for best results",
        key="trip_source_city"
    )

    travel_option = st.selectbox(
        "Travel Option",
        ["Bus", "Train", "Flight", "Personal Car", "Bike"],
        key="trip_travel_option"
    )
    stay_type = automatic_stay_type(budget)
    st.caption(f"Stay selected automatically for {budget}: {stay_type}")

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
    planned_context = st.session_state.last_plan_context
    same_planned_destination = (
        planned_context.get("destination", "").casefold() == clean_destination.casefold()
        if clean_destination else False
    )
    weather = planned_context.get("weather", "N/A") if same_planned_destination else "Generate plan to load"
    

    with m1:
        st.markdown(f"""
        <div class="metric-box">
        <h4>📍 Destination</h4>
        <h2>{escape(destination) if destination else '--'}</h2>
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
        just_once=True,
        key="trip_voice_recorder"
    )

    if voice:
        audio_bytes = voice.get("bytes", b"") if isinstance(voice, dict) else b""
        voice_hash = hashlib.sha256(audio_bytes).hexdigest() if audio_bytes else ""
        if voice_hash and voice_hash != st.session_state.processed_voice_hash:
            if st.button("Use Voice Details", key="apply_voice_details"):
                try:
                    with st.spinner("Understanding your travel request..."):
                        transcript = transcribe_voice(voice)
                        extracted_fields = extract_voice_trip_fields(transcript)
                    st.session_state.voice_transcript = transcript
                    st.session_state.processed_voice_hash = voice_hash
                    st.session_state.pending_voice_fields = extracted_fields
                    st.rerun()
                except GeminiQuotaError as error:
                    st.warning(str(error))
                except Exception as error:
                    st.error("Voice input could not be processed right now. Please try again shortly.")

    if st.session_state.voice_transcript:
        st.caption(f"Voice request: {st.session_state.voice_transcript}")

    # AI PLAN GENERATION
    ai_cooldown_remaining = max(
        0,
        math.ceil(st.session_state.get("gemini_cooldown_until", 0) - time.time())
    )
    if ai_cooldown_remaining:
        st.info(f"AI request limit is cooling down. Try again in about {ai_cooldown_remaining} seconds.")

    if st.button("Make My Plan 🚀"):
        destination = clean_city_name(destination)
        
        if destination and source_city.strip():
            with st.spinner("Generating your plan..."):
                try:
                    weather = get_weather(destination)
                    journey_context = build_journey_context(
                        source_city.strip(),
                        destination,
                        days,
                        travel_option
                    )

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
                    Total trip duration: {days} days, counted from departure in {source_city.strip()} to the final day in {destination}
                    Budget style: {budget}
                    Total available budget: {total_budget:.2f} {currency}
                    Travelers: {members}
                    Selected travel: {travel_option}
                    Selected stay: {stay_type}
                    Interests: {interests or "General sightseeing and local culture"}
                    Journey analysis: {json.dumps(journey_context, ensure_ascii=False)}

                    {language_instruction}

                    The {days} days include all travel days, intermediate overnight stops, and destination days. Never add extra days.
                    Respect the selected travel and stay options. For every travel day, state the starting place, ending place, approximate travel time, and overnight city.
                    Use route-based overnight stop candidates when provided. For Train or Flight, follow the journey guidance and do not invent train numbers, flights, schedules, hotel availability, or opening hours.
                    If duration_feasible is false, clearly warn that the selected duration is too short and provide the safest possible adjustment.

                    The Destination Overview must be engaging and specific, not a generic summary. In 5-7 short sentences explain:
                    - what {destination} is best known for
                    - its distinctive history, culture, landscape, or atmosphere
                    - two or three signature experiences that make it worth visiting
                    - a notable local food, craft, tradition, or lesser-known highlight
                    - why it matches the traveler's interests and selected budget style
                    Use accurate, widely established facts. Do not invent legends, statistics, awards, or historical claims.

                    Format:
                    # Destination Overview
                    # Journey and Overnight Stops
                    # Day 1: Source to Stop/Destination
                    - Morning
                    - Afternoon
                    - Evening
                    - Overnight stay
                    # Remaining Day-by-Day Plan
                    # Budget Tips
                    # Foods to Try
                    # Important Booking Checks
                    """

                    response = generate_gemini_content(prompt)
                    st.session_state.response = response.text
                    st.session_state.chat_history = []
                    st.session_state.last_plan_context = {
                        "source_city": source_city.strip(),
                        "destination": destination,
                        "days": days,
                        "budget_level": budget,
                        "total_budget": total_budget,
                        "currency": currency,
                        "members": members,
                        "travel_option": travel_option,
                        "stay_type": stay_type,
                        "interests": interests,
                        "weather": weather,
                        "journey": journey_context
                    }
                except GeminiQuotaError as error:
                    st.warning(str(error))
                except Exception:
                    st.error("The AI service could not generate the plan right now. Please try again shortly.")
                else:
                    st.session_state.images = get_destination_images(destination)
                    saved, save_message = save_trip(
                        destination,
                        days,
                        budget,
                        interests,
                        response.text,
                        metadata=st.session_state.last_plan_context
                    )
                    if saved:
                        st.success("Plan generated and saved successfully.")
                    elif save_message:
                        st.warning(save_message)
                    if not st.session_state.images:
                        st.info("Plan is ready. No reliable destination photos were found for this place.")

        elif not destination:
            st.warning("Please enter destination")
        else:
            st.warning("Please enter Starting City so the total journey days and overnight stops can be planned.")

    # CHATBOT
    st.subheader("💬 Trip Assistant Chatbot")

    user_query = st.text_input("Ask anything about your trip")

    if st.button("Ask AI"):
        if user_query:
            try:
                context = st.session_state.last_plan_context or {
                    "source_city": source_city,
                    "destination": destination,
                    "days": days,
                    "budget_level": budget,
                    "total_budget": total_budget,
                    "currency": currency,
                    "members": members,
                    "travel_option": travel_option,
                    "stay_type": stay_type,
                    "interests": interests,
                    "weather": weather
                }
                prompt = f"""
                You are the user's trip assistant.
                Trip details: {json.dumps(context, ensure_ascii=False)}
                Generated plan: {st.session_state.response[:12000] or "No plan generated yet"}
                Question: {user_query}
                Answer in {language}. Be practical and concise. Clearly label prices, schedules, availability, and opening hours as estimates unless verified.
                """

                reply = generate_gemini_content(prompt).text

                st.session_state.chat_history.append(("You", user_query))
                st.session_state.chat_history.append(("AI", reply))

            except GeminiQuotaError as error:
                st.warning(str(error))
            except Exception:
                st.error("The trip assistant is temporarily unavailable. Please try again shortly.")

    for sender, msg in st.session_state.chat_history:
        st.write(f"**{sender}:** {msg}")
        
#----------------------------Part 4---------------------------------------------
# ---------------- EXTRA FUNCTIONS ----------------
@st.cache_data(ttl=21600, show_spinner=False)
def google_places_search(search_query, limit=5, price_levels=()):
    if not GOOGLE_PLACES_KEY:
        return []

    try:
        request_body = {
            "textQuery": search_query,
            "pageSize": min(limit, 10),
            "languageCode": "en"
        }
        if price_levels:
            request_body["priceLevels"] = list(price_levels)

        response = requests.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": GOOGLE_PLACES_KEY,
                "X-Goog-FieldMask": (
                    "places.displayName,places.formattedAddress,places.rating,"
                    "places.userRatingCount,places.googleMapsUri,places.location,places.priceLevel"
                )
            },
            json=request_body,
            timeout=20
        )
        response.raise_for_status()
        places = []
        for place in response.json().get("places", []):
            display_name = place.get("displayName", {}).get("text")
            if not display_name:
                continue
            places.append({
                "name": display_name,
                "rating": place.get("rating"),
                "rating_count": place.get("userRatingCount"),
                "price_level": place.get("priceLevel"),
                "address": place.get("formattedAddress", "Address unavailable"),
                "maps_url": place.get("googleMapsUri"),
                "source": "Google Places"
            })
        return places
    except requests.RequestException:
        return []


@st.cache_data(ttl=21600, show_spinner=False)
def openstreetmap_places(destination, place_kind, limit=5, budget_level=None):
    location = geocode_place(destination)
    if not location:
        return []

    if place_kind == "hotel":
        tourism_types = {
            "Budget-Friendly": "hostel|guest_house|motel",
            "Moderate": "hotel|guest_house",
            "Luxury": "hotel"
        }.get(budget_level, "hotel|hostel|guest_house|motel")
        selectors = f'nwr(around:30000,{location["latitude"]},{location["longitude"]})["tourism"~"{tourism_types}"];'
    else:
        selectors = "\n".join([
            f'nwr(around:30000,{location["latitude"]},{location["longitude"]})["tourism"~"attraction|museum|viewpoint|gallery|zoo|theme_park"];',
            f'nwr(around:30000,{location["latitude"]},{location["longitude"]})["historic"]["name"];',
            f'nwr(around:30000,{location["latitude"]},{location["longitude"]})["natural"~"peak|waterfall|cave_entrance"]["name"];'
        ])

    query = f"""
    [out:json][timeout:22];
    (
      {selectors}
    );
    out center tags {limit * 4};
    """
    try:
        response = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            headers={"User-Agent": "AITripPlanner/3.1"},
            timeout=30
        )
        response.raise_for_status()
        places = []
        seen = set()
        for element in response.json().get("elements", []):
            tags = element.get("tags", {})
            name = tags.get("name:en") or tags.get("name")
            if not name or name.casefold() in seen:
                continue
            seen.add(name.casefold())
            center = element.get("center", {})
            latitude = element.get("lat") or center.get("lat")
            longitude = element.get("lon") or center.get("lon")
            address_parts = [
                tags.get("addr:housenumber"), tags.get("addr:street"),
                tags.get("addr:city") or tags.get("addr:village") or tags.get("addr:town")
            ]
            address = ", ".join(part for part in address_parts if part) or f"Near {clean_city_name(destination)}"
            maps_url = None
            if latitude is not None and longitude is not None:
                maps_url = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
            places.append({
                "name": name,
                "rating": None,
                "rating_count": None,
                "price_level": None,
                "address": address,
                "maps_url": maps_url,
                "source": "OpenStreetMap"
            })
            if len(places) >= limit:
                break
        return places
    except requests.RequestException:
        return []


def merge_unique_places(primary, fallback, limit=5):
    merged = []
    seen = set()
    for place in primary + fallback:
        key = place["name"].casefold()
        if key not in seen:
            seen.add(key)
            merged.append(place)
        if len(merged) >= limit:
            break
    return merged


def get_real_hotels(destination, budget_level):
    search_settings = {
        "Budget-Friendly": (
            "hostels guest houses and budget hotels",
            ("PRICE_LEVEL_INEXPENSIVE", "PRICE_LEVEL_MODERATE")
        ),
        "Moderate": (
            "mid-range comfort hotels",
            ("PRICE_LEVEL_MODERATE", "PRICE_LEVEL_EXPENSIVE")
        ),
        "Luxury": (
            "luxury premium hotels",
            ("PRICE_LEVEL_EXPENSIVE", "PRICE_LEVEL_VERY_EXPENSIVE")
        )
    }
    search_phrase, price_levels = search_settings.get(budget_level, search_settings["Budget-Friendly"])
    google_results = google_places_search(
        f"{search_phrase} in {clean_city_name(destination)}",
        5,
        price_levels
    )
    osm_results = (
        openstreetmap_places(destination, "hotel", 5, budget_level)
        if len(google_results) < 5 else []
    )
    return merge_unique_places(google_results, osm_results)


def get_real_attractions(destination):
    google_results = google_places_search(f"tourist attractions in {clean_city_name(destination)}", 5)
    osm_results = openstreetmap_places(destination, "attraction", 5) if len(google_results) < 5 else []
    return merge_unique_places(google_results, osm_results)


@st.cache_data(ttl=43200, show_spinner=False)
def get_exchange_rate(from_currency, to_currency):
    if from_currency == to_currency:
        return 1.0
    try:
        response = requests.get(
            f"https://api.frankfurter.dev/v2/rate/{from_currency}/{to_currency}",
            timeout=12
        )
        response.raise_for_status()
        return float(response.json()["rate"])
    except (requests.RequestException, KeyError, TypeError, ValueError):
        inr_values = {"INR": 1.0, "USD": 0.012, "EUR": 0.0105}
        return inr_values[to_currency] / inr_values[from_currency]


def convert_currency(amount, from_currency, to_currency):
    return float(amount) * get_exchange_rate(from_currency, to_currency)


def format_money(amount_in_inr, currency):
    symbols = {"INR": "₹", "USD": "$", "EUR": "€"}
    converted = convert_currency(amount_in_inr, "INR", currency)
    return f"{symbols[currency]}{converted:,.0f}"


def estimate_flight(source, destination, members=1):
    direct_distance = estimate_trip_distance(source, destination)
    if not direct_distance:
        return None

    source_location = geocode_place(source)
    destination_location = geocode_place(destination)
    same_country = (
        source_location and destination_location
        and source_location.get("details", {}).get("country_code")
        == destination_location.get("details", {}).get("country_code")
    )
    one_way_base = max(2500, direct_distance * 5.5) if same_country else max(8000, direct_distance * 7.0)
    low = round(one_way_base * 2 * members / 100) * 100
    high = round(low * 1.75 / 100) * 100
    return low, high


@st.cache_data(ttl=86400, show_spinner=False)
def estimate_trip_distance(source_city, destination):
    source = geocode_place(source_city)
    destination_location = geocode_place(destination)
    if not source or not destination_location:
        return None
    return max(1, round(haversine_distance(source, destination_location)))


def calculate_trip_budget(source_city, destination, days, members, travel_option, budget_level):
    direct_distance = estimate_trip_distance(source_city, destination)
    if not direct_distance:
        return None

    stay_type = automatic_stay_type(budget_level)
    distance_factor = 1.0 if travel_option == "Flight" else 1.15 if travel_option == "Train" else 1.25
    distance_km = round(direct_distance * distance_factor)
    round_trip_distance = distance_km * 2
    if travel_option == "Bus":
        travel_cost = round(round_trip_distance * 1.5 * members)
        travel_note = "Round-trip intercity bus estimate"
    elif travel_option == "Train":
        travel_cost = round(round_trip_distance * 1.1 * members)
        travel_note = "Round-trip train estimate"
    elif travel_option == "Flight":
        flight_range = estimate_flight(source_city, destination, members)
        travel_cost = round(sum(flight_range) / 2) if flight_range else round(distance_km * 11 * members)
        travel_note = "Round-trip flight estimate"
    elif travel_option == "Personal Car":
        vehicles = math.ceil(members / 4)
        travel_cost = round(round_trip_distance * 10.5 * vehicles)
        travel_note = f"Fuel and toll estimate for {vehicles} personal car(s)"
    else:
        vehicles = math.ceil(members / 2)
        travel_cost = round(round_trip_distance * 3.2 * vehicles)
        travel_note = f"Fuel and maintenance estimate for {vehicles} bike(s)"

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
        "stay_type": stay_type,
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
    result_context = st.session_state.last_plan_context
    result_destination = result_context.get("destination") if st.session_state.response else ""
    result_travel_option = result_context.get("travel_option", travel_option)
    result_budget_level = result_context.get("budget_level", budget)
    result_days = result_context.get("days", days)
    result_weather = result_context.get("weather", "N/A")
    plan_ready_for_current_trip = bool(
        st.session_state.response
        and result_destination.casefold() == clean_city_name(destination).casefold()
        and clean_city_name(result_context.get("source_city", "")).casefold()
        == clean_city_name(source_city).casefold()
    )

    if st.session_state.response:
        st.success("🎉 Your plan is ready!")

        st.markdown('<div class="plan-card">', unsafe_allow_html=True)
        st.markdown("## ✨ Your AI Generated Trip Plan")
        st.markdown(st.session_state.response)
        st.markdown('</div>', unsafe_allow_html=True)

        journey = result_context.get("journey", {})
        if journey:
            st.markdown(
                '<div class="section-title">Journey Duration & Overnight Stops</div>',
                unsafe_allow_html=True
            )
            total_col, travel_col, destination_col = st.columns(3)
            total_col.metric("Total trip", f"{journey.get('total_trip_days', result_days)} days")
            travel_col.metric("Journey time", f"{journey.get('estimated_travel_hours', '--')} hours")
            destination_col.metric(
                "Destination time",
                f"{journey.get('destination_days_available', '--')} days"
            )

            if journey.get("duration_feasible") is False:
                st.error(
                    f"This route needs about {journey.get('travel_days_required', '--')} travel day(s) by "
                    f"{journey.get('travel_option', result_travel_option)}. Increase Total Trip Days for a safer plan."
                )

            overnight_stops = journey.get("overnight_stops", [])
            if overnight_stops:
                st.markdown("**Suggested route-based overnight stops**")
                for night_number, stop_name in enumerate(overnight_stops, start=1):
                    st.write(f"Night {night_number}: {stop_name}")
                st.caption("Verify the final hotel and road conditions before departure.")
            else:
                st.info(journey.get("guidance", "No intermediate overnight stop is required."))

        # PDF DOWNLOAD
        pdf_data = generate_pdf(st.session_state.response)
        st.download_button(
            "📄 Download PDF",
            data=pdf_data,
            file_name="trip_plan.pdf",
            mime="application/pdf"
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
                st.image(img["url"], caption=img.get("alt"), use_container_width=True)
                if img.get("credit_url"):
                    st.caption(f"[{img.get('credit', 'Photo source')}]({img['credit_url']})")

    # POSTER
    if st.session_state.response and result_destination:
        st.markdown(
            '<div class="section-title">🖼 Travel Poster</div>',
            unsafe_allow_html=True
        )

        poster = get_poster(result_destination)

        if poster:
            st.markdown('<div class="poster-card">', unsafe_allow_html=True)
            st.image(poster["url"], caption=poster.get("alt"), use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

    # WEATHER
    if st.session_state.response and result_destination:
        st.markdown(
            '<div class="section-title">🌤 Weather</div>',
            unsafe_allow_html=True
        )

        st.info(result_weather)

    # PACKING LIST
    if st.session_state.response and result_destination:
        st.markdown(
            '<div class="section-title">🎒 Packing Checklist</div>',
            unsafe_allow_html=True
        )

        items = packing_list(result_destination, result_weather, result_travel_option, result_days)

        st.markdown('<div class="small-card">', unsafe_allow_html=True)

        for item in items:
            checklist_key = hashlib.sha1(
                f"{result_destination}|{result_travel_option}|{item}".encode("utf-8")
            ).hexdigest()
            st.checkbox(item, key=f"packing_{checklist_key}")

        st.markdown('</div>', unsafe_allow_html=True)

    # BUDGET FEASIBILITY
    if plan_ready_for_current_trip and total_budget > 0:
        st.markdown(
            '<div class="section-title">💰 Trip Budget Check</div>',
            unsafe_allow_html=True
        )

        st.markdown('<div class="small-card">', unsafe_allow_html=True)

        if source_city and destination:
            current_budget_query = (
                clean_city_name(source_city), clean_city_name(destination), days,
                members, travel_option, budget, total_budget, currency
            )
            if st.button("Calculate Trip Budget", key="calculate_trip_budget"):
                with st.spinner("Calculating travel, stay and daily costs..."):
                    st.session_state.budget_result = calculate_trip_budget(
                        source_city,
                        destination,
                        days,
                        members,
                        travel_option,
                        budget
                    )
                    st.session_state.budget_query = current_budget_query

            trip_budget = (
                st.session_state.budget_result
                if st.session_state.budget_query == current_budget_query
                else None
            )

            if trip_budget:
                total_budget_inr = convert_currency(total_budget, currency, "INR")
                difference = total_budget_inr - trip_budget["total"]
                available_col, estimate_col, per_person_col = st.columns(3)
                available_col.metric("Your total budget", f"{currency} {total_budget:,.0f}")
                estimate_col.metric("Estimated trip cost", format_money(trip_budget["total"], currency))
                per_person_col.metric("Estimated per traveler", format_money(trip_budget["total"] / members, currency))

                if difference >= 0:
                    st.success(
                        f"Yes, this budget is workable. You should have about {format_money(difference, currency)} left as extra flexibility."
                    )
                else:
                    st.error(
                        f"This plan is short by about {format_money(abs(difference), currency)}. Increase the budget or choose a cheaper travel/stay option."
                    )

                breakdown = [
                    {
                        "Category": "Round-trip travel",
                        "Estimated group spend": format_money(trip_budget["travel"], currency),
                        "Per traveler": format_money(trip_budget["travel"] / members, currency)
                    },
                    {
                        "Category": f"{trip_budget['stay_type']} stay ({trip_budget['nights']} night(s))",
                        "Estimated group spend": format_money(trip_budget["stay"], currency),
                        "Per traveler": format_money(trip_budget["stay"] / members, currency)
                    },
                    {
                        "Category": "Food",
                        "Estimated group spend": format_money(trip_budget["food"], currency),
                        "Per traveler": format_money(trip_budget["food"] / members, currency)
                    },
                    {
                        "Category": "Local transport and activities",
                        "Estimated group spend": format_money(trip_budget["local"], currency),
                        "Per traveler": format_money(trip_budget["local"] / members, currency)
                    },
                    {
                        "Category": "Emergency buffer",
                        "Estimated group spend": format_money(trip_budget["buffer"], currency),
                        "Per traveler": format_money(trip_budget["buffer"] / members, currency)
                    }
                ]
                st.dataframe(breakdown, hide_index=True, use_container_width=True)
                st.caption(
                    f"Distance used: about {trip_budget['distance_km']} km one way. "
                    f"Travel estimate: {trip_budget['travel_note']}. Currency conversion uses a recent reference rate. "
                    "Prices are planning estimates and can change with dates and bookings."
                )
            elif st.session_state.budget_query == current_budget_query:
                st.warning("We could not calculate this route. Add the district, state, or country to both places and try again.")
            else:
                st.info("Select Calculate Trip Budget to check feasibility and category-wise spending.")
        else:
            st.info("Enter both Starting City and Destination to check whether your budget is sufficient.")

        st.markdown('</div>', unsafe_allow_html=True)

    # HOTELS + ATTRACTIONS
    if st.session_state.response and result_destination:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown('<div class="small-card">', unsafe_allow_html=True)
            st.subheader(f"🏨 Top {result_budget_level} Stays")

            hotels = get_real_hotels(result_destination, result_budget_level)

            if hotels:
                for hotel in hotels:
                    st.write(f"🏨 **{hotel['name']}**")
                    if hotel.get("rating") is not None:
                        rating_count = f" ({hotel['rating_count']} reviews)" if hotel.get("rating_count") else ""
                        st.write(f"⭐ {hotel['rating']}{rating_count}")
                    if hotel.get("price_level"):
                        price_label = hotel["price_level"].replace("PRICE_LEVEL_", "").replace("_", " ").title()
                        st.write(f"Price category: {price_label}")
                    st.write(f"📍 {hotel['address']}")
                    if hotel.get("maps_url"):
                        st.markdown(f"[View on map]({hotel['maps_url']})")
                    st.caption(f"Source: {hotel['source']}")
                    st.divider()
                st.caption(
                    f"Filtered for the {result_budget_level} budget tier. Verify current room rates and availability before booking."
                )
            else:
                st.info(f"No verified {result_budget_level.lower()} stays were found nearby.")

            st.markdown('</div>', unsafe_allow_html=True)

        with col2:
            st.markdown('<div class="small-card">', unsafe_allow_html=True)
            st.subheader("🏛 Top Attractions")

            attractions = get_real_attractions(result_destination)

            if attractions:
                for place in attractions:
                    st.write(f"📍 **{place['name']}**")
                    st.write(place["address"])
                    if place.get("rating") is not None:
                        st.write(f"⭐ {place['rating']}")
                    if place.get("maps_url"):
                        st.markdown(f"[View on map]({place['maps_url']})")
                    st.caption(f"Source: {place['source']}")
                    st.divider()
            else:
                st.info("No verified attraction listings were found nearby.")

            st.markdown('</div>', unsafe_allow_html=True)

    # FLIGHT COST
    if travel_option == "Flight" and source_city and destination:
        flight_range = estimate_flight(source_city, destination, members)
        if flight_range:
            price = f"{format_money(flight_range[0], currency)} - {format_money(flight_range[1], currency)}"
            st.markdown(f"""
            <div class="flight-card">
            <h2>✈ Estimated Round-trip Flight Cost</h2>
            <h1>{price}</h1>
            <p>{escape(source_city)} → {escape(destination)} · {members} traveler(s)</p>
            </div>
            """, unsafe_allow_html=True)
            st.caption("Planning estimate only. Check airline or booking websites for travel-date fares and baggage rules.")

    # ROUTE PLANNER
    if plan_ready_for_current_trip and source_city and destination:
        st.markdown(
            '<div class="section-title">🗺 Route Planner</div>',
            unsafe_allow_html=True
        )
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)

        route_query = (
            clean_city_name(source_city),
            clean_city_name(destination),
            travel_option
        )
        if st.button("Show Detailed Route", key="show_detailed_route"):
            with st.spinner("Finding the best route..."):
                st.session_state.route_data = get_route_data(
                    source_city,
                    destination,
                    travel_option
                )
                st.session_state.route_query = route_query

        if st.session_state.route_query == route_query and st.session_state.route_data:
            display_route(st.session_state.route_data)
        else:
            st.info(f"Select Show Detailed Route to view the recommended {travel_option.lower()} connection.")

        st.markdown('</div>', unsafe_allow_html=True)
    elif plan_ready_for_current_trip and destination:
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
