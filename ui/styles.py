"""
Design System and Custom CSS injection for LocalScribe UI.
"""

import streamlit as st

CUSTOM_CSS = """
<style>
    /* Import Inter depuis Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    /* Appliquer Inter globalement */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Bouton principal — style moderne */
    .stButton > button {
        background: linear-gradient(135deg, #6366f1 0%, #818cf8 100%);
        border: none;
        border-radius: 10px;
        padding: 0.6rem 2rem;
        font-weight: 600;
        transition: all 0.2s ease;
        box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 16px rgba(99, 102, 241, 0.4);
    }
    
    /* Progress bar — accent indigo */
    .stProgress > div > div {
        background: linear-gradient(90deg, #6366f1, #818cf8);
        border-radius: 8px;
    }
    
    /* Sidebar — bordure subtile */
    section[data-testid="stSidebar"] {
        border-right: 1px solid rgba(99, 102, 241, 0.15);
    }
    
    /* Cards / Containers */
    .stExpander, [data-testid="stStatusWidget"] {
        border: 1px solid rgba(248, 250, 252, 0.08);
        border-radius: 12px;
    }
    
    /* Masquer le menu hamburger et le footer Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
"""

def inject_custom_css():
    """Injecte le CSS global dans l'application Streamlit."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
