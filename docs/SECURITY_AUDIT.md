# Audit de sécurité et d'intégration — étape 11

**Date de l'audit :** 2026-10-16
**Portée :** `Upload → validation archive → parsing XML → Pydantic → moteur déterministe → narration IA facultative → SQLite → web → historique → export → suppression`
**Statut global :** **complet, avec réserves explicites** (voir §9 et §10).

Ce document n'est ni un test d'intrusion, ni une certification, ni un audit de
code externe. C'est une revue de sécurité et d'intégration du code de ce dépôt,
appuyée sur des mesures reproductibles et sur des tests automatisés ajoutés au
projet.

---

## 1. Environnement et dépendances

| Élément | Valeur observée |
| --- | --- |
| Python | 3.13.12 (`python3` du système → `.venv/bin/python`) |
| Système | Kali GNU/Linux Rolling 2025.2 |
| Matériel | Intel i5-4300U, 3 857 Mio de RAM |
| Base de référence Git | `f17bf1a` — arbre de travail propre au démarrage de l'étape |

Dépendances d'exécution déclarées (`requirements.txt`, `pyproject.toml`) et
versions installées :

| Paquet | Déclaration | Installé |
| --- | --- | --- |
| Flask | `>=3.0,<4.0` | 3.1.3 |
| pydantic | `>=2.7,<3.0` | 2.14.1 |
| defusedxml | `>=0.7.1,<0.8` | 0.7.1 |
| requests | `>=2.31,<3.0` | 2.34.2 |
| python-dotenv | `>=1.0,<2.0` | 1.2.4 |
| pytest (test) | `>=8.0,<9.0` | 8.4.2 |

Transitaires installées : Werkzeug 3.1.9, Jinja2 3.1.6, MarkupSafe 3.0.4,
itsdangerous 2.2.0, click 8.5.0, blinker 1.9.0, pydantic-core 2.50.1,
urllib3 2.8.0, certifi 2026.7.22, charset-normalizer 3.5.2, idna 3.20.

---

## 2. Méthodologie

1. Lecture intégrale des onze documents du kit, de `docs/IMPLEMENTATION_LOG.md`,
   de `.env.example` et des configurations de dépendances et de tests.
2. Établissement d'une base de référence indépendante (§4), sans reprendre le
   compte de tests annoncé par l'étape 10.
3. Inspection de chaque module à la frontière de son voisin :
   `core/archive.py`, `core/parser.py`, `core/models.py`, `core/errors.py`,
   `core/rules.py`, `core/briefing.py`, `config.py`, `securite.py`, `erreurs.py`,
   `api/routes.py`, `services.py`, `export.py`, `storage/database.py`,
   `main.py`, `ai/prompts.py`, `ai/ollama_client.py`, les six gabarits, la
   feuille de style et le script d'impression.
4. Pour chaque exigence de `03_SECURITY_PRIVACY.md`, recherche du chemin
   d'implémentation **et** du test qui la vérifie, avant de conclure qu'un
   contrôle existe.
5. Mesure, et non supposition, pour tout ce qui concerne les ressources : RSS
   du processus, durée, taille de charge utile, codes de réponse réels.
6. Vérification en conditions réelles sur serveur de boucle locale et base
   temporaire (§8).
7. Ajout de tests de régression pour chaque défaut confirmé (§7).

**Classification employée :** *Critique* (compromission, exécution de code,
divulgation majeure), *Élevée* (contournement d'une frontière de sécurité ou
compromission de données importantes), *Moyenne* (faiblesse réelle à portée
limitée ou sous condition), *Basse* (durcissement, défense en profondeur),
*Informationnelle* (limite documentée, non vulnérabilité).

---

## 3. Synthèse des résultats

