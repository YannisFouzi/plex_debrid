#import modules
from base import *
from threading import Lock
from ui.ui_print import *
import releases

base_url = "http://127.0.0.1:9696"
api_key = ""
name = "prowlarr"
session = requests.Session()
max_results = 250
category_filter_ids = [2000, 5000]
resolver_timeout = 30
max_resolve = 50
resolver_concurrency = 10
resolver_retries = 1
resolver_retry_delay = 1

# Optimization settings
filter_low_quality = True  # Filter out 720p and below before resolving

# Global rate limiter: prevent API bursts that trigger 429 on indexers like C411
_RATE_LIMIT_DELAY = 5  # seconds between consecutive Prowlarr API requests
_last_request_time = 0
_rate_limit_lock = Lock()

def _rate_limited_get(url, headers, params, timeout):
    """Wrapper around session.get that enforces a minimum delay between API calls."""
    global _last_request_time
    with _rate_limit_lock:
        now = time.time()
        elapsed = now - _last_request_time
        if elapsed < _RATE_LIMIT_DELAY:
            wait = _RATE_LIMIT_DELAY - elapsed
            _debug(f'[prowlarr][rate-limit] waiting {wait:.1f}s before next API call')
            time.sleep(wait)
        _last_request_time = time.time()
        return session.get(url, headers=headers, params=params, timeout=timeout)

# Fallback negative cache: avoid spamming indexers when episode isn't available yet
# Key: base_title (e.g. "pitt"), Value: {"ts": timestamp, "fails": consecutive_fail_count}
_fallback_cache = {}
_FALLBACK_BASE_DELAY = 60       # 1 minute initial cooldown
_FALLBACK_MAX_DELAY = 600       # 10 minutes max cooldown

def _fallback_should_skip(cache_key):
    """Check if we should skip fallback for this query (cooldown not expired)."""
    if cache_key not in _fallback_cache:
        return False
    entry = _fallback_cache[cache_key]
    delay = min(_FALLBACK_BASE_DELAY * (2 ** (entry["fails"] - 1)), _FALLBACK_MAX_DELAY)
    elapsed = time.time() - entry["ts"]
    if elapsed < delay:
        _debug(f'[prowlarr][fallback] skipping "{cache_key}" (cooldown {int(delay - elapsed)}s remaining, fails={entry["fails"]})')
        return True
    return False

def _fallback_record_fail(cache_key):
    """Record a failed fallback attempt (all queries returned 0 for this episode)."""
    if cache_key in _fallback_cache:
        _fallback_cache[cache_key]["fails"] += 1
        _fallback_cache[cache_key]["ts"] = time.time()
    else:
        _fallback_cache[cache_key] = {"ts": time.time(), "fails": 1}
    entry = _fallback_cache[cache_key]
    delay = min(_FALLBACK_BASE_DELAY * (2 ** (entry["fails"] - 1)), _FALLBACK_MAX_DELAY)
    _debug(f'[prowlarr][fallback] recorded fail for "{cache_key}" (fails={entry["fails"]}, next retry in {int(delay)}s)')

def _fallback_record_success(cache_key):
    """Clear cooldown on success."""
    if cache_key in _fallback_cache:
        del _fallback_cache[cache_key]

_LEADING_ARTICLES = {"the", "a", "an", "le", "la", "les", "un", "une"}
_STOPWORDS = {
    "of", "the", "and", "or", "a", "an",
    "le", "la", "les", "de", "des", "du", "d",
    "un", "une", "et", "en",
}
_ALLOWED_EXTRAS = {
    "4k", "2160", "2160p", "1080", "1080p", "720", "720p", "480", "480p",
    "uhd", "hdr", "hdr10", "hdr10plus", "dv", "dovi", "dolby", "vision",
    "web", "webrip", "webdl", "web-dl", "bluray", "brrip", "bdrip", "remux",
    "dvdrip", "hdtv", "hdrip", "x264", "x265", "h264", "h265", "hevc", "av1",
    "xvid", "10bit", "8bit", "12bit", "ddp", "dd", "dts", "truehd", "atmos",
    "aac", "ac3", "eac3", "flac", "opus", "mp3", "multi", "vff", "vf", "vfi",
    "vo", "vostfr", "truefrench", "french", "fr", "german", "de", "english",
    "eng", "ita", "italian", "spa", "spanish", "es", "jpn", "japanese",
    "rus", "russian", "dual", "dub", "dubbed", "extended", "director",
    "directors", "cut", "uncut", "unrated", "remastered", "remaster",
    "edition", "special", "collector", "limited", "ultimate", "final", "noir",
    "imax", "redux", "theatrical", "proper", "repack", "complete",
    "integrale", "integral", "anniversary", "version", "nf", "amzn", "dsnp",
    "atvp", "hmax", "hulu", "itunes",
}

