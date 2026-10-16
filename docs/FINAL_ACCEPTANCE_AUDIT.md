# Audit d'acceptation final — MailGuard Digest (étape 12)

**Date de l'audit :** 2026-10-16
**Objet :** vérification de l'état réel du dépôt au moment de l'étape 12, audit de
chaque case applicable de `08_DEFINITION_OF_DONE.md`, guide d'exploitation Kali
Linux reproductible, et verdict de préparation.

Ce document ne modifie ni le code métier, ni le schéma de base, ni les tests, ni
les gabarits, ni les dépendances. Les seules modifications apportées sont
documentaires, et seulement là où une affirmation était fausse, incomplète ou
dangereuse pour l'exploitation.

**Aucun rapport de étape antérieure n'a été repris comme preuve.** Les
constats « 376 tests », « 417 tests », « conforme à §15 » et autres ont été
re-vérifiés par exécution dans cet environnement ; le détail figure en §5.

---

## 1. Périmètre de l'audit et environnement

### 1.1 État du dépôt au démarrage de l'étape

| Élément | Valeur observée |
| --- | --- |
| Branche | `main` |
| Commit | `f17bf1a Initial commit: local DMARC aggregate report analyser` (unique) |
| `git status --short` | 11 fichiers modifiés, 2 non suivis — **tous issus de l'étape 11, aucun travail utilisateur préexistant** |
| Fichiers non suivis | `docs/SECURITY_AUDIT.md`, `tests/test_audit_etape11.py` |
| `.env` | **absent** (jamais créé — le dépôt ne contient aucun secret) |
| `data/` | **absent** (aucune base n'a jamais été créée dans le dépôt) |
| Fichiers versionnés | 80 |

Les modifications de l'étape 11 sont **non commitées**. Elles ont été
conservées intactes : ni écrasement, ni `reset`, ni reformattage. Aucun commit
n'a été créé à cette étape.

### 1.2 Environnement

| Élément | Valeur observée |
| --- | --- |
| Système | Kali GNU/Linux Rolling 2025.2 (`/etc/os-release`) |
| Python du poste | `Python 3.13.12` |
| Python exigé | `requires-python = ">=3.11"` (`pyproject.toml:6`) |
| Matériel | Intel i5-4300U, 3 857 Mio de RAM |
| Environnement virtuel du dépôt | `.venv` (Python 3.13.12, symlink vers `/usr/bin/python3`) |
| Environnement virtuel de contrôle | `/tmp/opencode/verif-venv`, créé **de zéro** pendant cette étape |

### 1.3 Fichiers de documentation référencés : existence réelle

Le kit place les documents à la racine du dépôt, pas dans `docs/`.

| Chemin attendu par la consigne d'étape | État réel | Emplacement réel |
| --- | --- | --- |
| `docs/SECURITY_PRIVACY.md` | **ABSENT** | `03_SECURITY_PRIVACY.md` (racine) |
| `docs/ARCHITECTURE.md` | **ABSENT** | `02_ARCHITECTURE.md` (racine) |
| `docs/TEST_STRATEGY.md` | **ABSENT** | `05_TEST_STRATEGY.md` (racine) |
| `docs/IMPLEMENTATION_LOG.md` | présent (74 120 octets) | `docs/` |
| `docs/SECURITY_AUDIT.md` | présent (31 008 octets), créé à l'étape 11 | `docs/` |
| `docs/FINAL_ACCEPTANCE_AUDIT.md` | créé par cette étape | `docs/` |
| `PROMPT_DE_DEMARRAGE.txt` (README §Documents, point 11) | **ABSENT** | — |

Aucune substitution silencieuse n'a été faite : `03_`, `02_` et `05_` ont été
utilisés comme équivalents**, et `PROMPT_DE_DEMARRAGE.txt` reste signalé comme
manquant (le README le mentionnait déjà en §Limites actuelles).

### 1.4 Ce qui n'était pas vérifiable dans cet environnement

| Limite | Conséquence sur l'audit |
| --- | --- |
| `ollama` absent du poste, port 11434 fermé | L'intégration **réelle** Ollama/modèle ne peut pas être vérifiée : `NOT TESTED — real Ollama/model integration` |
| Aucun navigateur disponible | Aucune vérification visuelle du rendu, de l'impression ni du contraste WCAG |
| Pas de `sudo`, donc pas d'isolation réseau par namespace | « Fonctionne sans Internet » démontré par blocage logiciel des connexions non locales (voir §2, item 23) |
| Aucun outil d'audit de dépendances installé | Les avis de sécurité des dépendances proviennent de l'étape 11 (API OSV), non re-interrogés ici |

---

## 2. Matrice de la definition of done

Statuts employés : `PASS` (vérifié par preuve directe ou test reproductible),
`PARTIAL` (exigence partiellement satisfaite, écart identifié), `FAIL` (exigence
applicable non satisfaite), `NOT TESTED` (preuves insuffisantes), `N/A` (non
applicable, motif donné).

### 2.1 Fonctionnel

| # | Exigence (`08_DEFINITION_OF_DONE.md`) | Statut | Preuve | Limite / action requise |
| --- | --- | --- | --- | --- |
| 1 | Import XML, XML.GZ et ZIP avec limites | **PASS** | Routes `app/api/routes.py:54-102`. `app/core/archive.py` : `_verifier_taille_televersee`, `_Budget` (octets réellement lus), `_verifier_volume` (membres + volume), `_verifier_noms`, `_verifier_types`, `_verifier_nombre_rapports`. Vérifié en réel : `.xml` 200, `.xml.gz` 200, `.zip` 200. Tests : 59 dans `tests/test_archive.py` + 8 dans `tests/test_audit_etape11.py`. | Limites en octets seulement ; voir §4.2 pour l'abondance. Aucune action requise pour un usage local. |
| 2 | Parseur validant métadonnées, politique et records | **PASS** | `app/core/parser.py` + `app/core/models.py` (`extra="forbid"`, enums stricts). Vérification indépendante : 18 fixtures sur 25 sont refusées avec le bon type d'erreur (`ReportParseError` / `ReportValidationError`), 7 acceptées et validées. 34 tests dans `tests/test_parser.py`, 37 dans `tests/test_models.py`. | Aucune action requise. |
| 3 | Calculs exacts et invariants testés | **PASS** | Contrôle indépendant exécuté sur les 7 fixtures acceptées : `pass+fail=total`, `somme(dispositions)=total`, invariant par source, `taux is None ⟺ total==0` — **tous vrais**. Tests : `test_taux_sont_ponderes_par_les_comptteurs_et_non_moyennes`, `test_volume_total_nul_laisse_les_taux_indisponibles`, `test_taux_non_arrondi_en_interne_mais_arrondi_a_l_affichage`, `test_incoherence_de_dispositions_est_detectee_par_la_fonction_du_controle`, `test_les_contradictions_ne_survivent_pas_a_la_validation_des_modeles`. | Aucune action requise. |
| 4 | Erreurs compréhensibles | **PASS** | Messages réels relevés sur le serveur : « the content is not XML although the file format announces it », « entry « ../evasion.xml » escapes the archive root », « the ZIP archive is empty », « the report is unreadable or truncated ». Aucun `Traceback`, aucun `pydantic`, aucun `sqlite3.` dans les pages d'erreur (grep sur 5 pages). | Aucune action requise. |
| 5 | Interface locale utilisable | **PASS** | Parcours réel : accueil → `/upload` → import → rapport → `/history` → relecture → exports → suppression. HTTP 200 partout. 8 sections de rapport présentes, libellés anglais vérifiés dans `app/templates/resultat.html`. `lang="en"`, lien d'évitement, `<main tabindex="-1">`, `<caption>` sur les tableaux. | **Non vérifié visuellement** (aucun navigateur) : mise en page, contraste, petite taille d'écran. Aucune action bloquante pour un usage local. |
| 6 | Rapport avec chiffres et constats traçables | **PASS** | `app/core/rules.py` : `Constat` porte `mesures`, `sources`, `limites`. Contrôle indépendant : **7 constats sur 7** ont une limite d'interprétation non vide. `app/core/briefing.py` : résumé exécutif, chiffres clés, observations, points à vérifier, limites, à retenir. | Aucune action requise. |
| 7 | Historique SQLite et détection des doublons | **PASS** | `app/storage/database.py` : table unique `analyses`, `empreinte TEXT NOT NULL UNIQUE`, schéma versionné par `PRAGMA user_version`. Doublon = violation `UNIQUE` rattrapée, jamais un `SELECT` préalable. Vérifié en réel : second import du même contenu → HTTP 200 avec « already been imported », toujours 1 ligne. Tests : `test_second_import_identique_ne_cree_pas_de_ligne`, `test_appels_concurrents_ne_creent_qu_une_ligne`, `test_contrainte_d_unicite_verifiee_par_sqlite`. | Liste bornée à 20 entrées sans pagination, total réel affiché à côté. Documenté, non bloquant. |
| 8 | Export HTML imprimable | **PASS** | `app/static/css/style.css:548` `@media print` ; `app/static/js/print.js` (13 lignes, local) déclenché par `data-action="print"`. CSP `script-src 'self'` autorise ce script unique. Vérifié en réel : CSS 200, JS 200, bouton « Print report » présent sur rapport neuf **et** rapport stocké. | **Non vérifié visuellement** : pagination, veuves/orphelines, position des sauts dépendent du navigateur. Aucune action bloquante. |
| 9 | PDF implémenté ou limitation documentée | **PASS** | PDF **non implémenté** (choix assumé). Limitation documentée dans `README.md` §Print and export, dans `resultat.html:367` (« Printing uses the browser's own print dialog; choose "Save as PDF" there… ») et dans `docs/IMPLEMENTATION_LOG.md`. `06_UI_AND_REPORTION.md` autorise explicitement ce choix. | Le PDF dépend du navigateur et n'est pas un document certifié. Documenté. |
| 10 | IA facultative, désactivée par défaut, avec fallback | **PARTIAL** | Désactivée par défaut : `Configuration.ai_active = False` (`app/config.py:60`), `.env.example` `MAILGUARD_AI_ENABLED=0`. Vérifié en réel : statut « AI narration is disabled in this installation. », **aucune mention d'Ollama ni de `requests` dans le journal**. Fallback vérifié en réel (connexion refusée → « Local AI is unavailable » + `ConnectionError`, mesures conservées) et avec timeout réel borné. 39 tests `tests/test_ai.py` + 10 tests web. | **Écart : l'intégration avec un vrai modèle n'a jamais été vérifiée** (`ollama` absent du poste). Le contrat `/api/chat` est supposé, non confirmé. Voir §4.3. Aucune action requise pour le cœur déterministe. |

### 2.2 Qualité

| # | Exigence | Statut | Preuve | Limite / action requise |
| --- | --- | --- | --- | --- |
| 11 | Tests automatisés passent | **PASS** | `.venv/bin/python -m pytest -q` → **417 passed**, code de sortie 0. **Réexécuté dans un environnement virtuel neuf** créé depuis `requirements-dev.txt` → **417 passed**, code de sortie 0. 0 test ignoré, `xfail` ou désélectionné. | Aucune action requise. |
| 12 | Aucun secret versionné | **PASS** | `git ls-files` : ni `.env`, ni certificat, ni clé, ni base SQLite. `.env.example:8` `FLASK_SECRET_KEY=` vide. Balayage `git grep -IE` sur le code : uniquement des identifiants (`cle_secrete`, `secrets.token_hex`, `token_urlsafe`, `compare_digest`), aucune valeur. | Aucune action requise. |
| 13 | Pas de données clients dans les fixtures | **PASS** | 26 fixtures. Organisations : `Example Mail Provider`, `Another Example Mail Provider`, `Test provider without identifier`. Domaines : `example.com/net/org` (RFC 2606). IP : `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` (RFC 5737) et `2001:db8::/32` (RFC 3849). Toutes marquées « FIXTURE SYNTHÉTIQUE ». | Aucune action requise. |
| 14 | Pas de trace brute dans l'interface | **PASS** | Vérifié sur 5 pages d'erreur réelles : aucun `Traceback`, `File "`, `pydantic` ou `sqlite3.`. `app/erreurs.py:58` renvoie le message métier ; l'exception non gérée renvoie un texte générique (`app/__init__.py:19`). | Aucune action requise. |
| 15 | Aucune extraction ZIP non sécurisée | **PASS** | `app/core/archive.py` ne contient **ni `extractall` ni `os.path` ni écriture disque**. Test `test_aucun_fichier_n_est_ecrit_sur_le_disque`. Traversée refusée en réel : `../evasion.xml` → « escapes the archive root ». | Aucune action requise. |
| 16 | Les chiffres IA ne remplacent jamais les calculs déterministes | **PASS** | `app/services.py` : `narrer_import` ne reçoit que l'analyse ; `ResultatImport.analyse` lit `enregistrement.analyse`, jamais la narration. `app/ai/ollama_client.py` ne renvoie que `ResultatNarration`, jamais de métrique. Tests : `test_la_narration_ne_modifie_aucune_metrique_deterministe`, `test_le_briefing_deterministe_est_inchange_par_un_echec_ia`, `test_export_json_ne_contient_pas_de_narration`, `test_export_csv_ne_contient_pas_de_narration`, `test_base_de_donnees_inchangee_par_la_narration`. | Aucune action requise. |
| 17 | README couvre installation, exécution, tests et limites | **PARTIAL** | Les quatre sections existent. **Écarts corrigés à cette étape** : (a) une phrase obsolète affirmait encore « `pytest -q` renvoie le code de sortie 5 (aucun test collecté…) » ; (b) le chemin de la base était décrit comme apparaissant dans le journal, ce qui n'est pas observable (§4.5) ; (c) la dépendance à `.venv` n'était pas explicitée pour les commandes. | **Écart restant : pas de section de dépannage ni de guide d'exploitation complet.** Corrigé : voir §3 (désormais également dans le README). |
| 18 | `.gitignore` exclut venv, caches, DB locale, rapports importés et secrets | **PASS** | 14 motifs testés un par un avec `git check-ignore`, **tous `IGNORE`** : `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.env`, `.env.*` (hors `.env.example`), `*.sqlite3`, `data/`, `imports/`, `uploads/`, `instance/`, `imported_reports/`, `build/`, `dist/`. | Un `.xml.gz` posé **à la racine du dépôt** n'est pas ignoré (`NON IGNORE`) : ce n'est pas un défaut de `.gitignore` (les rapports importés vivent dans `imports/`, `uploads/`, `data/`), mais cela vaut avertissement. **Action requise : ne jamais déposer un rapport dans la racine du dépôt avant `git add .`.** |

### 2.3 Matériel modeste

| # | Exigence | Statut | Preuve | Limite / action requise |
| --- | --- | --- | --- | --- |
| 19 | Pas de Docker requis | **PASS** | Aucun `Dockerfile`, `docker-compose*`, `package.json`, `Makefile`, `tox.ini`, `setup.cfg`, `.pre-commit-config.yaml`, `poetry.lock` dans le dépôt. Exécution directe depuis les sources (`pyproject.toml:28-29`). | Aucune action requise. |
| 20 | Fonctionne sans Ollama | **PASS** | Parcours complet exécuté sur ce poste où `ollama` est **absent** : import, historique, relecture, exports JSON/CSV, CSS, JS — tous HTTP 200. `docs/SECURITY_AUDIT.md` §F5 : statut affiché, mesures conservées. | Aucune action requise. |
| 21 | Fonctionne sans Internet après installation | **PASS** | **Démonstration directe** : parcours complet exécuté avec `socket.socket.connect` et `socket.getaddrinfo` modifiés pour **lever une exception sur toute destination hors boucle locale** (127.0.0.1, ::1, localhost). Résultat : import 200, historique 200, rapport stocké 200, exports 200, CSS 200, JS 200, 1 ligne en base, mesures réelles présentes, **connexions hors boucle localees : AUCUNE**. | Aucune action requise. Le seul client réseau du dépôt (`requests`) n'est importé qu'à l'intérieur de `_transport_requests`, jamais au niveau module. |
| 22 | Dépendances raisonnables | **PASS** | 5 dépendances d'exécution (Flask, pydantic, defusedxml, requests, python-dotenv), 1 de test (pytest). Installation reproduite de zéro : 25 paquets au total, venv de 47 Mo. Aucune dépendance superflue, dupliquée ou manquante ( graphe d'imports entièrement couvert). | Aucune action requise. |
| 23 | Aucun traitement lourd en arrière-plan | **PASS** | `grep` sur `app/` : **aucune occurrence** de `multiprocessing`, `Thread(`, `daemon=`, `Timer(`, `schedule`, `celery`, `apscheduler`, `asyncio`, `subprocess`, `Popen`, `fork(`. Seul `threading.Lock()` dans `ai/ollama_client.py:145`, c'est-à-dire un verrou de narration créé à l'appel d'une classe, jamais un travail de fond. L'application ne fait rien tant qu'une requête n'est pas servie. | Aucune action requise. |

### 2.4 Exigences complémentaires de `05_TEST_STRATEGY.md` et `03_SECURITY_PRIVACY.md`

| Exigence | Statut | Preuve |
| --- | --- | --- |
| XML avec/sans namespace, dates UTC, IPv4/IPv6, plusieurs records | **PASS** | `rapport_valide_sans_namespace.xml`, `rapport_valide_avec_namespace.xml`, `rapport_plusieurs_records.xml` (IPv4 + IPv6) ; `test_adresse_ipv6_est_normalisee_en_forme_canonique` |
| XML tronqué, mauvaise racine, metadata/policy manquantes | **PASS** | 4 fixtures dédiées, refusées avec le type d'erreur attendu (contrôle indépendant ci-dessus) |
| Compteurs absents/non numériques/négatifs, IP invalide, disposition/résultat inconnus | **PASS** | 7 fixtures dédiées, toutes refusées |
| Période inversée, DTD/entité refusée | **PASS** | `rapport_periode_inversee.xml`, `rapport_avec_dtd.xml`, `rapport_entite_non_definie.xml` |
| Archives : vide, corrompu, trop grand, trop de membres | **PASS** | 59 tests `tests/test_archive.py` |
| GZIP au-delà de la limite, extension/contenu incohérents | **PASS** | `test_donnees_decompressees_au_dela_de_la_limite_interrompent_la_lecture` |
| Stockage : schéma, insertion/lecture, SHA-256, doublon, SQL hostile | **PASS** | 41 tests `tests/test_database.py`, dont `test_valeurs_avec_apostrophes_ne_provoquent_pas_d_injection` |
| API/UI : accueil 200, import valide/invalide/trop gros, échappement, détail, historique, export | **PASS** | 111 tests `tests/test_web.py` |
| IA : désactivée par défaut ; serveur absent, timeout, réponse invalide → fallback | **PARTIAL** | Tests avec transport simulé **+ connexion refusée réelle et timeout réel**. Le cas « réponse invalide d'un vrai modèle » n'a pas été produit par un modèle réel. |

### 2.5 Répartition des statuts

| Statut | Nombre | Items |
| --- | --- | --- |
| PASS | 20 | 1-9, 11-16, 18-23 + 7 exigences `05_TEST_STRATEGY.md` |
| PARTIAL | 2 | item 10 (IA sans modèle réel), item 17 (README, corrigé partiellement) |
| FAIL | **0** | — |
| NOT TESTED | 0 déclaré item, mais 4 vérifications impossibles listées en §1.4 et §5.4 | — |

---

## 3. Guide d'exploitation Kali Linux

> Toutes les commandes de cette section ont été **exécutées dans cet
> environnement**. Les résultats observés sont indiqués. Aucune commande n'est
> inventée : chaque variable et chaque chemin d'entrée a été relu dans le code.

### 3.1 Prérequis

| Élément | Minimum vérifié | Recommandé | Comment vérifier |
| --- | --- | --- | --- |
| Système | Linux avec `python3` et `venv` | Kali GNU/Linux Rolling (cible du kit) | `cat /etc/os-release` |
| Python | **3.11** ou plus récent | 3.13 (version de référence du projet) | `python3 --version` |
| RAM | Non mesuré comme minimum | 3,8 Go (machine de référence) | `free -m` |
| Git | Non requis pour utiliser l'application | Recommandé pour versionner | `git --version` |
| Paquets système | **Aucun** sur une installation Kali standard : `python3-venv` est normalement déjà présent | — | `dpkg -l python3-venv` |

**Aucun paquet système n'a été nécessaire sur ce poste** : `python3-venv
3.13.9-3+b1` y est déjà installé, et ni Docker, ni Node, ni compilateur ne sont
requis. Sur une installation Kali minimale où `python3 -m venv` échouerait pour
cause de module `venv` absent, `sudo apt install python3-venv` est le seul `sudo`
éventuellement nécessaire, et il ne s'agit pas d'une installation Python
globale.

**Concernant la RAM :** aucune mesure de charge ou de pic mémoire sous
utilisateur réel n'a été effectuée. Les seules mesures disponibles sont celles de
`docs/SECURITY_AUDIT.md` §5.2-5.3, sur des charges **synthétiques** : un
téléversement de 43 Kio représentant 10 000 records occupe 61 Mio de RSS et
0,49 s de traitement. **Aucune affirmation de performance sur un portable 4 Go
n'est faite ici.**

### 3.2 Environnement virtuel et installation

Le dépôt n'est **pas** installable en paquet : `pyproject.toml` ne déclare
**aucune table `[build-system]`** (vérifié : 0 occurrence). `pip install .` et
`pip install -e .` échoueront. C'est un choix assumé — le projet s'exécute depuis
les sources (`pyproject.toml:28-29`). **La méthode documentée et la seule
supportée est l'installation par `requirements-dev.txt`.**

```bash
cd mailguard-digest                       # ou le chemin où se trouve le dépôt

# 1. Vérifier Python (doit afficher 3.11 ou plus)
python3 --version

# 2. Vérifier que venv est disponible avant de commencer
python3 -c "import venv; print('venv OK')" || sudo apt install python3-venv

# 3. Créer l'environnement virtuel (ignoré par Git)
python3 -m venv .venv

# 4. Activer l'environnement
source .venv/bin/activate                    # Bash sur Kali
#   (ou, sans activation, remplacer « python » par « .venv/bin/python » partout)

# 5. Installer les dépendances de développement (inclut le runtime)
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements-dev.txt
```

**Résultat observé** dans un environnement créé de zéro pendant cette étape :

```
Successfully installed Flask-3.1.3 annotated-types-0.8.0 blinker-1.9.0 certifi-2026.7.22
charset_normalizer-3.5.2 click-8.5.0 defusedxml-0.7.1 idna-3.20 iniconfig-2.3.1
itsdangerous-2.2.0 jinja2-3.1.6 markupsafe-3.0.4 packaging-26.3 pluggy-1.7.0
pydantic-2.14.1 pydantic-core-2.50.1 pygments-2.21.0 pytest-8.4.2 python-dotenv-1.2.4
requests-2.34.2 typing-extensions-4.16.0 typing-inspection-0.4.4 urllib3-2.8.0
werkzeug-3.1.9
```
Code de sortie **0**, 25 paquets.

Runtime seul, sans les outils de test :

```bash
python3 -m pip install -r requirements.txt      # 5 dépendances seulement
```

Vérification rapide de l'installation :

```bash
python3 -c "import flask, pydantic, defusedxml, requests, dotenv; print('dépendances OK')"
```

> **Ne jamais exécuter `sudo pip install ...`.** Le projet n'exige aucune
> installation globale : elle mêlerait les versions système et casserait la
> reproductibilité.

### 3.3 Configuration et secret

`.env` est **le** mécanisme de configuration (`app/config.py:_charger_fichier_env`
appelle `dotenv.load_dotenv`, import différé). Le fichier `.env` **n'existe pas
actuellement dans le dépôt** et doit être créé par l'utilisateur.

```bash
cp .env.example .env
```

Générer un secret suffisamment fort, sans réseau :

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copier le résultat dans `FLASK_SECRET_KEY=` dans `.env`. **Ne pas coller de
secret dans ce document, et ne pas versionner `.env`** (déjà ignoré par Git).

| Variable | Requise ? | Défaut sûr | Rôle |
| --- | --- | --- | --- |
| `FLASK_SECRET_KEY` | **Oui, obligatoire hors tests** | *aucun* | Signature des cookies de session et du jeton CSRF. Longueur minimale 32 caractères ; une valeur absente ou courte **refuse le démarrage** (`app/config.py:213-227`). |
| `MAILGUARD_HOST` | Non | `127.0.0.1` | Interface d'écoute. **Ne pas modifier** (§4.1). |
| `MAILGUARD_PORT` | Non | `5000` | Port d'écoute, borné 1-65535. |
| `MAILGUARD_DATABASE_PATH` | Non | `data/mailguard.sqlite3` | Fichier SQLite, relatif à la racine du dépôt. Le dossier parent est créé au démarrage. |
| `MAILGUARD_MAX_COMPRESSED_BYTES` | Non | `10485760` (10 Mio) | Taille maximale d'un fichier téléversé. |
| `MAILGUARD_MAX_DECOMPRESSED_BYTES` | Non | `52428800` (50 Mio) | Volume décompressé cumulé. |
| `MAILGUARD_MAX_ARCHIVE_MEMBERS` | Non | `100` | Membres maximum par archive ZIP. |
| `MAILGUARD_MAX_REPORTS_PER_IMPORT` | Non | `20` | Rapports XML maximum par import. |
| `MAILGUARD_MAX_RECORDS_PER_REPORT` | Non | `10000` | Éléments `<record>` maximum par rapport (cf. §4.2). |
| `MAILGUARD_MAX_CONTENT_LENGTH` | Non | `12582912` (12 Mio) | Limite appliquée par Flask à la requête HTTP. Doit rester ≥ la limite fichier, sinon refus au démarrage. |
| `FLASK_DEBUG` | Non | `0` | **Laisser à 0.** Active le débogueur interactif Werkzeug, qui n'a pas été audité. |
| `MAILGUARD_AI_ENABLED` | Non | `0` | `0` = aucune requête IA, aucun modèle requis. |
| `MAILGUARD_OLLAMA_URL` | Seulement si `MAILGUARD_AI_ENABLED=1` | `http://127.0.0.1:11434` | Doit être une adresse de boucle locale, sauf `MAILGUARD_OLLAMA_ALLOW_REMOTE=1`. |
| `MAILGUARD_OLLAMA_MODEL` | Seulement si `MAILGUARD_AI_ENABLED=1` | vide | Doit nommer un modèle **déjà présent** en local ; un nom vide refuse le démarrage quand l'IA est activée. |
| `MAILGUARD_OLLAMA_TIMEOUT_SECONDS` | Non | `10` | Borné 0,5-120 s. |
| `MAILGUARD_OLLAMA_MAX_INPUT_CHARS` | Non | `4000` | Borné 200-20000. |
| `MAILGUARD_OLLAMA_MAX_OUTPUT_TOKENS` | Non | `300` | Borné 32-2000. |
| `MAILGUARD_OLLAMA_ALLOW_REMOTE` | Non | `0` | **Laisser à 0** sauf/opt-in explicite et comprehensible (§4.3). |

Une valeur numérique illisible ou incohérente (par exemple
`MAILGUARD_MAX_ARCHIVE_MEMBERS=beaucoup`) **refuse le démarrage** avec un message
nommant la variable ; aucune limite n'est jamais désactivée silencieusement.

`.env` existant n'a **pas** été modifié par cette étape (il n'existe pas).

