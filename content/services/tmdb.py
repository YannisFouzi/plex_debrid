from base import requests, json, time, regex, os
import ui.ui_print as ui_print_module
from ui.ui_print import ui_print, ui_settings

name = "TMDb"
api_key = ""

_BASE_URL = "https://api.themoviedb.org/3"
_SESSION = requests.Session()

_CACHE = {}
_CACHE_LOADED = False
_CACHE_FILE = "tmdb_status_cache.json"
_TTL_ENDED = 30 * 24 * 3600
_TTL_ONGOING = 24 * 3600


def _cache_path():
    return os.path.join(ui_print_module.config_dir, _CACHE_FILE)


def _load_cache():
    global _CACHE, _CACHE_LOADED
    if _CACHE_LOADED:
        return
    _CACHE_LOADED = True
    path = _cache_path()
    if not os.path.exists(path):
        _CACHE = {}
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _CACHE = data
        else:
            _CACHE = {}
    except Exception as e:
        _CACHE = {}
        ui_print(f"[tmdb] cache load failed: {e}", ui_settings.debug)


def _save_cache():
    path = _cache_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_CACHE, f, indent=2)
    except Exception as e:
        ui_print(f"[tmdb] cache save failed: {e}", ui_settings.debug)


def _cache_get(key):
    _load_cache()
    if not key or key not in _CACHE:
        return None
    entry = _CACHE.get(key, {})
    if "expected_episodes" not in entry:
        return None
    try:
        checked_at = float(entry.get("checked_at", 0))
    except Exception:
        checked_at = 0
    ended = bool(entry.get("ended", False))
    ttl = _TTL_ENDED if ended else _TTL_ONGOING
    if time.time() - checked_at <= ttl:
        cached = dict(entry)
        cached["source"] = "cache"
        return cached
    return None


def _cache_put(key, entry):
    if not key:
        return
    _load_cache()
    _CACHE[key] = entry
    _save_cache()


def _extract_ids(eids):
    ids = {"tmdb": None, "tvdb": None, "imdb": None}
    if not eids:
        return ids
    for eid in eids:
        value = str(eid)
        lower = value.lower()
        m = regex.search(r"(?:tmdb|themoviedb)://(\\d+)", lower)
        if m and not ids["tmdb"]:
            ids["tmdb"] = m.group(1)
        m = regex.search(r"(?:tvdb|thetvdb)://(\\d+)", lower)
        if m and not ids["tvdb"]:
            ids["tvdb"] = m.group(1)
        m = regex.search(r"imdb://(tt\\d+)", lower)
        if m and not ids["imdb"]:
            ids["imdb"] = m.group(1)
    return ids


def _tmdb_get(path, params=None, timeout=30):
    if not api_key:
        return None
    if params is None:
        params = {}
    params["api_key"] = api_key
    url = _BASE_URL + path
    response = _SESSION.get(url, params=params, timeout=timeout)
    if response.status_code != 200:
        raise Exception(f"tmdb http {response.status_code}")
    return response.json()


def _tmdb_find(external_id, source):
    path = f"/find/{external_id}"
    params = {"external_source": source}
    return _tmdb_get(path, params=params)


def _tmdb_search_show(title, year=None):
    params = {"query": title}
    if year:
        params["first_air_date_year"] = str(year)
    return _tmdb_get("/search/tv", params=params)


def _pick_tmdb_result(results, title_lower, year):
    best = None
    best_score = -1
    for result in results:
        name = str(result.get("name", "")).lower()
        orig = str(result.get("original_name", "")).lower()
        score = 0
        if name == title_lower or orig == title_lower:
            score += 3
        elif title_lower and (title_lower in name or title_lower in orig):
            score += 1
        if year:
            first_air = result.get("first_air_date") or ""
            if first_air.startswith(str(year)):
                score += 2
        if score > best_score:
            best_score = score
            best = result
    return best


def _status_is_ended(status):
    if not status:
        return None
    s = str(status).strip().lower()
    return s in ("ended", "canceled", "cancelled")


def _expected_episode_count(show):
    seasons = show.get("seasons")
    if not isinstance(seasons, list):
        return None, None
    total = 0
    found = False
    for season in seasons:
        try:
            season_number = int(season.get("season_number"))
        except Exception:
            season_number = None
        if season_number is None or season_number <= 0:
            continue
        try:
            episode_count = int(season.get("episode_count"))
        except Exception:
            episode_count = None
        if episode_count is None:
            continue
        total += episode_count
        found = True
    if found:
        return total, "seasons"
    return None, None


