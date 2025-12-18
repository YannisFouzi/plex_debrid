import os, time
from opensubtitlescom import OpenSubtitles

API_KEY = os.environ.get("OST_API_KEY")
USER    = os.environ.get("OST_USER")
PWD     = os.environ.get("OST_PASS")

if not (API_KEY and USER and PWD):
    raise SystemExit("Manque OST_API_KEY / OST_USER / OST_PASS dans les variables d'environnement.")

cli = OpenSubtitles("PlexSubs v0.1", API_KEY)

delay = 1.2
for attempt in range(1, 8):
    try:
        print(f"[TRY {attempt}] login…", flush=True)
        cli.login(USER, PWD)
        print("[OK] login success", flush=True)

        # mini appel derrière pour valider que le token marche
        r = cli.search(query="The Matrix", languages="fr")
        print(f"[OK] search success (results={len(r.data)})", flush=True)
        break
    except Exception as e:
        print(f"[ERR] {type(e).__name__}: {e}", flush=True)
        print(f"sleep {delay:.1f}s", flush=True)
        time.sleep(delay)
        delay = min(delay * 1.8, 20)
else:
    raise SystemExit("Toujours throttlé après plusieurs tentatives. IP probablement bridée côté OpenSubtitles.")