### 3.4 Base de données et démarrage

**Il n'existe aucune commande dédiée d'initialisation de la base.** Ne pas en
inventer une. La base est créée ou mise à niveau **automatiquement** au démarrage
par `app/main.py:71` → `StockageAnalyses.initialiser()`, qui applique les
migrations manquantes dans l'ordre, **sans jamais effacer de données**.

```bash
.venv/bin/python -m app.main
```

Options facultatives : `--host`, `--port`, `--debug` (développement local
uniquement). Elles surchargent la configuration, qui est **revalidée** après
surcharge.

Emplacement par défaut : `data/mailguard.sqlite3`, **relatif au répertoire
depuis lequel le processus est lancé**. Lancer la commande depuis un autre
répertoire crée donc une base différente : lancer depuis la racine du dépôt.

**Sans `.env` valide, le démarrage échoue** — comportement vérifié :

```
app.core.errors.ConfigurationErreur: FLASK_SECRET_KEY is missing. Generate one with:
python -c "import secrets; print(secrets.token_hex(32))" then store it in the .env file.
```
Code de sortie **1**. C'est normal et sans danger : l'application n'est pas
démarrée à moitié.

**Écoute par défaut : `127.0.0.1`, port `5000`** (`app/config.py:50-51`).
Vérifié par `ss -tlnp` sur le serveur de contrôle :

