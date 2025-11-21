import pkg_resources
import sys
import requests
import os

def check_dependencies():
    print("--- Controllo Dipendenze ---")
    requirements_path = 'requirements.txt'
    if not os.path.exists(requirements_path):
        print(f"❌ File {requirements_path} non trovato.")
        return False

    with open(requirements_path, 'r') as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    missing = []
    for req in requirements:
        # Gestione base per nomi pacchetti vs import (es. langchain-community)
        pkg_name = req.split('[')[0].split('==')[0].split('>=')[0]
        try:
            pkg_resources.get_distribution(pkg_name)
            print(f"✅ {pkg_name} installato.")
        except pkg_resources.DistributionNotFound:
            missing.append(pkg_name)
            print(f"❌ {pkg_name} MANCANTE.")

    if missing:
        print(f"\n⚠️ Pacchetti mancanti: {', '.join(missing)}")
        print("Esegui: pip install -r requirements.txt")
        return False
    return True

def check_ollama():
    print("\n--- Controllo Ollama ---")
    try:
        response = requests.get("http://127.0.0.1:11434/")
        if response.status_code == 200:
            print("✅ Server Ollama attivo.")
        else:
            print(f"⚠️ Server Ollama risponde con status {response.status_code}.")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Server Ollama NON raggiungibile. Assicurati che Ollama sia in esecuzione.")
        return False

    # Controllo modello
    required_model = "llama3:8b"
    try:
        response = requests.get("http://127.0.0.1:11434/api/tags")
        if response.status_code == 200:
            models = [m['name'] for m in response.json().get('models', [])]
            if required_model in models or f"{required_model}:latest" in models:
                print(f"✅ Modello '{required_model}' trovato.")
            else:
                print(f"❌ Modello '{required_model}' NON trovato. Modelli disponibili: {models}")
                print(f"Esegui: ollama pull {required_model}")
                return False
    except Exception as e:
        print(f"⚠️ Impossibile verificare i modelli: {e}")
        return False
    
    return True

if __name__ == "__main__":
    deps_ok = check_dependencies()
    ollama_ok = check_ollama()
    
    if deps_ok and ollama_ok:
        print("\n✅✅✅ AMBIENTE PRONTO! ✅✅✅")
    else:
        print("\n❌❌❌ CI SONO PROBLEMI DA RISOLVERE. ❌❌❌")
