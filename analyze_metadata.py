import pickle
import json
import sys

# Désactiver les imports pour éviter les erreurs
class FakeModule:
    def __getattr__(self, name):
        return FakeModule()

# Remplacer les modules qui causent des problèmes
sys.modules['content'] = FakeModule()
sys.modules['releases'] = FakeModule()
sys.modules['ui'] = FakeModule()
sys.modules['settings'] = FakeModule()
sys.modules['debrid'] = FakeModule()

# Lire le fichier pickle
try:
    with open('plex_metadata.pkl', 'rb') as f:
        metadata = pickle.load(f)
except Exception as e:
    print(f"Erreur lors du chargement: {e}")
    print("\nEssai de lecture partielle...")

    # Essayer de lire le pickle en mode "unsafe" pour au moins voir la structure
    with open('plex_metadata.pkl', 'rb') as f:
        content = f.read()

    # Chercher les strings dans le binaire
    print("\nRecherche de 'Welcome to Derry' dans le fichier binaire...")
    if b'Welcome to Derry' in content:
        print("✓ Trouvé 'Welcome to Derry'")
        idx = content.find(b'Welcome to Derry')
        print(f"Position: {idx}")
        print(f"Contexte: {content[max(0,idx-100):idx+200]}")

    print("\nRecherche de 'Spartacus' dans le fichier binaire...")
    if b'Spartacus' in content:
        print("✓ Trouvé 'Spartacus'")
        idx = content.find(b'Spartacus')
        print(f"Position: {idx}")
        print(f"Contexte: {content[max(0,idx-100):idx+200]}")

    sys.exit(1)

# Chercher IT et Spartacus
print("=" * 80)
print("RECHERCHE DE IT: WELCOME TO DERRY")
print("=" * 80)

for key, value in metadata.items():
    if isinstance(key, str) and 'welcome' in key.lower() and 'derry' in key.lower():
        print(f"\nClé trouvée: {key}")
        print(f"Type de valeur: {type(value)}")
        if hasattr(value, '__dict__'):
            print(f"Attributs: {value.__dict__}")
        else:
            print(f"Valeur: {value}")

    if isinstance(value, dict):
        for subkey, subvalue in value.items():
            if isinstance(subkey, str) and 'welcome' in subkey.lower() and 'derry' in subkey.lower():
                print(f"\nSous-clé trouvée: {subkey}")
                print(f"Type de valeur: {type(subvalue)}")
                if hasattr(subvalue, '__dict__'):
                    print(f"Attributs: {subvalue.__dict__}")
                else:
                    print(f"Valeur: {subvalue}")

print("\n" + "=" * 80)
print("RECHERCHE DE SPARTACUS")
print("=" * 80)

for key, value in metadata.items():
    if isinstance(key, str) and 'spartacus' in key.lower():
        print(f"\nClé trouvée: {key}")
        print(f"Type de valeur: {type(value)}")
        if hasattr(value, '__dict__'):
            print(f"Attributs: {value.__dict__}")
        else:
            print(f"Valeur: {value}")

    if isinstance(value, dict):
        for subkey, subvalue in value.items():
            if isinstance(subkey, str) and 'spartacus' in subkey.lower():
                print(f"\nSous-clé trouvée: {subkey}")
                print(f"Type de valeur: {type(subvalue)}")
                if hasattr(subvalue, '__dict__'):
                    print(f"Attributs: {subvalue.__dict__}")
                else:
                    print(f"Valeur: {subvalue}")

print("\n" + "=" * 80)
print("STRUCTURE GENERALE DU FICHIER")
print("=" * 80)
print(f"Type racine: {type(metadata)}")
print(f"Nombre de clés racine: {len(metadata) if hasattr(metadata, '__len__') else 'N/A'}")
if isinstance(metadata, dict):
    print(f"Premières clés (max 10): {list(metadata.keys())[:10]}")