```
LISTEN 0 128  127.0.0.1:5123  0.0.0.0:*  users:(("python",pid=35468,fd=3))
```

Le serveur n'écoute **que** sur la boucle locale.

**Accès navigateur :** <http://127.0.0.1:5000/>

**Arrêt :** `Ctrl+C` dans le terminal du serveur.

**Comment confirmer que le démarrage a réussi.** Il n'existe **aucun endpoint de
santé** et il ne faut pas en inventer un. Trois vérifications :

1. Le journal contient `* Running on http://127.0.0.1:<port>` et
   `* Debug mode: off` ;
2. une requête HTTP renvoie 200 :
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5000/
   ```
   → `200` ;
3. le fichier de base existe et sa version de schéma vaut 1 :
   ```bash
   ls -l data/mailguard.sqlite3
   python3 -c "import sqlite3;c=sqlite3.connect('data/mailguard.sqlite3');print('schema',c.execute('PRAGMA user_version').fetchone()[0])"
   ```

> **À savoir :** la ligne de journal `History database initialized (schema
> version 1) at …` prévue par `app/main.py:72` **n'est jamais émise**. Le niveau
> du logger Flask est `NOTSET` et le niveau effectif par défaut est `WARNING`, donc
> les messages `INFO` sont filtrés. La base est bien créée (vérifié :
> `user_version=1`, table `analyses` présente), mais **l'opérateur ne voit aucune
> confirmation positive dans le journal**. C'est pourquoi les vérifications 2 et 3
> ci-dessus sont nécessaires.

### 3.5 Tests et vérification statique

Commandes **supportées par le dépôt** (`pyproject.toml` ne déclare que
`[tool.pytest.ini_options]` — **aucun outil de lint ou de typage n'est
configuré** ; il n'existe donc aucune commande `ruff`/`mypy`/`flake8` à lancer).

```bash
# Suite complète
.venv/bin/python -m pytest -q

