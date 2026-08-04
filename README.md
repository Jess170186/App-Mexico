# App Mexico — Agrégateur d'événements automatique

Ce dossier contient le « cerveau » qui alimente l'app **App Mexico** :
il va chercher tout seul les événements du **Quintana Roo** et du **Yucatán**
sur les sites officiels, en extrait pour chacun **titre, date, lieu, catégorie,
description, image et lien source**, puis écrit un fichier `events.json` que
l'application lit et affiche. Tout se fait grâce à **ta clé API Claude**.

```
Sites officiels ──► aggregator.py (API Claude) ──► events.json ──► l'app App Mexico
   (SITUR, Mérida,        extrait + résume            se met à jour toute seule
    Yucatán, presse)      + récupère image/lien
```

## Contenu

| Fichier | Rôle |
|---|---|
| `aggregator.py` | Le pipeline : récupère, extrait via Claude, dédoublonne, écrit `events.json` |
| `events.json` | Le résultat (exemple fourni ; régénéré à chaque exécution) |
| `requirements.txt` | Dépendances Python |
| `.github/workflows/update-events.yml` | Exécution automatique toutes les 6 h (GitHub Actions) |
| `places_sync.py` | (Option payante) Synchronise le répertoire avec Google Maps (notes ★ + photos) |
| `osm_extract.py` | **(Gratuit, recommandé)** Extraction mensuelle depuis OpenStreetMap → `repertoire.xlsx` + `places.json` |
| `places.json` | Le répertoire (restaurants, plages, bars…) que lit l'app |
| `repertoire.xlsx` | Le tableur lisible/éditable généré chaque mois |