def _debug(msg):
    ui_print(msg, ui_settings.debug)

def _id_to_int(value):
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    try:
        text = str(value).lower()
    except Exception:
        return None
    if text.startswith("tt"):
        text = text[2:]
    match = regex.search(r"(\d+)", text)
    if not match:
        return None
    try:
        parsed = int(match.group(1))
    except Exception:
        return None
    if parsed <= 0:
        return None
    return parsed

def _normalize_ids(ids):
    if not ids:
        return {"imdb": None, "tmdb": None, "tvdb": None}
    imdb = tmdb = tvdb = None
    if isinstance(ids, dict):
        imdb = _id_to_int(ids.get("imdb"))
        tmdb = _id_to_int(ids.get("tmdb"))
        tvdb = _id_to_int(ids.get("tvdb"))
    else:
        for item in ids:
            text = str(item).lower()
            if imdb is None:
                match = regex.search(r"(?:imdb)://(tt\d+)", text)
                if match:
                    imdb = _id_to_int(match.group(1))
            if tmdb is None:
                match = regex.search(r"(?:tmdb|themoviedb)://(\d+)", text)
                if match:
                    tmdb = _id_to_int(match.group(1))
            if tvdb is None:
                match = regex.search(r"(?:tvdb|thetvdb)://(\d+)", text)
                if match:
                    tvdb = _id_to_int(match.group(1))
    return {"imdb": imdb, "tmdb": tmdb, "tvdb": tvdb}

def _result_id(result, attr):
    try:
        return _id_to_int(getattr(result, attr, None))
    except Exception:
        return None

def _result_has_ids(result):
    return (
        _result_id(result, "imdbId") is not None
        or _result_id(result, "tmdbId") is not None
        or _result_id(result, "tvdbId") is not None
    )

def _normalize_tokens(text):
    if text is None:
        return []
    import unicodedata

    # Fold accents (Château -> Chateau) so matching works on id-less VF titles
    folded = unicodedata.normalize("NFKD", str(text))
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    normalized = regex.sub(r"[^A-Za-z0-9]+", ".", folded.lower())
    normalized = regex.sub(r"\.+", ".", normalized).strip(".")
    return normalized.split(".") if normalized else []

def _extract_query_tokens(query):
    tokens = _normalize_tokens(query)
    year = None
    if tokens and regex.match(r"^(19|20)\d{2}$", tokens[-1]):
        year = tokens[-1]
        tokens = tokens[:-1]
    return tokens, year

def _match_prefix_length(result_tokens, query_tokens):
    if len(result_tokens) >= len(query_tokens) and result_tokens[:len(query_tokens)] == query_tokens:
        return len(query_tokens)
    if query_tokens and query_tokens[0] in _LEADING_ARTICLES:
        trimmed = query_tokens[1:]
        if trimmed and len(result_tokens) >= len(trimmed) and result_tokens[:len(trimmed)] == trimmed:
            return len(trimmed)
    return 0

def _is_show_like_altquery(altquery):
    if not altquery:
        return False
    hay = str(altquery).lower()
    return ("s[0-9]" in hay) or ("season" in hay) or ("series" in hay) or ("e[0-9]" in hay)

def _is_show_marker(token):
    if not token:
        return False
    if regex.match(r"^s\d{1,2}(e\d{1,2})?$", token):
        return True
    return token in {"season", "seasons", "complete", "integrale", "integral", "series", "pack", "collection"}

def _is_year_token(token):
    return bool(token and regex.match(r"^(19|20)\d{2}$", token))

def _passes_title_guard(query, altquery, title):
    if not query or altquery == "(.*)":
        return True
    query_tokens, query_year = _extract_query_tokens(query)
    if not query_tokens:
        return True
    result_tokens = _normalize_tokens(title)
    prefix_len = _match_prefix_length(result_tokens, query_tokens)
    if prefix_len == 0:
        return False
    next_token = result_tokens[prefix_len] if len(result_tokens) > prefix_len else None
    if next_token is None:
        return True
    show_like = _is_show_like_altquery(altquery)
    if show_like:
        return _is_show_marker(next_token) or _is_year_token(next_token) or next_token in _ALLOWED_EXTRAS
    if query_year and next_token == query_year:
        return True
    return _is_year_token(next_token) or next_token in _ALLOWED_EXTRAS

