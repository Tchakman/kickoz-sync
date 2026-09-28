/**
 * Cloudflare Worker — Proxy FFF DOFA API
 * Déployer sur : https://dash.cloudflare.com → Workers & Pages → Create Worker
 * 
 * Ce worker tourne sur les IPs Cloudflare (whitelistées par FFF)
 * et retourne le classement en JSON propre.
 * 
 * Appel depuis GitHub Actions : GET https://TON_WORKER.workers.dev/classement
 */

const FFF_API = "https://api-dofa.fff.fr/api/compets/457713/phases/1/poules/2/classement_journees";
const CLUB    = "OZOIR FC 77";

// Secret pour protéger ton worker (à définir dans les variables d'env Cloudflare)
// Ou laisser vide pour accès public
const SECRET  = "";

export default {
  async fetch(request, env) {
    // Vérification optionnelle d'un secret
    const url = new URL(request.url);
    if (env.SECRET && url.searchParams.get("key") !== env.SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    // Appel à l'API FFF depuis Cloudflare (IPs whitelistées)
    const resp = await fetch(FFF_API, {
      headers: {
        "Accept":             "application/json, text/plain, */*",
        "Accept-Language":    "fr-FR,fr;q=0.9",
        "Origin":             "https://seineetmarne.fff.fr",
        "Referer":            "https://seineetmarne.fff.fr/",
        "Sec-Ch-Ua":          '"Google Chrome";v="153", "Not_A Brand";v="8"',
        "Sec-Ch-Ua-Mobile":   "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest":     "empty",
        "Sec-Fetch-Mode":     "cors",
        "Sec-Fetch-Site":     "same-site",
        "User-Agent":         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153.0.0.0 Safari/537.36",
      }
    });

    if (!resp.ok) {
      return new Response(JSON.stringify({ error: `FFF API returned ${resp.status}` }), {
        status: 502,
        headers: { "Content-Type": "application/json" }
      });
    }

    const data = await resp.json();

    // Parser et retourner un classement propre
    const rows = Array.isArray(data) ? data
      : data.classement || data.ranking || data.data || data.teams || [];

    const standings = rows
      .filter(r => typeof r === "object")
      .map((r, i) => {
        const name = r.clubName || r.name || r.club || r.nom || r.libelle || r.shortName || "";
        const pts  = parseInt(r.points || r.pts || r.point || 0) || 0;
        const j    = parseInt(r.played || r.joues || r.j || 0) || 0;
        // Chercher dans sous-objets
        let finalName = name;
        if (!finalName) {
          for (const v of Object.values(r)) {
            if (typeof v === "object" && v) {
              finalName = v.name || v.nom || v.libelle || v.shortName || v.longName || "";
              if (finalName) break;
            }
          }
        }
        return {
          pos:  i + 1,
          club: finalName.trim(),
          pts,
          j,
          mine: finalName.toLowerCase().includes(CLUB.toLowerCase()),
        };
      })
      .filter(r => r.club);

    return new Response(JSON.stringify({ standings, raw: data }), {
      headers: {
        "Content-Type":                "application/json",
        "Access-Control-Allow-Origin": "*",
      }
    });
  }
};
