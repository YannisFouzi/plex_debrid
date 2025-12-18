import argparse
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import requests
from plexapi.server import PlexServer
from opensubtitlescom import OpenSubtitles


# ---------------------------
# Logs
# ---------------------------
def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------
# Path helpers
# ---------------------------
VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".ts"}


def normalize_win_path(p: str) -> str:
    p = str(p).replace("/", "\\")
    p = p.strip().strip('"').strip("'")
    return p


def ensure_trailing_backslash(folder: str) -> str:
    folder = normalize_win_path(folder)
    return folder if folder.endswith("\\") else folder + "\\"


def list_video_files_recursive(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            out.append(p)
    return out


def pick_largest(paths: list[Path]) -> Path:
    return max(paths, key=lambda p: p.stat().st_size)


def find_target_video(path_arg: str) -> Path:
    p = Path(normalize_win_path(path_arg))
    if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
        return p

    if not p.exists() or not p.is_dir():
        raise SystemExit(f"Path invalide (pas un fichier vidéo, ni un dossier existant): {p}")

    vids = list_video_files_recursive(p)
    log(f"DIR: video files found = {len(vids)}")
    if not vids:
        raise SystemExit(f"Aucun fichier vidéo trouvé dans: {p}")

    for v in vids[:5]:
        log(f"DIR: video -> {v}")

    chosen = pick_largest(vids)
    log(f"DIR: selected (largest) = '{chosen}'")
    return chosen


# ---------------------------
# Plex: scan + find ratingKey by exact file match
# ---------------------------
def plex_refresh_section_path(baseurl: str, token: str, section: int, folder_path: str) -> None:
    url = f"{baseurl}/library/sections/{section}/refresh?path={quote(folder_path)}&X-Plex-Token={quote(token)}"
    log(f"REFRESH -> GET {url.split('&X-Plex-Token=')[0]}  path='{folder_path}'")
    r = requests.get(url, timeout=30)
    log(f"REFRESH <- HTTP {r.status_code}")
    r.raise_for_status()


def wait_find_rating_key_by_file_scan_all(
    baseurl: str,
    token: str,
    section: int,
    target_file: str,
    timeout_s: int = 240,
    page_size: int = 200,
    max_pages: int = 20,
) -> tuple[str, str, str]:
    deadline = time.time() + timeout_s
    want = normalize_win_path(target_file).lower()
    url = f"{baseurl}/library/sections/{section}/all"

    attempt = 0
    while time.time() < deadline:
        attempt += 1
        log(f"SCAN attempt#{attempt} -> /all sort=addedAt:desc (page_size={page_size}, max_pages={max_pages})")

        for page in range(max_pages):
            start = page * page_size
            params = {
                "X-Plex-Token": token,
                "X-Plex-Container-Start": start,
                "X-Plex-Container-Size": page_size,
                "sort": "addedAt:desc",
            }
            log(f"SCAN page {page+1}/{max_pages} -> start={start} size={page_size}")
            r = requests.get(url, params=params, timeout=60)
            log(f"SCAN page {page+1} <- HTTP {r.status_code} (len={len(r.text)})")
            r.raise_for_status()

            root = ET.fromstring(r.text)
            videos = list(root.iter("Video"))
            if not videos:
                break

            for video in videos:
                rkey = video.attrib.get("ratingKey", "")
                vtype = video.attrib.get("type", "")
                title = video.attrib.get("title", "")
                year = video.attrib.get("year")

                for part in video.iter("Part"):
                    f = part.attrib.get("file", "")
                    if normalize_win_path(f).lower() == want:
                        nice_title = title + (f" ({year})" if year else "")
                        log(f"FOUND (exact file): ratingKey={rkey} type={vtype} title='{nice_title}'")
                        return (rkey, vtype, nice_title)

        log("NOT FOUND in /all yet. Sleep 3s…")
        time.sleep(3)

    raise TimeoutError("Timeout: Plex n'a pas trouvé ce fichier via /library/sections/{section}/all")


# ---------------------------
# OpenSubtitles helpers
# ---------------------------
def subtitle_obj_to_dict(obj) -> dict:
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict()
        except Exception:
            return {}
    if isinstance(obj, dict):
        return obj
    return {}


def is_ai_or_machine_translated(sub_dict: dict) -> bool:
    attrs = sub_dict.get("attributes", sub_dict)
    for k in ("ai_translated", "machine_translated", "is_ai_translated"):
        if attrs.get(k) is True:
            return True
    return False


def extract_release_text(sub_dict: dict) -> str:
    attrs = sub_dict.get("attributes", sub_dict)
    rel = attrs.get("release") or attrs.get("release_name") or ""
    return rel if isinstance(rel, str) else ""


def iter_best_subtitles(resp, prefer_release_contains: str | None = None):
    data = getattr(resp, "data", []) or []
    if not data:
        return

    # 1) d'abord candidates non-AI
    primary = []
    secondary = []
    for s in data:
        d = subtitle_obj_to_dict(s)
        (secondary if is_ai_or_machine_translated(d) else primary).append((s, d))

    candidates = primary + secondary

    # 2) si on force un release, on remonte ceux qui matchent
    if prefer_release_contains:
        needle = prefer_release_contains.lower()
        rel_matches = [c for c in candidates if needle in extract_release_text(c[1]).lower()]
        non_matches = [c for c in candidates if c not in rel_matches]
        candidates = rel_matches + non_matches

    for s, d in candidates:
        yield s, d


def td_to_srt_timestamp(td: timedelta) -> str:
    total_ms = int(td.total_seconds() * 1000)
    if total_ms < 0:
        total_ms = 0
    h = total_ms // 3600000
    rem = total_ms % 3600000
    m = rem // 60000
    rem = rem % 60000
    s = rem // 1000
    ms = rem % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def serialize_subtitle_list_to_srt(subs: list) -> str:
    lines: list[str] = []
    for i, sub in enumerate(subs, start=1):
        idx = getattr(sub, "index", i) or i
        start = getattr(sub, "start", None)
        end = getattr(sub, "end", None)
        content = getattr(sub, "content", "")

        if isinstance(start, timedelta) and isinstance(end, timedelta):
            ts = f"{td_to_srt_timestamp(start)} --> {td_to_srt_timestamp(end)}"
        else:
            ts = "00:00:00,000 --> 00:00:00,000"

        text = str(content).replace("\r\n", "\n").replace("\r", "\n").strip()

        lines.append(str(idx))
        lines.append(ts)
        lines.append(text)
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def download_srt_text_from_opensubtitles(ost: OpenSubtitles, subtitle_obj) -> str:
    srt_obj = ost.download_and_parse(subtitle_obj)

    if isinstance(srt_obj, (bytes, bytearray)):
        return srt_obj.decode("utf-8", errors="replace")

    if isinstance(srt_obj, str):
        return srt_obj if srt_obj.endswith("\n") else (srt_obj + "\n")

    if isinstance(srt_obj, list):
        if not srt_obj:
            return ""
        if isinstance(srt_obj[0], str):
            return "\n".join(srt_obj).strip() + "\n"
        return serialize_subtitle_list_to_srt(srt_obj)

    return str(srt_obj).strip() + "\n"


def looks_like_valid_srt(text: str) -> bool:
    # Timestamp SRT classique
    return bool(re.search(r"\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}", text))


def is_bad_ai_srt(text: str) -> bool:
    bad_markers = [
        "Traduit par ChatGPT",
        "fait via Google Translate",
        "Google Translate",
        "machine translated",
        "AI translated",
    ]
    t = text.lower()
    return any(m.lower() in t for m in bad_markers)


# ---------------------------
# Plex upload
# ---------------------------
def plex_upload_subtitle(baseurl: str, token: str, rating_key: str, srt_path: str) -> None:
    plex = PlexServer(baseurl, token)
    item = plex.fetchItem(int(rating_key))
    log(f"UPLOAD -> Plex uploadSubtitles('{srt_path}')")
    item.uploadSubtitles(srt_path)
    log("UPLOAD OK")


# ---------------------------
# Main
# ---------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseurl", default="http://127.0.0.1:32400")
    ap.add_argument("--token", required=True)
    ap.add_argument("--section", type=int, required=True)
    ap.add_argument("--path", required=True, help="Dossier OU fichier vidéo. Scan récursif; prend la plus grosse vidéo.")
    ap.add_argument("--lang", default="fr")
    ap.add_argument("--outdir", default=r"C:\PlexAutomation\PlexSubtitles")
    ap.add_argument("--timeout", type=int, default=240)

    # IMPORTANT: dest=... pour éviter tout doute
    ap.add_argument("--ost-agent", dest="ost_agent", default="PlexSubAuto/1.0")
    ap.add_argument("--ost-release-contains", dest="ost_release_contains", default=None)
    ap.add_argument("--ost-key", dest="ost_key", default=os.getenv("OST_API_KEY"))
    ap.add_argument("--ost-user", dest="ost_user", default=os.getenv("OST_USER"))
    ap.add_argument("--ost-pass", dest="ost_pass", default=os.getenv("OST_PASS"))

    ap.add_argument("--max-sub-tries", type=int, default=8, help="Nombre max de sous-titres OpenSubtitles testés.")

    args = ap.parse_args()

    log("START")

    target_video = find_target_video(args.path)
    target_folder = ensure_trailing_backslash(str(target_video.parent))
    target_video_str = normalize_win_path(str(target_video))

    log(f"Args: baseurl={args.baseurl} section={args.section} path='{args.path}'")
    log(f"Target: folder='{target_folder}' file='{target_video_str}' outdir='{args.outdir}'")

    if not args.ost_user or not args.ost_pass or not args.ost_key:
        raise SystemExit("Missing OpenSubtitles creds: set OST_API_KEY / OST_USER / OST_PASS (env)")

    os.makedirs(args.outdir, exist_ok=True)

    plex_refresh_section_path(args.baseurl, args.token, args.section, target_folder)

    rating_key, vtype, title = wait_find_rating_key_by_file_scan_all(
        args.baseurl, args.token, args.section, target_video_str, timeout_s=args.timeout
    )
    log(f"Plex item: type={vtype} ratingKey={rating_key} title='{title}'")

    # OpenSubtitles init (ICI était ton crash)
    ost = OpenSubtitles(args.ost_agent, args.ost_key)

    # login (avec backoff 429)
    for i in range(1, 11):
        try:
            log(f"OST login try {i}/10 …")
            ost.login(args.ost_user, args.ost_pass)
            log("OST login OK")
            break
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or "rate limit" in msg:
                time.sleep(1.2)
                continue
            raise

    # Requête propre basée sur le titre Plex
    cleaned = re.sub(r"[\[\]\(\)\._\-]+", " ", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    log(f"OST search movie: query='{cleaned}' lang={args.lang}")

    resp = ost.search(query=cleaned, languages=args.lang)
    if not getattr(resp, "data", None):
        raise SystemExit("OpenSubtitles search: 0 résultats")

    chosen_srt_text = None
    chosen_idx = 0

    for idx, (sub_obj, sub_dict) in enumerate(
        iter_best_subtitles(resp, prefer_release_contains=args.ost_release_contains), start=1
    ):
        if idx > args.max_sub_tries:
            break

        release = extract_release_text(sub_dict)
        log(f"OST candidate #{idx}: release='{release}' ai_flag={is_ai_or_machine_translated(sub_dict)}")
        try:
            srt_text = download_srt_text_from_opensubtitles(ost, sub_obj)
        except Exception as e:
            log(f"OST candidate #{idx}: download FAILED -> {e}")
            continue

        if not srt_text or len(srt_text.strip()) < 200:
            log(f"OST candidate #{idx}: rejected (too short)")
            continue

        if not looks_like_valid_srt(srt_text):
            log(f"OST candidate #{idx}: rejected (not valid SRT format)")
            continue

        if is_bad_ai_srt(srt_text):
            log(f"OST candidate #{idx}: rejected (AI/GT marker detected)")
            continue

        chosen_srt_text = srt_text
        chosen_idx = idx
        log(f"OST candidate #{idx}: accepted")
        break

    if not chosen_srt_text:
        raise SystemExit(f"OpenSubtitles: aucun SRT acceptable trouvé sur {args.max_sub_tries} essais")

    out_path = os.path.join(args.outdir, f"plex_{rating_key}.{args.lang}.srt")
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(chosen_srt_text)

    log(f"WROTE -> {out_path} (from candidate #{chosen_idx})")

    plex_upload_subtitle(args.baseurl, args.token, rating_key, out_path)

    log("END -> OK")


if __name__ == "__main__":
    main()