# Vérification de compilation
.venv/bin/python -m compileall -q app tests

# Un fichier de test ciblé
.venv/bin/python -m pytest -q tests/test_web.py
.venv/bin/python -m pytest -q tests/test_audit_etape11.py
```

`pytest` est configuré avec `testpaths = ["tests"]` et `pythonpath = ["."]`, donc
la commande doit être lancée **depuis la racine du dépôt**.

Résultats observés — voir §5 pour le détail et les codes de sortie.

### 3.6 Parcours utilisateur réel

Routes confirmées dans `app/api/routes.py` :

| Route | Méthode | Usage |
| --- | --- | --- |
| `/` | GET | Accueil |
| `/upload` | GET, POST | Formulaire d'import et traitement |
| `/history` | GET | Historique |
| `/history/<id>` | GET | Rapport stocké |
| `/history/<id>/delete` | **POST uniquement** | Suppression |
| `/history/<id>/export.json` | GET | Export JSON |
| `/history/<id>/export.csv` | GET | Export CSV |

**Formats :** `.xml`, `.xml.gz`, `.zip`. Un ZIP peut contenir plusieurs rapports
XML et des répertoires ; les fichiers ordinaires non pris en charge y sont
ignorés **et listés** dans le rapport (jamais silencieusement). Archive imbriquée,
membre chiffré, lien symbolique, chemin piégé : refusés.

**Parcours, tel que vérifié sur un serveur réel :**

1. **Accueil** → bouton « Upload a DMARC report » (`/` → `/upload`).
2. **Import** : champ fichier étiqueté « DMARC report file », bouton « Analyze
   this report ». Un jeton CSRF est requis.
3. **Rapport** (`DMARC analysis result`) : huit sections — Report identification,
   Quantitative summary, Sources and results, Deterministic findings, Analysis
   briefing, Import record, AI-assisted explanation, Print and export.
4. **Historique** : `History` dans la barre de navigation. La page affiche
   « Showing the 20 most recent analyses of N stored » ; le total réel est
   affiché, la liste n'est jamais présentée comme exhaustive.
5. **Relecture** : lien « View report » → bannière « Viewing a stored analysis ».
   Le parseur et le moteur **ne sont pas relancés**.
6. **Suppression** : bouton « Delete » de la ligne, envoi POST avec jeton.
   **Immédiate et irréversible**, sans corbeille ni confirmation JavaScript. Un
   `GET` sur la route renvoie **405** et ne supprime rien.
7. **Exports** : « Download JSON » et « Download CSV (sources) », tous deux
   rattachés à l'identifiant numérique de l'analyse affichée.
8. **Impression** : bouton « Print report » → boîte d'impression native du
   navigateur ; choisir « Save as PDF » pour un PDF. **Sans JavaScript**, le menu
   d'impression du navigateur donne la même mise en page.

**Doublons :** l'empreinte SHA-256 est calculée sur les octets exacts reçus. Un
contenu **binaire identique** déjà importé ne crée aucune ligne : la page
annonce « already been imported » et affiche l'analyse existante. Un même rapport
fourni sous une autre forme (XML vs ZIP) produit une ligne distincte, la
déduplication portant sur le contenu binaire et non sur le sens.

> **Ne jamais déposer un rapport réel client comme fixture de test.** Les
> fixtures de `tests/fixtures/` sont synthétiques. Pour un essai manuel, utiliser
> un fichier de démonstration dans un dossier temporaire hors du dépôt.

### 3.7 Ollama optionnel

L'application est **pleinement utilisable sans Ollama** — c'est le mode par
défaut, et il a été vérifié sur ce poste où `ollama` est absent.

**Laisser l'IA désactivée (par défaut, recommandé) :** ne rien faire.
`MAILGUARD_AI_ENABLED=0` ⇒ aucune requête, aucun modèle requis. La section «
AI-assisted explanation » affiche « AI narration is disabled in this
installation. »

**Activer la narration locale** (choix explicite de l'utilisateur) :

1. Installer Ollama **séparément** et le démarrer (`ollama serve`). L'application
   ne le lance jamais et ne télécharge jamais de modèle.
2. Télécharger **une fois, à la main**, un modèle de petite taille adapté au
   matériel, puis vérifier sa présence :
   ```bash
   ollama list          # le modèle doit apparaître
   curl -s http://127.0.0.1:11434/api/tags   |  sert à vérifier que le service répond
   ```
3. Dans `.env` :
   ```
   MAILGUARD_AI_ENABLED=1
   MAILGUARD_OLLAMA_URL=http://127.0.0.1:11434
   MAILGUARD_OLLAMA_MODEL=<nom exact renvoyé par « ollama list »>
   ```
4. **Redémarrer** l'application. Sans ces deux dernières valeurs, le démarrage
   est refusé avec un message nommant la variable fautive.

**Diagnostiquer une indisponibilité :**

```bash
curl -s -m 3 -o /dev/null -w "%{http_code}\n" http://127.0.0.1:11434/   # 000 = service absent
ollama list                                                           # modèles disponibles
```

Si Ollama est absent, lent ou mal configuré, **l'import réussit quand même**, le
rapport et le briefing déterministes sont inchangés, et la page affiche « Local
AI is unavailable » avec le motif (par exemple `ConnectionError`, `ReadTimeout`).

**Revenir à l'IA désactivée :** `MAILGUARD_AI_ENABLED=0` puis redémarrer.

> **Ce qui n'est pas vérifié :** la compatibilité réelle avec un modèle Ollama.
> Tous les tests d'adaptateur utilisent un transport HTTP simulé ; seules la
> connexion refusée réelle et un timeout réel ont été observés. **Un test simulé
> ne prouve pas la compatibilité avec un modèle réel.**

### 3.8 Dépannage

| Symptôme | Cause probable | Solution |
| --- | --- | --- |
| `Python 3.10 or older is not supported` | Interpréteur trop ancien | `python3 --version` ; utiliser Python ≥ 3.11 |
| `The virtual environment was not created successfully because ensurepip is not available` | Module `venv` absent du Python système | `sudo apt install python3-venv`, puis recréer `.venv` |
| `No module named flask` | Environnement virtuel non activé | `source .venv/bin/activate`, ou remplacer `python` par `.venv/bin/python` |
| `No module named named 'app'` | Commande lancée hors de la racine du dépôt | `cd` vers la racine ; `pytest` a besoin de `pythonpath = ["."]` |
| `ConfigurationErreur: FLASK_SECRET_KEY is missing` | `.env` absent ou clé non renseignée | `cp .env.example .env` puis générer une clé (§3.3) |
| `FLASK_SECRET_KEY must contain at least 32 characters` | Clé trop courte | Régénérer avec `secrets.token_hex(32)` |
| `OSError: [Errno 98] Address already in use` | Port occupé | Changer `MAILGUARD_PORT` dans `.env`, ou utiliser `--port 5050` |
| `MAILGUARD_MAX_CONTENT_LENGTH must be greater than or equal to …` | Limite HTTP inférieure à la limite fichier | Corriger la valeur dans `.env` |
| `The format of « fichier » is not supported` | Extension autre que `.xml`, `.xml.gz`, `.zip` | Renommer ou convertir |
| `the content is not XML although the file format announces it` | Fichier renommé `.xml` sans XML dedans | Utiliser le vrai rapport |
| `the report is unreadable or truncated` | XML incomplet (téléchargement interrompu) | Retélécharger le rapport |
| `entry « ../x.xml » escapes the archive root` | Chemin piégé dans le ZIP — **comportement de sécurité, pas un bug** | Demander un ZIP propre à l'émetteur |
| `the ZIP archive is empty` | Archive sans membre | Vérifier l'archive |
| `the uploaded file exceeds the … byte limit` | Fichier trop volumineux | Respecter la limite affichée sur la page d'import |
| `The report contains N records, the limit is M per report` | Trop de lignes `<record>` | Lever `MAILGUARD_MAX_RECORDS_PER_REPORT` **en connaissance de cause**, ou demander un rapport plus petit |
| `The local history database could not be opened` / `is not a usable SQLite database` | Fichier de base corrompu ou non-SQLite | Renommer `data/mailguard.sqlite3` (l'historique sera perdu ; aucune donnée n'est effacée automatiquement) |
| `The history database is at version N, while this software supports version 1` | Base créée par une version plus récente | Ne pas lancer une version plus ancienne sur cette base |
| `The stored results are incomplete or invalid` | Ligne d'historique endommagée | Ouvrir `/history/<id>` directement pour les autres entrées ; la ligne fautive doit être supprimée ou la base restaurée depuis une sauvegarde |
| `Local AI is unavailable` | Ollama arrêté, absent, ou modèle indisponible | Voir §3.7 ; l'analyse déterministe reste valide |
| Page imprimée mal mise en page | Moteur d'impression du navigateur | Préférer Firefox ou Chromium ; la pagination n'est pas contrôlable depuis l'application |
| Page illisible / couleurs insuffisantes | Aucune vérification visuelle n'a été faite | Constat enabler |

**Aucune de ces solutions ne consiste à désactiver une protection.** En
particulier : ne pas mettre `FLASK_DEBUG=1`, ne pas mettre
`MAILGUARD_OLLAMA_ALLOW_REMOTE=1`, et ne pas fixer `MAILGUARD_HOST=0.0.0.0`.

---

## 4. Frontière de sécurité et risques résiduels

### 4.1 Usage local uniquement — limite structurelle

**L'application n'a ni authentification ni autorisation.** Aucun compte, aucun
rôle, aucun jeton d'API. Il n'existe dans le code aucun mécanisme de contrôle
d'accès : ce n'est pas un oubli, c'est hors périmètre selon
`01_PRODUCT_SPEC.md` (« Comptes utilisateurs, multi-tenant ou cloud » sont
explicitement hors périmètre).

**Conséquence directe :** quiconque peut **atteindre le port** peut importer,
consulter l'historique **et supprimer des analyses**. L'accès est protégé par la
seule adresse d'écoute.

**Contrôle vérifié :** le défaut est `127.0.0.1` (`app/config.py:50`), confirmé à
l'exécution par `ss -tlnp` — le socket n'écoute que sur `127.0.0.1`.

En conséquence :

- **Usage prévu :** poste de travail de confiance, un seul opérateur, réseau
  local personnel.
- **Ne pas exposer directement** cette application à un LAN, un réseau public,
  une passerelle inverse ou Internet, en l'état.
- **Ne pas utiliser `MAILGUARD_HOST=0.0.0.0` comme contournement de commodité.**
  Cela rendrait immédiatement accessible à tout le réseau la suppression
  d'historique, sans aucune authentification.
- **`SESSION_COOKIE_SECURE=False`** (`app/__init__.py:53`) est **approprié** pour
  une écoute HTTP sur la boucle locale : le cookie ne quitte jamais la machine.
  Ce serait **inadapté** à une exposition HTTPS, car le cookie transitait alors en
  clair sur le réseau. Ce n'est pas une configuration de production.
- Le serveur utilisé est celui de développement de Werkzeug, qui affiche
  lui-même `WARNING: This is a development server. Do not use it in a production
  deployment.` **Cette application n'est pas prête pour la production et ne doit
  pas être présentée comme telle.**

Aucune authentification n'a été ajoutée et l'architecture de déploiement n'a
pas été modifiée à cette étape.

### 4.2 Épuisement de ressources et limites d'entrée

**Limites effectivement implémentées et vérifiées :**

| Limite | Défaut | Vérification |
| --- | --- | --- |
| Requête HTTP (`MAX_CONTENT_LENGTH`) | 12 Mio | 413 vérifié en réel et en test |
| Fichier téléversé (`max_upload_bytes`) | 10 Mio | refus testé |
| Volume décompressé cumulé | 50 Mio | GZIP et ZIP testés, y compris bombes |
| Membres par archive | 100 | testé |
| Rapports par import | 20 | testé |
| `<record>` par rapport | 10 000 | testé (étape 11, F1) |
| Longueur des champs texte | 1024 / 512 / 256 | testé (étape 11, F2) |

**Risques résiduels — aucun n'est éliminé, tous sont documentés :**

1. **Le plafond de records ne plafonne pas tout.** Il borne les éléments
   `<record>`, pas le nombre total d'éléments XML ni le nombre de résultats
   bruts (`auth_results/spf`, `auth_results/dkim`) par record. Un rapport peut
   porter de nombreux résultats bruts tout en restant sous 10 000 records.
2. **Le répertoire central d'un ZIP est traité avant le contrôle du nombre de
   membres.** `zipfile.infolist()` est appelé dans `_importer_zip` avant
   `_verifier_volume`. Sur une archive de 10 Mio, ce travail est borné par la
   taille téléversée, mais il a lieu avant le refus applicatif.
3. **Les limites en octets n'établissent pas une borne dure complète sur la
   mémoire de pointe.** Elles bornent les données, pas toute leur expansion. Les
   mesures de l'étape 11 (corrections appliquées) montrent 61 Mio pour une charge
   de 43 Kio représentant 10 000 records, mais il ne s'agit pas d'une preuve
   mathématique d'absence d'amplification.
4. **Aucun quota cumulatif ni limitation de débit.** La mémoire est bornée **par
   requête**, pas par unité de temps. Un opérateur peut enchaîner les imports.
   Un tel contrôle relève d'un proxy ou d'une exposition réseau, hors périmètre
   d'une application locale.
5. **Aucune revendication d'absence de déni de service n'est faite.** Une
   limitation existe, elle n'est pas une garantie.

### 4.3 IA : sécurité et fiabilité

**L'analyse déterministe reste autoritative.** Vérifié par construction
(`app/services.py` ne transmet que l'analyse ; l'IA ne renvoie que du texte) et
par 22 tests dédiés (`test_la_narration_ne_modifie_aucune_metrique_deterministe`,
`test_export_json_ne_contient_pas_de_narration`, …). **La narration n'est jamais
stockée, exportée, ni utilisée pour reconstruire un rapport.**

**Limites à connaître :**

- **L'intégration réelle n'est pas vérifiée.** `ollama` est absent de ce poste.
  Statut : **`NOT TESTED — real Ollama/model integration`**. Le contrat supposé
  est l'API `/api/chat` avec `stream: false` et un champ `message.content`.
- **Le garde-fou de contenu est heuristique.** `MOTIFS_INTERDITS`
  (`app/ai/ollama_client.py`) filtre des formulations courantes (changement de
  politique, jugement de source, balise `<script`), pas toutes les formulations
  possibles. La protection réelle est la validation stricte du schéma et le repli
  déterministe.
- **La résistance à l'injection de prompt est en couches, mais repose encore sur
  le modèle.** Les données importées sont encadrées comme non fiables, le prompt
  est borné et tronqué, la sortie strictement validée — mais aucune défense ne
  peut garantir qu'un modèle local obéira. C'est pourquoi la sortie est rejetée
  en bloc dès qu'une contrainte est violée.
- **`MAILGUARD_OLLAMA_ALLOW_REMOTE=1` envoie les constats sur le réseau.** C'est
  un choix explicite de l'utilisateur, jamais un défaut. La valeur par défaut est
  `0`, et l'endpoint doit être une boucle locale sinon.
- **Une narration IA n'est pas un verdict de sécurité.** Elle ne peut ni calculer,
  ni corriger, ni remplacer un chiffre, un verdict ou une politique. L'écran la
  présente comme un complément, jamais comme une autorité.

### 4.4 Autres limites connues — statut revérifié à cette étape

| Limite | Statut revérifié le 2026-10-16 |
| --- | --- |
| Chemin de la base dans le journal console | **Le code existe (`app/main.py:72`) mais la ligne n'est jamais émise** : niveau de logger Flask `NOTSET`, niveau effectif `WARNING`. Le journal réel ne contient ni chemin ni mention de base. **L'affirmation de `docs/SECURITY_AUDIT.md` F10 est donc inexacte et a été corrigée.** Effet de bord : aucune confirmation positive d'initialisation non plus (§3.4). |
| Briefings stockés antérieurement possibly en français | **Confirmé et fonctionnel** : un enregistrement de démonstration contenant des textes français a été relu tel quel (`Briefing` revalidé, `total_messages` revalidé en `int`). Comportement voulu. |
| Aucune vérification visuelle d'impression | **Confirmé** : aucun navigateur dans cet environnement. Le CSS `@media print` et `print.js` existent et sont servis en 200, mais le rendu n'a pas été vu. |
| Aucun test de charge ou de concurrence à l'échelle | **Confirmé** : seul le verrou de narration (`threading.Lock`) et la contrainte `UNIQUE` sont testés, à faible échelle. |
| Aucune mesure WCAG | **Confirmé** : le contraste des couleurs est **déclaré** conforme par l'auteur, **jamais mesuré**. |
| `app/ai` chargé sur le chemin HTTP même IA désactivée | **Confirmé** (constat F7) : `POST /upload` et `GET /history/<id>` chargent le paquet pour construire le statut neutre. Sans effet sur la confidentialité. Documenté dans le README. |
| Aucun endpoint de santé | **Confirmé** : ni route ni commande de vérification d'état. La méthode de vérification est donnée en §3.4. |
| `pyproject.toml` non installable en paquet | **Confirmé** : aucune table `[build-system]`, donc `pip install .` échoue. Choix assumé (exécution depuis les sources), signalé dans ce guide. |
| Rapport déposé à la racine du dépôt | Non ignoré par `.gitignore` : les rapports importés doivent être placés hors du dépôt, ou dans `imports/`, `uploads/`, `data/` (déjà ignorés). |

### 4.5 Points de sécurité positifs vérifiés

- **CSP stricte** : `default-src 'none'; style-src 'self'; script-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'`. Ni `unsafe-inline`, ni `unsafe-eval`, ni source distante.
- **En-têtes** : `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` — présents aussi sur les réponses d'erreur.
- **Échappement** : aucune occurrence de `|safe`, `Markup(` ou `{% raw %}` dans `app/`.
- **SQL** : requêtes paramétrées partout ; le seul SQL construit par interpolation est `PRAGMA user_version = <int>` avec un entier interne.
- **XML** : `defusedxml` avec `forbid_dtd`, `forbid_entities`, `forbid_external`.
- **ZIP** : aucune extraction sur disque.
- **CSV** : injection de formule neutralisée par un `'` préfixe.
- **Exports** : nom de fichier construit depuis le seul entier de l'identifiant ; aucune donnée importée n'atteint un en-tête HTTP.
- **En-têtes d'interface** : une seule balise `<script>` par page, celle du script local autorisé.

