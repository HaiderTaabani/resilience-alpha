# Assistant opérateur (PC IA)

Assistant local pour les opérateurs : Ollama + LangChain + RAG sur la documentation de `docs/`.
Il explique, il n'agit pas : aucun accès au système.

## Prérequis
- Ollama installé, avec les modèles `llama3.2:3b` et `nomic-embed-text` (`ollama pull ...`)
- Python 3.11 ou plus

## Installation (une fois)
```powershell
cd assistant-ia
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Lancement
```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8100
```
Puis ouvrir http://127.0.0.1:8100

## Adapter la base de connaissances
Ajouter ou modifier des fichiers `.md` dans `docs/`, puis relancer le serveur (l'index est reconstruit au démarrage).

## Variables
`OLLAMA_URL`, `CHAT_MODEL`, `EMBED_MODEL`, `DOCS_DIR`, `TOP_K`