| Sévérité | Constat | Statut |
| --- | --- | --- |
| **Critique** | — | aucun |
| **Élevée** | F1 — nombre de `record` non borné : épuisement mémoire (680 Kio → 945 Mio de RSS) | **corrigé** |
| **Élevée** | F2 — longueurs de texte libre non bornées : `org_name` de 51 380 224 caractères accepté | **corrigé** |
| **Moyenne** | F3 — chemin complet du fichier de base divulgué dans la réponse HTTP | **corrigé** |
| **Moyenne** | F4 — `/history` : `KeyError` non traduite sur charge utile endommagée (500 opaque) | **corrigé** |
| **Moyenne** | F5 — la narration IA pouvait référencer un constat écarté par la troncature du prompt | **corrigé** |
| **Moyenne** | F6 — `requests` honorait `HTTP_PROXY` : la charge utile pouvait sortir de la machine | **corrigé** |
| **Basse** | F7 — le README affirme que le code IA n'est jamais importé, faux sur le chemin HTTP | documenté, non corrigé (voir §5.7) |
| **Basse** | F8 — docstring de `supprimer()` obsolète (`« aucune route n'existe à ce stade »`) | **corrigé** |
| **Basse** | F9 — `LONGUEUR_MAX_PHRASE` défini mais jamais utilisé dans `ai/ollama_client.py` | **corrigé** |
| Informationnelle | F10 — `app.main` écrit le chemin de la base dans le journal du serveur | conservé et documenté ; **ligne jamais émise en pratique**, voir §5.9 |

---

## 4. Base de référence avant toute modification

| Commande | Résultat observé |
| --- | --- |
| `git status --porcelain` | sortie vide (aucune modification non commitée) |
| `git log --oneline` | `f17bf1a Initial commit: local DMARC aggregate report analyser` |
| `.venv/bin/python --version` | `Python 3.13.12` |
| `.venv/bin/python -m pytest -q` | **`376 passed in 5.10s`, code de sortie 0** |
| `.venv/bin/python -m compileall -q app tests` | **code de sortie 0, aucune sortie** |

Le chiffre de 376 tests annoncé par l'étape 10 a donc été **vérifié
indépendamment** et confirmé, et non repris tel quel.

---

## 5. Résultats détaillés

### 5.1 Exigences vérifiées sans défaut trouvé (Fait vérifié)

| Exigence de `03_SECURITY_PRIVACY.md` | Résultat | Preuve |
| --- | --- | --- |
| 1. XML via `defusedxml`, sans DTD, entité externe ni réseau | **Conforme** | `core/parser.py:111` passe `forbid_dtd=True, forbid_entities=True, forbid_external=True` ; XXE testé (§6) |
| 2. ZIP jamais extrait sur disque, membres lus en mémoire | **Conforme** | `core/archive.py` : aucun `extractall()`, aucun `ZipInfo.filename` utilisé comme chemin ; `test_aucun_fichier_n_est_ecrit_sur_le_disque` |
| 3. GZIP : taille décompressée limitée | **Conforme** | `_Budget` cumulé, arrêté au bloc qui dépasse ; `test_archive_trop_compressee_interrompue_pendant_la_lecture` |
| 4. Limites configurables initiales | **Conforme, incomplet** | 10 Mio / 50 Mio / 100 membres / 20 rapports respectés ; **complétée par F1** (records par rapport) et **F2** (longueurs de texte) |
| 5. Extensions inconnues, archives imbriquées, membres chiffrés, chemins ambigus refusés | **Conforme** | 14 tests dédiés dans `tests/test_archive.py` |
| 6. Vérifier que le contenu est bien un XML DMARC attendu | **Conforme** | `_exiger_contenu_xml` puis validation du modèle ; extension favorable + contenu non XML → refus |
| 7. Secret Flask hors tests | **Conforme** | `config.py:213` refuse une clé absente ou < 32 caractères |
| 8. Pas de `debug=True` hors développement | **Conforme** | `FLASK_DEBUG` défaut `0` ; `--debug` explicite et documenté « développement local uniquement » |
| 9. Taille des requêtes HTTP limitée, erreur claire | **Conforme** | `MAX_CONTENT_LENGTH` + `_lire_contenu` borné ; 413 vérifié en conditions réelles |
| 10. Requêtes SQLite paramétrées | **Conforme** | seul `PRAGMA user_version = <int>` est interpolé, avec un entier interne |
| 11. Échappement Jinja, jamais de `safe` | **Conforme** | `grep` sur `app/` : aucune occurrence de `\|safe`, `Markup(` ou `{% raw %}` |
| 12. Aucune API distante pour analyser les rapports | **Conforme** | seul `requests` est le transport Ollama optionnel, désactivé par défaut |
| 13. Ollama en adresse locale, désactivé par défaut, timeout court | **Conforme, renforcé** | boucle locale exigée sauf opt-in ; **F6** neutralise les mandataires d'environnement |
| 14. XML complet non stocké | **Conforme** | colonnes dénormalisées + `Analyse`/`Briefing` uniquement ; relu sur toute la ligne en test |
| 15. Ni secret, ni chemin complet, ni trace dans l'interface | **Non conforme, corrigé** | voir **F3** |
| 16. CSRF sur les actions modifiant l'état | **Conforme** | jeton en session, `compare_digest`, suppression en POST uniquement ; vérification inter-sessions réelle |
| 17. Pas de `shell=True`, pas de commande depuis un nom de fichier | **Conforme** | `grep` : aucune occurrence de `subprocess`, `os.system`, `shell=True` dans `app/` |
| 18. Aucune télémétrie | **Conforme** | aucun appel sortant en dehors d'Ollama, désactivé par défaut |

