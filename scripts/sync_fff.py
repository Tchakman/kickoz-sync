#!/usr/bin/env python3
"""
Sync classement FFF → Firebase via API DOFA.
Headers exacts copiés depuis DevTools Chrome Android.
"""
import json, os, sys
import requests
import firebase_admin
from firebase_admin import credentials, firestore

API_URL       = "https://api-dofa.fff.fr/api/compets/457713/phases/1/poules/2/classement_journees"
CLUB_NAME_FFF = "OZOIR FC 77"
FIREBASE_DOC  = ("kickoff", "appState")

# Headers EXACTEMENT comme Chrome Android sur seineetmarne.fff.fr
HEADERS = {
    "Accept":             "application/json, text/plain, */*",
    "Accept-Encoding":    "gzip, deflate, br, zstd",
    "Accept-Language":    "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin":             "https://seineetmarne.fff.fr",
    "Priority":           "u=1, i",
    "Referer":            "https://seineetmarne.fff.fr/",
    "Sec-Ch-Ua":          '"Google Chrome";v="153", "Not_A Brand";v="8", "Chromium";v="153"',
    "Sec-Ch-Ua-Mobile":   "?1",
    "Sec-Ch-Ua-Platform": '"Android"',
    "Sec-Fetch-Dest":     "empty",
    "Sec-Fetch-Mode":     "cors",
    "Sec-Fetch-Site":     "same-site",
    "User-Agent":         "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Mobile Safari/537.36",
}

def init_firebase():
    cred_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not cred_json:
        print("❌ FIREBASE_SERVICE_ACCOUNT manquant"); sys.exit(1)
    cred = credentials.Certificate(json.loads(cred_json))
    firebase_admin.initialize_app(cred)
    return firestore.client()

def fetch_standings():
    print(f"  GET {API_URL}")
    r = requests.get(API_URL, headers=HEADERS, timeout=15)
    print(f"  → {r.status_code}")
    if r.status_code != 200:
        print(f"  Body: {r.text[:300]}")
        r.raise_for_status()
    data = r.json()
    print(f"  Type: {type(data).__name__}")
    if isinstance(data, dict):
        for k, v in data.items():
            print(f"    '{k}': {type(v).__name__} = {str(v)[:200]}")
    elif isinstance(data, list):
        print(f"  {len(data)} éléments, premier: {str(data[0])[:300]}")
    return data

def parse_standings(data):
    rows = data if isinstance(data, list) else None
    if isinstance(data, dict):
        for key in ["classement","ranking","data","results","teams","clubs","items","poule","content"]:
            if key in data and isinstance(data[key], list) and data[key]:
                rows = data[key]; break
    if not rows:
        return []
    standings = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict): continue
        name = ""
        for k in ["clubName","name","club","equipe","team","nom","libelle","shortName","longName","fullName"]:
            if k in row and row[k]: name = str(row[k]).strip(); break
        if not name:
            for v in row.values():
                if isinstance(v, dict):
                    for k2 in ["name","nom","libelle","shortName","longName"]:
                        if k2 in v and v[k2]: name = str(v[k2]).strip(); break
                if name: break
        pts = next((int(row[k]) for k in ["points","pts","point","totalPoints","nbPoints","nb_points"] if k in row and str(row[k]).isdigit()), 0)
        j   = next((int(row[k]) for k in ["played","joues","j","matchsJoues","gamesPlayed","nb_matchs"] if k in row and str(row[k]).isdigit()), 0)
        if name:
            standings.append({"pos":i+1,"club":name,"pts":pts,"j":j,"mine":CLUB_NAME_FFF.lower() in name.lower()})
    return standings

def main():
    print("🔄 Sync FFF → Firebase")
    db = init_firebase()
    data = fetch_standings()
    standings = parse_standings(data)
    print(f"\n  {len(standings)} équipes parsées")
    if standings:
        for s in standings:
            print(f"    {s['pos']}. {s['club']} — {s['pts']} pts {'⭐' if s['mine'] else ''}")
        db.collection(FIREBASE_DOC[0]).document(FIREBASE_DOC[1]).set({"standings": standings}, merge=True)
        print("  ✅ Firebase mis à jour")
    else:
        print("  ⚠️ Parsing échoué — structure inattendue")
        sys.exit(0)

if __name__ == "__main__":
    main()
