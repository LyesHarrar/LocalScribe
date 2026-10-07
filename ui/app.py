"""
Point d'entrée principal de l'UI Streamlit de LocalScribe.
"""

import streamlit as st
from styles import inject_custom_css

def main():
    # 1. Configuration de la page
    st.set_page_config(
        page_title="LocalScribe",
        page_icon="🎙️",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # 2. Injection du design system
    inject_custom_css()

    # 3. Interface de base (Scaffolding)
    st.title("LocalScribe")
    st.markdown("Bienvenue sur l'application de transcription 100% locale.")
    
    st.sidebar.header("Paramètres")
    st.sidebar.info("La détection matérielle arrivera à la Phase 1.")

if __name__ == "__main__":
    main()