### 5.2 F1 — Élevée — nombre de `record` non borné (CORRIGÉ)

**Défaut.** `ImportLimits` bornait les octets téléversés, les octets
décompressés, les membres et les rapports, mais **rien ne bornait le nombre
d'éléments `<record>` dans un rapport**. `DmarcReport.records` ne portait qu'un
`min_length=1` (`app/core/models.py`, avant correctif).

**Chemin affecté.** `app/core/parser.py` (`_lire_records`) → `app/core/models.py`
(`DmarcReport`) → `app/core/rules.py` (`analyser`) → `app/storage/database.py`
(`enregistrer`).

**Mesure avant correctif** (`.xml.gz` synthétique, 660 Kio, 154 079 records) :

| Étape | RSS cumulé |
| --- | --- |
| televised | 660 Kio |
| arbre ElementTree | 142 Mio |
| dictionnaires du parseur | 217 Mio |
| **modèles Pydantic** | **630 Mio** |
| moteur + briefing | 647 Mio |
| total mesuré | **945 Mio**, 17 s de CPU |

Le coût dominant est la conversion en objets métier, pas le texte : les trois
limites en octets de `03_SECURITY_PRIVACY.md` ne protégeaient donc pas contre
l'épuisement mémoire.

**Correctif.** `MAX_RECORDS_PAR_RAPPORT = 10_000` dans `core/parser.py`, contrôle
après `_elements_obligatoires()` et **avant** la conversion du moindre record ;
propagé par `ImportLimits.max_records_per_report`, `Configuration.max_records_per_report`
et la variable `MAILGUARD_MAX_RECORDS_PER_REPORT`.

**Mesure après correctif :**

| Cas | Upload | Résultat | RSS | Durée |
| --- | --- | --- | --- | --- |
| 154 079 records | 660 Kio | **refusé** (message explicite) | 35 Mio | 2,35 s |
| 20 000 records | 86 Kio | **refusé** | 32 Mio | 0,27 s |
| 10 000 records (à la limite) | 43 Kio | accepté, 489 604 messages | 61 Mio | 0,49 s |

**Réserve :** la valeur 10 000 reste une convention, pas une donnée du standard.
Elle est très supérieure aux rapports agrégés légitimes (quelques centaines à
quelques milliers de sources) et configurable ; un opérateur traitant des
rapports plus larges peut la relever en connaissance de cause.

### 5.3 F2 — Élevée — longueurs de texte libre non bornées (CORRIGÉ)

**Défaut.** Aucun champ textuel n'avait de `max_length`. Un rapport de 49 Kio
compressés déclarant un `org_name` de **51 380 224 caractères** était accepté,
puis écrit en base, recopié dans le briefing, rendu dans la page HTML et inclus
dans l'export JSON — soit environ 50 Mio par rendu.

**Correctif.** Bornes dans `core/models.py` : `LONGUEUR_TEXTE_MAX = 1024`
(`org_name`, `report_id`, `email`, `extra_contact_info`, `error`, `comment`,
`human_result`), `LONGUEUR_DOMAINE_MAX = 512` (domaines, `smtp_mailfrom`,
enveloppes), `LONGUEUR_COURTE_MAX = 256` (`scope`, `selector`). Ces bornes sont
très supérieures à ce que publie la RFC 7489 et **n'ont fait échouer aucun test
existant** ; un test vérifie explicitement qu'un rapport de référence légitime
reste accepté.

**Réserve :** `str(e.text)` n'est plus nécessaire pour borner la sortie du
modèle — la borne `LONGUEUR_MAX_TEXTE` s'applique déjà à tous les champs texte de
la narration (voir F9).

### 5.4 F3 — Moyenne — chemin du fichier de base divulgué (CORRIGÉ)

