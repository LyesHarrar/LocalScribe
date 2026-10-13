"""
ui/visual_component.py — Composant UI pour l'onglet 'Schémas & Captures Vidéo'
Affiche les schémas et diapositives détectés, permet l'extraction à la demande,
la prévisualisation en galerie, le téléchargement ZIP et l'export Markdown illustré.
"""

import os
from pathlib import Path
from typing import List, Any, Optional
import streamlit as st

from core.clipboard import copy_to_clipboard
from core.text_formatter import parse_srt, TranscriptionSegment
from core.visual_extractor import (
    VisualKeyframe,
    is_video_file,
    detect_visual_moments_heuristic,
    process_video_visuals,
    generate_illustrated_markdown,
    create_captures_zip_bytes
)


def render_visual_tab(
    file_path: Path,
    output_dir: Path,
    segments: Optional[List[Any]] = None,
    srt_text: str = "",
    base_name: str = "",
    key_prefix: str = "single"
):
    """
    Rendu complet de l'onglet 'Schémas & Captures Vidéo'.
    Gère la vérification vidéo, la détection sémantique, la galerie d'images et les exports.
    """
    st.markdown("##### 🖼️ Détection et Captures Automatiques des Schémas Vidéo")
    st.markdown(
        "<p style='font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.85rem;'>"
        "Repère automatiquement quand l'orateur montre un schéma, slide, tableau ou framework à l'écran, "
        "et capture l'image exacte correspondante pour enrichir la transcription tout en économisant les tokens des LLMs."
        "</p>",
        unsafe_allow_html=True
    )

    # 1. Vérification si le fichier source est une vidéo
    if not is_video_file(file_path):
        st.markdown(f"""
        <div style="background: #18181b; border: 1px solid #27272a; border-radius: 12px; padding: 1.1rem 1.25rem; margin-top: 0.5rem;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 1.2rem;">🎙️</span>
                <span style="font-weight: 600; color: #38bdf8; font-size: 0.92rem;">Enregistrement Audio Seul</span>
            </div>
            <div style="color: #a1a1aa; font-size: 0.82rem; margin-top: 0.4rem; line-height: 1.45;">
                Le fichier <code>{file_path.name}</code> est un fichier audio sans flux d'images vidéo.<br>
                L'extraction de schémas s'applique exclusivement aux fichiers vidéo (<code>.mp4</code>, <code>.mkv</code>, <code>.mov</code>, <code>.avi</code>, <code>.webm</code>).
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # 2. Récupération des segments de transcription
    actual_segments = segments or []
    if not actual_segments and srt_text:
        actual_segments = parse_srt(srt_text)

    if not actual_segments:
        st.warning("Aucun segment de transcription disponible pour analyser la vidéo.")
        return

    state_kf_key = f"{key_prefix}_{base_name}_keyframes"
    captures_dir = output_dir / f"captures_{base_name}"

    # Détection si des captures existent déjà sur disque
    if state_kf_key not in st.session_state:
        existing_keyframes: List[VisualKeyframe] = []
        if captures_dir.is_dir():
            jpg_files = list(captures_dir.glob("*.jpg"))
            if jpg_files:
                # Retrouver les métadonnées correspondantes via l'heuristique
                candidates = detect_visual_moments_heuristic(actual_segments)
                for c in candidates:
                    matching_img = captures_dir / c.image_filename
                    if matching_img.is_file():
                        c.image_path = str(matching_img)
                        existing_keyframes.append(c)
        st.session_state[state_kf_key] = existing_keyframes

    current_keyframes: List[VisualKeyframe] = st.session_state.get(state_kf_key, [])

    # 3. Barre de commande et déclenchement d'analyse
    col_opt1, col_opt2 = st.columns([2, 1], vertical_alignment="center")
    with col_opt1:
        detection_engine = st.radio(
            "Moteur de détection :",
            options=["⚡ Heuristique Sémantique (0 token • Ultra-rapide)", "🧠 IA Locale (Ollama / LM Studio)"],
            horizontal=True,
            key=f"{key_prefix}_visual_engine_choice"
        )
    with col_opt2:
        use_ai_detection = "IA Locale" in detection_engine
        btn_label = "📸 Extraire les schémas" if not current_keyframes else "🔄 Ré-analyser la vidéo"
        launch_extract = st.button(
            btn_label, 
            type="primary" if not current_keyframes else "secondary", 
            use_container_width=True, 
            key=f"{key_prefix}_btn_launch_visual"
        )

    if launch_extract:
        with st.spinner("Analyse sémantique et extraction chirurgicale des captures via FFmpeg..."):
            try:
                extracted, out_dir_res = process_video_visuals(
                    video_path=file_path,
                    segments=actual_segments,
                    output_dir=output_dir,
                    use_ai=use_ai_detection
                )
                st.session_state[state_kf_key] = extracted
                current_keyframes = extracted
                
                # Génération automatique du fichier Markdown illustré sur disque
                if extracted:
                    metadata = {
                        "filename": file_path.name,
                        "duration": actual_segments[-1].end if hasattr(actual_segments[-1], "end") else 0.0,
                        "language": st.session_state.get("detected_language", "fr")
                    }
                    ill_md = generate_illustrated_markdown(actual_segments, metadata, extracted)
                    ill_path = output_dir / f"{base_name}_illustre.md"
                    ill_path.write_text(ill_md, encoding="utf-8")

                if extracted:
                    st.toast(f"{len(extracted)} schéma(s) extrait(s) avec succès !", icon="📸")
                else:
                    st.info("Aucun schéma ou slide détecté dans cette vidéo.")
                st.rerun()
            except Exception as ex:
                st.error(f"Erreur lors de l'extraction des schémas : {ex}")

    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

    # 4. Affichage des résultats
    if not current_keyframes:
        if not launch_extract:
            st.markdown(f"""
            <div style="background: #11131a; border: 1px dashed #232738; border-radius: 12px; padding: 1.5rem; text-align: center;">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">📸</div>
                <div style="color: #f8fafc; font-weight: 600; font-size: 0.95rem;">Prêt à analyser les visuels de la vidéo</div>
                <div style="color: #94a3b8; font-size: 0.8rem; margin-top: 0.25rem; max-width: 550px; margin-left: auto; margin-right: auto;">
                    Cliquez sur <b>Extraire les schémas</b> pour scanner les mentions de diagrammes, diapositives et tableaux, et extraire automatiquement les captures HD correspondantes.
                </div>
            </div>
            """, unsafe_allow_html=True)
        return

    # Barre d'actions rapides pour les captures
    st.markdown(f"#### 🎯 {len(current_keyframes)} Schéma(s) & Visuel(s) Clé(s) Identifié(s)")

    col_a1, col_a2, col_a3, col_a4 = st.columns([1.3, 1.3, 1.3, 1.1])
    
    # 1. Télécharger tout en ZIP
    zip_bytes = create_captures_zip_bytes(current_keyframes)
    with col_a1:
        st.download_button(
            label="📥 Télécharger (.zip)",
            data=zip_bytes,
            file_name=f"{base_name}_captures.zip",
            mime="application/zip",
            use_container_width=True,
            key=f"{key_prefix}_dl_zip_btn"
        )

    # 2. Copier Markdown illustré
    metadata = {
        "filename": file_path.name,
        "duration": actual_segments[-1].end if hasattr(actual_segments[-1], "end") else 0.0,
        "language": st.session_state.get("detected_language", "fr")
    }
    ill_md_content = generate_illustrated_markdown(actual_segments, metadata, current_keyframes)
    with col_a2:
        if st.button("📋 Copier le Markdown Illustré", key=f"{key_prefix}_copy_ill_md", use_container_width=True):
            if copy_to_clipboard(ill_md_content):
                st.toast("Markdown illustré copié dans le presse-papier !", icon="📋")
            else:
                st.error("Impossible d'accéder au presse-papier.")

    # 3. Télécharger Markdown illustré
    with col_a3:
        st.download_button(
            label="⬇️ Markdown Illustré (.md)",
            data=ill_md_content,
            file_name=f"{base_name}_illustre.md",
            mime="text/markdown",
            use_container_width=True,
            key=f"{key_prefix}_dl_ill_md_btn"
        )

    # 4. Ouvrir le dossier des captures dans Windows
    with col_a4:
        if st.button("📁 Ouvrir Dossier", key=f"{key_prefix}_open_captures_dir", use_container_width=True):
            if captures_dir.is_dir():
                try:
                    os.startfile(str(captures_dir))
                except Exception as oe:
                    st.warning(f"Impossible d'ouvrir le dossier : {oe}")

    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

    # 5. Galerie en Grille des Schémas
    cols_grid = st.columns(2)
    for idx, kf in enumerate(current_keyframes):
        col = cols_grid[idx % 2]
        with col:
            st.markdown(f"""
            <div style="background: #18181b; border: 1px solid #27272a; border-radius: 12px; padding: 1rem; margin-bottom: 1rem; box-shadow: 0 4px 12px rgba(0,0,0,0.25);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <span style="font-weight: 700; color: #f8fafc; font-size: 0.95rem;">🖼️ {kf.title}</span>
                    <span style="background: rgba(46, 116, 253, 0.15); color: #60a5fa; border: 1px solid rgba(46, 116, 253, 0.3); padding: 2px 8px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600;">⏱️ {kf.time_str}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if kf.image_path and Path(kf.image_path).is_file():
                st.image(kf.image_path, use_container_width=True)
                
                st.markdown(f"""
                <div style="background: #11131a; border-left: 3px solid #3b82f6; padding: 0.5rem 0.75rem; border-radius: 0 6px 6px 0; margin-top: -0.25rem; margin-bottom: 0.5rem; font-size: 0.78rem; color: #cbd5e1; font-style: italic;">
                    « {kf.context} »
                </div>
                """, unsafe_allow_html=True)

                img_bytes = Path(kf.image_path).read_bytes()
                st.download_button(
                    label=f"⬇️ Télécharger {kf.image_filename}",
                    data=img_bytes,
                    file_name=kf.image_filename,
                    mime="image/jpeg",
                    use_container_width=True,
                    key=f"{key_prefix}_dl_img_{idx}"
                )
            else:
                st.caption("Fichier image non disponible sur disque.")

    # 6. Accordéon de prévisualisation du Markdown Illustré
    with st.expander("📄 Prévisualisation du Markdown Illustré (avec liens images)", expanded=False):
        st.markdown(ill_md_content)
