# 08 — Critères de livraison

## Fonctionnel
- [ ] Import XML, XML.GZ et ZIP avec limites.
- [ ] Parseur validant métadonnées, politique et records.
- [ ] Calculs exacts et invariants testés.
- [ ] Erreurs compréhensibles.
- [ ] Interface locale utilisable.
- [ ] Rapport avec chiffres et constats traçables.
- [ ] Historique SQLite et détection des doublons.
- [ ] Export HTML imprimable.
- [ ] PDF implémenté ou limitation documentée.
- [ ] IA facultative, désactivée par défaut, avec fallback.

## Qualité
- [ ] Tests automatisés passent.
- [ ] Aucun secret versionné.
- [ ] Pas de données clients dans les fixtures.
- [ ] Pas de trace brute dans l'interface.
- [ ] Aucune extraction ZIP non sécurisée.
- [ ] Les chiffres IA ne remplacent jamais les calculs déterministes.
- [ ] README couvre installation, exécution, tests et limites.
- [ ] `.gitignore` exclut venv, caches, DB locale, rapports importés et secrets.

## Matériel modeste
- [ ] Pas de Docker requis.
- [ ] Fonctionne sans Ollama.
- [ ] Fonctionne sans Internet après installation.
- [ ] Dépendances raisonnables.
- [ ] Aucun traitement lourd en arrière-plan.