**Défaut.** Six `StorageError` interpolaient `{chemin}` ou `{parent}`. Or
`app/erreurs.py:58` renvoie `str(erreur)` tel quel à l'interface. Constaté en
conditions réelles :

```
GET /history  ->  503
<p>The file « /tmp/mg-probe-877vijhk/pas-une-base.sqlite3 » is not a usable SQLite database.</p>
```

Cela contrevient directement au point 15 de `03_SECURITY_PRIVACY.md`. Le chemin
reste dans `__cause__` et dans le journal du serveur, qui n'est pas exposé.

**Correctif.** Messages sans chemin, cause inchangée. Un test vérifie à la fois le
comportement HTTP et l'absence de `{chemin}` / `{parent}` dans toute fonction
levant `StorageError`.

### 5.5 F4 — Moyenne — `/history` cassée par une seule ligne corrompue (CORRIGÉ)

**Défaut.** `_ligne_vers_resume` accédait directement à `enveloppe["analyse"]`
sans passer par la traduction d'erreur de `_deserialiser`. Constaté :

| Route | Avant correctif | Après correctif |
| --- | --- | --- |
| `GET /history` | **500**, `KeyError` journalisée | **503**, message métier |
| `GET /history/1` | 503 | 503 |
| `GET /history/1/export.json` | 503 | 503 |

Une seule ligne corrompue rendait la page d'historique entièrement inutilisable,
sans trace renvoyée au navigateur mais avec une trace complète dans le journal.

**Correctif.** Point de traduction unique `_revalider(enveloppe, cle, modele)`,
utilisé par `_deserialiser` comme par `_ligne_vers_resume` ; `lister()` ne relit
toujours que `analyse_json` (pas de coût supplémentaire sur la colonne de
briefing).

### 5.6 F5 — Moyenne — narration IA référençant un constat non transmis (CORRIGÉ)

**Défaut.** `ClientOllama.narrer()` calculait les identifiants autorisés avec
`identifiants_transmis(constats_a_expliquer(analyse))`, soit les **douze
premiers** constats, alors que `construire_prompt` peut tronquer le prompt à un
nombre inférieur pour respecter `max_input_chars`. Constaté :

| `max_input_chars` | Constats dans le prompt | Le modèle cite un constat absent du prompt | Statut |
| --- | --- | --- | --- |
| 4 000 | 8 | non | `ok` |
| 2 500 | 3 | **oui** | **`ok` — accepté à tort** |
| 2 000 | 1 | **oui** | **`ok` — accepté à tort** |

La narration affichée pouvait donc s'appuyer sur un constat que l'application
n'avait jamais transmis au modèle, contrairement à ce qu'annonce le README.

**Correctif.** `prompts.selection_constats(analyse, max_chars)` devient la source
de vérité unique de la sélection ; le client valide contre
`identifiants_transmis(selection_constats(...))`. La signature publique de
`construire_prompt` est inchangée (les tests existants sont préservés tels
quels). Après correctif, les deux cas tronqués sont rejetés
(`The local model referenced a finding that does not exist.`), et un constat
réellement transmis reste accepté.

### 5.7 F7 — Basse — le README surestime l'indépendance du paquet IA (NON CORRIGÉ, documenté)

`README.md` affirme : « With `MAILGUARD_AI_ENABLED=0` the application never
contacts Ollama, **never imports the AI code**, and never logs anything about
it. »

Mesuré en sous-processus :

| Chemin | `app.ai` chargé |
| --- | --- |
| import du cœur déterministe seul (`core.archive`, `core.rules`, `core.briefing`, `storage.database`, `export`) | **non** |
| `GET /history` | **non** |
| `POST /upload` (IA désactivée) | **oui** |
| `GET /history/<id>` (IA désactivée) | **oui** |

Cause : `app/services.py` importe `ResultatNarration` et `StatutNarration` pour
construire le statut neutre « désactivée » / « non re-narrée ».

**Impact réel : nul pour la sécurité.** Le paquet n'importe que la bibliothèque
standard et Pydantic au niveau module ; `requests` n'est chargé qu'au moment de
l'appel. Aucune requête, aucune dépendance IA, aucune ligne de journal : ces
trois propriétés, qui sont les garanties de confidentialité énoncées, sont
confirmées.

**Décision : documenté, non corrigé.** Déplacer le type de statut hors de
`app/ai` modifierait la frontière d'architecture entre le cœur déterministe et la
fonction optionnelle ; c'est une décision structurelle, hors du périmètre d'un
audit, et elle est enregistrée dans `DECISIONS.md`. Le README est corrigé pour
dire ce qui est vrai.

