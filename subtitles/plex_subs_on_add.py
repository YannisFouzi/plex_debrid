#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import re
import sys
import time
import gzip
import zipfile
import io
import subprocess
import datetime
import xml.etree.ElementTree as ET

print("[EARLY] Basic imports done, importing requests...", flush=True)
import requests

# Ensure stdout/stderr can emit UTF-8 safely on Windows consoles to avoid encode crashes
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---- Utils logs ----
def log(msg: str) -> None:
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}", flush=True)

# ---- Video discovery (recursive) ----
VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts"}
TIER1_MAX_ATTEMPTS = 3
ENABLE_TIER2 = False
ENABLE_TIER3 = False
RETRY_INTERVAL_S = 15
RETRY_MAX_S = 60
EP_TAG_RE = re.compile(r"(S\d{1,2}E\d{1,2}|\d{1,2}x\d{1,2})", re.IGNORECASE)

def find_video_files_recursive(root: str) -> list[str]:
    out = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in VIDEO_EXTS:
                out.append(os.path.join(dirpath, fn))
    return out

def pick_largest(paths: list[str]) -> str:
    if not paths:
        raise RuntimeError("Aucun fichier vid├®o trouv├®.")
    paths = sorted(paths, key=lambda p: os.path.getsize(p), reverse=True)
    return paths[0]

def looks_like_episode(path: str) -> bool:
    return bool(EP_TAG_RE.search(os.path.basename(path)))

def is_retryable_plex_miss(err: Exception) -> bool:
    msg = str(err).lower()
    if "item not found" in msg:
        return True
    if "tier-3" in msg and "timeout" in msg:
        return True
    if "not found after" in msg and "tier" in msg:
        return True
    return False

# ---- ffprobe check: does MKV contain embedded FR subtitles? ----
FR_LANGS = {"fr", "fra", "fre", "french"}

def has_embedded_french_subtitle(ffprobe_bin: str, video_path: str) -> bool:
    """
    Returns True if ffprobe detects a subtitle stream with language tag matching FR.
    This checks embedded tracks inside the container (exactly what you want).
    """
    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "s",
        video_path,
    ]
    log(f"FFPROBE -> {' '.join(cmd)}")
    try:
        p = subprocess.run(cmd, capture_output=True, text=False, check=False)
    except FileNotFoundError:
        raise RuntimeError("ffprobe introuvable. Verifie ton PATH ou passe --ffprobe.")
    stdout = p.stdout if p.stdout is not None else b""
    stderr = p.stderr if p.stderr is not None else b""
    stdout_text = stdout.decode("utf-8", errors="replace").strip()
    stderr_text = stderr.decode("utf-8", errors="replace").strip()
    if p.returncode != 0:
        log(f"FFPROBE <- rc={p.returncode}")
        log(f"FFPROBE stderr: {stderr_text}")
        return False
    if not stdout_text:
        log("FFPROBE: sortie vide, skip check.")
        return False

    try:
        data = json.loads(stdout_text)
    except (json.JSONDecodeError, TypeError):
        log("FFPROBE: sortie JSON invalide, skip check.")
        return False

    streams = data.get("streams", []) or []
    for s in streams:
        tags = s.get("tags", {}) or {}
        lang = (tags.get("language") or tags.get("LANGUAGE") or "").strip().lower()
        if lang in FR_LANGS:
            codec = s.get("codec_name", "?")
            log(f"FFPROBE: sous-titre FR trouv├® dans le MKV (lang={lang}, codec={codec}).")
            return True

    log("FFPROBE: aucun sous-titre FR int├®gr├® d├®tect├® dans le MKV.")
    return False

# ---- Plex helpers ----
def plex_get(baseurl: str, token: str, path: str, params: dict | None = None) -> requests.Response:
    url = baseurl.rstrip("/") + path
    params = dict(params or {})
    params["X-Plex-Token"] = token
    r = requests.get(url, params=params, timeout=30)
    return r

