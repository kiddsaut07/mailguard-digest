# 05 — Stratégie de tests

Ne pas marquer une étape terminée tant que les tests correspondants ne passent pas. Les fixtures doivent être synthétiques et clairement étiquetées; ne jamais utiliser de rapports clients réels.

## Parser
- XML avec et sans namespace; dates UTC; plusieurs records; IPv4 et IPv6.
- XML tronqué; mauvaise racine; metadata/policy manquante.
- count absent, non numérique ou négatif; IP invalide; disposition/résultat inconnu.
- période inversée; DTD/entité refusée.

## Archives
- `.xml`, `.xml.gz`, `.zip` avec un ou plusieurs XML.
- ZIP vide/corrompu/trop grand/trop de membres.
- membre non XML selon politique documentée.
- archive imbriquée refusée; chemin malveillant jamais extrait.
- GZIP décompressé trop volumineux; extension et contenu incohérents.

## Règles
- total exact; pass + fail = total; zéro message sans division par zéro.
- calcul fondé sur résultats DMARC évalués; résultats bruts conservés séparément.
- dispositions agrégées; incohérences signalées.

## Stockage
- initialisation schéma, insertion/lecture, SHA-256 stable, doublon explicite, SQL paramétré et chemin DB configurable.

## API/UI
- accueil HTTP 200; import valide; import invalide; fichier trop gros.
- pas de trace brute exposée; données importées échappées.
- détail, historique et export HTML imprimable.

## IA facultative
- désactivée par défaut; serveur absent, timeout et réponse invalide → fallback déterministe.
- texte IA ne peut changer aucun chiffre ou politique source; aucune requête externe.

## Commandes de validation
```bash
pytest -q
python -m compileall -q app
```
Rapporter honnêtement les commandes exécutées et leur résultat. Ne jamais prétendre qu'un test a été exécuté s'il ne l'a pas été.
