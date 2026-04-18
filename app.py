import streamlit as st
import requests
import anthropic
import google.generativeai as genai
from datetime import datetime, timedelta
from supabase import create_client, Client

# ---------------------------------------------------------------
# 1. CONFIGURATION & CLIENT INITIALIZATION
# ---------------------------------------------------------------
NEWS_API_KEY = st.secrets["NEWS_API_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
ANTHROPIC_API_KEY = st.secrets["ANTHROPIC_API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

genai.configure(api_key=GEMINI_API_KEY)
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="NeutralGround Weekly", layout="wide", page_icon="⚖️")

# ---------------------------------------------------------------
# 2. DATA FETCHING 
# ---------------------------------------------------------------

@st.cache_data(ttl=3600)
def get_all_sources():
    url = f"https://newsapi.org/v2/top-headlines/sources?apiKey={NEWS_API_KEY}"
    try:
        response = requests.get(url).json()
        return {s['name']: s['id'] for s in response.get("sources", [])}
    except Exception:
        return {"BBC News": "bbc-news", "Reuters": "reuters"}

def fetch_weekly_news(source_ids):
    source_str = ",".join(source_ids)
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    url = (
        f"https://newsapi.org/v2/everything?sources={source_str}&from={seven_days_ago}"
        f"&sortBy=popularity&pageSize=20&apiKey={NEWS_API_KEY}"
    )
    try:
        response = requests.get(url).json()
        return response.get("articles", [])
    except Exception:
        return []

# ---------------------------------------------------------------
# 3. AI PROVIDER LOGIC
# ---------------------------------------------------------------

def _call_claude(prompt: str, max_tokens: int) -> str:
    msg = claude_client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=max_tokens,
        system="You are a world-class investigative journalist specializing in objective media synthesis.",
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text

def _call_gemini_model(model_name: str, prompt: str, max_tokens: int) -> str:
    m = genai.GenerativeModel(model_name)
    response = m.generate_content(
        prompt,
        generation_config={"max_output_tokens": max_tokens}
    )
    return response.text

PROVIDERS = [
    ("Gemini Flash", lambda p, t: _call_gemini_model('gemini-1.5-flash', p, t)),
    ("Gemini Pro", lambda p, t: _call_gemini_model('gemini-1.5-pro', p, t)),
    ("Claude (Anthropic)", _call_claude),
]

RATE_LIMIT_SIGNALS = ["rate_limit", "quota", "429", "overloaded", "exhausted"]

def _is_rate_limit_error(e: Exception) -> bool:
    return any(sig in str(e).lower() for sig in RATE_LIMIT_SIGNALS)

FORMAT_INSTRUCTIONS = {
    "Bullet Points": "Provide a concise list of the week's top 5 developments with 2 bullets each.",
    "Short Format (2-3 min)": "Write a 500-word executive summary grouped by theme.",
    "Longform Narrative (7-10 min)": "Write a 1,500-word deep-dive feature story with media bias analysis."
}

def generate_digest(articles, format_type):
    if not articles:
        return "No data found."

    raw_data = "".join(f"SOURCE: {a['source']['name']} | TITLE: {a['title']}\n" for a in articles)
    prompt = f"FORMAT: {FORMAT_INSTRUCTIONS[format_type]}\n\nDATA:\n{raw_data}"
    
    max_tokens = 4000 if "Longform" in format_type else 2000
    last_error = "Unknown Error"

    for name, fn in PROVIDERS:
        try:
            result = fn(prompt, max_tokens)
            st.session_state["last_provider"] = name
            return result
        except Exception as e:
            last_error = str(e)
            if _is_rate_limit_error(e):
                st.warning(f"⚠️ {name} capacity limit. Trying next...")
                continue
            return f"Error with {name}: {last_error}"

    return f"All AI providers unavailable. Last error: {last_error}"

# ---------------------------------------------------------------
# 4. DATABASE & AUTH HELPERS
# ---------------------------------------------------------------

def save_digest(user_id, title, format_type, sources, content):
    data = {"user_id": user_id, "title": title, "format_type": format_type, "sources": sources, "content": content}
    return supabase.table("digests").insert(data).execute()

def load_past_digests(user_id):
    try:
        res = supabase.table("digests").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        return res.data
    except:
        return []

def log_out():
    st.session_state["user"] = None
    st.rerun()

# ---------------------------------------------------------------
# 5. MAIN APP UI
# ---------------------------------------------------------------

def show_main_app():
    user = st.session_state["user"]
    st.sidebar.header("Settings")
    read_format = st.sidebar.radio("Depth:", list(FORMAT_INSTRUCTIONS.keys()))
    
    available_sources = get_all_sources()
    selected_names = st.sidebar.multiselect("Outlets:", options=sorted(available_sources.keys()), default=["BBC News", "Reuters"])

    if st.sidebar.button("Log out"):
        log_out()

    tab1, tab2 = st.tabs(["Generate", "History"])

    with tab1:
        st.title("⚖️ NeutralGround")
        if st.button("Generate", use_container_width=True):
            with st.spinner("Synthesizing..."):
                ids = [available_sources[name] for name in selected_names]
                articles = fetch_weekly_news(ids)
                if articles:
                    content = generate_digest(articles, read_format)
                    st.markdown(content)
                    save_digest(str(user.id), f"Digest {datetime.now().date()}", read_format, selected_names, content)
                else:
                    st.error("No news found.")

    with tab2:
        digests = load_past_digests(str(user.id))
        for d in digests:
            with st.expander(f"{d['title']} - {d['created_at'][:10]}"):
                st.markdown(d['content'])

# ---------------------------------------------------------------
# 6. ENTRY POINT
# ---------------------------------------------------------------

if "user" not in st.session_state or st.session_state["user"] is None:
    st.title("Login")
    email = st.text_input("Email")
    pw = st.text_input("Password", type="password")
    if st.button("Login"):
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": pw})
            st.session_state["user"] = res.user
            st.rerun()
        except Exception as e:
            st.error(f"Failed: {e}")
else:
    show_main_app()
