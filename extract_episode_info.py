import re

# Lire le fichier binaire
with open('plex_metadata.pkl', 'rb') as f:
    content = f.read()

# Ecrire dans un fichier UTF-8
with open('episode_metadata.txt', 'w', encoding='utf-8', errors='ignore') as out:
    out.write("="*80 + "\n")
    out.write("EPISODES IT: WELCOME TO DERRY\n")
    out.write("="*80 + "\n\n")

    # Chercher "Season 1" autour de IT
    for match in re.finditer(b'it-welcome-to-derry.*?Season 1', content, re.IGNORECASE | re.DOTALL):
        pos = match.start()
        context = content[max(0, pos-400):pos+600]
        decoded = context.decode('utf-8', errors='ignore')
        out.write(f"Position {pos}:\n")
        out.write(decoded)
        out.write("\n" + "."*80 + "\n\n")

    out.write("\n" + "="*80 + "\n")
    out.write("RECHERCHE NOMBRE TOTAL EPISODES IT\n")
    out.write("="*80 + "\n\n")

    # Chercher les IDs de metadata IT
    it_meta_ids = []
    for match in re.finditer(b'/library/metadata/(\d+).*?it-welcome-to-derry', content, re.IGNORECASE | re.DOTALL):
        meta_id = match.group(1).decode('ascii')
        if meta_id not in it_meta_ids:
            it_meta_ids.append(meta_id)

    out.write(f"IDs de metadata IT trouves: {it_meta_ids}\n\n")

    # Pour chaque ID, chercher les infos
    for meta_id in it_meta_ids:
        pattern = f'/library/metadata/{meta_id}'.encode('ascii')
        out.write(f"\n--- Metadata ID {meta_id} ---\n")

        for match in re.finditer(pattern, content):
            pos = match.start()
            context = content[max(0, pos-200):pos+400]
            decoded = context.decode('utf-8', errors='ignore')
            out.write(f"Position {pos}:\n{decoded}\n")
            out.write("."*40 + "\n")

    out.write("\n" + "="*80 + "\n")
    out.write("EPISODES SPARTACUS\n")
    out.write("="*80 + "\n\n")

    # Pareil pour Spartacus
    spartacus_meta_ids = []
    for match in re.finditer(b'/library/metadata/(\d+).*?spartacus-house-of-ashur', content, re.IGNORECASE | re.DOTALL):
        meta_id = match.group(1).decode('ascii')
        if meta_id not in spartacus_meta_ids:
            spartacus_meta_ids.append(meta_id)

    out.write(f"IDs de metadata Spartacus trouves: {spartacus_meta_ids}\n\n")

    # Limiter à 5 IDs pour Spartacus
    for meta_id in spartacus_meta_ids[:5]:
        pattern = f'/library/metadata/{meta_id}'.encode('ascii')
        out.write(f"\n--- Metadata ID {meta_id} ---\n")

        count = 0
        for match in re.finditer(pattern, content):
            if count >= 3:  # Max 3 occurrences par ID
                break
            pos = match.start()
            context = content[max(0, pos-200):pos+400]
            decoded = context.decode('utf-8', errors='ignore')
            out.write(f"Position {pos}:\n{decoded}\n")
            out.write("."*40 + "\n")
            count += 1

print("Fichier episode_metadata.txt cree avec succes")
