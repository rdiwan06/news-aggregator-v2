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
        model="claude-3-5-sonnet-latest", # Updated to current stable model
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
    ("Gemini Flash",        lambda p, t: _call_gemini_model('gemini-1.5-flash', p, t)),
    ("Gemini Pro",          lambda p, t: _call_gemini_model('gemini-1.5-pro', p, t)),
    ("Claude (Anthropic)",  _call_claude),
]

RATE_LIMIT_SIGNALS = [
    "rate_limit", "rate limit", "quota", "429", "overloaded",
    "resource_exhausted", "insufficient_quota", "too many requests",
    "credit balance is too low", "your credit balance",
]

def _is_rate_limit_error(e: Exception) -> bool:
    return any(sig in str(e).lower() for sig in RATE_LIMIT_SIGNALS)

FORMAT_INSTRUCTIONS = {
    "Bullet Points": (
        "Provide a concise list of the week's top 5 developments with 2 bullets each. "
        "Focus on speed of reading."
    ),
    "Short Format (2-3 min)": (
        "Write a 500-word executive summary. Group stories by theme and provide a "
        "high-level overview of the global state of affairs."
    ),
    "Longform Narrative (7-10 min)": (
        "Write a comprehensive, 1,500-word deep-dive feature story.\n"
        "- Use a compelling 'Big Picture' headline.\n"
        "- Start with a global 'state of the union' lede.\n"
        "- Create long, detailed sections for each major global event.\n"
        "- Explicitly contrast source perspectives.\n"
        "- Include a 'Media Bias Analysis' section at the end.\n"
        "- Use a sophisticated, journalistic tone."
    ),
}

def generate_digest(articles, format_type):
    if not articles:
        return "No data found."

    raw_data = "".join(
        f"SOURCE: {a['source']['name']} | TITLE: {a['title']} | CONTENT: {a['description']}\n---\n"
        for a in articles
    )

    prompt = f"""
    REQUIRED FORMAT: {FORMAT_INSTRUCTIONS[format_type]}

    OBJECTIVE: Using the news data below, synthesize a holistic view of the past week.
    Ensure you are 100% unbiased. If sources disagree, present both arguments with equal weight.
    Use each source roughly the same number of times.

    DATA:
    {raw_data}
    """

    max_tokens = 4000 if "Longform" in format_type else 2000
    last_error = None

    for name, fn in PROVIDERS:
        try:
            result = fn(prompt, max_tokens)
            st.session_state["last_provider"] = name
            return result
        except Exception as e:
            if _is_rate_limit_error(e):
                st.warning(f"⚠️ {name} is at capacity — trying next provider…")
                last_error = e
                continue
            return f"Synthesis Error ({name}): {str(e)}"

    return f"All AI providers are currently unavailable
