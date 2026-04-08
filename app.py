import streamlit as st
import requests
import google.generativeai as genai
from datetime import datetime, timedelta

# --- CONFIGURATION ---
NEWS_API_KEY = st.secrets["NEWS_API_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

# --- THE FINAL FIX ---
genai.configure(api_key=GEMINI_API_KEY)
# Update this line to the 2026 standard model
model = genai.GenerativeModel('gemini-2.5-flash')
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

# --- THE ADVANCED SYNTHESIS ENGINE ---
def generate_digest(articles, format_type):
    if not articles: return "No data found."
    
    raw_data = ""
    for a in articles:
        raw_data += f"SOURCE: {a['source']['name']} | TITLE: {a['title']} | CONTENT: {a['description']}\n---\n"
    
    # Logic for format lengths
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
    You are a world-class investigative journalist specializing in objective media synthesis.
    
    REQUIRED FORMAT: {format_instructions[format_type]}
    
    OBJECTIVE: Using the news data below, synthesize a holistic view of the past week. 
    Ensure you are 100% unbiaseed. If sources disagree, present both arguments with equal weight. Do this by using each sourcee roughly the same number of times.
    
    DATA:
    {raw_data}
    """
    
    try:
        # We increase the token limit for the longform format
        max_tokens = 10000 if "Longform" in format_type else 4000
        response = model.generate_content(prompt, generation_config={"max_output_tokens": max_tokens})
        return response.text
    except Exception as e:
        return f"Synthesis Error: {str(e)}"

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
            # Displaying the synthesis
            st.markdown(generate_digest(articles, read_format))
            
            st.divider()
            with st.expander("References & Sources"):
                for art in articles:
                    st.write(f"**{art['source']['name']}**: [{art['title']}]({art['url']})")
        else:
            st.error("No news found. Try adding more mainstream international sources.")
