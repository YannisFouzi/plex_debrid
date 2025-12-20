from base import *

import os
import re

import releases
# Subtitle trigger (optional)
try:
    import subtitle_runner
except Exception:
    subtitle_runner = None
import debrid
import scraper
from ui.ui_print import *

imdb_scraped = False


class watchlist(Sequence):
    def __init__(self, other):
        self.data = other

    def __getitem__(self, index):
        return self.data[index]

    def __len__(self):
        return len(self.data)

    def __eq__(self, other):
        return len(self) == len(other)

    def __add__(self, other):
        return watchlist(self.data + other.data)

    def remove(self, item):
        self.data.remove(item)

    def add(self, item, user):
        self.data.append(item)


class library:

    active = []

    def setup(cls, new=False):
        from settings import settings_list

        settings = []
        for category, allsettings in settings_list:
            for setting in allsettings:
                if setting.cls == cls or setting.name.startswith(cls.name):
                    settings += [setting]
        back = False
        if not new:
            while not back:
                print("0) Back")
                indices = []
                for index, setting in enumerate(settings):
                    print(str(index + 1) + ") " + setting.name)
                    indices += [str(index + 1)]
                print()
                choice = input("Choose an action: ")
                if choice in indices:
                    settings[int(choice) - 1].input()
                    if not cls.name in library.active:
                        library.active = [cls.name]
                    back = True
                elif choice == "0":
                    back = True
        else:
            print()
            indices = []
            for setting in settings:
                setting.setup()
                if not cls.name in library.active:
                    library.active = [cls.name]

    def __new__(cls):
        activeservices = []
        for servicename in library.active:
            for service in cls.__subclasses__():
                if service.name == servicename:
                    activeservices += [service]
        return activeservices


class refresh:

    active = []

    def setup(cls, new=False):
        from settings import settings_list

        settings = []
        for category, allsettings in settings_list:
            for setting in allsettings:
                if setting.cls == cls or setting.name.startswith(cls.name):
                    settings += [setting]
        back = False
        if not new:
            while not back:
                print("0) Back")
                indices = []
                for index, setting in enumerate(settings):
                    print(str(index + 1) + ") " + setting.name)
                    indices += [str(index + 1)]
                print()
                choice = input("Choose an action: ")
                if choice in indices:
                    settings[int(choice) - 1].input()
                    if not cls.name in refresh.active:
                        refresh.active = [cls.name]
                    back = True
                elif choice == "0":
                    back = True
        else:
            print()
            indices = []
            for setting in settings:
                setting.setup()
                if not cls.name in refresh.active:
                    refresh.active = [cls.name]

    def __new__(cls):
        activeservices = []
        for servicename in refresh.active:
            for service in cls.__subclasses__():
                if service.name == servicename:
                    activeservices += [service]
        return activeservices


class ignore:

    active = []
    ignored = []

    def setup(cls, new=False):
        from settings import settings_list

        settings = []
        for category, allsettings in settings_list:
            for setting in allsettings:
                if setting.cls == cls or setting.name.startswith(cls.name):
                    settings += [setting]
        back = False
        if not new:
            while not back:
                print("0) Back")
                indices = []
                for index, setting in enumerate(settings):
                    print(str(index + 1) + ") " + setting.name)
                    indices += [str(index + 1)]
                print()
                choice = input("Choose an action: ")
                if choice in indices:
                    settings[int(choice) - 1].input()
                    if not cls.name in ignore.active:
                        ignore.active += [cls.name]
                    back = True
                elif choice == "0":
                    back = True
        else:
            print()
            indices = []
            for setting in settings:
                setting.setup()
                if not cls.name in ignore.active:
                    ignore.active += [cls.name]

    def __new__(cls):
        activeservices = []
        for servicename in ignore.active:
            for service in cls.__subclasses__():
                if service.name == servicename:
                    activeservices += [service]
        return activeservices

    def add(self):
        for service in ignore():
            ui_print(
                "ignoring item of type '"
                + self.__module__
                + "' on service '"
                + service.__module__
                + "'",
                ui_settings.debug,
            )
            self.match(service.__module__)
            service.add(self)

    def remove(self):
        for service in ignore():
            ui_print(
                "un-ignoring item of type '"
                + self.__module__
                + "' on service '"
                + service.__module__
                + "'",
                ui_settings.debug,
            )
            self.match(service.__module__)
            service.remove(self)

    def check(self):
        check = False
        for service in ignore():
            self.match(service.__module__)
            if service.check(self):
                check = True
        return check


class map:

    import xml.etree.ElementTree as ET

    def element_to_dict(element):
        result = {}
        for key, value in element.items():
            result[key] = value

        if element.text and element.text.strip():
            result[element.tag] = element.text.strip()

        for child in element:
            child_dict = map.element_to_dict(child)
            if child.tag in result:
                if isinstance(result[child.tag], list):
                    result[child.tag].append(child_dict)
                else:
                    result[child.tag] = [result[child.tag], child_dict]
            else:
                result[child.tag] = child_dict

        return result

    def xml_to_dict(xml_string):
        root = map.ET.fromstring(xml_string)
        return {root.tag: map.element_to_dict(root)}

    class anidb:

        titles = {}
        last_update = 0

        def construct():
            try:
                response = requests.get(
                    "https://raw.githubusercontent.com/Anime-Lists/anime-lists/master/anime-list.xml",
                    timeout=60,
                )
                ids = map.xml_to_dict(response.content.decode("utf-8"))
                response = requests.get(
                    "https://raw.githubusercontent.com/Anime-Lists/anime-lists/master/animetitles.xml",
                    timeout=60,
                )
                titles = map.xml_to_dict(response.content.decode("utf-8"))
            except Exception as e:
                ui_print(
                    "Failed to get anime mapping lists: " + str(e), ui_settings.debug
                )
                return
            map.anidb.titles = {}
            temp = {}
            for match in titles["animetitles"]["anime"]:
                temp[match["aid"]] = match
            for element in ids["anime-list"]["anime"]:
                aliases = []
                match = temp[element["anidbid"]]
                if match == None:
                    continue
                if not isinstance(match["title"], list):
                    match["title"] = [match["title"]]
                for title in match["title"]:
                    if (
                        title["type"] in ["main", "official", "short"]
                        and not title["title"].split(":")[0] in aliases
                    ):
                        aliases += [title["title"].split(":")[0]]
                if "imdbid" in element:
                    map.anidb.titles["imdb://" + str(element["imdbid"])] = aliases
                if "tvdbid" in element and not element["tvdbid"] == "movie":
                    map.anidb.titles["tvdb://" + str(element["tvdbid"])] = aliases

        def __new__(cls, self) -> list:
            if time.time() - map.anidb.last_update > 3600:
                map.anidb.construct()
                map.anidb.last_update = time.time()
            for EID in self.EID:
                if EID in map.anidb.titles:
                    return map.anidb.titles[EID]