def plex_refresh_section_path(baseurl: str, token: str, section: int, folder_path: str) -> None:
    # Plex Windows accepte refresh?path=<folder>
    log(f"REFRESH -> GET {baseurl}/library/sections/{section}/refresh?path=...  path='{folder_path}'")
    r = plex_get(baseurl, token, f"/library/sections/{section}/refresh", params={"path": folder_path})
    log(f"REFRESH <- HTTP {r.status_code}")
    r.raise_for_status()

# ---- NEW: Optimized multi-tier search functions ----

def extract_title_from_filepath(filepath: str) -> str:
    """
    Extract a clean title from a file path for search purposes.
    E.g., "Batman.Begins.2005.2160p.UHD.BDRemux.mkv" -> "Batman Begins"
    """
    filename = os.path.basename(filepath)
    # Remove extension
    name = os.path.splitext(filename)[0]

    # Remove common patterns (year, resolution, codec info, etc.)
    # Remove year pattern (4 digits between 1900-2099)
    name = re.sub(r'\b(19|20)\d{2}\b', '', name)

    # Remove resolution patterns
    name = re.sub(r'\b(480p|576p|720p|1080p|2160p|4K|UHD)\b', '', name, flags=re.IGNORECASE)

    # Remove codec/quality patterns
    name = re.sub(r'\b(BDRemux|BluRay|BRRip|WEB-DL|WEBRip|HDTV|HDRip|DVDRip|x264|x265|H264|H265|HEVC|DTS|AAC|AC3)\b', '', name, flags=re.IGNORECASE)

    # Remove release group tags in brackets
    name = re.sub(r'\[.*?\]|\(.*?\)', '', name)

    # Replace dots and underscores with spaces
    name = re.sub(r'[._-]+', ' ', name)

    # Remove any remaining special characters
    name = re.sub(r'[^\w\s]', ' ', name)

    # Clean up multiple spaces and trim
    name = re.sub(r'\s+', ' ', name).strip()

    return name

def find_item_tier1_recently_added(baseurl: str, token: str, section: int, exact_file: str,
                                   timeout_s: int = 30, max_attempts: int = TIER1_MAX_ATTEMPTS) -> tuple[str, str, str, str | None, str | None, str | None, str | None] | None:
    """
    TIER 1: Check recently added items first (fastest).
    Returns (ratingKey, plex_type, title, year_str_or_None, show_title, season_index, episode_index) or None if not found.
    """
    wanted = os.path.normpath(exact_file)
    deadline = time.time() + timeout_s

    attempt = 0
    while time.time() < deadline and attempt < max_attempts:
        attempt += 1
        log(f"[TIER-1] attempt #{attempt} -> checking /recentlyAdded (first 100 items)")

        try:
            # Get the last 100 recently added items
            params = {
                "X-Plex-Container-Start": 0,
                "X-Plex-Container-Size": 100,
            }
            r = plex_get(baseurl, token, f"/library/sections/{section}/recentlyAdded", params=params)
            r.raise_for_status()

            # Parse XML response
            root = ET.fromstring(r.text)

            # Check each video item
            for video in root.findall(".//Video"):
                rating_key = video.attrib.get("ratingKey")
                vtype = video.attrib.get("type", "unknown")
                title = video.attrib.get("title", "")
                year = video.attrib.get("year")
                show_title = video.attrib.get("grandparentTitle")
                season_index = video.attrib.get("parentIndex")
                episode_index = video.attrib.get("index")

                # Check file parts
                for part in video.findall(".//Part"):
                    file_path = part.attrib.get("file", "")
                    if os.path.normpath(file_path) == wanted:
                        log(f"[TIER-1] FOUND in recently added (attempt #{attempt}): ratingKey={rating_key} title='{title}'")
                        return rating_key, vtype, title, year, show_title, season_index, episode_index

            log(f"[TIER-1] Not found in recently added items, retrying in 2s...")

        except ET.ParseError as e:
            log(f"[TIER-1] XML parse error: {e}")
        except requests.RequestException as e:
            log(f"[TIER-1] API request error: {e}")

        time.sleep(2)

    log(f"[TIER-1] Not found after {attempt} attempts (max {max_attempts}, timeout: {timeout_s}s)")
    return None

