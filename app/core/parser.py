"""Lecture d'un rapport DMARC agrégé XML vers les modèles validés.

Le parseur ne fait que trois choses :

1. vérifier la structure XML attendue par la RFC 7489 (`feedback`,
   `report_metadata`, `policy_published`, `record`) ;
2. convertir les valeurs textuelles en types stricts (timestamps Unix, entiers,
   énumérations) en **explicitant** toute valeur refusée ;
3. déléguer la validation métier aux modèles Pydantic de `app/core/models.py`.

Il n'effectue aucun calcul d'agrégation (réservé à `app/core/rules.py`) et
n'accède ni à Flask, ni à SQLite, ni au réseau.

Deux familles d'erreurs sont distinguées :

- `ReportParseError` : document illisible, DTD ou entité, racine inattendue,
  élément obligatoire manquant ;
- `ReportValidationError` : structure correcte mais valeur invalide (IP, compteur,
  timestamp, énumération, période incohérente).

Le XML importé est non fiable : il est analysé avec `defusedxml`, qui interdit
DTD, entités et références externes.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree as SecureElementTree
from defusedxml.common import DefusedXmlException
from pydantic import ValidationError

from app.core.errors import ReportParseError, ReportValidationError
from app.core.models import AlignmentMode, DmarcReport

RACINE_ATTENDUE = "feedback"
"""Nom local de la racine imposée par la RFC 7489."""

ENTIER_SIGNE_OU_NON = re.compile(r"^-?[0-9]+$")
"""Entier éventuellement négatif, utilisé pour distinguer un signe d'un texte."""

ENTIER_NATUREL = re.compile(r"^[0-9]+$")
"""Entier naturel : compteurs, timestamps, pourcentages."""

NOMBRE_DECIMAL = re.compile(r"^[0-9]+(\.[0-9]+)?$")
"""Nombre décimal positif, utilisé pour `version`."""

MODES_ALIGNEMENT = {
    "r": AlignmentMode.RELAXED,
    "s": AlignmentMode.STRICT,
    "relaxed": AlignmentMode.RELAXED,
    "strict": AlignmentMode.STRICT,
}
"""Alignement : la RFC 7489 publie `r`/`s`, quelques outils publient les formes longues."""

MAX_DETAIL_VALIDATION = 5
"""Nombre maximal de champs cités dans un message d'erreur, pour rester lisible."""

DESCRIPTIONS_FRANCAISES = {
    "missing": "required field is absent",
    "enum": "value not allowed",
    "string_too_short": "value is empty",
    "greater_than": "value is too large",
    "greater_than_equal": "value is too small",
    "less_than": "value is too large",
    "less_than_equal": "value is too small",
    "int_type": "integer expected",
    "int_parsing": "integer expected",
    "float_type": "decimal number expected",
    "finite_number": "number expected",
}
"""Traduction des refus techniques de Pydantic, afin que l'interface reste française."""


def parse_dmarc_report(source: str | bytes) -> DmarcReport:
    """Transforme un rapport XML DMARC agrégé en modèle validé.

    Lève `ReportParseError` si le document est illisible ou mal formé, et
    `ReportValidationError` si une valeur ne respecte pas `04_DATA_MODEL_AND_DMARC_RULES.md`.
    """
    racine = _lire_racine(source)
    _verifier_racine(racine)

    version = _lire_version(racine)
    metadonnees = _lire_metadonnees(_element_obligatoire(racine, "report_metadata"))
    politique = _lire_politique(_element_obligatoire(racine, "policy_published"))
    records = _lire_records(_elements_obligatoires(racine, "record"))

    return _valider(
        {
            "version": version,
            "metadata": metadonnees,
            "policy_published": politique,
            "records": records,
        }
    )


# --- Lecture sécurisée du document -------------------------------------------


