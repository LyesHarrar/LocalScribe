"""
ui/editor_component.py — Composant d'Éditeur Audio-Texte Interactif & Synchronisé
Offre un lecteur audio karaoké synchronisé avec suivi en temps réel du texte,
une barre d'outils de recherche/remplacement, et une double interface d'édition
(cartes interactives avec écoute ciblée + grille tabulaire st.data_editor).
"""

import base64
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core.text_formatter import (
    TranscriptionSegment,
    format_timestamp_short,
    parse_srt
)
from core.editor_engine import (
    search_and_replace_segments,
    merge_adjacent_segments,
    split_segment,
    delete_segment,
    save_edited_transcription
)
from core.clipboard import copy_to_clipboard

logger = logging.getLogger("LocalScribe.UI.Editor")


def get_audio_mime(suffix: str) -> str:
    """Détermine le type MIME approprié pour un fichier audio/vidéo."""
    ext = suffix.lower()
    if ext == ".mp3":
        return "audio/mp3"
    elif ext == ".wav":
        return "audio/wav"
    elif ext == ".m4a":
        return "audio/mp4"
    elif ext == ".ogg":
        return "audio/ogg"
    elif ext == ".flac":
        return "audio/flac"
    elif ext in (".mp4", ".mkv", ".mov", ".avi"):
        return "video/mp4"
    return "audio/mpeg"


