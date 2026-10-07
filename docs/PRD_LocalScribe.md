# 📘 PRD & Spécifications Techniques : "LocalScribe"

**Statut :** Approuvé pour développement (Phase MVP)
**Auteur :** Lyes Harrar
**Packaging UX Validé :** Fenêtre d'Application Dédiée (`pywebview`) avec Python Portable embarqué.

---

## 1. Vision et Proposition de Valeur
**Objectif :** Créer un outil de bureau 100 % local, gratuit et privé, permettant de transcrire des fichiers audio/vidéo sans limite de durée. Il sert de pont direct entre le contenu brut (Cours, Webinaires, Streams) et les LLMs pour générer des synthèses d'experts, ou pour exporter des sous-titres.

**Cibles Utilisateurs :**
1. **Le Pro de la Tech / Apprenant :** Veut extraire la connaissance de dossiers massifs de cours vidéo (Cours, Masterclass, Webinaires, Conférences) en formatant les textes pour Claude/Gemini.
2. **Le Créateur de Contenu :** Streamers (Twitch) ou podcasteurs fuyant les SaaS payants à la minute, nécessitant une transcription gratuite (.srt) pour des VODs très longues (> 2h).
3. **Le Professionnel (Confidentialité) :** Journalistes ou psychologues ou cadres voulant transcrire des réunions (Zoom/Teams) ou enregistrements sans qu'aucune donnée ne quitte leur machine locale.
4. **Etudiants : en medecine, avocats et domaines ou il est utile d'extraire une trascription comme l'enregistrement des conseils d'un pro pour le transformer/l'organiser en conseils/méthodes actionnables a travers un LLM par la suite.

---

## 2. L'Expérience Utilisateur (UX) & Architecture
Le logiciel repose sur le principe du **"Zéro Terminal, Zéro Installation Système"** :

* **Interface (UI) :** Front-end Web local propulsé par `Streamlit`.
* **Encapsulation :** Utilisation de `pywebview` (ou Edge Chromium WebView2) pour afficher l'interface dans une fenêtre native Windows/Mac. Aucun onglet de navigateur visible, aucune URL, aucune console noire.
* **Environnement :** Python Portable embarqué. Le dossier contient sa propre version de Python. Un double-clic sur le lanceur suffit, garantissant un fonctionnement universel sans altérer le PC de l'utilisateur.

---

## 3. Direction Artistique & UI Design (Design System)
L'outil doit s'éloigner de l'aspect "Script Data Science" pour adopter une esthétique "SaaS Moderne" (façon Notion, Framer, Julian.com).

* **Typographie :** Utilisation stricte de la police **`Inter`** (ou système sans-serif moderne) pour une lisibilité optimale.
* **Palette de Couleurs ("Dim Mode" Reposant) :**
* **Composants :** Intégration de `streamlit-shadcn-ui` (si applicable) ou du CSS Tailwind-like pour des boutons épurés, des switches modernes et des bordures douces. Le fichier `.streamlit/config.toml` devra forcer ces paramètres esthétiques.

---

## 4. User Stories & Critères d'Acceptation (Machine-Readable pour IA)

### US-01 : Transcription Batch et "Smart Resume" (Anti-Crash)
**Intention :** L'utilisateur cible un dossier ; le logiciel traite toutes les vidéos sans corrompre les données en cas d'arrêt brutal (coupure de courant, fermeture accidentelle).
**Critères d'acceptation (Predicates) :**
- [ ] L'UI propose le choix entre "Fichier unique" et "Dossier cible". L'input accepte un chemin absolu valide.
- [ ] La recherche (`rglob`) cible `[.mp4, .mkv, .avi, .webm, .mp3, .wav, .m4a]`.
- [ ] **Écriture Atomique (CRITIQUE) :** L'inférence s'écrit dans un fichier temporaire `[nom_video].md.tmp`.
- [ ] Ce n'est qu'à la complétion (100 %) que le `.tmp` est renommé en `.md` ou `.txt`.
- [ ] Règle de saut : La vidéo est ignorée *uniquement* si le fichier final `.md` existe et que `st_size > 0`. Si un `.tmp` est détecté au lancement, il est écrasé.

