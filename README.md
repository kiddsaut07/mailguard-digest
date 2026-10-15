# MailGuard Digest — Kit de référence OpenCode

## But
Construire progressivement une application locale qui transforme des rapports DMARC agrégés en XML, XML.GZ ou ZIP en analyses vérifiables et briefings lisibles. Ce dossier est le contrat du projet : OpenCode doit lire tous les fichiers Markdown avant de coder.

## Environnement cible
- Kali Linux, Dell Latitude E7240, Intel i5 4e génération, 4 Go RAM.
- Python 3.11+ et Flask/Jinja, SQLite.
- Pas de React, Node, Docker ou service lourd requis.
- Aucun service cloud payant. Ollama est facultatif et désactivé par défaut.
- Après installation des dépendances, l'application doit fonctionner sans Internet ni IA.

## Documents
1. `01_PRODUCT_SPEC.md` — objectif, fonctionnalités, hors périmètre.
2. `02_ARCHITECTURE.md` — structure et responsabilités.
3. `03_SECURITY_PRIVACY.md` — sécurité et confidentialité.
4. `04_DATA_MODEL_AND_DMARC_RULES.md` — données et règles métier.
5. `05_TEST_STRATEGY.md` — tests obligatoires.
6. `06_UI_AND_REPORTING.md` — interface et rapports.
7. `07_IMPLEMENTATION_RULES.md` — règles strictes pour l'agent.
8. `08_DEFINITION_OF_DONE.md` — critères de livraison.
9. `DECISIONS.md` — décisions fixes.
10. `PROMPTS_ETAPES.md` — plan séquentiel.
11. `PROMPT_DE_DEMARRAGE.txt` — prompt initial à coller dans OpenCode.

## Utilisation
Ouvre le dépôt de l'application dans OpenCode, colle `PROMPT_DE_DEMARRAGE.txt`, vérifie la fin de l'étape, puis envoie uniquement `continue` pour l'étape suivante. Ne lui demande pas de tout construire d'un coup.

Les rapports importés sont des données non fiables. Le produit n'envoie pas d'e-mail, ne modifie pas le DNS et ne doit jamais recommander automatiquement `p=quarantine` ou `p=reject` sur la seule base d'un rapport.

---

# Application — MailGuard Digest

**User interface language: English.** The whole interface — pages, labels, error messages,
deterministic findings and the analysis briefing — is written in English. Source code comments and
internal developer documentation remain in French, and internal identifiers (multipart field names,
storage keys, finding identifiers) are unchanged on purpose.

Section d'ajoutée au fur et à mesure de l'implémentation. État actuel : **étapes 0 à 10 terminées** (configuration, audit, modèles validés, parseur XML sécurisé, importation `.xml` / `.xml.gz` / `.zip`, moteur de règles et briefing déterministes, historique SQLite, interface web en anglais avec rapport HTML et CSS local responsive).  Le journal détaillé se trouve dans `docs/IMPLEMENTATION_LOG.md`.

## Prérequis

- Linux (cible : Kali Linux), Python 3.11 ou plus récent.
  Environnement de référence vérifié le 2026-10-15 : Kali 2025.2, Python 3.13.12, Intel i5-4300U, 3,8 Go de RAM.
- Aucun Docker, aucun service externe, aucun compte cloud.

## Installation

```bash
cd mailguard-digest
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
```

Dépendances d'exécution : Flask, Pydantic, defusedxml, requests (appel local facultatif à Ollama), python-dotenv. Dépendance de test : pytest.

## Configuration

```bash
cp .env.example .env
```

Puis renseigner `FLASK_SECRET_KEY`, générable sans réseau :

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Variables notables : `MAILGUARD_HOST` et `MAILGUARD_PORT` (écoute locale par défaut), `MAILGUARD_DATABASE_PATH`, les limites d'import `MAILGUARD_MAX_*` (10 Mio compressé, 50 Mio décompressé, 100 membres, 20 rapports) et les options `MAILGUARD_AI_ENABLED` / `MAILGUARD_OLLAMA_*` (IA désactivée par défaut).

Le fichier `.env` est ignoré par Git. Aucun secret ne doit être versionné.

## Exécution

```bash
.venv/bin/python -m app.main
```

Options facultatives : `--host`, `--port`, `--debug` (développement local uniquement).