def _passes_loose_guard(query, altquery, title):
    """
    Stricter check for id-less releases:
    - require the release title to contain the query year (if present)
    - AND contain either:
      * a full alias substring (query/altquery normalized), or
      * at least one "strong" token (len>=4, not a stopword) from the alias list
    """
    title_tokens = _normalize_tokens(title)
    query_tokens, query_year = _extract_query_tokens(query)

    # Extract simple tokens from altquery (strip regex noise)
    alt_tokens = []
    alt_aliases = []
    if altquery and altquery != "(.*)":
        try:
            cleaned = regex.sub(r'[^A-Za-z0-9|]+', '.', altquery)
            alt_tokens = _normalize_tokens(cleaned)
            alt_aliases = []
            for raw in regex.sub(r'\.+', '.', cleaned).split('|'):
                trimmed = raw.strip('.')
                if trimmed and regex.search(r'[a-z]', trimmed, regex.I):
                    alt_aliases.append(trimmed)
        except Exception:
            alt_tokens = []
            alt_aliases = []

    year_ok = bool(query_year and query_year in title_tokens)
    if not year_ok:
        return False

    # Build alias strings to test substring match
    alias_strings = []
    if query_tokens:
        alias_strings.append(".".join(query_tokens))
    alias_strings.extend(alt_aliases)
    norm_title_str = ".".join(title_tokens)
    full_alias_match = any(alias and alias in norm_title_str for alias in alias_strings)

    # Build strong tokens (length >=4, not a stopword)
    all_tokens = set(query_tokens + alt_tokens)
    strong_tokens = [
        tok for tok in all_tokens
        if len(tok) >= 4 and tok not in _STOPWORDS and regex.search(r'[a-z]', tok, regex.I)
    ]
    strong_token_match = any(tok in title_tokens for tok in strong_tokens)

    return full_alias_match or strong_token_match

def _matches_target_ids(result, target_ids):
    imdb_id = target_ids.get("imdb")
    tmdb_id = target_ids.get("tmdb")
    tvdb_id = target_ids.get("tvdb")
    if imdb_id is not None and _result_id(result, "imdbId") == imdb_id:
        return True
    if tmdb_id is not None and _result_id(result, "tmdbId") == tmdb_id:
        return True
    if tvdb_id is not None and _result_id(result, "tvdbId") == tvdb_id:
        return True
    return False

def _is_low_quality(title):
    """Check if release is 720p or lower quality (to filter out before resolving)."""
    # Match 720p, 480p, 360p, etc. but NOT 1080p, 2160p, 4K
    if regex.search(r'(?<![0-9])720p', title, regex.I):
        return True
    if regex.search(r'(?<![0-9])(480|360|240)p', title, regex.I):
        return True
    if regex.search(r'(?i)\b(DVDRip|DVDScr|HDTV|PDTV|TVRip|CAM|TS|TC|R5)\b', title) and not regex.search(r'(?i)(1080|2160|4K)', title):
        return True
    return False

def _is_season_pack(title):
    """Check if release is a season pack (S01, S02) vs individual episode (S01E01)."""
    # Season pack: has S01, S02, etc. but NOT S01E01, S02E03, etc.
    if regex.search(r'\b(complete|integrale)\b', title, regex.I):
        return True
    if regex.search(r'\bS\d{1,2}\W*S?\d{1,2}\b', title, regex.I):
        return True
    has_season = regex.search(r'\.S\d{1,2}\.', title, regex.I) or regex.search(r'\.S\d{1,2}$', title, regex.I)
    has_episode = regex.search(r'\.S\d{1,2}E\d{1,2}', title, regex.I)
    return has_season and not has_episode

def _sort_packs_first(results):
    """Sort results to put season packs first, individual episodes last."""
    # Priority: 0 = season pack, 1 = episode
    return sorted(results, key=lambda r: (0 if _is_season_pack(getattr(r, 'title', '')) else 1))

def _extract_season_numbers(title):
    """Extract season number(s) from a release title. Returns a set of integers."""
    seasons = set()
    # Match S01, S02, etc. (single season packs)
    single_match = regex.search(r'\.S(\d{1,2})\.', title, regex.I)
    if single_match:
        seasons.add(int(single_match.group(1)))
    # Match S01-S04, S01.S02.S03, etc. (multi-season packs)
    multi_match = regex.findall(r'S(\d{1,2})', title, regex.I)
    for m in multi_match:
        seasons.add(int(m))
    return seasons

def _get_with_retry(url, allow_redirects, timeout):
    for attempt in range(resolver_retries + 1):
        try:
            return session.get(url, allow_redirects=allow_redirects, timeout=timeout)
        except requests.exceptions.Timeout:
            if attempt >= resolver_retries:
                raise
            _debug('[prowlarr][resolver] timeout, retrying ' + str(attempt + 1) + '/' + str(resolver_retries))
            time.sleep(resolver_retry_delay)

