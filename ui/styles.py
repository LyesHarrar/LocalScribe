"""
Design System de pointe pour LocalScribe.
Inspiré de Linear, Framer et Shadcn UI :
- Typographie Inter haute lisibilité
- Palette assortie au logo (Noir Obsidienne #05070e, Bleu Électrique #2e74fd, Cyan #38bdf8)
- Bordures douces, effets de verre (glassmorphism), micro-interactions
"""

import streamlit as st

CUSTOM_CSS = """
<style>
    /* 1. Typographie Inter importée depuis Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    
    *, *::before, *::after, 
    html, body, [class*="css"], 
    .stMarkdown, .stText, h1, h2, h3, h4, h5, h6, 
    p, span, label, input, button, textarea, select {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }
    
    /* 2. Fond d'écran global — Noir Profond / Obsidienne */
    .stApp {
        background-color: #05070e !important;
        color: #f8fafc !important;
    }
    
    /* 3. Titres avec dégradé subtil argenté / azur */
    h1 {
        font-weight: 800 !important;
        letter-spacing: -0.035em !important;
        background: linear-gradient(135deg, #ffffff 40%, #93c5fd 100%) !important;
        -webkit-background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
        margin-bottom: 0.2rem !important;
    }
    h2, h3 {
        font-weight: 700 !important;
        letter-spacing: -0.025em !important;
        color: #f1f5f9 !important;
    }
    h4, h5 {
        font-weight: 600 !important;
        letter-spacing: -0.015em !important;
        color: #e2e8f0 !important;
    }
    
    /* 4. Barre latérale (Sidebar) élégante */
    section[data-testid="stSidebar"] {
        background-color: #070a14 !important;
        border-right: 1px solid rgba(46, 116, 253, 0.12) !important;
    }
    section[data-testid="stSidebar"] hr {
        border-color: rgba(46, 116, 253, 0.15) !important;
    }

    /* 5. Bouton Principal — Gradient Bleu Électrique Logo */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1d4ed8 0%, #2e74fd 60%, #38bdf8 100%) !important;
        color: #ffffff !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        border-radius: 10px !important;
        padding: 0.7rem 1.8rem !important;
        font-size: 0.95rem !important;
        font-weight: 600 !important;
        letter-spacing: -0.01em !important;
        transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1) !important;
        box-shadow: 0 4px 16px rgba(46, 116, 253, 0.35) !important;
    }
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 26px rgba(46, 116, 253, 0.55) !important;
        filter: brightness(1.08) !important;
    }
    .stButton > button[kind="primary"]:active {
        transform: translateY(0px) !important;
    }

    /* 6. Bouton Secondaire — Contours discrets & fond nuit */
    .stButton > button[kind="secondary"] {
        background-color: #0b1020 !important;
        color: #cbd5e1 !important;
        border: 1px solid rgba(46, 116, 253, 0.2) !important;
        border-radius: 10px !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background-color: #121830 !important;
        border-color: rgba(46, 116, 253, 0.45) !important;
        color: #ffffff !important;
    }

    /* 7. Bouton Téléchargement */
    .stDownloadButton > button {
        background: linear-gradient(135deg, #0e162e 0%, #172346 100%) !important;
        color: #60a5fa !important;
        border: 1px solid rgba(46, 116, 253, 0.3) !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3) !important;
        transition: all 0.2s ease !important;
    }
    .stDownloadButton > button:hover {
        background: linear-gradient(135deg, #172346 0%, #203162 100%) !important;
        border-color: #38bdf8 !important;
        color: #ffffff !important;
        transform: translateY(-1px) !important;
    }

    /* 8. Sélecteur de Mode (Radio) transformé en Segmented Pills moderne */
    div[data-testid="stRadio"] > div {
        background: #080c18 !important;
        border: 1px solid rgba(46, 116, 253, 0.15) !important;
        border-radius: 12px !important;
        padding: 6px 10px !important;
        gap: 12px !important;
    }
    div[data-testid="stRadio"] label {
        color: #cbd5e1 !important;
        font-weight: 500 !important;
        cursor: pointer !important;
    }
    div[data-testid="stRadio"] label:hover {
        color: #ffffff !important;
    }

    /* 9. Champs de saisie (Text Input & Selectbox) */
    div[data-baseweb="input"], div[data-baseweb="select"] > div {
        background-color: #090e1c !important;
        border: 1px solid rgba(46, 116, 253, 0.22) !important;
        border-radius: 10px !important;
        color: #f8fafc !important;
        transition: all 0.2s ease !important;
    }
    div[data-baseweb="input"]:focus-within, div[data-baseweb="select"] > div:focus-within {
        border-color: #2e74fd !important;
        box-shadow: 0 0 0 3px rgba(46, 116, 253, 0.2) !important;
    }

    /* 10. Zone de téléversement (File Uploader) */
    [data-testid="stFileUploader"] {
        background: #070b16 !important;
        border: 1.5px dashed rgba(46, 116, 253, 0.3) !important;
        border-radius: 14px !important;
        padding: 1.5rem !important;
        transition: all 0.2s ease !important;
    }
    [data-testid="stFileUploader"]:hover {
        border-color: #2e74fd !important;
        background: #0a1022 !important;
    }

    /* 11. Barre de Progression Néon Azur */
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #1d4ed8 0%, #2e74fd 60%, #38bdf8 100%) !important;
        border-radius: 9999px !important;
        box-shadow: 0 0 14px rgba(46, 116, 253, 0.5) !important;
    }
    .stProgress > div > div {
        background-color: #0b1122 !important;
        border-radius: 9999px !important;
        height: 10px !important;
    }

    /* 12. Alertes & Bannières d'informations */
    .stAlert {
        background-color: rgba(14, 22, 46, 0.7) !important;
        backdrop-filter: blur(8px) !important;
        border: 1px solid rgba(46, 116, 253, 0.25) !important;
        border-radius: 12px !important;
        color: #e2e8f0 !important;
    }

    /* 13. Expanders & Containers */
    .stExpander {
        background-color: #090e1c !important;
        border: 1px solid rgba(46, 116, 253, 0.15) !important;
        border-radius: 12px !important;
    }

    /* 14. Onglets (Tabs) style Linear / Shadcn */
    div[data-baseweb="tab-list"] {
        background-color: transparent !important;
        border-bottom: 1px solid rgba(46, 116, 253, 0.15) !important;
        gap: 8px !important;
        margin-bottom: 1.5rem !important;
    }
    button[data-baseweb="tab"] {
        background-color: transparent !important;
        color: #94a3b8 !important;
        font-weight: 500 !important;
        font-size: 0.92rem !important;
        border-radius: 8px 8px 0 0 !important;
        padding: 0.6rem 1.2rem !important;
        border: none !important;
        transition: all 0.2s ease !important;
    }
    button[data-baseweb="tab"]:hover {
        color: #f8fafc !important;
        background-color: rgba(46, 116, 253, 0.06) !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #ffffff !important;
        font-weight: 600 !important;
        border-bottom: 2px solid #2e74fd !important;
    }

    /* 15. Masquer les éléments résiduels Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
"""

def inject_custom_css():
    """Injecte le système de design moderne dans Streamlit."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
