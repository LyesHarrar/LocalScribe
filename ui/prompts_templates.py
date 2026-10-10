"""
Module Studio IA & Synthèse sur place pour LocalScribe.
Permet d'exécuter des synthèses, plans d'action, chapitrages, réécritures
et questions/réponses directement dans l'application via Ollama, LM Studio ou API Cloud.
Harmonisé avec le thème Obsidian & Electric Blue.
"""

from pathlib import Path
from typing import Optional, Dict, Any
import streamlit as st

from core.clipboard import copy_to_clipboard
from core.local_ai_engine import (
    load_ai_config,
    save_ai_config,
    detect_available_backends,
    generate_ai_response,
    ask_ai_about_transcript,
    AI_TEMPLATES
)


def _render_ai_config_popover(backends: Dict[str, Any], key_prefix: str = "main"):
    """Affiche le volet de configuration de l'IA locale et des modèles."""
    with st.popover("⚙️ Configurer l'IA & Modèles", use_container_width=True):
        st.markdown("#### Configuration du Moteur IA")
        st.caption("LocalScribe privilégie les moteurs 100% locaux et hors-ligne (Ollama, LM Studio).")
        
        cfg = load_ai_config()
        
        # Choix de backend
        backend_choices = ["auto", "ollama", "lmstudio", "api"]
        backend_labels = [
            "Auto-détection (Recommandé)",
            "Ollama local (localhost:11434)",
            "LM Studio local (localhost:1234)",
            "Clé API Cloud personnelle (Mistral, OpenAI, Groq, Gemini)"
        ]
        curr_b_idx = backend_choices.index(cfg.get("backend", "auto")) if cfg.get("backend", "auto") in backend_choices else 0
        selected_backend_label = st.selectbox(
            "Mode de détection :",
            options=backend_labels,
            index=curr_b_idx,
            key=f"{key_prefix}_cfg_backend"
        )
        selected_backend = backend_choices[backend_labels.index(selected_backend_label)]
        
        # Configuration Ollama
        st.markdown("---")
        st.markdown("**Paramètres Ollama**")
        ollama_url = st.text_input(
            "URL Ollama :",
            value=cfg.get("ollama_url", "http://localhost:11434"),
            key=f"{key_prefix}_cfg_ollama_url"
        )
        if backends.get("ollama", {}).get("available"):
            st.success(f"Ollama connecté — Modèles trouvés : {len(backends['ollama']['models'])}")
        else:
            st.caption("Ollama non détecté sur cette adresse.")

        # Configuration LM Studio
        st.markdown("---")
        st.markdown("**Paramètres LM Studio / OpenAI-compatible**")
        lmstudio_url = st.text_input(
            "URL LM Studio :",
            value=cfg.get("lmstudio_url", "http://localhost:1234/v1"),
            key=f"{key_prefix}_cfg_lm_url"
        )
        if backends.get("lmstudio", {}).get("available"):
            st.success("LM Studio connecté.")
        else:
            st.caption("LM Studio non détecté sur cette adresse.")

        # Modèle spécifique si modèles disponibles
        all_models = backends.get("available_models", [])
        if all_models:
            st.markdown("---")
            st.markdown("**Modèle actif**")
            curr_model = cfg.get("selected_model", "")
            model_idx = all_models.index(curr_model) if curr_model in all_models else 0
            chosen_model = st.selectbox(
                "Sélectionner le modèle :",
                options=all_models,
                index=model_idx,
                key=f"{key_prefix}_cfg_model"
            )
        else:
            chosen_model = ""

        # Fournisseur API Cloud optionnel
        st.markdown("---")
        st.markdown("**Fournisseur Cloud (Optionnel - BYOK)**")
        providers = ["mistral", "openai", "groq", "gemini"]
        p_idx = providers.index(cfg.get("api_provider", "mistral")) if cfg.get("api_provider", "mistral") in providers else 0
        chosen_provider = st.selectbox(
            "Fournisseur :",
            options=providers,
            index=p_idx,
            key=f"{key_prefix}_cfg_prov"
        )
        api_key = st.text_input(
            "Clé API privée :",
            value=cfg.get("api_key", ""),
            type="password",
            key=f"{key_prefix}_cfg_key",
            help="Votre clé reste strictement sur votre machine locale dans data/ai_config.json."
        )

        if st.button("💾 Enregistrer la configuration", type="primary", use_container_width=True, key=f"{key_prefix}_save_cfg"):
            cfg["backend"] = selected_backend
            cfg["ollama_url"] = ollama_url.strip()
            cfg["lmstudio_url"] = lmstudio_url.strip()
            cfg["api_provider"] = chosen_provider
            cfg["api_key"] = api_key.strip()
            if chosen_model:
                cfg["selected_model"] = chosen_model
            save_ai_config(cfg)
            st.toast("Configuration IA enregistrée !", icon="💾")
            st.rerun()


