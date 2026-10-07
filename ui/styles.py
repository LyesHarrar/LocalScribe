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
    /* 1. Typographie Inter et Material Symbols importées depuis Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,1,0');
    
    html, body, 
    .stMarkdown, .stText, h1, h2, h3, h4, h5, h6, 
    p, label, input, textarea, select {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }
    
    .material-symbols-rounded {
        font-family: 'Material Symbols Rounded' !important;
        font-weight: normal;
        font-style: normal;
        font-size: 24px;
        line-height: 1;
        letter-spacing: normal;
        text-transform: none;
        display: inline-block;
        white-space: nowrap;
        word-wrap: normal;
        direction: ltr;
        font-feature-settings: 'liga';
        -moz-font-feature-settings: 'liga';
        -moz-osx-font-smoothing: grayscale;
    }
    
    /* 2. Fond d'écran global — Zinc-950 (Obsidienne) */
    .stApp {
        background-color: #09090b !important;
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
    
    /* 4. Barre latérale (Sidebar) - Zinc-950/900 */
    section[data-testid="stSidebar"] {
        background-color: #09090b !important;
        border-right: 1px solid #27272a !important;
    }
    section[data-testid="stSidebar"] hr {
        border-color: #27272a !important;
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

    /* 6. Bouton Secondaire — Contours discrets & fond nuit (Zinc-900) */
    .stButton > button[kind="secondary"] {
        background-color: #18181b !important;
        color: #e2e8f0 !important;
        border: 1px solid #27272a !important;
        border-radius: 10px !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background-color: #27272a !important;
        border-color: #3f3f46 !important;
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
        background: #18181b !important;
        border: 1px solid #27272a !important;
        border-radius: 12px !important;
        padding: 6px 10px !important;
        gap: 12px !important;
    }
    div[data-testid="stRadio"] label {
        color: #a1a1aa !important;
        font-weight: 500 !important;
        cursor: pointer !important;
    }
    div[data-testid="stRadio"] label:hover {
        color: #ffffff !important;
    }

    /* 9. Champs de saisie (Text Input & Selectbox) */
    div[data-baseweb="input"], div[data-baseweb="select"] > div {
        background-color: #18181b !important;
        border: 1px solid #27272a !important;
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
        background: #09090b !important;
        border: 1.5px dashed #3f3f46 !important;
        border-radius: 14px !important;
        padding: 1.5rem !important;
        transition: all 0.2s ease !important;
    }
    [data-testid="stFileUploader"]:hover {
        border-color: #2e74fd !important;
        background: rgba(46, 116, 253, 0.05) !important;
    }

    /* 11. Barre de Progression Néon Azur */
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #1d4ed8 0%, #2e74fd 60%, #38bdf8 100%) !important;
        border-radius: 9999px !important;
        box-shadow: 0 0 14px rgba(46, 116, 253, 0.5) !important;
    }
    .stProgress > div > div {
        background-color: #18181b !important;
        border: 1px solid #27272a !important;
        border-radius: 9999px !important;
        height: 10px !important;
    }

    /* 12. Alertes & Bannières d'informations */
    .stAlert {
        background-color: rgba(24, 24, 27, 0.8) !important;
        backdrop-filter: blur(8px) !important;
        border: 1px solid #27272a !important;
        border-radius: 12px !important;
        color: #e2e8f0 !important;
    }

    /* 13. Expanders & Containers */
    .stExpander {
        background-color: #18181b !important;
        border: 1px solid #27272a !important;
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

    /* 15. Masquer UNIQUEMENT le menu burger et le bouton Deploy de Streamlit */
    #MainMenu { display: none !important; }
    footer { display: none !important; }
    [data-testid="stAppDeployButton"] { display: none !important; }
    [data-testid="stMainMenu"] { display: none !important; }

    /* Rendre le Header transparent mais ACTIF pour les boutons de navigation */
    header[data-testid="stHeader"], header {
        background: transparent !important;
        visibility: visible !important;
        display: flex !important;
        height: 3.5rem !important;
        pointer-events: auto !important;
    }

    /* Bouton d'ouverture de la barre latérale quand elle est fermée */
    [data-testid="stExpandSidebarButton"],
    [data-testid="collapsedControl"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        position: fixed !important;
        top: 0.75rem !important;
        left: 0.75rem !important;
        z-index: 9999999 !important;
        background-color: #18181b !important;
        border: 1px solid #3f3f46 !important;
        border-radius: 8px !important;
        padding: 4px !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.5) !important;
        transition: all 0.2s ease !important;
        cursor: pointer !important;
    }
    [data-testid="stExpandSidebarButton"]:hover,
    [data-testid="collapsedControl"]:hover {
        background-color: #27272a !important;
        border-color: #38bdf8 !important;
        transform: scale(1.05) !important;
    }
    [data-testid="stExpandSidebarButton"] button {
        visibility: visible !important;
        opacity: 1 !important;
    }
    [data-testid="stExpandSidebarButton"] span,
    [data-testid="collapsedControl"] span {
        color: #f8fafc !important;
    }

    /* Bouton de fermeture de la barre latérale quand elle est ouverte */
    [data-testid="stSidebarCollapseButton"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        background-color: #18181b !important;
        border: 1px solid #27272a !important;
        border-radius: 8px !important;
        padding: 2px !important;
        transition: all 0.2s ease !important;
        cursor: pointer !important;
    }
    [data-testid="stSidebarCollapseButton"]:hover {
        background-color: #27272a !important;
        border-color: #38bdf8 !important;
    }
    [data-testid="stSidebarCollapseButton"] button {
        visibility: visible !important;
        opacity: 1 !important;
    }

    /* 16. Sélecteur de Mode Segmenté moderne (Linear / iOS Style) */
    div[data-testid="stButtonGroup"] > div,
    div[data-testid="stSegmentedControl"] > div,
    div[data-testid="stPills"] > div {
        background: #18181b !important;
        border: 1px solid #27272a !important;
        border-radius: 12px !important;
        padding: 4px !important;
        gap: 6px !important;
        display: inline-flex !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2) !important;
    }
    div[data-testid="stButtonGroup"] button,
    div[data-testid="stSegmentedControl"] button,
    div[data-testid="stPills"] button {
        border-radius: 8px !important;
        font-weight: 500 !important;
        font-size: 0.9rem !important;
        color: #94a3b8 !important;
        background-color: transparent !important;
        border: 1px solid transparent !important;
        transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
        padding: 0.55rem 1.25rem !important;
        cursor: pointer !important;
    }
    div[data-testid="stButtonGroup"] button:hover,
    div[data-testid="stSegmentedControl"] button:hover,
    div[data-testid="stPills"] button:hover {
        color: #f8fafc !important;
        background-color: rgba(255, 255, 255, 0.06) !important;
    }
    div[data-testid="stButtonGroup"] button[aria-checked="true"],
    div[data-testid="stButtonGroup"] button[data-selected="true"],
    div[data-testid="stSegmentedControl"] button[aria-checked="true"],
    div[data-testid="stPills"] button[aria-checked="true"] {
        background: linear-gradient(135deg, #1d4ed8 0%, #2e74fd 100%) !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        box-shadow: 0 4px 14px rgba(46, 116, 253, 0.45) !important;
    }
    div[data-testid="stButtonGroup"] button[aria-checked="true"] p,
    div[data-testid="stButtonGroup"] button[data-selected="true"] p {
        color: #ffffff !important;
        font-weight: 600 !important;
    }
    div[data-testid="stButtonGroup"] button[aria-checked="true"] span,
    div[data-testid="stButtonGroup"] button[data-selected="true"] span {
        color: #ffffff !important;
    }
</style>
"""

def inject_custom_css():
    """Injecte le système de design moderne dans Streamlit."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
