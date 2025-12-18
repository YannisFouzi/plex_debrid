#!/usr/bin/env python3
"""Test complet du système de sous-titres avec tous les logs"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Simule le contexte d'exécution
class MockSettings:
    debug = "true"

# Mock ui_settings
from ui import ui_print
ui_print.ui_settings = MockSettings()

from subtitle_runner import _find_media_path, _run_subs

def test_complete_flow():
    print("\n" + "="*60)
    print("TEST COMPLET DU SYSTEME DE SOUS-TITRES")
    print("="*60 + "\n")

    # 1. Test de recherche de fichier
    print("[TEST] Recherche du fichier Batman Begins...")
    path = _find_media_path("Z:\\", "batman.begins.2005", timeout=10)

    if path:
        print(f"[OK] Fichier trouve: {path}\n")

        # 2. Test du lancement du script de sous-titres
        print("[TEST] Lancement du script de sous-titres...")
        _run_subs(path)

    else:
        print("[ERREUR] Fichier non trouve\n")

        # Liste les fichiers disponibles pour debug
        print("[DEBUG] Fichiers disponibles sur Z:\\:")
        try:
            for item in os.listdir("Z:\\"):
                print(f"  - {item}")
        except Exception as e:
            print(f"  Erreur: {e}")

if __name__ == "__main__":
    test_complete_flow()