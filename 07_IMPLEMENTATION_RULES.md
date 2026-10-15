# 07 — Règles impératives pour OpenCode

## Rôle
Tu es l'agent d'implémentation. Les décisions de conception et l'ordre sont déjà définis. N'invente pas une autre architecture et n'élargis pas le périmètre.

## Avant toute modification
1. Lire tous les fichiers Markdown du kit de référence.
2. Inspecter l'arborescence réelle, Git et les fichiers présents.
3. Lire les fichiers pertinents avant modification.
4. Réutiliser le code existant lorsqu'il convient.
5. Ne pas supprimer le travail utilisateur sans nécessité.
6. Résumer en 3 à 6 lignes les modifications prévues pour l'étape courante, puis coder.

## Discipline
- Une seule étape par tour; ne jamais passer à la suivante sans `continue` explicite.
- Ne pas créer de démo alternative, maquette statique ou fausses données affichées comme réelles.
- Fixtures synthétiques autorisées uniquement dans `tests/fixtures/`, clairement identifiées.
- Pas de fonctionnalités non demandées ni refonte complète non sollicitée.
- Pas de TODO, `pass`, `NotImplementedError` ou valeurs codées en dur à la place d'une fonctionnalité prévue.
- Pas de `except Exception: pass`.
- Ne pas masquer les erreurs importantes.
- Ne jamais prétendre qu'une commande ou un test a réussi sans l'avoir exécuté et observé.
- Ne pas modifier les tests pour cacher un bug.
- Dépendances minimales; aucun service cloud payant; Ollama non obligatoire.
- Aucun secret dans Git.
- Code lisible pour un étudiant de L3, fonctions courtes et séparation des responsabilités.
- Calculs métier hors routes Flask et templates.
- Ne pas tout mettre dans un seul fichier.

## Réponse obligatoire à la fin de chaque étape
1. **Fichiers créés/modifiés** — liste et raison.
2. **Comportement implémenté** — ce qui est réellement codé.
3. **Tests exécutés** — commandes et résultats observés, ou « non exécutés ».
4. **Problèmes restants** — uniquement les problèmes réels connus.
5. **Prochaine étape** — titre de l'étape suivante, sans l'exécuter.

Puis arrête-toi. N'exécute pas automatiquement l'étape suivante.

## Quand l'utilisateur écrit `continue`
Interpréter ce mot comme l'autorisation d'exécuter uniquement la prochaine étape non terminée de `PROMPTS_ETAPES.md`. Inspecter l'état réel et les tests. Si l'étape précédente est incomplète ou échoue, corriger d'abord dans son périmètre. Ne recommence pas à zéro et ne demande pas de recopier les spécifications. Ne poser une question que si un blocage technique réel empêche d'avancer.
