import re

# Lire le fichier binaire
with open('plex_metadata.pkl', 'rb') as f:
    content = f.read()

print("="*80)
print("RECHERCHE IT: WELCOME TO DERRY")
print("="*80)

# Chercher toutes les occurrences de "IT" ou "Welcome" ou "Derry"
it_positions = []
for match in re.finditer(b'IT.*?Welcome.*?Derry|Welcome.*?Derry', content, re.IGNORECASE):
    pos = match.start()
    it_positions.append(pos)
    print(f"\nPosition {pos}:")
    # Afficher 200 bytes avant et après
    start = max(0, pos - 200)
    end = min(len(content), pos + 300)
    context = content[start:end]
    # Essayer de décoder en ignorant les erreurs
    try:
        decoded = context.decode('utf-8', errors='ignore')
        print(decoded)
    except:
        print(context)
    print("-" * 80)

if not it_positions:
    print("Pas trouve dans le format 'IT Welcome Derry', recherche 'Derry' seul...")
    for match in re.finditer(b'Derry', content):
        pos = match.start()
        print(f"\nPosition {pos}:")
        start = max(0, pos - 200)
        end = min(len(content), pos + 300)
        context = content[start:end]
        try:
            decoded = context.decode('utf-8', errors='ignore')
            print(decoded)
        except:
            print(context)
        print("-" * 80)
        if len([m for m in re.finditer(b'Derry', content)]) > 5:
            print("\nTrop d'occurrences, arret apres 5...")
            break

print("\n" + "="*80)
print("RECHERCHE SPARTACUS")
print("="*80)

for match in re.finditer(b'Spartacus', content):
    pos = match.start()
    print(f"\nPosition {pos}:")
    start = max(0, pos - 200)
    end = min(len(content), pos + 300)
    context = content[start:end]
    try:
        decoded = context.decode('utf-8', errors='ignore')
        print(decoded)
    except:
        print(context)
    print("-" * 80)

    spartacus_count = len([m for m in re.finditer(b'Spartacus', content)])
    if spartacus_count > 5:
        print(f"\nTrop d'occurrences ({spartacus_count}), arret apres 5...")
        break

print("\n" + "="*80)
print("RECHERCHE DE PATTERNS INTERESSANTS")
print("="*80)

# Chercher des patterns comme "Season 1" ou "episode" ou "episodes"
for pattern in [b'Season 1', b'episode', b'episodes', b'duration']:
    matches = list(re.finditer(pattern, content, re.IGNORECASE))
    print(f"\nPattern '{pattern.decode()}': {len(matches)} occurrences")