### US-02 : Profilage Matériel (Graceful Degradation)
**Intention :** L'outil détecte dynamiquement le matériel au lancement et adapte ses paramètres pour éviter tout crash `Out of Memory`.
**Critères d'acceptation :**
- [ ] Le script `hardware_profiler.py` sonde le système (NVIDIA CUDA, Apple Silicon MPS, ou CPU).
- [ ] **VRAM > 6Go :** Modèle `medium` (float16) par défaut. Toutes options activées.
- [ ] **VRAM < 4Go :** Modèle `small` recommandé. Avertissement affiché.
- [ ] **Apple Silicon :** Modèle `medium` (int8) via accélération Metal/CPU.
- [ ] **CPU :** Modèle `base/small` (int8). Options lourdes comme la Diarisation sont grisées (disabled) dans l'UI.

### US-03 : Estimation du Temps et Monitoring
**Intention :** L'utilisateur a une vision claire de l'avancement d'un traitement massif.
**Critères d'acceptation :**
- [ ] L'UI affiche une barre de progression globale (ex: *Vidéo 3 / 15*).
- [ ] Un chronomètre (`time.time()`) mesure la durée de chaque inférence.
- [ ] L'UI affiche dynamiquement le temps écoulé pour le fichier en cours ou précédent.
- [ ] Les métadonnées YAML du fichier Markdown généré incluent : `Temps de traitement : X min Y sec` et le modèle utilisé.

### US-04 : Options d'Export & Formatage (UI Checkboxes)
**Intention :** Paramétrer les sorties textuelles selon les besoins métiers variés.
**Critères d'acceptation :**
- [ ] Checkbox : Insertion de Timestamps `[MM:SS]` toutes les X minutes dans le texte.
- [ ] Checkbox : Génération simultanée d'un sous-titre `.srt` standard (pour les créateurs).
- [ ] Checkbox : Génération d'un fichier global `INDEX_COURS.md` listant les fichiers traités.
- [ ] Checkbox : Création d'un dossier miroir `Transcriptions_Exports` isolant les `.md` de leurs vidéos lourdes.
- [ ] Checkbox : Alerte sonore / Notification système en fin de traitement de lot.

### US-05 : Agencement de l'Interface & Exploitation LLM
**Intention :** Offrir une expérience logicielle robuste.
**Critères d'acceptation :**
- [ ] **Sidebar (`st.sidebar`) :** Utilisée pour les réglages techniques (Modèle, Checkboxes d'export, Profil matériel).
- [ ] **Main Area :** Réservée à l'action (Chemin du dossier, Bouton Lancer, Progress Bar, Logs d'état via `st.status`).
- [ ] **State Management :** Le bouton "Lancer" devient inactif (`disabled=True`) pendant le calcul.
- [ ] **Générateur de Prompts :** Un onglet ou bouton permet de fusionner la transcription avec un "Template PM" et de le copier dans le presse-papier pour Claude/Gemini.

---

## 5. Structure du Repository Cible

```text
LocalScribe/
│
├── core/
│   ├── hardware_profiler.py     # Détection GPU/CPU et adaptation dynamique
│   ├── transcription_engine.py  # Moteur Whisper, Fichiers .tmp, gestion FFmpeg
│   └── text_formatter.py        # Markdown YAML, SRT, Dossier Miroir, Index
│
├── ui/
│   ├── app.py                   # Interface Streamlit (Layout, Shadcn, State)
│   └── prompts_templates.py     # Templates LLM (PM, Synthèse)
│
├── desktop/
│   └── run_app.py               # Wrapper pywebview pour fenêtre native
│
├── .streamlit/
│   └── config.toml              # Thème esthétique (Couleurs Slate, Police)
│
├── requirements.txt             # Dépendances (Streamlit, faster-whisper...)
├── install.bat                  # Script de création venv + portabilité
├── run_LocalScribe.bat          # Lanceur silencieux appelant desktop/run_app.py
└── README.md                    # Documentation (Configuration requise matérielle)
```