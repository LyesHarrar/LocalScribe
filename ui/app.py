"""
LocalScribe — Interface Utilisateur Haute Fidélité (Design System Épuré).
Assorti au logo : Noir Obsidienne (#05070e) & Bleu Électrique (#2e74fd).
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
from streamlit.runtime.scriptrunner import add_script_run_ctx

import importlib
import ui.styles
importlib.reload(ui.styles)
from ui.styles import inject_custom_css
from ui.prompts_templates import render_llm_templates
from core.hardware_profiler import detect_hardware
from core.clipboard import copy_to_clipboard
from core.transcription_engine import (
    transcribe_file_threaded, 
    transcribe_batch_threaded, 
    SUPPORTED_EXTENSIONS,
    SUPPORTED_LANGUAGES
)

LOGO_PATH = PROJECT_ROOT / "assets" / "logo.png"

def open_folder_in_explorer(folder_path: Path):
    """Ouvre le dossier dans l'explorateur de fichiers natif."""
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
    """Ouvre le sélecteur natif de dossier Windows/Mac."""
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

def render_metric_card(label: str, value: str, subtext: str = ""):
    """Rendu d'une carte métrique au style Framer / Linear."""
    st.markdown(f"""
    <div style="background: #18181b; border: 1px solid #27272a; border-radius: 12px; padding: 1rem 1.25rem; box-shadow: 0 4px 14px rgba(0,0,0,0.3);">
        <div style="color: #a1a1aa; font-size: 0.78rem; font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.3rem;">{label}</div>
        <div style="color: #f8fafc; font-size: 1.35rem; font-weight: 700; letter-spacing: -0.02em;">{value}</div>
        <div style="color: #71717a; font-size: 0.76rem; margin-top: 0.2rem;">{subtext}</div>
    </div>
    """, unsafe_allow_html=True)

def render_badge(text: str, color: str = "#60a5fa", bg: str = "rgba(46, 116, 253, 0.12)"):
    """Badge pill moderne avec support des icones material."""
    import re
    # Convert :material/icon: to HTML span
    parsed_text = re.sub(r':material/([^:]+):', r'<span class="material-symbols-rounded" style="font-family: \'Material Symbols Rounded\' !important; font-size: 1.1em; margin-right: 4px; vertical-align: -0.125em;">\1</span>', text)
    return f"""<span style="background: {bg}; color: {color}; border: 1px solid rgba(46, 116, 253, 0.28); padding: 4px 12px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; letter-spacing: 0.02em; display: inline-flex; align-items: center; margin-right: 6px;">{parsed_text}</span>"""

