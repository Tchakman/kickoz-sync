#!/usr/bin/env python3
"""
Sync classement FFF → Firebase.
Version diagnostic : dump du HTML pour identifier la structure exacte.
"""
import json, os, sys, time
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# URL exacte fournie
FFF_URL       = "https://seineetmarne.fff.fr/recherche-clubs?subtab=ranking&tab=resultats&scl=116693&competition=457713&stage=1&group=2&label=U14%20D2"
CLUB_NAME_FFF = "OZOIR FC 77"
FIREBASE_DOC  = ("kickoff", "appState")

def init_firebase():
    cred_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not cred_json:
        print("❌ FIREBASE_SERVICE_ACCOUNT manquant"); sys.exit(1)
    cred = credentials.Certificate(json.loads(cred_json))
    firebase_admin.initialize_app(cred)
    return firestore.client()

def scrape():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
        ])
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="fr-FR",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()

        # Intercepter les appels API XHR/fetch pour trouver l'endpoint JSON
        api_responses = []
        def handle_response(response):
            if "fff.fr" in response.url and response.status == 200:
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    try:
                        data = response.json()
                        print(f"  🔗 API JSON: {response.url}")
                        print(f"     → {str(data)[:300]}")
                        api_responses.append({"url": response.url, "data": data})
                    except:
                        pass
        page.on("response", handle_response)

        print(f"  📖 Chargement...")
        page.goto(FFF_URL, wait_until="domcontentloaded", timeout=30000)

        # Attendre 8 secondes que Vue.js rende le contenu
        print("  ⏳ Attente rendu Vue.js (8s)...")
        time.sleep(8)

        html = page.content()
        print(f"  📄 HTML après attente: {len(html)} chars")

        # Chercher OZOIR dans le HTML
        if "OZOIR" in html.upper():
            print("  ✅ 'OZOIR' trouvé dans le HTML !")
            # Extraire la zone autour
            idx = html.upper().index("OZOIR")
            print(f"  Contexte: ...{html[max(0,idx-200):idx+300]}...")
        else:
            print("  ❌ 'OZOIR' PAS trouvé dans le HTML")

        # Lister tous les éléments <table> et <tr>
        tables = page.locator("table").count()
        trs    = page.locator("tr").count()
        print(f"  Tables: {tables}, Lignes TR: {trs}")

        # Chercher des classes communes de classement
        for cls in ["ranking", "classement", "standings", "group-standing", "poule"]:
            els = page.locator(f"[class*='{cls}']").count()
            if els:
                print(f"  Classe '{cls}': {els} éléments")

        # Dump premiers 5000 chars du body
        print("\n  === HTML BODY (5000 chars) ===")
        body = page.locator("body").inner_html()
        print(body[:5000])
        print("  === FIN HTML ===\n")

        browser.close()

        # Si des API JSON ont été interceptées, utiliser ces données
        if api_responses:
            print(f"  🎯 {len(api_responses)} appels API interceptés - utilisation des données JSON")
            return parse_api_data(api_responses)

        return []

def parse_api_data(responses):
    """Parse les réponses API pour extraire le classement."""
    for resp in responses:
        data = resp["data"]
        # Chercher une liste avec des infos de clubs
        rows = None
        if isinstance(data, list) and len(data) > 3:
            rows = data
        elif isinstance(data, dict):
            for key in ["ranking", "classement", "standings", "data", "results", "groups", "teams"]:
                if key in data and isinstance(data[key], list):
                    rows = data[key]
                    break
        if rows:
            standings = []
            for i, row in enumerate(rows):
                name = (row.get("clubName") or row.get("name") or row.get("club") or
                        row.get("team") or row.get("nom") or row.get("libelle") or "").strip()
                pts  = int(row.get("points") or row.get("pts") or row.get("point") or 0)
                j    = int(row.get("played") or row.get("joues") or row.get("j") or row.get("matchsJoues") or 0)
                if name:
                    standings.append({
                        "pos":  i + 1,
                        "club": name,
                        "pts":  pts,
                        "j":    j,
                        "mine": CLUB_NAME_FFF.lower() in name.lower(),
                    })
            if standings:
                return standings
    return []

def main():
    print("🔄 Sync FFF → Firebase (diagnostic)")
    db = init_firebase()
    standings = scrape()
    print(f"\n  Résultat: {len(standings)} équipes")
    if standings:
        for s in standings:
            print(f"    {s['pos']}. {s['club']} — {s['pts']} pts {'⭐' if s['mine'] else ''}")
        db.collection(FIREBASE_DOC[0]).document(FIREBASE_DOC[1]).set(
            {"standings": standings}, merge=True
        )
        print("  ✅ Firebase mis à jour")
    else:
        print("  ⚠️ Aucune donnée")

if __name__ == "__main__":
    main()