---

## 5. Résultats de vérification

### 5.1 Suite de tests — environnement du dépôt

```
$ .venv/bin/python -m pytest -q
417 passed in 6.00s
code de sortie : 0
```

### 5.2 Suite de tests — environnement virtuel neuf créé à cette étape

Preuve que le chemin d'installation documenté est reproductible :

```
$ python3 -m venv /tmp/opencode/verif-venv
$ /tmp/opencode/verif-venv/bin/python -m pip install -r requirements-dev.txt
Successfully installed Flask-3.1.3 … werkzeug-3.1.9          code de sortie : 0

$ /tmp/opencode/verif-venv/bin/python -m pytest -q
417 passed in 6.26s
code de sortie : 0
```

### 5.3 Compilation

```
$ .venv/bin/python -m compileall -q app tests
code de sortie : 0   (aucune sortie)

$ /tmp/opencode/verif-venv/bin/python -m compileall -q app tests
code de sortie : 0   (aucune sortie)
```

### 5.4 Récapitulatif des vérifications

| Vérification | Résultat | Statut |
| --- | --- | --- |
| Suite complète, venv du dépôt | 417 passed, exit 0 | fait |
| Suite complète, venv neuf | 417 passed, exit 0 | fait |
| Compilation `app tests` | exit 0 | fait |
| Installation depuis `requirements-dev.txt` | 25 paquets, exit 0 | fait |
| Démarrage sans `.env` | `ConfigurationErreur`, exit 1 | fait |
| Démarrage réel, port 5123 | écoute `127.0.0.1` uniquement | fait |
| Parcours web complet (import/historique/relecture/exports/suppression) | tous 200 | fait |
| Parcours avec réseau non local bloqué | AUCUNE connexion tentée | fait |
| Erreurs utilisateur | 5 messages clairs, aucune trace | fait |
| Invariants DMARC sur fixtures | tous vrais | fait |
| `.gitignore` | 14/14 motifs efficaces | fait |
| Fixtures synthétiques | domaines RFC 2606, IP RFC 5737/3849 | fait |
| Secrets versionnés | aucun | fait |
| `git diff --check` | aucun défaut d'espace | fait |
| **Intégration Ollama avec un vrai modèle** | `ollama` absent du poste | **NOT TESTED** |
| **Rendu visuel et aperçu d'impression** | aucun navigateur | **NOT TESTED** |
| **Mesure de contraste WCAG** | aucun outil | **NOT TESTED** |
| **Charge / concurrence à l'échelle** | non characterisation | **NOT TESTED** |

