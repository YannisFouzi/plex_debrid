# Best-effort subtitle trigger: waits for the downloaded media file to appear, then runs subtitles/plex_subs_on_add.py
import json
import os
import re
import time
import threading
import subprocess
from ui.ui_print import ui_print, ui_settings

# Subtitle settings (from settings.json or env vars)
_SETTINGS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "settings.json"))

def _load_settings_json():
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.loads(f.read())
    except Exception:
        return {}

def _get_setting(settings, key, default=""):
    value = settings.get(key)
    if value is None or value == "":
        return default
    return value

_settings = _load_settings_json()
MEDIA_ROOT = os.getenv("SUBS_MEDIA_ROOT", _get_setting(_settings, "Subs media root", r"Z:\\"))
SCRIPT_PATH = os.getenv(
    "SUBS_SCRIPT_PATH",
    _get_setting(
        _settings,
        "Subs script path",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "plex_subs_on_add.py")),
    ),
)
PLEX_TOKEN = os.getenv("SUBS_PLEX_TOKEN", _get_setting(_settings, "Subs Plex token", ""))
PLEX_SECTION_MOVIE = os.getenv(
    "SUBS_PLEX_SECTION_MOVIE",
    _get_setting(_settings, "Subs Plex section movie", _get_setting(_settings, "Subs Plex section", "1")),
)
PLEX_SECTION_SHOW = os.getenv(
    "SUBS_PLEX_SECTION_SHOW",
    _get_setting(_settings, "Subs Plex section show", "2"),
)
PLEX_SECTION = PLEX_SECTION_MOVIE
OST_API = os.getenv("SUBS_OST_API_KEY", _get_setting(_settings, "Subs OpenSubtitles API key", ""))
OST_USER = os.getenv("SUBS_OST_USER", _get_setting(_settings, "Subs OpenSubtitles user", ""))
OST_PASS = os.getenv("SUBS_OST_PASS", _get_setting(_settings, "Subs OpenSubtitles pass", ""))
_queue = []
_queue_lock = threading.Lock()
_worker_started = False


def _sanitize(text: str) -> str:
    # Lowercase, remove non alnum, collapse spaces
    cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return cleaned.strip()


def _pick_plex_section(job_key: str) -> str:
    key = (job_key or "").lower()
    if "shows_" in key or "episodes_" in key:
        return PLEX_SECTION_SHOW
    if "movies_" in key:
        return PLEX_SECTION_MOVIE
    return PLEX_SECTION


def _find_media_path(root: str, query: str, extensions=None, timeout=120, poll=5):
    if extensions is None:
        extensions = [".mkv", ".mp4", ".avi", ".mov", ".ts", ".m2ts"]  # Plus d'extensions
    deadline = time.time() + timeout
    query_s = _sanitize(query)

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


def _run_subs(path: str, plex_section_override: str = None):
    script_path = SCRIPT_PATH
    plex_token = PLEX_TOKEN
    plex_section = plex_section_override or PLEX_SECTION
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

    ui_print(f"[subs trigger] executing command: python {script_path} with path={path_to_pass}", debug=ui_settings.debug)

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

        # Attend que le processus se termine (max 15 minutes pour les packs séries)
        try:
            stdout, stderr = result.communicate(timeout=900)

            # Affiche le code de retour
            ui_print(f"[subs trigger] subprocess finished with return code: {result.returncode}", debug=ui_settings.debug)

            # Affiche stdout s'il y en a (afficher TOUTES les lignes pour le debug)
            if stdout:
                for line in stdout.strip().split('\n'):  # Toutes les lignes
                    if line.strip():
                        ui_print(f"[subs stdout] {line}", debug=ui_settings.debug)

            # Affiche stderr s'il y a des erreurs
            if stderr and result.returncode != 0:
                for line in stderr.strip().split('\n'):  # Toutes les lignes
                    if line.strip():
                        ui_print(f"[subs stderr] {line}", debug=True)

            # Vérifie si c'était un succès
            if result.returncode == 0:
                ui_print(f"[subs trigger] ✓ Subtitle script completed successfully!", debug=ui_settings.debug)
            else:
                ui_print(f"[subs trigger] ✗ Subtitle script failed with code {result.returncode}", debug=ui_settings.debug)

        except subprocess.TimeoutExpired:
            ui_print("[subs trigger] subprocess timeout after 15 minutes", debug=ui_settings.debug)
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
                plex_section = _pick_plex_section(key)
                ui_print(f"[subs trigger] using plex section {plex_section} for key '{key}'", debug=ui_settings.debug)
                ui_print(f"[subs trigger] media found, launching subtitle script for: {path}", debug=ui_settings.debug)
                _run_subs(path, plex_section_override=plex_section)
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
