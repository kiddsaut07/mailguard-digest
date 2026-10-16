# Journal d'implémentation — MailGuard Digest

Ce journal est mis à jour à la fin de chaque étape de `PROMPTS_ETAPES.md`.
Il n'y contient que des commandes réellement exécutées et des résultats observés.

Dernière mise à jour : 2026-10-16 (étape 12)

## 1. Audit initial de l'environnement

Commandes exécutées le 2026-10-15 avant toute modification :

| Commande | Résultat observé |
| --- | --- |
| `ls -la` | Le dépôt ne contenait que les 11 fichiers Markdown du kit. Aucun code applicatif. |
| `git status` | `fatal: ni ceci ni aucun de ses répertoires parents n'est un dépôt git` — aucun dépôt Git initialisé. |
| `cat /etc/os-release` | Kali GNU/Linux Rolling 2025.2, conforme à l'environnement cible du kit. |
| `grep -m1 'model name' /proc/cpuinfo` | Intel(R) Core(TM) i5-4300U CPU @ 1.90GHz, conforme au kit. |
| `free -m` | 3 857 Mio de mémoire totale, conforme à la cible 4 Go. |
| `python3 --version` | `Python 3.13.12` (le kit exige 3.11+, la contrainte est respectée). |
| `python3 -c "import venv"` / `import ensurepip` | Disponibles : création d'environnement virtuel possible hors réseau ultérieur. |
| `python3 -m pip list` | Flask 3.1.0, Pydantic 2.10.6, defusedxml 0.7.1, requests 2.32.3 présents au niveau système ; **pytest absent**. |

Points relevés pendant l'audit :

1. `PROMPT_DE_DEMARRAGE.txt` est annoncé au point 11 de `README.md` mais n'existe pas dans le dossier. Aucune action corrective décidée ici : le kit de référence reste intact.
2. Le dossier n'est pas un dépôt Git. `.gitignore` est tout de même créé (exigence de `08_DEFINITION_OF_DONE.md`). L'initialisation Git n'est pas faite automatiquement ; commande proposée : `git init`.
3. `pytest` n'étant pas installé au niveau système et l'environnement système étant partagé, un environnement virtuel local `.venv` (ignoré par Git) a été créé pour la suite du projet.

## 2. Configuration mise en place à l'étape 0

| Fichier | Raison |
| --- | --- |
| `.gitignore` | Exclut venv, caches Python, `.env`, base SQLite locale, rapports importés et secrets (exigences qualité de `08_DEFINITION_OF_DONE.md`). |
| `requirements.txt` | Dépendances d'exécution minimales : Flask, Pydantic, defusedxml, requests (Ollama local facultatif), python-dotenv. |
| `requirements-dev.txt` | Dépendances de test : `pytest`, plus les dépendances d'exécution. |
| `pyproject.toml` | Métadonnées du projet, `requires-python = ">=3.11"` et configuration pytest (`testpaths = ["tests"]`). Liste des versions alignée sur `requirements.txt`. |
| `.env.example` | Modèle de configuration : secret Flask, écoute sur `127.0.0.1`, chemin SQLite, limites d'import de `03_SECURITY_PRIVACY.md`, options Ollama désactivées par défaut. |
| `docs/IMPLEMENTATION_LOG.md` | Ce journal, exigé par l'étape 0. |
| `README.md` | Ajout d'une section « Application » (installation, exécution, tests, limites). Le contenu du kit de référence a été conservé intact. |

Limites initiales reprises telles quelles de `03_SECURITY_PRIVACY.md` point 4 :
10 MiB par fichier compressé, 50 MiB décompressés, 100 membres par archive, 20 rapports par import.
`MAILGUARD_MAX_CONTENT_LENGTH` vaut 12 582 912 octets (12 Mio), soit la limite fichier augmentée d'une petite marge pour l'en-tête multipart, tout en refusant les requêtes HTTP trop volumineuses.

## 3. Vérification de la configuration (résultats réels)

Environnement virtuel créé puis dépendances installées :

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
```

Résultat observé : `Successfully installed Flask-3.1.3 ... defusedxml-0.7.1 pydantic-2.14.1 pytest-8.4.2 python-dotenv-1.2.4 requests-2.34.2` (26 paquets, `.venv` = 47 Mo).

Contrôle d'import des dépendances :

```bash
.venv/bin/python -c "import flask, pydantic, defusedxml, requests, dotenv, pytest; ..."
```

Résultat observé : `flask 3.1.3`, `pydantic 2.14.1`, `defusedxml 0.7.1`, `requests 2.34.2`, `python-dotenv` installé, `pytest 8.4.2`.

Commandes de validation de `05_TEST_STRATEGY.md` à ce stade :

| Commande | Résultat observé |
| --- | --- |
| `.venv/bin/python -m pytest -q` | Code de sortie 5 : aucun test collecté, car le dossier `tests/` n'existe pas encore. Comportement attendu à l'étape 0 (pas de logique métier). Un avertissement `PytestConfigWarning` signale l'absence de fichiers dans `testpaths`. |
| `.venv/bin/python -m compileall -q app` | Message `Can't list 'app'` : le paquet `app/` sera créé à l'étape 1. Aucune erreur de compilation, aucun fichier à compiler. |

Aucun test n'a donc été exécuté avec succès à cette étape, et aucun n'est déclaré comme l'étant.

## 3 bis. Étape 1 — Modèles de données (2026-10-15)

Initialisation Git demandée explicitement par l'utilisateur et effectuée :

```bash
git init
```

Résultat observé : `Dépôt Git vide initialisé dans <répertoire-du-projet>/.git/`.
Aucun fichier supprimé ni écrasé. `git status --short` ne liste que les fichiers non suivis et
n'affiche ni `.venv/` ni `.pytest_cache/` : les exclusions du `.gitignore` sont vérifiées
comme efficaces. Aucun commit n'a été créé, en attente de l'accord de l'utilisateur.

Fichiers ajoutés ou modifiés :

| Fichier | Raison |
| --- | --- |
| `app/__init__.py` | Paquet applicatif, version `0.1.0`. |
| `app/core/__init__.py` | Paquet du cœur métier, sans dépendance Flask ni SQLite. |
| `app/core/models.py` | Modèles Pydantic validés : énumérations, types annotés, métadonnées, politique publiée, résultats bruts, résultats évalués, record, rapport agrégé. |
| `tests/test_models.py` | 37 tests unitaires : objets valides, valeurs hors nomenclature, compteurs négatifs et non entiers, IP invalides, incohérences de période et de champ inconnu. |
| `pyproject.toml` | Ajout de `pythonpath = ["."]` pour que `pytest` trouve le paquet `app` depuis la racine. |

Choix de conception retenus, tous ancrés dans `04_DATA_MODEL_AND_DMARC_RULES.md` :

1. Séparation stricte entre `Record.auth_results` (résultats bruts SPF/DKIM, qui acceptent
   `softfail`, `neutral`, `temperror`, `permerror`) et `Record.policy_evaluated` (verdicts DMARC,
   limités à `pass` et `fail`). La propriété `Record.dmarc_pass` ne lit que les résultats évalués.
2. `DmarcModel` impose `extra="forbid"` : un champ inconnu est refusé au lieu d'être ignoré.
3. `message_count` est un entier strict (`strict=True`, `ge=0`) : `"-1"`, `"100"`, `100.5` et `True`
   sont refusés, `0` est accepté.
4. `source_ip` est validé par `ipaddress` puis normalisé en forme canonique (IPv4 ou IPv6).
5. Les dates sont des datetimes aware convertis en UTC ; une date sans fuseau est refusée et
   `end < begin` est rejeté. Les timestamps Unix restent accessibles par propriétés.
6. Valeurs par défaut uniquement lorsqu'elles sont définies par la RFC 7489 : `adkim=relaxed`,
   `aspf=relaxed`, `pct=100`. `sp` n'est pas remplacé par `p` ; l'application effective est exposée
   par la propriété `PublishedPolicy.effective_subdomain_policy`.
