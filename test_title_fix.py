#!/usr/bin/env python3
"""Test du fix de génération de variantes de titres"""

import re as regex

# Simule ce que fait le nouveau code
def generate_alternate_titles(plex_title):
    # releases.rename() convertit en lowercase et remplace les espaces/chars spéciaux
    title = plex_title.lower().replace(" ", ".").replace(":", "")

    alternate_titles = []

    # Titre original
    alternate_titles.append(title)

    # Génère variante sans chiffres (nouveau fix!)
    title_no_digits = regex.sub(r'\d+', '', title)
    if title_no_digits != title and title_no_digits:
        alternate_titles.append(title_no_digits)

    return alternate_titles

# Test avec PLUR1BUS
plex_title = "PLUR1BUS"
alternates = generate_alternate_titles(plex_title)

print("=" * 80)
print("TEST DU FIX: Génération de variantes de titres")
print("=" * 80)
print()
print(f"Titre Plex: {plex_title}")
print(f"Alternate titles générés: {alternates}")
print()

# Génère le pattern comme le code le fait
pattern = r"(.*?)((" + "|".join(alternates) + r"):?.)(series.|[^A-Za-z0-9]+)?(\(?2025\)?.)?(S01E[0-9]+)"
print("Pattern généré:")
print(pattern)
print()

# Test avec des releases réelles
releases = [
    "Pluribus.S01E01.Noi.siamo.noi.ITA.ENG.2160p.ATVP.WEB-DL.DDP5.1.Atmos.DV.HDR.H.265-MeM.GP.mkv",
    "Pluribus.S01E06.POU.ITA.ENG.1080p.ATVP.WEB-DL.DDP5.1.Atmos.H.264-MeM.GP.mkv",
]

print("=" * 80)
print("TEST DE MATCHING:")
print("=" * 80)
print()

for release in releases:
    match = regex.match(pattern, release, regex.I)
    if match:
        print(f"[OK] MATCHE: {release[:60]}...")
        print(f"     Matched title: '{match.group(2)}'")
    else:
        print(f"[XX] NE MATCHE PAS: {release[:60]}...")
    print()

print("=" * 80)
print()
if all(regex.match(pattern, r, regex.I) for r in releases):
    print("[OK] FIX FONCTIONNE! Tous les releases matchent maintenant!")
else:
    print("[XX] Fix ne fonctionne pas complètement")
print()
