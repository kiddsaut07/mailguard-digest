# 03 — Sécurité et confidentialité

## Modèle de menace
Les fichiers importés peuvent être malformés, très volumineux, contenir des chemins ZIP trompeurs ou des champs contrôlés par un tiers. Les considérer comme non fiables.

## Obligations
1. XML via `defusedxml`; ne pas activer DTD, entités externes ou résolution réseau.
2. ZIP : ne jamais extraire les chemins de l'archive directement sur disque; lire les membres en mémoire avec limites.
3. GZIP : limiter la taille décompressée.
4. Limites initiales configurables et documentées : 10 MiB par fichier compressé, 50 MiB décompressés, 100 membres par archive, 20 rapports par import.
5. Refuser extensions inconnues, archives imbriquées, membres chiffrés et chemins ambigus.
6. Vérifier que le contenu est bien un XML DMARC attendu.
7. Secret Flask par variable d'environnement hors tests; secret de développement explicitement local seulement.
8. Ne pas activer `debug=True` hors développement.
9. Limiter la taille des requêtes HTTP et renvoyer une erreur claire.
10. Requêtes SQLite paramétrées, jamais de concaténation de SQL utilisateur.
11. Échapper les champs dans Jinja; ne jamais marquer le contenu importé comme `safe`.
12. Aucune API distante pour analyser les rapports.
13. Ollama uniquement sur une adresse locale configurable; désactivé par défaut; timeout court.
14. Ne pas stocker le XML complet en base par défaut. Stocker seulement les résultats nécessaires, nom nettoyé, SHA-256 et date.
15. Ne pas afficher de secret, chemin privé complet ou trace d'exception dans l'interface.
16. Protection CSRF sur les formulaires qui modifient l'état, ou documenter une solution minimale sûre pour le MVP local.
17. Ne pas utiliser `shell=True` ni exécuter de commande à partir d'un nom de fichier.
18. Aucune télémétrie.

## Limites d'interprétation
- Une IP source n'est pas malveillante parce que DMARC échoue.
- SPF/DKIM bruts « pass » ne garantissent pas l'alignement DMARC.
- Les dispositions agrégées ne prouvent pas que chaque message a été livré ou bloqué.
- Les rapports ne contiennent pas nécessairement les messages individuels.
- Ne jamais recommander automatiquement `p=reject` ou `p=quarantine`.

## Tests sécurité minimaux
XML malformé; DTD/entité; ZIP avec `../`; ZIP trop volumineux; trop de membres; GZIP dépassant la limite; extension trompeuse; champ HTML affiché comme texte; apostrophes dans une entrée SQL.
