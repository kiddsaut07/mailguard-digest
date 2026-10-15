"""Modèles validés d'un rapport DMARC agrégé (RFC 7489).

Ce module décrit uniquement des structures et leurs contraintes :

- aucune lecture de fichier, aucun accès réseau, aucun accès Flask ou SQLite ;
- aucune agrégation de chiffres : les totaux et taux relèvent de
  `app/core/rules.py` ;
- aucune valeur inventée : un champ absent reste absent, sauf lorsque le
  standard DMARC définit une valeur par défaut explicite (voir `PublishedPolicy`
  et `AuthResults`).

Distinction essentielle : `Record.auth_results` contient les résultats bruts
SPF/DKIM déclarés par le serveur, tandis que `Record.policy_evaluated` contient
les résultats **évalués pour DMARC** (prise en compte de l'alignement). Les deux
ne doivent jamais être confondus ni fusionnés.
"""

from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

MessageCount = Annotated[int, Field(strict=True, ge=0)]
"""Nombre de messages observés : entier strict, jamais négatif."""

Percentage = Annotated[int, Field(strict=True, ge=0, le=100)]
"""Pourcentage défini par la RFC 7489 : entier de 0 à 100."""

DomainName = Annotated[str, Field(min_length=1)]
"""Nom de domaine non vide, tel que publié par le serveur de rapport."""


def _canonical_ip(value: str) -> str:
    """Retourne la forme canonique d'une adresse IPv4 ou IPv6."""
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as error:
        raise ValueError(f"invalid IP address: {value!r}") from error


SourceIP = Annotated[str, AfterValidator(_canonical_ip)]
"""Adresse IP source validée comme IPv4 ou IPv6."""


def _as_utc(value: datetime) -> datetime:
    """Exige un datetime avec fuseau et le ramène explicitement en UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime without timezone: an explicit UTC offset is required")
    return value.astimezone(timezone.utc)


UtcDateTime = Annotated[AwareDatetime, AfterValidator(_as_utc)]
"""Date et heure UTC issues des timestamps Unix du rapport."""


class DmarcModel(BaseModel):
    """Base commune : tout champ inconnu est refusé, sans conversion implicite."""

    model_config = ConfigDict(extra="forbid")


class DmarcPolicy(StrEnum):
    """Politique publiée dans l'enregistrement DNS (`p` ou `sp`)."""

    NONE = "none"
    QUARANTINE = "quarantine"
    REJECT = "reject"


class Disposition(StrEnum):
    """Disposition évaluée par le serveur pour un record (`policy_evaluated`)."""

    NONE = "none"
    QUARANTINE = "quarantine"
    REJECT = "reject"


class AlignmentMode(StrEnum):
    """Mode d'alignement DMARC (`adkim` et `aspf`)."""

    RELAXED = "relaxed"
    STRICT = "strict"


class DmarcEvaluation(StrEnum):
    """Résultat DMARC évalué : seules ces deux valeurs sont admises."""

    PASS = "pass"
    FAIL = "fail"


class SpfResult(StrEnum):
    """Résultat SPF brut, tel que rapporté par le serveur.

    Ces valeurs sont plus riches que `DmarcEvaluation` : un `softfail` brut ne
    signifie pas forcément un échec DMARC.
    """

    NONE = "none"
    PASS = "pass"
    FAIL = "fail"
    SOFTFAIL = "softfail"
    NEUTRAL = "neutral"
    TEMPERROR = "temperror"
    PERMERROR = "permerror"


class DkimResult(StrEnum):
    """Résultat DKIM brut, tel que rapporté par le serveur."""

    NONE = "none"
    PASS = "pass"
    FAIL = "fail"
    POLICY = "policy"
    NEUTRAL = "neutral"
    TEMPERROR = "temperror"
    PERMERROR = "permerror"


class ReasonType(StrEnum):
    """Motif donné par le serveur pour une disposition évaluée."""

    FORWARDED = "forwarded"
    SAMPLED_OUTGOING = "sampled_outgoing"
    TRUSTED_FORWARDER = "trusted_forwarder"
    MAILING_LIST = "mailing_list"
    LOCAL_POLICY = "local_policy"
    OTHER = "other"


class SpfAuthResult(DmarcModel):
    """Un résultat SPF brut issu de `auth_results`."""

    domain: DomainName
    result: SpfResult
    scope: str | None = None


class DkimAuthResult(DmarcModel):
    """Un résultat DKIM brut issu de `auth_results`."""

    domain: DomainName
    result: DkimResult
    selector: str | None = None
    human_result: str | None = None


class AuthResults(DmarcModel):
    """Résultats d'authentification bruts, conservés séparément des évaluations.

    Une liste vide signifie « le serveur n'a déclaré aucun résultat de ce type »,
    et non « authentification réussie ».
    """

    spf: list[SpfAuthResult] = Field(default_factory=list)
    dkim: list[DkimAuthResult] = Field(default_factory=list)