### 5.5 Intégrité des données et des secrets

- `data/` n'a **jamais** été créé dans le dépôt ; `git status --short` ne le
  mentionne pas.
- Aucun rapport réel client n'a été utilisé : seules les fixtures synthétiques
  du dépôt ont été employées.
- Aucun enregistrement n'a été ajouté à une base de l'utilisateur : tous les
  tests ont utilisé des bases temporaires créées puis abandonnées dans `/tmp`.
- Le serveur de contrôle a écrit dans `/tmp/opencode/runbook/h.sqlite3`, puis a
  été arrêté (`port 5123` fermé, aucun processus `app.main` restant). Les trois
  enregistrements qu'il contient proviennent de fixtures synthétiques.
- `.env` n'a pas été créé ni modifié.
- Aucun modèle n'a été téléchargé, aucun service IA lancé, aucune requête IA
  émise : `ollama` est absent du poste.
- Aucun test n'a été supprimé, `skip`, `xfail` ou affaibli.
- Aucun commit, aucune étiquette, aucune publication, aucun `push`.

---

## 6. Verdict de préparation

Trois catégories distinctes. Elles ne sont **pas** équivalentes.

### 6.1 Prêt pour le développement et les tests locaux — **OUI**

| Preuve | |
| --- | --- |
| Installation reproductible de zéro | 25 paquets, exit 0, venv neuf |
| Suite complète | **417 passed**, exit 0, dans deux environnements distincts |
| Compilation | exit 0 |
| Serveur démarrable, écoute boucle locale | vérifié par `ss -tlnp` |
| Parcours fonctionnel complet | vérifié sur serveur réel |
| Erreurs actionnables | vérifiées sur 5 cas réels |

