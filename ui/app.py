"""
LocalScribe — Interface Utilisateur Moderne (Streamlit + Shadcn UI).
Supporte la transcription par dossier (récursive avec .txt in-place et Smart Resume)
ainsi que la transcription de fichier unique.
"""

import os
import sys
import time
import queue
import threading
import tempfile
import subprocess
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
from core.transcription_engine import (
    transcribe_file_threaded, 
    transcribe_batch_threaded, 
    SUPPORTED_EXTENSIONS
)

LOGO_PATH = PROJECT_ROOT / "assets" / "logo.png"

def open_folder_in_explorer(folder_path: Path):
    """Ouvre le dossier dans l'explorateur Windows ou le gestionnaire de fichiers."""
    try:
        if sys.platform == "win32":
            os.startfile(str(folder_path))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(folder_path)])
        else:
            subprocess.run(["xdg-open", str(folder_path)])
    except Exception:
        pass

def select_folder_dialog() -> str:
    """Ouvre la boîte de dialogue native pour sélectionner un dossier."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(title="Sélectionnez le dossier contenant vos vidéos")
        root.destroy()
        return folder
    except Exception:
        return ""

def render_sidebar():
    """Affiche la barre latérale avec logo et options de configuration."""
    with st.sidebar:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), use_container_width=True)
        else:
            st.title("🎙️ LocalScribe")
            
        st.markdown("### ⚙️ Matériel & Accélération")
        
        # Détection matérielle
        if "hw_profile" not in st.session_state:
            st.session_state.hw_profile = detect_hardware()
            
        profile = st.session_state.hw_profile
        
        col_dev, col_comp = st.columns(2)
        with col_dev:
            st.caption("Périphérique")
            dev_badge_variant = "default" if profile.device == "cuda" else "secondary"
            ui.badge(profile.device.upper(), variant=dev_badge_variant)
        with col_comp:
            st.caption("Précision")
            ui.badge(profile.compute_type, variant="outline")
            
        if profile.vram_gb:
            st.caption(f"VRAM disponible : **{profile.vram_gb:.1f} GB**")
            
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
            help="Modèles plus grands = meilleure précision mais plus lents. 'medium' est optimal pour une RTX 3060."
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
    
    # En-tête Principal
    col_logo, col_header = st.columns([1, 6])
    with col_logo:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=100)
    with col_header:
        st.title("LocalScribe")
        st.caption("Transcription audio & vidéo haute performance, 100 % locale et sécurisée.")
        ui.badges([
            ("🔒 100% Hors-Ligne", "default"),
            ("📁 Traitement par Dossier (In-Place)", "secondary"),
            ("⚡ GPU RTX CUDA Actif", "outline")
        ])
        
    st.markdown("<div style='margin-bottom: 1.25rem;'></div>", unsafe_allow_html=True)

    # Initialisation de l'état
    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False
    if "transcription_done" not in st.session_state:
        st.session_state.transcription_done = False
    if "mode" not in st.session_state:
        st.session_state.mode = "batch" # Par défaut : mode dossier
    if "target_folder" not in st.session_state:
        st.session_state.target_folder = ""
    if "latest_text" not in st.session_state:
        st.session_state.latest_text = ""
    if "batch_stats" not in st.session_state:
        st.session_state.batch_stats = {}

    # Sélecteur de Mode
    mode_selection = st.radio(
        "Mode de traitement :",
        options=["📁 Dossier complet (Tous les sous-dossiers & fichiers .txt in-place)", "📄 Fichier unique (Glisser-déposer)"],
        horizontal=True,
        disabled=st.session_state.is_processing
    )
    is_batch_mode = "Dossier complet" in mode_selection

    # =========================================================================
    # VUE 1 : Configuration et Lancement
    # =========================================================================
    if not st.session_state.is_processing and not st.session_state.transcription_done:
        
        # --- MODE 1 : DOSSIER COMPLET (BATCH RÉCURSIF IN-PLACE) ---
        if is_batch_mode:
            st.markdown("### 📁 Sélection du dossier de vidéos")
            st.info(
                "LocalScribe va analyser le dossier choisi ainsi que **tous ses sous-dossiers**. "
                "Chaque vidéo sera retranscrite sous forme d'un fichier **`.txt` portant exactement le même nom**, "
                "placé **directement à côté de la vidéo**. Si un fichier `.txt` existe déjà, il sera automatiquement ignoré (Smart Resume)."
            )
            
            col_path, col_btn = st.columns([5, 1])
            with col_path:
                target_input = st.text_input(
                    "Chemin du dossier :",
                    value=st.session_state.target_folder,
                    placeholder=r"Exemple : C:\Users\Nom\Vidéos\Formations",
                    help="Entrez le chemin absolu du dossier ou utilisez le bouton Parcourir."
                )
                if target_input:
                    st.session_state.target_folder = target_input
            with col_btn:
                st.markdown("<div style='margin-top: 1.85rem;'></div>", unsafe_allow_html=True)
                if st.button("📂 Parcourir...", use_container_width=True):
                    picked = select_folder_dialog()
                    if picked:
                        st.session_state.target_folder = picked
                        st.rerun()

            # Analyse en direct du dossier si spécifié
            current_folder = Path(st.session_state.target_folder).resolve() if st.session_state.target_folder else None
            if current_folder and current_folder.exists() and current_folder.is_dir():
                found_files = [
                    f for f in current_folder.rglob("*")
                    if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
                ]
                total_found = len(found_files)
                already_done = sum(1 for f in found_files if f.with_suffix(".txt").exists() and f.with_suffix(".txt").stat().st_size > 0)
                remaining = total_found - already_done
                
                col_m1, col_m2, col_m3 = st.columns(3)
                with col_m1:
                    ui.metric_card("Vidéos détectées", total_found, description="Dans le dossier & sous-dossiers")
                with col_m2:
                    ui.metric_card("Déjà transcrites (.txt)", already_done, description="Ignorées (Smart Resume)")
                with col_m3:
                    ui.metric_card("Restantes à traiter", remaining, description="À convertir")

                # Options d'export supplémentaires
                st.markdown("##### Options de génération :")
                col_opt1, col_opt2, col_opt3 = st.columns(3)
                with col_opt1:
                    st.checkbox("📄 Fichier texte brut (.txt)", value=True, disabled=True, help="Toujours généré dans le même dossier que la vidéo.")
                with col_opt2:
                    export_srt = st.checkbox("⏱️ Sous-titres (.srt)", value=False, help="Générer également un fichier .srt à côté de chaque vidéo.")
                with col_opt3:
                    export_md = st.checkbox("📝 Markdown structuré (.md)", value=False, help="Générer également un fichier .md avec front-matter.")

                if total_found > 0:
                    if st.button("🚀 Démarrer la transcription du dossier", type="primary", use_container_width=True):
                        st.session_state.progress_queue = queue.Queue()
                        st.session_state.stop_event = threading.Event()
                        st.session_state.is_processing = True
                        st.session_state.is_batch = True
                        st.session_state.progress_pct = 0
                        st.session_state.status_label = "Démarrage du lot..."
                        st.session_state.current_file_name = ""
                        st.session_state.current_file_idx = 0
                        st.session_state.total_batch_files = total_found
                        st.session_state.latest_text = ""
                        
                        t = threading.Thread(
                            target=transcribe_batch_threaded,
                            kwargs={
                                "target_dir": current_folder,
                                "profile": st.session_state.hw_profile,
                                "progress_queue": st.session_state.progress_queue,
                                "stop_event": st.session_state.stop_event,
                                "model_size": st.session_state.selected_model,
                                "export_srt": export_srt,
                                "export_md": export_md
                            }
                        )
                        add_script_run_ctx(t)
                        t.start()
                        st.rerun()
                else:
                    st.warning("Aucun fichier vidéo ou audio supporté trouvé dans ce dossier.")
            elif st.session_state.target_folder:
                st.error("Le chemin spécifié n'existe pas ou n'est pas un dossier valide.")

        # --- MODE 2 : FICHIER UNIQUE (GLISSER-DÉPOSER) ---
        else:
            st.markdown("### 📄 Importer un enregistrement individuel")
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
                    ui.metric_card("Modèle", st.session_state.selected_model, description="Whisper sélectionné")
                    
                if st.button("🚀 Démarrer la transcription", type="primary", use_container_width=True):
                    file_path = save_uploaded_file(uploaded_file)
                    output_dir = PROJECT_ROOT / "output"
                    
                    st.session_state.progress_queue = queue.Queue()
                    st.session_state.stop_event = threading.Event()
                    st.session_state.current_file = file_path
                    st.session_state.output_dir = output_dir
                    st.session_state.is_processing = True
                    st.session_state.is_batch = False
                    st.session_state.progress_pct = 0
                    st.session_state.status_label = "Initialisation..."
                    st.session_state.latest_text = ""
                    
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

    # =========================================================================
    # VUE 2 : Traitement en cours (Non bloquant)
    # =========================================================================
    elif st.session_state.is_processing:
        st.markdown("### ⏳ Transcription en cours...")
        
        is_batch = st.session_state.get("is_batch", False)
        
        col_bar, col_stop = st.columns([5, 1])
        with col_bar:
            if is_batch:
                current_idx = st.session_state.get("current_file_idx", 0)
                total_files = st.session_state.get("total_batch_files", 1)
                file_name = st.session_state.get("current_file_name", "")
                
                # Double barre : avancement du lot et avancement du fichier en cours
                batch_pct = int((current_idx / total_files) * 100) if total_files > 0 else 0
                st.markdown(f"**Progression globale : Vidéo {current_idx} / {total_files}**")
                st.progress(batch_pct)
                
                file_pct = int(st.session_state.get("progress_pct", 0))
                st.markdown(f"Fichier en cours : `{file_name}` ({file_pct}%)")
                st.progress(file_pct)
            else:
                progress_val = int(st.session_state.get("progress_pct", 0))
                st.progress(progress_val)
                st.markdown(f"**Statut :** `{st.session_state.get('status_label', 'En cours...')}`")
                
        with col_stop:
            if st.button("🛑 Interrompre", type="secondary", use_container_width=True):
                st.session_state.stop_event.set()
                st.session_state.is_processing = False
                st.warning("Arrêt demandé...")
                st.rerun()
                
        # Consommation de la queue
        while not st.session_state.progress_queue.empty():
            msg = st.session_state.progress_queue.get()
            status = msg.get("status")
            
            if status == "loading_model":
                st.session_state.status_label = "Chargement du modèle en mémoire GPU..."
            elif status == "batch_discovered":
                st.session_state.total_batch_files = msg.get("total_files", 1)
            elif status == "file_start":
                st.session_state.current_file_name = msg.get("file_name", "")
                st.session_state.current_file_idx = msg.get("current_idx", 1)
                st.session_state.progress_pct = 0
                st.session_state.latest_text = ""
            elif status == "file_skipped":
                st.session_state.current_file_idx = msg.get("current_idx", 1)
            elif status == "progress":
                st.session_state.progress_pct = int(msg.get("percentage", 0))
                st.session_state.current_file_name = msg.get("file_name", st.session_state.get("current_file_name", ""))
                st.session_state.current_file_idx = msg.get("current_idx", st.session_state.get("current_file_idx", 1))
                st.session_state.latest_text += " " + msg.get("segment_text", "")
            elif status == "file_complete":
                if not is_batch:
                    st.session_state.is_processing = False
                    st.session_state.transcription_done = True
                    st.session_state.progress_pct = 100
                    st.rerun()
            elif status == "batch_complete":
                st.session_state.is_processing = False
                st.session_state.transcription_done = True
                st.session_state.batch_stats = {
                    "total": msg.get("total_files", 0),
                    "processed": msg.get("processed", 0),
                    "skipped": msg.get("skipped", 0)
                }
                st.rerun()
            elif status == "error":
                st.session_state.is_processing = False
                st.error(f"Erreur durant la transcription : {msg.get('error')}")
                st.rerun()
            elif status == "stopped":
                st.session_state.is_processing = False
                st.warning("Traitement arrêté par l'utilisateur.")
                st.rerun()
                
        # Flux en direct
        if st.session_state.latest_text:
            st.markdown("##### 🎙️ Flux retranscrit en direct :")
            preview = st.session_state.latest_text[-400:]
            st.info(f"... {preview}")
            
        time.sleep(0.3)
        st.rerun()

    # =========================================================================
    # VUE 3 : Résultats et Exports
    # =========================================================================
    elif st.session_state.transcription_done:
        is_batch = st.session_state.get("is_batch", False)
        
        if is_batch:
            stats = st.session_state.get("batch_stats", {})
            st.success("🎉 Transcription du dossier terminée avec succès !")
            
            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                ui.metric_card("Total analysé", stats.get("total", 0), description="Vidéos dans le dossier")
            with col_b2:
                ui.metric_card("Nouvellement transcrites", stats.get("processed", 0), description="Fichiers .txt générés in-place")
            with col_b3:
                ui.metric_card("Déjà existantes", stats.get("skipped", 0), description="Ignorées (Smart Resume)")
                
            st.markdown("---")
            folder_path = Path(st.session_state.target_folder)
            st.markdown(f"Tous les fichiers **`.txt`** ont été enregistrés directement à côté de chaque vidéo dans :  \n`{folder_path.resolve()}`")
            
            if st.button("📂 Ouvrir le dossier dans l'explorateur", type="primary"):
                open_folder_in_explorer(folder_path)
                
            st.markdown("<hr style='margin: 1.5rem 0; opacity: 0.15;'>", unsafe_allow_html=True)
            if st.button("🔄 Traiter un autre dossier", use_container_width=True):
                st.session_state.transcription_done = False
                st.session_state.is_processing = False
                st.session_state.latest_text = ""
                st.rerun()
        else:
            # Affichage fichier unique
            st.success("🎉 Transcription terminée avec succès !")
            file_path = st.session_state.current_file
            out_dir = st.session_state.output_dir
            base_name = file_path.stem
            txt_file = out_dir / f"{base_name}.txt"
            md_file = out_dir / f"{base_name}.md"
            srt_file = out_dir / f"{base_name}.srt"
            
            txt_text = txt_file.read_text(encoding="utf-8") if txt_file.exists() else ""
            md_text = md_file.read_text(encoding="utf-8") if md_file.exists() else ""
            srt_text = srt_file.read_text(encoding="utf-8") if srt_file.exists() else ""
            
            tab_options = ["📄 Texte (.TXT)", "📝 Markdown (.MD)", "⏱️ Sous-titres (.SRT)", "🤖 Templates LLM"]
            active_tab = ui.tabs(options=tab_options, key="results_tabs_nav")
            
            if active_tab == "📄 Texte (.TXT)":
                st.download_button(
                    label="📥 Télécharger le fichier texte (.txt)",
                    data=txt_text,
                    file_name=f"{base_name}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
                st.text_area("Transcription brute :", value=txt_text, height=350)
                
            elif active_tab == "📝 Markdown (.MD)":
                st.download_button(
                    label="📥 Télécharger le Markdown (.md)",
                    data=md_text,
                    file_name=f"{base_name}.md",
                    mime="text/markdown",
                    use_container_width=True
                )
                st.markdown(md_text)
                
            elif active_tab == "⏱️ Sous-titres (.SRT)":
                st.download_button(
                    label="📥 Télécharger les Sous-titres (.srt)",
                    data=srt_text,
                    file_name=f"{base_name}.srt",
                    mime="text/plain",
                    use_container_width=True
                )
                st.code(srt_text, language="text")
                
            elif active_tab == "🤖 Templates LLM":
                render_llm_templates(transcription_text=txt_text)
                
            st.markdown("<hr style='margin: 2rem 0; opacity: 0.15;'>", unsafe_allow_html=True)
            if st.button("🔄 Nouvelle transcription", use_container_width=True):
                st.session_state.transcription_done = False
                st.session_state.is_processing = False
                st.session_state.latest_text = ""
                st.rerun()

if __name__ == "__main__":
    main()