### 5.8 F6 — Moyenne — mandataires d'environnement pour l'appel Ollama (CORRIGÉ)

`requests` honore `HTTP_PROXY` par défaut. Vérifié :

| Environnement | Mandataires effectifs pour `http://127.0.0.1:11434/api/chat` |
| --- | --- |
| aucun | `{}` |
| `HTTP_PROXY=http://mandataire.interne:3128` | `{'http': 'http://mandataire.interne:3128'}` |
| `HTTP_PROXY=…` + `NO_PROXY=127.0.0.1` | `{}` |

Sur un poste configuré avec un mandataire et sans `NO_PROXY`, la charge utile
aurait été routée vers ce mandataire, alors que la configuration n'autorise qu'une
adresse de boucle locale.

**Correctif.** `proxies={"http": None, "https": None}` passé à `requests.post` ;
vérifié par test que les mandataires d'environnement ne sont plus retenus.
`allow_redirects=False` et les timeouts sont conservés.

### 5.9 F10 — Informationnelle — chemin de base dans le journal

`app/main.py:72` écrit le chemin de la base dans le journal **serveur**
(`logging`, console). Le point 15 de `03_SECURITY_PRIVACY.md` porte sur
l'**interface**, et `02_ARCHITECTURE.md` autorise les logs locaux à contenir des
détails utiles. Conservé tel quel, signalé ici pour que le comportement soit
connu plutôt que supposé.

> **Correction apportée à l'étape 12.** L'affirmation précédente — « le chemin
> apparaît dans le journal console » — a été vérifiée par exécution et s'est
> révélée **inexacte en pratique** : le niveau du logger Flask est `NOTSET` et le
> niveau effectif par défaut est `WARNING`, donc la ligne `INFO` **n'est jamais
> émise**. Le journal réel ne contient ni chemin ni mention de base. Cette
> correction a un effet de bord utile : l'opérateur ne dispose d'aucune
> confirmation positive d'initialisation de la base, ce qui impose de vérifier
> l'application par une requête HTTP 200 et par l'existence du fichier
> `.sqlite3` (voir `docs/FINAL_ACCEPTANCE_AUDIT.md` §3.4). Le code n'a pas été
> modifié : corriger le niveau de journalisation relève d'un choix d'exploitation,
> pas d'une documentation.

### 5.10 Correctifs mineurs

