"""
LocalScribe — Interface Utilisateur Moderne (Streamlit + Shadcn UI).
"""

import os
import sys
import time
import queue
import threading
import tempfile
from pathlib import Path

# Résolution des imports locaux
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import streamlit_shadcn_ui as ui
from streamlit.runtime.scriptrunner import add_script_run_ctx

from ui.styles import inject_custom_css
from ui.prompts_templates import render_llm_templates
from core.hardware_profiler import detect_hardware
from core.transcription_engine import transcribe_file_threaded

LOGO_PATH = PROJECT_ROOT / "assets" / "logo.png"

def render_sidebar():
    """Affiche la barre latérale avec logo et options de configuration."""
    with st.sidebar:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), use_container_width=True)
        else:
            st.title("🎙️ LocalScribe")
            
        st.markdown("### ⚙️ Matériel & Accélération")
        
        # Détection matérielle en cache de session
        if "hw_profile" not in st.session_state:
            st.session_state.hw_profile = detect_hardware()
            
        profile = st.session_state.hw_profile
        
        # Affichage des métriques matérielles avec badges
        col_dev, col_comp = st.columns(2)
        with col_dev:
            st.caption("Périphérique")
            dev_badge_variant = "default" if profile.device == "cuda" else "secondary"
            ui.badge(profile.device.upper(), variant=dev_badge_variant)
        with col_comp:
            st.caption("Précision")
            ui.badge(profile.compute_type, variant="outline")
            
        if profile.vram_gb:
            st.caption(f"VRAM disponible : {profile.vram_gb:.1f} GB")
            
        for warning in profile.warnings:
            st.warning(warning)
            
        st.markdown("<hr style='margin: 1rem 0; opacity: 0.15;'>", unsafe_allow_html=True)
        
        st.markdown("### 🧠 Modèle Whisper")
        model_options = ["tiny", "base", "small", "medium", "large-v3"]
        default_index = model_options.index(profile.recommended_model) if profile.recommended_model in model_options else 1
        
        selected_model = st.selectbox(
            "Taille du modèle",
            options=model_options,
            index=default_index,
            help="Modèles plus grands = meilleure précision mais plus lents. 'base' ou 'small' conviennent à la plupart des usages."
        )
        st.session_state.selected_model = selected_model
        
        st.caption(f"Recommandation auto : `{profile.recommended_model}`")
        
        st.markdown("<hr style='margin: 1.5rem 0; opacity: 0.15;'>", unsafe_allow_html=True)
        st.caption("🛡️ **100% Local & Privé**\nAucune donnée n'est transmise sur internet.")