def get_original_title(media):
    """
    Récupère le titre original d'un média via TMDB.
    Utile pour les contenus non-anglais (ex: "Validé" au lieu de "All the Way Up")
    """
    if not api_key:
        return None
    
    eids = getattr(media, "EID", [])
    ids = _extract_ids(eids)
    title = getattr(media, "title", "")
    year = getattr(media, "year", None)
    media_type = getattr(media, "type", "show")
    
    tmdb_id = ids.get("tmdb")
    
    try:
        # Si pas d'ID TMDB direct, essayer de le trouver via IMDB ou TVDB
        if not tmdb_id and ids.get("imdb"):
            find = _tmdb_find(ids["imdb"], "imdb_id")
            results_key = "tv_results" if media_type in ["show", "season", "episode"] else "movie_results"
            results = find.get(results_key, [])
            if results:
                tmdb_id = str(results[0].get("id"))
        
        if not tmdb_id and ids.get("tvdb"):
            find = _tmdb_find(ids["tvdb"], "tvdb_id")
            tv_results = find.get("tv_results", [])
            if tv_results:
                tmdb_id = str(tv_results[0].get("id"))
        
        # Fallback: recherche par titre
        if not tmdb_id and title:
            if media_type in ["show", "season", "episode"]:
                search = _tmdb_search_show(title, year)
                result = _pick_tmdb_result(search.get("results", []), str(title).lower(), year)
            else:
                # Pour les films
                params = {"query": title}
                if year:
                    params["year"] = str(year)
                search = _tmdb_get("/search/movie", params=params)
                results = search.get("results", []) if search else []
                result = results[0] if results else None
            
            if result:
                tmdb_id = str(result.get("id"))
        
        if not tmdb_id:
            return None
        
        # Récupérer les détails pour avoir le titre original
        if media_type in ["show", "season", "episode"]:
            details = _tmdb_get(f"/tv/{tmdb_id}")
            original_title = details.get("original_name") if details else None
            current_title = details.get("name") if details else None
        else:
            details = _tmdb_get(f"/movie/{tmdb_id}")
            original_title = details.get("original_title") if details else None
            current_title = details.get("title") if details else None
        
        # Ne retourner que si le titre original est différent du titre actuel
        if original_title and current_title and original_title.lower() != current_title.lower():
            ui_print(f"[tmdb] original title found: '{original_title}' (current: '{current_title}')", ui_settings.debug)
            return original_title
        
        return None
        
    except Exception as e:
        ui_print(f"[tmdb] get_original_title failed for '{title}': {e}", ui_settings.debug)
        return None


def get_show_status(media, allow_fallback_search=True):
    if not api_key:
        return None
    eids = getattr(media, "EID", [])
    ids = _extract_ids(eids)
    title = getattr(media, "title", "")
    year = getattr(media, "year", None)

    cache_key = None
    if ids["tmdb"]:
        cache_key = f"tmdb:{ids['tmdb']}"
    elif ids["imdb"]:
        cache_key = f"imdb:{ids['imdb']}"
    elif ids["tvdb"]:
        cache_key = f"tvdb:{ids['tvdb']}"
    elif title:
        cache_key = f"title:{str(title).lower()}|{year or ''}"

    cached = _cache_get(cache_key)
    if cached:
        if title:
            ui_print(
                f"[tmdb] cache: {title} ended={cached.get('ended')} status={cached.get('status')}",
                ui_settings.debug,
            )
        return cached

    tmdb_id = ids["tmdb"]
    source = "guid"
    try:
        if not tmdb_id and ids["imdb"]:
            find = _tmdb_find(ids["imdb"], "imdb_id")
            tv_results = find.get("tv_results", [])
            if tv_results:
                tmdb_id = str(tv_results[0].get("id"))
                source = "find_imdb"
        if not tmdb_id and ids["tvdb"]:
            find = _tmdb_find(ids["tvdb"], "tvdb_id")
            tv_results = find.get("tv_results", [])
            if tv_results:
                tmdb_id = str(tv_results[0].get("id"))
                source = "find_tvdb"
        if not tmdb_id and allow_fallback_search and title:
            search = _tmdb_search_show(title, year)
            result = _pick_tmdb_result(search.get("results", []), str(title).lower(), year)
            if result:
                tmdb_id = str(result.get("id"))
                source = "search"
    except Exception as e:
        ui_print(f"[tmdb] lookup failed for '{title}': {e}", ui_settings.debug)
        return None

    if not tmdb_id:
        return None

    try:
        show = _tmdb_get(f"/tv/{tmdb_id}")
    except Exception as e:
        ui_print(f"[tmdb] fetch failed for '{title}': {e}", ui_settings.debug)
        return None

    status = show.get("status")
    in_production = show.get("in_production")
    ended = _status_is_ended(status)
    if ended is None:
        ended = False
    expected_episodes, expected_source = _expected_episode_count(show)

    entry = {
        "tmdb_id": tmdb_id,
        "status": status,
        "in_production": in_production,
        "ended": ended,
        "expected_episodes": expected_episodes,
        "expected_source": expected_source,
        "source": source,
        "checked_at": time.time(),
    }

    if title:
        ui_print(
            f"[tmdb] fetched: {title} ended={ended} status={status} expected={expected_episodes} source={source}",
            ui_settings.debug,
        )

    _cache_put(cache_key, entry)
    if tmdb_id and cache_key != f"tmdb:{tmdb_id}":
        _cache_put(f"tmdb:{tmdb_id}", entry)

    return entry
