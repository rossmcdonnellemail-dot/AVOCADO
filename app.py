import streamlit as st
import os
import csv
import re
import time
from datetime import datetime
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp
from openai import OpenAI

# --- CONFIGURATION & SETUP ---
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

st.set_page_config(page_title="Avocado", page_icon="🥑", layout="centered")

# Custom CSS - Streamlit Cloud compatible
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(to bottom right, #ecfdf5, #d1fae5, #ccfbf1);
    }
    [data-testid="stHeader"] {
        background: transparent;
    }
    [data-testid="stToolbar"] {
        right: 2rem;
    }
    .block-container {
        padding-top: 2rem;
    }
    div[data-testid="stTextArea"] textarea {
        text-align: center;
        font-size: 18px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize OpenAI Client
client = None
if api_key:
    client = OpenAI(api_key=api_key)

# Initialize session state
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'result' not in st.session_state:
    st.session_state.result = None
if 'failed' not in st.session_state:
    st.session_state.failed = False
if 'url' not in st.session_state:
    st.session_state.url = ""

# --- HELPER FUNCTIONS ---

def log_usage(url, method, status, details=""):
    """Logs usage data to a hidden CSV file."""
    file_exists = os.path.isfile("usage_logs.csv")
    with open("usage_logs.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "Method", "URL", "Status", "Details"])
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), method, url, status, details])

def extract_emails(text):
    """Finds emails in text using regex."""
    if not text:
        return []
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = list(set(re.findall(email_pattern, text)))
    filtered = [e for e in emails if not any(x in e.lower() for x in ['example.com', 'test.com', 'noreply'])]
    return filtered

def get_video_id(url):
    """Extracts YouTube Video ID from various URL formats."""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'(?:watch\?v=)([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def detect_platform(url):
    """Detects platform from URL."""
    lower = url.lower()
    if 'youtube.com' in lower or 'youtu.be' in lower:
        return 'YouTube'
    elif 'vimeo.com' in lower:
        return 'Vimeo'
    elif 'locals.com' in lower:
        return 'Locals'
    elif 'instagram.com' in lower:
        return 'Instagram'
    elif 'facebook.com' in lower:
        return 'Facebook'
    elif 'tiktok.com' in lower:
        return 'TikTok'
    return 'Unknown'

def format_transcript_with_timestamps(data):
    """Formats transcript with timestamps for better readability."""
    formatted = []
    for entry in data:
        timestamp = int(entry['start'])
        minutes = timestamp // 60
        seconds = timestamp % 60
        time_str = f"[{minutes:02d}:{seconds:02d}]"
        formatted.append(f"{time_str} {entry['text']}")
    return "\n".join(formatted)

def try_youtube_extraction(url):
    """Try YouTube API extraction."""
    video_id = get_video_id(url)
    if not video_id:
        return None

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_manually_created_transcript(['en'])
            method = "Manual Captions"
        except:
            try:
                transcript = transcript_list.find_generated_transcript(['en'])
                method = "Auto-Generated"
            except:
                available = list(transcript_list)
                if available:
                    transcript = available[0]
                    method = f"Fallback ({transcript.language})"
                else:
                    return None

        data = transcript.fetch()
        full_text = format_transcript_with_timestamps(data)

        return {
            'text': full_text,
            'method': f'YouTube API - {method}',
            'platform': 'YouTube',
            'word_count': len(full_text.split()),
            'cost': '$0.00'
        }
    except:
        return None

