# RESILIENCE-ALPHA - version personnelle (workshop EPSI Bac+5, groupe 15)

Plateforme de paiement **fictive** qui subit un incident de securite et retrouve son fonctionnement
sans intervention humaine. Ce depot est ma **version personnelle** construite pendant le workshop :
la plateforme presentee au jury etait celle d'un coequipier (Node.js) ; ici, j'ai ecrit une architecture
equivalente en Python et la partie IA.

## Ma contribution
- **PC IA** : Ollama (modele local `qwen2.5:3b`), reseau et pare-feu du groupe (dossier `assistant-ia/`).
- **Assistant operateur (RAG)** : Ollama + LangChain, repond a partir de la documentation en citant ses sources, en lecture seule.
- **Partie IA du dossier** : `Dossier-partie-IA.md`.
- **Plateforme Python** (`services/`) : API FastAPI, authentification JWT, WAF ModSecurity, Prometheus, Loki, Grafana,
  detecteur d'anomalies, orchestrateur de remediation, frontend React.

Le detecteur ML (Isolation Forest) et le moteur de remediation de la plateforme finale presentee ont ete developpes par Ismael Cherif.

## Structure
```text
docker-compose.yml        # plateforme complete (Docker Compose)
services/                 # api, auth, db, detector, orchestrator, frontend, prometheus, grafana, alloy
scripts/                  # scripts de test locaux
assistant-ia/             # assistant RAG (FastAPI + page web), lancement par script
Dossier-partie-IA.md      # partie IA du dossier (version simple)
```

## Lancer la plateforme (en local)
Prerequis : Docker Desktop (WSL2), environ 8 Go de RAM.
```powershell
Copy-Item .env.example .env        # puis remplacer chaque "CHANGE_ME" par un secret aleatoire
docker compose up --build -d
docker compose ps
```
Frontend : http://127.0.0.1:8082 - Grafana : http://127.0.0.1:3000 - Prometheus : http://127.0.0.1:9090

## Lancer l'assistant IA
Il faut Ollama avec les modeles `qwen2.5:3b` et `nomic-embed-text`, et des fichiers `.md` dans `assistant-ia/docs/`.
```powershell
cd assistant-ia
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:OLLAMA_URL = "http://127.0.0.1:11434"
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8100
```

## Securite
Aucun secret dans le depot (`.env` est ignore). Toutes les donnees sont fictives. L'assistant est en lecture seule et sans acces au systeme.
Le script `lancer-assistant.ps1` contient l'adresse du reseau du groupe (`192.168.137.149`) : a adapter.
