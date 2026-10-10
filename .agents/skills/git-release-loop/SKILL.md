---
name: git-release-loop
description: >-
  Automatise la boucle Git complète : exécution des tests unitaires, commit conventionnel,
  push de la branche courante, bascule sur main, pull origin main, fusion (--no-ff),
  push sur origin main, et suppression locale et distante de la branche secondaire.
  Déclenché par des expressions comme "fais la boucle habituelle", "boucle git",
  "commit push merge et supprime la branche".
---

# Git Release Loop (Boucle Git Complète)

## Overview
Ce skill standardise et automatise l'intégralité du cycle de release Git pour le projet LocalScribe.
Il garantit la stabilité du code grâce à la validation des tests avant toute action Git,
maintient un historique propre avec des commits conventionnels, fusionne sur `main` sans écrasement
d'historique (`--no-ff`), synchronise avec GitHub et supprime proprement la branche secondaire de travail.

## Dependencies
- `git` CLI opérationnel avec accès configuré au dépôt distant (`origin`).
- `python` environnement actif avec la suite de tests du projet (`tests/test_*.py`).

## Quick Start / Déclencheurs
Activez ce skill dès que l'utilisateur prononce l'une des requêtes suivantes :
- *"fais la boucle habituelle"*
- *"boucle git"*
- *"commit, push, valide la PR, checkout main, pull et supprime la branche"*
- *"merge sur main et supprime la branche courante"*

---

## Workflow Détaillé

Suivez scrupuleusement les 7 étapes séquentielles ci-dessous :

### 1. Pré-requis & Détection de Branche
1. Obtenez le nom de la branche active :
   ```powershell
   git branch --show-current
   ```
2. **Garde-fou :** Si la branche courante est `main` ou `master` :
   - **Interrompez immédiatement la séquence.**
   - Avertissez l'utilisateur : *"Vous êtes déjà sur la branche principale main. Impossible d'exécuter la boucle de fusion/suppression de branche secondaire."*
   - Proposez uniquement de commiter et pusher directement sur `main`.

### 2. Validation des Tests Unitaires (Qualité Garantie)
Avant de toucher à Git, lancez la suite complète de tests de non-régression :
```powershell
python -m unittest discover -s tests -p "test_*.py"
```
- **Si les tests échouent :** **ARRÊTEZ TOUT.** Ne faites aucun commit. Affichez l'erreur rencontrée à l'utilisateur pour résolution.
- **Si tous les tests sont au vert :** Poursuivez vers l'étape 3.

### 3. Staging & Commit Conventionnel
1. Inspectez les fichiers modifiés et non-suivis :
   ```powershell
   git status
   ```
2. Ajoutez tous les fichiers du livrable :
   ```powershell
   git add .
   ```
3. Créez un commit au format Conventionnel (`feat:`, `fix:`, `chore:`, `docs:`) résumant fidèlement le travail effectué :
   ```powershell
   git commit -m "<type>(<scope>): <résumé court en français>" -m "<détails des réalisations sous forme de tirets>"
   ```

### 4. Push de la Branche de Travail
Poussez la branche locale vers le remote `origin` :
```powershell
git push origin <nom-de-la-branche>
```

### 5. Bascule & Synchronisation sur `main`
1. Basculez sur la branche principale :
   ```powershell
   git checkout main
   ```
2. Mettez à jour `main` avec les derniers changements du dépôt distant :
   ```powershell
   git pull origin main
   ```

### 6. Fusion & Push sur `origin/main`
1. Fusionnez la branche de travail dans `main` avec création d'un merge commit explicite :
   ```powershell
   git merge <nom-de-la-branche> --no-ff -m "Merge branch '<nom-de-la-branche>' into main"
   ```
2. Poussez la branche `main` fusionnée vers le dépôt distant :
   ```powershell
   git push origin main
   ```

### 7. Nettoyage de la Branche Secondaire
Une fois la fusion confirmée sur `main` et poussée sur `origin` :
1. Supprimez la branche locale :
   ```powershell
   git branch -d <nom-de-la-branche>
   ```
2. Supprimez la branche distante sur GitHub :
   ```powershell
   git push origin --delete <nom-de-la-branche>
   ```
3. Vérifiez l'état final :
   ```powershell
   git status
   ```
4. Affichez un récapitulatif clair et ordonné des actions exécutées avec les identifiants de commit.

---

## Gestion des Erreurs & Cas Limites

| Situation | Action à Entreprendre |
| :--- | :--- |
| **Échec des tests à l'étape 2** | Stoppe net. Ne commite pas. Rapporte les assertions échouées. |
| **Branche courante = `main`** | Refuse la boucle (évite toute suppression accidentelle de `main`). |
| **Conflit lors du merge sur `main`** | Alerte l'utilisateur, liste les fichiers en conflit, ne force jamais sans confirmation. |
| **Branche non mergée lors du `git branch -d`** | N'utilisez `-D` qu'après avoir revérifié formellement que tous les commits sont bien sur `main` (`git log main..<branche>` vide). |

## Common Mistakes
1. **Oublier les tests avant le commit :** Risque de pousser du code cassé sur `main`. Toujours exécuter `unittest` en étape 2.
2. **Utiliser un fast-forward silencieux (`git merge`) :** Toujours spécifier `--no-ff` pour préserver la traçabilité de la feature/fix dans le graphe Git.
3. **Supprimer la branche avant de pusher `main` :** Toujours valider le `git push origin main` avant d'exécuter `git branch -d` et `git push origin --delete`.