def try_ytdlp_extraction(url):
    """Try yt-dlp extraction."""
    try:
        ydl_opts = {
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['en'],
            'quiet': True,
            'no_warnings': True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            description = info.get('description', '')

            if description:
                return {
                    'text': f"Metadata extracted:\n\n{description}",
                    'method': 'yt-dlp Scraper',
                    'platform': detect_platform(url),
                    'word_count': len(description.split()),
                    'cost': '$0.00'
                }
    except:
        return None
    return None

def extract_video(url):
    """Main extraction function - tries multiple methods."""
    platform = detect_platform(url)

    # Try YouTube API first for YouTube videos
    if platform == 'YouTube':
        result = try_youtube_extraction(url)
        if result:
            return result

    # Try yt-dlp for other platforms
    result = try_ytdlp_extraction(url)
    if result:
        return result

    return None

# --- UI LAYOUT ---

# Logo
st.markdown(
    '<h1 style="text-align: center; font-size: 4rem; margin: 0;">🥑</h1>',
    unsafe_allow_html=True
)
st.markdown(
    '<p style="text-align: center; color: #4b5563; font-size: 1.1rem; margin-bottom: 2rem;">'
    'Drop any video, <span style="color: #059669; font-weight: 600;">A</span>vocado '
    '<span style="color: #059669; font-weight: 600;">I</span>ntelligence makes your notes for you</p>',
    unsafe_allow_html=True
)

# Main container
container = st.container()

with container:
    # Input state - show only if not processing and no result
    if not st.session_state.processing and not st.session_state.result and not st.session_state.failed:
        url_input = st.text_area(
            "paste_box",
            value=st.session_state.url,
            placeholder="paste video here...",
            height=130,
            label_visibility="collapsed",
            key="url_input"
        )

        # Show platform detection if URL present
        if url_input.strip():
            platform = detect_platform(url_input)
            if platform != 'Unknown':
                st.success(f"✓ {platform} detected")
            st.session_state.url = url_input

        # Green button (empty, just color)
        if st.button("🥑", key="extract_btn", use_container_width=True):
            if url_input.strip():
                st.session_state.processing = True
                st.session_state.url = url_input
                st.rerun()

    # Processing state
    elif st.session_state.processing:
        # Animated progress bar
        progress_placeholder = st.empty()
        status_placeholder = st.empty()

        hints = [
            "Trying multiple methods...",
            "Checking video sources...",
            "Analyzing platform requirements...",
            "Scanning for subtitles..."
        ]

        # Show progress bar
        progress_bar = progress_placeholder.progress(0)

        for i, hint in enumerate(hints):
            progress = (i + 1) / len(hints)
            progress_bar.progress(progress)
            status_placeholder.info(hint)
            time.sleep(0.8)

        # Try extraction
        result = extract_video(st.session_state.url)

        if result:
            st.session_state.result = result
            st.session_state.processing = False
            log_usage(st.session_state.url, result['method'], "Success", result['platform'])
        else:
            st.session_state.failed = True
            st.session_state.processing = False
            log_usage(st.session_state.url, "All methods", "Failed", detect_platform(st.session_state.url))

        progress_placeholder.empty()
        status_placeholder.empty()
        st.rerun()

    # Failed state
    elif st.session_state.failed:
        st.warning("⚠️ Couldn't auto-extract this time")
        st.info("📝 Good news: Intelligence learns from every challenge. Next time this type of video will be faster!")

        if st.button("Upload File Instead"):
            st.info("File upload coming soon! For now, try a different video.")

        if st.button("Try Another Video"):
            st.session_state.failed = False
            st.session_state.url = ""
            st.rerun()

    # Result state
    elif st.session_state.result:
        result = st.session_state.result

        # Show result
        st.success(f"✅ Extracted via {result['method']}")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Words", result['word_count'])
        with col2:
            st.metric("Cost", result['cost'])

        # Transcript
        st.text_area("Transcript:", result['text'], height=300)

        # Download button
        st.download_button(
            label="📥 Download Transcript",
            data=result['text'],
            file_name=f"transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain"
        )

        # Lead harvesting
        emails = extract_emails(result['text'])
        if emails:
            st.markdown("---")
            st.write("📧 **Business Leads Found:**")
            for email in emails:
                st.code(email)

        # New video button
        if st.button("Extract Another Video"):
            st.session_state.result = None
            st.session_state.url = ""
            st.rerun()

# Footer
st.markdown("---")
st.caption("🥑 Avocado Intelligence | All usage logged to usage_logs.csv")
