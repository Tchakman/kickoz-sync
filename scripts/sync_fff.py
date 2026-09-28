#!/usr/bin/env python3
"""
Sync classement FFF → Firebase via Playwright (vrai navigateur).
"""
import json, os, sys, re, time
from datetime import datetime
from playwright.sync_api import sync_playwright
import firebase_admin
from firebase_admin import credentials, firestore

# ── Config ─────────────────────────────────────────────────────────────
FFF_URL       = "https://seineetmarne.fff.fr/recherche-clubs?scl=116693&tab=resultats&subtab=ranking&competition=457713&stage=1&group=2&label=U14%20D2"
CLUB_NAME_FFF = "OZOIR FC 77"
FIREBASE_DOC  = ("kickoff", "appState")

# ── Firebase ────────────────────────────────────────────────────────────
def init_firebase():
    cred_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not cred_json:
        print("❌ FIREBASE_SERVICE_ACCOUNT manquant"); sys.exit(1)
    cred = credentials.Certificate(json.loads(cred_json))
    firebase_admin.initialize_app(cred)
    return firestore.client()

# ── Scrape avec Playwright ──────────────────────────────────────────────
def scrape_with_playwright():
    standings = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({
            "Accept-Language": "fr-FR,fr;q=0.9",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        print(f"  📖 Chargement de la page FFF...")
        page.goto(FFF_URL, wait_until="networkidle", timeout=30000)
        time.sleep(3)

        # Chercher la table classement
        html = page.content()
        print(f"  📄 Page chargée ({len(html)} chars)")

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        # Chercher toutes les tables
        for table in soup.find_all("table"):
            ths = [th.get_text(strip=True).upper() for th in table.find_all("th")]
            print(f"  Table headers: {ths[:6]}")
            if any(h in ths for h in ["PTS", "POINTS", "PT"]):
                tbody = table.find("tbody")
                rows  = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]
                for i, row in enumerate(rows):
                    cols = [td.get_text(strip=True) for td in row.find_all("td")]
                    if len(cols) < 3: continue
                    print(f"    Row {i}: {cols[:6]}")
                    # Trouver le nom et les points
                    name = ""
                    pts  = 0
                    j    = 0
                    for c in cols:
                        if any(x in c.upper() for x in ["FC", "US ", "AS ", "SC ", "OZOIR", "SENART", "PONTAULT", "CLAYE", "LOGNES", "GRETZ", "TORCY", "BRIARD", "VAL D", "ENT."]):
                            name = c
                        if c.isdigit():
                            if not j: j = int(c)
                            pts = int(c)  # dernier nombre = pts
                    if not name and len(cols) > 1:
                        name = cols[1]
                    standings.append({
                        "pos":  i + 1,
                        "club": name.strip(),
                        "pts":  pts,
                        "j":    j,
                        "mine": CLUB_NAME_FFF.lower() in name.lower(),
                    })
                break

        browser.close()
    return standings

# ── Main ────────────────────────────────────────────────────────────────
def main():
    print("🔄 Sync FFF → Firebase (Playwright)")
    db = init_firebase()

    standings = scrape_with_playwright()
    print(f"  ✅ {len(standings)} équipes trouvées")

    if standings:
        our = next((s for s in standings if s["mine"]), None)
        if our:
            print(f"  🏆 {CLUB_NAME_FFF} : {our['pos']}e — {our['pts']} pts")
        db.collection(FIREBASE_DOC[0]).document(FIREBASE_DOC[1]).set(
            {"standings": standings}, merge=True
        )
        print("  ✅ Firebase mis à jour")
    else:
        print("  ⚠️ Aucune donnée — Firebase inchangé")

if __name__ == "__main__":
    main()