def _redact_url(url):
    try:
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
        parts = urlsplit(url)
        if not parts.query:
            return url
        redacted = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if key.lower() in ('apikey', 'passkey', 'link'):
                redacted.append((key, '***'))
            else:
                redacted.append((key, value))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(redacted), parts.fragment))
    except Exception:
        return url

def _add_release(scraped_releases, result, magnet, torrent_bytes=None):
    if not magnet:
        _debug('[prowlarr][resolver] no magnet to add for: ' + getattr(result, 'title', '<unknown>'))
        return
    if result.indexer is not None and result.size is not None:
        r = releases.release('[prowlarr: ' + str(result.indexer) + ']', 'torrent', result.title, [],
                             float(result.size) / 1000000000, [magnet], seeders=result.seeders)
    elif result.indexer is not None:
        r = releases.release('[prowlarr: ' + str(result.indexer) + ']', 'torrent', result.title, [], 1,
                             [magnet], seeders=result.seeders)
    elif result.size is not None:
        r = releases.release('[prowlarr: unnamed]', 'torrent', result.title, [],
                             float(result.size) / 1000000000, [magnet], seeders=result.seeders)
    else:
        return
    if torrent_bytes:
        r.torrent_bytes = torrent_bytes
    scraped_releases += [r]

def _safe_torrent_to_magnet(torrent_bytes):
    try:
        return releases.torrent2magnet(torrent_bytes)
    except Exception:
        try:
            metadata = releases.torrent2magnet.bdecode(torrent_bytes)
            info = metadata.get(b'info', None)
            if not info:
                return None
            try:
                digest = hashlib.sha1(releases.torrent2magnet.bencode(info)).hexdigest()
            except Exception:
                return None
            dn = ""
            try:
                name = info.get(b'name', b'')
                if isinstance(name, bytes):
                    dn = name.decode('utf-8', 'ignore')
                elif isinstance(name, str):
                    dn = name
            except Exception:
                dn = ""
            tr = ""
            try:
                announce = metadata.get(b'announce', b'')
                if isinstance(announce, bytes):
                    tr = announce.decode('utf-8', 'ignore')
                elif isinstance(announce, str):
                    tr = announce
            except Exception:
                tr = ""
            magnet = 'magnet:?xt=urn:btih:' + digest
            if dn:
                magnet += '&dn=' + dn
            if tr:
                magnet += '&tr=' + tr
            return magnet
        except Exception:
            return None

def is_movies_or_tv(result):
    categories = getattr(result, 'categories', None)
    if not categories:
        return False
    for cat in categories:
        try:
            cat_id = int(getattr(cat, 'id', -1))
        except (TypeError, ValueError):
            continue
        if 2000 <= cat_id < 3000 or 5000 <= cat_id < 6000:
            return True
    return False

def setup(cls, new=False):
    from scraper.services import setup
    setup(cls,new)

