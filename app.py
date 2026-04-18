import streamlit as st
import requests
import anthropic
import google.generativeai as genai
from datetime import datetime, timedelta

# ---------------------------------------------------------------
# 1. CONFIGURATION (Requires only News and AI Keys)
# ---------------------------------------------------------------
NEWS_API_KEY = st.secrets["NEWS_API_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
ANTHROPIC_API_KEY = st.secrets["ANTHROPIC_API_KEY"]

genai.configure(api_key=GEMINI_API_KEY)
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

st.set_page_config(page_title="NeutralGround Weekly", layout="wide", page_icon="⚖️")

# ---------------------------------------------------------------
# 2. DATA FETCHING 
# ---------------------------------------------------------------

@st.cache_data(ttl=3600)
def get_all_sources():
    url = f"https://newsapi.org/v2/top-headlines/sources?apiKey={NEWS_API_KEY}"
    try:
        response = requests.get(url).json()
        sources = response.get("sources", [])
        if not sources:
            return {"BBC News": "bbc-news", "Reuters": "reuters"}
        return {s['name']: s['id'] for s in sources}
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
    ("Claude (Anthropic)", _call_claude),
]

FORMAT_INSTRUCTIONS = {
    "Bullet Points": "Provide a concise list of the week's top 5 developments with 2 bullets each. Focus on speed of reading.",
    "Short Format (2-3 min)": "Write a 500-word executive summary. Group stories by theme and provide a high-level overview.",
    "Longform Narrative (7-10 min)": "Write a comprehensive, 1,500-word deep-dive feature story. Contrast source perspectives and include a 'Media Bias Analysis' section."
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
    OBJECTIVE: Synthesize the news data below. Be 100% unbiased. 
    DATA:
    {raw_data}
    """

    for name, fn in PROVIDERS:
        try:
            return fn(prompt, 4000 if "Longform" in format_type else 2000)
        except Exception as e:
            st.warning(f"⚠️ {name} failed, trying next provider...")
            continue
    return "All AI providers are currently unavailable."

# ---------------------------------------------------------------
# 4. THE MAIN WEBSITE UI
# ---------------------------------------------------------------

st.title("⚖️ NeutralGround: DeepDive")
st.write(f"**Holistic Media Synthesis** | {datetime.now().strftime('%A, %B %d, %Y')}")

# --- Sidebar ---
st.sidebar.header("Settings")
read_format = st.sidebar.radio("Select Reading Depth:", list(FORMAT_INSTRUCTIONS.keys()), index=1)

st.sidebar.divider()
st.sidebar.header("Sources")
available_sources = get_all_sources()
selected_names = st.sidebar.multiselect(
    "Select outlets:", 
    options=sorted(available_sources.keys()), 
    default=[n for n in ["BBC News", "Reuters", "The Associated Press"] if n in available_sources]
)

# --- Main Action ---
if st.button("Generate Digest", use_container_width=True):
    if not selected_names:
        st.error("Please select at least one source in the sidebar.")
    else:
        with st.spinner(f"Synthesizing your {read_format}..."):
            ids = [available_sources[name] for name in selected_names]
            articles = fetch_weekly_news(ids)

            if articles:
                content = generate_digest(articles, read_format)
                
                st.markdown(f"## {read_format}")
                st.write("---")
                st.markdown(content)

                st.divider()
                with st.expander("View Original References"):
                    for art in articles:
                        st.write(f"**{art['source']['name']}**: [{art['title']}]({art['url']})")
            else:
                st.error("No articles found for these sources in the last 7 days.")