def _lire_racine(source: str | bytes):
    """Analyse le document avec defusedxml et renvoie l'élément racine."""
    if not isinstance(source, (str, bytes)):
        raise ReportParseError(
            "The report must be provided as XML text or raw bytes."
        )
    try:
        return SecureElementTree.fromstring(
            source, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except DefusedXmlException as error:
        raise ReportParseError(
            "The report is refused: it contains a DTD, an entity or an "
            "external reference, which are blocked for security reasons."
        ) from error
    except ParseError as error:
        if "entity" in str(error).lower():
            raise ReportParseError(
                "The report is refused: it uses an undeclared entity, "
                "which is blocked for security reasons."
            ) from error
        raise ReportParseError(
            "The report is unreadable or truncated: the XML is incomplete."
        ) from error
    except ValueError as error:
        raise ReportParseError(
            "The report could not be decoded before XML parsing."
        ) from error


def _verifier_racine(racine) -> None:
    """Vérifie que la racine locale est `feedback`."""
    nom = _nom_local(racine.tag)
    if nom != RACINE_ATTENDUE:
        raise ReportParseError(
            f"Unexpected XML root: « {nom} » instead of « {RACINE_ATTENDUE} »."
        )


# --- Helpers d'accès aux éléments -------------------------------------------


def _nom_local(balise: str) -> str:
    """Retire le namespace XML d'un nom de balise (`{uri}nom` devient `nom`)."""
    if balise.startswith("{"):
        return balise.split("}", 1)[1]
    return balise


def _enfants(element, nom: str) -> list:
    """Tous les enfants directs portant le nom local demandé."""
    return [enfant for enfant in element if _nom_local(enfant.tag) == nom]


def _premier(element, nom: str):
    """Premier enfant direct portant le nom local demandé, sinon `None`."""
    enfants = _enfants(element, nom)
    return enfants[0] if enfants else None


def _element_obligatoire(element, nom: str, contexte: str = "Racine du rapport"):
    """Renvoie un enfant obligatoire ou lève une erreur de structure."""
    enfant = _premier(element, nom)
    if enfant is None:
        raise ReportParseError(f"{contexte}: missing element « {nom} ».")
    return enfant


def _elements_obligatoires(element, nom: str) -> list:
    """Renvoie une liste non vide d'enfants, sinon lève une erreur de structure."""
    enfants = _enfants(element, nom)
    if not enfants:
        raise ReportParseError(f"Element « {nom} » is missing or empty.")
    return enfants


def _texte(parent, nom: str, contexte: str, obligatoire: bool = False) -> str | None:
    """Texte d'un enfant, nettoyé des espaces, ou `None` s'il est absent."""
    enfant = _premier(parent, nom)
    if enfant is None:
        if obligatoire:
            raise ReportValidationError(f"{contexte}: element « {nom} » is absent.")
        return None
    return (enfant.text or "").strip()


def _texte_obligatoire(parent, nom: str, contexte: str) -> str:
    """Texte non vide d'un enfant obligatoire."""
    valeur = _texte(parent, nom, contexte, obligatoire=True)
    if not valeur:
        raise ReportValidationError(f"{contexte}: element « {nom} » is empty.")
    return valeur


def _texte_ou_absent(parent, nom: str) -> str | None:
    """Texte optionnel traité comme absent s'il est vide.

    Un champ vide n'apporte aucune information : le conserver None évite
    d'inventer une valeur, sans masquer une erreur sur les champs obligatoires.
    """
    enfant = _premier(parent, nom)
    if enfant is None:
        return None
    return (enfant.text or "").strip() or None


def _entier(parent, nom: str, contexte: str) -> int:
    """Entier strict, négatif ou non numérique explicitement refusé."""
    brut = _texte_obligatoire(parent, nom, contexte)
    if brut.startswith("-"):
        raise ReportValidationError(f"{contexte}: « {nom} » cannot be negative.")
    if not ENTIER_NATUREL.fullmatch(brut):
        raise ReportValidationError(
            f"{contexte}: « {nom} » must be a positive integer, received « {brut} »."
        )
    return int(brut)


def _pourcentage(parent, nom: str, contexte: str) -> int:
    """Pourcentage de la RFC 7489, entre 0 et 100."""
    valeur = _entier(parent, nom, contexte)
    if valeur > 100:
        raise ReportValidationError(
            f"{contexte}: « {nom} » must be between 0 and 100."
        )
    return valeur


def _timestamp(parent, nom: str, contexte: str) -> datetime:
    """Convertit un timestamp Unix en datetime UTC, sans approximation."""
    brut = _texte_obligatoire(parent, nom, contexte)
    if not ENTIER_SIGNE_OU_NON.fullmatch(brut):
        raise ReportValidationError(
            f"{contexte}: « {nom} » must be an integer Unix timestamp, "
            f"received « {brut} »."
        )
    if brut.startswith("-"):
        raise ReportValidationError(
            f"{contexte}: « {nom} » cannot be a negative timestamp."
        )
    try:
        return datetime.fromtimestamp(int(brut), tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as error:
        raise ReportValidationError(
            f"{contexte}: « {nom} » is outside the representable date range."
        ) from error


def _mode_alignement(parent, nom: str, contexte: str) -> AlignmentMode:
    """Valeur brute d'alignement, traduite selon la RFC 7489.

    Le modèle ne connaît que `relaxed` et `strict` : la valeur `r` du standard
    est donc traduite ici, et non dans le modèle.
    """
    brut = _texte_obligatoire(parent, nom, contexte).lower()
    if brut not in MODES_ALIGNEMENT:
        raise ReportValidationError(
            f"{contexte}: « {nom} » must be r or s, received « {brut} »."
        )
    return MODES_ALIGNEMENT[brut]


# --- Lecture des sections ----------------------------------------------------


def _lire_version(racine) -> float | None:
    """Version du rapport, absente ou strictement positive."""
    version = _texte_ou_absent(racine, "version")
    if version is None:
        return None
    if not NOMBRE_DECIMAL.fullmatch(version):
        raise ReportValidationError(
            f"« version » must be a positive number, received « {version} »."
        )
    return float(version)


def _lire_metadonnees(element) -> dict:
    """Section `report_metadata`."""
    contexte = "Report metadata"
    periode = _element_obligatoire(element, "date_range", contexte)
    return {
        "org_name": _texte_obligatoire(element, "org_name", contexte),
        "report_id": _texte_ou_absent(element, "report_id"),
        "email": _texte_ou_absent(element, "email"),
        "extra_contact_info": _texte_ou_absent(element, "extra_contact_info"),
        "error": _texte_ou_absent(element, "error"),
        "date_range": _lire_periode(periode, contexte),
    }


def _lire_periode(element, contexte: str) -> dict:
    """Section `date_range`, convertie en datetimes UTC."""
    return {
        "begin": _timestamp(element, "begin", contexte),
        "end": _timestamp(element, "end", contexte),
    }


def _lire_politique(element) -> dict:
    """Section `policy_published`.

    Les défauts du standard sont appliqués par le modèle, pas ici : le parseur ne
    fournit que ce qui est écrit dans le document.
    """
    contexte = "Published policy"
    politique = {
        "p": _texte_obligatoire(element, "p", contexte),
        "domain": _texte_ou_absent(element, "domain"),
        "sp": _texte_ou_absent(element, "sp"),
    }
    if _premier(element, "adkim") is not None:
        politique["adkim"] = _mode_alignement(element, "adkim", contexte)
    if _premier(element, "aspf") is not None:
        politique["aspf"] = _mode_alignement(element, "aspf", contexte)
    if _premier(element, "pct") is not None:
        politique["pct"] = _pourcentage(element, "pct", contexte)
    return politique


def _lire_records(elements) -> list[dict]:
    """Liste des records, dans l'ordre du document."""
    return [_lire_record(element, index) for index, element in enumerate(elements, 1)]


def _lire_record(element, index: int) -> dict:
    """Un record agrégé : source, compteur, évaluation et résultats bruts."""
    contexte = f"Record #{index}"
    return {
        "source_ip": _texte_obligatoire(element, "row", contexte),
        "message_count": _entier(element, "count", contexte),
        "policy_evaluated": _lire_evaluation(
            _element_obligatoire(element, "policy_evaluated", contexte), contexte
        ),
        "auth_results": _lire_authentification(element, contexte),
        "identifiers": _lire_identifiants(element),
    }


def _lire_evaluation(element, contexte: str) -> dict:
    """Section `policy_evaluated` : verdicts DMARC et disposition."""
    evaluation = {
        "disposition": _texte_obligatoire(element, "disposition", contexte),
        "spf": _texte_obligatoire(element, "spf", contexte),
        "dkim": _texte_obligatoire(element, "dkim", contexte),
        "smtp_mailfrom": _texte_ou_absent(element, "smtp_mailfrom"),
    }
    if _premier(element, "reason") is not None:
        evaluation["reason"] = _lire_raisons(element, contexte)
    return evaluation


def _lire_raisons(element, contexte: str) -> list[dict]:
    """Toutes les raisons déclarées par le serveur."""
    return [_lire_raison(raison, contexte) for raison in _enfants(element, "reason")]


def _lire_raison(element, contexte: str) -> dict:
    """Une raison : type obligatoire, commentaire facultatif."""
    return {
        "type": _texte_obligatoire(element, "type", contexte),
        "comment": _texte_ou_absent(element, "comment"),
    }


def _lire_authentification(element, contexte: str) -> dict:
    """Section `auth_results`, entièrement facultative.

    Absente, elle ne laisse que des listes vides : ce qui signifie « aucun
    résultat déclaré », jamais « authentification réussie ».
    """
    section = _premier(element, "auth_results")
    if section is None:
        return {}
    return {
        "spf": _lire_spf(section, contexte),
        "dkim": _lire_dkim(section, contexte),
    }


def _lire_spf(section, contexte: str) -> list[dict]:
    """Résultats SPF bruts.

    La RFC 7489 n'en autorise qu'un par `auth_results` ; plusieurs occurrences
    sont lues comme une liste pour ne perdre aucune donnée, sans en inventer.
    """
    return [
        {
            "domain": _texte_obligatoire(spf, "domain", contexte),
            "result": _texte_obligatoire(spf, "result", contexte),
            "scope": _texte_ou_absent(spf, "scope"),
        }
        for spf in _enfants(section, "spf")
    ]


def _lire_dkim(section, contexte: str) -> list[dict]:
    """Résultats DKIM bruts, éventuellement multiples pour un même record."""
    return [_lire_dkim_unitaire(dkim, contexte) for dkim in _enfants(section, "dkim")]


def _lire_dkim_unitaire(element, contexte: str) -> dict:
    """Un résultat DKIM brut, sélecteur et message humain facultatifs."""
    return {
        "domain": _texte_obligatoire(element, "domain", contexte),
        "result": _texte_obligatoire(element, "result", contexte),
        "selector": _texte_ou_absent(element, "selector"),
        "human_result": _texte_ou_absent(element, "human_result"),
    }


def _lire_identifiants(element) -> dict:
    """Section `identifiers`, facultative."""
    section = _premier(element, "identifiers")
    if section is None:
        return {}
    return {
        "header_from": _texte_ou_absent(section, "header_from"),
        "envelope_from": _texte_ou_absent(section, "envelope_from"),
        "envelope_to": _texte_ou_absent(section, "envelope_to"),
    }


# --- Validation finale -------------------------------------------------------


def _valider(donnees: dict) -> DmarcReport:
    """Construit le modèle et traduit les refus de Pydantic en erreur métier."""
    try:
        return DmarcReport(**donnees)
    except ValidationError as erreur:
        raise _erreur_validation(erreur) from erreur


def _erreur_validation(erreur: ValidationError) -> ReportValidationError:
    """Message lisible listant les champs refusés, cause conservée."""
    details = [
        f"{_chemin(detail)} : {_decrire(detail)}" for detail in erreur.errors()[:MAX_DETAIL_VALIDATION]
    ]
    return ReportValidationError("Report refused, invalid data: " + "; ".join(details))


def _chemin(detail: dict) -> str:
    """Emplacement du champ refusé, par exemple `records.0.policy_evaluated.spf`."""
    return ".".join(str(part) for part in detail["loc"]) or "racine"


def _decrire(detail: dict) -> str:
    """Explication française d'un refus de validation."""
    type_erreur = detail.get("type", "")
    if type_erreur == "enum":
        attendus = _valeurs_attendues(detail)
        if attendus:
            return "value not allowed, accepted values: " + attendus
        return DESCRIPTIONS_FRANCAISES["enum"]
    if type_erreur in DESCRIPTIONS_FRANCAISES:
        return DESCRIPTIONS_FRANCAISES[type_erreur]
    return str(detail.get("msg", type_erreur))


def _valeurs_attendues(detail: dict) -> str:
    """Liste des valeurs autorisées, que Pydantic fournisse une chaîne ou une liste."""
    attendus = detail.get("ctx", {}).get("expected", "")
    if isinstance(attendus, str):
        return attendus.replace("'", "")
    return ", ".join(str(valeur) for valeur in attendus)