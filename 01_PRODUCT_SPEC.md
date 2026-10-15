# 01 — Spécification produit

## Produit
**MailGuard Digest** analyse localement des rapports DMARC agrégés et produit un briefing explicable pour un technicien ou un client non spécialiste.

## Fonctionnalités MVP
1. Import de fichiers `.xml`, `.xml.gz` et `.zip` contenant des rapports XML DMARC.
2. Validation du format et erreurs compréhensibles.
3. Parsing déterministe des métadonnées, politique, records et résultats d'authentification.
4. Calculs exacts : messages observés, DMARC pass/fail, dispositions `none`, `quarantine`, `reject`.
5. Tableau récapitulatif et détail par IP source.
6. Synthèse explicable par règles déterministes.
7. Historique local SQLite, date d'import et empreinte SHA-256.
8. Rapport HTML imprimable et PDF si une bibliothèque légère convient.
9. Narration IA locale facultative via Ollama, sans dépendance fonctionnelle.
10. Tests automatisés et documentation.

## Hors périmètre
- Envoi d'e-mails, modification DNS, connexion aux fournisseurs, réputation IP en ligne ou services tiers.
- Déduire qu'une IP est malveillante sur la base d'un rapport.
- Recommander automatiquement une politique DMARC plus stricte.
- Comptes utilisateurs, multi-tenant ou cloud pour le MVP.
- Envoyer automatiquement un rapport à un client.
- Présenter des données fictives comme réelles.

## Principes
- Local-first : fichiers et résultats restent sur la machine.
- « Deterministic core, optional AI narrative ».
- Les chiffres proviennent exclusivement du parseur et des règles déterministes.
- Chaque constat doit être relié à une mesure source.
- Une absence de résultat n'est jamais convertie en succès.
- Les erreurs ne sont jamais ignorées silencieusement.
- Fonctionnement utile sans Ollama, API ou Internet après installation.

## Parcours principal
Import → limites et validation → lecture sécurisée → parsing XML → validation des modèles → calculs déterministes → stockage local facultatif → rapport et export.

## Langue
Interface en français, ton professionnel et neutre. Conserver les termes techniques DMARC standards quand nécessaire.
