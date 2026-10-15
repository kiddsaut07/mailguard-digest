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