7. `report_id`, `domain`, `header_from` restent facultatifs : aucun identifiant n'est inventé.
8. `DmarcReport.records` exige au moins un record ; `total_messages` est une simple somme des
   compteurs validés, sans taux ni agrégation de dispositions (réservé à l'étape 4).

Résultats réels des commandes de validation après implémentation :

| Commande | Résultat observé |
| --- | --- |
| `.venv/bin/python -m pytest -q` | `37 passed in 0.25s` (code de sortie 0). |
| `.venv/bin/python -m pytest -q tests/test_models.py` | `37 passed in 0.15s` (code de sortie 0). |
| `.venv/bin/python -m compileall -q app` | Code de sortie 0, aucune sortie. |
| `.venv/bin/python -m compileall -q tests` | Code de sortie 0, aucune sortie. |

Aucune fixture XML n'a été créée : les tests construisent des données synthétiques en Python
(domaines `example.*`, plages RFC 5737 et RFC 3849), ce qui suffit à l'étape 1.

## 3 ter. Étape 2 — Parseur XML DMARC (2026-10-15)

Fichiers ajoutés ou modifiés :

| Fichier | Raison |
| --- | --- |
| `app/core/parser.py` | Lecture d'un rapport XML DMARC agrégé vers les modèles validés. 469 lignes, fonctions courtes, aucun accès Flask, SQLite, HTTP ou IA. |
| `app/core/errors.py` | Exceptions métier partagées (`MailGuardError`, `ReportParseError`, `ReportValidationError`). Structure ajoutée hors arborescence cible pour une raison précise : le parseur, l_future lecture d'archives et le moteur de règles doivent lever les mêmes erreurs sans s'importer mutuellement. Les détails techniques restent dans `__cause__`, les messages sont directement affichables. |
| `tests/fixtures/*.xml` (23 fichiers) | Fixtures synthétiques, chacune marquée d'un commentaire XML « FIXTURE SYNTHÉTIQUE — aucun rapport client réel ». |
| `tests/test_parser.py` | 34 tests : documents acceptés et documents refusés, avec vérification des valeurs obtenues dans les modèles. |

Décisions prises pendant l'implémentation :

1. **Alignement `r`/`s` traduits par le parseur, pas par le modèle.** La RFC 7489 publie
   `adkim`/`aspf` sous forme `r` ou `s`, alors que `AlignmentMode` de l'étape 1 ne connaît que
   `relaxed` et `strict`. La traduction est faite dans `_mode_alignement`, qui accepte aussi les
   formes longues `relaxed`/`strict` rencontrées dans quelques outils, et refuse tout le reste avec
   un message nommant la valeur reçue. Les modèles de l'étape 1 n'ont pas été réécrits.
2. **Éléments XML inconnus ignorés, éléments obligatoires vérifiés.** La RFC 7489 autorise des
   extensions (`extra_contact_info`, `policy_evaluated` étendus) : rejeter toute balise non
   prévue ferait échouer des rapports réels. En revanche `report_metadata`, `date_range`,
   `policy_published`, `p`, `record`, `row`, `count`, `disposition`, `spf` et `dkim` évalués sont
   exigés, l'absence étant signalée explicitement.
3. **Textes optionnels vides traités comme absents.** `report_id`, `email`, `domain`,
   `header_from` ou `scope` vides deviennent `None` : le champ reste absent plutôt que de
   recevoir une valeur inventée. Les champs obligatoires vides sont refusés.
4. **Entiers et timestamps lus par expressions régulières**, pas par `int()` : « 10.5 », « 1e3 »,
   chiffres non ASCII ou espaces internes sont refusés avec un message nommant la valeur reçue.
   Le timestamp est converti par `datetime.fromtimestamp(..., tz=utc)` ; un timestamp hors plage
   représentable est refusé.
5. **Période inversée refusée par le modèle**, pas par une second contrôle dans le parseur :
   `DateRange._check_period_order` reste l'unique source de vérité, l'erreur est traduite en
   `ReportValidationError`.
6. **Résultats bruts et résultats évalués lus par des fonctions distinctes** (`_lire_spf`,
   `_lire_dkim` d'un côté ; `_lire_evaluation` de l'autre). Plusieurs signatures DKIM sont toutes
   conservées dans l'ordre du document ; plusieurs éléments `spf` sont acceptés comme une liste
   alors que la RFC 7489 n'en autorise qu'un, pour ne perdre aucune donnée.
7. **Messages d'erreur en français.** Les refus techniques de Pydantic sont traduits par
   `_decrire`, avec la liste des valeurs acceptées pour les énumérations. La cause
   `ValidationError` complète est conservée dans `__cause__` et n'est jamais masquée.
8. **`defusedxml` utilisé avec `forbid_dtd`, `forbid_entities` et `forbid_external` à `True`.**
   Une DTD est refusée par `defusedxml` ; une entité non déclarée est refusée par le parseur sous-jacent,
   ce qui remontait en `ParseError`. Ce cas est détecté dans le message de `ParseError` afin de ne pas
   qualifier à tort le fichier de « tronqué ».
9. **Aucun calcul métier ajouté** : pas de taux, pas de total par disposition, pas de constat. Le
   total exposé reste la simple somme déjà présente dans le modèle à l'étape 1.

Résultats réels des commandes demandées :

| Commande | Résultat observé |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/test_parser.py` | `34 passed in 0.44s` (code de sortie 0). |
| `.venv/bin/python -m pytest -q` | `71 passed in 0.42s` (code de sortie 0), soit 37 tests de l'étape 1 et 34 tests de l'étape 2. |
| `.venv/bin/python -m compileall -q app tests` | Code de sortie 0, aucune sortie. |

Trois défauts ont été trouvés par ces tests et corrigés dans le périmètre de l'étape 2 :
`_element_obligatoire` appelé sans son contexte, `_mode_alignement` qui renvoyait la valeur brute au
lieu du mode traduit, et l'affichage des valeurs autorisées qui itérait sur une chaîne au lieu d'une
liste. Une coquille dans un test (`record.total_messages` au lieu de `rapport.total_messages`) a
également été corrigée : le défaut était dans le test, pas dans le code. Aucun test n'a été assoupli.

## 3 quater. Étape 3 — Importation sécurisée XML, GZIP et ZIP (2026-10-15)

Fichiers créés ou modifiés :

| Fichier | Raison |
| --- | --- |
| `app/core/archive.py` | Importation sécurisée : `import_reports(nom, contenu, limites)` → `ImportResult`. Tout est fait en mémoire, sans fichier temporaire et sans `extractall()`. Aucune dépendance ajoutée : uniquement la bibliothèque standard (`gzip`, `zipfile`, `io`, `zlib`, `stat`, `re`, `dataclasses`). |
| `app/core/errors.py` | Ajout de `ArchiveError`, `ArchiveLimitError` et `UnsafeArchiveError`, toutes dérivées de `MailGuardError`. Aucun code existant n'a été modifié. |
| `tests/test_archive.py` | 59 tests : formats valides, fichiers invalides, limites, cas de sécurité ZIP, ordre déterministe, absence d'écriture sur disque. |
| `docs/IMPLEMENTATION_LOG.md` | Journal de l'étape 3. |
| `README.md` | État d'avancement et résultats de tests. |

Interface publique retenue :

```python
import_reports(nom: str, contenu: bytes, limites: ImportLimits = LIMITES_PAR_DEFAUT) -> ImportResult
```

- `ImportLimits(max_upload_bytes=10 MiB, max_decompressed_bytes=50 MiB, max_archive_members=100, max_reports=20)` :
  valeurs reprises telles quelles de `03_SECURITY_PRIVACY.md` point 4 et de `.env.example`. La lecture
  des variables d'environnement reste hors de cette étape ; les limites sont donc fournies par paramètre.
- `ImportResult(file_name, reports, ignored_entries)` avec `reports : list[DmarcReport]` réellement produits
  par `parse_dmarc_report()` et `total_messages` comme simple somme.

Décisions de sécurité :

1. **Lecture à double barrière.** Un contrôle rapide porte sur les métadonnées annoncées (nombre de
   membres, volume déclaré, nombre de rapports XML), puis un compteur `_Budget` cumulé vérifie les
   octets **réellement lus** membre par membre, par blocs de 64 Kio. La déclaration d'une taille n'est
   jamais suffisante pour valider une archive. Le budget est partagé par tous les membres : un membre ne
   peut pas consommer la marge laissée par les autres.
2. **Une limite atteinte interrompt l'import.** Elle n'est jamais désactivée, jamais contournée, et
   l'exception `ArchiveLimitError` est levée, y compris pour les données fortement compressées (bombes
   GZIP ou ZIP) : la lecture s'arrête dès le bloc qui dépasse.
3. **Aucune extraction, aucun nom utilisé comme chemin.** `extractall()` n'est pas appelé, aucun
   `ZipInfo.filename` n'est interprété comme un chemin disque. Les noms sont pourtant validés et refusés
   s'ils sont absolus, containants `..`, ambigus (`//`, espaces en bord, caractères de contrôle) ou en
   double après normalisation (antislash changé en `/`, casse ignorée). Le nom de fichier téléversé est
   nettoyé pour l'affichage (répertoire retiré, caractères de contrôle supprimés, 200 caractères maximum).
4. **Entrées non ordinaires refusées** : membre chiffré (`flag_bits & 0x1`), lien symbolique
   (`S_ISLNK`), FIFO, socket ou périphérique. Un mode UNIX absent ou sans bits de type, hérité d'un
   création Windows ou DOS, est traité comme un fichier ordinaire.
5. **Politique ZIP explicite.** Répertoire : validé puis ignoré et listé dans `ignored_entries`.
   Fichier `.xml` : lu et analysé. Archive imbriquée (`.zip`, `.gz`, `.xml.gz`, `.tar`, `.tgz`, `.bz2`,
   `.xz`, `.7z`, `.rar`) : refus `UnsafeArchiveError`. Autre fichier ordinaire : ignoré et listé dans
   `ignored_entries`, jamais interprété comme un rapport. Rien n'est ignoré silencieusement.
6. **Échec global.** Un seul membre en échec fait échouer l'import entier ; aucune importation partielle
   n'est renvoyée comme un succès. Le type d'erreur du parseur est conservé (`ReportParseError`,
   `ReportValidationError`) et le nom du membre fautif est ajouté en préfixe, la cause d'origine restant
   dans `__cause__`.
7. **Ordre déterministe** : membres triés par nom, rapports dans cet ordre. Vérifié par deux imports du
   même contenu comparés champ par champ.
8. **Contenu réellement vérifié.** Un contenu qui n'est pas du XML est refusé même si l'extension est
   favorable ; un XML valide mais illisible ou invalide est refusé par le parseur existant, jamais
   reparsé ici. Aucune règle de validation Pydantic n'est dupliquée.
9. **Aucune journalisation** dans ce module : ni le XML, ni les adresses e-mail, ni le contenu des
   entrées ignorées ne sont écrits dans des logs. Le nom de fichier nettoyer est la seule donnée reprise.

Limites de test assumées, signalées plutôt que masquées :

- **Caractère NUL dans un nom de membre** : `zipfile` tronque les noms au caractère NUL à l'écriture
  comme à la lecture (vérifié par essai), le cas n'est donc pas représentable de bout en bout. Le
  garde-fou est testé directement sur une `ZipInfo` fabriquée.
- **Taille réelle supérieure à la taille annoncée** : la bibliothèque standard lit au plus la taille
  annoncée et échoue alors sur le CRC ; le scénario de bout en bout produit donc `ArchiveError`, ce qui
  est vérifié. Aucune archive ZIP honnête ne peut faire mentir sa taille déclarée : la barrière de
  comptage réel (`_Budget`) est donc testée directement, en plus du scénario GZIP fortement compressé
  où elle est la seule protection.

Résultats réels des commandes demandées :

| Commande | Résultat observé |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/test_archive.py` | `59 passed in 0.49s`, code de sortie 0. |
| `.venv/bin/python -m pytest -q` | `130 passed in 0.52s`, code de sortie 0 (37 modèles + 34 parseur + 59 archives). |
| `.venv/bin/python -m compileall -q app tests` | Code de sortie 0, aucune sortie. |

Trois défauts ont été révélés par ces tests et corrigés dans le périmètre de l'étape 3 : les répertoires
n'étaient pas listés dans `ignored_entries`, une archive ZIP vide renvoyait le message « aucun rapport
admissible » au lieu d'un message explicite « archive vide », et une séquence d'échappement invalide dans
une chaîne de documentation produisait un `SyntaxWarning`. Aucune assertion n'a été affaiblie.

## 3 quinquies. Étape 4 — Moteur de règles et briefing déterministes (2026-10-15)

Fichiers créés ou modifiés :

| Fichier | Raison |
| --- | --- |
| `app/core/rules.py` | Métriques, vues par source, constats et détection d'incohérences. Modèles Pydantic figés (`frozen=True`, `extra="forbid"`), cohérents avec `models.py`. |
| `app/core/briefing.py` | Briefing français construit uniquement à partir d'un objet `Analyse`. Aucun calcul, aucun appel réseau. |
| `tests/test_rules.py` | 36 tests de métriques, de sources, de constats et d'incohérences. |
| `tests/test_briefing.py` | 19 tests de contenu, de reproductibilité et d'interdits. |
| `tests/fixtures/rapport_volume_nul.xml` | Rapport synthétique sans aucun message : taux non calculable. |
| `tests/fixtures/rapport_sans_identifiants.xml` | Rapport synthétique sans domaine publié ni identifiant. |
| `tests/fixtures/rapport_autre_domaine.xml` | Second domaine synthétique, pour plusieurs contextes de politique. |
| `docs/IMPLEMENTATION_LOG.md`, `README.md` | Journal et état d'avancement. |

Aucune modification n'a été apportée à `models.py`, `parser.py`, `archive.py` ou `errors.py`.
Les tests construisent leurs entrées en analysant les fixtures avec `parse_dmarc_report()`, donc avec
de véritables objets `DmarcReport` : aucun objet de démonstration n'est injecté dans le code de
production.

Formules implémentées, toutes documentées dans l'en-tête de `rules.py` :

- `total_messages` = somme de `record.message_count` ;
- `messages_pass` = somme des compteurs des records dont `record.dmarc_pass` est vrai, donc d'après
  `policy_evaluated` uniquement et jamais d'après `auth_results` ;
- `messages_fail` = `total_messages - messages_pass` ;
- `taux` = `numerateur / denominateur * 100`, avec `valeur = None` si le dénominateur est nul ;
  l'arrondi n'intervient que dans `Taux.affichage` (une décimale, virgule décimale française) ;
- dispositions et verdicts évalués répartis **en messages**, jamais en nombre de records ;
- résultats bruts comptés en occurrences et conservés dans `ResultatBrutAuthentification`, structure
  distincte qui ne participe à aucun taux.

Décisions prises, avec leur justification :

1. **Aucune moyenne de taux par record** : tous les taux sont pondérés par les compteurs, comme
   l'exige `04_DATA_MODEL_AND_DMARC_RULES.md`.
2. **Taux indisponible plutôt que 0** : `Taux.valeur` vaut `None`, `affichage` renvoie
   « non calculable (aucun message) », et un constat de niveau `indisponible` est produit.
3. **Aucun seuil de volume inventé** : les sources associées à des échecs sont listées avec leur volume
   mesuré, sans qualification de leur nature. Les documents de référence ne fournissant aucun seuil,
   aucun n'a été créé.
4. **Niveaux de constat limités à trois** : `attention`, `info`, `indisponible`. Aucun niveau critique
   n'est créé, faute de base de gravité dans les documents de référence.
5. **Distinction des contextes de politique** : chaque source est rattachée à un `ContexteRapport`
   (index, organisation, domaine publié, identifiant). Deux rapports, même pour une même adresse IP,
   donnent deux vues distinctes : aucune conformité n'est fusionnée entre contextes. Un constat
   `contextes-policiels-multiples` est produit quand un import couvre plusieurs domaines publiés.
6. **Politique décrite, jamais recommandée** : `p=none` produit un constat factuel « politique publiée
   en mode surveillance » dont la limite précise qu'aucune recommandation n'est formulée. Aucun texte
   du moteur ou du briefing ne propose de passer en `quarantine` ou `reject`.
7. **Données inhabituelles distinctes des incohérences** : trois familles sont relevées,
   `INCOHERENCE`, `DONNEE_INHABITUELLE` (record à zéro message, volume total nul) et `DONNEE_MANQUANTE`
   (domaine publié absent, identifiant absent, erreur déclarée par le serveur). Un rapport valide n'est
   jamais rejeté pour des résultats inhabituels.
8. **Contrôle des dispositions exposé séparément** : `verifier_coherence_dispositions()` est publique
   et testé directement. Après validation Pydantic, la somme des dispositions est structurellement
   égale au total : l'incohérence est inatteignable en production, et le test travaille sur des
   valeurs construites, sans affaiblir les modèles ni la validation.
9. **Accord français partagé** : `formuler_compte()` vit dans `rules.py` et est réutilisé par
   `briefing.py`, pour éviter deux règles d'accord divergentes dans le texte affiché.
10. **Briefing sans état propre** : `construire_briefing(analyse)` est une fonction pure ; mêmes
    entrées, même sortie, ordre des sources (volume décroissant puis adresse IP) et des constats
    (ordre fixe de production) compris.

Limites assumées, signalées plutôt que contournées :

- Un rapport DMARC ne contient aucun champ permettant de rattacher un record à la politique d'un
  sous-domaine précis au-delà de `policy_published.domain` et de `identifiers.header_from`. Le moteur
  conserve ces deux notions séparément et ne les fusionne pas en une métrique unique.
- Le contrôle « somme des dispositions = total » est structurellement inatteignable après validation ;
  il est testé au niveau de la fonction, comme décrit au point 8.
- Aucune donnée n'est fabriquée dans le code de production : tous les textes du briefing sont
  construits à partir de mesures, et toute valeur absente est annoncée comme absente.

Résultats réels des commandes demandées :

| Commande | Résultat observé |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/test_rules.py tests/test_briefing.py` | `55 passed in 1.35s`, code de sortie 0. |
| `.venv/bin/python -m pytest -q` | `185 passed in 2.20s`, code de sortie 0 (37 modèles + 34 parseur + 59 archives + 36 règles + 19 briefing). |
| `.venv/bin/python -m compileall -q app tests` | Code de sortie 0, aucune sortie. |

Quatre défauts ont été révélés par ces tests puis corrigés dans le périmètre de l'étape 4 : un
identifiant Python corrompu lors de la rédaction de `rules.py`, une affectation sur un modèle figé qui
construisait mal la vérification des dispositions, un accord français incorrect (`1 source(s)`,
`2 constats appelle`) et une assertion de test qui attendait une formulation antérieure. Aucune
assertion n'a été affaiblie et aucun test n'a été supprimé.

## 3 sexies. Étape 5 — Persistance SQLite (2026-10-15)

Fichiers créés ou modifiés :

| Fichier | Raison |
| --- | --- |
| `app/storage/__init__.py` | Paquet de persistance, sans dépendance Flask. |
| `app/storage/database.py` | Schéma versionné, enregistrement, relecture, doublons, suppression. Bibliothèque standard `sqlite3` uniquement. |
| `app/core/errors.py` | Ajout de `StorageError(MailGuardError)`. Aucun code existant modifié. |
| `tests/test_database.py` | 37 tests sur base temporaire, un répertoire isolé par test. |
| `docs/IMPLEMENTATION_LOG.md`, `README.md` | Journal et état d'avancement. |

`models.py`, `parser.py`, `archive.py`, `rules.py` et `briefing.py` n'ont pas été modifiés.

Sérialisation : la vérification préalable a montré que `Analyse` et `Briefing` sont des modèles
Pydantic dont tous les champs sont sérialisables et relisibles à l'identique
(`Analyse.model_validate_json(a.model_dump_json()) == a` vérifié), les propriétés n'étant pas
sérialisées mais recalculées. Aucune modification de modèle n'a donc été nécessaire. Chaque colonne
stocke sa propre enveloppe versionnée :

```json
{"version": 1, "analyse": {...}}
{"version": 1, "briefing": {...}}
```

La version est contrôlée à la lecture ; une version inconnue provoque une erreur explicite plutôt
qu'une lecture approximative. Un taux `None` reste `None` et n'est jamais relu comme 0.

Schéma : une seule table `analyses`, créée par la migration 1, avec `identifiant` en clé primaire
locale `AUTOINCREMENT`, `empreinte` en `UNIQUE`, `nom_fichier`, `date_import` (ISO 8601 UTC),
`version_schema`, `version_moteur`, `domaine_publie`, `nombre_rapports`, `total_messages`,
`analyse_json`, `briefing_json`, plus un index sur `date_import DESC, identifiant DESC`.

Décisions prises, avec leur justification :

1. **Trois notions séparées** : empreinte du fichier binaire reçu, identité locale de l'analyse
   (entier) et informations déclarées par le rapport. L'identifiant de rapport DMARC n'est jamais
   utilisé comme clé : plusieurs émetteurs peuvent produire le même identifiant. Deux rapports de
   domaines différents restent deux lignes distinctes.
2. **Empreinte calculée sur les octets exacts reçus**, avant décompression ou normalisation, et sa
   limite est documentée dans le module : elle identifie un contenu binaire importé, pas l'identité
   sémantique d'un rapport. Un XML et un ZIP contenant le même rapport produisent donc trois lignes
   distinctes, ce qui est testé.
3. **Doublon détecté par SQLite, pas par un `SELECT` préalable** : l'insertion est tentée, et seule
   la violation de la contrainte `UNIQUE` fait foi. En cas de violation, la ligne existante est relue
   et renvoyée avec `cree=False`, sans jamais confondre doublon et panne de base. Le test de
   concurrence (deux fils, même contenu) vérifie qu'une seule ligne est créée ; il a été exécuté
   cinq fois de suite pour vérifier sa stabilité.
4. **Aucune écriture avant validation** : la charge utile est sérialisée avant l'ouverture de la
   transaction. Une panne pendant l'insertion est annulée par le rollback de la connexion, testé par
   injection de faute.
5. **Colonnes dénormalisées limitées à trois** (`domaine_publie`, `nombre_rapports`,
   `total_messages`), justifiées par l'affichage de l'historique décrit dans `06_UI_AND_REPORTING.md`
   sans désérialiser la charge utile. La lecture renvoie toujours les objets `Analyse` et `Briefing`
   revalidés : ces colonnes ne sont jamais une source de vérité alternative.
6. **Minimisation** : ni XML, ni archive, ni donnée brute n'est écrit. Un test relit toutes les
   colonnes et vérifie qu'aucune ne contient de balise XML.
7. **Connexions courtes** : une connexion par appel, fermée dans un `finally`, avec `commit()` en
   sortie de bloc et `rollback()` sur erreur. `PRAGMA foreign_keys = ON` est activé par précaution pour
   les futurs schémas. Le mode WAL n'est pas activé : rien dans le kit ne l'exige et il créerait des
   fichiers annexes (`-wal`, `-shm`) ; le choix est documenté dans le module.
8. **Délai d'attente explicite** (`timeout_secondes`, 5 s par défaut, 10 s dans le test de
   concurrence) pour ne pas échouer immédiatement en cas de verrouillage.