def render_llm_templates(transcription_text: str = "", key_prefix: str = "main"):
    """
    Rendu principal du Studio IA & Synthèse sur place.
    Permet à l'utilisateur de générer des synthèses directement ou de copier les prompts.
    """
    st.markdown("### :material/smart_toy: Studio IA & Synthèse sur place")
    st.caption("Analysez, résumez et interrogez vos enregistrements en 1 clic grâce à votre IA locale.")

    # 1. Détection des moteurs IA
    cfg = load_ai_config()
    backends = detect_available_backends(cfg)
    active_b = backends.get("active_backend")
    active_m = backends.get("active_model", "Inconnu")

    # Barre de statut & Configuration
    col_status, col_refresh, col_cfg = st.columns([6, 2, 2.5])
    
    with col_status:
        if active_b == "ollama":
            st.markdown(
                f"<div style='background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); "
                f"padding: 7px 14px; border-radius: 8px; font-size: 0.88rem; display: flex; align-items: center; gap: 8px;'>"
                f"<span>🟢</span> <b>Moteur local actif :</b> Ollama (<code>{active_m}</code>) — <i>100% hors-ligne & gratuit</i>"
                f"</div>",
                unsafe_allow_html=True
            )
        elif active_b == "lmstudio":
            st.markdown(
                f"<div style='background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); "
                f"padding: 7px 14px; border-radius: 8px; font-size: 0.88rem; display: flex; align-items: center; gap: 8px;'>"
                f"<span>🟢</span> <b>Moteur local actif :</b> LM Studio (<code>{active_m}</code>) — <i>100% hors-ligne & gratuit</i>"
                f"</div>",
                unsafe_allow_html=True
            )
        elif active_b == "api":
            prov_name = cfg.get("api_provider", "Cloud").capitalize()
            st.markdown(
                f"<div style='background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.35); "
                f"padding: 7px 14px; border-radius: 8px; font-size: 0.88rem; display: flex; align-items: center; gap: 8px;'>"
                f"<span>🔵</span> <b>API Cloud active :</b> {prov_name} (<code>{active_m}</code>)"
                f"</div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                "<div style='background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); "
                "padding: 7px 14px; border-radius: 8px; font-size: 0.88rem; display: flex; align-items: center; gap: 8px;'>"
                "<span>⚪</span> <b>Aucun moteur IA actif sur cette machine.</b> Lancez Ollama ou configurez l'IA."
                "</div>",
                unsafe_allow_html=True
            )

    with col_refresh:
        if st.button("🔄 Actualiser", key=f"{key_prefix}_btn_refresh", use_container_width=True, help="Re-scanner les moteurs Ollama et LM Studio"):
            st.rerun()

    with col_cfg:
        _render_ai_config_popover(backends, key_prefix=key_prefix)

    # Aide explicative si aucun backend actif
    if not active_b:
        with st.expander("💡 Comment activer l'IA sur place en 30 secondes ?", expanded=False):
            st.markdown("""
            **LocalScribe fonctionne avec vos moteurs d'IA locaux pour garantir 100% de confidentialité et 0 € de coût :**
            1. **Ollama (Recommandé) :** Téléchargez [Ollama](https://ollama.com) puis lancez la commande suivante dans votre terminal :
               ```bash
               ollama run llama3.2
               ```
               *(ou `ollama run mistral` ou `ollama run qwen2.5:3b`)*.
            2. **LM Studio :** Démarrez votre modèle dans LM Studio et activez le **Local Server** (port 1234).
            3. Cliquez ensuite sur **🔄 Actualiser** ci-dessus : l'application détectera automatiquement le moteur !
            
            *Si vous préférez utiliser votre navigateur, vous pouvez copier les prompts ci-dessous pour ChatGPT ou Claude.*
            """)

    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

    if not transcription_text.strip():
        st.info("ℹ️ Aucune transcription textuelle disponible pour le moment. Réalisez une transcription pour exploiter les fonctionnalités IA.")
        return

    # Organisation en 2 sous-onglets : Templates & Questions/Réponses
    tab_templates, tab_qa = st.tabs([
        "✨ Synthèses & Formats en 1-Clic",
        "💬 Poser une Question sur l'Audio (Q&A)"
    ])

    with tab_templates:
        st.caption("Choisissez une action pour générer instantanément le document souhaité ou copier le prompt.")

        for tpl_id, tpl in AI_TEMPLATES.items():
            with st.container():
                col_t_info, col_t_badge = st.columns([5, 1.2])
                with col_t_info:
                    st.markdown(f"#### {tpl['title']}")
                    st.caption(tpl['description'])
                with col_t_badge:
                    st.markdown(
                        f"<div style='text-align: right;'><span style='background: rgba(46,116,253,0.12); color: {tpl['tag_color']}; "
                        f"border: 1px solid rgba(46,116,253,0.3); padding: 3px 10px; border-radius: 9999px; "
                        f"font-size: 0.75rem; font-weight: 600; display: inline-block; margin-top: 6px;'>"
                        f"{tpl['tag']}</span></div>", 
                        unsafe_allow_html=True
                    )

                # Clé session pour stocker le résultat généré
                res_key = f"ai_result_{key_prefix}_{tpl_id}"
                has_res = res_key in st.session_state and bool(st.session_state[res_key].get("text"))

                col_b_run, col_b_copy_prompt = st.columns([2.5, 3.5])
                
                with col_b_run:
                    btn_label = f"✨ Régénérer ({tpl['title'].split()[1]})" if has_res else f"✨ Générer sur place"
                    disabled_ai = not bool(active_b)
                    help_msg = "Générer directement via l'IA locale" if active_b else "Veuillez d'abord lancer Ollama ou configurer une clé"
                    
                    if st.button(
                        btn_label,
                        key=f"{key_prefix}_btn_gen_{tpl_id}",
                        type="primary" if not has_res else "secondary",
                        use_container_width=True,
                        disabled=disabled_ai,
                        help=help_msg
                    ):
                        with st.spinner(f"Génération en cours via {active_b.upper()} ({active_m})..."):
                            full_prompt = f"{tpl['prompt']}\n\n{transcription_text}"
                            gen_res = generate_ai_response(
                                prompt=full_prompt,
                                system_prompt=tpl.get("system"),
                                backend=active_b,
                                model=active_m,
                                config=cfg
                            )
                            if gen_res.get("success"):
                                st.session_state[res_key] = gen_res
                                st.toast(f"{tpl['title']} généré en {gen_res['elapsed_seconds']}s !", icon="✅")
                            else:
                                st.error(f"Erreur de génération : {gen_res.get('error')}")

                with col_b_copy_prompt:
                    with st.expander("👁️ Consulter / Copier le prompt (pour ChatGPT/Claude)", expanded=False):
                        full_prompt = f"{tpl['prompt']}\n\n{transcription_text}"
                        st.code(full_prompt, language="text")
                        col_c1, col_c2, col_c3 = st.columns(3)
                        with col_c1:
                            if st.button(":material/content_paste: Copier", key=f"{key_prefix}_cp_pr_{tpl_id}", use_container_width=True):
                                if copy_to_clipboard(full_prompt):
                                    st.toast("Prompt copié dans le presse-papier !", icon="📋")
                                else:
                                    st.error("Échec de copie.")
                        with col_c2:
                            st.link_button("🌐 ChatGPT", "https://chatgpt.com", use_container_width=True)
                        with col_c3:
                            st.link_button("🌐 Claude", "https://claude.ai/new", use_container_width=True)

                # Affichage du résultat s'il existe
                if has_res:
                    res_data = st.session_state[res_key]
                    text_out = res_data["text"]
                    elapsed = res_data.get("elapsed_seconds", 0)
                    model_used = res_data.get("model", active_m)
                    backend_used = res_data.get("backend", active_b)

                    with st.container():
                        st.markdown(
                            f"<div style='background: #18181b; border: 1px solid rgba(46,116,253,0.3); border-radius: 8px; padding: 1rem; margin-top: 0.8rem;'>"
                            f"<div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.8rem;'>"
                            f"<span style='color: #10b981; font-weight: 600; font-size: 0.9rem;'>⚡ Généré en {elapsed}s via {backend_used} ({model_used})</span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                        st.markdown(text_out)
                        st.markdown("</div>", unsafe_allow_html=True)

                        # Boutons d'export et de copie du résultat
                        col_r_cp, col_r_dl, col_r_clr = st.columns([2, 2, 1])
                        with col_r_cp:
                            if st.button(f"📋 Copier le résultat", key=f"{key_prefix}_cp_res_{tpl_id}", use_container_width=True):
                                if copy_to_clipboard(text_out):
                                    st.toast("Résultat copié dans le presse-papier !", icon="📋")
                                else:
                                    st.error("Échec de la copie.")
                        with col_r_dl:
                            st.download_button(
                                label="⬇️ Télécharger .md",
                                data=text_out,
                                file_name=f"Synthese_{tpl_id}.md",
                                mime="text/markdown",
                                key=f"{key_prefix}_dl_res_{tpl_id}",
                                use_container_width=True
                            )
                        with col_r_clr:
                            if st.button("🗑️", key=f"{key_prefix}_clr_res_{tpl_id}", help="Effacer ce résultat"):
                                del st.session_state[res_key]
                                st.rerun()

                st.markdown("<hr style='margin: 1.2rem 0; border: none; border-top: 1px solid #27272a;'>", unsafe_allow_html=True)

    with tab_qa:
        st.markdown("#### 💬 Interroger l'enregistrement en langage naturel")
        st.caption("Posez n'importe quelle question sur le contenu (décisions, chiffres, intervenants, citations).")

        qa_session_key = f"ai_qa_history_{key_prefix}"
        if qa_session_key not in st.session_state:
            st.session_state[qa_session_key] = []

        q_col_input, q_col_btn = st.columns([5, 1.2])
        with q_col_input:
            question_input = st.text_input(
                "Votre question :",
                placeholder="Ex : Qui a pris la décision concernant le budget ? Quels sont les prochains jalons ?",
                key=f"{key_prefix}_qa_question_field",
                label_visibility="collapsed"
            )
        with q_col_btn:
            ask_clicked = st.button(
                "✨ Poser la question",
                key=f"{key_prefix}_qa_ask_btn",
                type="primary",
                use_container_width=True,
                disabled=not bool(active_b)
            )

        if ask_clicked:
            if not question_input.strip():
                st.warning("Veuillez saisir une question.")
            else:
                with st.spinner(f"Recherche et analyse en cours via {active_b.upper()}..."):
                    qa_res = ask_ai_about_transcript(
                        question=question_input.strip(),
                        transcript_text=transcription_text,
                        config=cfg
                    )
                    if qa_res.get("success"):
                        st.session_state[qa_session_key].insert(0, {
                            "question": question_input.strip(),
                            "answer": qa_res.get("text", ""),
                            "elapsed": qa_res.get("elapsed_seconds", 0),
                            "model": qa_res.get("model", active_m),
                            "backend": qa_res.get("backend", active_b)
                        })
                        st.toast("Réponse obtenue !", icon="💬")
                    else:
                        st.error(f"Erreur : {qa_res.get('error')}")

        # Historique des questions / réponses
        qa_history = st.session_state[qa_session_key]
        if qa_history:
            st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
            for idx, item in enumerate(qa_history):
                with st.container():
                    st.markdown(f"**❓ Question :** *{item['question']}*")
                    st.markdown(
                        f"<div style='background: #18181b; border: 1px solid rgba(46,116,253,0.25); border-radius: 8px; padding: 0.9rem; margin: 0.5rem 0;'>"
                        f"<div style='margin-bottom: 0.5rem;'><span style='color: #10b981; font-size: 0.8rem;'>⚡ Réponse générée en {item['elapsed']}s ({item['backend']} - {item['model']})</span></div>",
                        unsafe_allow_html=True
                    )
                    st.markdown(item["answer"])
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                    c_qa_cp, c_qa_space = st.columns([2, 4])
                    with c_qa_cp:
                        if st.button("📋 Copier la réponse", key=f"{key_prefix}_cp_qa_{idx}", use_container_width=True):
                            if copy_to_clipboard(item["answer"]):
                                st.toast("Réponse copiée !", icon="📋")
                    st.markdown("<hr style='margin: 0.8rem 0; border: none; border-top: 1px solid #27272a;'>", unsafe_allow_html=True)
        else:
            st.caption("Exemples de questions : *« Quel est le sujet principal ? »*, *« Y a-t-il eu des désaccords exprimés ? »*, *« Fais-moi une liste à puces des citations clés »*.")
