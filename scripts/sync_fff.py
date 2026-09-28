#!/usr/bin/env python3
"""
Sync classement FFF → Firebase via Cloudflare Worker proxy.
Le worker tourne sur les IPs Cloudflare (whitelistées par FFF).
"""
import json, os, sys
import requests
import firebase_admin
from firebase_admin import credentials, firestore

# URL de ton Cloudflare Worker (à remplacer après déploiement)
WORKER_URL    = os.environ.get("WORKER_URL", "https://kickoz-fff.workers.dev/classement")
CLUB_NAME_FFF = "OZOIR FC 77"
FIREBASE_DOC  = ("kickoff", "appState")

def init_firebase():
    cred_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not cred_json:
        print("❌ FIREBASE_SERVICE_ACCOUNT manquant"); sys.exit(1)
    cred = credentials.Certificate(json.loads(cred_json))
    firebase_admin.initialize_app(cred)
    return firestore.client()

def fetch_standings():
    print(f"  GET {WORKER_URL}")
    r = requests.get(WORKER_URL, timeout=15)
    print(f"  → {r.status_code}")
    r.raise_for_status()
    return r.json()

def main():
    print("🔄 Sync FFF → Firebase (via Worker)")
    db = init_firebase()
    data = fetch_standings()

    standings = data.get("standings", [])
    if not standings:
        print("  ⚠️ Aucune donnée")
        print(f"  Raw: {str(data.get('raw',''))[:500]}")
        sys.exit(0)

    print(f"\n  {len(standings)} équipes")
    for s in standings:
        print(f"    {s['pos']}. {s['club']} — {s['pts']} pts {'⭐' if s['mine'] else ''}")

    db.collection(FIREBASE_DOC[0]).document(FIREBASE_DOC[1]).set(
        {"standings": standings}, merge=True
    )
    print("  ✅ Firebase mis à jour")

if __name__ == "__main__":
    main()