def render_sidebar():
    """Barre latérale avec configuration et matériel."""
    with st.sidebar:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), use_container_width=True)
        else:
            st.title("LocalScribe")
            
        st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
        st.markdown("### :material/settings: Accélération Matérielle")
        
        if "hw_profile" not in st.session_state:
            st.session_state.hw_profile = detect_hardware()
            
        profile = st.session_state.hw_profile
        
        # Badges matériels
        dev_badge = render_badge(f":material/bolt: {profile.device.upper()}", color="#38bdf8", bg="rgba(56, 189, 248, 0.12)") if profile.device == "cuda" else render_badge(f":material/computer: {profile.device.upper()}", color="#94a3b8", bg="rgba(148, 163, 184, 0.12)")
        comp_badge = render_badge(f":material/center_focus_strong: {profile.compute_type}", color="#818cf8", bg="rgba(129, 140, 248, 0.12)")
        
        st.markdown(f"<div>{dev_badge}{comp_badge}</div>", unsafe_allow_html=True)
        
        if profile.vram_gb:
            st.markdown(f"<div style='color: #94a3b8; font-size: 0.85rem; margin-top: 0.6rem;'>VRAM Détectée : <strong style='color: #f8fafc;'>{profile.vram_gb:.1f} GB</strong></div>", unsafe_allow_html=True)
            
        for warning in profile.warnings:
            st.warning(warning)
            
        st.markdown("<hr style='margin: 1.25rem 0; border: none; border-top: 1px solid #27272a;'>", unsafe_allow_html=True)
        
        st.markdown("### :material/memory: Modèle Whisper")
        model_options = ["tiny", "base", "small", "medium", "large-v3"]
        default_index = model_options.index(profile.recommended_model) if profile.recommended_model in model_options else 1
        
        selected_model = st.selectbox(
            "Taille du modèle",
            options=model_options,
            index=default_index,
            help="Modèles plus grands = meilleure précision. 'medium' est idéal pour les cartes NVIDIA RTX 3060."
        )
        st.session_state.selected_model = selected_model
        st.caption(f"Recommandation système : `{profile.recommended_model}`")
        
        st.markdown("<hr style='margin: 1.25rem 0; border: none; border-top: 1px solid #27272a;'>", unsafe_allow_html=True)
        st.markdown("### :material/tune: Options Audio & IA")

        # 1. Tâche
        task_choice = st.radio(
            "Tâche :",
            options=["🎙️ Transcrire", "🌐 Traduire vers l'anglais"],
            index=0,
            help="'Transcrire' préserve la langue originale. 'Traduire vers l'anglais' traduit directement le texte en anglais."
        )
        st.session_state.selected_task = "translate" if "Traduire" in task_choice else "transcribe"

        # 2. Langue source
        lang_keys = list(SUPPORTED_LANGUAGES.keys())
        lang_labels = list(SUPPORTED_LANGUAGES.values())
        selected_lang_label = st.selectbox(
            "Langue source :",
            options=lang_labels,
            index=0,
            help="Langue parlée dans l'audio. Laissez sur Détection automatique si vous hésitez."
        )
        selected_lang_code = lang_keys[lang_labels.index(selected_lang_label)]
        st.session_state.selected_language = None if selected_lang_code == "auto" else selected_lang_code

        # 3. Filtre VAD (Voice Activity Detection)
        use_vad = st.checkbox(
            "Filtrer les silences (Silero VAD)",
            value=True,
            help="Supprime les silences pour accélérer le traitement et éliminer les hallucinations."
        )
        st.session_state.use_vad = use_vad

        # 4. Vocabulaire spécifique / Noms propres
        initial_prompt = st.text_input(
            "Vocabulaire & Acronymes (Optionnel) :",
            value="",
            placeholder="ex: LocalScribe, Whisper, Kubernetes...",
            help="Indiquez des mots rares, acronymes ou noms propres pour améliorer leur reconnaissance."
        )
        st.session_state.initial_prompt = initial_prompt.strip() if initial_prompt else None

        # 5. Diarisation des locuteurs (Identification qui parle)
        use_diarization = st.checkbox(
            "🗣️ Identifier les locuteurs (Diarisation)",
            value=False,
            help="Distingue les voix et attribue chaque segment à un interlocuteur distinct (ex: Locuteur 1, Locuteur 2)."
        )
        st.session_state.use_diarization = use_diarization

        num_speakers = None
        if use_diarization:
            speaker_choice = st.radio(
                "Nombre d'interlocuteurs :",
                options=["Auto-détection", "Nombre exact"],
                horizontal=True
            )
            if speaker_choice == "Nombre exact":
                num_speakers = st.number_input(
                    "Nombre de locuteurs :",
                    min_value=1,
                    max_value=10,
                    value=2,
                    step=1
                )
        st.session_state.num_speakers = num_speakers

        st.markdown("<hr style='margin: 1.25rem 0; border: none; border-top: 1px solid #27272a;'>", unsafe_allow_html=True)
        st.markdown("""
        <div style="background: #18181b; border: 1px solid #27272a; border-radius: 10px; padding: 0.85rem;">
            <div style="font-weight: 600; color: #38bdf8; font-size: 0.82rem;">🛡️ Confidentialité Absolue</div>
            <div style="color: #a1a1aa; font-size: 0.75rem; margin-top: 0.2rem;">Aucun appel réseau. Zéro donnée partagée. Inférence 100% exécutée sur vos puces locales.</div>
        </div>
        """, unsafe_allow_html=True)

def save_uploaded_file(uploaded_file) -> Path:
    """Sauvegarde temporaire du fichier uploadé pour traitement local."""
    temp_dir = Path(tempfile.gettempdir()) / "LocalScribe"
    temp_dir.mkdir(parents=True, exist_ok=True)
    file_path = temp_dir / uploaded_file.name
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path


