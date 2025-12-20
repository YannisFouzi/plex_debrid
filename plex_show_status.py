import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def load_settings(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def pick_token(settings):
    users = settings.get("Plex users") or []
    if users and isinstance(users, list):
        first = users[0]
        if isinstance(first, list) and len(first) > 1 and first[1]:
            return first[1]
    token = settings.get("Subs Plex token")
    return token if token else None


def fetch_xml(url, timeout=20):
    req = urllib.request.Request(url, headers={"Accept": "application/xml"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return ET.fromstring(data)


def fetch_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def iter_items(root):
    for elem in root.iter():
        if elem.tag in ("Metadata", "Directory", "Video"):
            yield elem


def match_score(item, title_lower):
    t = (item.attrib.get("title") or "").lower()
    score = 0
    if t == title_lower:
        score += 3
    elif title_lower and title_lower in t:
        score += 1
    if item.attrib.get("type") in ("show", "series"):
        score += 2
    return score


def parse_bool(value):
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    return None


def extract_external_ids(meta_root, attrs):
    ids = {"tmdb": None, "tvdb": None, "imdb": None}

    def parse_guid(value):
        if not value:
            return
        lower = value.lower()
        m = re.search(r"(?:tmdb|themoviedb)://(\\d+)", lower)
        if m and not ids["tmdb"]:
            ids["tmdb"] = m.group(1)
        m = re.search(r"(?:tvdb|thetvdb)://(\\d+)", lower)
        if m and not ids["tvdb"]:
            ids["tvdb"] = m.group(1)
        m = re.search(r"imdb://(tt\\d+)", lower)
        if m and not ids["imdb"]:
            ids["imdb"] = m.group(1)

    parse_guid(attrs.get("guid"))
    for guid_elem in meta_root.iter("Guid"):
        parse_guid(guid_elem.attrib.get("id"))

    return ids


def tmdb_search_show(api_key, title, year):
    q = urllib.parse.quote(title)
    url = f"https://api.themoviedb.org/3/search/tv?api_key={api_key}&query={q}"
    if year:
        url += f"&first_air_date_year={year}"
    return fetch_json(url)


def tmdb_get_show(api_key, tmdb_id):
    url = f"https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={api_key}"
    return fetch_json(url)


def pick_tmdb_result(results, title_lower, year):
    best = None
    best_score = -1
    for r in results:
        name = (r.get("name") or "").lower()
        orig = (r.get("original_name") or "").lower()
        score = 0
        if name == title_lower or orig == title_lower:
            score += 3
        elif title_lower and (title_lower in name or title_lower in orig):
            score += 1
        if year:
            first_air = r.get("first_air_date") or ""
            if first_air.startswith(str(year)):
                score += 2
        if score > best_score:
            best_score = score
            best = r
    return best


def tmdb_status_is_ended(status):
    if not status:
        return None
    s = str(status).strip().lower()
    return s in ("ended", "canceled", "cancelled")


def search_discover(base, token, title, title_lower):
    q = urllib.parse.quote(title)
    search_url = (
        f"{base}/library/search?query={q}&limit=20&searchTypes=movies%2Ctv"
        f"&includeMetadata=1&X-Plex-Token={token}"
    )
    root = fetch_xml(search_url)
    return [i for i in iter_items(root) if match_score(i, title_lower) > 0]


def search_local(base, token, title, title_lower):
    q = urllib.parse.quote(title)
    base = base.rstrip("/")
    search_url = f"{base}/search?query={q}&X-Plex-Token={token}"
    root = fetch_xml(search_url)
    return [i for i in iter_items(root) if match_score(i, title_lower) > 0]


def main():
    parser = argparse.ArgumentParser(
        description="Diagnostic Plex status for a show via discover.provider.plex.tv"
    )
    parser.add_argument("title", nargs="?", default="Chernobyl")
    parser.add_argument("--settings", default="settings.json")
    parser.add_argument("--token", default="")
    parser.add_argument("--base-url", default="https://discover.provider.plex.tv")
    parser.add_argument("--tmdb-key", default="")
    parser.add_argument(
        "--tmdb-fallback",
        default="true",
        help="Use TMDb search when no tmdb:// guid (true/false)",
    )
    args = parser.parse_args()

    try:
        settings = load_settings(args.settings)
    except Exception as e:
        print(f"ERROR: failed to read settings: {e}")
        return 1

    token = args.token or pick_token(settings)
    if not token:
        print("ERROR: no Plex token found (Plex users or Subs Plex token).")
        return 1

    title = args.title
    title_lower = title.lower()
    base = args.base_url.rstrip("/")

    watchlist_url = (
        f"{base}/library/sections/watchlist/all?"
        f"X-Plex-Container-Size=200&X-Plex-Container-Start=0&X-Plex-Token={token}"
    )
    items = []
    meta_base = base
    try:
        root = fetch_xml(watchlist_url)
        items = [i for i in iter_items(root) if match_score(i, title_lower) > 0]
        meta_base = base
    except Exception as e:
        print(f"WARNING: watchlist fetch failed: {e} (falling back to search)")

    if not items:
        try:
            items = search_discover(base, token, title, title_lower)
            meta_base = base
        except Exception as e:
            print(f"WARNING: search fetch failed: {e} (falling back to local server)")

    if not items:
        local_base = settings.get("Plex server address") or "http://127.0.0.1:32400"
        try:
            items = search_local(local_base, token, title, title_lower)
            meta_base = local_base
        except Exception as e:
            print(f"ERROR: local search fetch failed: {e}")
            return 1

    if not items:
        print(f"NO MATCH: '{title}' not found in watchlist or search.")
        return 2

    items.sort(key=lambda x: match_score(x, title_lower), reverse=True)
    print("CANDIDATES:")
    for i in items[:10]:
        print(
            f"- title='{i.attrib.get('title','')}' type={i.attrib.get('type','')}"
            f" year={i.attrib.get('year','')}"
            f" ratingKey={i.attrib.get('ratingKey','')}"
        )

    chosen = None
    for i in items:
        if i.attrib.get("type") in ("show", "series"):
            chosen = i
            break
    if chosen is None:
        chosen = items[0]

    rating_key = chosen.attrib.get("ratingKey")
    if not rating_key:
        print("ERROR: chosen item has no ratingKey.")
        return 1

    meta_url = (
        f"{meta_base}/library/metadata/{rating_key}?includeUserState=1&X-Plex-Token={token}"
    )
    try:
        meta_root = fetch_xml(meta_url)
    except Exception as e:
        print(f"ERROR: metadata fetch failed: {e}")
        return 1

    meta_items = [i for i in iter_items(meta_root)]
    if not meta_items:
        print("ERROR: no metadata returned.")
        return 1

    meta = meta_items[0]
    attrs = meta.attrib

    status = attrs.get("status")
    is_cont_raw = attrs.get("isContinuingSeries")
    is_cont = parse_bool(is_cont_raw)

    ended_by_status = status == "ended"
    ended_by_is_cont = is_cont is False

    print("\nSTATUS FIELDS:")
    print(f"title: {attrs.get('title','')}")
    print(f"type: {attrs.get('type','')}")
    print(f"year: {attrs.get('year','')}")
    print(f"ratingKey: {attrs.get('ratingKey','')}")
    print(f"status: {status if status is not None else '<missing>'}")
    print(
        "isContinuingSeries: "
        + (str(is_cont_raw) if is_cont_raw is not None else "<missing>")
    )
    print(f"ended_by_status: {ended_by_status}")
    print(f"ended_by_isContinuingSeries: {ended_by_is_cont}")
    print(f"leafCount: {attrs.get('leafCount','')}")
    print(f"viewedLeafCount: {attrs.get('viewedLeafCount','')}")
    print(f"originallyAvailableAt: {attrs.get('originallyAvailableAt','')}")
    print(f"addedAt: {attrs.get('addedAt','')}")
    print(f"updatedAt: {attrs.get('updatedAt','')}")
    print(f"guid: {attrs.get('guid','')}")

    ids = extract_external_ids(meta_root, attrs)
    print("\nEXTERNAL IDS:")
    print(f"tmdb_id: {ids['tmdb'] if ids['tmdb'] else '<missing>'}")
    print(f"tvdb_id: {ids['tvdb'] if ids['tvdb'] else '<missing>'}")
    print(f"imdb_id: {ids['imdb'] if ids['imdb'] else '<missing>'}")

    tmdb_key = args.tmdb_key or os.getenv("TMDB_API_KEY")
    tmdb_fallback = parse_bool(args.tmdb_fallback)
    if tmdb_fallback is None:
        tmdb_fallback = True

    if tmdb_key:
        tmdb_id = ids["tmdb"]
        tmdb_source = "guid"
        if not tmdb_id and tmdb_fallback:
            try:
                year = attrs.get("year")
                search = tmdb_search_show(tmdb_key, title, year)
                result = pick_tmdb_result(search.get("results", []), title_lower, year)
                if result:
                    tmdb_id = str(result.get("id"))
                    tmdb_source = "search"
            except Exception as e:
                print(f"WARNING: TMDb search failed: {e}")

        if tmdb_id:
            try:
                tmdb_show = tmdb_get_show(tmdb_key, tmdb_id)
                tmdb_status = tmdb_show.get("status")
                tmdb_in_prod = tmdb_show.get("in_production")
                tmdb_ended = tmdb_status_is_ended(tmdb_status)
                print("\nTMDB STATUS:")
                print(f"tmdb_id: {tmdb_id}")
                print(f"tmdb_source: {tmdb_source}")
                print(f"status: {tmdb_status}")
                print(f"in_production: {tmdb_in_prod}")
                print(f"ended_by_tmdb: {tmdb_ended}")
            except Exception as e:
                print(f"WARNING: TMDb fetch failed: {e}")
        else:
            print("\nTMDB STATUS:")
            print("tmdb_id: <missing>")
            print("status: <unknown>")
    else:
        print("\nTMDB STATUS:")
        print("tmdb_key: <missing>")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
