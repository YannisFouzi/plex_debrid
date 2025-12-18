#!/usr/bin/env python3
# Script de test pour vérifier que les corrections du système de sous-titres fonctionnent

import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from subtitle_runner import _sanitize, _find_media_path

def test_sanitize():
    """Test de la fonction sanitize"""
    print("\n=== Test de la fonction sanitize ===")
    tests = [
        ("Batman.Begins.2005", "batman begins 2005"),
        ("The.Batman.(2022).MULTi.VFF.2160p", "the batman 2022 multi vff 2160p"),
        ("Batman.Begins.2005.2160p.UHD.BDRemux.DTS-HD.MA.5.1.P8.HYBRID.DoVi-DVT.mkv",
         "batman begins 2005 2160p uhd bdremux dts hd ma 5 1 p8 hybrid dovi dvt mkv"),
    ]

    for input_text, expected in tests:
        result = _sanitize(input_text)
        print(f"  Input: {input_text}")
        print(f"  Expected: {expected}")
        print(f"  Got: {result}")
        print(f"  [PASS]" if result == expected else f"  [FAIL]")
        print()

def test_find_media():
    """Test de la fonction de recherche de fichiers"""
    print("\n=== Test de la recherche de fichiers ===")

    # Test avec les fichiers actuels sur Z:\
    test_queries = [
        "batman.begins.2005",
        "batman begins 2005",
        "the.batman.2022",
    ]

    root = r"Z:\\"
    print(f"Recherche dans: {root}")
    print()

    for query in test_queries:
        print(f"Test query: '{query}'")
        print(f"  Sanitized: '{_sanitize(query)}'")

        # Test rapide (timeout court pour le test)
        path = _find_media_path(root, query, timeout=10, poll=2)

        if path:
            print(f"  [TROUVE]: {path}")
        else:
            print(f"  [NON TROUVE]")
        print()

def test_real_files():
    """Verification des fichiers reels sur Z:"""
    print("\n=== Verification des fichiers sur Z:\\ ===")

    try:
        files = []
        root = r"Z:\\"

        # Lister les premiers fichiers vidéo trouvés
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                ext = os.path.splitext(name)[1].lower()
                if ext in [".mkv", ".mp4", ".avi"]:
                    files.append(os.path.join(dirpath, name))
                    if len(files) >= 5:
                        break
            if len(files) >= 5:
                break

        if files:
            print(f"Fichiers vidéo trouvés sur {root}:")
            for f in files:
                print(f"  - {f}")
        else:
            print(f"[ERREUR] Aucun fichier video trouve sur {root}")

    except Exception as e:
        print(f"[ERREUR] Erreur lors de l'acces a Z:\\: {e}")

def main():
    print("=" * 60)
    print("TEST DU SYSTÈME DE SOUS-TITRES AUTOMATIQUES")
    print("=" * 60)

    test_sanitize()
    test_real_files()
    test_find_media()

    print("\n" + "=" * 60)
    print("FIN DES TESTS")
    print("=" * 60)

if __name__ == "__main__":
    main()