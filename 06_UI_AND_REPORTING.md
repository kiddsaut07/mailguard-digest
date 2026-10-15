# 06 — Interface et rapports

## Direction visuelle
Interface sobre, professionnelle, responsive et lisible sur petit écran. HTML sémantique, CSS simple, pas de framework JavaScript lourd, glassmorphism, animations inutiles ou dashboard surchargé. Contraste suffisant et navigation clavier raisonnable.

## Pages MVP
### Accueil
Titre, explication, formulaire d'import, extensions et limites, mention du traitement local, lien vers historique.

### Rapport
Organisation déclarante, domaine, identifiant, période, politique publiée, total, pass, fail, taux pass, dispositions, tableau des IP et volumes, constats traçables, limites, impression/export.

### Historique
Date, domaine, période, compte, état; ouvrir un rapport enregistré; doublons identifiés clairement. Toute suppression doit être protégée contre CSRF.

## Briefing
1. Résumé exécutif de 3 à 5 phrases.
2. Chiffres clés.
3. Observations principales associées à une mesure source.
4. Points à vérifier par un humain.
5. Limites de l'analyse.

Ne jamais transformer corrélation en causalité ni présenter les résultats comme preuve de compromission.

## PDF
Implémenter après le parsing, les règles, l'interface et l'export HTML. Privilégier une bibliothèque légère. Si le moteur PDF est trop lourd ou difficile à installer, livrer une page HTML imprimable et documenter clairement que le PDF natif est optionnel. HTML et PDF doivent réutiliser le même objet de rapport et les mêmes calculs.