def find_item_tier2_search(baseurl: str, token: str, section: int, exact_file: str,
                           timeout_s: int = 20) -> tuple[str, str, str, str | None, str | None, str | None, str | None] | None:
    """
    TIER 2: Search by extracted title (medium speed).
    Returns (ratingKey, plex_type, title, year_str_or_None, show_title, season_index, episode_index) or None if not found.
    """
    wanted = os.path.normpath(exact_file)

    # Extract search query from filename
    search_query = extract_title_from_filepath(exact_file)

    if not search_query or len(search_query) < 3:
        log(f"[TIER-2] Cannot extract valid search query from filename, skipping tier 2")
        return None

    deadline = time.time() + timeout_s
    attempt = 0

    while time.time() < deadline:
        attempt += 1
        log(f"[TIER-2] attempt #{attempt} -> searching for '{search_query}'")

        try:
            # Search in the specific section
            params = {
                "query": search_query,
                "sectionId": section,
                "limit": 50,  # Limit results
            }
            r = plex_get(baseurl, token, "/search", params=params)
            r.raise_for_status()

            # Parse XML response
            root = ET.fromstring(r.text)

            # Check each video item in search results
            for video in root.findall(".//Video"):
                rating_key = video.attrib.get("ratingKey")
                vtype = video.attrib.get("type", "unknown")
                title = video.attrib.get("title", "")
                year = video.attrib.get("year")
                show_title = video.attrib.get("grandparentTitle")
                season_index = video.attrib.get("parentIndex")
                episode_index = video.attrib.get("index")

                # Check file parts
                for part in video.findall(".//Part"):
                    file_path = part.attrib.get("file", "")
                    if os.path.normpath(file_path) == wanted:
                        log(f"[TIER-2] FOUND via search (query='{search_query}'): ratingKey={rating_key} title='{title}'")
                        return rating_key, vtype, title, year, show_title, season_index, episode_index

            log(f"[TIER-2] Not found in search results for '{search_query}', retrying in 3s...")

        except ET.ParseError as e:
            log(f"[TIER-2] XML parse error: {e}")
        except requests.RequestException as e:
            log(f"[TIER-2] API request error: {e}")

        time.sleep(3)

    log(f"[TIER-2] Not found after {attempt} attempts (timeout: {timeout_s}s)")
    return None

def find_item_tier3_full_scan(baseurl: str, token: str, section: int, exact_file: str,
                              page_size: int = 500, max_pages: int = 10, timeout_s: int = 60) -> tuple[str, str, str, str | None, str | None, str | None, str | None]:
    """
    TIER 3: Full library scan (slowest but most thorough).
    Returns (ratingKey, plex_type, title, year_str_or_None, show_title, season_index, episode_index).
    """
    wanted = os.path.normpath(exact_file)
    deadline = time.time() + timeout_s

    attempt = 0
    while time.time() < deadline:
        attempt += 1
        log(f"[TIER-3] attempt #{attempt} -> full scan (page_size={page_size}, max_pages={max_pages})")

        for page in range(max_pages):
            start = page * page_size
            log(f"[TIER-3] scanning page {page + 1}/{max_pages} (start={start}, size={page_size})")

            try:
                params = {
                    "type": 1,  # Movies
                    "sort": "addedAt:desc",
                    "X-Plex-Container-Start": start,
                    "X-Plex-Container-Size": page_size,
                }
                r = plex_get(baseurl, token, f"/library/sections/{section}/all", params=params)
                r.raise_for_status()

                # Parse XML response
                root = ET.fromstring(r.text)

                # Check if we got any items
                items_count = len(root.findall(".//Video"))
                log(f"[TIER-3] page {page + 1} has {items_count} items")

                if items_count == 0:
                    log(f"[TIER-3] No more items, stopping pagination")
                    break

                # Check each video item
                for video in root.findall(".//Video"):
                    rating_key = video.attrib.get("ratingKey")
                    vtype = video.attrib.get("type", "unknown")
                    title = video.attrib.get("title", "")
                    year = video.attrib.get("year")
                    show_title = video.attrib.get("grandparentTitle")
                    season_index = video.attrib.get("parentIndex")
                    episode_index = video.attrib.get("index")

                    # Check file parts
                    for part in video.findall(".//Part"):
                        file_path = part.attrib.get("file", "")
                        if os.path.normpath(file_path) == wanted:
                            log(f"[TIER-3] FOUND via full scan: ratingKey={rating_key} title='{title}'")
                            return rating_key, vtype, title, year, show_title, season_index, episode_index

            except ET.ParseError as e:
                log(f"[TIER-3] XML parse error on page {page + 1}: {e}")
                continue
            except requests.RequestException as e:
                log(f"[TIER-3] API request error on page {page + 1}: {e}")
                continue

        log(f"[TIER-3] Not found after scanning {max_pages} pages, waiting 3s before retry...")
        time.sleep(3)

    raise RuntimeError(f"[TIER-3] Timeout: Item not found after {attempt} full scan attempts")

