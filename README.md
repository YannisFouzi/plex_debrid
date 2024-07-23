# plex-debrid | ElfHosted

## What is this?

This is an [ElfHosted](https://elfhosted.com) maintenance-and-features fork of the deprecated-and-archived https://github.com/itsToggle/plex_debrid with the following improvements:

## How does it work?

<iframe width="560" height="315" src="https://www.youtube.com/embed/JTFoy0jQS4s?si=xdbb1sAkBx-_zmn3" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

## Improvements

* ✅ Support [ElfHosted internal URLs](https://elfhosted.com/how-to/connect-apps/) for [Plex](https://elfhosted.com/app/plex/), [Jellyfin](https://elfhosted.com/app/jellyfin/), [Overseerr](https://elfhosted.com/app/overseerr/), [Jackett](https://elfhosted.com/app/jackett/), [Prowlarr](https://elfhosted.com/app/prowlarr/) by default.
* ✅ Trakt OAuth [fixed](https://github.com/elfhosted/plex_debrid/commit/c678fa1e5974a5c666b2fe70d65228c6fdfb4047) (*by passing your own client ID / secret in ENV vars*).
* ✅ Integrated with [Zilean](https://github.com/iPromKnight/zilean/) for scraping [DebridMediaManager](https://debridmediamanager.com/) (DMM) public hashes, defaults to ElfHosted internal Zilean service.
* ✅ Parametize watchlist loop interval (*defaults to 30s instead of hard-coded 30 min*)
* ✅ Single episode downloads [fixed](https://github.com/elfhosted/plex_debrid/pull/1)

## Thanks to these contributors!

<!-- readme: collaborators,contributors -start -->
<!-- readme: collaborators,contributors -end -->