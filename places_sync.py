#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
App Mexico — Synchronisation du répertoire avec Google Maps
==============================================================
Pour chaque lieu du répertoire, ce script interroge l'API Google Places (New) afin de :
  • VALIDER qu'il existe toujours (businessStatus) — les lieux FERMÉS sont retirés,
  • CORRIGER les infos (note, adresse, coordonnées, site web),
  • RÉCUPÉRER une PHOTO Google de l'adresse (téléchargée en local pour ne pas exposer la clé),
  • DÉCOUVRIR de nouveaux lieux populaires par ville et catégorie (recherche à proximité).
Il écrit places.json (le format que lit l'app App Mexico).

Utilisation :
    export GOOGLE_MAPS_API_KEY="AIza..."      # API « Places API (New) » activée
    pip install -r requirements.txt
    python places_sync.py

⚠️  Sécurité : on NE met JAMAIS la clé Google dans l'app. Les photos sont téléchargées
    ici (dossier images/) et servies depuis TON hébergement ; l'app n'appelle jamais Google.
"""

import os, re, json, time, pathlib, requests

API_KEY = os.environ["GOOGLE_MAPS_API_KEY"]
BASE = "https://places.googleapis.com/v1"
IMG_DIR = pathlib.Path(__file__).parent / "images"
IMG_BASE_URL = "https://TON-DOMAINE/images"      # ⬅️ où tu héberges le dossier images/
OUTPUT = pathlib.Path(__file__).parent / "places.json"
IMG_DIR.mkdir(exist_ok=True)

# Villes de référence (centre pour la découverte + rattachement)
CITY = {
    "Cancún": ("Quintana Roo", 21.161, -86.851), "Playa del Carmen": ("Quintana Roo", 20.629, -87.073),
    "Tulum": ("Quintana Roo", 20.211, -87.465), "Bacalar": ("Quintana Roo", 18.680, -88.395),
    "Cozumel": ("Quintana Roo", 20.422, -86.922), "Holbox": ("Quintana Roo", 21.522, -87.379),
    "Mérida": ("Yucatán", 20.967, -89.624), "Valladolid": ("Yucatán", 20.688, -88.202),
    "Progreso": ("Yucatán", 21.282, -89.665), "Chichén Itzá": ("Yucatán", 20.684, -88.568),
    "Uxmal": ("Yucatán", 20.360, -89.771), "Izamal": ("Yucatán", 20.934, -89.017),
}
# Nos catégories -> type Google (pour la découverte)
CAT_TYPE = {"Restaurantes": "restaurant", "Actividades": "tourist_attraction",
            "Playas": "beach", "Transporte": "transit_station", "Bares": "bar",
            "Compras": "shopping_mall"}

# ⭐ RÈGLE D'INCLUSION : tout lieu noté 3 étoiles ET PLUS entre dans l'app (100 %).
MIN_RATING = 3.0

# Quadrillage autour de chaque ville : Nearby (New) renvoie max 20 lieux par appel,
# donc on balaie plusieurs points pour approcher une couverture complète.
TILES = [(0, 0), (0.03, 0), (-0.03, 0), (0, 0.03), (0, -0.03),
         (0.03, 0.03), (-0.03, -0.03), (0.03, -0.03), (-0.03, 0.03),
         (0.06, 0), (-0.06, 0), (0, 0.06), (0, -0.06)]

# Lieux déjà répertoriés à revalider (nom + ville + catégorie)
SEED = [
    ("La Chaya Maya", "Mérida", "Restaurantes"), ("Hartwood", "Tulum", "Restaurantes"),
    ("Rosa Negra", "Cancún", "Restaurantes"), ("Chichén Itzá", "Chichén Itzá", "Actividades"),
    ("Cenote Dos Ojos", "Tulum", "Actividades"), ("Playa Delfines", "Cancún", "Playas"),
    ("Laguna de Bacalar", "Bacalar", "Playas"), ("La Negrita Cantina", "Mérida", "Bares"),
    ("Coco Bongo", "Cancún", "Bares"), ("Quinta Avenida", "Playa del Carmen", "Compras"),
    # … ajoute ici tous les lieux de ton répertoire …
]

FIELDS = ("places.id,places.displayName,places.businessStatus,places.rating,"
          "places.userRatingCount,places.location,places.formattedAddress,"
          "places.photos,places.websiteUri,places.editorialSummary")

def text_search(query):
    r = requests.post(f"{BASE}/places:searchText",
        headers={"X-Goog-Api-Key": API_KEY, "X-Goog-FieldMask": FIELDS,
                 "Content-Type": "application/json"},
        json={"textQuery": query, "languageCode": "es", "maxResultCount": 1}, timeout=20)
    r.raise_for_status()
    res = r.json().get("places", [])
    return res[0] if res else None

def nearby(lat, lng, gtype, radius=6000, n=8):
    r = requests.post(f"{BASE}/places:searchNearby",
        headers={"X-Goog-Api-Key": API_KEY, "X-Goog-FieldMask": FIELDS,
                 "Content-Type": "application/json"},
        json={"includedTypes": [gtype], "maxResultCount": n, "languageCode": "es",
              "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lng},
                                                  "radius": radius}}}, timeout=20)
    r.raise_for_status()
    return r.json().get("places", [])

def download_photo(place):
    """Télécharge la 1re photo Google de l'adresse -> images/<id>.jpg -> URL hébergée."""
    photos = place.get("photos") or []
    if not photos:
        return ""
    name = photos[0]["name"]  # ex: places/XXX/photos/YYY
    pid = place["id"]
    out = IMG_DIR / f"{pid}.jpg"
    if not out.exists():
        u = f"{BASE}/{name}/media?maxWidthPx=800&key={API_KEY}"
        img = requests.get(u, timeout=25)
        if img.status_code == 200:
            out.write_bytes(img.content)
        else:
            return ""
    return f"{IMG_BASE_URL}/{pid}.jpg"

def to_record(place, cat, city):
    region = CITY.get(city, ("", 0, 0))[0]
    loc = place.get("location", {})
    summary = (place.get("editorialSummary") or {}).get("text", "")
    return {
        "n": place["displayName"]["text"],
        "c": cat, "city": city, "region": region,
        "d": summary or place.get("formattedAddress", ""),
        "rt": round(place.get("rating", 0), 1),
        "reviews": place.get("userRatingCount", 0),
        "lat": loc.get("latitude"), "lng": loc.get("longitude"),
        "img": download_photo(place),
        "place_id": place["id"],
        "website": place.get("websiteUri", ""),
        "status": place.get("businessStatus", "OPERATIONAL"),
        # 'w' (WiFi gratuit) n'est pas fiable via l'API : à cocher à la main ou via avis.
    }

def run(discover=True):
    out, seen = [], set()
    removed = 0

    # 1) Revalider + corriger les lieux existants
    for name, city, cat in SEED:
        print(f"→ Valida: {name} ({city})")
        try:
            place = text_search(f"{name}, {city}, México")
        except Exception as e:
            print(f"   ⚠️ {e}"); continue
        if not place:
            print("   ✗ introuvable — retiré"); removed += 1; continue
        if place.get("businessStatus") != "OPERATIONAL":
            print(f"   ✗ {place.get('businessStatus')} — retiré"); removed += 1; continue
        rec = to_record(place, cat, city)
        out.append(rec); seen.add(rec["place_id"]); time.sleep(0.2)

    # 2) Découverte exhaustive : TOUT lieu >= 3 étoiles (quadrillage par ville + type)
    if discover:
        for city, (region, lat, lng) in CITY.items():
            for cat, gtype in CAT_TYPE.items():
                for dlat, dlng in TILES:
                    try:
                        found = nearby(lat + dlat, lng + dlng, gtype, radius=2500, n=20)
                    except Exception:
                        continue
                    for pl in found:
                        if pl["id"] in seen:
                            continue
                        if pl.get("rating", 0) >= MIN_RATING and pl.get("businessStatus") == "OPERATIONAL":
                            rec = to_record(pl, cat, city)          # règle : 3★ et plus → dans l'app
                            out.append(rec); seen.add(pl["id"])
                    time.sleep(0.15)
        print(f"   {len([r for r in out if r['rt'] >= MIN_RATING])} lieux ≥ {MIN_RATING}★ répertoriés")

    out.sort(key=lambda r: (-r["rt"], r["n"]))
    payload = {"updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "count": len(out), "removed": removed, "places": out}
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ {len(out)} lieux écrits, {removed} retirés (fermés/introuvables) → {OUTPUT}")

if __name__ == "__main__":
    run()
