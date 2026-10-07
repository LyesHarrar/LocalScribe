"""
Design System et CSS personnalisé pour l'UI LocalScribe (Thème Shadcn Dark).
"""

import streamlit as st

CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Style global sombre épuré */
    .stApp {
        background-color: #090a0f;
        color: #f8fafc;
    }
    
    /* Header branding */
    .brand-header {
        display: flex;
        align-items: center;
        gap: 1.25rem;
        margin-bottom: 1.5rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    .brand-header img {
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(99, 102, 241, 0.25);
    }
    
    /* Bouton principal Shadcn-like */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%) !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 8px !important;
        padding: 0.65rem 1.75rem !important;
        font-weight: 600 !important;
        letter-spacing: -0.01em;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 2px 10px rgba(79, 70, 229, 0.3) !important;
    }
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 18px rgba(99, 102, 241, 0.45) !important;
    }
    
    /* Bouton secondaire */
    .stButton > button[kind="secondary"] {
        background-color: #181926 !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 8px !important;
        color: #e2e8f0 !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background-color: #232538 !important;
        border-color: rgba(255, 255, 255, 0.25) !important;
    }
    
    /* Zone de drop de fichier */
    [data-testid="stFileUploader"] {
        background: #0f111a;
        border: 1px dashed rgba(99, 102, 241, 0.35);
        border-radius: 12px;
        padding: 1rem;
        transition: border-color 0.2s ease;
    }
    [data-testid="stFileUploader"]:hover {
        border-color: #6366f1;
    }
    
    /* Barre de progression */
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #4f46e5, #818cf8) !important;
        border-radius: 9999px;
    }
    .stProgress > div > div {
        background-color: #1e1f2e !important;
        border-radius: 9999px;
    }
    
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #0c0d14;
        border-right: 1px solid rgba(255, 255, 255, 0.08);
    }
    
    /* Containers & Cards */
    .glass-card {
        background: rgba(24, 25, 38, 0.6);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1rem;
    }
    
    /* Masquer le menu hamburger et header par défaut */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
"""

def inject_custom_css():
    """Injecte le CSS global dans l'application Streamlit."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
