# Best-effort subtitle trigger: waits for the downloaded media file to appear, then runs plex_subs_on_add.py
import os
import re
import time
import threading
import subprocess
from ui.ui_print import ui_print, ui_settings

# Hardcoded subtitle settings (bypass settings UI)
MEDIA_ROOT = r"Z:\\"  # Chemin réel où AllDebrid place les fichiers
SCRIPT_PATH = r"C:\\PlexAutomation\\plex_debrid_mehdi\\plex_subs_on_add_optimized.py"
PLEX_TOKEN = "V3f8y4xzv2VEo6xzcSXu"
PLEX_SECTION = "1"
OST_API = "1uRReegXFmxneboaeeTnaySPzAhfK5hn"
OST_USER = "rapture"
OST_PASS = "rNyH.Urf,z#r2LX"

_queue = []
_queue_lock = threading.Lock()
_worker_started = False


def _sanitize(text: str) -> str:
    # Lowercase, remove non alnum, collapse spaces
    cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return cleaned.strip()


def _find_media_path(root: str, query: str, extensions=None, timeout=120, poll=5):
    if extensions is None:
        extensions = [".mkv", ".mp4", ".avi", ".mov", ".ts", ".m2ts"]  # Plus d'extensions
    deadline = time.time() + timeout
    query_s = _sanitize(query)

    # Essayer différents patterns de recherche
    search_patterns = []
    # Pattern principal : le query sanitisé
    search_patterns.append(query_s)
    # Pattern alternatif : tous les mots du query doivent être présents (pas forcément dans l'ordre)
    query_words = query_s.split()

    ui_print(f"[subs trigger] searching for '{query}' (sanitized: '{query_s}') under {root}", debug=ui_settings.debug)

    attempt = 0
    while time.time() < deadline:
        attempt += 1
        candidates = []
        try:
            for dirpath, _, filenames in os.walk(root):
                for name in filenames:
                    ext = os.path.splitext(name)[1].lower()
                    if ext not in extensions:
                        continue

                    name_sanitized = _sanitize(name)
                    # Méthode 1 : Le query entier est dans le nom
                    if query_s in name_sanitized:
                        full = os.path.join(dirpath, name)
                        candidates.append((os.path.getmtime(full), full, "exact"))
                    # Méthode 2 : Tous les mots du query sont dans le nom
                    elif query_words and all(word in name_sanitized for word in query_words):
                        full = os.path.join(dirpath, name)
                        candidates.append((os.path.getmtime(full), full, "all_words"))

        except Exception as e:
            ui_print(f"[subs trigger] error scanning directory: {e}", debug=True)

        if ui_settings.debug == "true":
            ui_print(f"[subs trigger] attempt #{attempt}: found {len(candidates)} candidate(s)", debug=True)
            if candidates:
                for mtime, cand, match_type in sorted(candidates, key=lambda x: x[0], reverse=True)[:5]:
                    ui_print(f"[subs trigger] candidate ({match_type}): {cand}", debug=True)

        if candidates:
            # Prendre le fichier le plus récent
            candidates.sort(key=lambda x: x[0], reverse=True)
            chosen = candidates[0][1]
            ui_print(f"[subs trigger] found media file: {chosen}", debug=ui_settings.debug)
            return chosen

        time.sleep(poll)

    ui_print(f"[subs trigger] timeout after {attempt} attempts searching for '{query_s}'", debug=ui_settings.debug)
    return None


