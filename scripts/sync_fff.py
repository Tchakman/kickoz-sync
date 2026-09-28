#!/usr/bin/env python3
"""
Sync classement FFF → Firebase via Playwright avec attente du contenu JS.
"""
import json, os, sys, time
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

FFF_URL       = "https://seineetmarne.fff.fr/recherche-clubs?scl=116693&tab=resultats&subtab=ranking&competition=457713&stage=1&group=2&label=U14%20D2"
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
    standings = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-setuid-sandbox",
            "--disable-dev-shm-usage", "--disable-gpu",
        ])
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="fr-FR",
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()

        print(f"  📖 Chargement {FFF_URL}")
        page.goto(FFF_URL, wait_until="domcontentloaded", timeout=30000)

        # Attendre que le JS charge les données (table ou liste)
        print("  ⏳ Attente du contenu dynamique...")
        selectors = [
            "table tbody tr",
            ".ranking-table tr",
            ".classement tr",
            ".table-ranking tr",
            "[class*='ranking'] tr",
            "[class*='classement'] tr",
            "tr:has(td)",
        ]
        found_selector = None
        for sel in selectors:
            try:
                page.wait_for_selector(sel, timeout=8000)
                count = page.locator(sel).count()
                if count > 2:
                    found_selector = sel
                    print(f"  ✅ Sélecteur trouvé: '{sel}' ({count} éléments)")
                    break
            except PlaywrightTimeout:
                continue

        if not found_selector:
            # Attente brute + dump du HTML pour diagnostic
            time.sleep(5)
            html = page.content()
            print(f"  📄 HTML ({len(html)} chars)")
            # Sauvegarder un extrait pour diagnostic
            print("  --- Extrait HTML ---")
            print(html[:3000])
            print("  --- Fin extrait ---")
            browser.close()
            return []

        # Parser les lignes de la table
        rows = page.locator(found_selector).all()
        for i, row in enumerate(rows):
            cells = [td.inner_text().strip() for td in row.locator("td").all()]
            if len(cells) < 3:
                continue
            print(f"  Ligne {i}: {cells}")
            # Identifier le nom du club et les points
            name = ""
            pts  = 0
            j    = 0
            for ci, cell in enumerate(cells):
                # Le nom est généralement la cellule la plus longue avec des lettres
                if len(cell) > 3 and not cell.isdigit() and not cell in ["-", "/"]:
                    name = cell
                    break
            # Les points sont généralement la dernière colonne numérique
            nums = [c for c in cells if c.isdigit()]
            if nums:
                pts = int(nums[-1])
                if len(nums) > 1:
                    j = int(nums[0])
            if name:
                standings.append({
                    "pos":  i + 1,
                    "club": name,
                    "pts":  pts,
                    "j":    j,
                    "mine": CLUB_NAME_FFF.lower() in name.lower(),
                })

        browser.close()
    return standings

def main():
    print("🔄 Sync FFF → Firebase (Playwright)")
    db = init_firebase()
    standings = scrape()
    print(f"  ✅ {len(standings)} équipes trouvées")
    if standings:
        our = next((s for s in standings if s["mine"]), None)
        if our:
            print(f"  🏆 {CLUB_NAME_FFF} : {our['pos']}e — {our['pts']} pts")
        else:
            print(f"  ⚠️ Club '{CLUB_NAME_FFF}' non trouvé dans: {[s['club'] for s in standings]}")
        db.collection(FIREBASE_DOC[0]).document(FIREBASE_DOC[1]).set(
            {"standings": standings}, merge=True
        )
        print("  ✅ Firebase mis à jour")
    else:
        print("  ⚠️ Aucune donnée — Firebase inchangé")

if __name__ == "__main__":
    main()