def scrape(query, altquery, required_seasons=None, ids=None):
    """
    Scrape for releases.
    
    Args:
        query: Search query
        altquery: Alternative query pattern for filtering
        required_seasons: Optional list of season numbers (currently unused, kept for compatibility)
        ids: Optional dict of ids (imdb/tmdb/tvdb) for exact match filtering
    """
    from scraper.services import active
    scraped_releases = []
    if 'prowlarr' in active:
        url = base_url + '/api/v1/search'
        params = [
            ('query', query),
            ('type', 'search'),
            ('limit', max_results),
            ('offset', 0),
        ] + [('categories', cat_id) for cat_id in category_filter_ids]
        headers = {'X-Api-Key': api_key}
        _debug(f'[prowlarr][api] requesting url={base_url}/api/v1/search query="{query}" categories={category_filter_ids}')
        try:
            response = _rate_limited_get(url, headers, params, timeout=60)
        except requests.exceptions.Timeout:
            ui_print('[prowlarr] error: prowlarr request timed out. Reduce the number of prowlarr indexers or make sure they are healthy.')
            return []
        except :
            ui_print('[prowlarr] error: prowlarr couldnt be reached. Make sure your prowlarr base url is correctly formatted (default: http://prowlarr:9696).')
            return []
        _debug(f'[prowlarr][api] response status={response.status_code} content_length={len(response.content)}')
        if response.status_code == 200:
            try:
                response = json.loads(response.content, object_hook=lambda d: SimpleNamespace(**d))
            except:
                ui_print('[prowlarr] error: prowlarr didnt return any data.')
                return []
            _debug(f'[prowlarr][api] raw JSON returned {len(response)} results')
            if len(response) > 0:
                for i, r in enumerate(response[:5]):
                    title = getattr(r, 'title', '<no title>')
                    protocol = getattr(r, 'protocol', '<no protocol>')
                    cats = getattr(r, 'categories', [])
                    cat_ids = []
                    for c in (cats or []):
                        cat_id = getattr(c, 'id', None)
                        if cat_id is not None:
                            cat_ids.append(str(cat_id))
                    has_magnet = hasattr(r, 'magnetUrl') and r.magnetUrl is not None
                    has_download = hasattr(r, 'downloadUrl') and r.downloadUrl is not None
                    indexer = getattr(r, 'indexer', '<unknown>')
                    _debug(f'[prowlarr][api] result[{i}] title="{title}" protocol={protocol} cats=[{",".join(cat_ids)}] indexer={indexer} hasMagnet={has_magnet} hasDownload={has_download}')
            # Filter by category
            before_cat_filter = len(response)
            response = [result for result in response if is_movies_or_tv(result)]
            after_cat_filter = len(response)
            _debug(f'[prowlarr][cat-filter] {before_cat_filter} -> {after_cat_filter} after is_movies_or_tv() (filtered {before_cat_filter - after_cat_filter})')
            if before_cat_filter > 0 and after_cat_filter == 0:
                _debug('[prowlarr][cat-filter] ALL results filtered! (no re-fetch to avoid wasting API calls)')
            target_ids = _normalize_ids(ids)
            if any(target_ids.values()):
                has_any_id = any(_result_has_ids(r) for r in response)
                if has_any_id:
                    filtered = [r for r in response if _matches_target_ids(r, target_ids)]
                    if filtered:
                        response = filtered
                        _debug(f"[prowlarr][id-filter] kept {len(response)} releases after id match")
                    else:
                        idless = [r for r in response if not _result_has_ids(r)]
                        if idless:
                            response = idless
                            _debug(f"[prowlarr][id-filter] no id match; kept {len(response)} id-less releases")
                        else:
                            _debug("[prowlarr][id-filter] no id match; returning 0 releases")
                            return []
                else:
                    _debug("[prowlarr][id-filter] no ids on results; skipping id filter")
            _debug(f'[prowlarr][filter-loop] starting filter loop with {len(response)} results, altquery="{altquery[:120]}"')
            guard_filtered = 0
            alt_matched = 0
            alt_not_matched = 0
            magnet_added = 0
            no_magnet = 0
            dropped_no_alt = 0
            kept_for_resolver = 0
            for result in response[:]:
                result.title = result.title.replace(' ', '.')
                result.title = result.title.replace(':', '').replace("'", '')
                result.title = regex.sub(r'\.+', ".", result.title)
                has_ids = _result_has_ids(result)
                if not has_ids:
                    # Id-less: require strict guard OR (year+token) loose guard; allow VF token present even si romaji en tête
                    norm_title_str = ".".join(_normalize_tokens(result.title))
                    has_fr_alias = ("chateau" in norm_title_str and "araignee" in norm_title_str)
                    title_guard_ok = _passes_title_guard(query, altquery, result.title)
                    loose_guard_ok = _passes_loose_guard(query, altquery, result.title)
                    if not has_fr_alias and not title_guard_ok and not loose_guard_ok:
                        _debug(f'[prowlarr][guard-reject] title="{result.title}" title_guard={title_guard_ok} loose_guard={loose_guard_ok}')
                        response.remove(result)
                        guard_filtered += 1
                        continue
                    else:
                        _debug(f'[prowlarr][guard-pass] title="{result.title}" title_guard={title_guard_ok} loose_guard={loose_guard_ok} fr_alias={has_fr_alias}')
                else:
                    _debug(f'[prowlarr][guard-skip] title="{result.title}" has_ids=True')
                try:
                    alt_regex_str = r'(' + altquery.replace('.', r'\.').replace(r"\.*", ".*") + ')'
                    alt_match = regex.match(alt_regex_str, result.title, regex.I)
                except Exception as e:
                    _debug(f'[prowlarr][alt-regex-error] regex failed: {e} pattern="{alt_regex_str[:200]}"')
                    alt_match = None
                protocol = getattr(result, 'protocol', '<none>')
                _debug(f'[prowlarr][alt-match] title="{result.title}" alt_match={bool(alt_match)} protocol={protocol}')
                if alt_match and protocol == 'torrent':
                    alt_matched += 1
                    has_magnet_url = hasattr(result, 'magnetUrl') and result.magnetUrl is not None
                    has_indexer = result.indexer is not None
                    has_size = result.size is not None
                    _debug(f'[prowlarr][alt-match-detail] hasMagnetUrl={has_magnet_url} hasIndexer={has_indexer} hasSize={has_size} magnetUrl={str(getattr(result, "magnetUrl", None))[:80]}')
                    if has_magnet_url:
                        if has_indexer and has_size:
                            scraped_releases += [
                                releases.release('[prowlarr: ' + str(result.indexer) + ']', 'torrent', result.title,[], float(result.size) / 1000000000, [result.magnetUrl],seeders=result.seeders)]
                            magnet_added += 1
                        elif has_indexer:
                            scraped_releases += [
                                releases.release('[prowlarr: ' + str(result.indexer) + ']', 'torrent', result.title,[], 1, [result.magnetUrl], seeders=result.seeders)]
                            magnet_added += 1
                        elif has_size:
                            scraped_releases += [
                                releases.release('[prowlarr: unnamed]', 'torrent', result.title, [],float(result.size) / 1000000000, [result.magnetUrl],seeders=result.seeders)]
                            magnet_added += 1
                        response.remove(result)
                    else:
                        no_magnet += 1
                        _debug(f'[prowlarr][no-magnet] title="{result.title}" -> kept in response for resolver')
                else:
                    alt_not_matched += 1
                    # If id-less and passed loose guard, keep for resolver; otherwise drop
                    if has_ids or not _passes_loose_guard(query, altquery, result.title):
                        _debug(f'[prowlarr][drop-no-alt] title="{result.title}" has_ids={has_ids} loose_guard={_passes_loose_guard(query, altquery, result.title)}')
                        response.remove(result)
                        dropped_no_alt += 1
                    else:
                        kept_for_resolver += 1
                        _debug(f'[prowlarr][keep-loose] title="{result.title}" kept for resolver (loose guard passed)')
            _debug(f'[prowlarr][filter-summary] guard_filtered={guard_filtered} alt_matched={alt_matched} alt_not_matched={alt_not_matched} magnet_added={magnet_added} no_magnet={no_magnet} dropped_no_alt={dropped_no_alt} kept_for_resolver={kept_for_resolver}')
            _debug(f'[prowlarr][filter-summary] scraped_releases so far={len(scraped_releases)} remaining in response={len(response)}')
            if guard_filtered:
                _debug(f"[prowlarr][title-guard] filtered {guard_filtered} id-less releases")
            if len(response) > max_results:
                response = response[:max_results]
                _debug(f"[prowlarr][limit] trimmed to {max_results} results after filtering")
            # OPTIMIZATION 1: Filter out low quality (720p and below) before resolving
            if filter_low_quality:
                before_filter = len(response)
                response = [r for r in response if not _is_low_quality(getattr(r, 'title', ''))]
                filtered_count = before_filter - len(response)
                if filtered_count > 0:
                    _debug(f'[prowlarr][optimizer] filtered out {filtered_count} low-quality releases (720p/480p)')
            
            # OPTIMIZATION 2: Sort to resolve season packs first, episodes last
            response = _sort_packs_first(response)
            packs_count = sum(1 for r in response if _is_season_pack(getattr(r, 'title', '')))
            episodes_count = len(response) - packs_count
            _debug(f'[prowlarr][optimizer] sorted {len(response)} releases: {packs_count} packs first, {episodes_count} episodes last')
            
            # OPTIMIZATION 3: Prioritize packs but keep some episodes for fallback
            # If there are packs, resolve all packs + a few episodes as fallback
            # This way if packs fail/are unavailable, we still have episodes to try
            if packs_count > 0:
                # Keep all packs + some episodes for fallback (max 5 episodes as backup)
                max_fallback_episodes = min(5, episodes_count)
                total_to_resolve = min(packs_count + max_fallback_episodes, max_resolve)
                response = response[:total_to_resolve]
                actual_episodes = total_to_resolve - packs_count
                _debug(f'[prowlarr][optimizer] PACKS + FALLBACK: resolving {packs_count} packs + {actual_episodes} episodes for fallback')
            else:
                # No packs found, resolve episodes (limited by max_resolve)
                if len(response) > max_resolve:
                    response = response[:max_resolve]
                _debug(f'[prowlarr][optimizer] NO PACKS: resolving up to {len(response)} episodes')
            
            # Multiprocess resolving of result.Link for remaining releases
            results = [None] * len(response)
            threads = []
            
            # start thread for each remaining release in batches
            for index, result in enumerate(response):
                t = Thread(target=multi_init, args=(resolve, result, results, index))
                threads.append(t)
                t.start()
                
                if len(threads) >= resolver_concurrency:
                    for t in threads:
                        t.join()
                    threads = []
            
            # wait for any remaining threads to complete
            for t in threads:
                t.join()
            
            for result in results:
                if not result == [] and not result == None:
                    scraped_releases += result
        # FALLBACK: if no results and query contains an episode pattern (S##E##),
        # retry with broader queries since some indexers don't support episode-specific
        # text search. Queries use spaces (like the Prowlarr UI) instead of dots.
        # A strict episode regex filters results to only keep the correct episode.
        if len(scraped_releases) == 0:
            ep_match = regex.search(r'(\.S(\d{2}))E(\d{2})\.$', query, regex.I)
            if ep_match:
                season_num = ep_match.group(2)
                episode_num = ep_match.group(3)
                base_title = query[:ep_match.start()].replace('.', ' ').strip()
                season_tag = 'S' + season_num
                cache_key = base_title.lower() + ' S' + season_num + 'E' + episode_num
                if _fallback_should_skip(cache_key):
                    return scraped_releases
                # Strict regex: only accept titles containing the exact S##E## pattern
                strict_ep_regex = regex.compile(
                    r'S0*' + str(int(season_num)) + r'E0*' + str(int(episode_num)) + r'(?:\.|$)',
                    regex.I
                )
                # Strip leading article if present (e.g. "the pitt" -> "pitt")
                # Some indexers (e.g. C411) don't handle articles in API search
                base_words = base_title.split()
                if base_words and base_words[0].lower() in _LEADING_ARTICLES and len(base_words) > 1:
                    no_article_title = ' '.join(base_words[1:])
                else:
                    no_article_title = None
                # Progressively broader queries:
                # 1) "The Pitt S02E09" — full title + episode
                # 2) "The Pitt S02"    — full title + season
                # 3) "The Pitt"        — full title only
                # 4) "Pitt S02"        — no article + season (if article was present)
                # 5) "Pitt"            — no article only (if article was present)
                fallback_queries = [
                    base_title + ' ' + season_tag + 'E' + episode_num,
                    base_title + ' ' + season_tag,
                    base_title,
                ]
                if no_article_title:
                    fallback_queries.append(no_article_title + ' ' + season_tag)
                    fallback_queries.append(no_article_title)
                for fb_idx, fallback_query in enumerate(fallback_queries):
                    if len(scraped_releases) > 0:
                        break
                    _debug(f'[prowlarr][fallback] attempt {fb_idx+1}: trying query "{fallback_query}"')
                    fallback_params = [
                        ('query', fallback_query),
                        ('type', 'search'),
                        ('limit', max_results),
                        ('offset', 0),
                    ] + [('categories', cat_id) for cat_id in category_filter_ids]
                    try:
                        fb_response = _rate_limited_get(url, headers, fallback_params, timeout=60)
                    except:
                        _debug('[prowlarr][fallback] request failed')
                        continue
                    _debug(f'[prowlarr][fallback] response status={fb_response.status_code} content_length={len(fb_response.content)}')
                    if fb_response.status_code != 200:
                        continue
                    try:
                        fb_results = json.loads(fb_response.content, object_hook=lambda d: SimpleNamespace(**d))
                    except:
                        _debug('[prowlarr][fallback] JSON parse failed')
                        continue
                    _debug(f'[prowlarr][fallback] raw JSON returned {len(fb_results)} results')
                    fb_results = [r for r in fb_results if is_movies_or_tv(r)]
                    _debug(f'[prowlarr][fallback] {len(fb_results)} after category filter')
                    # Filter: only keep results matching the exact episode
                    accepted = []
                    for result in fb_results:
                        result.title = result.title.replace(' ', '.')
                        result.title = result.title.replace(':', '').replace("'", '')
                        result.title = regex.sub(r'\.+', ".", result.title)
                        if not strict_ep_regex.search(result.title):
                            _debug(f'[prowlarr][fallback] rejected: "{result.title}" (need S{season_num}E{episode_num})')
                            continue
                        _debug(f'[prowlarr][fallback] accepted: "{result.title}"')
                        accepted.append(result)
                    fb_results = accepted
                    if not fb_results:
                        _debug(f'[prowlarr][fallback] no results matched S{season_num}E{episode_num}, trying next query')
                        continue
                    # Separate magnet vs needs-resolving
                    for result in fb_results[:]:
                        protocol = getattr(result, 'protocol', '<none>')
                        if protocol == 'torrent':
                            has_magnet_url = hasattr(result, 'magnetUrl') and result.magnetUrl is not None
                            if has_magnet_url:
                                _add_release(scraped_releases, result, result.magnetUrl)
                                fb_results.remove(result)
                    # Filter low quality
                    if filter_low_quality:
                        fb_results = [r for r in fb_results if not _is_low_quality(getattr(r, 'title', ''))]
                    # Resolve remaining (no magnet)
                    if len(fb_results) > max_resolve:
                        fb_results = fb_results[:max_resolve]
                    _debug(f'[prowlarr][fallback] resolving {len(fb_results)} releases')
                    fb_resolve_results = [None] * len(fb_results)
                    threads = []
                    for index, result in enumerate(fb_results):
                        t = Thread(target=multi_init, args=(resolve, result, fb_resolve_results, index))
                        threads.append(t)
                        t.start()
                        if len(threads) >= resolver_concurrency:
                            for t in threads:
                                t.join()
                            threads = []
                    for t in threads:
                        t.join()
                    for result in fb_resolve_results:
                        if not result == [] and not result == None:
                            scraped_releases += result
                    _debug(f'[prowlarr][fallback] total scraped after fallback: {len(scraped_releases)}')
                if len(scraped_releases) > 0:
                    _fallback_record_success(cache_key)
                else:
                    _fallback_record_fail(cache_key)
    return scraped_releases

