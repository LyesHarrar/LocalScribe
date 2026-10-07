import os
import time
import queue
import threading
from pathlib import Path
import tempfile

import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx

# Pour pouvoir importer les modules core quand on lance depuis le root
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.styles import inject_custom_css
from ui.prompts_templates import render_llm_templates
from core.hardware_profiler import detect_hardware
from core.transcription_engine import transcribe_file_threaded

def render_sidebar():
    st.sidebar.header("⚙️ Matériel & Modèle")
    
    # Exécution unique du profiler
    if "hw_profile" not in st.session_state:
        st.session_state.hw_profile = detect_hardware()
        
    profile = st.session_state.hw_profile
    
    # Affichage du profil détecté
    st.sidebar.markdown(f"**Appareil détecté :** `{profile.device.upper()}`")
    if profile.vram_gb:
        st.sidebar.markdown(f"**VRAM :** `{profile.vram_gb:.1f} GB`")
    st.sidebar.markdown(f"**Précision calcul :** `{profile.compute_type}`")
    
    for warning in profile.warnings:
        st.sidebar.warning(warning)
        
    st.sidebar.divider()
    
    # Choix du modèle
    model_options = ["tiny", "base", "small", "medium", "large-v3"]
    default_index = model_options.index(profile.recommended_model) if profile.recommended_model in model_options else 1
    
    selected_model = st.sidebar.selectbox(
        "Taille du modèle Whisper",
        options=model_options,
        index=default_index,
        help="Plus le modèle est grand, meilleure est la qualité, mais plus il est lent et nécessite de RAM/VRAM."
    )
    
    st.session_state.selected_model = selected_model

def save_uploaded_file(uploaded_file) -> Path:
    temp_dir = Path(tempfile.gettempdir()) / "LocalScribe"
    temp_dir.mkdir(parents=True, exist_ok=True)
    file_path = temp_dir / uploaded_file.name
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def main():
    st.set_page_config(
        page_title="LocalScribe",
        page_icon="🎙️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    inject_custom_css()

    st.title("LocalScribe 🎙️")
    st.markdown("Transcription audio/vidéo 100% locale, rapide et sécurisée.")
    
    render_sidebar()
    
    # Upload zone
    uploaded_file = st.file_uploader(
        "Glissez un fichier audio ou vidéo ici",
        type=["mp3", "wav", "m4a", "mp4", "mkv", "mov"],
        help="Le fichier sera traité localement sans connexion internet."
    )
    
    # Initialisation de l'état
    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False
    if "transcription_done" not in st.session_state:
        st.session_state.transcription_done = False
        
    if uploaded_file and not st.session_state.is_processing and not st.session_state.transcription_done:
        if st.button("Lancer la transcription", type="primary", use_container_width=True):
            file_path = save_uploaded_file(uploaded_file)
            output_dir = Path.cwd() / "output"
            
            st.session_state.progress_queue = queue.Queue()
            st.session_state.stop_event = threading.Event()
            st.session_state.current_file = file_path
            st.session_state.output_dir = output_dir
            st.session_state.is_processing = True
            
            # Lancement du thread
            t = threading.Thread(
                target=transcribe_file_threaded,
                kwargs={
                    "file_path": file_path,
                    "output_dir": output_dir,
                    "profile": st.session_state.hw_profile,
                    "progress_queue": st.session_state.progress_queue,
                    "stop_event": st.session_state.stop_event,
                    "model_size": st.session_state.selected_model
                }
            )
            add_script_run_ctx(t)
            t.start()
            st.rerun()
            
    # Zone d'affichage en cours de traitement
    if st.session_state.is_processing:
        st.info("Traitement en cours... Ne fermez pas l'application.")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            progress_bar = st.progress(0)
            status_text = st.empty()
            live_text = st.empty()
            
        with col2:
            if st.button("Arrêter", type="secondary", use_container_width=True):
                st.session_state.stop_event.set()
                st.session_state.is_processing = False
                st.warning("Arrêt demandé...")
                st.rerun()
                
        # Lecture de la queue
        while not st.session_state.progress_queue.empty():
            msg = st.session_state.progress_queue.get()
            
            if msg["status"] == "loading_model":
                status_text.text("Chargement du modèle en mémoire... (Cela peut inclure un téléchargement in-app au premier lancement)")
            elif msg["status"] == "starting":
                status_text.text("Démarrage de la transcription...")
            elif msg["status"] == "progress":
                pct = msg["percentage"]
                progress_bar.progress(int(pct))
                status_text.text(f"Transcription : {pct:.1f}%")
                # Affichage du segment courant
                st.session_state.latest_text = st.session_state.get("latest_text", "") + " " + msg["segment_text"]
            elif msg["status"] == "file_complete":
                st.session_state.is_processing = False
                st.session_state.transcription_done = True
                status_text.text("Terminé !")
                progress_bar.progress(100)
                st.rerun()
            elif msg["status"] == "error":
                st.error(f"Erreur : {msg['error']}")
                st.session_state.is_processing = False
                st.rerun()
            elif msg["status"] == "stopped":
                st.session_state.is_processing = False
                st.rerun()
                
        # Affichage temps réel du texte
        if "latest_text" in st.session_state:
            live_text.markdown(f"*{st.session_state.latest_text[-500:]}*")
            
        time.sleep(0.5)
        st.rerun()
        
    # Résultats finaux
    if st.session_state.transcription_done and not st.session_state.is_processing:
        st.success("Transcription terminée avec succès !")
        
        file_path = st.session_state.current_file
        out_dir = st.session_state.output_dir
        base_name = file_path.stem
        md_file = out_dir / f"{base_name}.md"
        srt_file = out_dir / f"{base_name}.srt"
        
        col1, col2 = st.columns(2)
        if md_file.exists():
            with col1:
                with open(md_file, "r", encoding="utf-8") as f:
                    st.download_button(
                        label="📥 Télécharger le Markdown (.md)",
                        data=f.read(),
                        file_name=f"{base_name}.md",
                        mime="text/markdown",
                        use_container_width=True
                    )
                    
        if srt_file.exists():
            with col2:
                with open(srt_file, "r", encoding="utf-8") as f:
                    st.download_button(
                        label="📥 Télécharger les Sous-titres (.srt)",
                        data=f.read(),
                        file_name=f"{base_name}.srt",
                        mime="text/plain",
                        use_container_width=True
                    )
                    
        st.divider()
        render_llm_templates()
        st.divider()
        
        if md_file.exists():
            with open(md_file, "r", encoding="utf-8") as f:
                st.markdown(f.read())
                
        if st.button("Nouvelle transcription"):
            st.session_state.transcription_done = False
            st.session_state.latest_text = ""
            st.rerun()

if __name__ == "__main__":
    main()
