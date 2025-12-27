from base import *
from ui.ui_print import ui_print, ui_settings, config_dir
import releases

_STATE = None

_TIMER_WINDOW_SECONDS = 2 * 24 * 60 * 60
_OLD_MEDIA_DAYS = 365
_UPGRADE_MAX_AGE_DAYS = 2 * 365
_UPGRADE_CHECK_INTERVAL_SECONDS = 7 * 24 * 60 * 60


def _state_path():
    return os.path.join(config_dir, "release_policy.json")


def _load_state():
    global _STATE
    if _STATE is not None:
        return _STATE
    state = {}
    path = _state_path()
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            with open(path, "r") as f:
                state = json.load(f)
        except Exception:
            state = {}
    if "timers" not in state:
        state["timers"] = {}
    if "upgrade_queue" not in state:
        state["upgrade_queue"] = {}
    _STATE = state
    return _STATE


def _save_state():
    state = _load_state()
    path = _state_path()
    try:
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        ui_print(f"[release_policy] error: couldnt write {path}: {e}", ui_settings.debug)


def _now():
    return int(time.time())


def _normalize_id(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        try:
            return ",".join(sorted(str(v) for v in value))
        except Exception:
            return ",".join(str(v) for v in value)
    return str(value)


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def media_key(media):
    media_type = getattr(media, "type", "unknown")
    if media_type == "movie":
        if hasattr(media, "EID") and media.EID:
            base = _normalize_id(media.EID)
        elif hasattr(media, "guid"):
            base = _normalize_id(media.guid)
        elif hasattr(media, "ratingKey"):
            base = "plex:" + _normalize_id(media.ratingKey)
        else:
            base = f"title:{getattr(media, 'title', '')}:{getattr(media, 'year', '')}"
        return "movie|" + base
    if media_type == "season":
        if hasattr(media, "parentEID") and media.parentEID:
            base = _normalize_id(media.parentEID)
        elif hasattr(media, "parentGuid"):
            base = _normalize_id(media.parentGuid)
        else:
            base = f"title:{getattr(media, 'parentTitle', '')}:{getattr(media, 'parentYear', '')}"
        return "season|" + base + f"|S{_safe_int(getattr(media, 'index', 0)):02d}"
    if media_type == "episode":
        if hasattr(media, "grandparentEID") and media.grandparentEID:
            base = _normalize_id(media.grandparentEID)
        elif hasattr(media, "grandparentGuid"):
            base = _normalize_id(media.grandparentGuid)
        else:
            base = f"title:{getattr(media, 'grandparentTitle', '')}:{getattr(media, 'grandparentYear', '')}"
        return (
            "episode|"
            + base
            + f"|S{_safe_int(getattr(media, 'parentIndex', 0)):02d}E{_safe_int(getattr(media, 'index', 0)):02d}"
        )
    return media_type + "|" + _normalize_id(
        getattr(media, "guid", getattr(media, "ratingKey", getattr(media, "title", "")))
    )


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return None


def media_age_days(media):
    date_str = getattr(media, "originallyAvailableAt", None)
    parsed = _parse_date(date_str)
    if not parsed:
        return None
    return (datetime.datetime.utcnow() - parsed).days


def _resolution_from_release(release):
    res = getattr(release, "resolution", None)
    try:
        res_int = int(res)
        if res_int > 0:
            return res_int
    except Exception:
        pass
    title = str(getattr(release, "title", ""))
    match = regex.search(r"(?<![0-9])(2160|1080|720|480)(?=p)", title, regex.I)
    if match:
        try:
            return int(match.group(1))
        except Exception:
            return 0
    return 0


def _is_4k_release(release):
    res = _resolution_from_release(release)
    if res >= 2160:
        return True
    title = str(getattr(release, "title", ""))
    return bool(regex.search(r"\b(4k|uhd)\b", title, regex.I))


def _is_1080_release(release):
    res = _resolution_from_release(release)
    if res == 1080:
        return True
    title = str(getattr(release, "title", ""))
    return bool(regex.search(r"\b1080p\b", title, regex.I))


def _has_1080_plus(releases):
    for release in releases:
        res = _resolution_from_release(release)
        if res >= 1080:
            return True
        title = str(getattr(release, "title", ""))
        if regex.search(r"\b(1080p|2160p|4k|uhd)\b", title, regex.I):
            return True
    return False


def _version_applies_to_media(version_config, media_type):
    triggers = version_config[1]
    for trigger in triggers:
        if trigger[0] != "media type":
            continue
        operator = trigger[1]
        if operator == "all":
            return True
        if operator == "movies":
            return media_type == "movie"
        if operator == "shows":
            return media_type in ["show", "season", "episode"]
    return True


def _version_is_1080(version_config):
    rules = version_config[3]
    for rule in rules:
        if (
            rule[0] == "resolution"
            and rule[1] == "requirement"
            and rule[2] == "<="
            and str(rule[3]) == "1080"
        ):
            return True
    return False


def required_retries_for_1080(media):
    max_required = 0
    media_type = getattr(media, "type", "unknown")
    for version in releases.sort.versions:
        if "\u0336" in version[0]:
            continue
        if not _version_applies_to_media(version, media_type):
            continue
        if not _version_is_1080(version):
            continue
        for trigger in version[1]:
            if trigger[0] == "retries" and trigger[1] == ">=":
                try:
                    max_required = max(max_required, int(float(trigger[2])))
                except Exception:
                    continue
    return max_required


def apply_release_policy(media, releases):
    media_type = getattr(media, "type", "")
    if media_type not in ["movie", "season", "episode"]:
        media._force_4k_only = False
        media._skip_watch = False
        media.force_retries = None
        return releases, {"force_4k_only": False, "timer_active": False}

    releases = releases or []
    age_days = media_age_days(media)
    old_media = age_days is None or age_days > _OLD_MEDIA_DAYS
    key = media_key(media)
    state = _load_state()
    dirty = False

    if not old_media and releases and _has_1080_plus(releases):
        if key not in state["timers"]:
            state["timers"][key] = _now()
            dirty = True
            ui_print(
                f"[4K TIMER] start for '{getattr(media, 'title', media_type)}' key={key}",
                ui_settings.debug,
            )

    timer_start = state["timers"].get(key)
    timer_active = False
    if timer_start and not old_media:
        timer_active = (_now() - int(timer_start)) < _TIMER_WINDOW_SECONDS

    force_4k_only = timer_active and not old_media
    filtered = releases
    if force_4k_only:
        before = len(filtered)
        filtered = [r for r in releases if _is_4k_release(r)]
        if before != len(filtered):
            ui_print(
                f"[4K TIMER] filtering to 4K-only ({before}->{len(filtered)})",
                ui_settings.debug,
            )

    if force_4k_only:
        media.force_retries = 0
    else:
        media.force_retries = required_retries_for_1080(media)
    media._force_4k_only = force_4k_only
    media._skip_watch = len(filtered) == 0

    if dirty:
        _save_state()
    return filtered, {
        "force_4k_only": force_4k_only,
        "timer_active": timer_active,
        "age_days": age_days,
        "skip_watch": media._skip_watch,
    }


def filter_forced_4k(media, releases):
    if getattr(media, "_force_4k_only", False):
        return [r for r in (releases or []) if _is_4k_release(r)]
    return releases or []


def _entry_from_media(media):
    entry = {
        "type": getattr(media, "type", ""),
        "title": getattr(media, "title", ""),
        "year": getattr(media, "year", None),
        "originallyAvailableAt": getattr(media, "originallyAvailableAt", None),
        "parentTitle": getattr(media, "parentTitle", None),
        "parentYear": getattr(media, "parentYear", None),
        "parentIndex": getattr(media, "parentIndex", None),
        "grandparentTitle": getattr(media, "grandparentTitle", None),
        "grandparentYear": getattr(media, "grandparentYear", None),
        "index": getattr(media, "index", None),
    }
    try:
        if hasattr(media, "isanime") and media.isanime():
            entry["query"] = media.anime_query()
        else:
            entry["query"] = media.query()
    except Exception:
        entry["query"] = ""
    try:
        entry["altquery"] = media.deviation()
    except Exception:
        entry["altquery"] = "(.*)"
    return entry


def maybe_queue_upgrade(media, release):
    if getattr(media, "type", "") not in ["movie", "season", "episode"]:
        return
    age_days = media_age_days(media)
    if age_days is None or age_days > _UPGRADE_MAX_AGE_DAYS:
        return
    if _is_4k_release(release):
        clear_upgrade(media)
        return
    if not _is_1080_release(release):
        return
    state = _load_state()
    key = media_key(media)
    entry = _entry_from_media(media)
    now = _now()
    entry["added"] = now
    entry["last_checked"] = now
    state["upgrade_queue"][key] = entry
    _save_state()
    ui_print(
        f"[UPGRADE QUEUE] queued 4K check for '{entry.get('title', '')}'",
        ui_settings.debug,
    )


def clear_upgrade(media):
    state = _load_state()
    key = media_key(media)
    if key in state["upgrade_queue"]:
        del state["upgrade_queue"][key]
        _save_state()


def _build_media_from_entry(entry):
    from content import classes

    data = {
        "type": entry.get("type", ""),
        "title": entry.get("title", ""),
        "year": entry.get("year", None),
        "originallyAvailableAt": entry.get("originallyAvailableAt", None),
        "parentTitle": entry.get("parentTitle", None),
        "parentYear": entry.get("parentYear", None),
        "parentIndex": entry.get("parentIndex", None),
        "grandparentTitle": entry.get("grandparentTitle", None),
        "grandparentYear": entry.get("grandparentYear", None),
        "index": entry.get("index", None),
    }
    media_obj = classes.media(SimpleNamespace(**data))
    if data.get("type") == "season":
        media_obj.Episodes = []
    return media_obj


def run_upgrade_checks():
    state = _load_state()
    now = _now()
    if not state["upgrade_queue"]:
        return
    changed = False
    for key, entry in list(state["upgrade_queue"].items()):
        last_checked = entry.get("last_checked", 0)
        if now - int(last_checked) < _UPGRADE_CHECK_INTERVAL_SECONDS:
            continue
        date_str = entry.get("originallyAvailableAt")
        if date_str:
            try:
                age_days = (datetime.datetime.utcnow() - _parse_date(date_str)).days
            except Exception:
                age_days = None
            if age_days is None or age_days > _UPGRADE_MAX_AGE_DAYS:
                del state["upgrade_queue"][key]
                changed = True
                continue
        query = entry.get("query", "")
        altquery = entry.get("altquery", "(.*)")
        if not query:
            entry["last_checked"] = now
            state["upgrade_queue"][key] = entry
            changed = True
            continue
        try:
            ui_print(
                f"[UPGRADE QUEUE] checking 4K for '{entry.get('title', '')}'",
                ui_settings.debug,
            )
            import scraper

            releases_list = scraper.scrape(query, altquery)
        except Exception as e:
            ui_print(f"[UPGRADE QUEUE] scrape error: {e}", ui_settings.debug)
            entry["last_checked"] = now
            state["upgrade_queue"][key] = entry
            changed = True
            continue
        releases_list = [r for r in releases_list if _is_4k_release(r)]
        entry["last_checked"] = now
        if not releases_list:
            state["upgrade_queue"][key] = entry
            changed = True
            continue
        try:
            media_obj = _build_media_from_entry(entry)
            media_obj.Releases = releases_list
            media_obj.existing_releases = []
            media_obj.downloaded_releases = []
            media_obj.force_retries = 0
            downloaded, _retry = media_obj.debrid_download(force=False)
            if downloaded:
                del state["upgrade_queue"][key]
            else:
                state["upgrade_queue"][key] = entry
            changed = True
        except Exception as e:
            ui_print(f"[UPGRADE QUEUE] download error: {e}", ui_settings.debug)
            state["upgrade_queue"][key] = entry
            changed = True
    if changed:
        _save_state()