def _run_subs(path: str):
    script_path = SCRIPT_PATH
    plex_token = PLEX_TOKEN
    plex_section = PLEX_SECTION
    ost_api = OST_API
    ost_user = OST_USER
    ost_pass = OST_PASS
    if not (plex_token and plex_section and ost_api and ost_user and ost_pass):
        ui_print("[subs trigger] missing subtitle credentials; skipping.", debug=ui_settings.debug)
        return

    # AllDebrid crée une structure bizarre : dossier\fichier.mkv où dossier = fichier
    # On doit passer juste le dossier parent (qui contient le fichier)
    if os.path.isfile(path):
        # Si c'est un fichier, on prend son dossier parent
        path_to_pass = os.path.dirname(path)
        ui_print(f"[subs trigger] detected file path, using parent directory: {path_to_pass}", debug=ui_settings.debug)
    else:
        # Sinon on garde le chemin tel quel
        path_to_pass = path
        ui_print(f"[subs trigger] using directory path as-is: {path_to_pass}", debug=ui_settings.debug)

    cmd = [
        "python",
        script_path,
        "--token",
        plex_token,
        "--section",
        plex_section,
        "--path",
        path_to_pass,
        "--ost-api-key",
        ost_api,
        "--ost-user",
        ost_user,
        "--ost-pass",
        ost_pass,
    ]

    ui_print(f"[subs trigger] executing command: python plex_subs_on_add.py with path={path_to_pass}", debug=ui_settings.debug)

    try:
        # Lance le subprocess et capture toutes les sorties
        result = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        ui_print(f"[subs trigger] subprocess started with PID {result.pid}", debug=ui_settings.debug)

        # Attend que le processus se termine (max 60 secondes)
        try:
            stdout, stderr = result.communicate(timeout=60)

            # Affiche le code de retour
            ui_print(f"[subs trigger] subprocess finished with return code: {result.returncode}", debug=ui_settings.debug)

            # Affiche stdout s'il y en a
            if stdout:
                for line in stdout.strip().split('\n')[:20]:  # Max 20 lignes
                    if line.strip():
                        ui_print(f"[subs stdout] {line}", debug=ui_settings.debug)

            # Affiche stderr s'il y a des erreurs
            if stderr and result.returncode != 0:
                for line in stderr.strip().split('\n')[:10]:  # Max 10 lignes d'erreur
                    if line.strip():
                        ui_print(f"[subs stderr] {line}", debug=True)

            # Vérifie si c'était un succès
            if result.returncode == 0:
                ui_print(f"[subs trigger] ✓ Subtitle script completed successfully!", debug=ui_settings.debug)
            else:
                ui_print(f"[subs trigger] ✗ Subtitle script failed with code {result.returncode}", debug=ui_settings.debug)

        except subprocess.TimeoutExpired:
            ui_print("[subs trigger] subprocess timeout after 60 seconds", debug=ui_settings.debug)
            result.kill()
            stdout, stderr = result.communicate()

    except Exception as e:
        ui_print(f"[subs trigger] failed to launch script: {e}", debug=ui_settings.debug)
        import traceback
        ui_print(f"[subs trigger] traceback: {traceback.format_exc()}", debug=True)


def _worker():
    root = MEDIA_ROOT or "Z:\\"
    ui_print(f"[subs trigger] worker initialized with root: {root}", debug=ui_settings.debug)
    while True:
        try:
            job = None
            with _queue_lock:
                if _queue:
                    job = _queue.pop(0)
            if not job:
                time.sleep(2)
                continue
            query = job.get("query", "")
            key = job.get("key", "")
            ui_print(f"[subs trigger] processing job: '{key}' with query '{query}'", debug=ui_settings.debug)

            path = _find_media_path(root, query)
            if path:
                ui_print(f"[subs trigger] media found, launching subtitle script for: {path}", debug=ui_settings.debug)
                _run_subs(path)
            else:
                ui_print(f"[subs trigger] file for '{query}' not found under {root} (timeout).", debug=ui_settings.debug)
        except Exception as e:
            ui_print(f"[subs trigger] worker error: {e}", debug=True)
            import traceback
            ui_print(f"[subs trigger] traceback: {traceback.format_exc()}", debug=True)


def enqueue(element):
    global _worker_started
    with _queue_lock:
        # Utiliser query() au lieu de deviation() pour un pattern de recherche plus simple
        _queue.append({"query": element.query(), "key": element.query() + " [" + element.version.name + "]"})
        if not _worker_started:
            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            _worker_started = True
            ui_print("[subs trigger] worker started", debug=ui_settings.debug)