### 6.2 Prêt pour un usage local routinier, avec précautions — **OUI, SOUS RÉSERVES EXPLICITES**

L'analyse déterministe est complète, exacte et testée ; l'interface est
fonctionnelle ; l'historique, les exports et l'impression sont opérationnels ;
l'application fonctionne sans Internet et sans IA.

**Précautions à respecter :**

1. **Rester sur `127.0.0.1`.** Ne pas exposer le port, en aucune circonstance.
2. **Créer `.env` avec une clé forte**, et vérifier qu'elle n'est pas versionnée.
3. **Lancer depuis la racine du dépôt**, sinon la base créée n'est pas celle
   attendue.
4. **La suppression est irréversible** : sauvegarder `data/mailguard.sqlite3` si
   l'historique a de la valeur.
5. **Ne pas déposer de rapport réel à la racine du dépôt** (il ne serait pas
   ignoré par Git).
6. **Accepter que la narration IA ne soit pas vérifiée** et la laisser
   désactivée par défaut tant qu'aucun modèle réel n'a pas été testé
   explicitement.
7. **Accepter que le rendu visuel n'ait pas été contrôlé** et vérifier une fois
   soi-même l'affichage et l'impression.

### 6.3 Prêt pour un déploiement réseau ou en production — **NON**

| Motif | Preuve |
| --- | --- |
| **Aucune authentification ni autorisation** | aucun contrôle d'accès dans le code ; quiconque atteint le port peut supprimer l'historique |
| **Serveur de développement uniquement** | Werkzeug affiche lui-même l'avertissement « Do not use it in a production deployment » |
| **`SESSION_COOKIE_SECURE=False`** | incompatible avec une exposition HTTPS |
| **Aucune protection de débit ni quota** | borné par requête, pas dans le temps |
| **TLS absent, journalisation minimale** | pas de configuration ni de documentation pour un déploiement réseau |
| **Audit de sécurité limité** | revue de code et tests automatisés ; **ni test d'intrusion, ni certification, ni audit de code par un tiers** |

