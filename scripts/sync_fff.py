#!/usr/bin/env python3
"""
Sync classement FFF → Firebase Firestore via l'API interne FFF.
"""

import json, os, sys, time
import requests
import firebase_admin
from firebase_admin import credentials, firestore

# ── Config ─────────────────────────────────────────────────────────────
COMPETITION_ID = "457713"
POULE_ID       = "1"          # groupe/poule B
CLUB_NAME_FFF  = "OZOIR FC 77"
FIREBASE_DOC   = ("kickoff", "appState")

# L'API interne que le site FFF utilise en JSON
STANDINGS_URL = f"https://seineetmarne.fff.fr/api/competition/{COMPETITION_ID}/ranking?group={POULE_ID}"
CALENDAR_URL  = f"https://seineetmarne.fff.fr/api/competition/{COMPETITION_ID}/calendar?group={POULE_ID}"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer":         "https://seineetmarne.fff.fr/",
    "Origin":          "https://seineetmarne.fff.fr",
}

MOIS = {"janvier":1,"février":2,"mars":3,"avril":4,"mai":5,"juin":6,
        "juillet":7,"août":8,"septembre":9,"octobre":10,"novembre":11,"décembre":12}

# ── Init Firebase ───────────────────────────────────────────────────────
def init_firebase():
    cred_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not cred_json:
        print("❌ FIREBASE_SERVICE_ACCOUNT manquant")
        sys.exit(1)
    cred = credentials.Certificate(json.loads(cred_json))
    firebase_admin.initialize_app(cred)
    return firestore.client()

# ── Fetch avec retry ────────────────────────────────────────────────────
def fetch(url, params=None):
    for attempt in range(3):
        try:
            time.sleep(2 + attempt * 3)
            r = requests.get(url, headers=HEADERS, params=params, timeout=20)
            print(f"  GET {url} → {r.status_code}")
            if r.status_code == 200:
                return r
            if r.status_code == 403:
                print(f"  ⚠️ 403 tentative {attempt+1}/3")
        except Exception as e:
            print(f"  ⚠️ Erreur réseau: {e}")
    return None

# ── Parse classement ────────────────────────────────────────────────────
def get_standings():
    r = fetch(STANDINGS_URL)
    if not r:
        return try_scrape_standings()
    try:
        data = r.json()
        rows = data if isinstance(data, list) else data.get("ranking", data.get("classement", data.get("data", [])))
        standings = []
        for i, row in enumerate(rows):
            name = (row.get("name") or row.get("club") or row.get("team") or row.get("nom") or "").strip()
            pts  = int(row.get("points") or row.get("pts") or 0)
            j    = int(row.get("played") or row.get("joues") or row.get("j") or 0)
            standings.append({
                "pos":  i + 1,
                "club": name,
                "pts":  pts,
                "j":    j,
                "mine": CLUB_NAME_FFF.lower() in name.lower(),
            })
        print(f"  ✅ {len(standings)} équipes (API JSON)")
        return standings
    except Exception as e:
        print(f"  ⚠️ JSON parse error: {e}")
        return try_scrape_standings()

# ── Scrape HTML fallback classement ─────────────────────────────────────
def try_scrape_standings():
    from bs4 import BeautifulSoup
    page_url = f"https://seineetmarne.fff.fr/recherche-clubs?scl=116693&tab=resultats&subtab=ranking&competition={COMPETITION_ID}&stage=1&group={POULE_ID}"
    headers_html = {**HEADERS, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    try:
        time.sleep(5)
        r = requests.get(page_url, headers=headers_html, timeout=30)
        if r.status_code != 200:
            print(f"  ❌ HTML fallback aussi bloqué ({r.status_code})")
            return []
        soup = BeautifulSoup(r.text, "lxml")
        # Chercher la table avec colonnes Points
        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True).upper() for th in table.find_all("th")]
            if "PTS" in headers or "POINTS" in headers:
                standings = []
                for i, row in enumerate(table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")[1:]):
                    cols = [td.get_text(strip=True) for td in row.find_all("td")]
                    if len(cols) < 3: continue
                    name = cols[1] if len(cols) > 2 else cols[0]
                    pts  = next((int(c) for c in reversed(cols) if c.isdigit()), 0)
                    standings.append({"pos":i+1,"club":name.strip(),"pts":pts,"j":0,"mine":CLUB_NAME_FFF.lower() in name.lower()})
                print(f"  ✅ {len(standings)} équipes (HTML fallback)")
                return standings
        print("  ⚠️ Table classement non trouvée dans le HTML")
        return []
    except Exception as e:
        print(f"  ❌ Scrape HTML error: {e}")
        return []

# ── Main ────────────────────────────────────────────────────────────────
def main():
    print("🔄 Sync FFF → Firebase")
    db = init_firebase()
    
    standings = get_standings()
    
    doc_ref = db.collection(FIREBASE_DOC[0]).document(FIREBASE_DOC[1])
    update  = {}
    
    if standings:
        update["standings"] = standings
        our = next((s for s in standings if s["mine"]), None)
        if our:
            print(f"  🏆 {CLUB_NAME_FFF} : {our['pos']}e — {our['pts']} pts")
    
    if update:
        doc_ref.set(update, merge=True)
        print("  ✅ Firebase mis à jour")
    else:
        print("  ℹ️ Aucune donnée récupérée — Firebase inchangé")

if __name__ == "__main__":
    main()