## 1. Mise en route (test local, 5 minutes)

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."   # ta clé API Claude
python aggregator.py
```

Le script affiche les sources traitées et écrit un `events.json` à jour.

## 2. Ta clé API Claude

Crée-la sur **console.anthropic.com → API Keys**, puis fournis-la au script
via la variable d'environnement `ANTHROPIC_API_KEY` (ne l'écris jamais en dur
dans le code). Le modèle utilisé par défaut est `claude-sonnet-4-5` (rapide et
peu coûteux pour de l'extraction) ; change `MODEL` en haut du fichier si besoin.

**Coût indicatif :** l'extraction d'une page coûte quelques centimes. Avec 4
sources rafraîchies toutes les 6 h, on reste sous quelques dollars par mois.

## 3. Ajouter / retirer des sources

Ouvre `aggregator.py` et modifie la liste `SOURCES` (nom, région, URL de la
page d'agenda). Aucune autre modification n'est nécessaire : Claude s'adapte à
la mise en page de chaque site.

## 4. Rendre la mise à jour 100 % automatique

Trois options, de la plus simple à la plus robuste :

**a) GitHub Actions (recommandé, gratuit).** Mets ce dossier dans un dépôt
GitHub. Dans *Settings → Secrets and variables → Actions*, ajoute un secret
`ANTHROPIC_API_KEY`. Le workflow fourni régénère `events.json` toutes les 6 h et
le publie. Sers ensuite le fichier via *GitHub Pages* ou le lien « raw ».

**b) Cron sur un serveur.** `0 */6 * * * cd /chemin && ANTHROPIC_API_KEY=... python aggregator.py`

**c) Fonction planifiée** (AWS Lambda + EventBridge, Google Cloud Scheduler,
Vercel Cron…) qui appelle le script.

## 5. Brancher l'app sur le flux

Dans le fichier de l'app (`peninsula-prototype.html`), en haut du script :

```js
const EVENTS_URL = 'https://TON-DOMAINE/events.json'; // l'URL publique de ton events.json
```

Au chargement, l'app récupère ce fichier et affiche les événements à jour
(image, description, lien source) ; si l'URL n'est pas joignable, elle retombe
sur les données de démonstration intégrées. Le petit tampon « maj AAAA-MM-JJ »
dans l'agenda confirme la fraîcheur des données.

## 6. Synchronisation du répertoire avec Google Maps

`places_sync.py` garde le répertoire de lieux (restaurants, plages, bars, activités,
transports, commerces) **à jour à partir de Google Maps** :

- **Validation** : pour chaque lieu, on vérifie `businessStatus`. Un lieu **fermé**
  (`CLOSED_PERMANENTLY`) ou introuvable est **retiré** automatiquement.
- **Corrections** : note, adresse, coordonnées et site web sont mis à jour.
- **Photos** : la 1re photo Google de l'adresse est **téléchargée** dans `images/`
  puis servie depuis ton hébergement (l'app affiche `img`). On ne met jamais la clé
  Google dans l'app — les photos passent par toi.
- **Règle d'inclusion (100 %)** : **tout lieu noté 3 étoiles et plus** (`rating ≥ 3.0`)
  sur Google entre dans l'app, pour **toutes les catégories** (restos, activités, plages,
  transports, bars, commerces). La découverte balaie chaque ville par **quadrillage**
  (plusieurs points × types), car l'API renvoie au maximum 20 résultats par appel —
  le quadrillage permet d'approcher une couverture complète. Seuil réglable via
  `MIN_RATING` en haut de `places_sync.py`.

Mise en route :

```bash
export GOOGLE_MAPS_API_KEY="AIza..."   # API « Places API (New) » activée dans Google Cloud
python places_sync.py                  # écrit places.json + images/
```

Puis, dans l'app, pointe `PLACES_URL` vers ton `places.json` public (comme `EVENTS_URL`),
et héberge le dossier `images/` sur le domaine indiqué dans `IMG_BASE_URL`.

**Clé & coûts.** Crée la clé dans Google Cloud Console (activer *Places API (New)*),
restreins-la (par API + référent/IP). Google offre un crédit mensuel ; au-delà, Text
Search / Nearby / Details / Photos sont facturés à l'usage — vérifie la grille
[tarifaire officielle](https://developers.google.com/maps/documentation/places/web-service/usage-and-billing).
⚠️ La couverture « 3★ et + à 100 % » multiplie les appels (villes × catégories × points du
quadrillage + une photo par lieu) : lance la synchro complète peu souvent (1×/jour ou /semaine)
et ne re-télécharge pas une photo déjà présente (le script saute les fichiers existants).
Le champ « WiFi gratuit » n'est pas fiable via l'API : garde-le manuel ou déduis-le des avis.

**Note légale (Google).** Les données/photos Google Maps sont soumises aux conditions
Google : elles servent à afficher l'info dans ton app avec attribution ; ne les
revends pas telles quelles et respecte les règles d'affichage de Google.

## 7. Option GRATUITE : répertoire mensuel via OpenStreetMap (recommandé)

Pour **ne rien payer**, `osm_extract.py` remplace la synchro Google : il interroge
**OpenStreetMap** (API Overpass, gratuite, sans clé, sans carte bancaire) pour tout le
**Quintana Roo** et le **Yucatán**, et produit une fois par mois :

- **`repertoire.xlsx`** — le tableur que tu voulais : Nom · Catégorie · Ville · Région ·
  Adresse · Description · Téléphone · Site web · Image URL · Note · Lat · Lng.
- **`places.json`** — chargé automatiquement par l'app.

```bash
pip install -r requirements.txt
python osm_extract.py       # écrit repertoire.xlsx + places.json
```

**Automatique le 1er de chaque mois** : le workflow `.github/workflows/update-places-osm.yml`
lance l'extraction et publie les fichiers (aucune clé requise). Sers ensuite `places.json`
via une URL publique (GitHub Pages) et pointe `PLACES_URL` de l'app dessus.

**Ce qu'OpenStreetMap donne / ne donne pas.** Il fournit nom, adresse, téléphone, site web,
catégorie, ville et coordonnées — gratuitement et sans limite. En revanche il **n'a ni note
en étoiles ni photo**. Le script applique donc un **filtre qualité** (on ne garde que les
lieux « établis » : nom + adresse **ou** téléphone **ou** site web) à la place du « 3★+ »,
et l'app affiche ses **visuels par catégorie** au lieu de photos. Colonnes « Image URL » et
« Note » restent vides — tu peux les remplir à la main pour tes lieux vedettes si tu veux.

> Besoin des vraies étoiles + photos plus tard ? Reprends `places_sync.py` (Google, payant
> au-delà du crédit gratuit). Les deux écrivent le même `places.json`.

## Note légale (important)

L'agrégateur ne recopie pas les articles : il ne conserve que les **faits**
(titre, date, lieu) et un **résumé reformulé**, et renvoie **toujours vers la
source** via `source_url`. Pour un usage commercial, privilégie les sources qui
offrent un flux officiel et, idéalement, obtiens un accord de republication
auprès des offices de tourisme et municipalités partenaires.