def find_item_by_exact_file_optimized(baseurl: str, token: str, section: int, exact_file: str) -> tuple[str, str, str, str | None, str | None, str | None, str | None]:
    """
    Optimized multi-tier approach to find a Plex item by exact file path.
    Tries progressively slower but more thorough methods.
    Returns (ratingKey, plex_type, title, year_str_or_None, show_title, season_index, episode_index).
    """
    log(f"SEARCH: Starting optimized search for file: {exact_file}")

    # TIER 1: Check recently added items (fastest, 95% hit rate)
    log("[TIER-1] Starting: Recently Added scan")
    result = find_item_tier1_recently_added(
        baseurl, token, section, exact_file,
        timeout_s=30, max_attempts=TIER1_MAX_ATTEMPTS
    )
    if result:
        log(f"[SUCCESS] Found via TIER-1 in < 30s")
        return result
    log("[TIER-1] Not found")

    if ENABLE_TIER2:
        # TIER 2: Search by title extracted from filename (fast, 4% hit rate)
        log("[TIER-2] Starting: Search by extracted title")
        result = find_item_tier2_search(baseurl, token, section, exact_file, timeout_s=20)
        if result:
            log(f"[SUCCESS] Found via TIER-2 in < 20s")
            return result
        log("[TIER-2] Not found, moving to TIER-3")
    else:
        log("[TIER-2] Skipped (disabled)")

    if ENABLE_TIER3:
        # TIER 3: Full library scan (slow but thorough, 1% hit rate)
        log("[TIER-3] Starting: Full library scan (fallback)")
        result = find_item_tier3_full_scan(baseurl, token, section, exact_file,
                                         page_size=500, max_pages=10, timeout_s=60)
        log("[TIER-3] Completed")
        return result
    log("[TIER-3] Skipped (disabled)")
    raise RuntimeError("[TIER-1] Item not found in recently added; TIER-2/3 disabled")

# ---- OpenSubtitles.com API (direct HTTP) ----
API_BASE = "https://api.opensubtitles.com/api/v1"

def ost_headers(api_key: str, user_agent: str, bearer: str | None = None) -> dict:
    h = {
        "Api-Key": api_key,
        "User-Agent": user_agent,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if bearer:
        h["Authorization"] = f"Bearer {bearer}"
    return h

def ost_login(api_key: str, user_agent: str, username: str, password: str, max_tries: int = 10) -> str:
    url = f"{API_BASE}/login"
    payload = {"username": username, "password": password}
    for i in range(1, max_tries + 1):
        log(f"OST login try {i}/{max_tries} ÔÇª")
        r = requests.post(url, headers=ost_headers(api_key, user_agent), json=payload, timeout=30)
        if r.status_code == 429:
            # rate-limit 1 req/sec -> backoff simple
            time.sleep(1.2)
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"OpenSubtitles login failed: HTTP {r.status_code} {r.text}")
        data = r.json()
        token = data.get("token")
        if not token:
            raise RuntimeError(f"OpenSubtitles login: token absent. Response: {data}")
        log("OST login OK")
        return token
    raise RuntimeError("OpenSubtitles login: trop de 429, abandon.")

