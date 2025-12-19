#!/usr/bin/env python3
"""
Script de test pour valider les optimisations du système de sous-titres.
Teste spécifiquement l'approche en 3 niveaux pour la recherche dans Plex.
"""

import os
import sys
import argparse
import time

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plex_subs_on_add_optimized import (
    extract_title_from_filepath,
    find_item_tier1_recently_added,
    find_item_tier2_search,
    find_item_tier3_full_scan,
    find_item_by_exact_file_optimized,
    plex_get
)

def test_title_extraction():
    """Test l'extraction de titre depuis les noms de fichiers"""
    print("\n=== TEST: Extraction de titre ===")
    print("-" * 50)

    test_cases = [
        ("Batman.Begins.2005.2160p.UHD.BDRemux.DTS-HD.MA.5.1.P8.HYBRID.DoVi-DVT.mkv", "Batman Begins"),
        ("The.Dark.Knight.2008.1080p.BluRay.x264.mkv", "The Dark Knight"),
        ("Inception.2010.4K.UHD.HDR.mkv", "Inception"),
        ("Spider-Man.No.Way.Home.2021.WEB-DL.mkv", "Spider Man No Way Home"),
        ("Dune.Part.Two.2024.2160p.mkv", "Dune Part Two"),
    ]

    for filename, expected in test_cases:
        result = extract_title_from_filepath(filename)
        status = "✓" if expected in result else "✗"
        print(f"{status} Input: {filename}")
        print(f"  Expected: {expected}")
        print(f"  Got: {result}")
        print()

def test_plex_connection(baseurl: str, token: str):
    """Test la connexion à Plex"""
    print("\n=== TEST: Connexion Plex ===")
    print("-" * 50)

    try:
        r = plex_get(baseurl, token, "/")
        if r.status_code == 200:
            print("✓ Connexion Plex OK")
            return True
        else:
            print(f"✗ Erreur Plex: HTTP {r.status_code}")
            return False
    except Exception as e:
        print(f"✗ Erreur de connexion: {e}")
        return False

def test_tier_performance(baseurl: str, token: str, section: int, test_file: str = None):
    """Test les performances de chaque niveau"""
    print("\n=== TEST: Performance des 3 niveaux ===")
    print("-" * 50)

    if not test_file:
        print("⚠ Aucun fichier de test spécifié, utilisation d'un fichier bidon")
        test_file = r"Z:\Test\Movie\Test.Movie.2024.mkv"

    print(f"Fichier de test: {test_file}")
    print()

    # Test TIER-1
    print("[TIER-1] Test /recentlyAdded...")
    start = time.time()
    result = find_item_tier1_recently_added(baseurl, token, section, test_file, timeout_s=10)
    elapsed = time.time() - start

    if result:
        print(f"✓ TIER-1: Trouvé en {elapsed:.2f}s")
        print(f"  Title: {result[2]}")
        print(f"  RatingKey: {result[0]}")
    else:
        print(f"✗ TIER-1: Non trouvé après {elapsed:.2f}s")
    print()

    # Test TIER-2
    print("[TIER-2] Test /search...")
    start = time.time()
    result = find_item_tier2_search(baseurl, token, section, test_file, timeout_s=10)
    elapsed = time.time() - start

    if result:
        print(f"✓ TIER-2: Trouvé en {elapsed:.2f}s")
        print(f"  Title: {result[2]}")
        print(f"  RatingKey: {result[0]}")
    else:
        print(f"✗ TIER-2: Non trouvé après {elapsed:.2f}s")
    print()

    # Test TIER-3 (optionnel car plus lent)
    print("[TIER-3] Test full scan (optionnel, appuyez sur Entrée pour skipper)...")
    response = input("Tester TIER-3 (peut prendre 30-60s)? [y/N]: ")
    if response.lower() == 'y':
        start = time.time()
        try:
            result = find_item_tier3_full_scan(baseurl, token, section, test_file,
                                              page_size=500, max_pages=5, timeout_s=30)
            elapsed = time.time() - start
            print(f"✓ TIER-3: Trouvé en {elapsed:.2f}s")
            print(f"  Title: {result[2]}")
            print(f"  RatingKey: {result[0]}")
        except Exception as e:
            elapsed = time.time() - start
            print(f"✗ TIER-3: {e} après {elapsed:.2f}s")

def test_recently_added_endpoint(baseurl: str, token: str, section: int):
    """Test l'endpoint /recentlyAdded pour voir les derniers ajouts"""
    print("\n=== TEST: Endpoint /recentlyAdded ===")
    print("-" * 50)

    try:
        params = {
            "X-Plex-Container-Start": 0,
            "X-Plex-Container-Size": 10,
        }
        r = plex_get(baseurl, token, f"/library/sections/{section}/recentlyAdded", params=params)
        r.raise_for_status()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.text)

        videos = root.findall(".//Video")
        print(f"✓ Found {len(videos)} recent items:")
        print()

        for i, video in enumerate(videos[:5], 1):
            title = video.attrib.get("title", "Unknown")
            year = video.attrib.get("year", "")
            added = video.attrib.get("addedAt", "")

            # Get file path
            file_path = "N/A"
            for part in video.findall(".//Part"):
                file_path = part.attrib.get("file", "N/A")
                break

            print(f"  {i}. {title} ({year})")
            print(f"     File: {file_path}")
            print()

    except Exception as e:
        print(f"✗ Erreur: {e}")

def main():
    parser = argparse.ArgumentParser(description="Test des optimisations du système de sous-titres")
    parser.add_argument("--baseurl", default="http://127.0.0.1:32400", help="URL Plex")
    parser.add_argument("--token", default="V3f8y4xzv2VEo6xzcSXu", help="Token Plex")
    parser.add_argument("--section", type=int, default=1, help="Section ID Plex")
    parser.add_argument("--file", help="Chemin complet d'un fichier à tester")
    parser.add_argument("--quick", action="store_true", help="Test rapide (skip certains tests)")

    args = parser.parse_args()

    print("=" * 60)
    print("TEST DES OPTIMISATIONS DU SYSTÈME DE SOUS-TITRES")
    print("=" * 60)

    # Test title extraction
    if not args.quick:
        test_title_extraction()

    # Test Plex connection
    if test_plex_connection(args.baseurl, args.token):
        # Show recently added items
        test_recently_added_endpoint(args.baseurl, args.token, args.section)

        # Test tier performance if a file is specified
        if args.file:
            test_tier_performance(args.baseurl, args.token, args.section, args.file)
        else:
            print("\n💡 Conseil: Spécifiez un fichier avec --file pour tester les performances")
            print("   Exemple: --file \"Z:\\Batman.Begins.2005.2160p.UHD.BDRemux.mkv\\Batman.Begins.2005.2160p.UHD.BDRemux.mkv\"")

    print("\n" + "=" * 60)
    print("FIN DES TESTS")
    print("=" * 60)

if __name__ == "__main__":
    main()