Au démarrage, l'application charge et valide la configuration, crée ou met à niveau la base
SQLite à l'emplacement configuré, puis sert l'application sur `http://127.0.0.1:5000` par défaut.
Aucune donnée n'est effacée au démarrage, et aucun service externe n'est contacté.

## Optional local AI narration (Ollama)

**Deterministic core, optional AI narrative.** Every figure, verdict, policy value, finding and
interpretation limit shown by MailGuard Digest is produced by the deterministic engine. A local
language model may only rephrase findings that already exist. It never calculates, corrects or
replaces anything, and its text is never stored, exported or used to rebuild a report.

**Disabled by default.** With `MAILGUARD_AI_ENABLED=0` the application never contacts Ollama,
never imports the AI code, and never logs anything about it.

To enable it:

1. Install Ollama separately and start it (`ollama serve`). MailGuard Digest never launches it.
2. Download a model once, by hand, for example a small instruct model suited to modest hardware:
   `ollama pull <model>`. Verify it is present with `ollama list`. The application never downloads a
   model and never requires one to be installed.
3. Copy `.env.example` to `.env` and set:

   ```bash
   MAILGUARD_AI_ENABLED=1
   MAILGUARD_OLLAMA_URL=http://127.0.0.1:11434
   MAILGUARD_OLLAMA_MODEL=<model already available locally>
   MAILGUARD_OLLAMA_TIMEOUT_SECONDS=10
   MAILGUARD_OLLAMA_MAX_INPUT_CHARS=4000
   MAILGUARD_OLLAMA_MAX_OUTPUT_TOKENS=300
   ```

4. Restart the application.

Only loopback endpoints are accepted unless `MAILGUARD_OLLAMA_ALLOW_REMOTE=1` is set explicitly.
Redirects are never followed, requests are never retried, and the answer is bounded in size and
generation length.

**What is sent to Ollama:** the identifier, severity label, title, description and interpretation
limit of at most twelve deterministic findings, wrapped in an explicit untrusted-data block.

**What is never sent:** raw XML, archive contents, source records, source IP addresses, database
content, file paths, environment variables, secrets, briefing text, or any other analysis.

Prompt-injection resistance is layered: imported text is labelled as data, the system prompt forbids
following it, input is truncated to a fixed budget, and the answer is strictly validated. The
narration is accepted only if it matches a strict schema, references only finding identifiers that
were actually sent, contains no control characters, stays within length limits and contains no
policy recommendation or source judgement. Otherwise the narration is discarded as a whole.

**When Ollama is offline, slow or misconfigured**, the import still succeeds, the deterministic
report and briefing are unchanged, and the report page states that local AI is unavailable. A
timeout is an optional-feature failure, never an analysis failure.

**Privacy guarantee and its limit:** inference stays on the configured Ollama endpoint, which is
loopback by default. That guarantee depends on your Ollama deployment and on the endpoint you
configure; a remote endpoint opted in with `MAILGUARD_OLLAMA_ALLOW_REMOTE=1` sends the findings
over the network.

Narration is generated once, at import time, and is never requested again: stored reports are shown
unchanged, so no model is called on page refresh and no database migration is needed.

**What was actually tested:** the adapter, the validation, the fallback and the user interface with a
simulated HTTP transport, plus one real attempt against `127.0.0.1:11434` with no Ollama running
(connection refused, deterministic report preserved). **No real model was downloaded or run**, and no
claim is made about how a given model performs on a 4 GB machine.

## Print and export

- **Print report** (report page, new or stored): uses the browser's own print dialog. Choose
  “Save as PDF” there if a PDF file is needed — no PDF engine runs on the server, and the result is
  not a certified document. Without JavaScript, printing from the browser menu gives the same layout.
- **Download JSON**: `GET /history/<identifiant>/export.json`, `application/json` attachment named
  `mailguard-analysis-<identifiant>.json`. Envelope:

  ```json
  {
    "schema_version": 1,
    "exported_at": "…",
    "analysis_identifier": 12,
    "stored_at": "…",
    "stored_by_version": "0.1.0",
    "uploaded_file_name": "rapport.xml",
    "content_sha256": "…",
    "analysis": { "…": "stored deterministic analysis" },
    "briefing": { "…": "stored briefing text" }
  }
  ```

  Numbers stay numbers, booleans stay booleans and missing values stay `null`. The uploaded XML is
  never included because it is never stored.