def render_history_view():
    """Affiche la bibliothèque et l'historique complet des transcriptions."""
    import streamlit_shadcn_ui as ui
    from core.history_manager import (
        get_records,
        get_history_stats,
        delete_record,
        clear_history
    )
    
    st.markdown("### :material/history: Bibliothèque & Historique des Transcriptions")
    st.markdown("<p style='color: #94a3b8; font-size: 0.95rem; margin-top: -0.25rem;'>Accédez à toutes vos transcriptions passées, recherchez par mot-clé et réexportez vos fichiers en un clic.</p>", unsafe_allow_html=True)
    
    # 1. Statistiques globales
    stats = get_history_stats()
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        ui.metric_card(
            label="Total Enregistré", 
            value=f"{stats['total_count']} fichiers", 
            description="Transcriptions mémorisées"
        )
    with col_s2:
        ui.metric_card(
            label="Volume Audio", 
            value=f"{stats['total_duration_hours']:.1f} h", 
            description=f"Soit ~{stats['total_duration_minutes']:.0f} minutes traitées"
        )
    with col_s3:
        ui.metric_card(
            label="Langues Rencontrées", 
            value=str(stats['distinct_languages']), 
            description="Langues sources distinctes"
        )
        
    st.markdown("<div style='margin-top: 1.25rem;'></div>", unsafe_allow_html=True)
    
    # 2. Barre de recherche et actions
    col_search, col_action = st.columns([4.2, 1])
    with col_search:
        search_query = st.text_input(
            "Recherche plein texte :",
            placeholder="🔍 Filtrer par mot-clé, nom de fichier, locuteur (ex: Alice), langue...",
            label_visibility="collapsed",
            key="history_search_input"
        )
    with col_action:
        if stats['total_count'] > 0:
            if st.button("🗑️ Vider tout", type="secondary", use_container_width=True, help="Efface tout l'historique de la base locale"):
                clear_history()
                st.success("Historique vidé.")
                st.rerun()

    # 3. Récupération des enregistrements
    records = get_records(query=search_query)
    
    if not records:
        if search_query:
            st.info(f"Aucune transcription ne correspond à votre recherche '{search_query}'.")
        else:
            st.info("Aucune transcription dans l'historique. Effectuez votre première transcription pour la voir apparaître ici !")
        return
        
    st.markdown(f"<p style='color: #94a3b8; font-size: 0.85rem; margin-bottom: 0.75rem;'>{len(records)} transcription(s) trouvée(s) :</p>", unsafe_allow_html=True)
    
    # 4. Affichage des fiches de transcription
    for rec in records:
        rec_id = rec["id"]
        filename = rec["filename"]
        created = rec["created_at"][:16].replace("T", " à ") if rec.get("created_at") else "Date inconnue"
        duration_s = rec.get("duration", 0.0)
        m, s = divmod(int(duration_s), 60)
        h, m = divmod(m, 60)
        dur_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
        speakers = rec.get("speakers", [])
        spk_str = ", ".join(speakers) if speakers else "Non segmenté"
        
        with st.expander(f"📄 **{filename}** — *{created}* ({dur_str})", expanded=False):
            # Métriques rapides
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"**Langue :** `{rec.get('language', 'auto').upper()}` ({rec.get('language_probability', 100):.0f}%)")
            c2.markdown(f"**Tâche :** `{rec.get('task', 'transcribe')}`")
            c3.markdown(f"**Modèle :** `{rec.get('model', 'medium')}`")
            c4.markdown(f"**Locuteurs :** `{spk_str}`")
            
            st.markdown("<hr style='margin: 0.5rem 0; border: none; border-top: 1px solid #27272a;'>", unsafe_allow_html=True)
            
            # Aperçu du texte
            txt_content = rec.get("transcript_text", "")
            if not txt_content and rec.get("txt_path"):
                p = Path(rec["txt_path"])
                if p.exists():
                    try:
                        txt_content = p.read_text(encoding="utf-8")
                    except Exception:
                        pass
                        
            st.text_area(
                "Texte de la transcription :",
                value=txt_content,
                height=180,
                key=f"hist_txt_{rec_id}"
            )
            
            # Boutons de copie, téléchargement et suppression
            col_cp, col_d1, col_d2, col_d3, col_del = st.columns([1.8, 1.2, 1.2, 1.2, 0.9])
            with col_cp:
                if st.button("📋 Copier le texte", key=f"btn_cp_hist_{rec_id}", use_container_width=True, help="Copier l'intégralité du texte dans le presse-papier"):
                    if copy_to_clipboard(txt_content):
                        st.toast("Transcription copiée dans le presse-papier !", icon="📋")
                    else:
                        st.error("Impossible d'accéder au presse-papier.")
            with col_d1:
                st.download_button(
                    label="⬇️ .txt",
                    data=txt_content,
                    file_name=f"{Path(filename).stem}.txt",
                    mime="text/plain",
                    key=f"dl_txt_{rec_id}",
                    use_container_width=True
                )
            with col_d2:
                # Contenu Markdown
                md_content = ""
                if rec.get("md_path") and Path(rec["md_path"]).exists():
                    try:
                        md_content = Path(rec["md_path"]).read_text(encoding="utf-8")
                    except Exception:
                        pass
                if not md_content:
                    md_content = f"# Transcription de {filename}\n\n{txt_content}"
                st.download_button(
                    label="⬇️ .md",
                    data=md_content,
                    file_name=f"{Path(filename).stem}.md",
                    mime="text/markdown",
                    key=f"dl_md_{rec_id}",
                    use_container_width=True
                )
            with col_d3:
                # Contenu SRT
                srt_content = ""
                if rec.get("srt_path") and Path(rec["srt_path"]).exists():
                    try:
                        srt_content = Path(rec["srt_path"]).read_text(encoding="utf-8")
                    except Exception:
                        pass
                if srt_content:
                    st.download_button(
                        label="⬇️ .srt",
                        data=srt_content,
                        file_name=f"{Path(filename).stem}.srt",
                        mime="text/plain",
                        key=f"dl_srt_{rec_id}",
                        use_container_width=True
                    )
                else:
                    st.caption("SRT non disponible")
            with col_del:
                if st.button("🗑️ Suppr.", key=f"del_rec_{rec_id}", use_container_width=True, help="Supprimer cet enregistrement de la base"):
                    delete_record(rec_id)
                    st.rerun()