def save_uploaded_file(uploaded_file) -> Path:
    """Sauvegarde temporaire du fichier uploadé pour traitement local."""
    temp_dir = Path(tempfile.gettempdir()) / "LocalScribe"
    temp_dir.mkdir(parents=True, exist_ok=True)
    file_path = temp_dir / uploaded_file.name
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def main():
    st.set_page_config(
        page_title="LocalScribe — Transcription Locale",
        page_icon="🎙️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    inject_custom_css()
    render_sidebar()
    
    # Header Principal
    col_logo, col_header = st.columns([1, 6])
    with col_logo:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=100)
    with col_header:
        st.title("LocalScribe")
        st.caption("Transcription audio & vidéo haute performance, 100 % locale et sécurisée.")
        ui.badges([
            ("🔒 Zéro Réseau", "default"),
            ("⚡ faster-whisper", "secondary"),
            ("🎯 Front-Matter & SRT", "outline")
        ])
        
    st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)

    # État de l'application
    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False
    if "transcription_done" not in st.session_state:
        st.session_state.transcription_done = False
    if "latest_text" not in st.session_state:
        st.session_state.latest_text = ""
        
    # Vue 1 : Upload et initialisation
    if not st.session_state.is_processing and not st.session_state.transcription_done:
        st.markdown("### 📁 Importer un enregistrement")
        uploaded_file = st.file_uploader(
            "Glissez-déposez un fichier audio ou vidéo",
            type=["mp3", "wav", "m4a", "ogg", "flac", "mp4", "mkv", "mov"],
            help="Formats supportés : MP3, WAV, M4A, OGG, FLAC, MP4, MKV, MOV"
        )
        
        if uploaded_file:
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                ui.metric_card("Fichier", uploaded_file.name, description="Nom source")
            with col_info2:
                file_size_mb = uploaded_file.size / (1024 * 1024)
                ui.metric_card("Taille", f"{file_size_mb:.2f} MB", description="Poids du fichier")
            with col_info3:
                ui.metric_card("Modèle sélectionné", st.session_state.selected_model, description="faster-whisper")
                
            st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
            
            if st.button("🚀 Démarrer la transcription", type="primary", use_container_width=True):
                file_path = save_uploaded_file(uploaded_file)
                output_dir = PROJECT_ROOT / "output"
                
                st.session_state.progress_queue = queue.Queue()
                st.session_state.stop_event = threading.Event()
                st.session_state.current_file = file_path
                st.session_state.output_dir = output_dir
                st.session_state.is_processing = True
                st.session_state.progress_pct = 0
                st.session_state.status_label = "Initialisation..."
                st.session_state.latest_text = ""
                
                # Lancement du thread de traitement
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

    # Vue 2 : Traitement en cours (Non bloquant)
    elif st.session_state.is_processing:
        st.markdown("### ⏳ Transcription en cours...")
        
        col_bar, col_stop = st.columns([5, 1])
        with col_bar:
            progress_val = int(st.session_state.get("progress_pct", 0))
            st.progress(progress_val)
            st.markdown(f"**Statut :** `{st.session_state.get('status_label', 'En cours...')}`")
        with col_stop:
            if st.button("🛑 Interrompre", type="secondary", use_container_width=True):
                st.session_state.stop_event.set()
                st.session_state.is_processing = False
                st.warning("Arrêt demandé...")
                st.rerun()
                
        # Lecture réactive de la queue
        while not st.session_state.progress_queue.empty():
            msg = st.session_state.progress_queue.get()
            
            if msg["status"] == "loading_model":
                st.session_state.status_label = "Chargement du modèle en mémoire..."
            elif msg["status"] == "starting":
                st.session_state.status_label = "Traitement audio et analyse..."
            elif msg["status"] == "progress":
                st.session_state.progress_pct = int(msg["percentage"])
                st.session_state.status_label = f"Progression : {msg['percentage']:.1f}% ({msg['current_time']:.1f}s / {msg['duration']:.1f}s)"
                st.session_state.latest_text += " " + msg["segment_text"]
            elif msg["status"] == "file_complete":
                st.session_state.is_processing = False
                st.session_state.transcription_done = True
                st.session_state.progress_pct = 100
                st.rerun()
            elif msg["status"] == "error":
                st.session_state.is_processing = False
                st.error(f"Erreur durant la transcription : {msg.get('error')}")
                st.rerun()
            elif msg["status"] == "stopped":
                st.session_state.is_processing = False
                st.warning("Transcription interrompue.")
                st.rerun()
                
        # Flux texte en direct
        if st.session_state.latest_text:
            st.markdown("##### 🎙️ Flux retranscrit en direct :")
            preview = st.session_state.latest_text[-400:]
            st.info(f"... {preview}")
            
        time.sleep(0.4)
        st.rerun()

    # Vue 3 : Résultats et Export
    elif st.session_state.transcription_done:
        st.success("🎉 Transcription terminée avec succès !")
        
        file_path = st.session_state.current_file
        out_dir = st.session_state.output_dir
        base_name = file_path.stem
        md_file = out_dir / f"{base_name}.md"
        srt_file = out_dir / f"{base_name}.srt"
        
        md_text = md_file.read_text(encoding="utf-8") if md_file.exists() else ""
        srt_text = srt_file.read_text(encoding="utf-8") if srt_file.exists() else ""
        
        # Navigation par onglets Shadcn
        tab_options = ["📄 Transcription (Markdown)", "⏱️ Sous-titres (SRT)", "🤖 Templates LLM", "📊 Fichiers & Métadonnées"]
        active_tab = ui.tabs(options=tab_options, key="results_tabs_nav")
        
        if active_tab == "📄 Transcription (Markdown)":
            col_dl, col_space = st.columns([1, 3])
            with col_dl:
                st.download_button(
                    label="📥 Télécharger .MD",
                    data=md_text,
                    file_name=f"{base_name}.md",
                    mime="text/markdown",
                    use_container_width=True
                )
            st.markdown(md_text)
            
        elif active_tab == "⏱️ Sous-titres (SRT)":
            col_dl_srt, col_space = st.columns([1, 3])
            with col_dl_srt:
                st.download_button(
                    label="📥 Télécharger .SRT",
                    data=srt_text,
                    file_name=f"{base_name}.srt",
                    mime="text/plain",
                    use_container_width=True
                )
            st.code(srt_text, language="text")
            
        elif active_tab == "🤖 Templates LLM":
            render_llm_templates(transcription_text=md_text)
            
        elif active_tab == "📊 Fichiers & Métadonnées":
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                ui.metric_card("Fichier source", file_path.name, description=f"Stocké dans {file_path.parent}")
            with col_m2:
                ui.metric_card("Dossier d'export", str(out_dir), description="Sorties MD et SRT")
                
            st.markdown(f"""
            - **Fichier Markdown :** `{md_file.resolve()}`
            - **Fichier SRT :** `{srt_file.resolve()}`
            """)
            
        st.markdown("<hr style='margin: 2rem 0; opacity: 0.15;'>", unsafe_allow_html=True)
        if st.button("🔄 Nouvelle transcription", use_container_width=True):
            st.session_state.transcription_done = False
            st.session_state.is_processing = False
            st.session_state.latest_text = ""
            st.rerun()

if __name__ == "__main__":
    main()