class Reason(DmarcModel):
    """Motif associé à une disposition évaluée."""

    type: ReasonType
    comment: str | None = None


class PolicyEvaluated(DmarcModel):
    """Résultats évalués pour DMARC, champs `policy_evaluated` du rapport.

    `spf` et `dkim` portent ici le verdict DMARC (alignement compris). Ils ne
    doivent pas être lus comme les résultats bruts de `AuthResults`.
    """

    disposition: Disposition
    spf: DmarcEvaluation
    dkim: DmarcEvaluation
    smtp_mailfrom: str | None = None
    reason: list[Reason] = Field(default_factory=list)


class Identifiers(DmarcModel):
    """Identifiants d'en-tête utiles au contexte, sans valeur inventée."""

    header_from: DomainName | None = None
    envelope_from: DomainName | None = None
    envelope_to: DomainName | None = None


class Record(DmarcModel):
    """Une ligne agrégée d'un rapport DMARC."""

    source_ip: SourceIP
    message_count: MessageCount
    policy_evaluated: PolicyEvaluated
    auth_results: AuthResults = Field(default_factory=AuthResults)
    identifiers: Identifiers = Field(default_factory=Identifiers)

    @property
    def dmarc_pass(self) -> bool:
        """Vrai si DMARC passe pour ce record, selon les résultats évalués.

        DMARC passe si SPF évalué **ou** DKIM évalué vaut `pass` : ces verdicts
        intègrent déjà l'alignement avec le domaine visible `From`.
        """
        return (
            self.policy_evaluated.spf is DmarcEvaluation.PASS
            or self.policy_evaluated.dkim is DmarcEvaluation.PASS
        )


class DateRange(DmarcModel):
    """Période couverte par le rapport, en UTC.

    Les timestamps Unix du XML sont convertis en datetimes aware par le parseur ;
    cette conversion est le seul endroit où ce choix est fait.
    """

    begin: UtcDateTime
    end: UtcDateTime

    @model_validator(mode="after")
    def _check_period_order(self) -> DateRange:
        if self.end < self.begin:
            raise ValueError(
                "inconsistent reporting period: the end date is before the start date"
            )
        return self

    @property
    def duration_seconds(self) -> int:
        """Durée de la période en secondes."""
        return int((self.end - self.begin).total_seconds())

    @property
    def begin_timestamp(self) -> int:
        """Timestamp Unix du début, pour affichage ou export."""
        return int(self.begin.timestamp())

    @property
    def end_timestamp(self) -> int:
        """Timestamp Unix de la fin, pour affichage ou export."""
        return int(self.end.timestamp())


class ReportMetadata(DmarcModel):
    """Métadonnées déclarées par l'organisation qui publie le rapport."""

    org_name: str
    report_id: str | None = None
    email: str | None = None
    extra_contact_info: str | None = None
    date_range: DateRange
    error: str | None = None


class PublishedPolicy(DmarcModel):
    """Politique DMARC publiée, champs `policy_published` du rapport.

    Les valeurs par défaut présentes ci-dessous sont celles de la RFC 7489
    (`adkim=relaxed`, `aspf=relaxed`, `pct=100`). `sp` n'est pas remplacé par
    `p` : l'absence est conservée et l'application effective est exposée par
    `effective_subdomain_policy`.
    """

    p: DmarcPolicy
    domain: DomainName | None = None
    adkim: AlignmentMode = AlignmentMode.RELAXED
    aspf: AlignmentMode = AlignmentMode.RELAXED
    pct: Percentage = 100
    sp: DmarcPolicy | None = None

    @property
    def effective_subdomain_policy(self) -> DmarcPolicy:
        """Politique appliquée aux sous-domaines : `sp` si publié, sinon `p`."""
        return self.sp if self.sp is not None else self.p


class DmarcReport(DmarcModel):
    """Rapport DMARC agrégé complet et validé."""

    metadata: ReportMetadata
    policy_published: PublishedPolicy
    records: list[Record] = Field(min_length=1)
    version: float | None = Field(default=None, gt=0)

    @property
    def total_messages(self) -> int:
        """Somme des compteurs des records.

        simple somme des valeurs validées ; aucun taux n'est calculé ici.
        """
        return sum(record.message_count for record in self.records)

    @property
    def domain(self) -> str | None:
        """Domaine publié dans la politique, s'il est déclaré."""
        return self.policy_published.domain


__all__ = [
    "AuthResults",
    "AlignmentMode",
    "DateRange",
    "DkimAuthResult",
    "DkimResult",
    "Disposition",
    "DmarcEvaluation",
    "DmarcPolicy",
    "DmarcReport",
    "DmarcModel",
    "DomainName",
    "Identifiers",
    "MessageCount",
    "Percentage",
    "PolicyEvaluated",
    "PublishedPolicy",
    "Reason",
    "ReasonType",
    "Record",
    "ReportMetadata",
    "SourceIP",
    "SpfAuthResult",
    "SpfResult",
    "UtcDateTime",
]