def main():
    st.set_page_config(
        page_title="LocalScribe — Transcription Locale Haute Fidélité",
        page_icon="",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    inject_custom_css()
    render_sidebar()
    
    # En-tête Principal de l'Application
    st.markdown("""
    <div style="margin-bottom: 0.8rem;">
        <h1 style="font-size: 2.2rem; font-weight: 800; letter-spacing: -0.035em; margin: 0; background: linear-gradient(135deg, #ffffff 40%, #93c5fd 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">LocalScribe</h1>
        <p style="color: #94a3b8; font-size: 0.95rem; margin-top: 0.25rem; margin-bottom: 0;">Transcription audio & vidéo 100 % locale, privée et propulsée par faster-whisper.</p>
    </div>
    """, unsafe_allow_html=True)
    
    badges_html = (
        render_badge(":material/lock: Zéro Réseau", color="#38bdf8", bg="rgba(56, 189, 248, 0.1)") +
        render_badge(":material/folder: Batch In-Place", color="#60a5fa", bg="rgba(46, 116, 253, 0.1)") +
        render_badge(":material/bolt: Accélération RTX CUDA", color="#34d399", bg="rgba(52, 211, 153, 0.1)")
    )
    st.markdown(f"<div style='margin-top: 0.2rem;'>{badges_html}</div>", unsafe_allow_html=True)
    
    st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)

    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False
    if "transcription_done" not in st.session_state:
        st.session_state.transcription_done = False
    if "target_folder" not in st.session_state:
        st.session_state.target_folder = ""
    if "latest_text" not in st.session_state:
        st.session_state.latest_text = ""
    if "batch_stats" not in st.session_state:
        st.session_state.batch_stats = {}

    import streamlit_shadcn_ui as ui

    # Sélecteur de Mode Segmenté moderne
    mode_selection = st.segmented_control(
        "Mode de transcription",
        options=[
            ":material/folder: Mode Dossier (Batch)", 
            ":material/description: Mode Fichier Unique",
            ":material/history: Historique & Bibliothèque"
        ],
        default=":material/folder: Mode Dossier (Batch)",
        selection_mode="single",
        label_visibility="collapsed",
        key="mode_segmented_control"
    )
    if not mode_selection:
        mode_selection = ":material/folder: Mode Dossier (Batch)"
    is_batch_mode = "Dossier" in mode_selection
    is_history_mode = "Historique" in mode_selection

    # =========================================================================
    # VUE 1 : Configuration et Lancement / Bibliothèque
    # =========================================================================
    if not st.session_state.is_processing and not st.session_state.transcription_done:
        
        # --- MODE 0 : HISTORIQUE & BIBLIOTHÈQUE ---
        if is_history_mode:
            render_history_view()

        # --- MODE 1 : DOSSIER COMPLET (BATCH RÉCURSIF IN-PLACE) ---
        elif is_batch_mode:
            st.markdown("### :material/folder: Sélection du dossier racine")
            st.markdown("""
            <div style="background: #18181b; border: 1px solid #27272a; border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: 1.25rem;">
                <div style="color: #e2e8f0; font-size: 0.92rem; line-height: 1.5;">
                    LocalScribe va analyser récursivement ce dossier et <strong>l'ensemble de ses sous-dossiers</strong>. 
                    Chaque vidéo sera retranscrite sous forme d'un fichier <strong>.txt</strong> portant le même nom, 
                    <strong>déposé directement à côté de la vidéo</strong>. Les vidéos déjà transcrites seront ignorées automatiquement (<em>Smart Resume</em>).
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            col_path, col_btn = st.columns([5, 1])
            with col_path:
                target_input = st.text_input(
                    "Chemin d'accès au dossier :",
                    value=st.session_state.target_folder,
                    placeholder=r"Exemple : C:\Users\Nom\Vidéos\Formations"
                )
                if target_input:
                    st.session_state.target_folder = target_input
            with col_btn:
                st.markdown("<div style='margin-top: 1.7rem;'></div>", unsafe_allow_html=True)
                if st.button(":material/folder_open: Parcourir", use_container_width=True):
                    picked = select_folder_dialog()
                    if picked:
                        st.session_state.target_folder = picked
                        st.rerun()

            # Analyse dynamique du dossier
            current_folder = Path(st.session_state.target_folder).resolve() if st.session_state.target_folder else None
            if current_folder and current_folder.exists() and current_folder.is_dir():
                found_files = [
                    f for f in current_folder.rglob("*")
                    if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
                ]
                total_found = len(found_files)
                already_done = sum(1 for f in found_files if f.with_suffix(".txt").exists() and f.with_suffix(".txt").stat().st_size > 0)
                remaining = total_found - already_done
                
                st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
                col_m1, col_m2, col_m3 = st.columns(3)
                with col_m1:
                    ui.metric_card(label="Vidéos Détectées", value=str(total_found), description="Dans l'arborescence complète")
                with col_m2:
                    ui.metric_card(label="Déjà Transcrites", value=str(already_done), description="Ignorées (Smart Resume)")
                with col_m3:
                    ui.metric_card(label="Restantes à Traiter", value=str(remaining), description="À convertir par Whisper")

                st.markdown("<div style='margin-top: 1.25rem;'></div>", unsafe_allow_html=True)
                st.markdown("##### :material/settings: Options de sortie :")
                col_opt1, col_opt2, col_opt3 = st.columns(3)
                with col_opt1:
                    st.checkbox(":material/description: Texte brut (.txt)", value=True, disabled=True)
                with col_opt2:
                    export_srt = st.checkbox("⏱️ Sous-titres (.srt)", value=False)
                with col_opt3:
                    export_md = st.checkbox(":material/markdown: Markdown (.md)", value=False)

                st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
                if total_found > 0:
                    if st.button(":material/rocket_launch: Lancer la transcription du lot", key="btn_launch_batch", type="primary", use_container_width=True):
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
                                "export_md": export_md,
                                "language": st.session_state.get("selected_language"),
                                "task": st.session_state.get("selected_task", "transcribe"),
                                "initial_prompt": st.session_state.get("initial_prompt"),
                                "vad_filter": st.session_state.get("use_vad", True),
                                "diarize": st.session_state.get("use_diarization", False),
                                "num_speakers": st.session_state.get("num_speakers")
                            }
                        )
                        add_script_run_ctx(t)
                        t.start()
                        st.rerun()
                else:
                    st.warning("Aucun fichier vidéo ou audio supporté trouvé dans ce répertoire.")
            elif st.session_state.target_folder:
                st.error("Le dossier spécifié n'existe pas ou n'est pas accessible.")

        # --- MODE 2 : FICHIER UNIQUE ---
        else:
            st.markdown("### :material/description: Importer un enregistrement individuel")
            uploaded_file = st.file_uploader(
                "Glissez-déposez votre fichier ici",
                type=["mp3", "wav", "m4a", "ogg", "flac", "mp4", "mkv", "mov"]
            )
            
            if uploaded_file:
                col_info1, col_info2, col_info3 = st.columns(3)
                file_size_mb = uploaded_file.size / (1024 * 1024)
                with col_info1:
                    ui.metric_card(label="Fichier", value=uploaded_file.name[:15]+"...", description="Fichier source")
                with col_info2:
                    ui.metric_card(label="Taille", value=f"{file_size_mb:.2f} MB", description="Poids du fichier")
                with col_info3:
                    ui.metric_card(label="Modèle Actif", value=st.session_state.selected_model, description="faster-whisper")
                    
                st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
                if st.button(":material/rocket_launch: Démarrer la transcription", key="btn_launch_single", type="primary", use_container_width=True):
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
                            "model_size": st.session_state.selected_model,
                            "language": st.session_state.get("selected_language"),
                            "task": st.session_state.get("selected_task", "transcribe"),
                            "initial_prompt": st.session_state.get("initial_prompt"),
                            "vad_filter": st.session_state.get("use_vad", True),
                            "diarize": st.session_state.get("use_diarization", False),
                            "num_speakers": st.session_state.get("num_speakers")
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
            st.markdown("<div style='margin-top: 1.6rem;'></div>", unsafe_allow_html=True)
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
            elif status == "info_detected":
                st.session_state.detected_language = msg.get("language")
                st.session_state.language_probability = msg.get("language_probability")
                st.session_state.executed_task = msg.get("task", "transcribe")
                lang_disp = SUPPORTED_LANGUAGES.get(msg.get("language", ""), msg.get("language", "").upper())
                st.session_state.status_label = f"Langue : {lang_disp} ({msg.get('language_probability', 100)}%)"
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
            elif status == "diarizing":
                st.session_state.status_label = msg.get("message", "🗣️ Identification des locuteurs...")
            elif status == "file_complete":
                if not is_batch:
                    st.session_state.is_processing = False
                    st.session_state.transcription_done = True
                    st.session_state.progress_pct = 100
                    if msg.get("language"):
                        st.session_state.detected_language = msg.get("language")
                    if msg.get("language_probability") is not None:
                        st.session_state.language_probability = msg.get("language_probability")
                    if msg.get("task"):
                        st.session_state.executed_task = msg.get("task")
                    st.session_state.detected_speakers = msg.get("speakers", [])
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
                
        # Aperçu en direct du texte retranscrit
        if st.session_state.latest_text:
            st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
            st.markdown("##### Flux retranscrit en direct :")
            preview = st.session_state.latest_text[-400:]
            st.markdown(f"""
            <div style="background: #09090b; border: 1px solid #27272a; border-radius: 8px; padding: 1rem; font-family: 'Consolas', 'Courier New', monospace; color: #10b981; font-size: 0.85rem; line-height: 1.5; min-height: 120px; box-shadow: inset 0 0 10px rgba(0,0,0,0.5);">
                <span style="color: #64748b;">$ whisper --model {st.session_state.get('selected_model', 'medium')}</span><br><br>
                ... {preview}<span style="animation: blink 1s step-end infinite;">_</span>
            </div>
            <style>
                @keyframes blink {{ 50% {{ opacity: 0; }} }}
            </style>
            """, unsafe_allow_html=True)
            
        time.sleep(0.3)
        st.rerun()

    # =========================================================================
    # VUE 3 : Résultats et Exports
    # =========================================================================
    elif st.session_state.transcription_done:
        is_batch = st.session_state.get("is_batch", False)
        
        if is_batch:
            stats = st.session_state.get("batch_stats", {})
            st.success(":material/celebration: Transcription du dossier terminée avec succès !")
            
            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                ui.metric_card(label="Total Analysé", value=str(stats.get("total", 0)), description="Vidéos dans l'arborescence")
            with col_b2:
                ui.metric_card(label="Nouvellement Transcrites", value=str(stats.get("processed", 0)), description="Fichiers .txt générés in-place")
            with col_b3:
                ui.metric_card(label="Déjà Existantes", value=str(stats.get("skipped", 0)), description="Ignorées (Smart Resume)")
                
            st.markdown("<div style='margin-top: 1.25rem;'></div>", unsafe_allow_html=True)
            folder_path = Path(st.session_state.target_folder)
            st.markdown(f"Tous les fichiers **`.txt`** ont été enregistrés directement à côté de chaque vidéo dans :  \n`{folder_path.resolve()}`")
            
            if st.button(":material/folder_open: Ouvrir le dossier dans l'explorateur Windows", type="primary"):
                open_folder_in_explorer(folder_path)
                
            st.markdown("<hr style='margin: 1.5rem 0; border: none; border-top: 1px solid #27272a;'>", unsafe_allow_html=True)
            if st.button(":material/sync: Traiter un autre dossier", use_container_width=True):
                st.session_state.transcription_done = False
                st.session_state.is_processing = False
                st.session_state.latest_text = ""
                st.rerun()
        else:
            st.success(":material/celebration: Transcription terminée avec succès !")
            file_path = st.session_state.current_file
            out_dir = st.session_state.output_dir
            base_name = file_path.stem
            txt_file = out_dir / f"{base_name}.txt"
            md_file = out_dir / f"{base_name}.md"
            srt_file = out_dir / f"{base_name}.srt"
            
            txt_text = txt_file.read_text(encoding="utf-8") if txt_file.exists() else ""
            md_text = md_file.read_text(encoding="utf-8") if md_file.exists() else ""
            srt_text = srt_file.read_text(encoding="utf-8") if srt_file.exists() else ""

            # Résumé des métriques IA et audio
            speakers = st.session_state.get("detected_speakers", [])
            lang_code = st.session_state.get("detected_language", "auto")
            lang_label = SUPPORTED_LANGUAGES.get(lang_code, lang_code.upper() if lang_code else "AUTO")
            prob_val = st.session_state.get("language_probability", 100.0)
            task_type = "Traduction (EN)" if st.session_state.get("executed_task") == "translate" else "Transcription"

            if speakers:
                col_res1, col_res2, col_res3, col_res4 = st.columns(4)
                with col_res1:
                    ui.metric_card(label="Langue Identifiée", value=lang_label, description=f"Confiance : {prob_val}%")
                with col_res2:
                    ui.metric_card(label="Tâche Réalisée", value=task_type, description=f"VAD: {'Actif' if st.session_state.get('use_vad', True) else 'Inactif'}")
                with col_res3:
                    ui.metric_card(label="Modèle Whisper", value=st.session_state.get("selected_model", "medium"), description="faster-whisper local")
                with col_res4:
                    ui.metric_card(label="Locuteurs", value=f"{len(speakers)} voix", description=", ".join(speakers[:2]))
            else:
                col_res1, col_res2, col_res3 = st.columns(3)
                with col_res1:
                    ui.metric_card(label="Langue Identifiée", value=lang_label, description=f"Confiance : {prob_val}%")
                with col_res2:
                    ui.metric_card(label="Tâche Réalisée", value=task_type, description=f"VAD: {'Actif' if st.session_state.get('use_vad', True) else 'Inactif'}")
                with col_res3:
                    ui.metric_card(label="Modèle Whisper", value=st.session_state.get("selected_model", "medium"), description="faster-whisper local")

            st.markdown("<div style='margin-top: 1.25rem;'></div>", unsafe_allow_html=True)

            # Option interactive : personnalisation des locuteurs
            if speakers:
                with st.expander("👥 Personnaliser les noms des locuteurs", expanded=False):
                    st.markdown("<p style='font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.5rem;'>Attribuez les vrais prénoms des intervenants (ex: <em>Alice</em>, <em>Bob</em>) pour mettre à jour tous les exports instantanément.</p>", unsafe_allow_html=True)
                    renames = {}
                    cols_spk = st.columns(min(len(speakers), 4))
                    for i, spk in enumerate(speakers):
                        with cols_spk[i % 4]:
                            renames[spk] = st.text_input(
                                f"Nom pour {spk} :", 
                                value=st.session_state.get(f"rename_{spk}", spk),
                                key=f"rename_input_{spk}"
                            )
                    
                    if st.button("💾 Appliquer les noms aux fichiers", key="btn_apply_renames"):
                        for old_name, new_name in renames.items():
                            clean_new = new_name.strip()
                            if clean_new and clean_new != old_name:
                                txt_text = txt_text.replace(f"[{old_name}]", f"[{clean_new}]")
                                srt_text = srt_text.replace(f"[{old_name}]", f"[{clean_new}]")
                                md_text = md_text.replace(f"**{old_name}**", f"**{clean_new}**")
                                md_text = md_text.replace(f'"{old_name}"', f'"{clean_new}"')
                                st.session_state[f"rename_{old_name}"] = clean_new
                        txt_file.write_text(txt_text, encoding="utf-8")
                        md_file.write_text(md_text, encoding="utf-8")
                        srt_file.write_text(srt_text, encoding="utf-8")
                        st.success("Tous les fichiers et aperçus ont été mis à jour !")
                        st.rerun()
                
            st.markdown("<div style='margin-top: 1.25rem;'></div>", unsafe_allow_html=True)
            
            # Barre d'actions rapides (Copie & Téléchargement immédiat)
            col_act_cp, col_act_dl = st.columns([1, 1])
            with col_act_cp:
                if st.button("📋 Copier dans le presse-papier", type="primary", use_container_width=True, key="btn_copy_quick_main", help="Copier l'intégralité du texte transcrit en un seul clic"):
                    if copy_to_clipboard(txt_text):
                        st.toast("Transcription copiée dans le presse-papier !", icon="📋")
                    else:
                        st.error("Impossible d'accéder au presse-papier.")
            with col_act_dl:
                st.download_button(
                    label=":material/download: Télécharger le texte (.txt)",
                    data=txt_text,
                    file_name=f"{base_name}.txt",
                    mime="text/plain",
                    use_container_width=True,
                    key="btn_dl_quick_main"
                )
            
            st.markdown("<div style='margin-top: 0.75rem;'></div>", unsafe_allow_html=True)
            
            # Onglets élégants Linear / Shadcn
            tab_txt, tab_md, tab_srt, tab_llm = st.tabs([
                ":material/description: Texte Brut (.txt)", 
                ":material/markdown: Markdown (.md)", 
                "⏱️ Sous-titres (.srt)", 
                "🤖 Prompts LLM"
            ])
            
            with tab_txt:
                col_t_dl, col_t_cp = st.columns([1, 1])
                with col_t_dl:
                    st.download_button(
                        label=":material/download: Télécharger le fichier texte (.txt)",
                        data=txt_text,
                        file_name=f"{base_name}.txt",
                        mime="text/plain",
                        use_container_width=True,
                        key="dl_btn_tab_txt"
                    )
                with col_t_cp:
                    if st.button("📋 Copier le texte brut", key="btn_copy_tab_txt", use_container_width=True):
                        if copy_to_clipboard(txt_text):
                            st.toast("Texte brut copié dans le presse-papier !", icon="📋")
                st.text_area("Transcription brute :", value=txt_text, height=350)
                
            with tab_md:
                col_m_dl, col_m_cp = st.columns([1, 1])
                with col_m_dl:
                    st.download_button(
                        label=":material/download: Télécharger le Markdown (.md)",
                        data=md_text,
                        file_name=f"{base_name}.md",
                        mime="text/markdown",
                        use_container_width=True,
                        key="dl_btn_tab_md"
                    )
                with col_m_cp:
                    if st.button("📋 Copier le Markdown", key="btn_copy_tab_md", use_container_width=True):
                        if copy_to_clipboard(md_text):
                            st.toast("Markdown copié dans le presse-papier !", icon="📋")
                st.markdown(md_text)
                
            with tab_srt:
                col_s_dl, col_s_cp = st.columns([1, 1])
                with col_s_dl:
                    st.download_button(
                        label=":material/download: Télécharger les Sous-titres (.srt)",
                        data=srt_text,
                        file_name=f"{base_name}.srt",
                        mime="text/plain",
                        use_container_width=True,
                        key="dl_btn_tab_srt"
                    )
                with col_s_cp:
                    if st.button("📋 Copier les sous-titres", key="btn_copy_tab_srt", use_container_width=True):
                        if copy_to_clipboard(srt_text):
                            st.toast("Sous-titres copiés dans le presse-papier !", icon="📋")
                st.code(srt_text, language="text")
                
            with tab_llm:
                render_llm_templates(transcription_text=txt_text)
                
            st.markdown("<hr style='margin: 2rem 0; border: none; border-top: 1px solid rgba(46, 116, 253, 0.15);'>", unsafe_allow_html=True)
            if st.button(":material/sync: Nouvelle transcription", use_container_width=True):
                st.session_state.transcription_done = False
                st.session_state.is_processing = False
                st.session_state.latest_text = ""
                st.rerun()

if __name__ == "__main__":
    main()