class media:

    ignore_queue = []
    downloaded_versions = []
    pack_in_progress = {}

    def __init__(self, other):
        self.__dict__.update(other.__dict__)

    def __eq__(self, other) -> bool:
        try:
            if type(other) == type(None):
                if type(self) == type(None):
                    return True
                return False
            if not self.type == other.type:
                return False
            if self.type == "movie" or self.type == "show":
                if hasattr(self, "EID") and hasattr(other, "EID"):
                    for EID in self.EID:
                        if EID in other.EID:
                            return True
                    return False
                return self.guid == other.guid
            elif self.type == "season":
                if hasattr(self, "parentEID") and hasattr(other, "parentEID"):
                    for EID in self.parentEID:
                        if EID in other.parentEID and self.index == other.index:
                            return True
                    return False
                return self.parentGuid == other.parentGuid and self.index == other.index
            elif self.type == "episode":
                if hasattr(self, "grandparentEID") and hasattr(other, "grandparentEID"):
                    for EID in self.grandparentEID:
                        if (
                            EID in other.grandparentEID
                            and self.parentIndex == other.parentIndex
                            and self.index == other.index
                        ):
                            return True
                    return False
                return (
                    self.grandparentGuid == other.grandparentGuid
                    and self.parentIndex == other.parentIndex
                    and self.index == other.index
                )
        except:
            return False

    def pack_key(self):
        if self.type != "season":
            return None
        if hasattr(self, "parentEID"):
            try:
                return ("season", tuple(sorted(self.parentEID)), self.index)
            except Exception:
                return ("season", tuple(self.parentEID), self.index)
        if hasattr(self, "parentGuid"):
            return ("season", self.parentGuid, self.index)
        return ("season", self.parentTitle, self.index)

    def match(self, service):
        if not hasattr(self, "services"):
            self.services = [self.__module__]
        if self.type == "show":
            for season in self.Seasons:
                if not hasattr(season, "services"):
                    season.services = [self.__module__]
                for episode in season.Episodes:
                    if not hasattr(episode, "services"):
                        episode.services = [self.__module__]
        if self.type == "season":
            for episode in self.Episodes:
                if not hasattr(episode, "services"):
                    episode.services = [self.__module__]
        if not service in self.services:
            query = "unknown"
            try:
                query = self.query()
            except:
                try:
                    query = self.EID[0]
                except:
                    query = "unknown"
            if not service == "content.services.textfile":
                ui_print(
                    "matching item: '"
                    + query
                    + "' of service '"
                    + self.__module__
                    + "' to service '"
                    + service
                    + "'",
                    ui_settings.debug,
                )
            match = sys.modules[service].match(self)
            if match == None:
                return False
            delattr(match, "watchlist")
            if self.type in ["movie", "episode"]:
                delattr(match, "guid")
                if hasattr(match, "year"):
                    if match.year == None:
                        delattr(match, "year")
                self.__dict__.update(match.__dict__)
                self.services += [service]
                return True
            elif self.type == "show":
                for season in match.Seasons[:]:
                    if not season in self.Seasons:
                        match.Seasons.remove(season)
                    elif self.services != ["content.services.overseerr"]:
                        matching_season = next(
                            (x for x in self.Seasons if x == season), None
                        )
                        for episode in season.Episodes:
                            if not episode in matching_season.Episodes:
                                season.Episodes.remove(episode)
                if self.services != ["content.services.overseerr"]:
                    for season in match.Seasons:
                        matching_season = next(
                            (x for x in self.Seasons if x == season), None
                        )
                        if not matching_season == None:
                            for episode in season.Episodes:
                                matching_episode = next(
                                    (
                                        x
                                        for x in matching_season.Episodes
                                        if x == episode
                                    ),
                                    None,
                                )
                                if not matching_episode == None:
                                    delattr(episode, "guid")
                                    matching_episode.__dict__.update(episode.__dict__)
                            season.__dict__.update(matching_season.__dict__)
                    delattr(match, "guid")
                else:
                    for season in match.Seasons:
                        if not hasattr(season, "services"):
                            season.services = [self.__module__]
                        if not hasattr(season, "requestedBy") and hasattr(
                            self, "requestedBy"
                        ):
                            season.requestedBy = self.requestedBy
                        for episode in season.Episodes:
                            if not hasattr(episode, "services"):
                                episode.services = [self.__module__]
                            if not hasattr(episode, "requestedBy") and hasattr(
                                self, "requestedBy"
                            ):
                                episode.requestedBy = self.requestedBy
                self.__dict__.update(match.__dict__)
                self.services += [service]
                for season in self.Seasons:
                    season.services += [service]
                    for episode in season.Episodes:
                        episode.services += [service]
                return True
            elif self.type == "season":
                for episode in match.Episodes[:]:
                    if not episode in self.Episodes:
                        match.Episodes.remove(episode)
                for episode in match.Episodes:
                    matching_episode = next(
                        (x for x in self.Episodes if x == episode), None
                    )
                    if not matching_episode == None:
                        episode.__dict__.update(matching_episode.__dict__)
                self.__dict__.update(match.__dict__)
                self.services += [service]
                for episode in self.Episodes:
                    episode.services += [service]
                return True

    def query(self, title=""):
        if title == "":
            if self.type == "movie":
                title = releases.rename(self.title)
            elif self.type == "show":
                title = releases.rename(self.title)
            elif self.type == "season":
                title = releases.rename(self.parentTitle)
            elif self.type == "episode":
                title = releases.rename(self.grandparentTitle)
        if self.type == "movie":
            if regex.search(
                str(self.year),
                releases.rename(
                    self.title.replace(str(self.year), "") + " " + str(self.year)
                ),
            ):
                title = title.replace("." + str(self.year), "")
                return title + "." + str(self.year)
            else:
                return title
        elif self.type == "show":
            title = title.replace("." + str(self.year), "")
            return title
        elif self.type == "season":
            title = title.replace("." + str(self.parentYear), "")
            return title + ".S" + str("{:02d}".format(self.index)) + "."
        elif self.type == "episode":
            title = title.replace("." + str(self.grandparentYear), "")
            if hasattr(self, "scraping_adjustment"):
                for operator, value in self.scraping_adjustment:
                    if operator == "scrape w/ airdate format":
                        try:
                            if regex.search(value, title, regex.I):
                                airdate = datetime.datetime.strptime(
                                    self.originallyAvailableAt, "%Y-%m-%d"
                                )
                                return title + "." + airdate.strftime("%Y.%m.%d")
                        except:
                            continue
            return (
                title
                + ".S"
                + str("{:02d}".format(self.parentIndex))
                + "E"
                + str("{:02d}".format(self.index))
                + "."
            )

    def anime_query(self, title=""):
        if title == "":
            if self.type == "movie":
                title = releases.rename(self.title)
            elif self.type == "show":
                title = releases.rename(self.title)
            elif self.type == "season":
                title = releases.rename(self.parentTitle)
            elif self.type == "episode":
                title = releases.rename(self.grandparentTitle)
        if self.type == "movie":
            title = title.replace("." + str(self.year), "")
            return title.replace(".", " ") + " " + str(self.year)
        elif self.type == "show":
            title = title.replace("." + str(self.year), "")
            return title.replace(".", " ")
        elif self.type == "season":
            title = title.replace("." + str(self.parentYear), "")
            return title.replace(".", " ") + " "
        elif self.type == "episode":
            title = title.replace("." + str(self.grandparentYear), "")
            return title.replace(".", " ") + " " + str(self.anime_count)

    def aliases(self, lan="en"):
        if len(sys.modules["content.services.trakt"].users) > 0:
            if not hasattr(self, "alternate_titles"):
                self.alternate_titles = []
            self.match("content.services.trakt")
            aliases = sys.modules["content.services.trakt"].aliases(self, lan)
            translations = sys.modules["content.services.trakt"].translations(self, lan)
            if not len(translations) == 0 and not len(aliases) == 0:
                aliases = translations + aliases
            elif not len(translations) == 0:
                aliases = translations
            if (lan == "en" or len(aliases) == 0) and not releases.rename(
                self.title
            ) in self.alternate_titles:
                aliases.insert(0, self.title)
            elif not releases.rename(self.title) in self.alternate_titles:
                aliases += [self.title]
            if self.isanime():
                anidbtitles = map.anidb(self)
                if not aliases == None and not anidbtitles == None:
                    aliases = anidbtitles + aliases
            aliases = list(dict.fromkeys(aliases))
            for title in aliases:
                special_char = False
                for i in title:
                    if ord(i) > 512:
                        special_char = True
                if special_char:
                    continue
                if title == None or title == []:
                    continue
                if "." in title:
                    titledot = releases.rename(title.replace(".", ""))
                    if hasattr(self, "scraping_adjustment"):
                        for operator, value in self.scraping_adjustment:
                            title_ = None
                            if operator == "add text before title":
                                title_ = value + titledot
                            elif operator == "add text after title":
                                title_ = titledot + value
                            if (
                                not title_ == None
                                and not title_ in self.alternate_titles
                            ):
                                self.alternate_titles += [title_]
                        if not titledot in self.alternate_titles:
                            self.alternate_titles += [titledot]
                    else:
                        if not titledot in self.alternate_titles:
                            self.alternate_titles += [titledot]
                title = releases.rename(title)
                if hasattr(self, "scraping_adjustment"):
                    for operator, value in self.scraping_adjustment:
                        title_ = None
                        if operator == "add text before title":
                            title_ = value + title
                        elif operator == "add text after title":
                            title_ = title + value
                        if not title_ == None and not title_ in self.alternate_titles:
                            self.alternate_titles += [title_]
                    if not title in self.alternate_titles:
                        self.alternate_titles += [title]
                else:
                    if not title in self.alternate_titles:
                        self.alternate_titles += [title]
            if self.type == "show":
                if hasattr(self, "Seasons"):
                    for season in self.Seasons:
                        season.alternate_titles = self.alternate_titles
                        if hasattr(season, "Episodes"):
                            for episode in season.Episodes:
                                episode.alternate_titles = self.alternate_titles
        else:
            title = releases.rename(self.title)
            if not hasattr(self, "alternate_titles"):
                self.alternate_titles = []

            # Generate variant without digits for titles like "PLUR1BUS" -> "pluribus"
            import re
            title_no_digits = re.sub(r'\d+', '', title)
            if title_no_digits != title and title_no_digits:
                if not title_no_digits in self.alternate_titles:
                    self.alternate_titles.append(title_no_digits)

            if hasattr(self, "scraping_adjustment"):
                for operator, value in self.scraping_adjustment:
                    title_ = None
                    if operator == "add text before title":
                        title_ = value + title
                    elif operator == "add text after title":
                        title_ = title + value
                    if not title_ == None and not title_ in self.alternate_titles:
                        self.alternate_titles += [title_]
                if not title in self.alternate_titles:
                    self.alternate_titles += [title]
            else:
                self.alternate_titles = [title]
            if self.type == "show":
                if hasattr(self, "Seasons"):
                    for season in self.Seasons:
                        season.alternate_titles = self.alternate_titles
                        if hasattr(season, "Episodes"):
                            for episode in season.Episodes:
                                episode.alternate_titles = self.alternate_titles

    def deviation(self, year=""):
        self.versions()
        if not self.isanime():
            if hasattr(self, "alternate_titles"):
                title = "(" + "|".join(self.alternate_titles) + ")"
            else:
                if self.type == "movie":
                    title = releases.rename(self.title)
                elif self.type == "show":
                    title = releases.rename(self.title)
                elif self.type == "season":
                    title = releases.rename(self.parentTitle)
                elif self.type == "episode":
                    title = releases.rename(self.grandparentTitle)
            title = title.replace("[", "\[").replace("]", "\]")
            if self.type == "movie":
                if regex.search(
                    str(self.year),
                    releases.rename(
                        self.title.replace(str(self.year), "") + " " + str(self.year)
                    ),
                ):
                    title = title.replace("." + str(self.year), "")
                    if year != "":
                        return "(.*?)(" + title + ":?.*)\(?\[?(" + str(year) + ")?"
                    return (
                        "(.*?)("
                        + title
                        + ":?.*)\(?\[?("
                        + str(self.year)
                        + "|"
                        + str(self.year - 1)
                        + "|"
                        + str(self.year + 1)
                        + ")?"
                    )
                else:
                    title = title.replace("." + str(self.year), "")
                    return "(.*?)(" + title + ")"
            elif self.type == "show":
                title = title.replace("." + str(self.year), "")
                return (
                    "(.*?)("
                    + title
                    + ":?.)(series.|[^A-Za-z0-9]+)?((\(?"
                    + str(self.year)
                    + "\)?.)|(complete.)|(seasons?.[0-9]+.[0-9]?[0-9]?.?)|(S[0-9]+.S?[0-9]?[0-9]?.?)|(S[0-9]+E[0-9]+))"
                )
            elif self.type == "season":
                title = title.replace("." + str(self.parentYear), "")
                season_num = str(self.index)
                season_02d = str("{:02d}".format(self.index))
                return (
                    "(.*?)("
                    + title
                    + ":?.)(series.|[^A-Za-z0-9]+)?(\(?"
                    + str(self.parentYear)
                    + "\)?.)?(season."
                    + season_num
                    + "[^0-9]|season."
                    + season_02d
                    + "[^0-9]|S"
                    + season_02d
                    + "[^0-9]|S"
                    + season_02d
                    + "E[0-9]+|"
                    + season_num
                    + "x[0-9]+)"
                )
            elif self.type == "episode":
                title = title.replace("." + str(self.grandparentYear), "")
                try:
                    airdate_formats = []
                    airdate = datetime.datetime.strptime(
                        self.originallyAvailableAt, "%Y-%m-%d"
                    )
                    airdate_formats += [
                        airdate.strftime("(%y|%Y).*(%m|%b).*%d").replace("0", "0?")
                    ]
                    airdate_formats += [
                        airdate.strftime("%d.*(%m|%b).*(%Y|%y)").replace("0", "0?")
                    ]
                    airdate_formats += [
                        airdate.strftime("(%m|%b).*%d.*(%Y|%y)").replace("0", "0?")
                    ]
                    airdate_formats = "(" + ")|(".join(airdate_formats) + ")"
                    return (
                        "(.*?)("
                        + title
                        + ":?.)(series.)?(\(?"
                        + str(self.grandparentYear)
                        + "\)?.)?(S"
                        + str("{:02d}".format(self.parentIndex))
                        + "E"
                        + str("{:02d}".format(self.index))
                        + ".|"
                        + airdate_formats
                        + ")"
                    )
                except:
                    return (
                        "(.*?)("
                        + title
                        + ":?.)(series.)?(\(?"
                        + str(self.grandparentYear)
                        + "\)?.)?(S"
                        + str("{:02d}".format(self.parentIndex))
                        + "E"
                        + str("{:02d}".format(self.index))
                        + ".)"
                    )
        else:
            if hasattr(self, "alternate_titles"):
                title = "(" + "|".join(self.alternate_titles) + ")"
            else:
                if self.type == "movie":
                    title = releases.rename(self.title)
                elif self.type == "show":
                    title = releases.rename(self.title)
                elif self.type == "season":
                    title = releases.rename(self.parentTitle)
                elif self.type == "episode":
                    title = releases.rename(self.grandparentTitle)
            title = title.replace("[", "\[").replace("]", "\]")
            if self.type == "movie":
                title = title.replace("." + str(self.year), "")
                return (
                    "(.*?)("
                    + title
                    + ")(.*?)("
                    + str(self.year)
                    + "|"
                    + str(self.year - 1)
                    + "|"
                    + str(self.year + 1)
                    + ")?"
                )
            elif self.type == "show":
                title = title.replace("." + str(self.year), "")
                return (
                    "(.*?)("
                    + title
                    + ")(.*?)("
                    + self.anime_count
                    + "|(complete)|(seasons?[^0-9]?[0-9]+[^A-Z0-9]+S?[0-9]+)|(S[0-9]+[^A-Z0-9]+S?[0-9]+))"
                )
            elif self.type == "season":
                n = self.index
                roman = (
                    "I"
                    if n == 1
                    else (
                        "II"
                        if n == 2
                        else (
                            "III"
                            if n == 3
                            else (
                                "IV"
                                if n == 4
                                else (
                                    "V"
                                    if n == 5
                                    else (
                                        "VI"
                                        if n == 6
                                        else (
                                            "VII"
                                            if n == 7
                                            else (
                                                "VIII"
                                                if n == 8
                                                else (
                                                    "IX"
                                                    if n == 9
                                                    else "X" if n == 10 else str(n)
                                                )
                                            )
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
                title = title.replace("." + str(self.parentYear), "")
                return (
                    "(.*?)("
                    + title
                    + ")(.*?)(season[^0-9]?0*"
                    + str(self.index)
                    + "|S0*"
                    + str(self.index)
                    + "(?!E?[0-9])|"
                    + self.anime_count
                    + "|[^A-Z0-9]"
                    + roman
                    + "[^A-Z0-9])"
                )
            elif self.type == "episode":
                n = self.parentIndex
                roman = (
                    "I"
                    if n == 1
                    else (
                        "II"
                        if n == 2
                        else (
                            "III"
                            if n == 3
                            else (
                                "IV"
                                if n == 4
                                else (
                                    "V"
                                    if n == 5
                                    else (
                                        "VI"
                                        if n == 6
                                        else (
                                            "VII"
                                            if n == 7
                                            else (
                                                "VIII"
                                                if n == 8
                                                else (
                                                    "IX"
                                                    if n == 9
                                                    else "X" if n == 10 else str(n)
                                                )
                                            )
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
                title = title.replace("." + str(self.grandparentYear), "")
                return (
                    "(.*?)("
                    + title
                    + ")(.*?)((?<!part)[^0-9A-RT-Z\[]0*("
                    + str(self.parentIndex)
                    + "|"
                    + roman
                    + ")[^0-9A-DF-Z\[]0*"
                    + str(self.index)
                    + "(?![A-Z0-9]|\])|(?<!part)[^0-9A-Z\[]0*"
                    + self.anime_count
                    + "(?![A-Z0-9]|\]))"
                )

    def isanime(self):
        if "anime" in self.genre():
            if self.type == "show":
                self.anime_count = 0
                if hasattr(self, "Seasons"):
                    for season in self.Seasons:
                        season.genres = ["anime"]
                        season.anime_season = (
                            str(self.anime_count + 1)
                            if self.anime_count == 0
                            else str(self.anime_count)
                        )
                        if hasattr(season, "Episodes"):
                            for episode in season.Episodes:
                                self.anime_count += 1
                                episode.genres = ["anime"]
                                episode.anime_count = str(self.anime_count)
                        season.anime_count = (
                            "[0-9][^0-9]?-[^0-9]?0*("
                            + str(self.anime_count)
                            + "|"
                            + str(self.anime_count + 1)
                            + ")"
                        )
                        season.anime_season = (
                            season.anime_season + "-" + str(self.anime_count)
                        )
                self.anime_count = (
                    "[0-9][^0-9]?-[^0-9]?0*("
                    + str(self.anime_count)
                    + "|"
                    + str(self.anime_count + 1)
                    + ")"
                )
            return True
        return False

    def genre(self):
        genres = []
        if hasattr(self, "parentGenre"):
            return self.parentGenre
        if hasattr(self, "grandparentGenre"):
            return self.grandparentGenre
        if hasattr(self, "genres"):
            if not self.genres == None:
                for gen in self.genres:
                    genres += [gen]
        if hasattr(self, "Genre"):
            if not self.Genre == None:
                for gen in self.Genre:
                    genres += [gen.slug]
        if self.type == "show":
            for season in self.Seasons:
                season.parentGenre = genres
                for episode in season.Episodes:
                    episode.grandparentGenre = genres
        if self.type == "season":
            for episode in self.Episodes:
                episode.grandparentGenre = genres
        return genres

    def versions(self, quick=False):
        # initialize downloaded and existing releases
        if not hasattr(self, "existing_releases"):
            self.existing_releases = []
        if not hasattr(self, "downloaded_releases"):
            self.downloaded_releases = []
        if self.type == "show":
            for season in self.Seasons:
                if not hasattr(season, "existing_releases"):
                    season.existing_releases = []
                if not hasattr(season, "downloaded_releases"):
                    season.downloaded_releases = []
                for episode in season.Episodes:
                    if not hasattr(episode, "existing_releases"):
                        episode.existing_releases = []
                    if not hasattr(episode, "downloaded_releases"):
                        episode.downloaded_releases = []
        if self.type == "season":
            for episode in self.Episodes:
                if not hasattr(episode, "existing_releases"):
                    episode.existing_releases = []
                if not hasattr(episode, "downloaded_releases"):
                    episode.downloaded_releases = []
        # get all versions
        versions = []
        for version in releases.sort.versions:
            if not "\u0336" in version[0]:
                versions += [
                    releases.sort.version(
                        version[0], version[1], version[2], version[3]
                    )
                ]
        # update media items ignore count
        if self in media.ignore_queue:
            match = next((x for x in media.ignore_queue if self == x), None)
            self.ignored_count = match.ignored_count
        # remove versions that dont apply
        for version in versions[:]:
            if not version.applies(self):
                versions.remove(version)
        # remove versions that have been downloaded in this session:
        all_versions = copy.deepcopy(versions)
        for version in versions[:]:
            missing = False
            if self.type == "movie" or self.type == "episode":
                if (
                    self.query() + " [" + version.name + "]"
                    in media.downloaded_versions
                ):
                    versions.remove(version)
            elif self.type == "show":
                for season in self.Seasons:
                    for episode in season.Episodes:
                        if (
                            not episode.query() + " [" + version.name + "]"
                            in media.downloaded_versions
                        ):
                            missing = True
                            break
                    if missing == True:
                        break
                if not missing:
                    versions.remove(version)
            elif self.type == "season":
                for episode in self.Episodes:
                    if (
                        not episode.query() + " [" + version.name + "]"
                        in media.downloaded_versions
                    ):
                        missing = True
                        break
                if not missing:
                    versions.remove(version)
        if quick:
            return versions
        # If all versions vanished after the session-level filter, fall back to the applicable list
        if len(versions) == 0 and len(all_versions) > 0:
            ui_print(
                "[VERSIONS FALLBACK] No versions left after session filter; restoring applicable versions",
                ui_settings.debug,
            )
            versions = copy.deepcopy(all_versions)
        # If Trakt is the  collection service, the upgrading of collected content is not possible, since no record of the downloaded file names is kept. return the missing versions from this session.
        if library()[0].name != "Plex Library":
            return versions
        # If Plex is the collection service, check if all versions are missing in this session. If not all versions are missing, at least one can still be downloaded normally and no upgrades should be made.
        if versions != all_versions:
            return versions
        # Check if there are any missing versions with upgrade rules for this media item, if not, return all versions.
        upgrade_versions = []
        for version in versions:
            for rule in version.rules:
                if rule[1] == "upgrade":
                    if (
                        not self.query() + " [" + version.name + " upgrade]"
                        in media.downloaded_versions
                    ):
                        upgrade_versions += [version]
                        break
        if len(upgrade_versions) == 0:
            return versions
        # Check if the content is completely collected:
        from content.services.plex import current_library

        if not self.complete(current_library):
            return versions
        # If the collection service is Plex, all versions are missing, there are upgradable versions and content is completely collected, look for upgrades:
        versions = []
        for version in upgrade_versions:
            added = False
            self.set_file_names()
            if self.type == "movie" or self.type == "episode":
                if (
                    not self.query() + " [" + version.name + " upgrade]"
                    in media.downloaded_versions
                ):
                    for rule in version.rules:
                        if not rule[1] == "upgrade":
                            continue
                        if releases.sort.version.rule(
                            rule[0], rule[1], rule[2], rule[3]
                        ).upgrade(self.existing_releases):
                            upgrade_rules = copy.deepcopy(version.rules)
                            for i, rule_ in enumerate(version.rules):
                                if rule_[1] == "upgrade":
                                    upgrade_rules[i][1] = "requirement"
                            versions += [
                                releases.sort.version(
                                    version.name + " upgrade",
                                    version.triggers,
                                    version.lang,
                                    upgrade_rules,
                                )
                            ]
                            break
            elif self.type == "show":
                for season in self.Seasons:
                    for episode in season.Episodes:
                        if (
                            not episode.query() + " [" + version.name + " upgrade]"
                            in media.downloaded_versions
                        ):
                            for rule in version.rules:
                                if not rule[1] == "upgrade":
                                    continue
                                if releases.sort.version.rule(
                                    rule[0], rule[1], rule[2], rule[3]
                                ).upgrade(episode.existing_releases):
                                    upgrade_rules = copy.deepcopy(version.rules)
                                    for i, rule_ in enumerate(version.rules):
                                        if rule_[1] == "upgrade":
                                            upgrade_rules[i][1] = "requirement"
                                    versions += [
                                        releases.sort.version(
                                            version.name + " upgrade",
                                            version.triggers,
                                            version.lang,
                                            upgrade_rules,
                                        )
                                    ]
                                    added = True
                                    break
                            if added:
                                break
                    if added:
                        break
            elif self.type == "season":
                for episode in self.Episodes:
                    if (
                        not episode.query() + " [" + version.name + " upgrade]"
                        in media.downloaded_versions
                    ):
                        for rule in version.rules:
                            if not rule[1] == "upgrade":
                                continue
                            if releases.sort.version.rule(
                                rule[0], rule[1], rule[2], rule[3]
                            ).upgrade(episode.existing_releases):
                                upgrade_rules = copy.deepcopy(version.rules)
                                for i, rule_ in enumerate(version.rules):
                                    if rule_[1] == "upgrade":
                                        upgrade_rules[i][1] = "requirement"
                                versions += [
                                    releases.sort.version(
                                        version.name + " upgrade",
                                        version.triggers,
                                        version.lang,
                                        upgrade_rules,
                                    )
                                ]
                                added = True
                                break
                        if added:
                            break
        if len(versions) > 0:
            versions
        return versions

    def version_missing(self):
        all_versions = []
        if self in media.ignore_queue:
            match = next((x for x in media.ignore_queue if self == x), None)
            self.ignored_count = match.ignored_count
        for version in releases.sort.versions:
            if not "\u0336" in version[0]:
                all_versions += [
                    releases.sort.version(
                        version[0], version[1], version[2], version[3]
                    )
                ]
        for version in all_versions[:]:
            if not version.applies(self):
                all_versions.remove(version)
        return len(self.versions()) > 0 and not self.versions() == all_versions

    def set_file_names(self):
        if not library()[0].name == "Plex Library" or hasattr(self, "upgradable"):
            return
        import content.services.plex as plex

        self.upgradable = True
        if self.type == "show":
            for season in self.Seasons:
                season.upgradable = True
                for episode in season.Episodes:
                    episode.set_file_names()
        if self.type == "season":
            for episode in self.Episodes:
                episode.set_file_names()
        if self.type in ["episode", "movie"]:
            for element in plex.current_library:
                if self.type == "movie":
                    if self == element:
                        try:
                            for Media in element.Media:
                                res = (
                                    "2160"
                                    if Media.videoResolution == "4k"
                                    else Media.videoResolution
                                )
                                for Part in Media.Part:
                                    self.existing_releases += [
                                        "(" + res + "p) " + Part.file
                                    ]
                            return
                        except Exception as e:
                            ui_print(
                                "error: (file name exception): "
                                + self.query()
                                + " "
                                + str(e),
                                ui_settings.debug,
                            )
                            return
                elif self.type == "episode":
                    if element.type == "show":
                        if any(eid in self.grandparentEID for eid in element.EID):
                            for season in element.Seasons:
                                if not hasattr(season, "index"):
                                    continue
                                if self.parentIndex == season.index:
                                    for episode in season.Episodes:
                                        if self == episode:
                                            try:
                                                for Media in episode.Media:
                                                    res = (
                                                        "2160"
                                                        if Media.videoResolution == "4k"
                                                        else Media.videoResolution
                                                    )
                                                    for Part in Media.Part:
                                                        self.existing_releases += [
                                                            "("
                                                            + res
                                                            + "p) "
                                                            + Part.file
                                                        ]
                                                return
                                            except Exception as e:
                                                ui_print(
                                                    "error: (file name exception): "
                                                    + self.query()
                                                    + " "
                                                    + str(e),
                                                    ui_settings.debug,
                                                )
                                                return

    def complete(self, list):
        if self.type in ["movie", "episode"]:
            if (
                self.collected(list)
                or self.watched()
                or not self.released()
                or self.downloading()
            ):
                return True
        elif self.type == "show":
            if self.collected(list):
                return True
            Seasons = copy.deepcopy(self.Seasons)
            for season in Seasons[:]:
                if (
                    not season.collected(list)
                    and not season.watched()
                    and season.released()
                    and not season.downloading()
                ):
                    for episode in season.Episodes[:]:
                        if (
                            episode.collected(list)
                            or episode.watched()
                            or not episode.released()
                            or episode.downloading()
                        ):
                            season.Episodes.remove(episode)
                else:
                    if season in Seasons:
                        Seasons.remove(season)
                if len(season.Episodes) == 0 and season in Seasons:
                    Seasons.remove(season)
            return len(Seasons) == 0
        elif self.type == "season":
            if self.collected(list):
                return True
            Episodes = copy.deepcopy(self.Episodes)
            for episode in Episodes[:]:
                if (
                    episode.collected(list)
                    or episode.watched()
                    or not episode.released()
                    or episode.downloading()
                ):
                    Episodes.remove(episode)
            return len(Episodes) == 0
        return False

    def watch(self):
        global imdb_scraped
        imdb_scraped = False
        names = []
        retries = 0
        for version in self.versions():
            names += [version.name]
            for trigger in version.triggers:
                if trigger[0] == "retries" and trigger[1] == "<=":
                    if int(float(trigger[2])) > retries:
                        retries = int(float(trigger[2]))
        if retries == 0:
            return

        message = (
            "retrying download in "
            + str(round(int(ui_settings.loop_interval_seconds) / 60))
            + "min for item: "
            + self.query()
            + " - version/s ["
            + "],[".join(names)
            + "]"
        )
        if not self in media.ignore_queue:
            self.ignored_count = 1
            media.ignore_queue += [self]
            ui_print(
                message + " - attempt " + str(self.ignored_count) + "/" + str(retries)
            )
        else:
            match = next((x for x in media.ignore_queue if self == x), None)
            if match.ignored_count < retries:
                match.ignored_count += 1
                ui_print(
                    message
                    + " - attempt "
                    + str(match.ignored_count)
                    + "/"
                    + str(retries)
                )
            else:
                media.ignore_queue.remove(match)
                ignore.add(self)

    def unwatch(self):
        ignore.remove(self)

    def watched(self):
        return ignore.check(self)

    def released(self):
        try:
            if not hasattr(self, "originallyAvailableAt"):
                return False  # attribute may not be present

            released = datetime.datetime.utcnow() - datetime.datetime.strptime(
                self.originallyAvailableAt, "%Y-%m-%d"
            )
            if hasattr(self, "offset_airtime"):
                smallest_offset = 0
                for offset in self.offset_airtime:
                    if float(offset) < smallest_offset or smallest_offset == 0:
                        smallest_offset = float(offset)
                released = (
                    datetime.datetime.utcnow()
                    - datetime.datetime.strptime(self.originallyAvailableAt, "%Y-%m-%d")
                    - datetime.timedelta(hours=float(smallest_offset))
                )
            if self.type == "movie":
                if released.days >= -30 and released.days <= 180:
                    return self.available()
                return released.days > 0
            else:
                if released.days >= -1 and released.days <= 1:
                    return self.available()
                return released.days >= 0
        except Exception as e:
            ui_print(
                "media error: (released exception): " + str(e), debug=ui_settings.debug
            )
            return False

    def available(self):
        import content.services.plex as plex
        import content.services.trakt as trakt
        import content.services.overseerr as overseerr

        if (
            self.watchlist == plex.watchlist and len(trakt.users) > 0
        ) or self.watchlist == trakt.watchlist:
            if self.watchlist == plex.watchlist:
                self.match("content.services.trakt")
            trakt.current_user = trakt.users[0]
            try:
                if self.type == "show":
                    if hasattr(self, "offset_airtime"):
                        for offset in self.offset_airtime:
                            if datetime.datetime.utcnow() > self.offset_airtime[offset]:
                                return True
                        return False
                    if not hasattr(self, "first_aired") or self.first_aired is None:
                        return False
                    return datetime.datetime.utcnow() > datetime.datetime.strptime(
                        self.first_aired, "%Y-%m-%dT%H:%M:%S.000Z"
                    )
                elif self.type == "movie":
                    release_date = None
                    releases, header = trakt.get(
                        "https://api.trakt.tv/movies/"
                        + str(self.ids.trakt)
                        + "/releases/"
                    )
                    for release in releases:
                        if (
                            release.release_type == "digital"
                            or release.release_type == "physical"
                            or release.release_type == "tv"
                        ):
                            if release_date == None:
                                release_date = release.release_date
                            elif (
                                release.release_date is not None
                                and datetime.datetime.strptime(release_date, "%Y-%m-%d")
                                > datetime.datetime.strptime(
                                    release.release_date, "%Y-%m-%d"
                                )
                            ):
                                release_date = release.release_date
                    # If no release date was found, select the theatrical release date + 2 Month delay
                    if release_date == None:
                        for release in releases:
                            if release_date == None:
                                release_date = release.release_date
                            elif (
                                release.release_date is not None
                                and datetime.datetime.strptime(release_date, "%Y-%m-%d")
                                > datetime.datetime.strptime(
                                    release.release_date, "%Y-%m-%d"
                                )
                            ):
                                release_date = release.release_date
                        if release_date is not None:
                            release_date = datetime.datetime.strptime(
                                release_date, "%Y-%m-%d"
                            ) + datetime.timedelta(days=60)
                            release_date = release_date.strftime("%Y-%m-%d")
                    # Get trakt 'Latest HD/4k Releases' Lists to accept early releases
                    match = False
                    if trakt.early_releases == "true":
                        trakt_lists, header = trakt.get(
                            "https://api.trakt.tv/movies/"
                            + str(self.ids.trakt)
                            + "/lists/personal/popular"
                        )
                        for trakt_list in trakt_lists:
                            if regex.search(
                                r"(latest|new).*?(releases)", trakt_list.name, regex.I
                            ):
                                match = True
                    # if release_date and delay have passed or the movie was released early
                    if match:
                        ui_print(
                            "item: '"
                            + self.query()
                            + "' seems to be released prior to its official release date and will be downloaded."
                        )
                        return True
                    if release_date is None:
                        return False
                    if hasattr(self, "offset_airtime"):
                        for offset in self.offset_airtime:
                            if datetime.datetime.utcnow() > (
                                datetime.datetime.strptime(release_date, "%Y-%m-%d")
                                + datetime.timedelta(hours=float(offset))
                            ):
                                return True
                            available = (
                                datetime.datetime.strptime(release_date, "%Y-%m-%d")
                                + datetime.timedelta(hours=float(offset))
                                - datetime.datetime.utcnow()
                            )
                            ui_print(
                                "item: '"
                                + self.query()
                                + "' is available in: "
                                + "{:02d}d:{:02d}h:{:02d}m:{:02d}s".format(
                                    available.days,
                                    available.seconds // 3600,
                                    (available.seconds % 3600) // 60,
                                    available.seconds % 60,
                                )
                                + (
                                    " (including offset of: " + offset + "h)"
                                    if offset != "0"
                                    else ""
                                )
                            )
                        return False
                    available = (
                        datetime.datetime.strptime(release_date, "%Y-%m-%d")
                        - datetime.datetime.utcnow()
                    )
                    if not datetime.datetime.utcnow() > datetime.datetime.strptime(
                        release_date, "%Y-%m-%d"
                    ):
                        ui_print(
                            "item: '"
                            + self.query()
                            + "' is available in: "
                            + "{:02d}d:{:02d}h:{:02d}m:{:02d}s".format(
                                available.days,
                                available.seconds // 3600,
                                (available.seconds % 3600) // 60,
                                available.seconds % 60,
                            )
                        )
                    return datetime.datetime.utcnow() > datetime.datetime.strptime(
                        release_date, "%Y-%m-%d"
                    )
                elif self.type == "season":
                    try:
                        if not hasattr(self, "first_aired") or self.first_aired is None:
                            return False
                        if (
                            hasattr(self, "offset_airtime")
                            and len(self.offset_airtime) > 0
                        ):
                            for offset in self.offset_airtime:
                                if (
                                    datetime.datetime.utcnow()
                                    > datetime.datetime.strptime(
                                        self.first_aired, "%Y-%m-%dT%H:%M:%S.000Z"
                                    )
                                    + datetime.timedelta(hours=float(offset))
                                ):
                                    return True
                            return False
                        return datetime.datetime.utcnow() > datetime.datetime.strptime(
                            self.first_aired, "%Y-%m-%dT%H:%M:%S.000Z"
                        )
                    except:
                        return True
                elif self.type == "episode":
                    if not hasattr(self, "first_aired") or self.first_aired is None:
                        return False
                    if hasattr(self, "offset_airtime"):
                        for offset in self.offset_airtime:
                            if datetime.datetime.utcnow() > datetime.datetime.strptime(
                                self.first_aired, "%Y-%m-%dT%H:%M:%S.000Z"
                            ) + datetime.timedelta(hours=float(offset)):
                                return True
                            available = (
                                datetime.datetime.strptime(
                                    self.first_aired, "%Y-%m-%dT%H:%M:%S.000Z"
                                )
                                + datetime.timedelta(hours=float(offset))
                                - datetime.datetime.utcnow()
                            )
                            ui_print(
                                "item: '"
                                + self.query()
                                + "' is available in: "
                                + "{:02d}d:{:02d}h:{:02d}m:{:02d}s".format(
                                    available.days,
                                    available.seconds // 3600,
                                    (available.seconds % 3600) // 60,
                                    available.seconds % 60,
                                )
                                + (
                                    " (including offset of: " + offset + "h)"
                                    if offset != "0"
                                    else ""
                                )
                            )
                        return False
                    if datetime.datetime.utcnow() > datetime.datetime.strptime(
                        self.first_aired, "%Y-%m-%dT%H:%M:%S.000Z"
                    ):
                        return True
                    available = (
                        datetime.datetime.strptime(
                            self.first_aired, "%Y-%m-%dT%H:%M:%S.000Z"
                        )
                        - datetime.datetime.utcnow()
                    )
                    ui_print(
                        "item: '"
                        + self.query()
                        + "' is available in: "
                        + "{:02d}d:{:02d}h:{:02d}m:{:02d}s".format(
                            available.days,
                            available.seconds // 3600,
                            (available.seconds % 3600) // 60,
                            available.seconds % 60,
                        )
                    )
                    return False
            except Exception as e:
                ui_print(
                    "media error: (availability exception): " + str(e),
                    debug=ui_settings.debug,
                )
                return False
        try:
            released = datetime.datetime.utcnow() - datetime.datetime.strptime(
                self.originallyAvailableAt, "%Y-%m-%d"
            )
            if released.days < 0:
                return False
            return True
        except:
            return False

    def collect(self, refresh_=True):
        for refresh_service in refresh():
            if refresh_service.__module__ == self.__module__ or (
                self.__module__
                in [
                    "content.services.trakt",
                    "releases",
                    "content.services.overseerr",
                    "content.services.plex",
                ]
                and refresh_service.__module__
                in ["content.services.plex", "content.services.jellyfin"]
            ):
                if refresh_ or refresh_service.name == "Plex Labels":
                    refresh_service(self)
            elif (
                self.__module__
                in ["content.services.plex", "content.services.overseerr"]
                and refresh_service.__module__ == "content.services.trakt"
            ):
                try:
                    if refresh_:
                        self.match("content.services.trakt")
                        refresh_service(self)
                except:
                    ui_print("[trakt] error: adding item to trakt collection failed")
            else:
                ui_print(
                    "error: library update service could not be determined",
                    ui_settings.debug,
                )

    def collected(self, list):
        if self.type in ["movie", "show"]:
            if self in list:
                if self.type == "movie":
                    return True
                match = next((x for x in list if x == self), None)
                if not hasattr(match, "leafCount"):
                    return False
                if match.leafCount == self.leafCount:
                    return True
            return False
        if self.type == "season":
            for show in list:
                if show.type == "show":
                    for season in show.Seasons:
                        if self == season:
                            if season.leafCount == self.leafCount:
                                return True
                            return False
            return False
        if self.type == "episode":
            for show in list:
                if show.type == "show":
                    for season in show.Seasons:
                        for episode in season.Episodes:
                            if self == episode:
                                return True
            return False

    def uncollected(self, list):
        if self.type == "movie":
            if not self.collected(list):
                return [self]
        elif self.type == "show":
            if self.collected(list) and not self.version_missing():
                return []
            Seasons = copy.deepcopy(self.Seasons)
            for season in Seasons[:]:
                if (
                    (not season.collected(list) or season.version_missing())
                    and not season.watched()
                    and season.released()
                    and not season.downloading()
                ):
                    for episode in season.Episodes[:]:
                        if (
                            (episode.collected(list) and not episode.version_missing())
                            or episode.watched()
                            or not episode.released()
                            or episode.downloading()
                        ):
                            season.Episodes.remove(episode)
                else:
                    if season in Seasons:
                        Seasons.remove(season)
                if len(season.Episodes) == 0 and season in Seasons:
                    Seasons.remove(season)
            return Seasons
        return []

    def downloading(self):
        if hasattr(self, "version"):
            return [self.query() + " [" + self.version.name + "]"] in debrid.downloading
        else:
            return False

    def hasended(self):
        if hasattr(self, "_ended_cached"):
            return self._ended_cached

        def _parse_bool(value):
            if isinstance(value, bool):
                return value
            if value is None:
                return None
            v = str(value).strip().lower()
            if v in ("1", "true", "yes"):
                return True
            if v in ("0", "false", "no"):
                return False
            return None

        ended = None
        if hasattr(self, "status") and self.status is not None:
            if str(self.status).strip().lower() == "ended":
                ended = True
                self.ended_source = "plex_status"
        if ended is None and hasattr(self, "isContinuingSeries"):
            is_cont = _parse_bool(self.isContinuingSeries)
            if is_cont is not None:
                ended = not is_cont
                self.ended_source = "plex_isContinuingSeries"

        if ended is None and getattr(self, "type", "") == "show":
            try:
                from content.services import tmdb as tmdb_service
                tmdb_result = tmdb_service.get_show_status(self)
                if tmdb_result:
                    self.tmdb_status = tmdb_result.get("status")
                    self.tmdb_id = tmdb_result.get("tmdb_id")
                    self.tmdb_expected_episodes = tmdb_result.get("expected_episodes")
                    self.tmdb_expected_episodes_source = tmdb_result.get(
                        "expected_source"
                    )
                    self.ended_source = tmdb_result.get("source")
                    ended = bool(tmdb_result.get("ended", False))
            except Exception as e:
                ui_print(f"[tmdb] error: {e}", ui_settings.debug)

        if ended is None:
            ended = False
        self._ended_cached = ended
        return ended

    def _find_local_show(self, library):
        if not library:
            return None
        if hasattr(self, "EID") and self.EID:
            for item in library:
                if item.type == "show" and hasattr(item, "EID"):
                    for eid in self.EID:
                        if eid in item.EID:
                            return item
        tmdb_id = getattr(self, "tmdb_id", None)
        if tmdb_id:
            tmdb_ids = {f"tmdb://{tmdb_id}", f"themoviedb://{tmdb_id}"}
            for item in library:
                if item.type == "show" and hasattr(item, "EID"):
                    for eid in item.EID:
                        if eid in tmdb_ids:
                            return item
        if hasattr(self, "guid"):
            for item in library:
                if item.type == "show" and getattr(item, "guid", None) == self.guid:
                    return item
        title = str(getattr(self, "title", "")).strip().lower()
        year = getattr(self, "year", None)
        if title:
            matches = []
            for item in library:
                if item.type != "show":
                    continue
                if str(getattr(item, "title", "")).strip().lower() != title:
                    continue
                if year and hasattr(item, "year") and item.year not in (None, ""):
                    if str(item.year) != str(year):
                        continue
                matches.append(item)
            if len(matches) == 1:
                return matches[0]
        return None

    def _local_episode_count(self, local_show):
        if not local_show or not hasattr(local_show, "Seasons"):
            return None
        count = 0
        for season in local_show.Seasons:
            index = getattr(season, "index", None)
            try:
                index = int(index)
            except Exception:
                index = None
            if index == 0:
                continue
            if index is None:
                title = str(getattr(season, "title", "")).lower()
                if "special" in title:
                    continue
            season_count = getattr(season, "leafCount", None)
            if season_count is None:
                season_count = len(getattr(season, "Episodes", []))
            try:
                count += int(season_count)
            except Exception:
                continue
        return count

    def show_complete(self, library):
        expected = getattr(self, "tmdb_expected_episodes", None)
        expected_source = getattr(self, "tmdb_expected_episodes_source", None)
        if expected is None:
            try:
                from content.services import tmdb as tmdb_service
                tmdb_result = tmdb_service.get_show_status(self)
                if tmdb_result:
                    expected = tmdb_result.get("expected_episodes")
                    expected_source = tmdb_result.get("expected_source")
                    self.tmdb_expected_episodes = expected
                    self.tmdb_expected_episodes_source = expected_source
            except Exception as e:
                ui_print(f"[tmdb] error: {e}", ui_settings.debug)
        local_show = self._find_local_show(library)
        local_count = self._local_episode_count(local_show)
        complete = (
            expected is not None
            and local_count is not None
            and local_count >= expected
        )
        return complete, local_count, expected, expected_source

    def download(self, retries=0, library=[], parentReleases=[]):
        global imdb_scraped
        refresh_ = False
        i = 0
        self.Releases = []
        if self.type in ["movie", "show"]:
            if not hasattr(self, "title") or self.title == "" or self.title is None:
                ui_print(
                    "error: media item has no title. This unknown movie/show might not be released yet."
                )
                return
            elif not hasattr(self, "year") or self.year == "" or self.year is None:
                ui_print(
                    f"error: media item {self.title} has no release year. This movie/show might not be released yet."
                )
                return
        scraper.services.overwrite = []
        EIDS = []
        imdbID = "."
        if hasattr(self, "EID"):
            EIDS = self.EID
        if hasattr(self, "parentEID"):
            EIDS = self.parentEID
        if hasattr(self, "grandparentEID"):
            EIDS = self.grandparentEID
        for EID in EIDS:
            if EID.startswith("imdb"):
                service, imdbID = EID.split("://")
        # set anime info before episodes are removed
        self.isanime()
        if self.type == "movie":
            ui_print(
                f"processing movie: {self.title} ({self.year})", debug=ui_settings.debug
            )
            if (len(self.uncollected(library)) > 0 or self.version_missing()) and len(
                self.versions()
            ) > 0:
                if self.released() and not self.watched() and not self.downloading():
                    if not hasattr(self, "year") or self.year == None:
                        ui_print("error: media item has no release year.")
                        return
                    tic = time.perf_counter()
                    alternate_years = [self.year, self.year - 1, self.year + 1]
                    langs = []
                    for version in self.versions():
                        if not version.lang in langs and not version.lang == "en":
                            self.aliases(version.lang)
                            langs += [version.lang]
                    self.aliases("en")
                    imdb_scraped = False
                    for year in alternate_years:
                        i = 0
                        while len(self.Releases) == 0 and i <= retries:
                            for k, title in enumerate(self.alternate_titles):
                                self.Releases += scraper.scrape(
                                    self.query(title).replace(
                                        str(self.year), str(year)
                                    ),
                                    self.deviation(year=str(year))
                                    + "("
                                    + imdbID
                                    + ")?",
                                )
                                if (
                                    len(self.Releases) < 20
                                    and k == 0
                                    and not imdb_scraped
                                    and not imdbID == "."
                                ):
                                    self.Releases += scraper.scrape(
                                        imdbID, "(.*|" + imdbID + ")"
                                    )
                                    imdb_scraped = True
                                if len(self.Releases) > 0:
                                    break
                            i += 1
                        if not len(self.Releases) == 0:
                            self.year = year
                            break
                    debrid_downloaded, retry = self.debrid_download(force=False)
                    if debrid_downloaded:
                        refresh_ = True
                        if not retry and (
                            self.watchlist.autoremove == "both"
                            or self.watchlist.autoremove == "movie"
                        ):
                            self.watchlist.remove([], self)
                        toc = time.perf_counter()
                        ui_print("took " + str(round(toc - tic, 2)) + "s")
                    if retry:
                        self.watch()
        elif self.type == "show":
            ui_print(
                f"processing show: {self.title} ({self.year})", debug=ui_settings.debug
            )
            if (
                len(self.versions()) > 0
                and self.released()
                and (not self.collected(library) or self.version_missing())
                and not self.watched()
            ):
                self.isanime()
                self.Seasons = self.uncollected(library)
                # if there are uncollected episodes
                if len(self.Seasons) > 0:
                    tic = time.perf_counter()
                    langs = []
                    for version in self.versions():
                        if not version.lang in langs and not version.lang == "en":
                            self.aliases(version.lang)
                            langs += [version.lang]
                    self.aliases("en")
                    imdb_scraped = False
                    # if there is more than one uncollected season
                    if len(self.Seasons) > 1:
                        if self.isanime():
                            for k, title in enumerate(self.alternate_titles[:3]):
                                self.Releases += scraper.scrape(
                                    self.anime_query(title),
                                    self.deviation()
                                    + "("
                                    + imdbID
                                    + ")?(nyaa"
                                    + "|".join(self.alternate_titles)
                                    + ")?",
                                )
                                if (
                                    len(self.Releases) < 20
                                    and k == 0
                                    and not imdb_scraped
                                    and not imdbID == "."
                                ):
                                    self.Releases += scraper.scrape(
                                        imdbID,
                                        "(.*|S00|"
                                        + imdbID
                                        + "|nyaa"
                                        + "|".join(self.alternate_titles)
                                        + ")",
                                    )
                                    imdb_scraped = True
                                if len(self.Releases) > 0:
                                    break
                        else:
                            for k, title in enumerate(self.alternate_titles[:3]):
                                self.Releases += scraper.scrape(
                                    self.query(title),
                                    self.deviation() + "(" + imdbID + ")?",
                                )
                                if (
                                    len(self.Releases) < 20
                                    and k == 0
                                    and not imdb_scraped
                                    and not imdbID == "."
                                ):
                                    self.Releases += scraper.scrape(
                                        imdbID, "(.*|S00|" + imdbID + ")"
                                    )
                                    imdb_scraped = True
                                if len(self.Releases) > 0:
                                    break
                        debrid.check(self)
                        parentReleases = copy.deepcopy(self.Releases)
                        # if there are more than 3 uncollected seasons, look for multi-season releases before downloading single-season releases
                        if len(self.Seasons) > 3:
                            # gather file information on scraped, cached releases
                            multi_season_releases = []
                            season_releases = [None] * len(self.Seasons)
                            minimum_episodes = len(self.files()) / 2
                            season_queries = []
                            for season in self.Seasons:
                                season_queries += [season.deviation()]
                            season_queries_str = "(" + ")|(".join(season_queries) + ")"
                            if self.isanime():
                                for release in self.Releases:
                                    if regex.search(
                                        self.anime_count, release.title, regex.I
                                    ):
                                        multi_season_releases += [release]
                            for release in self.Releases:
                                match = regex.match(
                                    season_queries_str, release.title, regex.I
                                )
                                for version in release.files:
                                    if isinstance(version.wanted, int):
                                        # if a multi season pack contains more than half of all uncollected episodes, accept it as a multi-season-pack.
                                        if version.wanted > minimum_episodes:
                                            multi_season_releases += [release]
                                            break
                                            # if the release is a single-season pack, find out the quality
                                        if match:
                                            for index, season_query in enumerate(
                                                season_queries
                                            ):
                                                if regex.match(
                                                    season_query, release.title, regex.I
                                                ):
                                                    if (
                                                        version.wanted
                                                        >= len(
                                                            self.Seasons[index].files()
                                                        )
                                                        - 2
                                                        and season_releases[index]
                                                        == None
                                                    ):
                                                        quality = regex.search(
                                                            "(2160|1080|720|480)(?=p|i)",
                                                            release.title,
                                                            regex.I,
                                                        )
                                                        if quality:
                                                            quality = int(
                                                                quality.group()
                                                            )
                                                        else:
                                                            quality = 0
                                                        season_releases[index] = quality
                                                        break
                            # if there are eligible multi-season packs
                            if len(multi_season_releases) > 0:
                                download_multi_season_release = False
                                # if one of the shows seasons cant be downloaded as a single-season pack, download the multi-season pack.
                                for season_release in season_releases:
                                    if season_release == None:
                                        download_multi_season_release = True
                                        break
                                # if all seasons of the show could also be downloaded as single-season packs, compare the quality of the best ranking multi season pack with the lowest quality of the single season packs.
                                if not download_multi_season_release:
                                    season_quality = min(season_releases)
                                    quality = regex.search(
                                        "(2160|1080|720|480)(?=p|i)",
                                        multi_season_releases[0].title,
                                        regex.I,
                                    )
                                    if quality:
                                        quality = int(quality.group())
                                    else:
                                        quality = 0
                                    if quality >= season_quality:
                                        download_multi_season_release = True
                                # if either not all seasons can be downloaded as single-season packs or the single season packs are of equal or lower quality compared to the multi-season packs, download the multi season packs.
                                if download_multi_season_release:
                                    self.Releases = multi_season_releases
                                    debrid_downloaded, retry = self.debrid_download()
                                    if debrid_downloaded:
                                        refresh_ = True
                                        if not retry:
                                            if self.isanime():
                                                self.Seasons = []
                                            else:
                                                for season in self.Seasons[:]:
                                                    for episode in season.Episodes[:]:
                                                        for file in self.Releases[
                                                            0
                                                        ].files:
                                                            if hasattr(file, "match"):
                                                                if (
                                                                    file.match
                                                                    == episode.files()[
                                                                        0
                                                                    ]
                                                                ):
                                                                    season.Episodes.remove(
                                                                        episode
                                                                    )
                                                                    break
                                                    if len(season.Episodes) == 0:
                                                        self.Seasons.remove(season)
                    # Download all remaining seasons by starting a thread for each season.
                    results = [None] * len(self.Seasons)
                    threads = []
                    # start thread for each season
                    for index, Season in enumerate(self.Seasons):
                        results[index] = Season.download(
                            library=library, parentReleases=parentReleases
                        )
                    retry = False
                    for index, result in enumerate(results):
                        if result == None:
                            continue
                        if result[0]:
                            refresh_ = True
                        if result[1]:
                            retry = True
                    if not retry and (
                        self.watchlist.autoremove == "both"
                        or self.watchlist.autoremove == "show"
                    ):
                        ended = self.hasended()
                        ended_source = getattr(self, "ended_source", "unknown")
                        if ended:
                            (
                                show_complete,
                                local_count,
                                expected_count,
                                expected_source,
                            ) = self.show_complete(library)
                        else:
                            show_complete = False
                            local_count = None
                            expected_count = None
                            expected_source = None
                        if ended and show_complete:
                            self.watchlist.remove([], self)
                        else:
                            ui_print(
                                f"[SHOW_AUTOREMOVE] skipped: ended={ended} source={ended_source} complete={show_complete} local={local_count} expected={expected_count} expected_source={expected_source}",
                                ui_settings.debug,
                            )
                    toc = time.perf_counter()
                    ui_print("took " + str(round(toc - tic, 2)) + "s")
        elif self.type == "season":
            ui_print(
                f"processing: {self.parentTitle} {self.title}", debug=ui_settings.debug
            )

            # If this season was already handled via a pack in this session, skip further work
            if hasattr(self, "pack_downloaded") and self.pack_downloaded:
                ui_print(
                    "[SEASON_PACK] Season already marked as downloaded; skipping.",
                    ui_settings.debug,
                )
                return False, False

            debrid_downloaded = False
            retryep = False
            attempt_episodes = False
            for release in parentReleases:
                if regex.match(self.deviation(), release.title, regex.I):
                    self.Releases += [release]
            # Set the episodes parent releases to be the seasons parent releases:
            scraped_releases = copy.deepcopy(parentReleases)

            # If the season pack is already present locally (episodes have files in Plex or on disk),
            # mark them as collected to avoid pointless re-download attempts.
            try:
                self.set_file_names()
            except Exception as e:
                ui_print(f"[EPISODE LOOP DEBUG] set_file_names failed: {e}", ui_settings.debug)

            already_collected_eps = []
            plex_collected_eps = []
            season_key = self.pack_key()
            for ep in self.Episodes:
                # Match by Plex existing_releases (Plex is source of truth for "already present")
                has_existing = bool(getattr(ep, "existing_releases", []))
                if has_existing:
                    plex_collected_eps.append(ep)

                if has_existing:
                    ep.skip_download = True
                    ep.skip_scraping = True
                    ep.already_collected = True
                    # ensure a version exists for downstream steps (subtitle enqueue, etc.)
                    ep_versions = ep.versions()
                    if ep_versions:
                        ep.version = ep_versions[0]
                    already_collected_eps.append(ep)

            if already_collected_eps:
                ui_print(
                    f"[EPISODE LOOP DEBUG] {len(already_collected_eps)} episode(s) already present in Plex; skipping debrid download for them",
                    ui_settings.debug,
                )
            all_in_plex = self.Episodes and len(plex_collected_eps) == len(self.Episodes)
            if all_in_plex and season_key and season_key in media.pack_in_progress:
                del media.pack_in_progress[season_key]
                ui_print(
                    "[SEASON_IN_PROGRESS] Plex now has all episodes; clearing in-progress flag",
                    ui_settings.debug,
                )
            if all_in_plex:
                ui_print(
                    f"[SEASON_SKIP] All {len(self.Episodes)} episode(s) already present in Plex; skipping season pack/scrape",
                    ui_settings.debug,
                )
                self.pack_downloaded = True
                for ep in self.Episodes:
                    ep.skip_download = True
                    ep.skip_scraping = True
                return False, False
            if season_key and season_key in media.pack_in_progress:
                ui_print(
                    "[SEASON_IN_PROGRESS] Pack already sent; waiting for Plex, skipping re-scrape",
                    ui_settings.debug,
                )
                try:
                    self.collect(refresh_=True)
                except Exception as e:
                    ui_print(
                        f"[SEASON_IN_PROGRESS] collect() failed while waiting: {e}",
                        ui_settings.debug,
                    )
                return True, True
            # If there is more than one episode
            if len(self.Episodes) > 2:
                if self.season_pack(scraped_releases):
                    debrid_downloaded, retry = self.debrid_download()
                    ui_print(f"[SEASON_PACK] season_pack() returned True")
                    ui_print(f"[SEASON_PACK] debrid_download() returned: downloaded={debrid_downloaded}, retry={retry}")
                    if scraper.traditional() or debrid_downloaded:
                        ui_print(f"[SKIP_SCRAPING] Checking which episodes were actually downloaded")
                        ui_print(f"[SKIP_SCRAPING] scraper.traditional()={scraper.traditional()}, debrid_downloaded={debrid_downloaded}")

                        # Only set skip_scraping for episodes that match releases that were downloaded
                        for episode in self.Episodes:
                            # Check if this episode matches any of the season releases
                            episode_matched = False
                            for release in self.Releases:
                                if regex.match(episode.deviation(), release.title, regex.I):
                                    episode_matched = True
                                    break

                            if episode_matched:
                                episode.skip_scraping = True
                                ui_print(f"[SKIP_SCRAPING] Episode {episode.index}: Found matching release, skip_scraping set to True")
                            else:
                                ui_print(f"[SKIP_SCRAPING] Episode {episode.index}: No matching release, keeping skip_scraping=False")
                # If there was nothing downloaded, scrape specifically for this season
                if not debrid_downloaded:
                    ui_print(f"[SEASON_SCRAPING] Season pack failed, scraping specifically for season {self.index}")
                    ui_print(f"[SEASON_SCRAPING] Clearing self.Releases and starting fresh scraping")
                    self.Releases = []
                    if self.isanime():
                        for k, title in enumerate(self.alternate_titles[:3]):
                            self.Releases += scraper.scrape(
                                self.anime_query(title),
                                "(.*|S"
                                + str("{:02d}".format(self.index))
                                + "|"
                                + imdbID
                                + "|nyaa"
                                + "|".join(self.alternate_titles)
                                + ")",
                            )
                            if (
                                len(self.Releases) < 20
                                and k == 0
                                and not imdb_scraped
                                and not imdbID == "."
                            ):
                                self.Releases += scraper.scrape(
                                    imdbID,
                                    "(.*|S"
                                    + str("{:02d}".format(self.index))
                                    + "|"
                                    + imdbID
                                    + "|nyaa"
                                    + "|".join(self.alternate_titles)
                                    + ")",
                                )
                                imdb_scraped = True
                            if len(self.Releases) > 0:
                                break
                    if len(self.Releases) == 0:
                        ui_print(f"[SEASON_SCRAPING] No anime releases found, trying regular scraping")
                        for k, title in enumerate(self.alternate_titles[:3]):
                            query = self.query(title)[:-1]
                            ui_print(f"[SEASON_SCRAPING] Scraping with query: {query[:80]}")
                            self.Releases += scraper.scrape(
                                query,
                                "(.*|S"
                                + str("{:02d}".format(self.index))
                                + "|"
                                + imdbID
                                + ")",
                            )
                            if (
                                len(self.Releases) < 20
                                and k == 0
                                and not imdb_scraped
                                and not imdbID == "."
                            ):
                                self.Releases += scraper.scrape(
                                    imdbID,
                                    "(.*|S"
                                    + str("{:02d}".format(self.index))
                                    + "|"
                                    + imdbID
                                    + ")",
                                )
                                imdb_scraped = True
                            ui_print(f"[SEASON_SCRAPING] Found {len(self.Releases)} releases so far")
                            if len(self.Releases) > 0:
                                break
                    # Set the episodes parent releases to be the newly scraped releases
                    ui_print(f"[SEASON_SCRAPING] Total releases after scraping: {len(self.Releases)}")
                    debrid.check(self)
                    ui_print(f"[SEASON_SCRAPING] Checked debrid cache status")
                    scraped_releases = copy.deepcopy(self.Releases)
                    ui_print(f"[SEASON_SCRAPING] scraped_releases set with {len(scraped_releases)} releases")
            # If there was nothing downloaded, attempt downloading again using the newly scraped releases
            retry = False
            if not debrid_downloaded:
                removed = 0
                for release in self.Releases[:]:
                    if not regex.match(self.deviation(), release.title, regex.I):
                        removed += 1
                        self.Releases.remove(release)
                if removed and ui_settings.debug == "true":
                    ui_print(
                        f"[download (show)] filtered {removed} releases not matching deviation {self.deviation()}",
                        ui_settings.debug,
                    )
                ui_print(f"[SEASON_PACK_2] Checking season_pack() again after scraping")
                if self.season_pack(scraped_releases):
                    ui_print(f"[SEASON_PACK_2] season_pack() returned True, calling debrid_download()")
                    debrid_downloaded, retry = self.debrid_download()
                    ui_print(f"[SEASON_PACK_2] debrid_download() returned: downloaded={debrid_downloaded}, retry={retry}")
                else:
                    ui_print(f"[SEASON_PACK_2] season_pack() returned False")
            if debrid_downloaded:
                ui_print(f"[EPISODE_RELEASES] debrid_downloaded=True, setting up episode releases")
                refresh_ = True
                attempt_episodes = False
                for episode in self.Episodes:
                    ui_print(f"[EPISODE_RELEASES] Checking episode {episode.index}")
                    matches = [r.title for r in scraped_releases if regex.match(episode.deviation(), r.title, regex.I)]
                    if matches:
                        ui_print(f"[EPISODE_RELEASES] Episode {episode.index} matches {len(matches)} releases")
                        ui_print(f"[EPISODE_RELEASES] First match: {matches[0][:100] if matches else 'None'}")
                        episode.skip_scraping = True
                        ui_print(f"[EPISODE_RELEASES] Episode {episode.index}: skip_scraping=True")

                        episode_versions = episode.versions()
                        ui_print(f"[EPISODE_RELEASES] Episode {episode.index} has {len(episode_versions)} versions")

                        for version in copy.deepcopy(episode_versions):
                            ui_print(f"[EPISODE_RELEASES] Testing version: {version.name}")
                            for rule in version.rules[:]:
                                if rule[0] == "bitrate":
                                    version.rules.remove(rule)
                            test_releases = copy.deepcopy(scraped_releases)
                            releases.sort(test_releases, version, False)
                            ui_print(f"[EPISODE_RELEASES] Version {version.name}: {len(test_releases)} matching releases")
                            if len(test_releases) > 0:
                                attempt_episodes = True
                                ui_print(f"[EPISODE_RELEASES] Episode {episode.index}: Found releases, attempt_episodes=True")
                                break
                        if not attempt_episodes:
                            episode.skip_download = True
                            ui_print(f"[EPISODE_RELEASES] Episode {episode.index}: No valid releases, skip_download=True")
                    else:
                        ui_print(f"[EPISODE_RELEASES] Episode {episode.index}: No matches in scraped_releases")

            # If a season pack was downloaded (or files are already present) and no per-episode attempt is needed,
            # skip per-episode processing and stop retries for this season.
            if (debrid_downloaded or getattr(self, "pack_downloaded", False) or already_collected_eps) and not attempt_episodes:
                # mark season/episodes as already handled for next scheduler cycle
                self.pack_downloaded = True
                for ep in self.Episodes:
                    ep.skip_download = True
                    ep.skip_scraping = True
                # trigger collection/refresh to help Plex see the new files
                try:
                    self.collect(refresh_=True)
                except Exception as e:
                    ui_print(f"[SEASON_PACK] collect() failed after pack download: {e}", ui_settings.debug)
                ui_print(
                    "[EPISODE LOOP DEBUG] Season pack already downloaded; skipping per-episode downloads and relying on pack subtitles",
                    ui_settings.debug,
                )
                # Return with retry=False to avoid scheduler relaunch
                return True, False
            # Check if all episodes were successfuly downloaded, download them or queue them to be ignored otherwise
            ui_print(f"[EPISODE LOOP DEBUG] Starting episode loop for {self.title}")
            ui_print(f"[EPISODE LOOP DEBUG] Total episodes in self.Episodes: {len(self.Episodes)}")
            ui_print(f"[EPISODE LOOP DEBUG] Episode list: {[f'E{ep.index:02d}' for ep in self.Episodes]}")

            for episode_index, episode in enumerate(self.Episodes):
                ui_print(f"\n[EPISODE LOOP DEBUG] Processing episode {episode_index + 1}/{len(self.Episodes)}")
                ui_print(f"[EPISODE LOOP DEBUG] Episode index: {episode.index if hasattr(episode, 'index') else 'NO INDEX'}")
                ui_print(f"[EPISODE LOOP DEBUG] Episode title: {episode.title if hasattr(episode, 'title') else 'NO TITLE'}")

                # Check versions
                episode_versions = episode.versions() if hasattr(episode, 'versions') else []
                ui_print(f"[EPISODE LOOP DEBUG] episode.versions() returned {len(episode_versions)} versions")

                if len(episode_versions) > 0:
                    ui_print(f"[EPISODE LOOP DEBUG] Episode has versions, proceeding with download check")

                    downloaded = False
                    retryep = True

                    # Check skip_download attribute
                    has_skip_download = hasattr(episode, "skip_download")
                    ui_print(f"[EPISODE LOOP DEBUG] hasattr(episode, 'skip_download') = {has_skip_download}")

                    if has_skip_download:
                        ui_print(f"[EPISODE LOOP DEBUG] episode.skip_download = {episode.skip_download}")

                    if not has_skip_download:
                        ui_print(f"[EPISODE LOOP DEBUG] Calling episode.download()...")
                        try:
                            downloaded, retryep = episode.download(
                                library=library, parentReleases=scraped_releases
                            )
                            ui_print(f"[EPISODE LOOP DEBUG] episode.download() returned: downloaded={downloaded}, retryep={retryep}")
                        except Exception as e:
                            ui_print(f"[EPISODE LOOP ERROR] Exception in episode.download(): {str(e)}")
                            downloaded = False
                            retryep = False
                    else:
                        if getattr(episode, "already_collected", False):
                            ui_print(f"[EPISODE LOOP DEBUG] Skipping download: episode already present locally")
                            downloaded = True
                            retryep = False
                            # Trigger subtitle fetch even without a fresh download
                            if subtitle_runner and hasattr(episode, "version"):
                                try:
                                    subtitle_runner.enqueue(episode)
                                    ui_print(f"[subs trigger] enqueue subs for already-downloaded episode '{episode.query()}'", ui_settings.debug)
                                except Exception as e:
                                    ui_print(f"[subs trigger] error: {e}", ui_settings.debug)
                        else:
                            ui_print(f"[EPISODE LOOP DEBUG] Skipping download due to skip_download attribute")

                    if downloaded:
                        ui_print(f"[EPISODE LOOP DEBUG] Episode downloaded successfully, setting refresh_=True")
                        refresh_ = True
                    else:
                        ui_print(f"[EPISODE LOOP DEBUG] Episode NOT downloaded")

                    if retryep:
                        ui_print(f"[EPISODE LOOP DEBUG] Calling episode.watch()")
                        episode.watch()
                else:
                    ui_print(f"[EPISODE LOOP DEBUG] Episode has NO versions, checking if should download anyway")

                    # Check if episode should be downloaded even without versions
                    has_skip_download = hasattr(episode, "skip_download") and episode.skip_download
                    has_skip_scraping = hasattr(episode, "skip_scraping") and episode.skip_scraping

                    ui_print(f"[EPISODE LOOP DEBUG] skip_download={has_skip_download}, skip_scraping={has_skip_scraping}")

                    if not has_skip_download and not has_skip_scraping:
                        ui_print(f"[EPISODE LOOP DEBUG] Episode has no versions but should try downloading")
                        ui_print(f"[EPISODE LOOP DEBUG] Calling episode.download() to trigger individual scraping...")

                        try:
                            downloaded, retryep = episode.download(
                                library=library, parentReleases=scraped_releases
                            )
                            ui_print(f"[EPISODE LOOP DEBUG] episode.download() returned: downloaded={downloaded}, retryep={retryep}")

                            if downloaded:
                                ui_print(f"[EPISODE LOOP DEBUG] Episode downloaded successfully after individual scraping!")
                                refresh_ = True
                            else:
                                ui_print(f"[EPISODE LOOP DEBUG] Episode NOT downloaded after individual scraping")

                            if retryep:
                                ui_print(f"[EPISODE LOOP DEBUG] Adding episode to watch list")
                                episode.watch()
                        except Exception as e:
                            ui_print(f"[EPISODE LOOP ERROR] Exception in episode.download(): {str(e)}")
                    else:
                        ui_print(f"[EPISODE LOOP DEBUG] Episode has skip flags, not attempting download")

                ui_print(f"[EPISODE LOOP DEBUG] Finished processing episode {episode_index + 1}/{len(self.Episodes)}")

            ui_print(f"\n[EPISODE LOOP DEBUG] Loop completed. Processed all {len(self.Episodes)} episodes")
            ui_print(f"[EPISODE LOOP DEBUG] Returning: refresh_={refresh_ if 'refresh_' in locals() else 'undefined'}, retry={retry or retryep if 'retryep' in locals() else retry}")
            return refresh_, (retry or retryep)
        elif self.type == "episode":
            ui_print(f"[EPISODE_DOWNLOAD] Processing episode: {self.title if hasattr(self, 'title') else 'Unknown'} (Episode {self.index})")
            ui_print(f"[EPISODE_DOWNLOAD] parentReleases contains {len(parentReleases)} releases")

            # Check what releases match this episode
            matched_releases = []
            for release in parentReleases:
                if regex.match(self.deviation(), release.title, regex.I):
                    self.Releases += [release]
                    matched_releases.append(release.title[:80])

            ui_print(f"[EPISODE_DOWNLOAD] Found {len(matched_releases)} matching releases from parentReleases")
            if matched_releases:
                ui_print(f"[EPISODE_DOWNLOAD] First match: {matched_releases[0]}")

            debrid_downloaded = False
            retry = True

            if len(self.Releases) > 0:
                ui_print(f"[EPISODE_DOWNLOAD] Calling debrid_download() with {len(self.Releases)} releases")
                debrid_downloaded, retry = self.debrid_download()
                ui_print(f"[EPISODE_DOWNLOAD] debrid_download returned: downloaded={debrid_downloaded}, retry={retry}")
            else:
                ui_print(f"[EPISODE_DOWNLOAD] No releases to download yet")

            has_skip_scraping = hasattr(self, "skip_scraping")
            ui_print(f"[EPISODE_DOWNLOAD] skip_scraping attribute: exists={has_skip_scraping}, value={getattr(self, 'skip_scraping', 'N/A')}")

            if (not debrid_downloaded or retry) and not has_skip_scraping:
                ui_print(f"[EPISODE_DOWNLOAD] Will scrape individually (not downloaded={not debrid_downloaded}, retry={retry}, no skip_scraping)")
                if debrid_downloaded:
                    refresh_ = True
                if self.isanime():
                    for title in self.alternate_titles[:3]:
                        self.Releases += scraper.scrape(
                            self.anime_query(title),
                            self.deviation()
                            + "("
                            + imdbID
                            + ")?(nyaa"
                            + "|".join(self.alternate_titles)
                            + ")?",
                        )
                        if len(self.Releases) > 0:
                            break
                if len(self.Releases) == 0 or not self.isanime():
                    ui_print(f"[EPISODE_DOWNLOAD] Starting individual scraping for episode {self.index}")
                    for title in self.alternate_titles[:3]:
                        query = self.query(title)
                        ui_print(f"[EPISODE_DOWNLOAD] Scraping with query: {query[:80]}")

                        if self.isanime():
                            new_releases = scraper.scrape(
                                query.replace(".", " "),
                                self.deviation() + "(" + imdbID + ")?",
                            )
                        else:
                            new_releases = scraper.scrape(
                                query,
                                self.deviation() + "(" + imdbID + ")?",
                            )

                        ui_print(f"[EPISODE_DOWNLOAD] Scraping returned {len(new_releases)} releases")
                        self.Releases += new_releases

                        if len(self.Releases) > 0:
                            ui_print(f"[EPISODE_DOWNLOAD] Found releases, stopping scraping")
                            break

                ui_print(f"[EPISODE_DOWNLOAD] After scraping, total releases: {len(self.Releases)}")
                debrid_downloaded, retry = self.debrid_download()
                ui_print(f"[EPISODE_DOWNLOAD] Final debrid_download returned: downloaded={debrid_downloaded}, retry={retry}")

                if debrid_downloaded:
                    refresh_ = True
                return refresh_, retry
            else:
                ui_print(f"[EPISODE_DOWNLOAD] Skipping individual scraping (downloaded={debrid_downloaded} or has skip_scraping)")
            return debrid_downloaded, retry
        self.collect(refresh_)

    def downloaded(self):
        global imdb_scraped
        imdb_scraped = False
        if self.type == "movie" or self.type == "episode":
            media.downloaded_versions += [self.query() + " [" + self.version.name + "]"]
        elif self.type == "show":
            filemode = False
            for season in self.Seasons:
                for episode in season.Episodes:
                    for file in self.Releases[0].files:
                        if hasattr(file, "match"):
                            if file.match == episode.files()[0]:
                                episode.version = self.version
                                episode.downloaded()
                                filemode = True
                                break
            if not filemode:
                for season in self.Seasons:
                    season.version = self.version
                    season.Releases = self.Releases
                    season.downloaded()
        elif self.type == "season":
            filemode = False
            for episode in self.Episodes:
                episode.version = self.version
                for file in self.Releases[0].files:
                    if hasattr(file, "match"):
                        if file.match == episode.files()[0]:
                            episode.version = self.version
                            episode.downloaded()
                            filemode = True
                            break
            if not filemode:
                for episode in self.Episodes:
                    episode.version = self.version
                    episode.downloaded()

    def debrid_download(self, force=False):
        debrid.check(self)
        self.bitrate()
        if len(self.Releases) > 0:
            releases.print_releases(self.Releases, True)
        scraped_releases = copy.deepcopy(self.Releases)
        downloaded = []
        if len(scraped_releases) > 0:
            if len(self.versions()) == 0:
                ui_print(
                    "error: it seems that no version applies to this media item! nothing will be downloaded. adjust your version settings.",
                    ui_settings.debug,
                )
            for version in self.versions():
                debrid_uncached = True
                for i, rule in enumerate(version.rules):
                    if (
                        rule[0] == "cache status"
                        and rule[1] == "requirement"
                        and rule[2] == "cached"
                    ):
                        debrid_uncached = False
                ui_print(
                    f"[DEBRID_DOWNLOAD] Trying version '{version.name}' (allows_uncached={debrid_uncached})",
                    ui_settings.debug,
                )
                self.version = version
                self.Releases = copy.deepcopy(scraped_releases)
                releases.sort(self.Releases, self.version)
                if len(self.Releases) > 0:
                    releases.print_releases(self.Releases, True)
                ver_dld = False
                for release in copy.deepcopy(self.Releases):
                    self.Releases = [
                        release,
                    ]
                    if (hasattr(release, "cached") and len(release.cached) > 0) or (
                        hasattr(release, "maybe_cached")
                        and len(release.maybe_cached) > 0
                    ):
                        if debrid.download(self, stream=True, force=force):
                            self.downloaded()
                            downloaded += [True]
                            ver_dld = True
                            break
                    elif not self.type == "show" and debrid_uncached:
                        if debrid.download(self, stream=False, force=force):
                            self.downloaded()
                            debrid.downloading += [
                                self.query() + " [" + self.version.name + "]"
                            ]
                            downloaded += [True]
                            ver_dld = True
                            break
                # if a release was sent (cached or uncached), treat the version as successful and stop
                if ver_dld:
                    if self.type == "season":
                        key = self.pack_key()
                        if key:
                            media.pack_in_progress[key] = time.time()
                            ui_print(
                                "[SEASON_IN_PROGRESS] Pack sent; waiting for Plex to index",
                                ui_settings.debug,
                            )
                    # Trigger subtitle download job (best-effort)
                    if subtitle_runner:
                        try:
                            ui_print(f"[subs trigger] enqueue subs for '{self.query()}'", debug=ui_settings.debug)
                            subtitle_runner.enqueue(self)
                        except Exception as e:
                            ui_print(f"[subs trigger] error: {e}", debug=ui_settings.debug)
                    return True, False
            if not ver_dld:
                downloaded += [False]
        return True in downloaded, (False in downloaded or len(downloaded) == 0)

    def files(self):
        files = []
        if self.type == "movie":
            files = ["(mkv|mp4)"]
        elif self.type == "show":
            for season in self.Seasons:
                for episode in season.Episodes:
                    files += episode.files()
        elif self.type == "season":
            for episode in self.Episodes:
                files += episode.files()
        elif self.type == "episode":
            if self.isanime():
                files += [
                    "[^A-DF-Z0-9\[]0*("
                    + self.anime_count
                    + "|"
                    + str(self.index)
                    + ")(?![A-Z0-9]|\])"
                ]
            else:
                files += [
                    "S"
                    + str("{:02d}".format(self.parentIndex))
                    + "E"
                    + str("{:02d}".format(self.index))
                    + ""
                ]
        return files

    def bitrate(self):
        import content.services.plex as plex
        import content.services.trakt as trakt

        try:
            duration = 0
            if (
                self.watchlist == trakt.watchlist and len(plex.users) > 0
            ) or self.watchlist == plex.watchlist:
                if self.watchlist == trakt.watchlist:
                    self.match("content.services.plex")
                duration = (
                    0
                    if not hasattr(self, "duration") or self.duration == None
                    else self.duration
                )
            for release in self.Releases:
                release.bitrate = (
                    (release.size * 10000) / (duration / 1000) if duration > 0 else 0
                )
            ui_print(
                "set release bitrate using total "
                + self.type
                + " duration: "
                + "{:02d}h:{:02d}m".format(
                    int(duration / 1000) // 3600, (int(duration / 1000) % 3600) // 60
                ),
                ui_settings.debug,
            )
        except:
            ui_print("error: couldnt set release bitrate", ui_settings.debug)

    def season_pack(self, releases):
        ui_print(f"[SEASON_PACK_CHECK] Entering season_pack() with {len(self.Releases)} self.Releases and {len(releases)} parent releases")
        ui_print(f"[SEASON_PACK_CHECK] Episodes to check: {len(self.Episodes)}")

        season_releases = -1
        episode_releases = [-2] * len(self.Episodes)

        # Log self.Releases analysis
        cached_count = 0
        for release in self.Releases:  # find the highest resolution of all the cached releases
            if len(release.cached) + len(release.maybe_cached) > 0:
                cached_count += 1
                ui_print(f"[SEASON_PACK_CHECK] Cached release: {release.title[:80]} | Resolution: {release.resolution}")
                if int(release.resolution) > season_releases:
                    season_releases = int(release.resolution)

        ui_print(f"[SEASON_PACK_CHECK] Found {cached_count} cached releases in self.Releases")
        ui_print(f"[SEASON_PACK_CHECK] Highest season resolution: {season_releases}")

        for i, episode in enumerate(
            self.Episodes
        ):  # find the highest resolution for each episode
            ep_match = regex.compile(episode.deviation(), regex.IGNORECASE)
            episode_matches = 0
            for release in releases:
                if (
                    len(release.cached) + len(release.maybe_cached) > 0
                    and int(release.resolution) >= season_releases
                    and int(release.resolution) > episode_releases[i]
                    and ep_match.match(release.title)
                ):
                    episode_matches += 1
                    episode_releases[i] = int(release.resolution)
                    ui_print(f"[SEASON_PACK_CHECK] Episode {episode.index} matched: {release.title[:60]} | Resolution: {release.resolution}")
            ui_print(f"[SEASON_PACK_CHECK] Episode {episode.index}: {episode_matches} matches, best resolution: {episode_releases[i]}")

        lowest = 2160
        for (
            quality
        ) in episode_releases:  # find the lowest resolution of all the episodes
            if quality < lowest:
                lowest = quality

        ui_print(f"[SEASON_PACK_CHECK] Episode resolutions: {episode_releases}")
        ui_print(f"[SEASON_PACK_CHECK] Lowest episode resolution: {lowest}")
        ui_print(f"[SEASON_PACK_CHECK] Season pack resolution: {season_releases}")

        # If no cached episode release available for all episodes, or the quality is equal or lower to the cached season packs return True
        if lowest <= season_releases:
            ui_print(f"[SEASON_PACK_CHECK] DECISION: Use season pack (lowest={lowest} <= season={season_releases})")
            return True
        ui_print(f"[SEASON_PACK_CHECK] DECISION: Don't use season pack (lowest={lowest} > season={season_releases})")
        return False


def download(cls, library, parentReleases, result, index):
    result[index] = cls.download(library=library, parentReleases=parentReleases)
