"""
LocalScribe — Interface Utilisateur Haute Fidélité (Design System Épuré).
Assorti au logo : Noir Obsidienne (#05070e) & Bleu Électrique (#2e74fd).
"""

import io
import os
import sys
import time
import queue
import zipfile
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
from core.translation_engine import (
    SUPPORTED_TRANSLATION_LANGUAGES,
    is_translation_model_installed,
    ensure_translation_model,
    get_translation_engine,
    resolve_nllb_code
)
from core.transcription_engine import (
    transcribe_file_threaded, 
    transcribe_batch_threaded, 
    SUPPORTED_EXTENSIONS,
    SUPPORTED_LANGUAGES
)
from core.text_formatter import TranscriptionSegment, parse_srt
from core.audio_preprocessor import is_ffmpeg_available
from core.eta_calculator import format_friendly_duration
from core.notifications import notify_transcription_complete, notify_batch_complete
from ui.editor_component import render_editor_tab

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

def create_batch_zip(files_list: list) -> bytes:
    """Génère une archive ZIP en mémoire contenant tous les fichiers d'export du lot (originaux et traduits)."""
    if not files_list:
        return b""
    try:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files_list:
                for key in (
                    "txt_path", "srt_path", "md_path",
                    "translated_txt_path", "translated_srt_path", "translated_md_path"
                ):
                    p_str = f.get(key)
                    if p_str:
                        p = Path(p_str)
                        if p.exists() and p.is_file():
                            zf.write(p, arcname=p.name)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception:
        return b""

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

        # 6. Traduction Multilingue Hors-Ligne (NLLB-200)
        st.markdown("<hr style='margin: 1rem 0; border: none; border-top: 1px solid #27272a;'>", unsafe_allow_html=True)
        st.markdown("##### 🌐 Traduction Hors-Ligne (NLLB-200)")
        
        trans_options = ["Désactivée (langue originale)"] + [
            f"{d['flag']} {d['name']}" for d in SUPPORTED_TRANSLATION_LANGUAGES.values()
        ]
        chosen_trans = st.selectbox(
            "Traduire automatiquement vers :",
            options=trans_options,
            index=0,
            help="Traduction neuronale 100% hors-ligne via Meta NLLB-200. Génère des fichiers traduits synchronisés (.txt, .srt, .md)."
        )
        
        target_trans_code = None
        if chosen_trans != "Désactivée (langue originale)":
            for c, d in SUPPORTED_TRANSLATION_LANGUAGES.items():
                if d["name"] in chosen_trans:
                    target_trans_code = c
                    break
        st.session_state.target_translation_code = target_trans_code
        
        model_ready = is_translation_model_installed()
        if model_ready:
            st.markdown(
                render_badge("✅ Modèle NLLB-200 prêt", color="#34d399", bg="rgba(52, 211, 153, 0.1)"), 
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                render_badge("⚠️ Modèle non téléchargé", color="#f59e0b", bg="rgba(245, 158, 11, 0.1)"), 
                unsafe_allow_html=True
            )
            if st.button("📥 Télécharger NLLB-200 (622 Mo)", key="btn_dl_nllb_sidebar", use_container_width=True):
                with st.spinner("Téléchargement du modèle de traduction en cours (622 Mo)..."):
                    try:
                        ensure_translation_model()
                        st.success("Modèle téléchargé avec succès !")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur de téléchargement : {e}")

        # 7. Prétraitement Acoustique & FFmpeg
        st.markdown("<hr style='margin: 1.25rem 0; border: none; border-top: 1px solid #27272a;'>", unsafe_allow_html=True)
        st.markdown("### ⚡ Prétraitement Acoustique")
        
        ffmpeg_ok = is_ffmpeg_available()
        if ffmpeg_ok:
            st.markdown(
                render_badge("⚡ FFmpeg Détecté", color="#34d399", bg="rgba(52, 211, 153, 0.1)"),
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                render_badge("ℹ️ Repli direct (FFmpeg absent)", color="#94a3b8", bg="rgba(148, 163, 184, 0.1)"),
                unsafe_allow_html=True
            )

        normalize_vol = st.checkbox(
            "🔊 Normaliser le volume (Auto-Gain)",
            value=True,
            help="Égalise dynamiquement le volume sonore pour rehausser les voix faibles, chuchotées ou lointaines sans distorsion (filtre broadcast dynaudnorm)."
        )
        st.session_state.normalize_volume = normalize_vol

        denoise_audio = st.checkbox(
            "🧹 Réduire le bruit de fond (Denoising)",
            value=False,
            help="Filtre les bruits sourds de ventilation (HVAC) et sifflements de micro via des filtres passe-bande et suppression spectrale."
        )
        st.session_state.denoise_audio = denoise_audio
        st.session_state.preprocess_audio = normalize_vol or denoise_audio

        # 8. Notifications & Alertes Bureau
        st.markdown("<hr style='margin: 1rem 0; border: none; border-top: 1px solid #27272a;'>", unsafe_allow_html=True)
        st.markdown("##### 🔔 Notifications & Alertes")
        enable_notif = st.checkbox(
            "🔔 Notification bureau (Toast Windows)",
            value=True,
            help="Affiche une notification native dans le centre de notifications Windows à la fin du traitement."
        )
        st.session_state.enable_notifications = enable_notif

        enable_chime = st.checkbox(
            "🔊 Alerte sonore discrète",
            value=True,
            help="Émet un carillon système Windows discret à la fin de la transcription."
        )
        st.session_state.enable_chime = enable_chime

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

            # Éditeur interactif & Synchronisation pour l'historique
            with st.expander("✏️ Éditer & Synchroniser cette transcription...", expanded=False):
                h_file_path = Path(rec["filepath"]) if rec.get("filepath") else None
                h_out_dir = Path(rec["txt_path"]).parent if rec.get("txt_path") else Path(".")
                h_base_name = Path(filename).stem
                
                h_seg_key = f"hist_segs_{rec_id}"
                if h_seg_key not in st.session_state:
                    if rec.get("segments"):
                        st.session_state[h_seg_key] = [
                            TranscriptionSegment.from_dict(s) for s in rec["segments"]
                        ]
                    elif rec.get("srt_path") and Path(rec["srt_path"]).exists():
                        st.session_state[h_seg_key] = parse_srt(Path(rec["srt_path"]).read_text(encoding="utf-8"))
                    else:
                        st.session_state[h_seg_key] = []
                
                st.session_state.result_segments = st.session_state[h_seg_key]
                render_editor_tab(
                    file_path=h_file_path,
                    output_dir=h_out_dir,
                    base_name=h_base_name,
                    record_id=rec_id
                )

            # Traduction à la demande pour l'historique
            with st.expander("🌐 Traduire cet enregistrement...", expanded=False):
                if not is_translation_model_installed():
                    st.info("Modèle NLLB-200 non installé. Téléchargez-le dans la barre latérale pour activer la traduction.")
                else:
                    col_ht_tgt, col_ht_btn = st.columns([3, 1])
                    with col_ht_tgt:
                        h_trans_labels = [f"{d['flag']} {d['name']}" for d in SUPPORTED_TRANSLATION_LANGUAGES.values()]
                        h_trans_codes = list(SUPPORTED_TRANSLATION_LANGUAGES.keys())
                        chosen_h_label = st.selectbox("Langue cible :", options=h_trans_labels, index=1, key=f"sb_h_tgt_{rec_id}")
                        chosen_h_code = h_trans_codes[h_trans_labels.index(chosen_h_label)]
                    with col_ht_btn:
                        st.markdown("<div style='margin-top: 1.6rem;'></div>", unsafe_allow_html=True)
                        run_h_trans = st.button("🌐 Traduire", key=f"btn_h_tr_{rec_id}", use_container_width=True)
                        
                    h_tr_key = f"hist_tr_{rec_id}_{chosen_h_code}"
                    if run_h_trans:
                        with st.spinner("Traduction hors-ligne en cours..."):
                            try:
                                engine = get_translation_engine()
                                src_lang_rec = rec.get("language") or "auto"
                                h_res = engine.translate_text(txt_content, src_lang=src_lang_rec, tgt_lang=chosen_h_code)
                                st.session_state[h_tr_key] = h_res
                                st.toast(f"Traduit vers {chosen_h_label} !", icon="🌐")
                            except Exception as e:
                                st.error(f"Erreur de traduction : {e}")
                    if st.session_state.get(h_tr_key):
                        st.text_area(f"Résultat ({chosen_h_label}) :", value=st.session_state[h_tr_key], height=120, key=f"ta_h_res_{rec_id}")
                        col_h_cp, col_h_dl = st.columns(2)
                        with col_h_cp:
                            if st.button("📋 Copier", key=f"btn_h_cp_{rec_id}", use_container_width=True):
                                if copy_to_clipboard(st.session_state[h_tr_key]):
                                    st.toast("Copié !", icon="📋")
                        with col_h_dl:
                            st.download_button(
                                "⬇️ .txt Traduit",
                                data=st.session_state[h_tr_key],
                                file_name=f"{Path(filename).stem}_{chosen_h_code}.txt",
                                mime="text/plain",
                                key=f"dl_h_tr_{rec_id}",
                                use_container_width=True
                            )


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
    if "speed_str" not in st.session_state:
        st.session_state.speed_str = "—"
    if "eta_str" not in st.session_state:
        st.session_state.eta_str = "Calcul..."
    if "elapsed_str" not in st.session_state:
        st.session_state.elapsed_str = "00:00"
    if "batch_eta_str" not in st.session_state:
        st.session_state.batch_eta_str = "Calcul..."
    if "batch_elapsed_str" not in st.session_state:
        st.session_state.batch_elapsed_str = "00:00"

    import streamlit_shadcn_ui as ui

    # Sélecteur de Mode Segmenté moderne
    mode_selection = st.segmented_control(
        "Mode de transcription",
        options=[
            ":material/upload_file: File d'attente (Multi-Fichiers)", 
            ":material/folder: Mode Dossier (Scan Récursif)",
            ":material/history: Historique & Bibliothèque"
        ],
        default=":material/upload_file: File d'attente (Multi-Fichiers)",
        selection_mode="single",
        label_visibility="collapsed",
        key="mode_segmented_control"
    )
    if not mode_selection:
        mode_selection = ":material/upload_file: File d'attente (Multi-Fichiers)"
    is_folder_mode = "Dossier" in mode_selection
    is_history_mode = "Historique" in mode_selection

    # =========================================================================
    # VUE 1 : Configuration et Lancement / Bibliothèque
    # =========================================================================
    if not st.session_state.is_processing and not st.session_state.transcription_done:
        
        # --- MODE 0 : HISTORIQUE & BIBLIOTHÈQUE ---
        if is_history_mode:
            render_history_view()

        # --- MODE 1 : DOSSIER COMPLET (SCAN RÉCURSIF IN-PLACE) ---
        elif is_folder_mode:
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
                        st.session_state.is_queue_batch = False
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
                                "num_speakers": st.session_state.get("num_speakers"),
                                "target_translation": st.session_state.get("target_translation_code"),
                                "preprocess_audio": st.session_state.get("preprocess_audio", True),
                                "normalize_volume": st.session_state.get("normalize_volume", True),
                                "denoise": st.session_state.get("denoise_audio", False)
                            }
                        )
                        add_script_run_ctx(t)
                        t.start()
                        st.rerun()
                else:
                    st.warning("Aucun fichier vidéo ou audio supporté trouvé dans ce répertoire.")
            elif st.session_state.target_folder:
                st.error("Le dossier spécifié n'existe pas ou n'est pas accessible.")

        # --- MODE 2 : FILE D'ATTENTE MULTI-FICHIERS (DRAG & DROP) ---
        else:
            st.markdown("### :material/upload_file: File d'attente de fichiers (Glisser-Déposer)")
            st.markdown("""
            <div style="background: #18181b; border: 1px solid #27272a; border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: 1.25rem;">
                <div style="color: #e2e8f0; font-size: 0.92rem; line-height: 1.5;">
                    Glissez-déposez <strong>1, 5, 10 fichiers ou plus d'un coup</strong> ci-dessous. 
                    LocalScribe va traiter l'ensemble des fichiers <strong>à la chaîne en arrière-plan</strong> 
                    avec le modèle Whisper chargé en mémoire une seule fois.
                </div>
            </div>
            """, unsafe_allow_html=True)

            uploaded_files = st.file_uploader(
                "Glissez-déposez vos fichiers ici (sélection multiple supportée) :",
                type=["mp3", "wav", "m4a", "ogg", "flac", "mp4", "mkv", "mov", "avi", "webm"],
                accept_multiple_files=True
            )
            
            if uploaded_files:
                total_mb = sum(f.size for f in uploaded_files) / (1024 * 1024)
                col_info1, col_info2, col_info3 = st.columns(3)
                with col_info1:
                    ui.metric_card(
                        label="Fichiers en File", 
                        value=f"{len(uploaded_files)} fichier(s)", 
                        description="Prêts pour traitement"
                    )
                with col_info2:
                    ui.metric_card(
                        label="Taille Cumulée", 
                        value=f"{total_mb:.1f} MB", 
                        description="Poids total des médias"
                    )
                with col_info3:
                    ui.metric_card(
                        label="Modèle Whisper", 
                        value=st.session_state.selected_model, 
                        description="faster-whisper local"
                    )
                    
                st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
                with st.expander(f"📋 Liste des {len(uploaded_files)} fichier(s) en attente", expanded=(len(uploaded_files) <= 5)):
                    for idx, f in enumerate(uploaded_files, start=1):
                        f_mb = f.size / (1024 * 1024)
                        st.markdown(f"**{idx}.** `{f.name}` — *{f_mb:.2f} MB*")

                st.markdown("<div style='margin-top: 1.25rem;'></div>", unsafe_allow_html=True)
                st.markdown("##### :material/settings: Options de sortie pour la file :")
                col_o1, col_o2, col_o3 = st.columns(3)
                with col_o1:
                    st.checkbox(":material/description: Texte brut (.txt)", value=True, disabled=True, key="chk_q_txt")
                with col_o2:
                    queue_export_srt = st.checkbox("⏱️ Sous-titres (.srt)", value=True, key="chk_q_srt")
                with col_o3:
                    queue_export_md = st.checkbox(":material/markdown: Markdown (.md)", value=True, key="chk_q_md")

                st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
                btn_label = (
                    ":material/rocket_launch: Démarrer la transcription (1 fichier)"
                    if len(uploaded_files) == 1
                    else f":material/rocket_launch: Lancer la file d'attente ({len(uploaded_files)} fichiers)"
                )
                
                if st.button(btn_label, key="btn_launch_queue", type="primary", use_container_width=True):
                    saved_paths = [save_uploaded_file(f) for f in uploaded_files]
                    output_dir = PROJECT_ROOT / "output"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    
                    st.session_state.progress_queue = queue.Queue()
                    st.session_state.stop_event = threading.Event()
                    st.session_state.output_dir = output_dir
                    st.session_state.is_processing = True
                    st.session_state.progress_pct = 0
                    st.session_state.status_label = "Initialisation..."
                    st.session_state.latest_text = ""
                    
                    if len(saved_paths) == 1:
                        st.session_state.is_batch = False
                        st.session_state.is_queue_batch = False
                        st.session_state.current_file = saved_paths[0]
                        t = threading.Thread(
                            target=transcribe_file_threaded,
                            kwargs={
                                "file_path": saved_paths[0],
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
                                "num_speakers": st.session_state.get("num_speakers"),
                                "target_translation": st.session_state.get("target_translation_code"),
                                "preprocess_audio": st.session_state.get("preprocess_audio", True),
                                "normalize_volume": st.session_state.get("normalize_volume", True),
                                "denoise": st.session_state.get("denoise_audio", False)
                            }
                        )
                    else:
                        st.session_state.is_batch = True
                        st.session_state.is_queue_batch = True
                        st.session_state.total_batch_files = len(saved_paths)
                        st.session_state.current_file_idx = 1
                        st.session_state.current_file_name = saved_paths[0].name
                        t = threading.Thread(
                            target=transcribe_batch_threaded,
                            kwargs={
                                "files": saved_paths,
                                "output_dir": output_dir,
                                "profile": st.session_state.hw_profile,
                                "progress_queue": st.session_state.progress_queue,
                                "stop_event": st.session_state.stop_event,
                                "model_size": st.session_state.selected_model,
                                "export_srt": queue_export_srt,
                                "export_md": queue_export_md,
                                "language": st.session_state.get("selected_language"),
                                "task": st.session_state.get("selected_task", "transcribe"),
                                "initial_prompt": st.session_state.get("initial_prompt"),
                                "vad_filter": st.session_state.get("use_vad", True),
                                "diarize": st.session_state.get("use_diarization", False),
                                "num_speakers": st.session_state.get("num_speakers"),
                                "target_translation": st.session_state.get("target_translation_code"),
                                "preprocess_audio": st.session_state.get("preprocess_audio", True),
                                "normalize_volume": st.session_state.get("normalize_volume", True),
                                "denoise": st.session_state.get("denoise_audio", False)
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
                current_idx = st.session_state.get("current_file_idx", 1)
                total_files = st.session_state.get("total_batch_files", 1)
                file_name = st.session_state.get("current_file_name", "")
                file_pct = int(st.session_state.get("progress_pct", 0))
                
                # Progression globale prenant en compte les fichiers terminés + l'avancement du fichier en cours
                overall_progress = min(100, int((((current_idx - 1) + (file_pct / 100.0)) / total_files) * 100)) if total_files > 0 else 0
                st.markdown(f"**Progression globale : Fichier {current_idx} / {total_files}** ({overall_progress}%)")
                st.progress(overall_progress)
                
                st.markdown(f"Fichier en cours : `{file_name}` ({file_pct}%)")
                st.progress(file_pct)

                # Bandeau d'estimation dynamique en lot (Vitesse, ETA fichier, ETA lot)
                speed_txt = st.session_state.get("speed_str", "—")
                file_eta_txt = st.session_state.get("eta_str", "Calcul...")
                batch_eta_txt = st.session_state.get("batch_eta_str", "Calcul...")
                batch_elapsed_txt = st.session_state.get("batch_elapsed_str", "00:00")
                
                batch_badge_html = f"""
                <div style="display: flex; flex-wrap: wrap; gap: 1.25rem; align-items: center; background: #18181b; border: 1px solid #27272a; border-radius: 8px; padding: 0.5rem 0.85rem; margin-top: 0.5rem; font-size: 0.84rem;">
                    <div>⚡ Vitesse : <span style="color: #38bdf8; font-weight: 600;">{speed_txt}</span></div>
                    <div>⏱️ Écoulé total : <span style="color: #cbd5e1; font-weight: 600;">{batch_elapsed_txt}</span></div>
                    <div>⏳ Fichier en cours : <span style="color: #facc15; font-weight: 600;">{file_eta_txt}</span></div>
                    <div>📦 Lot restant (ETA) : <span style="color: #34d399; font-weight: 600;">{batch_eta_txt}</span></div>
                </div>
                """
                st.markdown(batch_badge_html, unsafe_allow_html=True)
            else:
                progress_val = int(st.session_state.get("progress_pct", 0))
                st.progress(progress_val)

                # Bandeau d'estimation dynamique mono-fichier
                speed_txt = st.session_state.get("speed_str", "—")
                eta_txt = st.session_state.get("eta_str", "Calcul...")
                elapsed_txt = st.session_state.get("elapsed_str", "00:00")

                eta_badge_html = f"""
                <div style="display: flex; flex-wrap: wrap; gap: 1.25rem; align-items: center; background: #18181b; border: 1px solid #27272a; border-radius: 8px; padding: 0.5rem 0.85rem; margin-top: 0.5rem; font-size: 0.84rem;">
                    <div>⚡ Vitesse : <span style="color: #38bdf8; font-weight: 600;">{speed_txt}</span></div>
                    <div>⏱️ Temps écoulé : <span style="color: #cbd5e1; font-weight: 600;">{elapsed_txt}</span></div>
                    <div>⏳ Temps restant estimé (ETA) : <span style="color: #34d399; font-weight: 600;">{eta_txt}</span></div>
                </div>
                """
                st.markdown(eta_badge_html, unsafe_allow_html=True)
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
                st.session_state.speed_str = "—"
                st.session_state.eta_str = "Calcul..."
            elif status == "file_skipped":
                st.session_state.current_file_idx = msg.get("current_idx", 1)
            elif status == "progress":
                st.session_state.progress_pct = int(msg.get("percentage", 0))
                st.session_state.current_file_name = msg.get("file_name", st.session_state.get("current_file_name", ""))
                st.session_state.current_file_idx = msg.get("current_idx", st.session_state.get("current_file_idx", 1))
                st.session_state.latest_text += " " + msg.get("segment_text", "")
                st.session_state.speed_str = msg.get("speed_str", "—")
                st.session_state.eta_str = msg.get("eta_str", "Calcul...")
                st.session_state.elapsed_str = msg.get("elapsed_str", "00:00")
                if is_batch:
                    st.session_state.batch_eta_str = msg.get("batch_eta_str", "Calcul...")
                    st.session_state.batch_elapsed_str = msg.get("batch_elapsed_str", "00:00")
            elif status == "preprocessing":
                st.session_state.status_label = msg.get("message", "⚡ Prétraitement acoustique en cours...")
            elif status == "diarizing":
                st.session_state.status_label = msg.get("message", "🗣️ Identification des locuteurs...")
            elif status == "translating":
                st.session_state.status_label = msg.get("message", "🌐 Traduction neuronale hors-ligne...")
            elif status == "file_complete":
                if not is_batch:
                    st.session_state.is_processing = False
                    st.session_state.transcription_done = True
                    st.session_state.progress_pct = 100
                    st.session_state.is_preprocessed = msg.get("preprocessed", False)
                    st.session_state.last_elapsed_seconds = msg.get("elapsed_seconds")
                    st.session_state.last_audio_duration = msg.get("duration")
                    if msg.get("language"):
                        st.session_state.detected_language = msg.get("language")
                    if msg.get("language_probability") is not None:
                        st.session_state.language_probability = msg.get("language_probability")
                    if msg.get("task"):
                        st.session_state.executed_task = msg.get("task")
                    st.session_state.detected_speakers = msg.get("speakers", [])
                    st.session_state.translated_text = msg.get("translated_text", "")
                    st.session_state.translated_txt_path = msg.get("translated_txt_path", "")
                    st.session_state.translated_srt_path = msg.get("translated_srt_path", "")
                    st.session_state.translated_md_path = msg.get("translated_md_path", "")
                    st.session_state.active_target_translation = msg.get("target_translation", None)
                    if msg.get("segments"):
                        st.session_state.result_segments = [
                            TranscriptionSegment.from_dict(s) for s in msg["segments"]
                        ]
                    else:
                        st.session_state.result_segments = []

                    # Notification système native Windows Toast
                    if st.session_state.get("enable_notifications", True):
                        try:
                            notify_transcription_complete(
                                filename=Path(msg.get("file", "")).name,
                                elapsed_seconds=msg.get("elapsed_seconds"),
                                audio_duration=msg.get("duration"),
                                sound=st.session_state.get("enable_chime", True)
                            )
                        except Exception:
                            pass

                    st.rerun()
            elif status == "batch_complete":
                st.session_state.is_processing = False
                st.session_state.transcription_done = True
                total_el = msg.get("total_elapsed_seconds", 0.0)
                st.session_state.batch_stats = {
                    "total": msg.get("total_files", 0),
                    "processed": msg.get("processed", 0),
                    "skipped": msg.get("skipped", 0),
                    "files": msg.get("files", []),
                    "total_elapsed_seconds": total_el
                }

                # Notification de lot Windows Toast
                if st.session_state.get("enable_notifications", True):
                    try:
                        notify_batch_complete(
                            total_files=msg.get("processed", 0),
                            elapsed_seconds=total_el,
                            sound=st.session_state.get("enable_chime", True)
                        )
                    except Exception:
                        pass

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
            completed_files = stats.get("files", [])
            is_queue = st.session_state.get("is_queue_batch", False)
            
            if is_queue:
                st.success(":material/celebration: File d'attente multi-fichiers traitée avec succès !")
            else:
                st.success(":material/celebration: Transcription du dossier terminée avec succès !")
            
            col_b1, col_b2, col_b3, col_b4 = st.columns(4)
            with col_b1:
                ui.metric_card(
                    label="Total Analysé", 
                    value=str(stats.get("total", len(completed_files))), 
                    description="Fichiers traités dans la file" if is_queue else "Vidéos dans l'arborescence"
                )
            with col_b2:
                ui.metric_card(
                    label="Nouvellement Transcrites", 
                    value=str(stats.get("processed", len(completed_files))), 
                    description="Transcriptions générées"
                )
            with col_b3:
                ui.metric_card(
                    label="Déjà Existantes", 
                    value=str(stats.get("skipped", 0)), 
                    description="Ignorées (Smart Resume)"
                )
            with col_b4:
                b_tot = stats.get("total_elapsed_seconds")
                b_val = format_friendly_duration(b_tot) if b_tot else "—"
                ui.metric_card(
                    label="Temps de calcul",
                    value=b_val,
                    description="Durée réelle du lot"
                )
                
            st.markdown("<div style='margin-top: 1.25rem;'></div>", unsafe_allow_html=True)
            
            # Détermination du dossier de destination
            if not is_queue and st.session_state.get("target_folder"):
                dest_dir = Path(st.session_state.target_folder)
                st.markdown(f"Tous les fichiers ont été enregistrés directement dans :  \n`{dest_dir.resolve()}`")
            else:
                dest_dir = st.session_state.get("output_dir", PROJECT_ROOT / "output")
                st.markdown(f"Tous les fichiers d'export ont été enregistrés dans :  \n`{dest_dir.resolve()}`")

            # --- BARRE D'ACTIONS RAPIDES GLOBALES ---
            col_act1, col_act2, col_act3 = st.columns([1, 1, 1])
            with col_act1:
                if st.button(":material/folder_open: Ouvrir le dossier", type="secondary", use_container_width=True, key="btn_open_batch_dir"):
                    open_folder_in_explorer(dest_dir)
            
            with col_act2:
                zip_data = create_batch_zip(completed_files)
                if zip_data:
                    st.download_button(
                        label="📦 Télécharger tout (.zip)",
                        data=zip_data,
                        file_name="transcriptions_lot.zip",
                        mime="application/zip",
                        type="primary",
                        use_container_width=True,
                        key="btn_dl_batch_zip"
                    )
                else:
                    st.button("📦 Télécharger tout (.zip)", disabled=True, use_container_width=True, key="btn_dl_batch_zip_dis")
                    
            with col_act3:
                all_text_combined = "\n\n".join([
                    f"=== {cf.get('filename')} ===\n{cf.get('text', '')}"
                    for cf in completed_files if cf.get("text")
                ])
                if st.button("📋 Copier tout le lot", type="secondary", use_container_width=True, key="btn_copy_all_batch", help="Copier l'ensemble des textes transcrits du lot"):
                    if all_text_combined and copy_to_clipboard(all_text_combined):
                        st.toast(f"{len(completed_files)} transcriptions copiées dans le presse-papier !", icon="📋")
                    else:
                        st.warning("Aucun texte à copier.")

            # --- DÉTAIL ET APERÇU FICHIER PAR FICHIER ---
            if completed_files:
                st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
                st.markdown(f"##### 📋 Fichiers transcrits ({len(completed_files)}) :")
                
                for idx, cf in enumerate(completed_files, start=1):
                    cf_name = cf.get("filename", f"Fichier_{idx}")
                    cf_dur = cf.get("duration")
                    cf_dur_str = f"{int(cf_dur // 60)}m {int(cf_dur % 60):02d}s" if cf_dur else ""
                    cf_lang = cf.get("language", "")
                    cf_lang_disp = SUPPORTED_LANGUAGES.get(cf_lang, cf_lang.upper()) if cf_lang else ""
                    cf_spk = cf.get("speakers") or []
                    
                    header_label = f"📄 {idx}. {cf_name}"
                    if cf_dur_str:
                        header_label += f" — {cf_dur_str}"
                    if cf_lang_disp:
                        header_label += f" ({cf_lang_disp})"
                    if cf_spk:
                        header_label += f" • {len(cf_spk)} locuteurs"
                        
                    with st.expander(header_label, expanded=(len(completed_files) == 1)):
                        cf_text = cf.get("text", "")
                        cf_txt_path = Path(cf.get("txt_path", "")) if cf.get("txt_path") else None
                        cf_srt_path = Path(cf.get("srt_path", "")) if cf.get("srt_path") else None
                        cf_md_path = Path(cf.get("md_path", "")) if cf.get("md_path") else None
                        
                        # Boutons d'action pour ce fichier
                        col_fa_cp, col_fa_txt, col_fa_srt, col_fa_md = st.columns(4)
                        with col_fa_cp:
                            if st.button("📋 Copier", key=f"btn_cp_file_{idx}", use_container_width=True):
                                if copy_to_clipboard(cf_text):
                                    st.toast(f"'{cf_name}' copié !", icon="📋")
                                else:
                                    st.error("Échec copie")
                        with col_fa_txt:
                            if cf_txt_path and cf_txt_path.exists():
                                txt_bytes = cf_txt_path.read_text(encoding="utf-8")
                                st.download_button(
                                    label=":material/download: .txt",
                                    data=txt_bytes,
                                    file_name=cf_txt_path.name,
                                    mime="text/plain",
                                    use_container_width=True,
                                    key=f"dl_txt_file_{idx}"
                                )
                        with col_fa_srt:
                            if cf_srt_path and cf_srt_path.exists():
                                srt_bytes = cf_srt_path.read_text(encoding="utf-8")
                                st.download_button(
                                    label="⏱️ .srt",
                                    data=srt_bytes,
                                    file_name=cf_srt_path.name,
                                    mime="text/plain",
                                    use_container_width=True,
                                    key=f"dl_srt_file_{idx}"
                                )
                        with col_fa_md:
                            if cf_md_path and cf_md_path.exists():
                                md_bytes = cf_md_path.read_text(encoding="utf-8")
                                st.download_button(
                                    label=":material/download: .md",
                                    data=md_bytes,
                                    file_name=cf_md_path.name,
                                    mime="text/markdown",
                                    use_container_width=True,
                                    key=f"dl_md_file_{idx}"
                                )
                        
                        if cf_text:
                            st.text_area(
                                label=f"Aperçu texte ({cf_name}) :",
                                value=cf_text,
                                height=140,
                                key=f"ta_preview_{idx}",
                                disabled=True
                            )
                        else:
                            st.info("Aucun contenu textuel généré.")

                        # Aperçu de la traduction si disponible pour ce fichier
                        tr_text = cf.get("translated_text", "")
                        tr_txt_p = Path(cf.get("translated_txt_path", "")) if cf.get("translated_txt_path") else None
                        tr_srt_p = Path(cf.get("translated_srt_path", "")) if cf.get("translated_srt_path") else None
                        if tr_text:
                            with st.expander(f"🌐 Version Traduite ({cf.get('target_translation', 'Traduction')})", expanded=False):
                                col_btr_cp, col_btr_txt, col_btr_srt = st.columns([1.5, 1, 1])
                                with col_btr_cp:
                                    if st.button("📋 Copier Traduction", key=f"btn_cp_btr_{idx}", use_container_width=True):
                                        if copy_to_clipboard(tr_text):
                                            st.toast("Traduction copiée !", icon="📋")
                                with col_btr_txt:
                                    if tr_txt_p and tr_txt_p.exists():
                                        st.download_button(
                                            label="⬇️ .txt Traduit",
                                            data=tr_txt_p.read_text(encoding="utf-8"),
                                            file_name=tr_txt_p.name,
                                            mime="text/plain",
                                            key=f"dl_btr_txt_{idx}",
                                            use_container_width=True
                                        )
                                with col_btr_srt:
                                    if tr_srt_p and tr_srt_p.exists():
                                        st.download_button(
                                            label="⏱️ .srt Traduit",
                                            data=tr_srt_p.read_text(encoding="utf-8"),
                                            file_name=tr_srt_p.name,
                                            mime="text/plain",
                                            key=f"dl_btr_srt_{idx}",
                                            use_container_width=True
                                        )
                                st.text_area(f"Texte traduit ({cf_name}) :", value=tr_text, height=120, key=f"ta_btr_{idx}", disabled=True)

                        # Éditeur interactif pour ce fichier du lot
                        with st.expander(f"✏️ Éditer & Synchroniser ({cf_name})", expanded=False):
                            b_fpath = Path(cf.get("file_path")) if cf.get("file_path") else None
                            b_out_dir = Path(cf["txt_path"]).parent if cf.get("txt_path") else Path(".")
                            b_bname = Path(cf_name).stem
                            b_seg_key = f"batch_segs_{idx}"
                            if b_seg_key not in st.session_state:
                                if cf.get("segments"):
                                    st.session_state[b_seg_key] = [
                                        TranscriptionSegment.from_dict(s) for s in cf["segments"]
                                    ]
                                elif cf.get("srt_path") and Path(cf["srt_path"]).exists():
                                    st.session_state[b_seg_key] = parse_srt(Path(cf["srt_path"]).read_text(encoding="utf-8"))
                                else:
                                    st.session_state[b_seg_key] = []
                            st.session_state.result_segments = st.session_state[b_seg_key]
                            render_editor_tab(
                                file_path=b_fpath,
                                output_dir=b_out_dir,
                                base_name=b_bname
                            )

            st.markdown("<hr style='margin: 1.5rem 0; border: none; border-top: 1px solid #27272a;'>", unsafe_allow_html=True)
            reset_label = ":material/sync: Traiter une nouvelle file d'attente" if is_queue else ":material/sync: Traiter un autre dossier"
            if st.button(reset_label, use_container_width=True, key="btn_reset_batch"):
                st.session_state.transcription_done = False
                st.session_state.is_processing = False
                st.session_state.latest_text = ""
                st.session_state.is_batch = False
                st.session_state.is_queue_batch = False
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

            is_prep = st.session_state.get("is_preprocessed", False)
            gain_label = "Auto-Gain" if is_prep else "Direct"
            vad_desc = f"VAD: {'Actif' if st.session_state.get('use_vad', True) else 'Inactif'} | {gain_label}"

            elapsed_sec = st.session_state.get("last_elapsed_seconds")
            audio_dur = st.session_state.get("last_audio_duration")
            speed_val = (audio_dur / elapsed_sec) if elapsed_sec and audio_dur and elapsed_sec > 0.1 else None
            speed_desc = f"Vitesse : {speed_val:.1f}x" if speed_val else "Instantané"
            el_str = format_friendly_duration(elapsed_sec) if elapsed_sec is not None else "—"

            if speakers:
                col_res1, col_res2, col_res3, col_res4, col_res5 = st.columns(5)
                with col_res1:
                    ui.metric_card(label="Langue Identifiée", value=lang_label, description=f"Confiance : {prob_val}%")
                with col_res2:
                    ui.metric_card(label="Tâche Réalisée", value=task_type, description=vad_desc)
                with col_res3:
                    ui.metric_card(label="Modèle Whisper", value=st.session_state.get("selected_model", "medium"), description="faster-whisper local")
                with col_res4:
                    ui.metric_card(label="Locuteurs", value=f"{len(speakers)} voix", description=", ".join(speakers[:2]))
                with col_res5:
                    ui.metric_card(label="Temps de calcul", value=el_str, description=speed_desc)
            else:
                col_res1, col_res2, col_res3, col_res4 = st.columns(4)
                with col_res1:
                    ui.metric_card(label="Langue Identifiée", value=lang_label, description=f"Confiance : {prob_val}%")
                with col_res2:
                    ui.metric_card(label="Tâche Réalisée", value=task_type, description=vad_desc)
                with col_res3:
                    ui.metric_card(label="Modèle Whisper", value=st.session_state.get("selected_model", "medium"), description="faster-whisper local")
                with col_res4:
                    ui.metric_card(label="Temps de calcul", value=el_str, description=speed_desc)

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
            tab_edit, tab_txt, tab_md, tab_srt, tab_trans, tab_llm = st.tabs([
                ":material/edit: Éditeur Audio-Texte",
                ":material/description: Texte Brut (.txt)", 
                ":material/markdown: Markdown (.md)", 
                "⏱️ Sous-titres (.srt)", 
                "🌐 Traduction Hors-Ligne",
                "🤖 Prompts LLM"
            ])
            
            with tab_edit:
                render_editor_tab(
                    file_path=file_path,
                    output_dir=out_dir,
                    base_name=base_name
                )
            
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
                
            with tab_trans:
                st.markdown("##### 🌐 Traduction Neuronale Hors-Ligne (NLLB-200)")
                st.markdown("<p style='font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.75rem;'>Traduisez cette transcription vers n'importe quelle langue sans Internet. Préserve les locuteurs et les sous-titres synchronisés.</p>", unsafe_allow_html=True)
                
                if not is_translation_model_installed():
                    st.warning("Le modèle de traduction NLLB-200 (622 Mo) n'est pas encore téléchargé localement.")
                    if st.button("📥 Télécharger le modèle NLLB-200 maintenant", key="btn_dl_nllb_tab", type="primary"):
                        with st.spinner("Téléchargement du modèle NLLB-200 en cours (622 Mo)..."):
                            try:
                                ensure_translation_model()
                                st.success("Modèle téléchargé avec succès !")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erreur de téléchargement : {e}")
                else:
                    col_tr_src, col_tr_tgt, col_tr_btn = st.columns([1.5, 1.5, 1.2])
                    
                    trans_lang_list = list(SUPPORTED_TRANSLATION_LANGUAGES.keys())
                    trans_labels = [f"{d['flag']} {d['name']}" for d in SUPPORTED_TRANSLATION_LANGUAGES.values()]
                    
                    default_src_code = lang_code if lang_code in SUPPORTED_TRANSLATION_LANGUAGES else "fr"
                    default_src_idx = trans_lang_list.index(default_src_code) if default_src_code in trans_lang_list else 0
                    
                    default_tgt_code = "en" if default_src_code == "fr" else "fr"
                    default_tgt_idx = trans_lang_list.index(default_tgt_code) if default_tgt_code in trans_lang_list else 1
                    
                    with col_tr_src:
                        chosen_src_label = st.selectbox("Langue source :", options=trans_labels, index=default_src_idx, key="sb_tr_src")
                        chosen_src_code = trans_lang_list[trans_labels.index(chosen_src_label)]
                    with col_tr_tgt:
                        chosen_tgt_label = st.selectbox("Langue cible :", options=trans_labels, index=default_tgt_idx, key="sb_tr_tgt")
                        chosen_tgt_code = trans_lang_list[trans_labels.index(chosen_tgt_label)]
                    with col_tr_btn:
                        st.markdown("<div style='margin-top: 1.6rem;'></div>", unsafe_allow_html=True)
                        launch_translation = st.button("🌐 Traduire", type="primary", use_container_width=True, key="btn_run_translation")
                        
                    state_tr_key = f"trans_result_{base_name}_{chosen_tgt_code}"
                    
                    # Si une traduction automatique a été générée pendant la transcription
                    if st.session_state.get("translated_text") and st.session_state.get("active_target_translation") == chosen_tgt_code:
                        if state_tr_key not in st.session_state:
                            st.session_state[state_tr_key] = {
                                "txt": st.session_state.get("translated_text", ""),
                                "srt": Path(st.session_state.get("translated_srt_path", "")).read_text(encoding="utf-8") if st.session_state.get("translated_srt_path") and Path(st.session_state["translated_srt_path"]).exists() else "",
                                "md": Path(st.session_state.get("translated_md_path", "")).read_text(encoding="utf-8") if st.session_state.get("translated_md_path") and Path(st.session_state["translated_md_path"]).exists() else ""
                            }
                            
                    if launch_translation:
                        with st.spinner(f"Traduction vers {chosen_tgt_label} en cours (CTranslate2 hors-ligne)..."):
                            try:
                                engine = get_translation_engine(device=st.session_state.hw_profile.device)
                                tr_txt = engine.translate_text(txt_text, src_lang=chosen_src_code, tgt_lang=chosen_tgt_code)
                                tr_srt = engine.translate_srt(srt_text, src_lang=chosen_src_code, tgt_lang=chosen_tgt_code) if srt_text else ""
                                tr_md = f"# Transcription ({chosen_tgt_label})\n\n{tr_txt}"
                                
                                # Écritures atomiques sur disque
                                (out_dir / f"{base_name}_{chosen_tgt_code}.txt").write_text(tr_txt, encoding="utf-8")
                                if tr_srt:
                                    (out_dir / f"{base_name}_{chosen_tgt_code}.srt").write_text(tr_srt, encoding="utf-8")
                                (out_dir / f"{base_name}_{chosen_tgt_code}.md").write_text(tr_md, encoding="utf-8")
                                
                                st.session_state[state_tr_key] = {
                                    "txt": tr_txt,
                                    "srt": tr_srt,
                                    "md": tr_md
                                }
                                st.toast(f"Traduction vers {chosen_tgt_label} terminée !", icon="🌐")
                            except Exception as e:
                                st.error(f"Erreur lors de la traduction : {e}")
                                
                    curr_trans = st.session_state.get(state_tr_key)
                    if curr_trans and curr_trans.get("txt"):
                        res_txt = curr_trans["txt"]
                        res_srt = curr_trans.get("srt", "")
                        res_md = curr_trans.get("md", "")
                        
                        st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
                        col_t_act_cp, col_t_act_txt, col_t_act_srt, col_t_act_md = st.columns(4)
                        with col_t_act_cp:
                            if st.button("📋 Copier la traduction", key=f"btn_cp_tr_{chosen_tgt_code}", use_container_width=True):
                                if copy_to_clipboard(res_txt):
                                    st.toast("Traduction copiée dans le presse-papier !", icon="📋")
                                else:
                                    st.error("Impossible d'accéder au presse-papier.")
                        with col_t_act_txt:
                            st.download_button(
                                label="⬇️ .txt Traduit",
                                data=res_txt,
                                file_name=f"{base_name}_{chosen_tgt_code}.txt",
                                mime="text/plain",
                                use_container_width=True,
                                key=f"dl_tr_txt_{chosen_tgt_code}"
                            )
                        with col_t_act_srt:
                            if res_srt:
                                st.download_button(
                                    label="⏱️ .srt Traduit",
                                    data=res_srt,
                                    file_name=f"{base_name}_{chosen_tgt_code}.srt",
                                    mime="text/plain",
                                    use_container_width=True,
                                    key=f"dl_tr_srt_{chosen_tgt_code}"
                                )
                            else:
                                st.caption("SRT non disponible")
                        with col_t_act_md:
                            if res_md:
                                st.download_button(
                                    label="⬇️ .md Traduit",
                                    data=res_md,
                                    file_name=f"{base_name}_{chosen_tgt_code}.md",
                                    mime="text/markdown",
                                    use_container_width=True,
                                    key=f"dl_tr_md_{chosen_tgt_code}"
                                )
                                
                        st.text_area(f"Texte traduit ({chosen_tgt_label}) :", value=res_txt, height=250, key=f"ta_tr_{chosen_tgt_code}")
                        if res_srt:
                            with st.expander("⏱️ Aperçu des sous-titres traduits (.srt)"):
                                st.code(res_srt, language="text")
                    else:
                        st.info("Sélectionnez les langues et cliquez sur '🌐 Traduire' pour générer la version traduite.")
                
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
