"""
Module des templates de prompts LLM pour exploitation post-transcription.
"""

import streamlit as st
import streamlit_shadcn_ui as ui
import pyperclip

TEMPLATES = [
    {
        "id": "summary",
        "title": "📝 Synthèse & Décisions",
        "tag": "Productivité",
        "description": "Extrait les points clés, décisions actées et to-do list concrète.",
        "prompt": (
            "Tu es un assistant de synthèse de haut niveau. À partir de la transcription ci-dessous, "
            "rédige un compte-rendu clair et percutant structuré comme suit :\n"
            "1. 🎯 Objectif principal et contexte\n"
            "2. 💡 Points clés et thématiques abordées (bullet points hiérarchisés)\n"
            "3. ⚖️ Décisions actées\n"
            "4. 📌 Plan d'action (qui fait quoi pour quand)\n\n"
            "Voici la transcription :\n\n"
        )
    },
    {
        "id": "youtube",
        "title": "🎬 Chapitrage & Timestamps",
        "tag": "Vidéo / Podcast",
        "description": "Crée des chapitres au format YouTube avec titres attractifs.",
        "prompt": (
            "À partir de la transcription fournie, génère un chapitrage complet et optimisé "
            "pour la description d'une vidéo YouTube ou d'un podcast.\n"
            "Format attendu :\n"
            "00:00 - Introduction & Accueil\n"
            "01:30 - [Titre accrocheur du sujet 1]\n"
            "...\n\n"
            "Ajoute également une courte description de 3 lignes résumant l'intérêt de la vidéo.\n\n"
            "Voici la transcription :\n\n"
        )
    },
    {
        "id": "article",
        "title": "📰 Article de Blog / LinkedIn",
        "tag": "Rédaction",
        "description": "Transforme la transcription orale en un article fluide et engageant.",
        "prompt": (
            "Rédige un article professionnel et captivant à partir de cette transcription.\n"
            "- Titre accrocheur\n"
            "- Introduction posant la problématique\n"
            "- Corps de texte structuré avec sous-titres (H2, H3)\n"
            "- Élimine toutes les tournures orales et hésitations\n"
            "- Conclusion percutante avec un call-to-action ou une question ouverte\n\n"
            "Voici la transcription :\n\n"
        )
    },
    {
        "id": "cleanup",
        "title": "✍️ Nettoyage & Correction Orthographique",
        "tag": "Édition",
        "description": "Corrige les fautes, supprime les tics de langage et fluidifie le style.",
        "prompt": (
            "Voici une transcription brute issue d'un enregistrement audio.\n"
            "Effectue un nettoyage minutieux :\n"
            "- Corrige les fautes d'orthographe, de grammaire et de ponctuation\n"
            "- Supprime les tics verbaux ('euh', 'en fait', 'du coup', répétitions inutiles)\n"
            "- Garde intacts le vocabulaire technique et les propos d'origine\n"
            "- Améliore la ponctuation pour rendre la lecture agréable\n\n"
            "Voici la transcription :\n\n"
        )
    }
]

def render_llm_templates(transcription_text: str = ""):
    st.markdown("### 🤖 Exploitation avec un LLM (ChatGPT, Claude, Ollama...)")
    st.caption("Sélectionnez un template pour formater un prompt prêt à coller dans votre modèle d'IA favori.")
    
    for tpl in TEMPLATES:
        with st.container():
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{tpl['title']}**")
                st.caption(tpl['description'])
            with col2:
                ui.badge(tpl['tag'], variant="secondary")
                
            full_prompt = tpl['prompt'] + transcription_text if transcription_text else tpl['prompt']
            
            with st.expander("👁️ Voir le prompt complet"):
                st.code(full_prompt, language="text")
                if st.button(f"📋 Copier le prompt", key=f"copy_{tpl['id']}"):
                    try:
                        pyperclip.copy(full_prompt)
                        st.success("Copié dans le presse-papier !")
                    except Exception:
                        st.info("Sélectionnez et copiez le texte ci-dessus.")
            st.markdown("<hr style='margin: 0.75rem 0; opacity: 0.1;'>", unsafe_allow_html=True)