def ost_search_movie(api_key: str, user_agent: str, bearer: str, query: str, year: str | None, lang: str = "fr") -> list[dict]:
    url = f"{API_BASE}/subtitles"
    params = {"query": query, "languages": lang, "order_by": "download_count", "order_direction": "desc"}
    if year and year.isdigit():
        params["year"] = year
    r = requests.get(url, headers=ost_headers(api_key, user_agent, bearer), params=params, timeout=30)
    if r.status_code == 429:
        time.sleep(1.2)
        r = requests.get(url, headers=ost_headers(api_key, user_agent, bearer), params=params, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"OpenSubtitles search failed: HTTP {r.status_code} {r.text}")
    data = r.json()
    return data.get("data", []) or []

def extract_file_id(candidate: dict) -> int | None:
    # Typical: candidate["attributes"]["files"][0]["file_id"]
    attrs = candidate.get("attributes", {}) or {}
    files = attrs.get("files", []) or []
    if files and isinstance(files[0], dict):
        fid = files[0].get("file_id")
        if isinstance(fid, int):
            return fid
    return None

def is_ai_translated(candidate: dict) -> bool:
    attrs = candidate.get("attributes", {}) or {}
    # Some API responses include ai_translated in attributes
    ai = attrs.get("ai_translated")
    if ai is True:
        return True
    # Fallback heuristic (very conservative)
    rel = (attrs.get("release") or "").lower()
    if "chatgpt" in rel or "ai translated" in rel:
        return True
    return False

def ost_pick_best(candidates: list[dict]) -> dict:
    for idx, c in enumerate(candidates[:50], start=1):
        attrs = c.get("attributes", {}) or {}
        release = attrs.get("release") or ""
        ai_flag = is_ai_translated(c)
        log(f"OST candidate #{idx}: release='{release}' ai_flag={ai_flag}")
        if ai_flag:
            continue
        fid = extract_file_id(c)
        if fid is None:
            continue
        log(f"OST candidate #{idx}: accepted")
        return c
    raise RuntimeError("Aucun sous-titre satisfaisant trouv├® (non-AI + file_id pr├®sent).")

def ost_download(api_key: str, user_agent: str, bearer: str, file_id: int) -> tuple[bytes, str | None]:
    url = f"{API_BASE}/download"
    payload = {"file_id": file_id}
    r = requests.post(url, headers=ost_headers(api_key, user_agent, bearer), json=payload, timeout=30)
    if r.status_code == 429:
        time.sleep(1.2)
        r = requests.post(url, headers=ost_headers(api_key, user_agent, bearer), json=payload, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"OpenSubtitles download init failed: HTTP {r.status_code} {r.text}")

    meta = r.json()
    link = meta.get("link") or meta.get("url")
    fname = meta.get("file_name") or meta.get("filename")

    if not link:
        raise RuntimeError(f"OpenSubtitles download: pas de lien dans la r├®ponse: {meta}")

    log(f"OST download -> GET {link}")
    r2 = requests.get(link, timeout=60)
    if r2.status_code >= 400:
        raise RuntimeError(f"OpenSubtitles file GET failed: HTTP {r2.status_code}")

    return r2.content, fname

def bytes_to_srt_text(blob: bytes) -> str:
    # Handle zip
    if blob.startswith(b"PK\x03\x04"):
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            # pick first .srt
            srt_names = [n for n in z.namelist() if n.lower().endswith(".srt")]
            name = srt_names[0] if srt_names else z.namelist()[0]
            data = z.read(name)
            return data.decode("utf-8", errors="replace")

    # Handle gzip
    if blob.startswith(b"\x1f\x8b"):
        try:
            data = gzip.decompress(blob)
            return data.decode("utf-8", errors="replace")
        except Exception:
            pass

    # Plain text
    try:
        return blob.decode("utf-8", errors="replace")
    except Exception:
        return blob.decode(errors="replace")

# ---- Plex upload (using plexapi) ----
def plex_upload_external_subtitle(baseurl: str, token: str, rating_key: str, srt_path: str) -> None:
    log(f"UPLOAD: Importing plexapi.server...")
    from plexapi.server import PlexServer  # imported here so script can still run parts without plexapi
    log(f"UPLOAD: plexapi imported, connecting to PlexServer...")
    plex = PlexServer(baseurl, token)
    log(f"UPLOAD: Connected, fetching item with ratingKey={rating_key}...")
    item = plex.fetchItem(int(rating_key))
    log(f"UPLOAD -> Plex uploadSubtitles('{srt_path}')")
    item.uploadSubtitles(srt_path)
    log("UPLOAD OK")

