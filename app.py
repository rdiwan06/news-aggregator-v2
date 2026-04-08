import streamlit as st
import requests
import anthropic
import google.generativeai as genai
from datetime import datetime, timedelta

# --- CONFIGURATION ---
NEWS_API_KEY = st.secrets["NEWS_API_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
ANTHROPIC_API_KEY = st.secrets["ANTHROPIC_API_KEY"]

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.5-flash')
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

st.set_page_config(page_title="NeutralGround Weekly", layout="wide", page_icon="⚖️")

# --- DATA FETCHING ---
@st.cache_data(ttl=3600)
def get_all_sources():
    url = f"https://newsapi.org/v2/top-headlines/sources?apiKey={NEWS_API_KEY}"
    try:
        response = requests.get(url).json()
        return {s['name']: s['id'] for s in response.get("sources", [])}
    except:
        return {"BBC News": "bbc-news", "Reuters": "reuters"}

def fetch_weekly_news(source_ids):
    source_str = ",".join(source_ids)
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    url = (f"https://newsapi.org/v2/everything?sources={source_str}&from={seven_days_ago}"
           f"&sortBy=popularity&pageSize=20&apiKey={NEWS_API_KEY}")
    try:
        response = requests.get(url).json()
        return response.get("articles", [])
    except:
        return []

# --- PROVIDER CALLS ---

def _call_claude(prompt: str, max_tokens: int) -> str:
    """Call Claude (Anthropic). Raises on rate limit / quota errors."""
    msg = claude_client.messages.create(
        model="claude-haiku-4-5-20251001",   # cheapest + fastest; swap to claude-sonnet-4-6 for higher quality
        max_tokens=max_tokens,
        system="You are a world-class investigative journalist specializing in objective media synthesis.",
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _call_gemini(prompt: str, max_tokens: int) -> str:
    """Call Gemini. Raises on rate limit / quota errors."""
    response = gemini_model.generate_content(
        prompt,
        generation_config={"max_output_tokens": max_tokens}
    )
    return response.text


# --- FALLBACK ENGINE ---
# Providers tried in order. To prefer Gemini first, swap the list.
PROVIDERS = [
    ("Claude (Anthropic)", _call_claude),
    ("Gemini (Google)", _call_gemini),
]

RATE_LIMIT_SIGNALS = ["rate_limit", "rate limit", "quota", "429", "overloaded",
                       "resource_exhausted", "insufficient_quota", "too many requests"]

def _is_rate_limit_error(e: Exception) -> bool:
    return any(sig in str(e).lower() for sig in RATE_LIMIT_SIGNALS)


def generate_digest(articles, format_type):
    if not articles:
        return "No data found."

    raw_data = ""
    for a in articles:
        raw_data += f"SOURCE: {a['source']['name']} | TITLE: {a['title']} | CONTENT: {a['description']}\n---\n"

    format_instructions = {
        "Bullet Points": "Provide a concise list of the week's top 5 developments with 2 bullets each. Focus on speed of reading.",
        "Short Format (2-3 min)": "Write a 500-word executive summary. Group stories by theme and provide a high-level overview of the global state of affairs.",
        "Longform Narrative (7-10 min)": """Write a comprehensive, 1,500-word deep-dive feature story.
        - Use a compelling 'Big Picture' headline.
        - Start with a global 'state of the union' lede.
        - Create long, detailed sections for each major global event.
        - Explicitly contrast source perspectives (e.g., 'While Source X focuses on the economic fallout, Source Y emphasizes the human rights angle').
        - Include a 'Media Bias Analysis' section at the end explaining how the week was framed globally.
        - Use a sophisticated, journalistic tone."""
    }

    prompt = f"""
    REQUIRED FORMAT: {format_instructions[format_type]}

    OBJECTIVE: Using the news data below, synthesize a holistic view of the past week.
    Ensure you are 100% unbiased. If sources disagree, present both arguments with equal weight.
    Use each source roughly the same number of times.

    DATA:
    {raw_data}
    """

    max_tokens = 10000 if "Longform" in format_type else 4000

    last_error = None
    for name, fn in PROVIDERS:
        try:
            result = fn(prompt, max_tokens)
            # Show which provider was used (subtle, in the expander)
            st.session_state["last_provider"] = name
            return result
        except Exception as e:
            if _is_rate_limit_error(e):
                st.warning(f"⚠️ {name} is at capacity — trying next provider…")
                last_error = e
                continue
            # Unexpected error: surface it directly
            return f"Synthesis Error ({name}): {str(e)}"

    return f"All AI providers are currently unavailable. Last error: {last_error}"


# --- UI DASHBOARD ---
st.title("⚖️ The Neutral Ground: DeepDive")
st.write(f"**Holistic Media Synthesis** | {datetime.now().strftime('%A, %B %d')}")

# SIDEBAR
st.sidebar.header("1. Digest Settings")
read_format = st.sidebar.radio(
    "Select Reading Depth:",
    ["Bullet Points", "Short Format (2-3 min)", "Longform Narrative (7-10 min)"],
    index=1
)

st.sidebar.divider()
st.sidebar.header("2. Sources")
available_sources = get_all_sources()
all_names = sorted(list(available_sources.keys()))
default_names = [n for n in ["BBC News", "Reuters", "The Wall Street Journal", "Al Jazeera English", "The Associated Press"] if n in all_names]

selected_names = st.sidebar.multiselect("Select outlets:", options=all_names, default=default_names)

if st.sidebar.button("Generate Digest", use_container_width=True):
    with st.spinner(f"Writing your {read_format}... this may take a moment."):
        ids = [available_sources[name] for name in selected_names]
        articles = fetch_weekly_news(ids)

        if articles:
            st.markdown(f"## {read_format}")
            st.write("---")
            st.markdown(generate_digest(articles, read_format))

            st.divider()
            with st.expander("References & Sources"):
                # Show which provider was used
                provider_used = st.session_state.get("last_provider", "Unknown")
                st.caption(f"Generated by: **{provider_used}**")
                st.write("")
                for art in articles:
                    st.write(f"**{art['source']['name']}**: [{art['title']}]({art['url']})")
        else:
            st.error("No news found. Try adding more mainstream international sources.")
