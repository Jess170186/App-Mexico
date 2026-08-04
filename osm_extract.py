#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
App Mexico — Extraction mensuelle GRATUITE via OpenStreetMap
===============================================================
Aucune clé, aucune carte bancaire, aucune limite. Une fois par mois, ce script
interroge OpenStreetMap (API Overpass) pour TOUT le Quintana Roo et le Yucatán, et
extrait restaurants, bars, commerces, plages, activités et transports avec :
    nom · adresse · description · contact (tél / site) · catégorie · ville · coordonnées

Il écrit DEUX fichiers :
    • repertoire.xlsx  (tableur lisible/éditable : la « base » que tu voulais)
    • places.json      (le format que lit l'app App Mexico)

⚠️ OpenStreetMap ne fournit ni note en étoiles ni photo. On garde donc les visuels
   par catégorie de l'app, et on applique un FILTRE QUALITÉ (lieu « établi » : il a un
   nom + au moins une adresse, un téléphone ou un site web) en remplacement du « 3★+ ».

Utilisation :
    pip install -r requirements.txt
    python osm_extract.py
"""

import json, time, math, pathlib
import requests
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

HERE = pathlib.Path(__file__).parent
OVERPASS = "https://overpass-api.de/api/interpreter"

# Villes de référence (pour rattacher chaque lieu à une ville et filtrer les zones)
CITY = {
    "Cancún": ("Quintana Roo", 21.161, -86.851), "Playa del Carmen": ("Quintana Roo", 20.629, -87.073),
    "Tulum": ("Quintana Roo", 20.211, -87.465), "Bacalar": ("Quintana Roo", 18.680, -88.395),
    "Cozumel": ("Quintana Roo", 20.422, -86.922), "Holbox": ("Quintana Roo", 21.522, -87.379),
    "Chetumal": ("Quintana Roo", 18.503, -88.305), "Puerto Morelos": ("Quintana Roo", 20.848, -86.875),
    "Mérida": ("Yucatán", 20.967, -89.624), "Valladolid": ("Yucatán", 20.688, -88.202),
    "Progreso": ("Yucatán", 21.282, -89.665), "Izamal": ("Yucatán", 20.934, -89.017),
    "Tizimín": ("Yucatán", 21.143, -88.152), "Uxmal": ("Yucatán", 20.360, -89.771),
}
MAX_KM = 35  # un lieu est rattaché à la ville connue la plus proche s'il est à moins de 35 km

# Catégorie app -> filtres OSM
CATS = {
    "Restaurantes": ['node["amenity"="restaurant"]', 'node["amenity"="cafe"]'],
    "Bares":        ['node["amenity"="bar"]', 'node["amenity"="pub"]', 'node["amenity"="nightclub"]'],
    "Compras":      ['node["shop"="mall"]', 'node["shop"="department_store"]',
                     'node["amenity"="marketplace"]', 'node["shop"="gift"]', 'node["shop"="supermarket"]'],
    "Playas":       ['node["natural"="beach"]', 'way["natural"="beach"]'],
    "Actividades":  ['node["tourism"="attraction"]', 'node["tourism"="museum"]',
                     'node["tourism"="theme_park"]', 'way["historic"="archaeological_site"]'],
    "Transporte":   ['node["amenity"="bus_station"]', 'node["amenity"="ferry_terminal"]',
                     'node["aeroway"="aerodrome"]'],
}
AREAS = ('area["name"="Quintana Roo"]["admin_level"="4"]->.qr;'
         'area["name"="Yucatán"]["admin_level"="4"]->.yu;')

def km(a1, a2, b1, b2):
    R = 6371; dLat = math.radians(b1 - a1); dLng = math.radians(b2 - a2)
    s = math.sin(dLat/2)**2 + math.cos(math.radians(a1))*math.cos(math.radians(b1))*math.sin(dLng/2)**2
    return 2*R*math.asin(math.sqrt(s))

def nearest_city(lat, lng):
    best = None
    for c, (r, la, lo) in CITY.items():
        d = km(lat, lng, la, lo)
        if not best or d < best[2]:
            best = (c, r, d)
    return best  # (city, region, dist_km)

def overpass(filters):
    body = "[out:json][timeout:180];\n" + AREAS + "\n(\n"
    for f in filters:
        body += f"  {f}(area.qr);\n  {f}(area.yu);\n"
    body += ");\nout center tags;"
    r = requests.post(OVERPASS, data={"data": body}, timeout=200)
    r.raise_for_status()
    return r.json().get("elements", [])

def describe(cat, tags):
    if cat == "Restaurantes":
        cu = tags.get("cuisine", "").replace("_", " ")
        return f"Restaurante {('· ' + cu) if cu else ''}".strip()
    if cat == "Bares":     return "Bar / vida nocturna"
    if cat == "Compras":   return tags.get("shop", tags.get("amenity", "Comercio")).replace("_", " ").title()
    if cat == "Playas":    return "Playa"
    if cat == "Actividades":
        return (tags.get("tourism") or tags.get("historic") or "Atracción").replace("_", " ").title()
    if cat == "Transporte":
        return {"bus_station": "Terminal de autobuses", "ferry_terminal": "Terminal de ferry"}.get(
            tags.get("amenity"), "Aeropuerto" if tags.get("aeroway") else "Transporte")
    return cat

def address(tags):
    parts = [tags.get("addr:street", ""), tags.get("addr:housenumber", ""),
             tags.get("addr:city", "")]
    return " ".join(p for p in parts if p).strip()

def contact(tags):
    return (tags.get("phone") or tags.get("contact:phone") or ""), \
           (tags.get("website") or tags.get("contact:website") or "")

def social(tags):
    def norm(v, base):
        if not v:
            return ""
        return v if v.startswith("http") else base + v.lstrip("@/")
    fb = norm(tags.get("contact:facebook") or tags.get("facebook") or "", "https://facebook.com/")
    ig = norm(tags.get("contact:instagram") or tags.get("instagram") or "", "https://instagram.com/")
    return fb, ig

def gmaps_url(lat, lng):
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"

def run():
    records, seen = [], set()
    for cat, filters in CATS.items():
        print(f"→ {cat} …")
        try:
            els = overpass(filters)
        except Exception as e:
            print(f"   ⚠️ {e}"); continue
        for el in els:
            tags = el.get("tags", {})
            name = tags.get("name")
            if not name:
                continue
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lng = el.get("lon") or (el.get("center") or {}).get("lon")
            if lat is None or lng is None:
                continue
            city, region, dist = nearest_city(lat, lng)
            if dist > MAX_KM:
                continue
            phone, website = contact(tags)
            fb, ig = social(tags)
            addr = address(tags)
            # FILTRE QUALITÉ (remplace « 3★+ ») : lieu établi = nom + (adresse ou tél ou site)
            if not (addr or phone or website):
                continue
            key = (name.lower(), round(lat, 4), round(lng, 4))
            if key in seen:
                continue
            seen.add(key)
            records.append({
                "n": name, "c": cat, "city": city, "region": region,
                "d": describe(cat, tags), "address": addr, "phone": phone,
                "website": website, "facebook": fb, "instagram": ig,
                "gmaps": gmaps_url(round(lat, 6), round(lng, 6)),
                "img": "", "w": tags.get("internet_access") in ("wlan", "yes"),
                "lat": round(lat, 6), "lng": round(lng, 6),
            })
        print(f"   {len([r for r in records if r['c']==cat])} lieux")
        time.sleep(1)

    records.sort(key=lambda r: (r["region"], r["city"], r["c"], r["n"]))

    # ---- places.json (pour l'app) ----
    (HERE / "places.json").write_text(json.dumps(
        {"updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "count": len(records), "source": "OpenStreetMap", "places": records},
        ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- repertoire.xlsx (le tableur) ----
    wb = Workbook(); ws = wb.active; ws.title = "Répertoire"
    head = ["Nom", "Catégorie", "Ville", "Région", "Adresse", "Description",
            "Téléphone", "Site web", "Facebook", "Instagram", "Google Maps",
            "Image URL", "Note", "Lat", "Lng"]
    ws.append(head)
    for i, h in enumerate(head, 1):
        c = ws.cell(row=1, column=i); c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0F7D7B"); c.alignment = Alignment(vertical="center")
    for r in records:
        ws.append([r["n"], r["c"], r["city"], r["region"], r["address"], r["d"],
                   r["phone"], r["website"], r["facebook"], r["instagram"], r["gmaps"],
                   r["img"], "—", r["lat"], r["lng"]])
    widths = [26, 14, 16, 14, 30, 22, 16, 26, 26, 26, 34, 16, 6, 10, 10]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64+i)].width = w
    ws.freeze_panes = "A2"
    wb.save(HERE / "repertoire.xlsx")

    print(f"\n✅ {len(records)} lieux → repertoire.xlsx + places.json")

if __name__ == "__main__":
    run()
