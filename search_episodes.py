import re

# Lire le fichier binaire
with open('plex_metadata.pkl', 'rb') as f:
    content = f.read()

print("="*80)
print("EPISODES IT: WELCOME TO DERRY")
print("="*80)

# Chercher les métadonnées de la saison IT
# On cherche autour de "IT: Welcome to Derry" et "Season 1"
for match in re.finditer(b'IT.*?Welcome.*?Derry.*?Season 1', content, re.IGNORECASE | re.DOTALL):
    pos = match.start()
    # Regarder 2000 bytes après pour voir les métadonnées de saison
    context = content[pos:pos+2000]
    decoded = context.decode('utf-8', errors='ignore')

    # Chercher des patterns comme "leafCount", "childCount", "viewedLeafCount"
    # Ces champs indiquent combien d'épisodes Plex pense qu'il y a
    print(f"\nPosition {pos}:")
    print(decoded[:500])
    print("\n" + "."*80)

# Chercher spécifiquement "leafCount" ou "childCount" près de "IT: Welcome"
print("\n" + "="*80)
print("RECHERCHE leafCount/childCount POUR IT")
print("="*80)

# Trouver "IT: Welcome to Derry" puis chercher leafCount dans les 500 bytes autour
it_positions = [m.start() for m in re.finditer(b'IT.*?Welcome.*?Derry', content, re.IGNORECASE)]
print(f"Trouve {len(it_positions)} occurrences de 'IT: Welcome to Derry'")

for pos in it_positions[:5]:  # Limite à 5
    context_before = content[max(0, pos-300):pos]
    context_after = content[pos:pos+300]
    full_context = context_before + b"[[[IT HERE]]]" + context_after

    decoded = full_context.decode('utf-8', errors='ignore')

    if 'leaf' in decoded.lower() or 'child' in decoded.lower():
        print(f"\nPosition {pos} - TROUVE DES METADONNEES:")
        print(decoded)
        print("-"*80)

# Faire pareil pour Spartacus
print("\n" + "="*80)
print("RECHERCHE leafCount/childCount POUR SPARTACUS")
print("="*80)

spartacus_positions = [m.start() for m in re.finditer(b'Spartacus.*?House.*?Ashur', content, re.IGNORECASE)]
print(f"Trouve {len(spartacus_positions)} occurrences de 'Spartacus: House of Ashur'")

for pos in spartacus_positions[:3]:  # Limite à 3
    context_before = content[max(0, pos-300):pos]
    context_after = content[pos:pos+300]
    full_context = context_before + b"[[[SPARTACUS HERE]]]" + context_after

    decoded = full_context.decode('utf-8', errors='ignore')

    if 'leaf' in decoded.lower() or 'child' in decoded.lower():
        print(f"\nPosition {pos} - TROUVE DES METADONNEES:")
        print(decoded)
        print("-"*80)
