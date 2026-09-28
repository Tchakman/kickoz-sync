#!/usr/bin/env python3
"""
Scrape le classement et calendrier FFF et les pousse dans Firebase Firestore.
À exécuter via GitHub Actions toutes les heures.
"""

import json, os, re, sys
from datetime import datetime

import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore

# ── Config ─────────────────────────────────────────────────────────────
FFF_URL = "https://seineetmarne.fff.fr/recherche-clubs?scl=116693&tab=resultats&subtab=calendar&competition=457713&stage=1&group=2&label=U14%20D2"
CLUB_NAME_FFF = "OZOIR FC 77"  # Nom exact tel qu'affiché sur fff.fr
FIREBASE_DOC  = ("kickoff", "appState")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KICKOZ-bot/1.0)",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

MOIS = {"janvier":1,"février":2,"mars":3,"avril":4,"mai":5,"juin":6,
        "juillet":7,"août":8,"septembre":9,"octobre":10,"novembre":11,"décembre":12}

# ── Init Firebase ───────────────────────────────────────────────────────
def init_firebase():
    cred_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not cred_json:
        print("❌ FIREBASE_SERVICE_ACCOUNT non défini")
        sys.exit(1)
    cred_dict = json.loads(cred_json)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    return firestore.client()

# ── Scrape FFF ──────────────────────────────────────────────────────────
def scrape_fff():
    r = requests.get(FFF_URL, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

# ── Parse classement ────────────────────────────────────────────────────
def parse_standings(soup):
    standings = []
    table = soup.find("table", class_=re.compile(r"classement|ranking|standing", re.I))
    if not table:
        # Essai par thead
        tables = soup.find_all("table")
        for t in tables:
            headers = [th.get_text(strip=True).lower() for th in t.find_all("th")]
            if any(h in headers for h in ["pts", "points", "j", "joués"]):
                table = t
                break
    if not table:
        print("⚠️ Table classement non trouvée")
        return []
    rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")[1:]
    for i, row in enumerate(rows):
        cols = [td.get_text(strip=True) for td in row.find_all("td")]
        if len(cols) < 4:
            continue
        # Format typique: Pos | Equipe | J | V | N | D | BP | BC | Diff | Pts
        try:
            club_name = cols[1] if len(cols) > 1 else cols[0]
            pts_col   = next((int(c) for c in reversed(cols) if c.isdigit()), 0)
            joues_col = int(cols[2]) if cols[2].isdigit() else 0
            standings.append({
                "pos":   i + 1,
                "club":  club_name.strip(),
                "pts":   pts_col,
                "j":     joues_col,
                "mine":  CLUB_NAME_FFF.lower() in club_name.lower(),
            })
        except (ValueError, IndexError):
            continue
    return standings

# ── Parse calendrier ────────────────────────────────────────────────────
def parse_calendar(soup):
    matches = []
    # Chercher les blocs de match (structure FFF typique)
    match_blocks = soup.find_all(class_=re.compile(r"match|rencontre|game", re.I))
    if not match_blocks:
        match_blocks = soup.find_all("tr", class_=re.compile(r"match|result", re.I))
    
    today = datetime.today()
    
    for block in match_blocks:
        text = block.get_text(" ", strip=True)
        
        # Chercher une date
        date_match = re.search(r"(\w+)\s+(\d{1,2})\s+(\w+)\s+(\d{4})\s*[-–]\s*(\d{1,2}[Hh]\d{0,2})", text, re.I)
        if not date_match:
            continue
        
        try:
            day, month_str, year, time_str = date_match.group(2), date_match.group(3).lower(), date_match.group(4), date_match.group(5)
            month = MOIS.get(month_str)
            if not month:
                continue
            date_iso = f"{year}-{month:02d}-{int(day):02d}"
            time_fmt  = time_str.upper().replace("H", ":").replace(":", "", 1) if ":" not in time_str else time_str
            # Chercher les équipes
            teams = re.findall(r"([A-ZÀ-Ÿ][A-ZÀ-Ÿa-zà-ÿ\s\.]+(?:\d+)?)", text)
            home, away = (teams[0].strip(), teams[1].strip()) if len(teams) >= 2 else ("?", "?")
            is_home = CLUB_NAME_FFF.lower() in home.lower()
            our_side = "Domicile" if is_home else "Extérieur"
            opponent = away if is_home else home
            match_date = datetime(int(year), month, int(day))
            status = "past" if match_date < today else "upcoming"
            matches.append({
                "date":      date_iso,
                "time":      time_fmt,
                "homeTeam":  home,
                "awayTeam":  away,
                "side":      our_side,
                "opponent":  opponent.strip(),
                "status":    status,
            })
        except Exception as e:
            print(f"  ⚠️ Erreur parsing match: {e}")
            continue
    return matches

# ── Main ────────────────────────────────────────────────────────────────
def main():
    print("🔄 Sync FFF → Firebase")
    db = init_firebase()
    soup = scrape_fff()
    
    standings = parse_standings(soup)
    print(f"  ✅ Classement : {len(standings)} équipes")
    
    calendar  = parse_calendar(soup)
    upcoming  = [m for m in calendar if m["status"] == "upcoming"]
    print(f"  ✅ Calendrier : {len(upcoming)} matchs à venir")
    
    doc_ref = db.collection(FIREBASE_DOC[0]).document(FIREBASE_DOC[1])
    update  = {}
    if standings:
        update["standings"] = standings
    if upcoming:
        # Ne pas écraser les upcomingMatches existants — merger par date+adversaire
        existing = doc_ref.get().to_dict().get("upcomingMatches", [])
        existing_keys = {(m.get("date",""), m.get("opponent","").lower()) for m in existing}
        new_matches = []
        for m in upcoming:
            key = (m["date"], m["opponent"].lower())
            if key not in existing_keys:
                new_matches.append({**m, "id": int(datetime.now().timestamp()*1000)})
        if new_matches:
            update["upcomingMatches"] = existing + new_matches
            print(f"  ➕ {len(new_matches)} nouveaux matchs ajoutés")
    
    if update:
        doc_ref.set(update, merge=True)
        print("  ✅ Firebase mis à jour")
    else:
        print("  ℹ️ Rien à mettre à jour")

if __name__ == "__main__":
    main()
