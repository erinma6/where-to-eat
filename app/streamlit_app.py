"""
Streamlit chatbot for restaurant recommendations.
"""

import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import asyncio
import streamlit as st
import re
from typing import List, Dict, Any
from src.services.search import SearchService, QueryParser, SearchFilters
from src.db.supabase_client import RestaurantRepository


# Page config
st.set_page_config(
    page_title="Where to Eat?",
    page_icon="🍽️",
    layout="centered"
)

# Editorial theme - warm cream & burnt sienna
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600&family=Playfair+Display:wght@400;500;600&display=swap" rel="stylesheet">

<style>
    :root {
        --cream: #F5F0E8;
        --cream-dark: #EDE8E0;
        --charcoal: #1A1A1A;
        --charcoal-light: #333333;
        --sienna: #B85C38;
        --sienna-dark: #8B4513;
        --gray: #666666;
        --gray-light: #999999;
    }

    /* Base theme */
    html, body, .stApp, .stMainBlockContainer, .stVerticalBlock {
        background-color: var(--cream) !important;
    }

    /* Hide avatars in chat */
    [data-testid="stChatMessageAvatar"] {
        display: none !important;
    }
    div[data-testid="stChatMessageAvatar"] {
        display: none !important;
    }
    .stChatMessageAvatar {
        display: none !important;
    }
    img[alt="assistant"] {
        display: none !important;
    }
    span[data-testid="stChatMessageAvatar"] {
        display: none !important;
    }

    div, section, main, header, footer {
        background-color: var(--cream) !important;
    }

    /* Typography */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Playfair Display', Georgia, serif !important;
        color: var(--charcoal) !important;
        font-weight: 500 !important;
    }

    h1 { font-size: 2.5rem !important; letter-spacing: -0.02em !important; }
    h2 { font-size: 1.75rem !important; letter-spacing: -0.01em !important; }
    h3 { font-size: 1.4rem !important; }

    p, .stMarkdown, .stMarkdown p, .stText, span:not(.stIcon) {
        font-family: 'DM Sans', -apple-system, sans-serif !important;
        color: var(--charcoal) !important;
        line-height: 1.6 !important;
    }

    /* Chat input styling */
    .stChatMessageContent, .stChatInputContainer, .stChatInput {
        background-color: var(--cream-dark) !important;
        border-radius: 12px !important;
    }

    textarea, input {
        background-color: #FFFFFF !important;
        color: var(--charcoal) !important;
        border: 1px solid #DDD !important;
        border-radius: 8px !important;
        font-family: 'DM Sans', sans-serif !important;
    }

    textarea:focus, input:focus {
        border-color: var(--sienna) !important;
        box-shadow: 0 0 0 2px rgba(184, 92, 56, 0.1) !important;
    }

    /* Container styling */
    .stContainer {
        background-color: transparent !important;
        border: none !important;
    }

    .stCaption, .stLiteCaption {
        color: var(--gray) !important;
        font-size: 0.85rem !important;
    }

    /* Chat bubbles */
    div[data-testid="stChatMessage-user"] {
        background-color: var(--charcoal);
    }
    div[data-testid="stChatMessage-user"] p,
    div[data-testid="stChatMessage-user"] span {
        color: var(--cream) !important;
    }

    div[data-testid="stChatMessage-assistant"] {
        background-color: #FFFFFF;
        border: 1px solid #E8E4DE;
    }

    /* Buttons */
    .stButton > button {
        background-color: var(--sienna) !important;
        color: #1A1A1A !important;
        border: none !important;
        border-radius: 8px !important;
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 500 !important;
        padding: 0.75rem 1.5rem !important;
        transition: all 0.3s ease !important;
    }

    .stButton > button:hover {
        background-color: var(--sienna-dark) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(184, 92, 56, 0.3) !important;
    }

    /* Divider */
    .stDivider {
        border-color: #DDD !important;
    }

    /* Links */
    a, a:hover {
        color: var(--sienna) !important;
    }

    /* Custom scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
    }
    ::-webkit-scrollbar-track {
        background: var(--cream-dark);
    }
    ::-webkit-scrollbar-thumb {
        background: var(--gray-light);
        border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: var(--gray);
    }

    /* Food emoji spinner */
    [data-testid="stSpinner"] svg {
        display: none !important;
    }
    [data-testid="stSpinner"] > div {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    [data-testid="stSpinner"] > div::before {
        content: "🍜";
        font-size: 1.4rem;
        animation: cycleFood 1.2s steps(1) infinite;
    }
    @keyframes cycleFood {
        0%   { content: "🍜"; }
        16%  { content: "🍕"; }
        32%  { content: "🍣"; }
        48%  { content: "🌮"; }
        64%  { content: "🍔"; }
        80%  { content: "🥗"; }
    }
</style>
""", unsafe_allow_html=True)



def md_to_html(text: str) -> str:
    """Convert basic markdown to HTML for safe rendering in custom divs."""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = text.replace('\n', '<br>')
    return text


def get_search_service() -> SearchService:
    """Get or create search service."""
    if "search_service" not in st.session_state:
        st.session_state.search_service = SearchService()
    return st.session_state.search_service


def get_query_parser() -> QueryParser:
    """Get or create query parser."""
    if "query_parser" not in st.session_state:
        st.session_state.query_parser = QueryParser()
    return st.session_state.query_parser


def _render_message(role: str, content: str) -> None:
    label = "You" if role == "user" else "Assistant"
    st.markdown(f"""
<div style="background: #FFFFFF; border: 1px solid #E8E4DE; border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: 0.75rem;">
    <strong style="color: #666; font-size: 0.8rem; display: block; margin-bottom: 0.5rem;">{label}</strong>
    <div style="margin: 0; font-family: 'DM Sans', sans-serif; color: #1A1A1A; line-height: 1.5;">{md_to_html(content)}</div>
</div>
""", unsafe_allow_html=True)


def main():
    # Editorial header
    st.markdown("""
    <div class="header-section">
        <div class="header-logo">Where Should You Eat With Erin?</div>
        <div class="header-tagline">Your curated restaurant guide</div>
    </div>

    <style>
    .header-section {
        text-align: center;
        padding: 2rem 0 2.5rem 0;
        border-bottom: 1px solid #E8E4DE;
        margin-bottom: 2rem;
    }
    .header-logo {
        font-family: 'Playfair Display', Georgia, serif;
        font-size: 3rem;
        font-weight: 500;
        color: #1A1A1A;
        letter-spacing: -0.03em;
        margin-bottom: 0.5rem;
    }
    .header-tagline {
        font-family: 'DM Sans', sans-serif;
        font-size: 1rem;
        color: #666;
        letter-spacing: 0.1em;
        text-transform: uppercase;
    }
    </style>
    """, unsafe_allow_html=True)

    # Editorial intro card
    st.markdown("""
    <div class="intro-container">
        <div class="intro-card">
            <div class="intro-title">Erin's Recommendations</div>
            <div class="intro-body">
                Explore restaurants from Erin's saved Google Maps list. Ask me naturally and I'll help you discover the perfect spot.
            </div>
        </div>
        <div class="intro-card accent">
            <div class="intro-title">Try asking for</div>
            <div class="example-list">
                <div class="example-item">Korean in Brooklyn</div>
                <div class="example-item">Italian for date night</div>
                <div class="example-item">Casual spots in NYC</div>
                <div class="example-item">Mexican under $30</div>
            </div>
        </div>
    </div>

    <style>
    .intro-container {
        display: grid;
        grid-template-columns: 2fr 1fr;
        gap: 1.5rem;
        margin-bottom: 2.5rem;
    }
    .intro-card {
        background: #FFFFFF;
        border: 1px solid #E8E4DE;
        border-radius: 12px;
        padding: 1.75rem;
    }
    .intro-card.accent {
        background: #EDE8E0;
        border-color: #DDD;
    }
    .intro-title {
        font-family: 'Playfair Display', Georgia, serif;
        font-size: 1.25rem;
        font-weight: 500;
        color: #1A1A1A;
        margin-bottom: 0.75rem;
    }
    .intro-card.accent .intro-title {
        color: #1A1A1A;
    }
    .intro-body {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.95rem;
        color: #666;
        line-height: 1.6;
    }
    .example-list {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
    }
    .example-item {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.9rem;
        color: #999;
        padding-left: 1rem;
        border-left: 2px solid #333;
    }
    .intro-card.accent .example-item {
        color: #666666;
        border-left-color: #B85C38;
    }
    @media (max-width: 768px) {
        .intro-container {
            grid-template-columns: 1fr;
        }
    }
    </style>
    """, unsafe_allow_html=True)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        _render_message(message["role"], message["content"])

    if not st.session_state.messages:
        st.markdown("""
<div style="background: #FFFFFF; border: 1px solid #E8E4DE; border-radius: 12px; padding: 1rem 1.5rem; margin-bottom: 1rem;">
    <p style="margin: 0; font-family: 'DM Sans', sans-serif; color: #1A1A1A;">Hi! I'm your restaurant recommendation assistant. Where are you craving to eat today?</p>
</div>
""", unsafe_allow_html=True)

    if prompt := st.chat_input("What are you craving?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        _render_message("user", prompt)

        with st.spinner("Searching for the perfect spot..."):
            try:
                search_service = get_search_service()
                parser = get_query_parser()

                match = re.search(r'\b(\d+)\s*(?:results?|options?|suggestions?)?\b', prompt.lower())
                num_results = int(match.group(1)) if match else 3

                restaurant_match = re.search(r'(?:about|info|details|more)\s+(?:the\s+)?(.+?)(?:\?|$)', prompt, re.IGNORECASE)
                is_specific_query = bool(re.search(r'(?:tell me more|more details|about|info for)', prompt, re.IGNORECASE))

                if is_specific_query and restaurant_match:
                    restaurant_name = restaurant_match.group(1).strip()
                    results = asyncio.run(search_service.search_by_name(restaurant_name))

                    if results:
                        restaurant = results[0]
                        response = f"**{restaurant.get('name', 'Unknown')}**\n\n"
                        response += f"**Rating:** {restaurant.get('rating', 'N/A')}/5\n"
                        response += f"**Address:** {restaurant.get('address', 'Unknown')}\n"
                        response += f"**Cuisine:** {', '.join(restaurant.get('cuisine_tags') or ['Unknown'])}\n"
                        if restaurant.get('vibe_tags'):
                            response += f"**Vibes:** {', '.join(restaurant.get('vibe_tags'))}\n"
                        if restaurant.get('notes'):
                            response += f"\n**Notes:** {restaurant.get('notes')}\n"
                        price = restaurant.get('price_level')
                        if price:
                            response += f"**Price:** {'$' * price}\n"
                    else:
                        response = f"I couldn't find a restaurant called '{restaurant_name}'. Try asking differently or check the spelling!"

                else:
                    async def _search():
                        filters = await parser.parse(prompt)
                        return await search_service.hybrid_search(
                            query=prompt,
                            filters=filters,
                            limit=num_results,
                        )
                    results = asyncio.run(_search())

                    if results:
                        response = f"I found **{len(results)}** options for you:\n\n"
                        for i, restaurant in enumerate(results, 1):
                            response += f"{i}. **{restaurant.get('name', 'Unknown')}** "
                            response += f"({restaurant.get('rating', 'N/A')})\n"
                            cuisines = restaurant.get('cuisine_tags') or []
                            if cuisines:
                                response += f"   {', '.join(cuisines)}\n"
                            notes = (restaurant.get('notes') or '')[:80]
                            if notes:
                                response += f"   {notes}...\n"
                            response += "\n"
                        response += "*Want more details about any of these?*"
                    else:
                        response = "I didn't find any restaurants matching your criteria. Try adjusting your filters or asking differently!"

            except Exception as e:
                response = f"Sorry, I ran into an error: {str(e)}. Please try again!"

        _render_message("ai", response)
        st.session_state.messages.append({"role": "ai", "content": response})

    # Editorial footer
    st.markdown("""
    <div class="footer-section">
        <span class="footer-count">""" + str(get_restaurant_count()) + """ places in your collection</span>
    </div>

    <style>
    .footer-section {
        text-align: center;
        padding: 2rem 0 1rem 0;
        margin-top: 2rem;
        border-top: 1px solid #E8E4DE;
    }
    .footer-count {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.85rem;
        color: #999;
        letter-spacing: 0.05em;
    }
    </style>
    """, unsafe_allow_html=True)


def get_restaurant_count() -> int:
    if "restaurant_count" not in st.session_state:
        try:
            repo = RestaurantRepository()
            st.session_state.restaurant_count = repo.count()
        except Exception:
            st.session_state.restaurant_count = 0
    return st.session_state.restaurant_count


if __name__ == "__main__":
    main()
