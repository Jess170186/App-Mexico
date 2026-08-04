#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
App Mexico — Agrégateur d'événements automatique
====================================================
Récupère les événements des sites officiels du Quintana Roo et du Yucatán,
extrait pour chacun {titre, date, lieu, catégorie, description, image, lien source}
via l'API Claude (extraction JSON structurée), dédoublonne, et écrit events.json.

L'app App Mexico lit ensuite events.json et se met à jour toute seule.

Utilisation :
    export ANTHROPIC_API_KEY="sk-ant-..."
    pip install -r requirements.txt
    python aggregator.py                # met à jour events.json

Approche respectueuse du droit d'auteur : on ne recopie pas les articles, on ne
garde que les faits (titre, date, lieu) + un court résumé reformulé, et on renvoie
TOUJOURS vers la source via 'source_url'.
"""

import os
import re
import json
import time
import html
import datetime as dt
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import anthropic

# ---------------------------------------------------------------------------
# 1) SOURCES — ajoute/retire librement des sites ici
# ---------------------------------------------------------------------------
SOURCES = [
    # Quintana Roo
    {"name": "SITUR Quintana Roo", "region": "Quintana Roo",
     "url": "https://siturq.gob.mx/eventos"},
    {"name": "Quintana Roo Hoy",   "region": "Quintana Roo",
     "url": "https://quintanaroohoy.com/cultura/"},
    # Yucatán
    {"name": "Ayuntamiento de Mérida", "region": "Yucatán",
     "url": "https://www.merida.gob.mx/eventos"},
    {"name": "Gobierno de Yucatán",    "region": "Yucatán",
     "url": "https://www.yucatan.gob.mx/"},
]

MODEL = "claude-sonnet-4-5"          # rapide et économique pour l'extraction
MAX_EVENTS_PER_SOURCE = 15
OUTPUT = os.path.join(os.path.dirname(__file__), "events.json")
CATEGORIES = ["Música", "Gastronomía", "Cultura", "Deporte", "Familia",
              "Fiesta", "Arte", "Feria", "Otro"]

client = anthropic.Anthropic()       # lit ANTHROPIC_API_KEY dans l'environnement

# ---------------------------------------------------------------------------
# 2) OUTIL D'EXTRACTION — schéma JSON que Claude DOIT remplir (tool_use)
# ---------------------------------------------------------------------------
EXTRACT_TOOL = {
    "name": "record_events",
    "description": "Enregistre la liste des événements trouvés sur la page.",
    "input_schema": {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title":       {"type": "string", "description": "Titre court de l'événement"},
                        "date_start":  {"type": "string", "description": "Date de début AAAA-MM-JJ (déduis l'année en cours si absente)"},
                        "date_end":    {"type": "string", "description": "Date de fin AAAA-MM-JJ ou vide"},
                        "location":    {"type": "string", "description": "Ville + lieu précis si disponible"},
                        "category":    {"type": "string", "enum": CATEGORIES},
                        "description": {"type": "string", "description": "Résumé reformulé de 1 à 2 phrases, en espagnol, SANS copier le texte original"},
                        "detail_url":  {"type": "string", "description": "Lien absolu vers la page de l'événement (ou la page source)"},
                    },
                    "required": ["title", "date_start", "location", "category", "description", "detail_url"],
                },
            }
        },
        "required": ["events"],
    },
}

# ---------------------------------------------------------------------------
# 3) OUTILS DE RÉCUPÉRATION WEB
# ---------------------------------------------------------------------------
HEADERS = {"User-Agent": "PeninsulaLiveBot/1.0 (+https://peninsulalive.app)"}

def fetch(url, timeout=20):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"   ⚠️  fetch échoué {url} : {e}")
        return ""

def clean_text(html_str, limit=14000):
    """Réduit la page à du texte lisible pour l'extraction (économise des tokens)."""
    soup = BeautifulSoup(html_str, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
    return text[:limit]

def og_meta(page_html, base_url):
    """Récupère l'image et la description OpenGraph d'une page (og:image / og:description)."""
    soup = BeautifulSoup(page_html, "html.parser")
    def meta(prop):
        el = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        return el["content"].strip() if el and el.get("content") else ""
    img = meta("og:image") or meta("twitter:image")
    desc = meta("og:description") or meta("description")
    if img:
        img = urljoin(base_url, img)
    return img, html.unescape(desc)

# ---------------------------------------------------------------------------
# 4) EXTRACTION VIA CLAUDE
# ---------------------------------------------------------------------------
def extract_events(source, page_text):
    year = dt.date.today().year
    prompt = (
        f"Voici le texte de la page « {source['name']} » ({source['region']}, México). "
        f"Nous sommes en {year}. Repère les ÉVÉNEMENTS à venir (concerts, festivals, ferias, "
        f"cultura, deporte, etc.). Pour chacun, remplis l'outil record_events. "
        f"Ignore la navigation et les publicités. Si une date n'a pas d'année, utilise {year}. "
        f"Les liens doivent être absolus. Résume les descriptions avec tes propres mots.\n\n"
        f"----- PAGE -----\n{page_text}"
    )
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            tools=[EXTRACT_TOOL],
            tool_choice={"type": "tool", "name": "record_events"},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in msg.content:
            if block.type == "tool_use" and block.name == "record_events":
                return block.input.get("events", [])[:MAX_EVENTS_PER_SOURCE]
    except Exception as e:
        print(f"   ⚠️  extraction Claude échouée : {e}")
    return []

# ---------------------------------------------------------------------------
# 5) ENRICHISSEMENT : image + description depuis la page de l'événement
# ---------------------------------------------------------------------------
def enrich(ev, source):
    url = ev.get("detail_url") or source["url"]
    ev["source_url"] = url
    ev["source_name"] = source["name"]
    ev["region"] = source["region"]
    img, og_desc = "", ""
    if url and urlparse(url).scheme.startswith("http"):
        page = fetch(url)
        if page:
            img, og_desc = og_meta(page, url)
    ev["image"] = img
    # garde le résumé de Claude ; complète avec l'OG si vide
    if not ev.get("description") and og_desc:
        ev["description"] = og_desc[:280]
    return ev

# ---------------------------------------------------------------------------
# 6) DÉDOUBLONNAGE
# ---------------------------------------------------------------------------
def key(ev):
    t = re.sub(r"\W+", "", (ev.get("title") or "").lower())[:40]
    return f"{t}|{ev.get('date_start','')}"

# ---------------------------------------------------------------------------
# 7) PIPELINE PRINCIPAL
# ---------------------------------------------------------------------------
def run():
    all_events, seen = [], set()
    for src in SOURCES:
        print(f"→ {src['name']} ({src['region']})")
        page = fetch(src["url"])
        if not page:
            continue
        events = extract_events(src, clean_text(page))
        print(f"   {len(events)} événement(s) extrait(s)")
        for ev in events:
            k = key(ev)
            if k in seen:
                continue
            seen.add(k)
            all_events.append(enrich(ev, src))
            time.sleep(0.3)   # courtoisie envers les serveurs sources

    # tri par date
    def sort_key(e):
        try:
            return dt.date.fromisoformat(e.get("date_start", "9999-12-31"))
        except Exception:
            return dt.date(9999, 12, 31)
    all_events.sort(key=sort_key)

    payload = {
        "updated_at": dt.datetime.utcnow().isoformat() + "Z",
        "count": len(all_events),
        "events": all_events,
    }
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n✅  {len(all_events)} événements écrits dans {OUTPUT}")

if __name__ == "__main__":
    run()
