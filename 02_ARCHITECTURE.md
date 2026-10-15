# 02 — Architecture cible

## Stack
- Python 3.11+.
- Flask et Jinja2 pour une application web locale.
- Pydantic pour valider les objets métier.
- `defusedxml` pour XML non fiable.
- Bibliothèque standard pour gzip, ZIP, hash, dates, IP et SQLite.
- `pytest` pour les tests.
- `requests` uniquement pour l'appel local facultatif à Ollama.
- Pas de React, Node, Docker, Redis, Celery ou base de données serveur.

## Arborescence cible
```text
mailguard-digest/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── main.py
│   ├── api/routes.py
│   ├── core/{models.py,parser.py,archive.py,rules.py,briefing.py}
│   ├── ai/{ollama_client.py,prompts.py}
│   ├── storage/database.py
│   ├── templates/{base.html,index.html,report.html,history.html}
│   └── static/style.css
├── tests/fixtures/
├── tests/test_parser.py
├── tests/test_archive.py
├── tests/test_rules.py
├── tests/test_storage.py
├── tests/test_api.py
├── tests/test_ai.py
├── docs/
├── scripts/
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

OpenCode peut adapter la structure uniquement si une raison technique précise est documentée et que les responsabilités restent séparées.

## Responsabilités
- `archive.py` : lire XML, GZIP et ZIP avec limites; ne jamais extraire un chemin ZIP sur disque.
- `parser.py` : XML DMARC vers modèle validé; aucun accès Flask ou SQLite.
- `models.py` : structures et contraintes métier.
- `rules.py` : agrégations, calculs et constats déterministes.
- `briefing.py` : texte français neutre issu des constats, sans IA obligatoire.
- `database.py` : schéma SQLite et requêtes paramétrées.
- `ollama_client.py` : appel local facultatif avec timeout et gestion des erreurs.
- `routes.py` : orchestration des services et rendu des templates, sans calcul métier.
- Templates : affichage uniquement.
- Tests : chaque couche indépendamment.

## Flux
Fichier → validation type/taille → lecture sécurisée → parsing → modèle validé → règles → stockage → interface/rapport → narration IA facultative.

## Erreurs
Les erreurs métier doivent être identifiables. L'interface affiche un message compréhensible, sans trace Python brute. Les logs locaux peuvent contenir des détails utiles mais jamais des secrets.
