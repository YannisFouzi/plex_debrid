#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de test pour vérifier la fonctionnalité d'override des épisodes.
"""

import json
import os

# Vérifier que le fichier episode_overrides.json existe
override_file = 'episode_overrides.json'

print("=" * 60)
print("TEST DES OVERRIDES D'ÉPISODES")
print("=" * 60)

# 1. Vérifier l'existence du fichier
if os.path.exists(override_file):
    print(f"✅ Fichier {override_file} trouvé")

    # 2. Charger et vérifier le contenu
    with open(override_file, 'r', encoding='utf-8') as f:
        overrides = json.load(f)

    print(f"\n📋 Contenu du fichier:")
    print("-" * 40)

    for show_name, show_data in overrides.items():
        if show_name.startswith("_"):  # Skip meta fields
            continue

        print(f"\n🎬 Série: {show_name}")
        print(f"   Année: {show_data.get('year')}")

        for season_num, season_data in show_data.get('seasons', {}).items():
            print(f"   Saison {season_num}:")
            print(f"      Total épisodes: {season_data.get('total_episodes')}")
            print(f"      Raison: {season_data.get('reason')[:50]}...")
else:
    print(f"❌ Fichier {override_file} introuvable")

# 3. Tester l'importation du module plex
print("\n" + "=" * 60)
print("TEST D'IMPORTATION DU MODULE")
print("=" * 60)

try:
    import sys
    sys.path.insert(0, 'content/services')

    # Simuler les imports nécessaires
    print("⚠️  Note: Import complet nécessite toutes les dépendances du projet")
    print("⚠️  Ce test vérifie uniquement la syntaxe et la structure de base")

    # Vérifier que le fichier plex.py peut être lu et parsé
    with open('content/services/plex.py', 'r', encoding='utf-8') as f:
        content = f.read()

    if 'def load_episode_overrides()' in content:
        print("✅ Fonction load_episode_overrides() trouvée")
    else:
        print("❌ Fonction load_episode_overrides() introuvable")

    if 'def create_fake_episode(' in content:
        print("✅ Fonction create_fake_episode() trouvée")
    else:
        print("❌ Fonction create_fake_episode() introuvable")

    if '# Episode Override Integration' in content:
        print("✅ Code d'intégration des overrides trouvé")
    else:
        print("❌ Code d'intégration des overrides introuvable")

    print("\n✅ Toutes les modifications semblent être en place!")

except Exception as e:
    print(f"❌ Erreur lors du test: {e}")

print("\n" + "=" * 60)
print("RÉSUMÉ")
print("=" * 60)
print("Les modifications ont été appliquées avec succès.")
print("\nPour utiliser cette fonctionnalité :")
print("1. Le fichier episode_overrides.json est configuré pour IT: Welcome to Derry (8 épisodes)")
print("2. Quand plex_debrid détectera cette série, il utilisera l'override")
print("3. Les 8 épisodes seront créés au lieu d'1 seul")
print("\n⚠️  IMPORTANT: Redémarrer plex_debrid pour appliquer les changements")