9. **Chemin maîtrisé** : il ne dépend jamais du nom du fichier importé. Le répertoire parent n'est
   créé que si `creer_repertoire` est vrai, paramètre explicite ; un chemin désignant un dossier, un
   fichier non SQLite ou une base de version supérieure est refusé avec un message clair.
10. **Requêtes paramétrées** partout ; le seul SQL construit par interpolation est
    `PRAGMA user_version = <int>`, qui n'accepte pas de paramètre et ne reçoit qu'un entier interne.
    Le nom de fichier est stocké comme donnée, nettoyé, borné à 255 caractères, et n'est jamais
    utilisé pour construire un chemin.
11. **Suppression implémentée** car `06_UI_AND_REPORTING.md` prévoit une suppression dans
    l'historique ; l'obligation CSRF correspondante est rappelée dans la docstring et devra être
    appliquée au niveau de la route à l'étape 8. Aucune route n'existe à ce stade.
12. **Versionnement par `PRAGMA user_version` et table `MIGRATIONS`** : `initialiser()` applique les
    migrations manquantes dans l'ordre, chacune dans une transaction, échoue explicitement sur une
    version inconnue ou trop récente, et n'efface jamais de données. Le test vérifie le passage d'une
    version antérieure (remise à 0 par le test) vers la version courante avec conservation des lignes.

Résultats réels des commandes demandées :

