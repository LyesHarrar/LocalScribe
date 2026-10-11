# 🤖 AGENTS.md — Système Opérationnel Agentique (LocalScribe)

Ce document est la **source de vérité comportementale et opérationnelle** pour l'agent IA (Lead Architect & Engineer) en charge du développement de LocalScribe. C'est un **Living Document** (document vivant) qui sera mis à jour de manière autonome à chaque fin de phase ou lors de l'évolution des conventions.

---

## 1. 🧠 Identité et Mission de l'Agent

* **Rôle :** Lead Software Architect & Agentic Workflow Engineer.
* **Projet :** LocalScribe — Application de bureau 100 % locale pour la transcription audio/vidéo.
* **Promesse Produit :** "Zéro Terminal", fluide, accessible aux profils non-techniques, robuste (reprise sur erreur), sécurisée (zéro réseau).
* **Stack Technique :** Python Portable, Streamlit + Shadcn, faster-whisper (CTranslate2), pywebview, multithreading natif.

## 2. 🛡️ Garde-fous et Principes d'Exécution (Anti-Biais de Confirmation)

Pour garantir une qualité irréprochable et éviter de m'enfermer dans mes propres hallucinations ou hypothèses, j'applique les règles suivantes :

1. **La Réalité Prime sur la Théorie (Empirical Verification Rule) :**
   Ma source de vérité *n'est pas* le code que je viens de générer, mais **le résultat de son exécution**. La réussite (tests au vert, rendu visuel parfait) ou l'échec (erreurs, crashs) de l'environnement extérieur prime sur toute déduction interne. Si un test échoue, je remets en question mon approche au lieu de la forcer.
2. **Recherche Proactive (Pre-Flight Research) :**
   Avant chaque implémentation de phase, je dois utiliser mes capacités de recherche (Web, lecture de documentation à jour, MCPs) pour vérifier s'il existe une méthode plus moderne, un framework plus optimisé, ou une pratique UI supérieure à ce qui a été initialement imaginé.
3. **Escalade Proactive (Proactive Escalation) :**
   Si j'identifie qu'une action hors de ma portée (un exécutable système tiers à installer, un choix de design critique, un logiciel de compilation spécifique) peut améliorer radicalement l'application, je dois **suspendre l'exécution et demander explicitement l'autorisation ou l'intervention de l'utilisateur** en lui expliquant le bénéfice.

## 3. 🏗️ Directives Architecturales Inviolables

* **L'UX est Reine :** Aucune console terminale (CMD/bash) ne doit jamais apparaître chez l'utilisateur final. L'interface Streamlit ne doit jamais geler (utilisation stricte de `threading`).
* **Résilience Absolue :** Tout traitement long (comme Whisper) utilise des écritures atomiques (`.tmp`). En cas de crash inopiné, aucune donnée ne doit être corrompue.
* **100% Hors-Ligne :** À l'exception du premier téléchargement du modèle (qui doit se faire via une UI avec barre de progression), l'application ne fait *aucun* call réseau. Zéro télémétrie.

## 4. 🔄 Workflow Agentique par Phase

Pour chaque phase de développement (définies dans le `tech_spec.md`), je suivrai ce protocole :

1. **Planification :** Analyse de la phase, vérification des dépendances, recherche de la meilleure approche actuelle.
2. **Exécution :** Écriture du code modulaire et documenté.
3. **Vérification Autonome :** Lancement de tests, vérification de la syntaxe, et validation empirique.
4. **Mise à jour de l'État :** Actualisation de ce fichier `AGENTS.md` (section 5).

---

## 5. 📍 État d'Avancement du Projet (Living State Tracker)

*Ceci est le tracker de l'agent. Il reflète l'état réel et vérifié du projet.*

