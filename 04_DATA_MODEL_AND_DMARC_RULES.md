# 04 — Modèle de données et règles DMARC

## Modèle conceptuel
### Rapport
- organisation déclarante (`org_name`), identifiant du rapport, domaine publié;
- période de début et de fin en UTC, converties depuis les timestamps Unix;
- politique publiée `p`, sous-domaine `sp`, modes `adkim`, `aspf`;
- liste de records et total des messages comptés.

### Record
- IP source, nombre de messages;
- disposition évaluée `none`, `quarantine` ou `reject`;
- SPF DMARC évalué `pass`/`fail`, DKIM DMARC évalué `pass`/`fail`;
- domaine `header_from`;
- résultats SPF bruts et résultats DKIM bruts quand présents.

## Règle DMARC essentielle
DMARC passe si au moins un mécanisme passe **et est aligné** avec le domaine visible `From` : SPF réussi et aligné selon `aspf`, OU DKIM réussi et aligné selon `adkim`. Dans les rapports agrégés, `policy_evaluated/dkim` et `policy_evaluated/spf` représentent les résultats évalués pour DMARC. Ne pas les confondre avec les résultats bruts de `auth_results`.

## Calculs
- `total_messages = somme(record.count)`.
- `dmarc_pass_messages = somme(count)` pour les records où SPF évalué = pass OU DKIM évalué = pass.
- `dmarc_fail_messages = total_messages - dmarc_pass_messages`.
- Dispositions agrégées à partir de `policy_evaluated/disposition`.
- Pourcentage pass = pass / total × 100; gérer total zéro sans division par zéro.
- Garder les nombres entiers; arrondir seulement à l'affichage.
- Invariants : pass + fail = total; dispositions = total si chaque record a une disposition valide.
- Si un calcul n'est pas fiable, signaler l'incohérence au lieu de corriger silencieusement.

## Validation
- Racine XML `feedback`, namespace facultatif.
- `report_metadata`, `policy_published` et au moins un `record`.
- dates valides, fin >= début.
- count entier >= 0.
- IP IPv4 ou IPv6 valide.
- politique et disposition dans `none`, `quarantine`, `reject`.
- résultats évalués dans `pass`, `fail`; toute autre valeur doit être traitée explicitement, jamais transformée silencieusement.
- Ne mettre une valeur par défaut à un champ absent que si le standard et le contexte le permettent.

## Constats permis
Taux pass/fail; sources avec échecs; volume par IP; dispositions reportées; politique publiée comparée aux dispositions avec prudence; période et organisation; avertissement d'incohérence uniquement si déductible des données.

## Conclusions interdites sans preuve
« IP malveillante », « compte piraté », « tous les emails rejetés », « passez immédiatement à reject », « domaine sécurisé à 100 % » ou attribution d'une source à un fournisseur sans référence fiable.
