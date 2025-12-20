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
from urllib.parse import quote

import requests

# ---- Utils logs ----
def log(msg: str) -> None:
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}", flush=True)

# ---- Video discovery (recursive) ----
VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts"}

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
        raise RuntimeError("Aucun fichier vidéo trouvé.")
    paths = sorted(paths, key=lambda p: os.path.getsize(p), reverse=True)
    return paths[0]

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
            log(f"FFPROBE: sous-titre FR trouvé dans le MKV (lang={lang}, codec={codec}).")
            return True

    log("FFPROBE: aucun sous-titre FR intégré détecté dans le MKV.")
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

def iter_section_all_sorted(baseurl: str, token: str, section: int, page_size: int, max_pages: int):
    # /all supports sort=addedAt:desc and paging (X-Plex-Container-Start/Size)
    for page in range(max_pages):
        start = page * page_size
        params = {
            "type": 1,  # not strictly required; Plex will still return videos
            "sort": "addedAt:desc",
            "X-Plex-Container-Start": start,
            "X-Plex-Container-Size": page_size,
        }
        r = plex_get(baseurl, token, f"/library/sections/{section}/all", params=params)
        r.raise_for_status()
        yield (page + 1, start, r.text)

def find_item_by_exact_file(baseurl: str, token: str, section: int, exact_file: str,
                            page_size: int = 200, max_pages: int = 20, timeout_s: int = 180) -> tuple[str, str, str, str | None]:
    """
    Returns (ratingKey, plex_type, title, year_str_or_None)
    Finds item by matching <Part file="..."> exactly to the mkv full path.
    """
    wanted = os.path.normpath(exact_file)
    deadline = time.time() + timeout_s

    attempt = 0
    while time.time() < deadline:
        attempt += 1
        log(f"SCAN attempt#{attempt} -> /all sort=addedAt:desc (page_size={page_size}, max_pages={max_pages})")
        for (page_no, start, xml_text) in iter_section_all_sorted(baseurl, token, section, page_size, max_pages):
            log(f"SCAN page {page_no}/{max_pages} -> start={start} size={page_size}")
            log(f"SCAN page {page_no} <- HTTP 200 (len={len(xml_text)})")

            try:
                root = ET.fromstring(xml_text)
            except ET.ParseError:
                continue

            # Items are usually <Video ...> with <Media><Part file="...">
            for video in root.findall(".//Video"):
                rating_key = video.attrib.get("ratingKey")
                vtype = video.attrib.get("type", "unknown")
                title = video.attrib.get("title", "")
                year = video.attrib.get("year")

                for part in video.findall(".//Part"):
                    f = part.attrib.get("file", "")
                    if os.path.normpath(f) == wanted:
                        log(f"FOUND (exact file): ratingKey={rating_key} type={vtype} title='{title}'")
                        return rating_key, vtype, title, year

        log("NOT FOUND in /all pages yet. Sleep 3s…")
        time.sleep(3)

    raise RuntimeError("Timeout: Plex n'a pas trouvé l'item (match exact sur le chemin du fichier) dans le délai.")

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
        log(f"OST login try {i}/{max_tries} …")
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
    raise RuntimeError("Aucun sous-titre satisfaisant trouvé (non-AI + file_id présent).")

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
        raise RuntimeError(f"OpenSubtitles download: pas de lien dans la réponse: {meta}")

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
    from plexapi.server import PlexServer  # imported here so script can still run parts without plexapi
    plex = PlexServer(baseurl, token)
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

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseurl", default="http://127.0.0.1:32400")
    ap.add_argument("--token", required=True)
    ap.add_argument("--section", type=int, required=True)
    ap.add_argument("--path", required=True, help="Dossier du média (ex: Z:\\Film\\MonFilm)")
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
    args = parse_args()

    folder = sanitize_folder_path(args.path)
    os.makedirs(args.outdir, exist_ok=True)

    log("START")
    log(f"Args: baseurl={args.baseurl} section={args.section} path='{folder}' outdir='{args.outdir}'")

    # 1) Find mkv/video (recursive), pick largest
    vids = find_video_files_recursive(folder)
    log(f"DIR: video files found = {len(vids)}")
    for v in vids[:10]:
        log(f"DIR: video -> {v}")
    if len(vids) > 10:
        log("DIR: (… liste tronquée …)")
    video_path = pick_largest(vids)
    log(f"DIR: selected (largest) = '{video_path}'")

    # 2) Ask Plex to scan the folder (targeted)
    plex_refresh_section_path(args.baseurl, args.token, args.section, folder)

    # 3) Wait/find Plex item by exact file match
    rating_key, plex_type, plex_title, plex_year = find_item_by_exact_file(
        args.baseurl, args.token, args.section,
        exact_file=video_path,
        page_size=200, max_pages=20, timeout_s=180
    )
    log(f"Plex item: type={plex_type} ratingKey={rating_key} title='{plex_title}' year={plex_year}")

    # 4) Check embedded FR subtitles in MKV (your requirement)
    if has_embedded_french_subtitle(args.ffprobe, video_path):
        log("SKIP: le MKV contient déjà un sous-titre FR intégré -> pas de téléchargement OpenSubtitles.")
        log("END -> OK (already has embedded FR)")
        return 0

    # 5) Download FR from OpenSubtitles.com
    if not args.ost_api_key or not args.ost_user or not args.ost_pass:
        raise RuntimeError("OpenSubtitles: il manque --ost-api-key/--ost-user/--ost-pass (ou variables OST_API_KEY/OST_USER/OST_PASS).")

    bearer = ost_login(args.ost_api_key, args.ost_useragent, args.ost_user, args.ost_pass)

    query = build_query_from_plex_title(plex_title, plex_year)
    log(f"OST search movie: query='{query}' lang={args.lang}")

    results = ost_search_movie(args.ost_api_key, args.ost_useragent, bearer, query=query, year=plex_year, lang=args.lang)
    if not results:
        raise RuntimeError("OpenSubtitles: 0 résultat pour cette recherche.")

    best = ost_pick_best(results)
    file_id = extract_file_id(best)
    if file_id is None:
        raise RuntimeError("OpenSubtitles: candidate choisi mais file_id introuvable (unexpected).")

    blob, remote_name = ost_download(args.ost_api_key, args.ost_useragent, bearer, file_id=file_id)
    srt_text = bytes_to_srt_text(blob)
    if len(srt_text.strip()) < 50:
        raise RuntimeError("OpenSubtitles: contenu SRT trop court (probablement mauvais fichier).")

    # Write
    srt_path = os.path.join(args.outdir, f"plex_{rating_key}.{args.lang}.srt")
    with open(srt_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(srt_text)
    log(f"WROTE -> {srt_path} (remote='{remote_name}')")

    # 6) Upload into Plex as external subtitle
    plex_upload_external_subtitle(args.baseurl, args.token, rating_key, srt_path)

    log("END -> OK")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        log("END -> interrupted")
        raise