- [x] **Documentation Initiale** : PRD et Spécifications Techniques générées et validées.
- [x] **Initialisation Agentique** : `AGENTS.md` créé.
- [x] **Phase 0 — Scaffolding** : *Arborescence, UI de base et config terminées.*
- [x] **Phase 1 — Moteur & Threading** : *Implémentée et validée (profiler, formatteur, moteur).*
- [x] **Phase 2 — UI & UX** : *Interface Streamlit complète (upload, multithread, templates LLM, design modernisé).*
- [x] **Phase 3 — Desktop & Lanceur** : *Implémentée (run_app.py pywebview, détection WebView2, launcher.py et LocalScribe.exe).*
- [x] **Version 1.1 — Fonctionnalités Audio Avancées** : *Implémentée (traduction anglaise directe, sélection 99 langues, filtre VAD Silero, prompt/vocabulaire, métriques de confiance).*
- [x] **Version 1.2 — Diarisation des Locuteurs (Speaker Diarization)** : *Implémentée et validée (sherpa-onnx 100% hors-ligne & zéro token, segmentation PyAnnote ONNX + embedding CAM++, alignement Whisper, renommage interactif des locuteurs, 32/32 tests au vert).*
- [x] **Version 1.3 — Historique Persistant & Recherche (SQLite)** : *Implémentée et validée (persistance automatique mono/batch, recherche textuelle plein champ, consultation et téléchargements rétroactifs, suppression/nettoyage, 36/36 tests au vert).*
- [x] **Version 1.4 — Distribution Portable Zéro Dépendance** : *Implémentée et validée (pipeline de packaging desktop/package_portable.py, CPython autonome embarqué sans installation requise, bootstrap launcher LocalScribe.exe ultra-léger avec fallback WebView2/navigateur et boîtes d'alerte natives ctypes, 46/46 tests au vert).*
- [x] **Version 1.5 — Copie Presse-Papier 1-Clic** : *Implémentée et validée (module core/clipboard.py multi-plateforme avec replis pyperclip/Win32 ctypes/PowerShell/pbcopy/wl-copy, boutons d'action rapide dans l'UI résultats, dans chaque onglet TXT/MD/SRT, dans les templates LLM et dans chaque fiche de l'historique, 53/53 tests au vert).*
- [x] **Version 1.6 — Traitement par Lot & File d'Attente Multi-Fichiers (Batch Processing)** : *Implémentée et validée (dropzone multi-fichiers drag & drop avec accept_multiple_files, file d'attente séquentielle à la chaîne en thread d'arrière-plan, chargement unique du modèle Whisper, double barre de progression globale et par fichier, écritures atomiques, persistance SQLite individuelle, téléchargement global ZIP en mémoire, copie 1-clic de tout le lot, fiches interactives par fichier avec aperçu et exports individuels, 56/56 tests au vert).*
- [x] **Version 1.7 — Traduction Multilingue 100% Hors-Ligne (NLLB-200 / CTranslate2)** : *Implémentée et validée (traduction neuronale multilingue 24 langues via Meta NLLB-200 INT8 & CTranslate2, zéro réseau, préservation des balises locuteurs et des timecodes SRT, intégration batch & mono-fichier, onglet dédié UI avec copie 1-clic et téléchargements TXT/SRT/MD, intégration historique SQLite, 63/63 tests au vert).*
- [x] **Version 1.8 — Éditeur Audio-Texte Interactif & Synchronisé** : *Implémentée et validée (lecteur karaoké synchronisé avec défilement et mise en surbrillance automatique en temps réel, saut au timecode au clic, outil de recherche et remplacement global, fusion et découpage de segments, édition en grille tabulaire st.data_editor, sauvegarde atomique et mise à jour de l'historique SQLite, 75/75 tests au vert).*
- [x] **Version 1.9 — Prétraitement Audio Intelligent & Extraction Rapide (FFmpeg Optimiseur)** : *Implémentée et validée (extraction audio ultra-rapide des flux vidéo .mp4/.mkv/.avi/.webm en WAV 16kHz mono 16-bit, égalisation dynamique Auto-Gain via dynaudnorm pour amplifier les voix chuchotées/faibles, réduction de bruit passe-bande et filtre spectral afftdn, repli automatique sans crash si FFmpeg absent, zéro pop-up terminal CREATE_NO_WINDOW, intégration complète mono-fichier/batch/dossier, suppression garantie des temporaires atomiques, 82/82 tests au vert).*
- [x] **Version 2.0 — Notifications Natives Windows & Estimation du Temps Restant (ETA & Vitesse)** : *Implémentée et validée (calculateur d'ETA en temps réel et facteur de vitesse de traitement unitaire et par lot, bandeau dynamique sous la barre de progression, notifications toast natives Windows 10/11 sans console CREATE_NO_WINDOW avec carillon sonore discret, cartes métriques de temps de calcul et vitesse réelle, 99/99 tests au vert).*
- [x] **Distribution Clé-en-Main Standalone 100% Hors-Ligne (Packaging v2 & Conformité Légale)** : *Implémentée et validée (FFmpeg autonome embarqué dans bin/ et injecté dans PATH, modèle Whisper pré-embarqué dans models/ sans téléchargement nécessaire, conformité légale LICENSE MIT et LICENSES-THIRD-PARTY.txt, mise à jour du pipeline package_portable.py, tests d'intégrité, 101/101 tests au vert).*
- [x] **Version 2.1 — Attribution d'Auteur & Vérificateur de Mises à Jour (GitHub Releases)** : *Implémentée et validée (module core/version.py centralisant __version__, __author__ et __github_repo__, en-tête moderne avec badge v2.0.0, lien direct GitHub repo et profil, popover interactif "À propos & Mises à jour" avec vérificateur GitHub Releases 100% Privacy-First sans télémétrie, intégration README et bundle portable, 108/108 tests au vert).*
- [x] **Accélération GPU NVIDIA Automatique & Résolution Dynamique cuBLAS** : *Implémentée et validée (détection et configuration automatique des DLLs NVIDIA cuBLAS 12 / cuDNN 9 sous Windows sans manipulation manuelle de PATH ni console terminale, déblocage complet de l'accélération GPU float16 sur GeForce RTX 3060, repli résilient garanti sur CPU multithreadé int8, 114/114 tests au vert).*
- [x] **Optimisation UX & Contrôle de Vitesse Décodage (Navigation Lock & Fast Beam)** : *Implémentée et validée (verrouillage de la navigation pendant la transcription avec bannière informative, widget de suivi de tâche épinglé dans la barre latérale avec bouton d'interruption dédié, désactivation immédiate des boutons de lancement pour éliminer tout clignotement, optimisation de la vitesse par désactivation de l'Auto-Gain lourd par défaut, sélecteur de mode de décodage Rapide Beam 1 vs Précis Beam 5, 116/116 tests au vert).*
- [x] **Version 2.2 — Simplification UX Non-Technique & Jauge d'Impact Dynamique (Solution Complète)** : *Implémentée et validée (3 profils 1-clic macro Éclair/Équilibré/Studio + Personnalisé, jauge interactive dynamique vitesse/précision/ETA avec core/impact_estimator.py sans parsing markdown buggé via st.html, accordéon replié d'options avancées progressive disclosure, en-tête aéré avec boutons popover pleine largeur sans rognage, 124/124 tests au vert).*
- [x] **Harmonisation Version v2.2.1 & Packaging Portable** : *Implémentée et validée (constante __version__ = '2.2.1' dans core/version.py et tests unitaires alignés, 124/124 tests au vert).*
- [x] **Version 2.3 — Historique des Dossiers & Suivi d'Avancement des Lots (Batch Runs)** : *Implémentée et validée (table SQLite batch_runs persistante, suivi de session temps réel début/interruption/fin, carte de synthèse du dernier dossier traité avec jauge d'avancement %, compteurs restants/déjà transcrits, bouton de reprise en 1-clic vers le Mode Dossier, ouverture directe dans l'Explorateur Windows, historique complet des lots précédents, 128/128 tests au vert).*
- [x] **Version 2.4 — Studio IA & Synthèse sur place (Ollama, LM Studio & Q&A Interactif)** : *Implémentée et validée (moteur multi-backend core/local_ai_engine.py auto-détectant Ollama et LM Studio locaux avec 0 Mo ajouté au bundle sans dépendance binaire lourde, repli optionnel Cloud BYOK, 5 actions d'analyse en 1-clic : Synthèse exécutive, Plan d'action & To-Do, Chapitrage horodaté, Article de publication, Réécriture stylistique, module de Q&A interactif en langage naturel sur la transcription, intégration universelle résultats unitaire, lots et bibliothèque d'historique, 142/142 tests au vert).*
- [x] **Audit Complet & Durcissement Global (v2.4.1 — Résilience, Performance & Caching)** : *Implémentée et validée (import tempfile manquant corrigé dans translation_engine.py, fermeture propre du flux HTTPError urllib dans version.py, résilience par fichier dans les lots et correction du bug critique base_name NameError dans transcription_engine.py, mise en cache TTL 30s de la détection Ollama/LM Studio dans local_ai_engine.py éliminant les lags de rendu UI, stabilisation des clés de widgets par ID de segment dans editor_component.py éliminant les collisions de texte lors des fusions/suppressions, mémoïsation du DDL init_db dans history_manager.py réduisant l'overhead DB, assainissement strict des uploads contre le path traversal dans app.py, 148/148 tests au vert).*
- [x] **Correctif Lanceur Desktop & Affichage Fenêtre Native** : *Résolu et validé (suppression de STARTF_USESHOWWINDOW/SW_HIDE dans desktop/launcher.py qui forçait la fenêtre pywebview WinForms/WebView2 à demeurer masquée sous Windows, ajout de l'appel forcé ShowWindow(hwnd, SW_SHOW) et SetForegroundWindow dans desktop/run_app.py on_shown, recompilation de LocalScribe.exe via PyInstaller, test unitaire dédié sans régression, 149/149 tests au vert, validation empirique de l'apparition visible de la fenêtre HWND IsVisible: 1).*

---
*Dernière mise à jour par l'Agent : Correctif d'affichage du lanceur LocalScribe.exe validé avec succès (149/149 tests au vert).*