# ---- Main ----
def sanitize_folder_path(p: str) -> str:
    p = p.strip().strip('"').strip("'")
    # normalize to Windows style, keep trailing backslash for folder refresh
    p = os.path.normpath(p)
    if not p.endswith(os.sep):
        p += os.sep
    return p

def build_query_from_plex_title(title: str, year: str | None) -> str:
    # Keep it simple and stable
    t = title.strip()
    t = re.sub(r"\s+", " ", t)
    if year and year.isdigit():
        return f"{t} {year}"
    return t

def format_sxxexx(season_index: str | None, episode_index: str | None) -> str | None:
    try:
        season_num = int(season_index)
        episode_num = int(episode_index)
    except (TypeError, ValueError):
        return None
    return f"S{season_num:02d}E{episode_num:02d}"

def extract_series_title_from_filename(filepath: str) -> str | None:
    base = os.path.splitext(os.path.basename(filepath))[0]
    m = EP_TAG_RE.search(base)
    if not m:
        return None
    title = base[:m.start()]
    title = re.sub(r"\[.*?\]|\(.*?\)", " ", title)
    title = re.sub(r"[._\-\s]+$", "", title)
    title = re.sub(r"[._-]+", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title or None

def build_query_for_episode_from_file(filepath: str, season_index: str | None, episode_index: str | None) -> str | None:
    title = extract_series_title_from_filename(filepath)
    if not title:
        return None
    tag = format_sxxexx(season_index, episode_index)
    if not tag:
        return None
    t = re.sub(r"\s+", " ", title.strip())
    return f"{t} {tag}"

def build_query_for_episode(show_title: str | None, season_index: str | None, episode_index: str | None) -> str | None:
    if not show_title:
        return None
    tag = format_sxxexx(season_index, episode_index)
    if not tag:
        return None
    t = show_title.strip()
    t = re.sub(r"\s+", " ", t)
    return f"{t} {tag}"

def filter_candidates_by_tag(candidates: list[dict], tag: str | None) -> list[dict]:
    if not tag:
        return candidates
    tag_lc = tag.lower()
    out = []
    for c in candidates:
        attrs = c.get("attributes", {}) or {}
        release = (attrs.get("release") or "").lower()
        if tag_lc in release:
            out.append(c)
    return out

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseurl", default="http://127.0.0.1:32400")
    ap.add_argument("--token", required=True)
    ap.add_argument("--section", type=int, required=True)
    ap.add_argument("--path", required=True, help="Dossier du m├®dia (ex: Z:\\Film\\MonFilm)")
    ap.add_argument("--outdir", default=r"C:\PlexAutomation\PlexSubtitles")
    ap.add_argument("--lang", default="fr")

    # ffprobe
    ap.add_argument("--ffprobe", default="ffprobe", help="Chemin vers ffprobe.exe (default: ffprobe dans PATH)")

    # OpenSubtitles API
    ap.add_argument("--ost-api-key", default=os.environ.get("OST_API_KEY"))
    ap.add_argument("--ost-user", default=os.environ.get("OST_USER"))
    ap.add_argument("--ost-pass", default=os.environ.get("OST_PASS"))
    ap.add_argument("--ost-useragent", default=os.environ.get("OST_USERAGENT", "PlexSubAuto/1.0"))

    return ap.parse_args()

def main():
    log("MAIN: Parsing arguments...")
    args = parse_args()
    log("MAIN: Arguments parsed")

    log(f"MAIN: Sanitizing folder path: {args.path}")
    folder = sanitize_folder_path(args.path)
    log(f"MAIN: Folder sanitized: {folder}")

    log(f"MAIN: Creating output directory: {args.outdir}")
    os.makedirs(args.outdir, exist_ok=True)
    log("MAIN: Output directory ready")

    log("START")
    log(f"Args: baseurl={args.baseurl} section={args.section} path='{folder}' outdir='{args.outdir}'")

    # 1) Find mkv/video (recursive), process all videos (episodes or movie)
    log("MAIN: Starting video file search (recursive)...")
    video_paths = find_video_files_recursive(folder)
    log(f"MAIN: Video search completed, found {len(video_paths) if video_paths else 0} files")

    if not video_paths:
        raise RuntimeError("Aucun fichier video trouve.")
    video_paths = sorted(video_paths)
    primary = pick_largest(video_paths)
    video_paths = [primary] + [p for p in video_paths if p != primary]
    log(f"MAIN: Prioritizing largest video file first: {primary}")
    log(f"DIR: video files found = {len(video_paths)}")
    for v in video_paths[:10]:
        log(f"DIR: video -> {v}")
    if len(video_paths) > 10:
        log("DIR: (liste tronquee)")

    # 2) Ask Plex to scan the folder (targeted)
    log("MAIN: Requesting Plex refresh...")
    plex_refresh_section_path(args.baseurl, args.token, args.section, folder)
    log("MAIN: Plex refresh request completed")

    # 3) Login OpenSubtitles once
    log("MAIN: Checking OpenSubtitles credentials...")
    if not args.ost_api_key or not args.ost_user or not args.ost_pass:
        raise RuntimeError("OpenSubtitles: il manque --ost-api-key/--ost-user/--ost-pass (ou variables OST_API_KEY/OST_USER/OST_PASS).")
    log("MAIN: Logging into OpenSubtitles...")
    bearer = ost_login(args.ost_api_key, args.ost_useragent, args.ost_user, args.ost_pass)
    log("MAIN: OpenSubtitles login successful")

    success = 0
    failures = []
    missing = []
    retry_enabled = any(looks_like_episode(p) for p in video_paths)
    if retry_enabled:
        log(f"RETRY: enabled interval={RETRY_INTERVAL_S}s max={RETRY_MAX_S}s")

    def process_video(video_path: str, idx: int, total: int, phase: str) -> tuple[str, str | None]:
        prefix = "MAIN" if phase == "MAIN" else f"RETRY-{phase}"
        log(f"{prefix}: [{idx}/{total}] Processing video file...")
        log(f"PROCESS -> {video_path}")
        try:
            log(f"{prefix}: [{idx}/{total}] Starting Plex item search...")
            rating_key, plex_type, plex_title, plex_year, show_title, season_index, episode_index = find_item_by_exact_file_optimized(
                args.baseurl, args.token, args.section,
                exact_file=video_path
            )
            log(f"{prefix}: [{idx}/{total}] Plex item found")
            log(f"Plex item: type={plex_type} ratingKey={rating_key} title='{plex_title}' year={plex_year}")
        except Exception as e:
            log(f"ERROR on {video_path}: {e}")
            if retry_enabled and looks_like_episode(video_path) and is_retryable_plex_miss(e):
                log(f"{prefix}: [{idx}/{total}] DEFERRED - Plex item missing, will retry")
                return "missing", str(e)
            log(f"{prefix}: [{idx}/{total}] FAILED - Continuing to next video")
            return "failed", str(e)

        try:
            # Skip if embedded FR
            log(f"{prefix}: [{idx}/{total}] Checking for embedded French subtitles...")
            if has_embedded_french_subtitle(args.ffprobe, video_path):
                log("SKIP: sous-titre FR deja present -> pas de telechargement.")
                return "success", None

            log(f"{prefix}: [{idx}/{total}] No embedded FR subtitles, searching OpenSubtitles...")
            if plex_type == "episode":
                tag = format_sxxexx(season_index, episode_index)
                if not tag:
                    raise RuntimeError("OpenSubtitles: impossible de construire la requete episode (saison/episode manquants).")
                queries = []
                file_query = build_query_for_episode_from_file(video_path, season_index, episode_index)
                if file_query:
                    queries.append(("file", file_query))
                plex_query = build_query_for_episode(show_title, season_index, episode_index)
                if plex_query and (not file_query or plex_query.lower() != file_query.lower()):
                    queries.append(("plex", plex_query))
                if not queries:
                    raise RuntimeError("OpenSubtitles: impossible de construire la requete episode (titre introuvable).")
                results = []
                for source, query in queries:
                    log(f"OST search: query='{query}' source={source} lang={args.lang}")
                    results = ost_search_movie(args.ost_api_key, args.ost_useragent, bearer, query=query, year=None, lang=args.lang)
                    results = filter_candidates_by_tag(results, tag)
                    if results:
                        if source != "file":
                            log(f"{prefix}: [{idx}/{total}] OST fallback used source={source}")
                        log(f"{prefix}: [{idx}/{total}] {len(results)} candidate(s) after SxxEyy filter")
                        break
            else:
                query = build_query_from_plex_title(plex_title, plex_year)
                log(f"OST search: query='{query}' lang={args.lang}")
                results = ost_search_movie(args.ost_api_key, args.ost_useragent, bearer, query=query, year=plex_year, lang=args.lang)
            if not results:
                raise RuntimeError("OpenSubtitles: 0 resultat pour cette recherche.")

            log(f"{prefix}: [{idx}/{total}] Found {len(results)} subtitle(s), picking best...")
            best = ost_pick_best(results)
            file_id = extract_file_id(best)
            if file_id is None:
                raise RuntimeError("OpenSubtitles: candidate choisi mais file_id introuvable (unexpected).")

            log(f"{prefix}: [{idx}/{total}] Downloading subtitle file_id={file_id}...")
            blob, remote_name = ost_download(args.ost_api_key, args.ost_useragent, bearer, file_id=file_id)
            srt_text = bytes_to_srt_text(blob)
            if len(srt_text.strip()) < 50:
                raise RuntimeError("OpenSubtitles: contenu SRT trop court (probablement mauvais fichier).")

            srt_path = os.path.join(args.outdir, f"plex_{rating_key}.{args.lang}.srt")
            with open(srt_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(srt_text)
            log(f"WROTE -> {srt_path} (remote='{remote_name}')")

            log(f"{prefix}: [{idx}/{total}] Uploading subtitle to Plex...")
            plex_upload_external_subtitle(args.baseurl, args.token, rating_key, srt_path)
            log("UPLOAD OK")
            log(f"{prefix}: [{idx}/{total}] SUCCESS - Video completed")
            return "success", None
        except Exception as e:
            log(f"ERROR on {video_path}: {e}")
            log(f"{prefix}: [{idx}/{total}] FAILED - Continuing to next video")
            return "failed", str(e)

    # 4) Process each video file
    log(f"MAIN: Starting processing loop for {len(video_paths)} video file(s)...")
    for idx, video_path in enumerate(video_paths, 1):
        status, err = process_video(video_path, idx, len(video_paths), "MAIN")
        if status == "success":
            success += 1
        elif status == "missing":
            missing.append(video_path)
        else:
            failures.append((video_path, err or "unknown error"))

    if retry_enabled and missing:
        retry_start = time.time()
        pass_no = 0
        while missing:
            elapsed = time.time() - retry_start
            remaining = RETRY_MAX_S - elapsed
            if remaining <= 0:
                break
            pass_no += 1
            sleep_s = min(RETRY_INTERVAL_S, remaining)
            log(f"RETRY: waiting {int(sleep_s)}s before pass {pass_no} for {len(missing)} item(s)")
            time.sleep(sleep_s)
            log(f"RETRY-{pass_no}: starting pass for {len(missing)} item(s)")
            new_missing = []
            for idx, video_path in enumerate(missing, 1):
                status, err = process_video(video_path, idx, len(missing), str(pass_no))
                if status == "success":
                    success += 1
                elif status == "missing":
                    new_missing.append(video_path)
                else:
                    failures.append((video_path, err or "unknown error"))
            missing = new_missing

        if missing:
            log(f"RETRY: giving up on {len(missing)} item(s) after {int(time.time() - retry_start)}s")
            for video_path in missing:
                failures.append((video_path, "Plex item still not found after retries"))

    if success == 0:
        raise RuntimeError("Aucun sous-titre n'a pu etre ajoute.")
    if failures:
        log(f"Completed with {success} success, {len(failures)} failure(s).")
    else:
        log("END -> OK")
    return 0
if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        log("END -> interrupted")
        raise
    except Exception as e:
        log(f"END -> exception: {e}")
        import traceback
        traceback.print_exc()
        raise
