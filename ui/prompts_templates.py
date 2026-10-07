import streamlit as st
import pyperclip

def render_llm_templates():
    st.markdown("### 🤖 Templates LLM (Post-Traitement)")
    st.markdown("Copiez l'un de ces prompts pour l'utiliser avec ChatGPT, Claude ou un LLM local, avec votre transcription.")
    
    templates = {
        "📝 Résumé Structuré": "Voici la transcription d'un audio/vidéo. Peux-tu m'en faire un résumé structuré avec les points clés (bullet points), les décisions prises et les actions à réaliser ?",
        "🎬 Chapitrage YouTube": "Voici une transcription. Peux-tu me générer des chapitres horodatés pertinents pour YouTube (format 00:00 - Titre du chapitre) ?",
        "📰 Article de Blog": "Réécris cette transcription sous la forme d'un article de blog engageant et bien structuré (titre, sous-titres H2, paragraphes clairs), tout en conservant le ton d'origine.",
        "✍️ Correction et Syntaxe": "Voici une transcription brute. Peux-tu la corriger (fautes d'orthographe, de grammaire, hésitations du type 'euh', répétitions) sans modifier le sens original ?"
    }
    
    for title, prompt in templates.items():
        with st.expander(title):
            st.code(prompt, language="text")
            if st.button(f"📋 Copier le prompt : {title}", key=title):
                try:
                    pyperclip.copy(prompt)
                    st.success("Copié dans le presse-papier !")
                except Exception as e:
                    st.error("Erreur de copie. Veuillez le copier manuellement.")
