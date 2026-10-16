# Décisions fixes

Ne modifier une décision qu'en présence d'un blocage technique concret, documenté, avec proposition d'alternative minimale.

1. Python + Flask + Jinja, application locale.
2. SQLite pour le MVP.
3. `defusedxml` pour le XML non fiable.
4. Pydantic pour les modèles validés.
5. pytest pour les tests.
6. Aucun frontend React/Node.
7. Aucun Docker requis.
8. Aucun fournisseur IA cloud.
9. Ollama facultatif, désactivé par défaut.
10. Le moteur déterministe est la source de vérité.
11. Aucune recommandation automatique de politique DMARC plus stricte.
12. Pas de données fictives dans l'interface par défaut.
13. Chaque étape doit passer ses tests avant la suivante.
14. Le code doit rester lisible et maintenable par un étudiant de L3.
15. Ne jamais affirmer qu'une commande a réussi sans l'avoir exécutée.
16. La narration IA est calculée une seule fois, à l'import, et n'est jamais persistée : aucun appel au modèle n'est déclenché à la relecture d'un rapport stocké, et aucune migration de base n'est nécessaire. Le texte généré reste donc éphémère et hors des exports.
17. Les réglages Ollama reprennent le préfixe existant `MAILGUARD_` (`MAILGUARD_OLLAMA_*`) et non les noms génériques `OLLAMA_*`, afin de ne pas dupliquer une convention de configuration déjà en place.
18. La CSP gagne `script-src 'self'` : le seul script autorisé est local et sert à déclencher l'impression native. `default-src 'none'` reste en vigueur, `unsafe-inline` reste absent.
19. L'étape 11 ajoute une limite d'**abondance** et non plus seulement de **taille** : `MAILGUARD_MAX_RECORDS_PER_REPORT` (10 000 par défaut) et des longueurs maximales sur les champs texte des modèles. Les limites de `03_SECURITY_PRIVACY.md` point 4 bornent les octets, pas l'expansion mémoire : un rapport de 154 000 records tenait dans 680 Kio compressés et occupait 945 Mio de RSS. La borne est configurable car 10 000 reste une convention conservative, non une donnée du standard DMARC.
20. `StorageError` est affichable par l'interface : aucun de ses messages n'interpole le chemin du fichier de base. Le chemin précis reste dans `__cause__` et dans le journal du serveur local, conformément au point 15 de `03_SECURITY_PRIVACY.md`.
21. La validation de la narration compare les identifiants de constats à ceux **réellement transmis**, donc après troncature du prompt. La sélection des constats_transmis est calculée une seule fois (`prompts.selection_constats`) et sert à la fois à l'assemblage du message et à la validation de la réponse.
22. L'appel Ollama neutralise les mandataires de l'environnement (`HTTP_PROXY`, `https_proxy`…). Sans cela, `requests` aurait pu router la charge utile hors de la machine alors que la configuration n'autorise qu'une adresse de boucle locale.
23. Le paquet optionnel `app/ai` reste chargé sur le chemin HTTP même lorsque la narration est désactivée, car le statut neutre « désactivée » est construit avec ses types. La garantie réelle — aucune requête, aucune dépendance IA, aucun journal — tient ; la promesse documentation d'un « jamais importé » a été retirée plutôt que de déplacer le type de statut hors de `app/ai`, ce qui modifierait la frontière entre le cœur déterministe et la fonction optionnelle. Constat F7 de `docs/SECURITY_AUDIT.md`.
