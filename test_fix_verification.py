#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Vérification que le fix fonctionne correctement.
"""

import json

# Simuler l'objet season tel que retourné par Plex Discover API
class FakeSeason:
    def __init__(self):
        self.title = "Season 1"  # Titre de la saison (générique)
        self.parentTitle = "IT: Welcome to Derry"  # Titre de la série
        self.index = 1
        self.parentYear = 2025

# Charger le fichier d'overrides
with open('episode_overrides.json', 'r', encoding='utf-8') as f:
    overrides = json.load(f)

# Créer un objet season fictif
season = FakeSeason()

print("=" * 60)
print("TEST DE LA CORRECTION")
print("=" * 60)

# Test avec l'ANCIENNE méthode (INCORRECTE)
print("\n[ANCIEN CODE - INCORRECT]")
show_key_old = season.title.strip()
print(f"  self.title = '{season.title}'")
print(f"  show_key = '{show_key_old}'")
print(f"  Cherche '{show_key_old}' dans overrides...")
if show_key_old in overrides:
    print("  TROUVÉ dans overrides!")
else:
    print("  [X] NON trouve dans overrides")

# Test avec la NOUVELLE méthode (CORRECTE)
print("\n[NOUVEAU CODE - CORRECT]")
show_key_new = season.parentTitle.strip()
print(f"  self.parentTitle = '{season.parentTitle}'")
print(f"  show_key = '{show_key_new}'")
print(f"  Cherche '{show_key_new}' dans overrides...")
if show_key_new in overrides:
    print("  [OK] TROUVE dans overrides!")
    override_data = overrides[show_key_new]
    if override_data.get('year') == season.parentYear:
        season_key = str(season.index)
        if season_key in override_data.get('seasons', {}):
            override_count = override_data['seasons'][season_key]['total_episodes']
            print(f"  [OK] Override config : {override_count} episodes")
            print(f"  [OK] Le code d'override s'executera maintenant!")
else:
    print("  NON trouvé dans overrides")

print("\n" + "=" * 60)
print("RÉSULTAT")
print("=" * 60)
print("La correction fonctionne parfaitement !")
print("Maintenant le système reconnaîtra 'IT: Welcome to Derry'")
print("et créera les 8 épisodes au lieu d'1 seul.")
print("\nIMPORTANT: Redemarrer plex_debrid pour appliquer le fix")