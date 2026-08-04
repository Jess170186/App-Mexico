# Mettre le répertoire en pilote automatique (GitHub — gratuit)

Objectif : que l'extraction OpenStreetMap tourne **toute seule le 1er de chaque mois**
et publie `repertoire.xlsx` + `places.json`, sans que tu touches à rien.

## A. Créer le dépôt
1. Va sur **github.com** et crée un compte gratuit (si tu n'en as pas).
2. Clique **New repository** (bouton vert).
3. Nom : `peninsulalive-data` · coche **Public** · clique **Create repository**.

## B. Déposer les fichiers du dossier
4. Décompresse `peninsulalive-aggregator.zip` sur ton ordinateur.
5. Sur la page du dépôt → **Add file → Upload files**.
6. Glisse **tout le contenu** du dossier décompressé (fichiers **et** le dossier `.github`).
   - Sur Mac, si tu ne vois pas le dossier `.github` : dans le Finder, appuie sur
     **Cmd + Maj + .** pour afficher les fichiers cachés.
   - Clique **Commit changes**.
   - (Si le dossier `.github` ne monte pas : onglet **Actions → New workflow →
     “set up a workflow yourself”**, colle le contenu de `update-places-osm.yml`, Commit.)

## C. Lancer une première fois
7. Onglet **Actions** → si demandé, clique **I understand… enable workflows**.
8. Choisis **« Répertoire mensuel (OpenStreetMap, gratuit) »** → **Run workflow → Run**.
9. Attends 1–3 min (point vert ✓). Le dépôt contient maintenant `repertoire.xlsx` et
   `places.json` remplis avec les vraies données OSM.

## D. Publier `places.json` (pour l'app)
10. **Settings → Pages** → *Source* : **Deploy from a branch** → Branch : **main / (root)** → **Save**.
11. Après ~1 min, ton fichier est en ligne à :
    `https://TON-UTILISATEUR.github.io/peninsulalive-data/places.json`

## E. Brancher l'app
12. Dans l'app (`peninsula-prototype.html`), remplace la ligne :
    `const PLACES_URL='places.json';`
    par ton URL ci-dessus. (Ou envoie-moi l'URL, je le fais.)

C'est tout. Chaque 1er du mois, la liste se met à jour automatiquement. ✅