def resolve(result):
    scraped_releases = []
    try:
        download_url = result.downloadUrl
        try:
            import html
            download_url = html.unescape(download_url)
        except Exception:
            download_url = result.downloadUrl
        _debug('[prowlarr][resolver] start title=' + getattr(result, 'title', '<unknown>') +
               ' indexer=' + str(getattr(result, 'indexer', '<unknown>')) +
               ' url=' + _redact_url(download_url))
        link = _get_with_retry(download_url, allow_redirects=False, timeout=resolver_timeout)
        if link is None:
            _debug('[prowlarr][resolver] empty response object')
            return scraped_releases
        _debug('[prowlarr][resolver] status=' + str(link.status_code) +
               ' content-type=' + str(link.headers.get('Content-Type', '')) +
               ' bytes=' + str(len(link.content)))
        if 'Location' in link.headers:
            location = link.headers['Location']
            try:
                import html
                location = html.unescape(location)
            except Exception:
                location = link.headers['Location']
            _debug('[prowlarr][resolver] redirect location=' + _redact_url(location))
            if regex.search(r'(?<=btih:).*?(?=&|$)', str(location), regex.I):
                _debug('[prowlarr][resolver] magnet found in redirect location')
                _add_release(scraped_releases, result, location)
                return scraped_releases
            try:
                from urllib.parse import urljoin
                location_url = urljoin(download_url, location)
                _debug('[prowlarr][resolver] fetching redirect target=' + _redact_url(location_url))
                redirected = _get_with_retry(location_url, allow_redirects=True, timeout=resolver_timeout)
                content_type = redirected.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
                is_torrent = content_type in ["application/x-bittorrent", "application/octet-stream"]
                if not is_torrent and redirected.content[:1] == b'd':
                    is_torrent = True
                _debug('[prowlarr][resolver] redirected status=' + str(redirected.status_code) +
                       ' content-type=' + str(redirected.headers.get('Content-Type', '')) +
                       ' bytes=' + str(len(redirected.content)) +
                       ' is_torrent=' + str(is_torrent))
                if is_torrent:
                    magnet = _safe_torrent_to_magnet(redirected.content)
                    if not magnet:
                        _debug('[prowlarr][resolver] torrent->magnet conversion failed')
                    _add_release(scraped_releases, result, magnet, torrent_bytes=redirected.content)
                else:
                    try:
                        import html
                        content = html.unescape(redirected.text)
                    except:
                        content = redirected.text
                    match = regex.search(r'(magnet:\?xt=urn:btih:[^\"\\s<]+)', content, regex.I)
                    magnet = match.group(1) if match else None
                    if magnet:
                        _debug('[prowlarr][resolver] magnet found in redirected content')
                    else:
                        _debug('[prowlarr][resolver] no magnet found in redirected content')
                    _add_release(scraped_releases, result, magnet)
            except:
                _debug('[prowlarr][resolver] redirect handling failed')
                pass
            return scraped_releases
        content_type = link.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
        is_torrent = content_type in ["application/x-bittorrent", "application/octet-stream"]
        if not is_torrent and link.content[:1] == b'd':
            is_torrent = True
        if is_torrent:
            magnet = _safe_torrent_to_magnet(link.content)
            if not magnet:
                _debug('[prowlarr][resolver] torrent->magnet conversion failed (direct)')
            _add_release(scraped_releases, result, magnet, torrent_bytes=link.content)
            return scraped_releases
        else:
            try:
                import html
                content = html.unescape(link.text)
            except:
                content = link.text
            match = regex.search(r'(magnet:\?xt=urn:btih:[^\"\\s<]+)', content, regex.I)
            if match:
                magnet = match.group(1)
                _debug('[prowlarr][resolver] magnet found in direct content')
                _add_release(scraped_releases, result, magnet)
                return scraped_releases
            _debug('[prowlarr][resolver] no magnet found in direct content')
    except Exception as e:
        ui_print("[prowlarr] error: resolver couldnt get magnet/torrent for release: " + result.title, ui_settings.debug)
        _debug('[prowlarr][resolver] exception=' + type(e).__name__ + ' msg=' + str(e))
        return scraped_releases
    
# Multiprocessing watchlist method
def multi_init(cls, obj, result, index):
    result[index] = cls(obj)