Ce verdict ne serait modifié qu'après, au minimum : ajout d'une authentification,
déploiement derrière un serveur WSGI de production avec terminaison TLS, et un
nouvel audit. **Aucune de ces actions n'est entreprise ici.**

### 6.4 Verdict global

**Étape 12 terminée.** Zéro critère `FAIL`. Deux `PARTIAL` sur 22 critères
applicables, tous deux explicitement documentés : l'intégration IA sans modèle
réel (non testable sur ce poste) et une documentation README qui a été corrigée
à cette étape. Les 24 items de `05_TEST_STRATEGY.md`/`03_SECURITY_PRIVACY.md`
sont couverts ou explicitement marqués.

L'état « terminé » signifie que **la vérification et la documentation sont
complètes**, pas que le logiciel est sans défaut. Les limites des §4 et §5.4
font partie du résultat.

---

## 7. Actions outstanding

### 7.1 Requises avant tout usage local

| # | Action | Pourquoi | Gravité si ignorée |
| --- | --- | --- | --- |
| 1 | Créer `.env` et y placer une `FLASK_SECRET_KEY` d'au moins 32 caractères | L'application **refuse de démarrer** sans elle (vérifié) | **Bloquant** |
| 2 | Ne pas modifier `MAILGUARD_HOST` ; garder `127.0.0.1` | Frontier de sécurité unique de l'application | **Critique** |
| 3 | Lancer depuis la racine du dépôt | Sinon la base est créée ailleurs | Modéré |
| 4 | Garder `FLASK_DEBUG=0` | Le débogueur interactif n'a pas été audité | Élevé |
| 5 | Sauvegarder `data/mailguard.sqlite3` avant toute suppression d'historique | Suppression irréversible, sans corbeille | Modéré |
| 6 | Ne pas déposer de rapport réel à la racine du dépôt | `.gitignore` ne couvre pas ce cas | Modéré |

### 7.2 Recommandées avant usage routinier

| # | Action | Pourquoi |
| --- | --- | --- |
| 7 | Vérifier une fois le rendu de l'interface et l'aperçu d'impression dans un navigateur | Aucun contrôle visuel n'a été possible ici |
| 8 | Mesurer le contraste des couleurs (WCAG AA) si l'accessibilité est un critère | Les couleurs sont déclarées conformes, jamais mesurées |
| 9 | Consigner `docs/SECURITY_AUDIT.md`, `docs/FINAL_ACCEPTANCE_AUDIT.md` dans Git | Ils ne sont pas encore versionnés |

### 7.3 Requises avant toute exposition réseau ou production — hors périmètre actuel

| # | Action |
| --- | --- |
| 10 | Ajouter une authentification et une autorisation (absentes par conception) |
| 11 | Servir l'application derrière un serveur WSGI de production, avec terminaison TLS |
| 12 | Passer `SESSION_COOKIE_SECURE=True` sous HTTPS et durcir les cookies |
| 13 | Mettre en place une limitation de débit et un quota cumulatif |
| 14 | Faire réaliser un audit de sécurité par un tiers, indépendant de celui-ci |
| 15 | Tester l'intégration IA contre un vrai modèle local, si la narration doit être activée |

### 7.4 Points de dette technique documentés, non bloquants

| # | Point |
| --- | --- |
| 16 | `app/ai` est chargé sur le chemin HTTP même IA désactivée (constat F7) — sans effet de confidentialité |
| 17 | La ligne de journal d'initialisation de la base n'est jamais émise (niveau de logger) — §4.4 |
| 18 | `pyproject.toml` n'est pas installable en paquet — choix assumé, à connaître |
| 19 | L'historique est borné à 20 entrées sans pagination |
| 20 | Les briefings enregistrés avant la mise à jour en anglais restent dans leur langue d'origine — comportement voulu |