def render_karaoke_html_player(
    audio_path: Path,
    segments: List[TranscriptionSegment],
    container_height: int = 420
) -> None:
    """
    Rendu d'un lecteur HTML5 ultra-rapide avec synchronisation automatique :
    - Écoute l'événement 'timeupdate' du lecteur audio.
    - Met en surbrillance dynamique le segment en cours de lecture.
    - Défilement automatique (auto-scroll) vers le segment actif.
    - Clic sur un timecode = saut instantané à la seconde exacte dans l'audio.
    """
    try:
        mime = get_audio_mime(audio_path.suffix)
        raw_bytes = audio_path.read_bytes()
        b64_audio = base64.b64encode(raw_bytes).decode("utf-8")
        audio_src = f"data:{mime};base64,{b64_audio}"
    except Exception as e:
        logger.warning(f"Impossible d'encoder le fichier audio en base64 : {e}")
        st.warning("Fichier trop volumineux pour le lecteur karaoké HTML5. Utilisez le lecteur standard ci-dessous.")
        return

    # Préparation des segments HTML
    segments_html = []
    for idx, s in enumerate(segments):
        start_str = format_timestamp_short(s.start)
        end_str = format_timestamp_short(s.end)
        spk_tag = f'<span class="spk-tag">[{s.speaker}]</span> ' if s.speaker else ""
        escaped_text = s.text.replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        
        segments_html.append(f"""
        <div class="seg-card" id="seg-{idx}" data-start="{s.start}" data-end="{s.end}" onclick="seekTo({s.start})">
            <div class="seg-header">
                <span class="seg-time">⏱️ {start_str} → {end_str}</span>
                {spk_tag}
            </div>
            <div class="seg-text">{escaped_text}</div>
        </div>
        """)

    all_segments_str = "\n".join(segments_html)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }}
        body {{ background: #09090b; color: #f8fafc; padding: 8px; }}
        .player-bar {{
            position: sticky;
            top: 0;
            background: #18181b;
            border: 1px solid #27272a;
            border-radius: 10px;
            padding: 10px 14px;
            z-index: 100;
            margin-bottom: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        audio {{
            flex: 1;
            height: 38px;
            border-radius: 8px;
            outline: none;
        }}
        .speed-btn {{
            background: #27272a;
            color: #94a3b8;
            border: 1px solid #3f3f46;
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 0.78rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
        }}
        .speed-btn:hover, .speed-btn.active {{
            background: #10b981;
            color: #ffffff;
            border-color: #10b981;
        }}
        .transcript-container {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            max-height: {container_height - 90}px;
            overflow-y: auto;
            padding-right: 4px;
        }}
        .transcript-container::-webkit-scrollbar {{
            width: 6px;
        }}
        .transcript-container::-webkit-scrollbar-thumb {{
            background: #27272a;
            border-radius: 4px;
        }}
        .seg-card {{
            background: #18181b;
            border: 1px solid #27272a;
            border-radius: 8px;
            padding: 10px 14px;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }}
        .seg-card:hover {{
            background: #27272a;
            border-color: #3b82f6;
            transform: translateX(2px);
        }}
        .seg-card.active {{
            background: rgba(16, 185, 129, 0.12);
            border: 1.5px solid #10b981;
            box-shadow: 0 0 14px rgba(16, 185, 129, 0.25);
            transform: scale(1.01);
        }}
        .seg-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;
        }}
        .seg-time {{
            font-size: 0.72rem;
            font-family: monospace;
            color: #60a5fa;
            background: rgba(96, 165, 250, 0.1);
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 600;
        }}
        .spk-tag {{
            font-size: 0.75rem;
            color: #a78bfa;
            font-weight: 700;
        }}
        .seg-text {{
            font-size: 0.88rem;
            color: #e2e8f0;
            line-height: 1.45;
        }}
        .seg-card.active .seg-text {{
            color: #ffffff;
            font-weight: 500;
        }}
    </style>
    </head>
    <body>
        <div class="player-bar">
            <audio id="ls-audio" controls src="{audio_src}"></audio>
            <button class="speed-btn" onclick="setSpeed(0.8)">0.8x</button>
            <button class="speed-btn active" id="btn-1x" onclick="setSpeed(1.0)">1.0x</button>
            <button class="speed-btn" onclick="setSpeed(1.2)">1.2x</button>
            <button class="speed-btn" onclick="setSpeed(1.5)">1.5x</button>
        </div>

        <div class="transcript-container" id="transcript-box">
            {all_segments_str}
        </div>

        <script>
            const audio = document.getElementById('ls-audio');
            const cards = document.querySelectorAll('.seg-card');
            const container = document.getElementById('transcript-box');
            let currentActive = null;

            function seekTo(seconds) {{
                audio.currentTime = seconds;
                audio.play();
            }}

            function setSpeed(rate) {{
                audio.playbackRate = rate;
                document.querySelectorAll('.speed-btn').forEach(btn => btn.classList.remove('active'));
                event.target.classList.add('active');
            }}

            audio.addEventListener('timeupdate', () => {{
                const cur = audio.currentTime;
                let activeFound = null;

                for (let card of cards) {{
                    const start = parseFloat(card.getAttribute('data-start'));
                    const end = parseFloat(card.getAttribute('data-end'));
                    if (cur >= start && cur <= end) {{
                        activeFound = card;
                        break;
                    }}
                }}

                if (activeFound && activeFound !== currentActive) {{
                    if (currentActive) {{
                        currentActive.classList.remove('active');
                    }}
                    activeFound.classList.add('active');
                    currentActive = activeFound;
                    activeFound.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
                }} else if (!activeFound && currentActive) {{
                    currentActive.classList.remove('active');
                    currentActive = null;
                }}
            }});
        </script>
    </body>
    </html>
    """
    components.html(html_code, height=container_height)


def render_editor_tab(
    file_path: Optional[Path],
    output_dir: Path,
    base_name: str,
    record_id: Optional[int] = None
) -> None:
    """
    Rendu complet de l'onglet Éditeur Audio-Texte & Synchronisation.
    Prend en charge la réconciliation des segments, l'écoute ciblée, la recherche/remplacement
    et la sauvegarde atomique immédiate vers tous les formats et SQLite.
    """
    # 1. Initialisation / Récupération des segments
    if "result_segments" not in st.session_state or not st.session_state.result_segments:
        srt_file = output_dir / f"{base_name}.srt"
        if srt_file.exists():
            st.session_state.result_segments = parse_srt(srt_file.read_text(encoding="utf-8"))
        else:
            st.session_state.result_segments = []

    segments: List[TranscriptionSegment] = st.session_state.result_segments

    if not segments:
        st.info("Aucun segment de transcription disponible pour l'édition.")
        return

    # 2. Section Lecteur Audio & Synchronisation
    audio_exists = file_path and file_path.exists()
    file_size_mb = (file_path.stat().st_size / (1024 * 1024)) if audio_exists else 0.0

    st.markdown("#### 🎧 Lecteur Audio & Synchronisation")

    if audio_exists:
        col_ctrl1, col_ctrl2 = st.columns([3, 1])
        with col_ctrl1:
            player_mode = st.radio(
                "Mode de lecture :",
                options=["✨ Karaoké Synchronisé (Saut & Défilement auto)", "🎵 Lecteur Standard"],
                horizontal=True,
                label_visibility="collapsed"
            )
        with col_ctrl2:
            st.caption(f"Fichier : `{file_path.name}` ({file_size_mb:.1f} MB)")

        if "Karaoké" in player_mode and file_size_mb <= 60.0:
            render_karaoke_html_player(file_path, segments, container_height=380)
        else:
            seek_time = float(st.session_state.get("editor_seek_time", 0.0))
            if seek_time > 0.0:
                st.caption(f"⏱️ Position d'écoute : `{format_timestamp_short(seek_time)}`")
            st.audio(str(file_path), start_time=int(seek_time))
    else:
        st.markdown("""
        <div style="background: #18181b; border: 1px solid #27272a; border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 0.75rem; color: #94a3b8; font-size: 0.85rem;">
            ℹ️ <em>Le fichier audio source d'origine n'est pas accessible en direct, mais l'éditeur de texte et sous-titres reste 100 % opérationnel pour modifier, fusionner et sauvegarder vos répliques.</em>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<hr style='margin: 1rem 0; border: none; border-top: 1px solid #27272a;'>", unsafe_allow_html=True)

    # 3. Barre d'outils d'Édition Rapide (Rechercher / Remplacer)
    with st.expander("🔍 Rechercher et remplacer dans tout le document", expanded=False):
        col_f1, col_f2, col_f3, col_f4 = st.columns([2.5, 2.5, 1.5, 1.5])
        with col_f1:
            find_str = st.text_input("Rechercher :", key="find_input", placeholder="Ex: Whispere")
        with col_f2:
            replace_str = st.text_input("Remplacer par :", key="replace_input", placeholder="Ex: Whisper")
        with col_f3:
            st.markdown("<div style='margin-top: 1.8rem;'></div>", unsafe_allow_html=True)
            match_case = st.checkbox("Casse exacte", key="chk_match_case")
        with col_f4:
            st.markdown("<div style='margin-top: 1.7rem;'></div>", unsafe_allow_html=True)
            if st.button("Remplacer tout", key="btn_exec_replace", use_container_width=True):
                if find_str.strip():
                    new_segs, count = search_and_replace_segments(
                        segments, find_str.strip(), replace_str, match_case=match_case
                    )
                    st.session_state.result_segments = new_segs
                    st.toast(f"✅ {count} occurrence(s) remplacée(s) !", icon="✏️")
                    st.rerun()
                else:
                    st.warning("Veuillez saisir un terme à rechercher.")

    # Choix du mode d'affichage
    col_mode, col_save_top = st.columns([3, 2])
    with col_mode:
        editor_display_mode = st.radio(
            "Vue d'édition :",
            options=[":material/view_agenda: Cartes & Écoute par segment", ":material/table_chart: Grille Tabulaire Multi-lignes"],
            horizontal=True,
            key="editor_display_mode"
        )
    with col_save_top:
        st.markdown("<div style='margin-top: 0.3rem;'></div>", unsafe_allow_html=True)
        if st.button("💾 Enregistrer toutes les modifications", type="primary", use_container_width=True, key="btn_save_top"):
            res = save_edited_transcription(
                output_dir=output_dir,
                base_name=base_name,
                segments=st.session_state.result_segments,
                metadata={"filename": f"{base_name}.mp3"},
                record_id=record_id
            )
            # Mise à jour des variables d'état globales
            st.session_state.latest_text = res["txt_text"]
            st.toast("Fichiers .txt, .srt et .md mis à jour avec succès !", icon="💾")
            st.rerun()

    # 4. Mode Cartes & Écoute
    if "Cartes" in editor_display_mode:
        st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
        
        # Pagination si nombre élevé de segments
        PAGE_SIZE = 40
        total_segs = len(segments)
        num_pages = max(1, (total_segs + PAGE_SIZE - 1) // PAGE_SIZE)
        
        current_page = 0
        if num_pages > 1:
            col_p1, col_p2 = st.columns([4, 1])
            with col_p1:
                st.caption(f"Affichage de {total_segs} segments (Page 1 à {num_pages})")
            with col_p2:
                current_page = st.selectbox("Page :", options=list(range(1, num_pages + 1)), index=0) - 1

        start_idx = current_page * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, total_segs)

        has_modifications = False

        for idx in range(start_idx, end_idx):
            s = segments[idx]
            card_id = f"seg_edit_{idx}"
            
            with st.container():
                col_btn, col_spk, col_act1, col_act2 = st.columns([1.6, 2, 1.2, 0.8])
                with col_btn:
                    # Bouton d'écoute ciblée
                    time_label = f"▶️ {format_timestamp_short(s.start)}"
                    if st.button(time_label, key=f"btn_play_{idx}", help=f"Écouter de {format_timestamp_short(s.start)} à {format_timestamp_short(s.end)}", use_container_width=True):
                        st.session_state.editor_seek_time = s.start
                        st.rerun()
                
                with col_spk:
                    # Modification du locuteur
                    new_spk = st.text_input(
                        "Locuteur :", 
                        value=s.speaker or "", 
                        key=f"spk_{idx}", 
                        label_visibility="collapsed",
                        placeholder="Locuteur (optionnel)"
                    )
                    if new_spk != (s.speaker or ""):
                        s.speaker = new_spk.strip() or None
                        has_modifications = True
                
                with col_act1:
                    # Fusionner avec le segment suivant
                    if idx < total_segs - 1:
                        if st.button("🔗 Fusionner", key=f"btn_merge_{idx}", help="Fusionner avec le segment suivant", use_container_width=True):
                            st.session_state.result_segments = merge_adjacent_segments(segments, idx)
                            st.rerun()
                
                with col_act2:
                    # Supprimer le segment
                    if st.button("🗑️", key=f"btn_del_{idx}", help="Supprimer ce segment", use_container_width=True):
                        st.session_state.result_segments = delete_segment(segments, idx)
                        st.rerun()

                # Champ texte éditable
                new_text = st.text_area(
                    label=f"Texte #{s.id} :",
                    value=s.text,
                    key=f"txt_{idx}",
                    height=70,
                    label_visibility="collapsed"
                )
                if new_text != s.text:
                    s.text = new_text.strip()
                    has_modifications = True

                st.markdown("<div style='margin-bottom: 0.6rem;'></div>", unsafe_allow_html=True)

    # 5. Mode Grille Tabulaire (st.data_editor)
    else:
        st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
        st.caption("Modifiez directement les valeurs dans le tableau ci-dessous, puis cliquez sur **Sauvegarder**.")

        df_data = []
        for s in segments:
            df_data.append({
                "ID": s.id or 1,
                "Début (s)": s.start,
                "Fin (s)": s.end,
                "Locuteur": s.speaker or "",
                "Texte": s.text
            })

        df = pd.DataFrame(df_data)

        edited_df = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "ID": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                "Début (s)": st.column_config.NumberColumn("Début (s)", step=0.1, format="%.2f", width="small"),
                "Fin (s)": st.column_config.NumberColumn("Fin (s)", step=0.1, format="%.2f", width="small"),
                "Locuteur": st.column_config.TextColumn("Locuteur", width="medium"),
                "Texte": st.column_config.TextColumn("Texte", width="large")
            },
            key="df_editor_table"
        )

        # Synchronisation du DataFrame vers result_segments
        if st.button("📥 Appliquer les modifications du tableau", key="btn_sync_df", type="secondary", use_container_width=True):
            new_segs = []
            for i, row in edited_df.iterrows():
                try:
                    seg = TranscriptionSegment(
                        start=float(row.get("Début (s)", 0.0)),
                        end=float(row.get("Fin (s)", 0.0)),
                        text=str(row.get("Texte", "")).strip(),
                        speaker=str(row.get("Locuteur", "")).strip() or None,
                        id=int(row.get("ID", i + 1))
                    )
                    new_segs.append(seg)
                except Exception as row_err:
                    logger.warning(f"Ligne de tableau ignorée : {row_err}")
            
            st.session_state.result_segments = new_segs
            st.toast("Tableau synchronisé ! N'oubliez pas d'enregistrer.", icon="✅")
            st.rerun()

    # 6. Bouton de sauvegarde inférieur
    st.markdown("<hr style='margin: 1.5rem 0; border: none; border-top: 1px solid #27272a;'>", unsafe_allow_html=True)
    col_save_b1, col_save_b2 = st.columns([1, 1])
    with col_save_b1:
        if st.button("💾 Enregistrer et mettre à jour tous les formats", type="primary", use_container_width=True, key="btn_save_bottom"):
            res = save_edited_transcription(
                output_dir=output_dir,
                base_name=base_name,
                segments=st.session_state.result_segments,
                metadata={"filename": f"{base_name}.mp3"},
                record_id=record_id
            )
            st.session_state.latest_text = res["txt_text"]
            st.toast("Modifications enregistrées ! Fichiers .txt, .srt et .md mis à jour.", icon="🎉")
            st.rerun()

    with col_save_b2:
        if st.button("📋 Copier le texte complet corrigé", key="btn_copy_edited_all", use_container_width=True):
            full_txt = "\n".join(
                f"[{s.speaker}] {s.text}" if s.speaker else s.text
                for s in st.session_state.result_segments
            )
            if copy_to_clipboard(full_txt):
                st.toast("Texte corrigé copié dans le presse-papier !", icon="📋")
