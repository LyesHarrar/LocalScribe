"""
Module des templates de prompts LLM pour exploitation post-transcription.
Harmonisé avec le thème Bleu Électrique & Obsidienne.
"""

import streamlit as st
import pyperclip

TEMPLATES = [
    {
        "id": "summary",
        "title": "📝 Synthèse & Décisions Actionnables",
        "tag": "Productivité",
        "tag_color": "#2e74fd",
        "description": "Extrait les points clés, décisions actées et plan d'action hiérarchisé.",
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
        "title": "🎬 Chapitrage Vidéo & Timestamps",
        "tag": "YouTube / Podcast",
        "tag_color": "#38bdf8",
        "description": "Crée des chapitres cliquables avec titres optimisés et description.",
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
        "title": "📰 Article de Blog / Synthèse LinkedIn",
        "tag": "Création de Contenu",
        "tag_color": "#818cf8",
        "description": "Transforme la parole orale en un écrit captivant et éditorialisé.",
        "prompt": (
            "Rédige un article professionnel et captivant à partir de cette transcription.\n"
            "- Titre percutant\n"
            "- Introduction posant le problème\n"
            "- Corps de texte fluide avec sous-titres (H2, H3)\n"
            "- Élimine les répétitions et hésitations orales\n"
            "- Conclusion inspirante avec question ouverte ou appel à l'action\n\n"
            "Voici la transcription :\n\n"
        )
    },
    {
        "id": "cleanup",
        "title": "✍️ Nettoyage Stylistique & Orthographe",
        "tag": "Relecture",
        "tag_color": "#34d399",
        "description": "Supprime les tics verbaux, hésitations et perfectionne la ponctuation.",
        "prompt": (
            "Voici une transcription brute issue d'un enregistrement audio.\n"
            "Effectue un nettoyage minutieux :\n"
            "- Corrige les fautes d'orthographe, de grammaire et de ponctuation\n"
            "- Supprime les tics verbaux ('euh', 'en fait', 'du coup', répétitions inutiles)\n"
            "- Garde intacts le vocabulaire technique et le fond des propos\n"
            "- Rend la lecture fluide et naturelle\n\n"
            "Voici la transcription :\n\n"
        )
    }
]

def render_llm_templates(transcription_text: str = ""):
    st.markdown("### 🤖 Exploitation avec un LLM (ChatGPT, Claude, Ollama...)")
    st.caption("Sélectionnez un modèle de prompt pour copier en 1 clic l'instruction pré-remplie avec votre texte.")
    
    for tpl in TEMPLATES:
        with st.container():
            col1, col2 = st.columns([5, 1])
            with col1:
                st.markdown(f"**{tpl['title']}**")
                st.caption(tpl['description'])
            with col2:
                st.markdown(
                    f"<span style='background: rgba(46,116,253,0.12); color: {tpl['tag_color']}; "
                    f"border: 1px solid rgba(46,116,253,0.3); padding: 3px 10px; border-radius: 9999px; "
                    f"font-size: 0.75rem; font-weight: 600; display: inline-block; margin-top: 6px;'>"
                    f"{tpl['tag']}</span>", 
                    unsafe_allow_html=True
                )
                
            full_prompt = tpl['prompt'] + transcription_text if transcription_text else tpl['prompt']
            
            with st.expander("👁️ Consulter et copier le prompt"):
                st.code(full_prompt, language="text")
                if st.button(f"📋 Copier le prompt dans le presse-papier", key=f"copy_{tpl['id']}"):
                    try:
                        pyperclip.copy(full_prompt)
                        st.success("Copié avec succès !")
                    except Exception:
                        st.info("Sélectionnez et copiez le texte ci-dessus.")
                        
            st.markdown("<hr style='margin: 0.8rem 0; border: none; border-top: 1px solid rgba(46, 116, 253, 0.1);'>", unsafe_allow_html=True)
