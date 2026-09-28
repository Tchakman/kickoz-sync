#!/usr/bin/env python3
"""
Sync classement FFF → Firebase via API DOFA officielle.
URL: https://api-dofa.fff.fr/api/compets/457713/phases/1/poules/2/classement_journees
"""
import json, os, sys
import requests
import firebase_admin
from firebase_admin import credentials, firestore

API_URL       = "https://api-dofa.fff.fr/api/compets/457713/phases/1/poules/2/classement_journees"
CLUB_NAME_FFF = "OZOIR FC 77"
FIREBASE_DOC  = ("kickoff", "appState")

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer":         "https://seineetmarne.fff.fr/",
    "Origin":          "https://seineetmarne.fff.fr",
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
    r.raise_for_status()
    data = r.json()
    print(f"  JSON keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
    print(f"  Sample: {str(data)[:400]}")
    return data

def parse_standings(data):
    standings = []
    # Chercher la liste des clubs dans la structure
    rows = None
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        # Parcourir toutes les clés pour trouver une liste
        for key, val in data.items():
            print(f"  Clé '{key}': {type(val).__name__} — {str(val)[:100]}")
            if isinstance(val, list) and len(val) > 0:
                rows = val
                print(f"  → Utilisation de '{key}' ({len(val)} éléments)")
                break

    if not rows:
        return []

    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        print(f"  Row {i}: {row}")
        # Chercher nom du club
        name = ""
        for k in ["clubName", "name", "club", "equipe", "team", "nom",
                  "libelle", "shortName", "longName", "teamName"]:
            if k in row and row[k]:
                name = str(row[k]).strip()
                break
        # Si pas trouvé, chercher dans les sous-objets
        if not name:
            for k, v in row.items():
                if isinstance(v, dict):
                    for k2 in ["name", "nom", "libelle", "shortName"]:
                        if k2 in v and v[k2]:
                            name = str(v[k2]).strip()
                            break
                if name:
                    break

        # Points
        pts = 0
        for k in ["points", "pts", "point", "totalPoints", "nbPoints", "nb_points"]:
            if k in row:
                try: pts = int(row[k]); break
                except: pass

        # Matchs joués
        j = 0
        for k in ["played", "joues", "j", "matchsJoues", "gamesPlayed", "nb_matchs", "nbMatchs"]:
            if k in row:
                try: j = int(row[k]); break
                except: pass

        if name:
            standings.append({
                "pos":  i + 1,
                "club": name,
                "pts":  pts,
                "j":    j,
                "mine": CLUB_NAME_FFF.lower() in name.lower(),
            })

    return standings

def main():
    print("🔄 Sync FFF → Firebase (API DOFA)")
    db = init_firebase()

    data = fetch_standings()
    standings = parse_standings(data)

    print(f"\n  ✅ {len(standings)} équipes parsées")
    if standings:
        for s in standings:
            print(f"    {s['pos']}. {s['club']} — {s['pts']} pts {'⭐' if s['mine'] else ''}")
        db.collection(FIREBASE_DOC[0]).document(FIREBASE_DOC[1]).set(
            {"standings": standings}, merge=True
        )
        print("  ✅ Firebase mis à jour")
    else:
        print("  ⚠️ Aucune équipe parsée — vérifier la structure JSON ci-dessus")

if __name__ == "__main__":
    main()
