# Prompts d'implémentation — ordre strict

OpenCode exécute une étape par message. L'utilisateur envoie `continue` entre les étapes. Ne jamais exécuter toutes les étapes d'un seul coup.

## Étape 0 — Audit et configuration
Lire tous les `.md` du kit; inspecter l'arborescence, Git, fichiers et environnement sans rien supprimer. Créer `docs/IMPLEMENTATION_LOG.md` avec étapes, statut, commandes et résultats réels. Créer/compléter `.gitignore`, `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `.env.example` et README initial s'ils manquent. Pas de logique métier. Vérifier la configuration et donner les commandes d'installation. S'arrêter.

## Étape 1 — Modèles
Implémenter `app/core/models.py` avec Pydantic : métadonnées, politique publiée, authentification, record et rapport. Définir contraintes, enums et invariants. Aucun parsing XML ni UI. Tests unitaires. Exécuter les tests ciblés et s'arrêter.

## Étape 2 — Parseur XML DMARC
Implémenter `app/core/parser.py`, XML avec/sans namespace, `defusedxml`, validation de structure, dates, période, IP, compteurs, dispositions et résultats. Distinguer résultats DMARC évalués des résultats bruts SPF/DKIM. Ne pas inventer les champs requis absents. Ajouter fixtures synthétiques et tests négatifs. Exécuter les tests ciblés et s'arrêter.

## Étape 3 — Archives sécurisées
Implémenter `app/core/archive.py` pour `.xml`, `.xml.gz`, `.zip`. Lire sans extraction des chemins ZIP sur disque. Appliquer les limites de taille compressée/décompressée, nombre de membres et nombre de rapports. Refuser archives imbriquées, corrompues ou dangereuses. Tester les cas de sécurité et s'arrêter.

## Étape 4 — Règles et briefing déterministes
Implémenter `app/core/rules.py` et `app/core/briefing.py`. Calculer totaux, pass/fail, taux, dispositions, sources et constats. Respecter les invariants de `04_DATA_MODEL_AND_DMARC_RULES.md`. Aucun appel IA. Aucun jugement non étayé sur la malveillance d'une IP. Tester cas normaux, zéro message et incohérences. S'arrêter.

## Étape 5 — SQLite
Implémenter `app/storage/database.py`, schéma et stratégie de migration minimale documentée. Stocker métadonnées/résultats nécessaires, SHA-256 et date. Requêtes paramétrées, transactions et chemin DB configurable. Détecter les imports identiques sans duplication silencieuse. Ne pas stocker XML complet par défaut. Tester initialisation, insertion, lecture, doublons et SQL hostile. S'arrêter.

## Étape 6 — Flask et upload
Créer app et routes dans `app/main.py`, `app/__init__.py`, `app/api/routes.py`. Formulaire d'import et page d'accueil. Utiliser pipeline archive → parser → règles. Limiter la taille HTTP, afficher des erreurs claires. Aucun calcul métier dans les routes. Tests Flask client pour succès et erreurs. Pas d'IA à cette étape. S'arrêter.

## Étape 7 — UI et rapport HTML
Créer templates Jinja et CSS léger. Accueil et détail rapport. Afficher domaine, période, politique, métriques, dispositions, sources, constats et limites. Échapper les données importées. Aucune donnée inventée. Tester rendu et champ HTML malveillant. S'arrêter.

## Étape 8 — Historique
Ajouter historique, consultation d'un rapport stocké et état de doublon. Pas de comptes ni multi-client. Si suppression ajoutée, CSRF obligatoire. Tester parcours. S'arrêter.

## Étape 9 — Export
Ajouter HTML imprimable. Réutiliser les mêmes objets/calculs que la page de rapport. Ajouter PDF uniquement si dépendance légère et tests fiables; sinon documenter l'impression HTML comme alternative. Tester. S'arrêter.

## Étape 10 — IA locale facultative
Implémenter `app/ai/ollama_client.py` et `prompts.py`. Désactivée par défaut, configuration par variables d'environnement. Appeler seulement Ollama local; envoyer les constats structurés nécessaires, pas le XML complet. Timeout court et sortie limitée. L'IA reformule sans changer chiffres, résultats ou politique. Fallback déterministe garanti. Tests avec mocks, sans Ollama installé. S'arrêter.

## Étape 11 — Audit sécurité et intégration
Repasser toutes les exigences de `03_SECURITY_PRIVACY.md`; compléter tests d'intégration et cas limites; corriger les problèmes réels. Exécuter `pytest -q` et `python -m compileall -q app`. Rapporter honnêtement les résultats. Mettre à jour README et `docs/IMPLEMENTATION_LOG.md`. S'arrêter.

## Étape 12 — Audit final
Vérifier chaque case de `08_DEFINITION_OF_DONE.md`. Donner les commandes exactes pour installer, lancer et tester sur Kali. Signaler explicitement les limites et cases non terminées. Pas de nouvelles fonctionnalités. S'arrêter.
