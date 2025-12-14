#!/usr/bin/env python3
"""Test pour comprendre pourquoi les patterns ne matchent pas"""

import re as regex

# Le pattern actuel de vos logs
pattern = r"(.*?)((plur1bus):?.)(series.|[^A-Za-z0-9]+)?(\(?2025\)?.)?(season.1[^0-9]|season.01[^0-9]|S01[^0-9]|S01E[0-9]+|1x[0-9]+)"

# Quelques releases de vos logs
releases = [
    "Pluribus.S01E01.Noi.siamo.noi.ITA.ENG.2160p.ATVP.WEB-DL.DDP5.1.Atmos.DV.HDR.H.265-MeM.GP.mkv",
    "Pluribus.S01E01-02.2160p.ATVP.WEB-DL.DDP5.1.Atmos.ITA-ENG.DV.HDR.H.265-G66",
    "Pluribus.1x01.Noi.Siamo.Noi.2160p.WEB-DL.H265.HDR10+.Dolby.Vision.Ita.Eng.AC3.5.1.Multisub.iDN_CreW",
]

print("=" * 80)
print("TEST: Pourquoi le pattern ne matche pas ?")
print("=" * 80)
print()
print("Pattern utilisé:")
print(pattern)
print()
print("=" * 80)
print()

for release in releases:
    print(f"Release: {release[:70]}...")
    match = regex.match(pattern, release, regex.I)
    if match:
        print(f"  [OK] MATCHE !")
        print(f"  Groups: {match.groups()}")
    else:
        print(f"  [XX] NE MATCHE PAS")

        # Test avec "pluribus" au lieu de "plur1bus"
        pattern_fixed = r"(.*?)((pluribus):?.)(series.|[^A-Za-z0-9]+)?(\(?2025\)?.)?(season.1[^0-9]|season.01[^0-9]|S01[^0-9]|S01E[0-9]+|1x[0-9]+)"
        match_fixed = regex.match(pattern_fixed, release, regex.I)
        if match_fixed:
            print(f"  [!!] MATCHERAIT avec 'pluribus' (sans le 1)")
        else:
            print(f"  [!!] Ne matcherait toujours pas")
    print()

print("=" * 80)
print()
print("PROBLÈME IDENTIFIÉ:")
print("  Le pattern cherche 'plur1bus' (avec le chiffre 1)")
print("  Mais les releases contiennent 'Pluribus' (sans chiffre)")
print()
print("  'PLUR1BUS' = Slug/ID interne de Plex")
print("  'Pluribus' = Titre réel de la série")
print()