- **F8** — `storage/database.py`, `supprimer()` : docstring obsolète
  (« aucune route n'existe à ce stade », alors que la route POST existe depuis
  l'étape 8). Corrigée.
- **F9** — `ai/ollama_client.py` : `LONGUEUR_MAX_PHRASE = 400` était défini et
  jamais utilisé ; les `limitations` de la narration étaient donc bornées par
  `LONGUEUR_MAX_TEXTE` (1 200) et non par 400. La borne est désormais appliquée.

---

## 6. Contrôles testés et conformes

Constats obtenus par mesure directe, pas seulement par lecture de test existant :

| Contrôle | Résultat observé |
| --- | --- |
| XXE (`<!ENTITY … SYSTEM "file:///etc/passwd">`) | refusée, `ReportParseError`, aucun accès fichier |
| « billion laughs » (DTD + entités imbriquées) | refusée par `forbid_dtd` avant toute expansion |
| XML très profond (200 000 niveaux d'imbrication) | accepté sans `RecursionError` ni dépassement mémoire (34 Mio) ; refusé ensuite pour structure absente |
| ZIP 200 000 entrées / 20,75 Mio | refusé avant analyse (dépassement de la limite de téléversement) |
| Nom de membre avec NUL, chemin absolu, `..`, `C:`, `//`, espaces en bord, doublon après normalisation | tous refusés |
| Membre chiffré, lien symbolique, FIFO | refusés |
| GZIP tronqué / corrompu / non-GZIP | refusés (`ArchiveError`) |
| ZIP invalide / tronqué / vide / sans rapport admissible | refusés |
| Échappement XSS : `<script>`, `<img onerror=…>`, nom de fichier piégé | échappés ; une seule balise `<script>` dans la page, le script local autorisé |
| Injection d'en-tête HTTP via domaine ou nom de fichier | impossible : `Content-Disposition` construit depuis le seul entier |
| Injection de formule CSV (`=cmd\|'/c calc'!A1`) | préfixée par `'` ; le module `csv` préserve séparateurs, guillemets et retours à la ligne |
| CSP | `default-src 'none'; style-src 'self'; script-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'` — ni `unsafe-inline` ni `unsafe-eval` |
| En-têtes | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, présents aussi sur les réponses 404 et 405 |
| Cookie de session | `HttpOnly`, `SameSite=Lax` |
| Suppression par GET | 405, base inchangée |
| Jeton d'une autre session | 400, message « The form session is invalid or has expired. », base inchangée |
| Export JSON | `int`/`float`/`None` préservés, aucun XML, aucune narration, aucun chemin |
| Export en lecture seule | objet stocké identique avant/après, table inchangée |
| Narration désactivée | aucun appel HTTP (transport remplacé par une fonction qui lève), aucune mention d'Ollama dans le journal |
| Narration activée sans serveur | `Local AI is unavailable` + `The local model could not be reached (ConnectionError)`, mesures déterministes conservées, une seule ligne en base |
| Timeout de lecture borné | socket muet + `timeout_secondes=2.0` → `ReadTimeout` en 2,10 s, aucune exception propagée |
| Boucle locale Ollama | refusée sans `ALLOW_REMOTE=1` |
| Paquet IA non requis | `app.core.*`, `app.storage.*`, `app.export` importés sans charger `app.ai` |

---

## 7. Tests ajoutés

`tests/test_audit_etape11.py`, **41 tests**, tous fondés sur une propriété de
sécurité et non sur une redite de l'implémentation :

- **F1** (8 tests) : refus au-delà de la limite, refus *avant* toute conversion
  (spy sur `_lire_record`), acceptation à la limite, application aux trois formats
  et aux membres de ZIP, valeur par défaut documentée, configuration invalide
  refusée, borne appliquée au parseur appelé directement.
- **F2** (6 tests) : `org_name`, domaine, commentaire de raison, `email`,
  `report_id` trop longs refusés ; valeurs normales toujours acceptées.
- **F3** (3 tests) : base inutilisable et chemin inaccessible via HTTP, plus un
  contrôle à la source de toutes les fonctions levant `StorageError`.
- **F4** (3 tests) : enveloppe sans clé `analyse`, charge utile incohérente, une
  ligne corrompue ne cassant plus la page entière.
- **F5** (2 tests) : un constat écarté par troncature est rejeté ; un constat
  réellement transmis reste accepté.
- **F6** (1 test) : mandataires d'environnement neutralisés, redirection toujours
  refusée.
- **Non-régression** (18 tests) : téléversement trop volumineux (limite HTTP et
  limite d'import), ZIP/GZIP corrompus, traversée de chemin, DTD, échappement et
  neutralisation CSV, en-têtes de sécurité, suppression par GET et par jeton,
  doublon, parcours nominal complet, export JSON/CSV, narration désactivée sans
  requête, identifiants d'historique inconnus, nom de fichier d'export,
  échappement CSV avec séparateurs/guillemets/saut de ligne, import du paquet IA
  absent du cœur.

**Aucun test existant n'a été supprimé, désactivé (`skip`) ni affaibli.** Les
41 tests existants ont d'abord échoué (59 échecs) pendant l'application des
correctifs, puis sont repassés sans modification.

---

## 8. Vérification en conditions réelles

Serveur réel sur la boucle locale (`http://127.0.0.1:5111`, `debug=False`,
`use_reloader=False`), base temporaire `/tmp/.../h.sqlite3`, fixtures
synthétiques du dépôt, serveur arrêté à la fin. **La base `data/` du dépôt n'a
jamais été créée ni touchée.**

| # | Étape demandée | Résultat observé |
| --- | --- | --- |
| 1 | Téléverser une fixture valide | `.xml` → 200, `.xml.gz` → 200, `.zip` (2 rapports + `notes.txt` + répertoire) → 200 |
| 2 | Rapport parsé et analysé | `Example Mail Provider`, `167` messages, `85.0 %` pour le ZIP, `100.0 %` et `15.0 %` par source |
| 3 | Résultat déterministe stocké | `analyses` : `(1, 1 rapport, 42)`, `(2, 1, 42)`, `(3, 2, 167)`, puis `(4, 1, 489604)` pour le rapport à 10 000 records |
| 4 | Rouvrir l'analyse stockée | `GET /history/1` → 200, « Viewing a stored analysis », « Viewing mode » |
| 5 | Export JSON et CSV | `application/json` + `attachment; filename="mailguard-analysis-3.json"` ; `text/csv; charset=utf-8` + `…-3.csv` ; 5 lignes CSV relues par `csv.reader` |
| 6 | L'export contient les valeurs réelles | `total_messages` = `167` (`int`), `taux_pass.valeur` = `85.02994011976048` (`float`), `nombre_rapports` = 2, sources `192.0.2.20 / 192.0.2.10 / 198.51.100.30 / 2001:db8::5`, `failure_rate_percent` **vide** pour la source à 0 message (jamais `0` fabriqué), `disposition_quarantine = 100` ; pas de XML, pas de narration |
| 7 | Suppression protégée par CSRF | GET → **405** ; POST sans jeton → **400** ; POST avec jeton d'une autre session → **400** et base inchangée `[1, 3]` ; POST avec jeton valide → **302** et confirmation |
| 8 | Flux IA désactivé : aucune requête Ollama | import 200, section « AI-assisted explanation » avec statut « AI narration is disabled in this installation. », mesures conservées, **aucune occurrence d'Ollama ou de `requests` dans le journal** |
| 9 | IA activée, indisponibilité simulée | import 200, « Local AI is unavailable », `ConnectionError`, `42` et `100.0 %` conservés, briefing déterministe présent, 1 seule ligne en base |

Contrôle supplémentaire : `GET /history` sur une base volontairement corrompue
renvoie 503 avec un message métier, sans trace Python dans le corps.

---

## 9. Dépendances et hygiène de la chaîne d'approvisionnement

Aucun outil d'audit n'était installé (`pip-audit`, `safety`, `osv-scanner`,
`bandit`, `ruff`, `mypy`, `pipdeptree` : tous absents) et **aucun n'a été
installé** : la consigne interdit d'ajouter une chaîne d'outils solely pour
produire un rapport. Le réseau étant disponible, l'**API OSV** a été interrogée
directement avec `urllib` de la bibliothèque standard, sans aucune dépendance
nouvelle au projet.

22 avis remontés sur les 17 paquets installés (déclarés ou résolus). **Aucun
n'affecte les versions installées** après vérification des plages `fixed` /
`last_affected` :

| Paquet | Avis | Version installée | Concerné |
| --- | --- | --- | --- |
| flask | 2 | 3.1.3 | non |
| jinja2 | 3 | 3.1.6 | non |
| pydantic | 1 (paquet **npm** homonyme) | 2.14.1 | non |
| pytest | 7 | 8.4.2 | non |
| python-dotenv | 3 (dont 1 paquet **npm** homonyme) | 1.2.4 | non |
| requests | 6 | 2.34.2 | non |
| defusedxml, werkzeug, urllib3, markupsafe, itsdangerous, click, blinker, certifi, idna, charset-normalizer | 0 | — | — |

Contrôles manuels :

- **Dépendances inutiles :** aucune. Les cinq dépendances d'exécution sont
  toutes importées ; `requests` et `python-dotenv` ne le sont qu'en différé.
- **Dépendances dupliquées :** aucune. `requirements.txt`, `requirements-dev.txt`
  et `pyproject.toml` portent les mêmes plages.
- **Dépendances de test en production :** aucune. `pytest` n'est que dans
  `requirements-dev.txt` et `[project.optional-dependencies].dev`.
- **Dépendances manquantes :** aucune. Le graphe d'imports du code de production
  est intégralement couvert : bibliothèque standard, `defusedxml`, `flask`,
  `pydantic`.
- **Artefacts ou secrets commités :** aucun. `git ls-files` (80 fichiers) ne
  contient ni `.env`, ni certificat, ni clé, ni base SQLite.
- **Aucune dépendance n'a été ajoutée, supprimée ou mise à niveau** pendant cet
  audit.

---

## 10. Ce qui n'a pas été vérifié

À lire comme des limites, non comme des réussites :

- **Aucun test d'intrusion externe, aucune certification, aucune garantie de
  sécurité complète.** Ce document ne constitue pas un avis de conformité.
- **Aucun modèle réel n'a été téléchargé ni exécuté.** La compatibilité de
  l'API `/api/chat` d'Ollama avec le format de réponse attendu reste **non
  vérifiée**. Tous les tests d'adaptateur utilisent un transport simulé ; seule la
  connexion réelle refusée et un timeout réel ont été observés. **Un test simulé
  ne prouve pas la compatibilité avec un modèle réel.**
- **Aucun test visuel dans un navigateur.** La feuille de style, le rendu des
  couleurs, la mise en page responsive et l'aperçu d'impression n'ont pas été
  vérifiés à l'œil ; seule la présence et le contenu du CSS livré ont été
  contrôlés programmatiquement.
- **Aucun test de charge ou de concurrence à l'échelle.** Le verrou global de la
  narration et la contrainte `UNIQUE` ont été testés à faible échelle ; un
  comportement sous charge saturante n'est pas characterised.
- **Aucun audit de sécurité des dépendances transitives** au-delà de l'API OSV,
  qui ne couvre pas les avis sans plage de versions exploitable et n'inclut pas
  les avis propres à Debian/Ubuntu non encore publiés dans OSV.
- **Le WCAG n'a pas été mesuré** (pas d'outil de contraste) ; les choix de couleur
  sont déclarés conformes, non mesurés.
- **Le serveur de développement Werkzeug est utilisé.** Il n'est ni audité ni
  destiné à une exposition réseau ; le README le présente comme tel.
- **La mitigation de formule CSV** protège contre les tableurs courants ; elle ne
  constitue pas une garantie absolue pour un tableur exotique (limite déjà
  signalée à l'étape 9).
- **Les tests de charge hostile ci-dessus sont des mesures ponctuelles**, pas une
  caractérisation complète des limites de ressources (par exemple, la consommation
  mémoire d'un répertoire central ZIP de 10 Mio n'a pas été mesurée en
  détail : le contrôle de taille s'applique avant `infolist()`).

---

## 11. Risques résiduels

1. **Les limites en octets ne bornent pas l'expansion.** F1 et F2 couvrent le
   nombre de records et la longueur des textes, mais pas, par exemple, le nombre
   total d'éléments XML ni le nombre de résultats bruts par record. Une archive
   faite de millions d'éléments astucieux resterait bornée par les 50 Mio
   décompressés et par les 10 000 records par rapport, ce qui limite fortement
   l'exposition, sans être une preuve d'absence d'amplification.
2. **Pas de quota cumulé ni de limitation de débit.** Un opérateur peut répéter
   des téléversements ; la mémoire reste bornée par requête, pas par unité de
   temps. Une telle protection relève d'un proxy ou d'une exposition réseau, hors
   périmètre d'une application locale.
3. **L'application n'a aucune authentification ni autorisation**, par conception
   (`01_PRODUCT_SPEC.md`, hors périmètre). Sur une machine multi-utilisateurs,
   quiconque peut atteindre le port peut importer, consulter et **supprimer** les
   analyses. C'est un choix documenté, pas un défaut, mais il conditionne la
   confiance que l'on peut accorder à un déploiement.
4. **Le secret de session est en cookie non `Secure`**, ce qui est cohérent avec
   une écoute en HTTP sur la boucle locale. Toute exposition en HTTP sur le
   réseau local rendrait ce choix inacceptable.
5. **Le garde-fou heuristique de la narration** (`MOTIFS_INTERDITS`) filtre des
   formulations courantes, pas toutes. La protection réelle reste la validation
   stricte du schéma et le repli déterministe.
6. **F7** : le paquet `app.ai` est chargé sur le chemin HTTP même désactivé (§5.7).
   Sans impact de confidentialité, mais la promesse du README était fausse et a
   été corrigée.
7. **Le chemin de la base n'apparaît pas en pratique dans le journal console**
   (F10, ligne jamais émise), et jamais dans l'interface ; en contrepartie,
   l'initialisation de la base ne produit aucune confirmation visible.
8. **Aucune garantie sur le comportement d'un modèle réel** (§10).

---

## 12. Statut global

Les six défauts confirmés de sécurité et d'intégration (F1 à F6) ont été corrigés,
testés et vérifiés en conditions réelles, sans régression sur les 376 tests
existants. Les deux points de faible gravité ont été corrigés (F8, F9). Le point
F7 est documenté et reporté comme risque résiduel, avec la raison de ne pas avoir
été corrigé dans cette étape.

Aucune vulnérabilité critique n'a été trouvée. Aucune vulnérabilité élevée ou
moyenne ne reste ouverte.

**Cette étape est terminée.** Les réserves des §10 et §11 doivent être lues avec
le rapport : l'absence de constat critique dans la portée auditée n'est pas une
garantie que l'application est sécurisée.