| Commande | Résultat observé |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/test_database.py` | `37 passed in 0.44s`, code de sortie 0. |
| `.venv/bin/python -m pytest -q` | `222 passed in 0.87s`, code de sortie 0 (37 modèles + 34 parseur + 59 archives + 36 règles + 19 briefing + 37 stockage). |
| `.venv/bin/python -m compileall -q app tests` | Code de sortie 0, aucune sortie. |

Le test de concurrence a été exécuté cinq fois consécutivement : `1 passed` à chaque fois.

Cinq défauts ont été révélés puis corrigés dans le périmètre de l'étape 5 : l'absence de `commit()`
explicite, qui laissait les lignes non écrites ; une enveloppe de sérialisation qui perdait le champ
`version` en base ; une conversion premature des `sqlite3.IntegrityError` en `StorageError`, qui
empêchait la détection des doublons ; et trois erreurs de rédaction dans les tests (identifiant
présent dans une fixture, faute de frappe sur un nom de variable, signature de la fonction
monkeypatchée). Aucun test n'a été supprimé et aucune assertion affaiblie.

## 3 octies. Étape 7 — Interface anglaise, CSS local et rapport HTML (2026-10-16)

Fichiers créés ou modifiés :

| Fichier | Raison |
| --- | --- |
| `app/static/css/style.css` | Feuille de style locale : variables CSS, mise en page responsive, tableaux utilisables sur mobile, focus clavier visible, `prefers-reduced-motion` et règle d'impression. Aucune ressource distante. |
| `app/templates/base.html` | Structure HTML5, `lang="en"`, lien d'évitement, `<main id="contenu">`, en-tête compact, pied de page local, chargement de la feuille de style. |
| `app/templates/index.html` | Accueil en anglais : ce qui est analysé, formats, déroulement, limites issues de la configuration, portée et limites de l'outil, appel à l'action vers `/upload`. |
| `app/templates/upload.html` | Formulaire en anglais : formats acceptés, limites réelles, champ fichier étiqueté, jeton CSRF et nom de champ inchangés, explication du traitement local. |
| `app/templates/resultat.html` | Rapport complet en six sections : identification, résumé quantitatif, sources et résultats, constats déterministes, briefing, enregistrement. |
| `app/templates/erreur.html` | Page d'erreur en anglais. |
| `app/api/routes.py` | Messages utilisateur en anglais : format non pris en charge, fichier absent, jeton invalide, taille dépassée. |
| `app/core/briefing.py` | Briefing entièrement en anglais, y compris libellés, phrases, points à vérifier, limites et À retenir. |
| `app/core/rules.py` | Titres, descriptions et limites des constats en anglais ; `Taux.affichage` passe de « non calculable » à « Not calculable » et de la virgule décimale au point. |
| `app/core/archive.py`, `app/core/parser.py`, `app/core/models.py`, `app/config.py`, `app/erreurs.py`, `app/storage/database.py`, `app/__init__.py`, `app/main.py` | Messages d'erreur visibles par l'utilisateur traduits ; libellés des limites affichées, aides en ligne de commande et messages du journal. |
| `tests/fixtures/*.xml` | Valeurs `org_name` des fixtures synthétiques traduites en anglais (`Example Mail Provider`, etc.), afin qu'aucune donnée affichée ne soit francophone. Les commentaires XML de marquage restent en français : ce sont des notes de développement. |
| `tests/test_web.py` | 17 tests ajoutés : langue, accessibilité de base, feuille de style servie, sections du rapport, taux indisponible, échappement, doublon, entrées ignorées. |
| `tests/test_archive.py`, `tests/test_parser.py`, `tests/test_rules.py`, `tests/test_briefing.py`, `tests/test_database.py`, `tests/test_models.py` | Attentes de messages traduites en anglais, sans affaiblissement. |
| `README.md` | Langue de l'interface documentée, fichiers statiques, état d'avancement. |

Décisions prises :

1. **Une seule langue, l'anglais.** Aucun sélecteur de langue ni infrastructure multilingue.
   Les identifiants internes (nom de champ `rapport`, clés JSON `analyse`/`briefing`, identifiants
   de constats `domaine-publie-absent`, `echecs-dmarc-observez`) sont volontairement conservés :
   ils sont stockés en base et référencés par les tests.
2. **Aucun calcul déplacé dans les gabarits.** Le rapport lit les objets `Analyse` et `Briefing`
   existants ; aucune nouvelle métrique, aucun score, aucun graphique.
3. **Taux indisponibles affichés tels quels.** `Taux.affichage` renvoie « Not calculable (no
   messages counted) » quand le dénominateur est zéro ; aucun 0 % n'est inventé, ce que le test
   correspondant vérifie sur une page réelle.
4. **Données optionnelles absentes rendues explicitement** par la mention « Not available in the
   report » plutôt que par une ligne vide.
5. **Échappement inchangé.** Aucune utilisation de `|safe` ni de `Markup()`, aucun script inline,
   aucunebalise construite à partir d'une donnée importée, CSP inchangée
   (`style-src 'self'` suffit pour une feuille de style locale).
6. **Design sobre et technique.** Variables CSS, une seule couleur d'accent, ambre réservé aux
   constats de niveau `attention` et aux alertes, bordures fines, largeur de lecture limitée,
   aucune animation autre que des transitions désactivées si `prefers-reduced-motion`.
7. **Accessibilité de base.** `lang="en"`, lien d'évitement, `main` focusable, hiérarchie de
   titres `h1` → `h2` → `h3`, libellé associé au champ fichier, `aria-label` sur la navigation,
   `role="alert"` et `role="status"` sur les messages, focus clavier visible.

Résultats réels des commandes demandées :

| Commande | Résultat observé |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/test_web.py` | `60 passed`, code de sortie 0 (43 tests de l'étape 6 mis à jour + 17 tests de l'étape 7). |
| `.venv/bin/python -m pytest -q` | `282 passed`, code de sortie 0 (37 modèles + 34 parseur + 59 archives + 36 règles + 19 briefing + 37 stockage + 60 web). |
| `.venv/bin/python -m compileall -q app tests` | Code de sortie 0, aucune sortie. |

Vérification en conditions réelles (serveur lancé sur la boucle locale, base temporaire, port 5097) :

```bash
FLASK_SECRET_KEY=<jeton> MAILGUARD_DATABASE_PATH=/tmp/.../h.sqlite3 \
MAILGUARD_PORT=5097 .venv/bin/python -m app.main
```

Résultats observés : `GET /` → 200 avec `lang="en"` et lien d'évitement, `GET /static/css/style.css`
→ 200 `text/css` sans aucune URL distante, import XML par le formulaire → 200 contenant les six
sections du rapport, `125`, `80.0 %` et « Not available in the report » pour l'identifiant absent.
Les en-têtes `X-Content-Type-Options`, `X-Frame-Options` et la CSP sont inchangés.

Recherche de chaînes françaises restantes : les gabarits ne contiennent plus aucun mot français dans
leur texte visible ; les chaînes utilisateur des modules Python sont en anglais. Les seules
occurrences restantes sont des docstrings et commentaires de développement en français, ainsi que les
identifiants internes listés au point 1, volontairement conservés.

Limites connues :

- Le CSS est rédigé en anglais ; le reste des commentaires du projet reste en français, conformément
  aux règles du kit.
- Les tableaux restent des tableaux HTML avec débordement horizontal sur petit écran plutôt que des
  cartes empilées : plus simple, mais moins confortable qu'un rendu empilé.
- Aucune mesure de contraste n'a été calculée automatiquement : les couleurs ont été choisies pour
  respecter les exigences WCAG AA sur le texte principal, sans outil de vérification.

## 3 septies. Étape 6 — Application Flask et import réel (2026-10-15)

Fichiers créés ou modifiés :

| Fichier | Raison |
| --- | --- |
| `app/config.py` | Configuration centrale lue dans `.env` et l'environnement, entiers validés explicitement, cohérence des limites vérifiée. |
| `app/securite.py` | Jeton CSRF tiré par `secrets`, vérifié avec `compare_digest`, stocké en session. |
| `app/erreurs.py` | Correspondance exception métier → code HTTP, messages français, en-têtes de sécurité. Module séparé pour éviter un cycle avec `app/__init__.py`. |
| `app/services.py` | Pipeline d'import partagé entre l'interface et les tests : import → règles → briefing → stockage. Aucun calcul métier. |
| `app/api/__init__.py`, `app/api/routes.py` | Blueprint : `GET /`, `GET|POST /upload`. Routes minces, sans DMARC ni SQL. |
| `app/templates/base.html`, `index.html`, `upload.html`, `resultat.html`, `erreur.html` | Gabarits HTML sémantiques en français, sans JavaScript et sans feuille de style (CSS prévu à l'étape 7). |
| `app/main.py` | Point d'entrée : configuration, initialisation non destructive de la base, serveur local, options `--host`, `--port`, `--debug`. |
| `app/__init__.py` | **Complété, pas écrasé** : `__version__` conservée, ajout de la fabrique `create_app()` et des gestionnaires d'erreur. Les imports sont faits dans les fonctions pour éviter le cycle `app → app.storage → app`. |
| `tests/test_web.py` | 43 tests HTTP sur configuration isolée et base temporaire. |
| `.env.example` | Retrait de `FLASK_ENV`, variable non lue par la configuration, au profit de `FLASK_DEBUG`. |
| `README.md` | Exécution, formats acceptés, limites, fonctionnement local. |

Aucune modification des étapes 1 à 5, à l'exception de l'ajout de `ConfigurationErreur` dans
`app/core/errors.py`.

Décisions prises :

1. **Aucun calcul dans les routes.** La route valide la requête, lit le téléversement par blocs
   bornés, puis appelle `executer_import()`. Le contrôle rapide du suffixe réutilise les constantes
   publiques `EXTENSIONS_RAPPORT` et `EXTENSIONS_ARCHIVE` de l'importateur, qui reste seul juge de la
   validité réelle du contenu.
2. **Double barrière de taille conservée.** Flask applique `MAX_CONTENT_LENGTH` (12 Mio) au niveau
   de la requête, et l'importateur applique ses propres limites (10 Mio téléversé, 50 Mio
   décompressés). `valider_configuration()` refuse une configuration où la limite HTTP serait
   inférieure à la limite fichier, pour que les deux règles ne se contredisent pas.
3. **Lecture bornée sans chemin ni temporaire.** Le contenu est lu par blocs de 64 Kio depuis le
   flux de Werkzeug, avec compteur : au-delà de la limite d'import, un `ArchiveLimitError` est levé.
   Le nom fourni n'est jamais utilisé comme chemin et n'est jamais exécuté.
4. **CSRF maison, pas Flask-WTF.** Le kit privilégie les dépendances minimales ; le jeton est tiré
   par `secrets.token_urlsafe`, stocké en session et comparé avec `secrets.compare_digest`. Un POST
   sans jeton ou avec un jeton fabriqué est refusé avant toute lecture de fichier, ce que les tests
   vérifient. Les cookies de session sont `HttpOnly` et `SameSite=Lax`.
5. **En-têtes de sécurité** appliqués à toutes les réponses : `X-Content-Type-Options`,
   `X-Frame-Options`, `Referrer-Policy` et une CSP sans script ni ressource distante.
6. **Échappement systématique.** Jinja échappe toutes les valeurs, aucun `|safe` n'est utilisé, et
   aucun HTML n'est construit à partir d'un champ importé. Un test injecte un nom de fichier et une
   organisation contenant des balises et vérifie la réponse brute échappée.
7. **Erreurs : message métier en français, code adapté, jamais de trace.** Le message métier est
   affiché tel quel (il est déjà rédigé pour l'utilisateur), la cause reste dans le journal serveur
   et dans `__cause__`. Une erreur interne renvoie un message générique en 500.
8. **Doublon affiché comme tel.** La route utilise `Enregistrement.cree` : un second import du même
   contenu n'ajoute aucune ligne et la page l'annonce explicitement avant d'afficher l'analyse
   enregistrée. Aucun message de succès n'est produit avant la confirmation du stockage : si
   l'enregistrement échoue, la réponse est une erreur 503 et la page indique qu'aucun résultat n'a
   été enregistré.
9. **Pas de CSRF sur GET, pas de route de suppression.** L'historique et la suppression restent hors
   de cette étape ; `StockageAnalyses.supprimer()` n'est exposé par aucune route.
10. **Application sans effet de bord à la création.** `create_app()` ne touche pas la base ;
    `initialiser_stockage()` est appelée explicitement par `app/main.py` et par les tests. Créer
    deux fois la base ne détruit rien, ce qui est testé.

Résultats réels des commandes demandées :

| Commande | Résultat observé |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/test_web.py` | `43 passed in 2.07s`, code de sortie 0. |
| `.venv/bin/python -m pytest -q` | `265 passed in 3.10s`, code de sortie 0 (37 modèles + 34 parseur + 59 archives + 36 règles + 19 briefing + 37 stockage + 43 web). |
| `.venv/bin/python -m compileall -q app tests` | Code de sortie 0, aucune sortie. |

Vérification réelle du lancement, avec une configuration de test (base temporaire, port 5098,
écoute sur la seule boucle locale, dossier `data/` du dépôt jamais créé) :

```bash
FLASK_SECRET_KEY=<jeton> MAILGUARD_DATABASE_PATH=/tmp/.../historique.sqlite3 \
MAILGUARD_PORT=5098 .venv/bin/python -m app.main
```

Résultats observés : `GET /` → 200, `GET /upload` → 200 avec jeton, POST d'un ZIP puis d'un XML via
le formulaire → 200 avec `125`, `80,0 %`, `quarantine : 100` et « Échecs DMARC observés » issus des
vrais résultats, second envoi du même fichier → 200 avec la mention « déjà été importé », et base de
données contenant exactement une ligne (`total_messages = 125`, `domaine_publie = example.com`).
Une tentative de POST avec un jeton obtenu dans une autre session a été refusée en 400, ce qui
confirme la protection CSRF en conditions réelles. La base réelle du dépôt (`data/`) est restée
absente.

Cinq défauts ont été révélés puis corrigés dans le périmètre de l'étape 6 : un cycle d'import entre
`app/__init__.py` et `app.storage.database`, l'absence de `commit()` lors du premier essai de
raccordement, des handlers d'erreur mal raccordés après ce déplacement, une assertion de test qui
cherchait une apostrophe non échappée, et une assertion qui visait la mauvaise cible de
`monkeypatch` (`app.core.rules.analyser` au lieu du nom réellement lié dans `app.services`). Aucun
test n'a été supprimé et aucune assertion affaiblie.

## 3 nonies. Étape 8 — Historique, rapport stocké et suppression CSRF (2026-10-16)

Fichiers créés ou modifiés :

| Fichier | Raison |
| --- | --- |
| `app/api/routes.py` | Ajout de `GET /history`, `GET /history/<int:identifiant>` et `POST /history/<int:identifiant>/delete`. Aucun SQL dans les routes, aucun moteur réexécuté. |
| `app/templates/history.html` | Page d'historique : liste bornée des analyses stockées, état vide, lien de consultation, formulaire de suppression par ligne. |
| `app/templates/base.html` | Lien « History » dans la navigation ; affichage des messages flash par catégorie (`alerte--succis` / `alerte--erreur`). |
| `app/templates/index.html` | Lien secondaire vers l'historique. |
| `app/templates/resultat.html` | Bloc conditionnel « Viewing a stored analysis » et ligne « Viewing mode », utilisés uniquement à la relecture. |
| `app/static/css/style.css` | Styles ajoutés : `.actions`, `.formulaire-suppression`, `.bouton--danger`, `.cellule-secondaire`, `.alerte--succes`, `.vide-etat`, `.visuellement-cachee`, `.tableau--historique`. |
| `app/storage/database.py` | `ResumeAnalyse` enrichi de `messages_pass`, `messages_fail`, `date_debut` et `date_fin`, relus dans la charge utile déjà stockée. `lister()` sélectionne désormais `analyse_json`. |
| `tests/test_web.py` | 23 tests ajoutés (historique, rapport stocké, suppression CSRF, pannes de stockage, régressions). |
| `tests/test_database.py` | 4 tests ajoutés sur les champs d'historique et sur une ligne corrompue. |
| `README.md` | Historique, consultation d'un rapport et suppression décrits. |

Routes ajoutées :

| Route | Méthode | Comportement |
| --- | --- | --- |
| `/history` | GET | Liste les analyses réellement stockées, plus le nombre total. |
| `/history/<int:identifiant>` | GET | Affiche le rapport stocké ; 404 si l'identifiant n'existe pas. |
| `/history/<int:identifiant>/delete` | POST | Supprime après vérification du jeton CSRF, puis redirige vers `/history`. |

Décisions prises :

1. **Bornage assumé.** `lister()` conserve sa limite par défaut de 20 ; la page affiche
   « Showing the 20 most recent analyses of N stored » et, lorsque N dépasse la limite, précise que
   les entrées plus anciennes ne sont pas listées. Aucune pagination n'a été ajoutée : elle
   exigerait une nouvelle méthode de stockage hors du périmètre. Le nombre total provient de
   `compter()`, donc l'affichage ne prétend jamais être exhaustif.
2. **Champs d'historique complets.** `ResumeAnalyse` a été étendu avec les compteurs pass/fail et la
   fenêtre de couverture, relus dans `analyse_json` sans nouveau calcul : ni le parseur, ni
   l'importateur, ni le moteur ne sont relancés. Pour une analyse à plusieurs rapports, `date_debut`
   et `date_fin` délimitent l'ensemble des périodes enregistrées ; l'intitulé « Reporting period » et
   ce comportement sont documentés ici et testés.
3. **Relecture d'un rapport.** La route reconstruit un `ResultatImport` à partir de l'enregistrement
   relu et réutilise `resultat.html` : une seule implémentation de rapport. Un test vérifie qu'un
   monkeypatch du moteur fait échouer le test si le moteur était réexécuté.
4. **Suppression uniquement par POST.** La route n'accepte que `POST` ; une suppression par `GET`
   renvoie 405 avant d'atteindre le gestionnaire, sans modifier la base. Le jeton est vérifié avec
   la fonction existante `verifier_jeton()` avant tout appel au stockage.
5. **Pas de message de succès prématuré.** `flash("The stored analysis was deleted.")` n'est émis
   qu'après un `supprimer()` qui renvoie `True`. Pour un identifiant absent, la redirection annonce
   que rien n'a été supprimé.
6. **Aucune cascade.** La suppression ne touche que la ligne ciblée et ne supprime aucun fichier :
   le modèle de données ne conserve que des résultats, pas de fichier associé. Test d'intégration :
   l'état réel de la base est vérifié avant et après.
7. **Enregistrements anciens en français.** Aucune réécriture des données stockées, aucune migration :
   un rapport enregistré avant l'étape 7 s'affiche avec ses constats et son briefing d'origine, dans
   leur langue d'origine. Seuls les libellés, la navigation et les messages de l'interface sont en
   anglais.
8. **Sécurité inchangée.** Pas de `|safe`, pas de script inline, CSP et en-têtes identiques,
   échappement vérifié sur un champ stocké contenant `<script>alert(1)</script>`.

Résultats réels des commandes demandées :

| Commande | Résultat observé |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/test_web.py` | `83 passed`, code de sortie 0 (60 tests antérieurs + 23 tests d'étape 8). |
| `.venv/bin/python -m pytest -q` | `309 passed`, code de sortie 0 (41 stockage, dont 4 nouveaux ; 83 web). |
| `.venv/bin/python -m pytest -q tests/test_database.py` | `41 passed`, code de sortie 0. |
| `.venv/bin/python -m compileall -q app tests` | Code de sortie 0, aucune sortie. |

Vérification en conditions réelles (boucle locale, base temporaire, port 5096) :
`GET /history` vide → 200 avec l'état vide ; après import → 200 avec `example.com`, `100 / 25` et le
lien `/history/1` ; `GET /history/1` → 200 avec « Viewing a stored analysis », `125` et `80.0 %` ;
`GET /history/1/delete` → 405 ; `POST /history/1/delete` avec jeton → 302 vers `/history`, message de
confirmation affiché et table passée à 0 ligne ; `GET /history/42` → 404.

Limites connues :

- L'historique est borné à 20 entrées par page sans pagination ; le total stocké est affiché à côté.
- Les analyses enregistrées avant l'étape 7 conservent leurs constats et briefings en français.
- La suppression est immédiate et irréversible ; aucune corbeille ni confirmation JavaScript
  n'est proposée, le bouton étant explicite et protégé par CSRF.
- `ResumeAnalyse` désérialise la charge utile de chaque ligne listée : le coût est borné par la
  limite de 20, mais la lecture de l'historique est plus lourde qu'un simple `SELECT` de colonnes.

## 3 decies. Étape 9 — Rapport imprimable et exports (2026-10-16)

Fichiers créés ou modifiés :

| Fichier | Raison |
| --- | --- |
| `app/export.py` | Construction des exports en mémoire : enveloppe JSON versionnée et CSV des sources, avec neutralisation des formules. |
| `app/static/js/print.js` | Script local minimal déclenchant la boîte d'impression native ; aucun script inline, aucune dépendance. |
| `app/templates/base.html` | Chargement du script local (`defer`) dans toutes les pages. |
| `app/templates/resultat.html` | Section « Print and export » : bouton d'impression, liens JSON et CSV rattachés à l'identifiant de l'analyse affichée. |
| `app/static/css/style.css` | Règles `@media print` développées (masquage de la navigation et des actions, conservation des titres, tableaux, limites) et styles des exports. |
| `app/erreurs.py` | Ajout de `script-src 'self'` à la CSP : autorise un script strictement local, toujours ni inline ni distant. |
| `app/api/routes.py` | Ajout de `GET /history/<int:identifiant>/export.json` et `/export.csv`, plus le helper `_enregistrement_stocke()` (404 explicite). |
| `tests/test_web.py` | 18 tests ajoutés (impression, JSON, CSV, sécurité, régression). |
| `README.md` | Section impression et exports, schéma JSON, colonnes CSV. |

Routes ajoutées :

| Route | Méthode | Comportement |
| --- | --- | --- |
| `/history/<id>/export.json` | GET | JSON de l'analyse enregistrée, en pièce jointe. |
| `/history/<id>/export.csv` | GET | CSV des sources, en pièce jointe. |

Décisions prises :

1. **Impression native, sans moteur PDF.** Le bouton « Print report » appelle `window.print()` via un
   script local de dix lignes ; l'utilisateur choisit « Save as PDF » dans la boîte native. Aucun
   paquet PDF n'a été ajouté : la RFC 7489 ne l'exige pas et `01_PRODUCT_SPEC.md` laisse le choix
   libre. Sans JavaScript, l'impression par le menu du navigateur produit exactement la même mise en
   page, ce qui est indiqué dans la page.
2. **CSP minimally élargie.** `script-src 'self'` est ajouté ; `default-src 'none'` reste en place,
   `unsafe-inline` reste absent et aucun script distant n'est autorisé.
3. **Export JSON versionné.** Enveloppe `{"schema_version": 1, "exported_at", "analysis_identifier",
   "stored_at", "stored_by_version", "uploaded_file_name", "content_sha256", "analysis", "briefing"}`.
   `analysis` et `briefing` proviennent de `model_dump(mode="json")` sur les objets Pydantic déjà
   validés : nombres, booléens et `null` sont préservés, aucune valeur n'est reconstruite à partir
   d'un texte, et aucun `repr()` n'est utilisé.
4. **Nom de fichier non manipulable.** `mailguard-analysis-<identifiant>.json|csv` n'utilise que
   l'entier de la clé primaire. Un domaine importé contenant un retour chariot ne peut donc pas
   injecter d'en-tête ; un test le vérifie avec `&#13;&#10;` dans le XML.
5. **CSV implémenté et sécurisé.** Le tableau des sources est tabulaire, non ambigu et directement
   utile. Colonnes documentées en anglais ; module `csv` de la bibliothèque standard ; encodage
   UTF-8 ; valeurs textuelles préfixées par `'` lorsqu'elles commencent par `=`, `+`, `-`, `@`,
   tabulation ou retour chariot, les colonnes numériques restant numériques et
   `failure_rate_percent` restant vide quand le taux n'est pas calculable.
6. **Lecture seule.** Aucun export ne modifie la base, ne relance le parseur, l'importateur ou le
   moteur, et ne crée de fichier temporaire. Un test compare l'objet stocké avant et après export.
7. **Stockage intact.** Aucune modification de schéma, de migration ni de SQL : les exports
   réutilisent `StockageAnalyses.obtenir()`.
8. **Enregistrements anciens préservés.** Les constats et briefings stockés avant l'étape 7 sont
   exportés tels quels, dans leur langue d'origine ; seul l'encadré d'export est en anglais.

Résultats réels des commandes demandées :

| Commande | Résultat observé |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/test_web.py` | `101 passed`, code de sortie 0 (83 tests antérieurs + 18 tests d'étape 9). |
| `.venv/bin/python -m pytest -q tests/test_database.py` | `41 passed`, code de sortie 0, inchangé. |
| `.venv/bin/python -m pytest -q` | `327 passed`, code de sortie 0. |
| `.venv/bin/python -m compileall -q app tests` | Code de sortie 0, aucune sortie. |

Deux assertions de l'étape 7 ont été mises à jour : la page contient désormais une balise
`<script>` locale et autorisée, donc le test vérifie qu'il n'existe qu'un script, qu'il est local,
qu'aucun gestionnaire `onclick` n'est présent et que le nom de fichier piégé reste échappé. La
propriété de sécurité testée — aucun script injecté par une donnée importée — est inchangée et reste
couverte.

Vérification en conditions réelles (boucle locale, base temporaire, port 5095) : rapport stocké 200
avec « Print report », « Download JSON », « Download CSV (sources) » et `js/print.js` ;
`export.json` → 200 `application/json` + `Content-Disposition: attachment; filename="mailguard-analysis-1.json"`,
JSON relu avec `json.load` et `total_messages` de type `int` ; `export.csv` → 200 `text/csv;
charset=utf-8`, relu avec `csv.reader` (4 lignes, en-tête correct) ; feuille de style et script servis
en 200 ; CSP avec `script-src 'self'` ; table toujours à 1 ligne après les exports.

Limites connues :

- L'impression dépend du moteur d'impression du navigateur : la pagination exacte, les veuves et
  orphelines et la position des sauts de page ne sont pas contrôlables depuis l'application.
- Le PDF est produit par le navigateur, pas par le serveur : le document n'est pas un PDF certifié et
  aucune propriété de certification n'est annoncée.
- L'export CSV ne couvre que le tableau des sources ; constats et briefing sont disponibles en JSON.
- La neutralisation de formule protège des tableurs courants ; un tableur exotique pourrait malgré
  tout interpréter certaines valeurs.
- Le contrôle des couleurs et de la pagination imprimée n'a pas été vérifié visuellement, seulement
  par le CSS livré et par la présence des règles attendues.

## 3 undecies. Étape 10 — Narration IA locale facultative (2026-10-16)

Fichiers créés ou modifiés :

| Fichier | Raison |
| --- | --- |
| `app/ai/__init__.py` | Paquet optionnel, jamais importé par le chemin déterministe. |
| `app/ai/prompts.py` | Construction du prompt : bloc de données non fiables délimité, troncature déterministe, borne de constats. |
| `app/ai/ollama_client.py` | Adaptateur HTTP : configuration, bornes, transport, validation stricte, statuts typés. |
| `app/config.py` | Réglages `MAILGUARD_OLLAMA_*` et validation de l'endpoint uniquement si la narration est activée. |
| `app/services.py` | `client_narration_de()`, `narrer_import()`, `narration_stockee()` : la couche service décide, la route ne fait qu'afficher. |
| `app/api/routes.py` | La route d'import et la route de rapport stocké fournissent le contexte de narration. |
| `app/templates/resultat.html` | Section « AI-assisted explanation », statut explicite, texte rendu échappé. |
| `app/static/css/style.css` | Styles de la section de narration. |
| `.env.example`, `README.md`, `DECISIONS.md` | Configuration, procédure d'activation et décisions d'architecture. |
| `tests/test_ai.py` | 39 tests : configuration, adaptateur, validation, confidentialité, intégrité, concurrence. |
| `tests/test_web.py` | 10 tests d'intégration HTTP de la narration. |

Décisions prises :

1. **Architecture conforme au kit** : `app/ai/` avec `ollama_client.py` et `prompts.py`, plus le
   contrat typé dans le client. Aucune logique IA dans les routes ni dans les gabarits.
2. **Désactivé par défaut.** `MAILGUARD_AI_ENABLED=0` : aucun appel, aucun import du paquet IA,
   aucun journal. Vérifié par un test qui inspecte `sys.modules` après import du chemin
   déterministe dans un sous-processus.
3. **Configuration préfixée `MAILGUARD_`.** Les noms déjà présents dans `.env.example` sont conservés
   (`MAILGUARD_AI_ENABLED`, `MAILGUARD_OLLAMA_URL`, `MAILGUARD_OLLAMA_MODEL`,
   `MAILGUARD_OLLAMA_TIMEOUT_SECONDS`) ; deux bornes sont ajoutées ainsi qu'un opt-in distant. Une
   configuration IA invalide est refusée au démarrage, jamais au milieu d'une analyse, et ne modifie
   aucune valeur déterministe.
4. **Endpoint local obligatoire.** Schéma HTTP(S) exigé, hôte de boucle locale exigé sauf
   `MAILGUARD_OLLAMA_ALLOW_REMOTE=1`, redirections jamais suivies, aucun hôte fourni par l'utilisateur
   dans une requête, aucune relance automatique.
5. **Minimisation des données.** Seuls identifiant, niveau, titre, description et limite des constats
   sont envoyés, dans un bloc `BEGIN DATA … END DATA` explicitement non fiable. Ni XML, ni records,
   ni adresses IP, ni briefing, ni chemins. Un test vérifie chaque motif interdit dans la charge
   utile réellement transmise.
6. **Intégrité numérique.** Le prompt interdit de reproduire ou de calculer un chiffre ; le modèle ne
   peut pas produire de métrique, de verdict, de politique ou de constat : chaque explication doit
   référencer un identifiant de constat réellement envoyé, sinon toute la narration est rejetée.
   L'analyse et le briefing déterministes ne sont jamais modifiés, et un test le vérifie avant/après.
7. **Validation stricte.** JSON strict, schéma Pydantic figé sans champ inconnu, longueurs bornées,
   caractères de contrôle refusés, et garde-fou heuristique rejettant toute mention de changement de
   politique (`p=quarantine`, `p=reject`) ou de jugement de source. Aucune acceptation partielle.
8. **Bornes de ressources.** Timeout de connexion et de lecture, réponse lue au plus de 32 Kio,
   `num_predict` borné, prompt borné avec troncature déterministe par la fin, douze constats au
   maximum, verrou de classe empêchant deux narrations simultanées.
9. **Narration éphémère.** Calculée une seule fois à l'import, jamais persistée, jamais exportée,
   jamais demandée à la relecture d'un rapport stocké : pas de migration, pas d'appel répété. Les
   exports JSON et CSV restent strictement déterministes, ce que deux tests vérifient.
10. **Interface honnête.** La section « AI-assisted explanation » affiche soit une narration validée,
    soit un statut : désactivée, indisponible ou rejetée par la validation. Le briefing déterministe
    reste toujours visible, et le texte généré est rendu comme texte échappé.

Résultats réels des commandes demandées :

| Commande | Résultat observé |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/test_ai.py` | `39 passed`, code de sortie 0. |
| `.venv/bin/python -m pytest -q tests/test_web.py` | `111 passed`, code de sortie 0 (101 antérieurs + 10 tests de narration). |
| `.venv/bin/python -m pytest -q tests/test_database.py` | `41 passed`, code de sortie 0, inchangé. |
| `.venv/bin/python -m pytest -q` | `376 passed`, code de sortie 0. |
| `.venv/bin/python -m compileall -q app tests` | Code de sortie 0, aucune sortie. |

Nature des tests : **tous les tests d'adaptateur utilisent un transport HTTP simulé** ; aucun
modèle n'a été téléchargé, aucun serveur Ollama n'était requis, aucun appel externe n'a été effectué.

Vérifications réelles sur serveur local :

- narration désactivée (défaut) : import 200, section « AI-assisted explanation » présente avec le
  statut « AI narration is disabled », mesures `125` et `80,0 %` conservées, et **aucune mention
  d'Ollama ou de requests dans le journal** ;
- narration activée sans Ollama en écoute, via le transport `requests` réel : import 200, statut
  « Local AI is unavailable », message « The local model could not be reached (ConnectionError) »,
  mesures déterministes conservées, une seule ligne en base.

Limites connues :

- **Aucun modèle réel n'a été exécuté.** Le contrat supposé est l'API Ollama `/api/chat` avec
  `stream: false` et un champ `message.content` ; cette compatibilité n'a pas été vérifiée en ligne.
- Les performances réelles dépendent du modèle et du matériel ; aucune affirmation n'est faite sur
  une machine de 4 Go, aucun modèle n'étant fourni par défaut.
- Le garde-fou sur les changements de politique et les jugements de source est heuristique : il
  filtre des formulations courantes, pas toutes les formulations possibles. La vraie protection reste
  la validation stricte et le repli déterministe.
- La narration n'est pas conservée : un utilisateur qui rouvre un rapport plus tard ne retrouve pas
  le texte généré. C'est un choix assumé pour éviter une migration et des appels répétés.
- La détection d'une injection dans un champ importé est vérifiée par le cadrage du prompt et la
  minimisation ; aucune défense ne repose sur le seul prompt.
- La concurrence est limitée par un verrou global simple : une seule narration à la fois, les autres
  recevant un statut « indisponible ».

## 3 duodecies. Étape 11 — Audit sécurité et intégration (2026-10-16)

Le rapport complet se trouve dans `docs/SECURITY_AUDIT.md` ; cette section n'en
donne que la synthèse.

Fichiers créés ou modifiés :

| Fichier | Raison |
| --- | --- |
| `docs/SECURITY_AUDIT.md` | Rapport d'audit : environnement, méthodologie, exigences vérifiées, résultats classés par sévérité, mesures, tests, ce qui n'a pas été vérifié, risques résiduels. |
| `app/core/parser.py` | `MAX_RECORDS_PAR_RAPPORT` et contrôle du nombre de `<record>` **avant** la conversion (F1) ; message dédié pour `string_too_long`. |
| `app/core/models.py` | Longueurs maximales sur tous les champs texte libres (F2). |
| `app/core/archive.py` | `ImportLimits.max_records_per_report`, propagé au parseur pour les trois formats. |
| `app/config.py` | Champ `max_records_per_report`, variable `MAILGUARD_MAX_RECORDS_PER_REPORT`, limite affichée sur la page d'import. |
| `.env.example` | Nouvelle variable, avec l'explication de pourquoi une limite en octets ne suffit pas. |
| `app/storage/database.py` | Messages `StorageError` sans chemin (F3) ; point de traduction unique `_revalider` pour `lister()` comme pour `obtenir()` (F4) ; docstring de `supprimer()` remise à jour (F8). |
| `app/ai/prompts.py` | `selection_constats()` devient la source de vérité unique de la sélection (F5). |
| `app/ai/ollama_client.py` | Validation sur les identifiants réellement transmis (F5) ; mandataires d'environnement neutralisés (F6) ; `LONGUEUR_MAX_PHRASE` effectivement appliquée (F9). |
| `tests/test_audit_etape11.py` | 41 tests de régression d'audit. |
| `README.md`, `DECISIONS.md` | Limite nouvelle documentée ; promesse d'import du paquet IA ramenée à ce qui est vrai (F7) ; mandataires d'environnement documentés ; notes d'exploitation. |

Six défauts confirmés ont été corrigés. Tous ont d'abord été **mesurés** avant
correction :

| # | Sévérité | Défaut | Mesure avant | Après |
| --- | --- | --- | --- | --- |
| F1 | Élevée | Nombre de `record` non borné | `.xml.gz` de 660 Kio → **945 Mio de RSS**, 17 s | refusé en 2,35 s, **35 Mio** |
| F2 | Élevée | Longueurs de texte non bornées | `org_name` de **51 380 224 caractères** accepté, stocké, rendu, exporté | refusé (`org_name`, domaines, `comment`, `email`, `report_id`) |
| F3 | Moyenne | Chemin de la base dans la réponse HTTP | `The file « /tmp/.../audit.sqlite3 » is not a usable SQLite database.` | message sans chemin ; cause et journal inchangés |
| F4 | Moyenne | `/history` en 500 sur une ligne corrompue | `KeyError: 'analyse'`, trace journalisée | 503 avec message métier, comme le rapport concerné |
| F5 | Moyenne | Narration référençant un constat non transmis | `max_input_chars=2000`, prompt de 1 constat, sortie **acceptée** | rejetée (`referenced a finding that does not exist`) |
| F6 | Moyenne | `HTTP_PROXY` capté par `requests` | `{'http': 'http://mandataire.interne:3128'}` | `proxies={'http': None, 'https': None}` |

Deux points de faible gravité ont aussi été corrigés (F8 docstring obsolète,
F9 constante inutilisée). Un point de faible gravité a été **documenté sans être
corrigé** : F7, le paquet `app/ai` est chargé sur le chemin HTTP même lorsque la
narration est désactivée, ce qui contreditait une phrase du README. Aucune
dépendance supplémentaire n'a été introduite.

Chemin d'audit également vérifié sans défaut : DTD/entités/XXE/billion-laughs,
XML très profond, chemins ZIP piégés, membres chiffrés et liens symboliques,
GZIP/ZIP corrompus, échappement XSS, injection d'en-tête HTTP, injection de
formule CSV, CSP et en-têtes, CSRF inter-sessions, suppression par GET, doublons,
SQL paramétré et rollback, revalidation à la lecture, absence de `|safe`, de
`Markup` et de `shell=True`.

Vérification en conditions réelles (serveur de boucle locale sur le port 5111,
base temporaire `/tmp/.../h.sqlite3`, fixtures synthétiques, serveur arrêté à la
fin ; la base `data/` du dépôt n'a jamais été créée) : import `.xml`, `.xml.gz`
et `.zip` (200), stockage (3 puis 4 lignes), relecture d'un rapport stocké,
exports JSON (`total_messages` `int` = 167, `taux_pass.valeur` `float` =
85.02994011976048, `failure_rate_percent` **vide** pour la source à 0 message) et
CSV (5 lignes relues par `csv.reader`), suppression GET → 405, POST sans jeton →
400, POST avec jeton d'une autre session → 400 et base inchangée, POST valide →
302, IA désactivée sans aucune requête et sans mention d'Ollama dans le journal,
IA activée sans serveur → « Local AI is unavailable » / `ConnectionError` avec
mesures conservées, timeout de lecture borné à 2,10 s pour 2,0 s demandés.

Dépendances : aucun outil d'audit n'était installé et aucun n'a été ajouté. Le
réseau étant disponible, l'API OSV a été interrogée directement avec `urllib` :
22 avis sur 17 paquets, **aucun n'affecte les versions installées** après
vérification des plages `fixed` / `last_affected`.

Résultats réels des commandes demandées :

| Commande | Résultat observé |
| --- | --- |
| `.venv/bin/python -m pytest -q` (avant, base de référence) | `376 passed in 5.10s`, code de sortie 0 — **vérifié indépendamment**, non repris de l'étape 10. |
| `.venv/bin/python -m compileall -q app tests` (avant) | Code de sortie 0, aucune sortie. |
| `.venv/bin/python -m pytest -q tests/test_audit_etape11.py` | `41 passed`, code de sortie 0. |
| `.venv/bin/python -m pytest -q` (après, dernière modification) | `417 passed`, code de sortie 0. |
| `.venv/bin/python -m compileall -q app tests` (après) | Code de sortie 0, aucune sortie. |

Aucun test existant n'a été supprimé, marqué `skip` ni affaibli. Les 41 tests
d'avant ont échoué (59 échecs) pendant l'application des correctifs, puis sont
repassés à l'identique.

Limites assumées, signalées plutôt que masquées :

- **Aucun modèle réel n'a été téléchargé ni exécuté.** La compatibilité de l'API
  `/api/chat` d'Ollama reste non vérifiée en ligne ; tous les tests d'adaptateur
  utilisent un transport simulé. Un test simulé ne prouve pas la compatibilité
  avec un modèle réel.
- **Aucun test visuel dans un navigateur** : feuille de style, rendu des couleurs,
  mise en page responsive et aperçu d'impression non vérifiés à l'œil.
- La limite de 10 000 records par rapport est une convention, pas une donnée du
  standard ; elle est configurable.
- Le paquet `app/ai` reste chargé sur le chemin HTTP même désactivé (F7), sans
  impact de confidentialité.
- Le chemin de la base apparaît dans le journal console du serveur, jamais dans
  l'interface.
- `pytest -q` renvoie 0 test ignoré ; aucun test n'est marqué `skip` ou `xfail`.

## 3 quaterdecies. Réécriture du README (2026-10-16, après l'étape 12)

À la demande explicite de l'utilisateur, `README.md` a été **réécrit depuis zéro**
sur le plan de la forme et de la mise en page. **Aucun code, test, gabarit, style,
schéma ni dépendance n'a été touché** ; toutes les affirmations vérifiées ont été
conservées, et deux omissions introduites pendant la réécriture ont été détectées
par un contrôle de non-régression puis rétablies.

Structure obtenue (638 lignes) :

| Élément | Détail |
| --- | --- |
| En-tête | Titre, signature, **6 badges** (Python, Flask, licence, IA locale, confidentialité) |
| Sommaire | 14 entrées avec **ancres HTML explicites** (`<a id="...">`), donc fonctionne sur GitHub, GitLab et GitLab self-hosted sans dépendre du calcul d'ancre sur emoji |
| Sécurité | Tableau des 10 garanties + bloc dépliable « ce que l'application n'est **pas** » |
| Démarrage | 5 commandes commentées, encadré de démarrage, URL en grand |
| Architecture | **Diagramme Mermaid** `graph TD` à 5 sous-graphiques colorés + tableau des responsabilités de modules |
| Pipeline | **Diagramme Mermaid** `flowchart LR` du chemin complet, avec sorties d'erreur colorées |
| Fonctionnalités | Formats acceptés / refusés, tableau des formules métriques, distinction évalué ≠ brut, liste des constats |
| Routes | Tableau des 10 routes avec colonne CSRF + **diagramme Mermaid** `stateDiagram-v2` du cycle de vie |
| Configuration | Tableau des 18 variables avec pictogrammes obligatoire / facultatif / si IA activée |
| Tests | Commandes, tableau de résultats datés, tableau des 9 suites avec leur nombre de tests |
| IA | Procédure d'activation, diagnostic, tableau des garanties, statut explicite sur le modèle réel |
| Impression / exports | Les trois mechanisms + enveloppe JSON + colonnes CSV |
| Dépannage | 22 symptômes → cause → solution, sans jamais désactiver une protection |
| Limites | Sous-sections sécurité / ressources / IA / non vérifié / choix assumés |
| Verdict | **Diagramme Mermaid** de la montée en préparation + tableau des trois catégories |
| Kit | Les 11 documents du contrat + les 4 documents projet |
| Langue | UI anglaise, commentaires français, identifiants inchangés |

Vérifications réellement exécutées :

| Contrôle | Résultat observé |
| --- | --- |
| Blocs Mermaid extraits | 4, tous syntaxiquement équilibrés (subgraph/end, parenthèses, nœuds, flèches) |
| **Rendu Mermaid réel** via `mermaid.ink` | `architecture` HTTP 200 (27 Kio), `pipeline` HTTP 200 (203 Kio), `routes` HTTP 200 (40 Kio), `verdict` HTTP 200 (13 Kio) — **les quatre se rendent** |
| Tableaux Markdown | 17 détectés, 0 ligne sans séparateur, 0 largeur de cellule incohérente (après suppression d'un `\|` ambigu) |
| Ancres du sommaire | 15 déclarées, 14 liens, **0 lien cassé** |
| Non-régression des faits | 31 marqueurs vérifiés ; 4 absents analysés, dont **2 omissions réelles rétablies** : `pip install .` échoue faute de `[build-system]`, et `requirements.txt` pour le runtime seul |
| Valeurs publiées contre le code | 16/16 conformes (hôte, port, les 6 limites, les 7 réglages IA, limite d'historique) |
| Comptage des tests publié | 9 fichiers recomptés : 37+34+59+36+19+41+111+39+41 = **417** |
| `git diff --check -- README.md` | code de sortie 0 ; 0 espace en fin de ligne, 0 tabulation, 0 caractère CJK parasite |
| `.venv/bin/python -m pytest -q` | `417 passed`, code de sortie 0 |
| `.venv/bin/python -m compileall -q app tests` | code de sortie 0 |

Choix de forme et leurs limites, signalés :

- **Animation.** Les quatre diagrammes sont **statiques** : Markdown ne permet pas
  d'animation. Une animation exigerait une ressource distante (GIF, `<img>` externe),
  ce qui contredirait le principe « local-first, aucune ressource distante » du
  projet. Les diagrammes Mermaid sont ici le compromis maximal compatible avec cet
  engagement.
- **Badges.** Les 6 badges sont les **seules** ressources distantes du README, et
  uniquement sur GitHub. Le texte reste complet et lisible hors ligne.
- **Langue.** L'interface du produit reste en anglais ; le README est désormais en
  anglais comme l'interface, avec les identifiants internes conservés.

Limites assumées : le rendu des badges, des couleurs d'<div align="center"> et des
diagrammes Mermaid **dépend du moteur d'affichage** ; ce n'est pas vérifié dans un
navigateur, aucun n'étant disponible dans cet environnement. Le contenu textuel,
lui, reste intégralement lisible partout.

## 4. Avancement des étapes

| Étape | Titre | Statut | Commentaire |
| --- | --- | --- | --- |
| 0 | Audit et configuration | Terminée | Configuration et documentation créées, installation vérifiée réellement. |
| 1 | Modèles | Terminée | `app/core/models.py` + 37 tests unitaires, `pytest -q` : 37 passed. Dépôt Git initialisé, sans commit. |
| 2 | Parseur XML DMARC | Terminée | `app/core/parser.py`, `app/core/errors.py`, 23 fixtures synthétiques, 34 tests. `pytest -q` : 71 passed. |
| 3 | Archives sécurisées | Terminée | `app/core/archive.py`, exceptions d'archive, 59 tests. `pytest -q` : 130 passed. |
| 4 | Règles et briefing déterministes | Terminée | `app/core/rules.py`, `app/core/briefing.py`, 3 fixtures, 55 tests. `pytest -q` : 185 passed. |
| 5 | SQLite | Terminée | `app/storage/database.py`, `StorageError`, 37 tests. `pytest -q` : 222 passed. |
| 6 | Flask et upload | Terminée | `app/config.py`, `app/main.py`, `app/api/routes.py`, gabarits, 43 tests. `pytest -q` : 265 passed. Lancement réel vérifié sur une base temporaire. |
| 7 | UI, CSS et rapport HTML | Terminée | Interface entièrement en anglais, `app/static/css/style.css`, rapport complet, 17 tests ajoutés. `pytest -q` : 282 passed. |
| 8 | Historique | Terminée | `/history`, `/history/<id>`, `/history/<id>/delete` (POST + CSRF), 27 tests ajoutés. `pytest -q` : 309 passed. |
| 9 | Export | Terminée | Impression native, `export.json` versionné, `export.csv` des sources, 18 tests. `pytest -q` : 327 passed. |
| 10 | IA locale facultative | Terminée | `app/ai/` (client + prompts), configuration `MAILGUARD_OLLAMA_*`, 49 tests. `pytest -q` : 376 passed. Aucun modèle réel exécuté. |
| 11 | Audit sécurité et intégration | Terminée | `docs/SECURITY_AUDIT.md`, 6 défauts confirmés corrigés (F1–F6), 41 tests de régression. `pytest -q` : 417 passed. Vérification réelle sur serveur de boucle locale. |
| 12 | Audit final | Terminée | `docs/FINAL_ACCEPTANCE_AUDIT.md` : 22 critères DoD audités (**0 FAIL**, 2 PARTIAL), guide Kali reproductible, verdict de préparation. `pytest -q` : **417 passed**, y compris dans un environnement virtuel neuf. README réécrit (voir §3 quaterdecies). |

## 3 tredecies. Étape 12 — Audit d'acceptation final (2026-10-16)

Étape de **vérification et de documentation** : aucun code métier, schéma de base,
test, gabarit, style ou dépendance n'a été modifié.

Fichiers créés ou modifiés :

| Fichier | Raison |
| --- | --- |
| `docs/FINAL_ACCEPTANCE_AUDIT.md` | Audit d'acceptation : périmètre et environnement, matrice des 22 critères de `08_DEFINITION_OF_DONE.md` avec statut et preuve, guide Kali complet, frontière de sécurité, résultats de vérification, verdict de préparation, actions priorisées. |
| `README.md` | Corrections d'affirmations fausses ou incomplètes (voir ci-dessous) et renvoi vers le guide. |
| `docs/SECURITY_AUDIT.md` | Correction de F10, dont l'affirmation s'est révélée inexacte à l'exécution. |
| `docs/IMPLEMENTATION_LOG.md` | Cette section et la ligne d'avancement. |

Ce qui n'a **pas** été vérifié par reprise d'un rapport antérieur : chaque case a
été contrôlée par exécution. Points notables de l'audit :

1. **Aucune case `FAIL`.** 20 `PASS`, 2 `PARTIAL` (IA sans modèle réel ; README
   avant correction), sur 22 critères applicables. Les exigences de
   `05_TEST_STRATEGY.md` et de `03_SECURITY_PRIVACY.md` sont toutes couvertes.
2. **`PROMPT_DE_DEMARRAGE.txt`** (README §Documents, point 11) : **absent**, déjà
   signalé, toujours signalé.
3. **Les documents du kit sont à la racine, pas dans `docs/`.** `docs/ARCHITECTURE.md`,
   `docs/TEST_STRATEGY.md` et `docs/SECURITY_PRIVACY.md` n'existent pas ; les
   équivalents réels sont `02_ARCHITECTURE.md`, `05_TEST_STRATEGY.md` et
   `03_SECURITY_PRIVACY.md`. Signalé, non substitué silencieusement.
4. **`pyproject.toml` n'est pas installable en paquet** : aucune table
   `[build-system]`, donc `pip install .` échoue. C'est un choix assumé (exécution
   depuis les sources, `pyproject.toml:28-29`) ; le guide indique désormais la
   seule méthode supportée.
5. **Installation reproduite de zéro** dans un environnement virtuel neuf créé à
   cette étape : `python3 -m venv` puis `pip install -r requirements-dev.txt`
   (25 paquets, code de sortie 0), puis suite complète. Cela confirme que le
   chemin documenté est reproductible, et pas seulement hérité.
6. **« Fonctionne sans Internet » démontré activement** : le parcours complet
   (import, historique, relecture, exports, CSS, JS) a été exécuté avec
   `socket.connect` et `socket.getaddrinfo` modifiés pour lever sur toute
   destination hors boucle locale. Résultat : tous HTTP 200, **aucune tentative
   de connexion sortante**.
7. **Le paquet IA n'est pas chargé par le cœur** : `GET /history` seul ne charge
   pas `app.ai` ; `POST /upload` et `GET /history/<id>` le chargent pour construire
   le statut neutre (constat F7, inchangé).
8. **Une affirmation de `docs/SECURITY_AUDIT.md` était fausse** : F10 affirmait que
   le chemin de la base apparaissait dans le journal console. Exécution : le
   niveau du logger Flask est `NOTSET`, niveau effectif `WARNING`, la ligne `INFO`
   n'est **jamais émise**. Corrigé. Effet de bord documenté : aucune confirmation
   positive d'initialisation de la base, d'où la méthode de vérification par
   HTTP 200 + existence du fichier `.sqlite3`.

Corrections documentaires apportées au `README.md` (uniquement des affirmations
fausses, incomplètes ou dangereuses) :

| Avant | Après |
| --- | --- |
| « À ce jour, `pytest -q` renvoie le code de sortie 5 (aucun test collecté…) » — phrase de l'étape 0 restée en place et contredisant les lignes suivantes | Tableau de résultats datés, avec mention explicite que la ligne « étape 0 » est historique |
| Installation sans activation de l'environnement virtuel | Ajout de `source .venv/bin/activate`, de la variante `.venv/bin/python`, et de l'avertissement « ne jamais utiliser `sudo pip install` » |
| Aucune mention de l'échec de démarrage sans `.env` | Comportement vérifié (code de sortie 1, message `FLASK_SECRET_KEY is missing`) documenté comme normal |
| Aucune mention de la confirmation de démarrage | Ajout d'une méthode de vérification par `curl` et par le fichier SQLite, avec le fait qu'aucun endpoint de santé n'existe |
| Aucune consigne sur `MAILGUARD_HOST` | Avertissement explicite : ne pas l'ouvrir, l'application n'a pas d'authentification et la suppression serait alors accessible à tout le réseau |
| Dépendances « raisonnables » sans détail | Dépendances listées, plus l'absence de lint/type-check configuré |

Résultats réels des commandes demandées :

| Commande | Résultat observé | Code de sortie |
| --- | --- | --- |
| `git status --short` | 11 fichiers modifiés (étape 11), 2 non suivis ; aucun travail utilisateur préexistant | — |
| `python3 --version` | `Python 3.13.12` | 0 |
| `python3 -m venv /tmp/opencode/verif-venv` | environnement créé | 0 |
| `/tmp/opencode/verif-venv/bin/python -m pip install -r requirements-dev.txt` | `Successfully installed Flask-3.1.3 … werkzeug-3.1.9` (25 paquets) | 0 |
| `/tmp/opencode/verif-venv/bin/python -m pytest -q` | **`417 passed in 6.26s`** | **0** |
| `/tmp/opencode/verif-venv/bin/python -m compileall -q app tests` | aucune sortie | **0** |
| `.venv/bin/python -m pytest -q` | **`417 passed in 6.00s`** | **0** |
| `.venv/bin/python -m compileall -q app tests` | aucune sortie | **0** |
| `.venv/bin/python -m app.main` sans `.env` | `ConfigurationErreur: FLASK_SECRET_KEY is missing…` | **1** (attendu) |
| `FLASK_SECRET_KEY=<jeton> MAILGUARD_DATABASE_PATH=/tmp/… MAILGUARD_PORT=5123 python -m app.main` | serveur démarré, `ss -tlnp` : `LISTEN 127.0.0.1:5123` uniquement | — |
| Parcours web réel (3 imports, historique, relecture, exports, doublon, suppression) | tous HTTP 200, 3 lignes en base puis 2 après suppression, messages « already been imported » et « The stored analysis was deleted. » | — |
| `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/` | `200` | — |
| Contrôle d'invariance DMARC sur les 25 fixtures | 18 refusées au bon type d'erreur, 7 acceptées, `pass+fail=total`, `Σdispositions=total`, invariant par source, `taux is None ⟺ total==0` — **tous vrais** | — |
| `git check-ignore` sur 15 motifs de `.gitignore` | 14 `IGNORE` ; un `.xml.gz` à la racine du dépôt n'est pas ignoré (signalé) | — |
| `git diff --check` | aucun défaut d'espace | 0 |
| Audit des dépendances | **non re-interrogé à cette étape** (résultats de l'étape 11 via API OSV, inchangés) | — |

Vérifications **impossibles** dans cet environnement, et donc non revendiquées :
intégration avec un vrai modèle Ollama (`ollama` absent du poste), rendu visuel et
aperçu d'impression (aucun navigateur), mesure de contraste WCAG (aucun outil),
isolation réseau au niveau noyau (pas de `sudo`). Le statut
`NOT TESTED — real Ollama/model integration` est explicite dans le README et dans
le rapport d'acceptation.

Intégrité et propreté vérifiées : `data/` jamais créé dans le dépôt ; aucun
`rapport réel client` utilisé ; aucun enregistrement dans une base utilisateur (bases
temporaires sous `/tmp` uniquement) ; `.env` ni créé ni modifié ; aucun modèle
téléchargé, aucun service IA lancé, aucune requête IA émise ; aucun test supprimé,
`skip`, `xfail` ou affaibli ; **aucun commit, aucune étiquette, aucun `push`** ; les
modifications non commitées de l'étape 11 ont été conservées intactes.

Limites assumées, signalées plutôt que masquées :

- **L'intégration IA avec un vrai modèle reste non vérifiée.** Les tests
  d'adaptateur utilisent un transport simulé ; le repli déterministe, lui, a été
  vérifié en conditions réelles (connexion refusée, timeout borné).
- **Aucun contrôle visuel.** La feuille de style, le script d'impression et les
  règles `@media print` existent et sont servis en 200, mais la mise en page
  imprimée et le contraste n'ont pas été vus ni mesurés.
- **Le niveau de journalisation de Flask n'a pas été modifié.** Corriger
  l'absence de confirmation d'initialisation de la base demanderait un changement
  de comportement, hors d'une étape de documentation.
- **`docs/SECURITY_AUDIT.md` et `docs/FINAL_ACCEPTANCE_AUDIT.md` ne sont pas
  encore versionnés.**
- Verdict de préparation : **prêt pour le développement et les tests locaux**, et
  **prêt pour un usage local routinier sous réserves explicites**, mais **non prêt
  pour un déploiement réseau ou en production** (absence d'authentification,
  serveur de développement, `SESSION_COOKIE_SECURE=False`).

## 5. Commandes d'installation et d'exécution

```bash
# Installation
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt

# Configuration (optionnelle, copie à adapter)
cp .env.example .env

# Tests (une fois les étapes suivantes implémentées)
.venv/bin/python -m pytest -q

# Compilation
.venv/bin/python -m compileall -q app
```

Le lancement de l'application (`python -m app.main`) n'est possible qu'à partir de l'étape 6.