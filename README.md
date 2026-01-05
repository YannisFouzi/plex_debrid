# plex_debrid

Automatisation de téléchargement via services debrid à partir de watchlists (Plex/Trakt/Overseerr), avec scrapers multi-sources, règles de qualité et intégration bibliothèque.

> Fork personnalisé de [itsToggle/plex_debrid](https://github.com/itsToggle/plex_debrid). Ce dépôt ajoute des correctifs et optimisations (politiques 4K, cache TMDb, overrides d'épisodes Plex, etc.).

## Sommaire
- [Aperçu](#apercu)
- [Fonctionnement](#fonctionnement)
- [Fonctionnalités](#fonctionnalites)
- [Services supportés](#services-supportes)
- [Prérequis](#prerequis)
- [Installation](#installation)
- [Démarrage rapide](#demarrage-rapide)
- [Mode service](#mode-service)
- [Configuration détaillée](#configuration-detaillee)
- [Système de versions](#systeme-de-versions)
- [Politique 4k et upgrades](#politique-4k-et-upgrades)
- [Fichiers générés et caches](#fichiers-generes-et-caches)
- [Overrides d'épisodes Plex](#overrides-depisodes-plex)
- [Sous-titres optionnel](#sous-titres-optionnel)
- [Docker](#docker)
- [Dépannage](#depannage)
- [Sécurité](#securite)
- [Crédits](#credits)

## Aperçu
plex_debrid est un script Python en mode CLI qui surveille vos watchlists et demandes, cherche automatiquement des releases via plusieurs scrapers, vérifie la disponibilité sur vos services debrid, puis déclenche le téléchargement et met à jour votre bibliothèque (Plex/Jellyfin/Trakt).

Le tout est piloté par un système de "versions" (profils de qualité) et de règles de filtrage, pour choisir automatiquement les releases les plus pertinentes selon vos préférences.

## Fonctionnement
1. Lecture des watchlists (Plex, Trakt) et des requêtes Overseerr.
2. Vérification de votre bibliothèque locale (Plex/Trakt/Jellyfin) pour éviter les doublons.
3. Scraping des sources configurées (Prowlarr, Jackett, Torrentio, etc.).
4. Contrôle du cache sur vos services debrid.
5. Ajout du torrent/flux sur le service debrid choisi.
6. Rafraîchissement des bibliothèques (Plex/Jellyfin), mise à jour Trakt, marquage Overseerr.
7. Optionnel: auto-remove des watchlists et gestion d'ignore lists.

## Fonctionnalités
- Multi-sources de contenu: Plex, Trakt, Overseerr.
- Multi-scrapers: Prowlarr, Jackett, Torrentio, Orionoid, Mediafusion, Comet, Zilean, Torbox, etc.
- Multi-debrid: Real-Debrid, AllDebrid, Premiumize, Debrid-Link, Put.io, Torbox.
- Système de versions (profils de qualité) avec triggers et règles avancées.
- Politique 4K (fenêtre "4K only" + file d'upgrade).
- Gestion des packs de saisons et fallback épisodes.
- Cache TMDb pour statut des séries (ended/ongoing) + titres originaux.
- Overrides d'épisodes Plex pour corriger les comptes erronés.
- Labels Plex automatiques (tag utilisateur + version).
- Logs optionnels dans `plex_debrid.log`.
- Mode service (non interactif) pour run en continu.

## Services supportés

### Sources de contenu
- Plex (watchlist)
- Trakt (watchlists, collections, listes publiques/privées)
- Overseerr (requêtes approuvées)

### Bibliothèque / Mise à jour
- Plex Library (collection)
- Trakt Collection (collection)
- Jellyfin Library (collection, partiel/expérimental)
- Plex Libraries (refresh)
- Plex Labels (tags sur les items téléchargés)
- Trakt Collection (refresh)
- Jellyfin Libraries (refresh)
- Overseerr Requests (marquer une requête comme "available")

### Ignore lists
- Plex Discover Watch Status
- Trakt Watch Status
- Local Ignore List (fichier texte)

### Scrapers
- prowlarr
- jackett
- torrentio
- orionoid
- nyaa
- rarbg / rarbgv2
- 1337x
- yts
- eztv
- thepiratebay
- torrentgalaxy
- limetorrents
- magnetDL
- zilean (DMM hashes)
- torbox
- mediafusion
- comet

### Debrid
- Real Debrid (RD)
- All Debrid (AD)
- Premiumize (PM)
- Debrid Link (DL)
- Put.io (PUT)
- Torbox (TB)

## Prérequis
- Python 3.x
- `pip` pour installer les dépendances
- Un compte debrid (au moins un)
- Un service de contenu (Plex/Trakt/Overseerr)
- Optionnel: Prowlarr/Jackett, TMDb API, Orionoid, Mediafusion/Comet, etc.
- Optionnel sous-titres: `ffprobe` (ffmpeg) et `plexapi`

## Installation

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\Activate.ps1
# Linux/macOS
# source .venv/bin/activate

pip install -r requirements.txt
```

### Trakt (obligatoire si Trakt actif)
Le script attend `CLIENT_ID` et `CLIENT_SECRET` via variables d'environnement ou fichier `.env`:

```env
CLIENT_ID=your_trakt_client_id
CLIENT_SECRET=your_trakt_client_secret
```

## Démarrage rapide
1. Lancez le script: `python main.py`
2. L'assistant d'initialisation crée `settings.json` et demande:
   - Service(s) de contenu
   - Service(s) debrid
   - Scrapers actifs
   - Bibliothèque de référence (Plex/Trakt/Jellyfin)
3. Le mode `Run` démarre la boucle de surveillance.

Astuce: utilisez `python main.py --config-dir config` pour isoler vos fichiers de configuration.

## Mode service
- `python main.py -service` lance le script sans interaction utilisateur.
- Combinable avec `Show Menu on Startup = false` pour un run headless.
- Relancez sans `-service` pour revenir à une exécution interactive.

## Configuration détaillée

### Content Services
- `Content Services` (obligatoire): choisir Plex/Trakt/Overseerr.
- `Plex users`: nom + token (`https://plex.tv/devices.xml`).
- `Plex auto remove`: movie/show/both/none.
- `Trakt users`: auth OAuth device code.
- `Trakt lists`: watchlists/collections/listes publiques/privées.
- `Trakt auto remove`: movie/show/both/none.
- `Trakt early movie releases`: active la recherche d'early releases.
- `Overseerr users`: users à surveiller (ou `all`).
- `Overseerr API Key` + `Overseerr Base URL`.
- `TMDb API Key` (optionnel): statut des séries + titre original.

### Library Services
- `Library collection service` (obligatoire):
  - `Plex Library`, `Trakt Collection`, ou `Jellyfin Library`.
- `Library update services` (obligatoire):
  - `Plex Libraries`, `Plex Labels`, `Trakt Collection`,
    `Jellyfin Libraries`, `Overseerr Requests`.
- `Library ignore services` (obligatoire):
  - `Plex Discover Watch Status`, `Trakt Watch Status`, `Local Ignore List`.
- `Trakt library user` / `Trakt refresh user`.
- `Plex library refresh`: sections à rafraîchir.
- `Plex library partial scan`: true/false.
- `Plex library refresh delay`: délai en secondes.
- `Plex server address`: ex. `http://plex:32400`.
- `Plex library check`: sections à utiliser pour éviter les doublons.
- `Plex ignore user` / `Trakt ignore user`.
- `Local ignore list path`: chemin contenant `ignored.txt`.
- `Jellyfin API Key` + `Jellyfin server address`.

### Scraper Settings
- `Sources`: scrapers actifs.
- `Versions`: profils de qualité (voir section suivante).
- `Special character renaming`: règles de nettoyage de titre.
- `Rarbg API Key`: valeur par défaut (auto refresh).
- `Jackett Base URL` + `Jackett API Key`.
- `Jackett resolver timeout` + `Jackett indexer filter`.
- `Prowlarr Base URL` + `Prowlarr API Key`.
- `Orionoid API Key` + paramètres.
- `Nyaa parameters` + `Nyaa sleep time` + `Nyaa proxy`.
- `Torrentio Scraper Parameters` (manifest) + `Torrentio Base URL`.
- `Zilean Base URL`.
- `Mediafusion Base URL` + `Mediafusion API Key` + timeouts + rate limit + manifest.
- `Comet Request Timeout` + rate limit + manifest.

### Debrid Services
- `Debrid Services` (obligatoire): choisir les services actifs.
- `Tracker specific Debrid Services`: regex de tracker -> code service (RD/PM/AD/PUT/DL/TB).
- API keys pour chaque service (Real Debrid, All Debrid, Premiumize, Debrid Link, Put.io, Torbox).

### Subtitles (config)
- `Subs media root`: racine des médias.
- `Subs script path`: chemin vers `subtitles/plex_subs_on_add.py`.
- `Subs Plex token` + `Subs Plex section`.
- `Subs OpenSubtitles API key/user/pass`.

### UI Settings
- `Show Menu on Startup`: true/false.
- `Debug printing`: true/false.
- `Log to file`: true/false.
- `Watchlist loop interval (sec)`: intervalle de vérification.
- `version`: usage interne (compat).

## Système de versions
Une "version" est un profil de qualité (ex. "1080p SDR") composé de:
- Triggers (quand s'applique la version)
- Règles (comment trier/filtrer les releases)
- Langue de scraping

Triggers disponibles:
- `retries` (<=, >=)
- `airtime offset` (délai avant de scraper un épisode)
- `year` (==, <=, >=)
- `media type` (all/movies/shows)
- `title` (==/include/exclude)
- `user` (==/include/exclude)
- `genre` (==/include/exclude)
- `scraper sources` (==/include/exclude)
- `scraping adjustment` (airdate, prefix/suffix)

Règles disponibles:
- `cache status` (cached requis/préféré)
- `resolution`
- `bitrate`
- `size`
- `seeders`
- `title` (include/exclude)
- `source` (include/exclude)
- `file names` (include/exclude)
- `file sizes` (highest/lowest)

Le profil par défaut est `1080p SDR` (voir `releases/__init__.py`). Vous pouvez créer vos propres versions via le menu `Options > Settings > Scraper Settings > Versions`.

## Politique 4k et upgrades
Le module `content/release_policy.py` applique:
- Une fenêtre "4K only" de 48h pour les contenus récents quand une release >= 1080p est détectée.
- Une file d'upgrade: si une version 1080p est téléchargée, le script re-teste périodiquement la disponibilité d'une version 4K (jusqu'à ~2 ans).
- Les médias trop anciens (> 1 an) ignorent la fenêtre 4K.

L'état est stocké dans `release_policy.json` (config dir).

## Fichiers générés et caches
Tous sont stockés dans le `config_dir` (par défaut: dossier courant, ou `--config-dir`).
- `settings.json`: configuration principale.
- `old.json`: sauvegarde lors d'une mise à jour de settings.
- `plex_metadata.pkl`: cache Plex.
- `tmdb_status_cache.json`: cache TMDb (statut séries).
- `release_policy.json`: timers 4K + upgrade queue.
- `plex_debrid.log`: logs (si activé).

## Overrides d'épisodes Plex
Le fichier `episode_overrides.json` corrige les séries où Plex Discover retourne un mauvais nombre d'épisodes.
Format:

```json
{
  "Nom de la Serie": {
    "year": 2025,
    "seasons": {
      "1": {
        "total_episodes": 8,
        "reason": "Plex Discover API retourne totalSize=1"
      }
    }
  }
}
```

Lors du chargement d'une saison, des épisodes "fictifs" sont créés pour atteindre le bon total.

## Sous-titres optionnel
Un script optionnel (`subtitles/plex_subs_on_add.py`) permet d'ajouter automatiquement des sous-titres via OpenSubtitles.

Points clés:
- Nécessite `ffprobe` (ffmpeg) + la lib `plexapi` (`pip install plexapi`).
- Configuration via `settings.json` ou variables `SUBS_*`.
- Le trigger est désactivé par défaut dans `content/classes.py` (voir `subtitle_runner = None`).
  Pour activer: décommentez l'import du runner et supprimez l'override.

Variables utiles:
- `SUBS_MEDIA_ROOT`
- `SUBS_SCRIPT_PATH`
- `SUBS_PLEX_TOKEN`
- `SUBS_PLEX_SECTION`
- `SUBS_PLEX_SECTION_MOVIE`
- `SUBS_PLEX_SECTION_SHOW`
- `SUBS_OST_API_KEY`, `SUBS_OST_USER`, `SUBS_OST_PASS`

## Docker
Exemple simple:

```bash
docker build -t plex-debrid .
docker run -it --rm \
  -v /path/to/config:/config \
  -e CLIENT_ID=... \
  -e CLIENT_SECRET=... \
  plex-debrid \
  python /main.py --config-dir /config
```

Adaptez les variables (Trakt, subtitles, etc.) et montez vos chemins de médias si nécessaire.

## Dépannage
- `401 unauthorized` (Plex/Trakt/Overseerr/Debrid): vérifiez les tokens/API keys.
- Plex library vide: ajoutez au moins un film et une série pour permettre le matching.
- Prowlarr/Jackett timeout: réduisez le nombre d'indexers ou augmentez le timeout.
- Trakt tokens expirés: l'app tente un refresh automatique, sinon re-auth.
- Statut série incorrect: ajoutez une clé TMDb ou corrigez via overrides.
- Releases ignorées: vérifiez vos versions (triggers/règles).

## Sécurité
- Ne versionnez jamais `settings.json` ou vos tokens.
- Utilisez `.env` pour Trakt et des secrets d'environnement pour Docker.
- Gardez vos clés API privées.

## Crédits
- Projet original: [itsToggle/plex_debrid](https://github.com/itsToggle/plex_debrid)
- Contributions et forks communautaires ayant inspiré ce dépôt.