- **Download CSV (sources)**: `GET /history/<identifiant>/export.csv`, UTF-8 `text/csv` attachment,
  one row per source IP with the columns `source_ip`, `total_messages`, `messages_pass`,
  `messages_fail`, `failure_rate_percent`, `evaluated_spf_pass`, `evaluated_spf_fail`,
  `evaluated_dkim_pass`, `evaluated_dkim_fail`, `disposition_none`, `disposition_quarantine`,
  `disposition_reject`, `header_from_domains`. Text values starting with `=`, `+`, `-` or `@` are
  prefixed with `'` to avoid spreadsheet formula injection.
- Exports are read-only: no stored value is modified, no engine runs again, and the file name is built
  only from the numeric analysis identifier, so imported values cannot influence response headers.

## History and deletion

- `GET /history` lists the analyses actually stored, most recent first. The listing is bounded to 20
  entries and the real total is displayed alongside, so the page never pretends to be exhaustive.
- `GET /history/<identifiant>` reopens a stored report. Results, findings and briefing text are read
  back as stored: neither the parser nor the rules engine runs again.
- `POST /history/<identifiant>/delete` deletes one analysis. Deletion exists only as a POST carrying
  a valid CSRF token, then redirects to the history page. It is immediate and irreversible.
- Analyses stored before the English-language update keep their original findings and briefing text,
  in their original language.

## Formats acceptés

`.xml`, `.xml.gz` et `.zip`. Un fichier `.zip` peut contenir plusieurs rapports XML ainsi que des
répertoires ; les fichiers ordinaires non pris en charge y sont ignorés puis listés dans le résultat.
Une archive imbriquée, un membre chiffré, un lien symbolique ou un chemin piégé est refusé.

Le pipeline complet est : import sécurisé → rapports validés → moteur déterministe → briefing →
historique SQLite. Le XML lui-même n'est jamais conservé.

## Tests

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q app
```

À ce jour, `pytest -q` renvoie le code de sortie 5 (aucun test collecté, `tests/` n'existe pas encore) et `compileall app` signale `Can't list 'app'` (paquet créé à l'étape 1).

Résultat observé le 2026-10-16 : `376 passed` (37 modèles, 34 parseur, 59 archives, 36 règles, 19 briefing, 41 stockage, 111 web, 39 tests IA) et `compileall` sans erreur.

## Limites actuelles

- Livré : modèles validés (`app/core/models.py`), parseur XML sécurisé (`app/core/parser.py`), import `.xml` / `.xml.gz` / `.zip` en mémoire (`app/core/archive.py`), moteur de règles et briefing déterministes (`app/core/rules.py`, `app/core/briefing.py`), historique local SQLite (`app/storage/database.py`) et application web locale (`app/main.py`, `app/api/routes.py`, `app/config.py`, `app/templates/`).
- Le moteur est la seule source des chiffres : totaux, taux pondérés par les compteurs, dispositions, vues par source IP et constats. Le briefing ne fait que reformuler ces résultats et n'effectue aucun appel réseau ni IA.
- Interface : interface en anglais, feuille de style locale et responsive (`app/static/css/style.css`), rapport HTML complet, aucune dépendance externe (police, image ou CDN).
- Les tests de l'IA locale utilisent un transport HTTP simulé : aucun modèle n'a été téléchargé ni exécuté.
- L'import est protégé par un jeton CSRF vérifié côté serveur ; la suppression d'un enregistrement existe dans la couche SQLite mais n'est pas exposée par l'interface.
- Le formulaire d'import accepte la configuration complète (`.env` ou variables d'environnement) ; toute valeur invalide ou incohérente est refusée au démarrage, aucune limite n'est désactivée.
- L'historique conserve l'empreinte SHA-256, le nom de fichier nettoyé, la date d'import et les résultats revalidés, jamais le XML ni l'archive. Un contenu binaire déjà importé n'est pas réenregistré : la contrainte d'unicité SQLite fait autorité.
- Un membre en échec dans une archive fait échouer l'import entier : aucune importation partielle n'est présentée comme un succès.
- Le dépôt Git a été initialisé (`git init`) mais aucun commit n'a encore été créé.
- `PROMPT_DE_DEMARRAGE.txt`, annoncé au point 11 du kit ci-dessus, est absent du dossier.
- Une fois les dépendances installées, l'application doit fonctionner sans Internet et sans IA.
