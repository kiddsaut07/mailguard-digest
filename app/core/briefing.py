"""Briefing en anglais, construit à partir des résultats déterministes du moteur.

Règles absolues de ce module :

- il ne calcule **aucun** chiffre : tous les nombres proviennent de
  `app/core/rules.py`, via l'objet `Analyse` reçu en paramètre ;
- il n'effectue aucun appel réseau, aucune requête vers un modèle de langue ;
- il ne qualifie aucune adresse IP et ne recommande aucun changement de
  politique DMARC ;
- il n'invente aucune donnée : une information absente est signalée comme
  telle ;
- pour une même analyse, il produit toujours exactement le même texte, sources
  et constats compris.

La reformulation par une IA locale, ajoutée plus tard, pourra porter sur ce texte
uniquement : elle ne pourra pas modifier les métriques, qui restent calculées ici.
"""

from __future__ import annotations

from datetime import datetime

from app.core.rules import (
    Analyse,
    ModelCalcule,
    NiveauConstat,
    formuler_compte,
)

NON_DISPONIBLE = "Not available in the report"
"""Formulation honnête employée quand une information est absente du document."""

ORDRE_NIVEAUX = (
    NiveauConstat.ATTENTION,
    NiveauConstat.INFO,
    NiveauConstat.INFORMATION_INDISPONIBLE,
)
"""Ordre de lecture des constats : ce qui appelle une vérification d'abord."""

LIMITES_ANALYSE = (
    "An aggregate DMARC report describes volumes and authentication verdicts, "
    "not message content or the fate of individual messages.",
    "An address associated with a DMARC failure is not qualified: the report "
    "contains no evidence to judge its activity.",
    "Raw SPF and DKIM results reported by the server do not guarantee DMARC "
    "alignment: only evaluated verdicts are used for the rates.",
    "An aggregate disposition does not prove that a message was delivered, "
    "quarantined or rejected.",
    "This briefing makes no recommendation to change the DMARC policy.",
    "Every figure comes from the report counters: nothing was estimated or filled in.",
)
"""Limites d'interprétation, reprises de `03_SECURITY_PRIVACY.md`."""

FORMAT_DATE = "%Y-%m-%d %H:%M"
"""Format de date UTC, non ambigu pour une audience internationale."""


class ChiffreCle(ModelCalcule):
    """Un chiffre du briefing, avec la mesure dont il est issu."""

    libelle: str
    valeur: str
    mesure: str


class Observation(ModelCalcule):
    """Un constat reformulé, conservé avec son niveau et sa limite."""

    identifiant: str
    niveau: NiveauConstat
    titre: str
    texte: str
    limite: str


class Briefing(ModelCalcule):
    """Briefing complet, déterministe et sans donnée inventée."""

    periode: str
    domaine: str
    organisation: str
    identifiant_rapport: str
    resume_executif: str
    chiffres_cles: list[ChiffreCle]
    observations: list[Observation]
    points_a_verifier: list[str]
    limites: list[str]
    a_retenir: list[str]

    @property
    def texte_complet(self) -> str:
        """Briefing rendu en texte simple, dans l'ordre des sections."""
        sections = [
            self.resume_executif,
            "Key figures: "
            + " ; ".join(f"{cle.libelle}: {cle.valeur}" for cle in self.chiffres_cles),
            "Findings: "
            + " | ".join(observation.texte for observation in self.observations),
            "To verify: " + " | ".join(self.points_a_verifier),
            "Limits: " + " | ".join(self.limites),
            "Key takeaways: " + " | ".join(self.a_retenir),
        ]
        return "\n".join(section for section in sections if section.strip())


def construire_briefing(analyse: Analyse) -> Briefing:
    """Transforme une analyse déterministe en briefing anglais lisible."""
    return Briefing(
        periode=_periode(analyse),
        domaine=_domaine(analyse),
        organisation=_organisation(analyse),
        identifiant_rapport=_identifiant(analyse),
        resume_executif=_resume_executif(analyse),
        chiffres_cles=_chiffres_cles(analyse),
        observations=_observations(analyse),
        points_a_verifier=_points_a_verifier(analyse),
        limites=list(LIMITES_ANALYSE),
        a_retenir=_a_retenir(analyse),
    )


# --- Éléments d'en-tête ------------------------------------------------------


def _formater_date(moment: datetime) -> str:
    """Date UTC affichée dans un format non ambigu."""
    return moment.strftime(FORMAT_DATE) + " UTC"


def _periode(analyse: Analyse) -> str:
    """Période couverte, une ligne par couple début/fin distinct."""
    if not analyse.metriques.periodes:
        return NON_DISPONIBLE
    return " ; ".join(
        f"from {_formater_date(debut)} to {_formater_date(fin)}"
        for debut, fin in analyse.metriques.periodes
    )


def _domaine(analyse: Analyse) -> str:
    """Domaine publié, ou formulation honnête s'il est absent ou multiple."""
    domaines = analyse.metriques.domaines_publies
    if not domaines:
        return NON_DISPONIBLE
    if len(domaines) == 1:
        return domaines[0]
    return "several domains: " + ", ".join(domaines)


def _organisation(analyse: Analyse) -> str:
    """Organisation émettrice, déclarée par le serveur de rapport."""
    if not analyse.rapports:
        return NON_DISPONIBLE
    return analyse.rapports[0].contexte.organisation


def _identifiant(analyse: Analyse) -> str:
    """Identifiants de rapport, listés seulement s'ils sont présents."""
    identifiants = [
        rapport.contexte.identifiant_rapport
        for rapport in analyse.rapports
        if rapport.contexte.identifiant_rapport is not None
    ]
    if not identifiants:
        return NON_DISPONIBLE
    return " ; ".join(sorted(identifiants))


# --- Résumé et chiffres ------------------------------------------------------


def _resume_executif(analyse: Analyse) -> str:
    """Trois à cinq phrases factuelles, construites à partir des mesures."""
    metriques = analyse.metriques
    phrases = [
        f"This briefing covers "
        f"{formuler_compte(metriques.total_messages, 'counted message', 'counted messages')} "
        f"in {formuler_compte(metriques.nombre_records, 'record', 'records')}, "
        f"from {formuler_compte(metriques.nombre_rapports, 'report', 'reports')}, "
        f"over the period {_periode(analyse)}.",
        _phrase_taux(metriques.taux_pass, metriques.taux_fail, metriques),
        _phrase_sources(analyse),
        f"Dispositions declared by the reporting server: {metriques.dispositions.affichage}.",
        _phrase_constats(analyse),
    ]
    return " ".join(phrase for phrase in phrases if phrase)


def _phrase_taux(taux_pass, taux_fail, metriques) -> str:
    """Phrase de synthèse sur les taux, honnête si le calcul est impossible."""
    if not taux_pass.disponible:
        return (
            "Since no messages are counted, the pass and failure rates cannot be "
            "calculated."
        )
    return (
        f"The DMARC pass rate is {taux_pass.affichage} and the failure rate is "
        f"{taux_fail.affichage}, that is "
        f"{formuler_compte(metriques.messages_fail, 'message', 'messages')} with a "
        "fail verdict."
    )


def _phrase_sources(analyse: Analyse) -> str:
    """Phrase factuelle sur les sources déclarées par le rapport."""
    sources = analyse.sources
    if not sources:
        return "No source is listed in this set of reports."
    avec_echecs = [source for source in sources if source.messages_fail > 0]
    if not avec_echecs:
        return (
            f"{formuler_compte(len(sources), 'source is', 'sources are')} declared, "
            "none of them associated with a DMARC failure during this period."
        )
    return (
        f"{formuler_compte(len(sources), 'source is', 'sources are')} declared, "
        f"{formuler_compte(len(avec_echecs), 'of them is', 'of them are')} associated "
        f"with DMARC failures covering "
        f"{formuler_compte(sum(source.messages_fail for source in avec_echecs), 'message', 'messages')}."
    )


def _phrase_constats(analyse: Analyse) -> str:
    """Phrase de conclusion factuelle, sans promesse de sécurité."""
    attentions = [
        constat
        for constat in analyse.constats
        if constat.niveau is NiveauConstat.ATTENTION
    ]
    if not attentions:
        return (
            "The findings listed below describe the report data; the absence of an "
            "attention-level finding is not a security guarantee."
        )
    return (
        f"{formuler_compte(len(attentions), 'finding requires', 'findings require')} "
        "human verification; they describe the report data and establish neither an "
        "origin nor an intent."
    )


def _chiffres_cles(analyse: Analyse) -> list[ChiffreCle]:
    """Chiffres principaux, chacun relié à sa mesure déterministe."""
    metriques = analyse.metriques
    chiffres = [
        ChiffreCle(
            libelle="Total messages",
            valeur=str(metriques.total_messages),
            mesure="total_messages",
        ),
        ChiffreCle(
            libelle="DMARC pass",
            valeur=_valeur_ou_indisponible(metriques.taux_pass, metriques.messages_pass),
            mesure="taux_pass",
        ),
        ChiffreCle(
            libelle="DMARC fail",
            valeur=_valeur_ou_indisponible(metriques.taux_fail, metriques.messages_fail),
            mesure="taux_fail",
        ),
        ChiffreCle(
            libelle="Observed dispositions (none / quarantine / reject)",
            valeur=(
                f"{metriques.dispositions.none} / {metriques.dispositions.quarantine}"
                f" / {metriques.dispositions.reject}"
            ),
            mesure="dispositions",
        ),
        ChiffreCle(
            libelle="Reported sources",
            valeur=str(len(analyse.sources)),
            mesure="nombre_sources",
        ),
        ChiffreCle(
            libelle="Published policy",
            valeur=", ".join(_politiques_publiees(analyse)),
            mesure="politique_publiee",
        ),
    ]
    return chiffres


def _politiques_publiees(analyse: Analyse) -> list[str]:
    """Valeurs p et sp effectivement publiées, par contexte distinct."""
    valeurs: list[str] = []
    for rapport in analyse.rapports:
        domaine = rapport.contexte.domaine_publie or "domain not declared"
        texte = f"{domaine}: p={rapport.politique_publiee}"
        if rapport.politique_sous_domaines_publiee is not None:
            texte += f", sp={rapport.politique_sous_domaines_publiee}"
        if texte not in valeurs:
            valeurs.append(texte)
    return valeurs


def _valeur_ou_indisponible(taux, messages: int) -> str:
    """Chiffre d'un taux : pourcentage, ou formule honnête s'il est impossible."""
    if not taux.disponible:
        return "Not calculable (no messages counted)"
    return f"{taux.affichage} ({formuler_compte(messages, 'message', 'messages')})"


# --- Observations, vérifications et synthèse --------------------------------


def _observations(analyse: Analyse) -> list[Observation]:
    """Constats reformulés, classés par niveau puis dans leur ordre de production."""
    groupes = analyse.constats_par_niveau
    return [
        Observation(
            identifiant=constat.identifiant,
            niveau=constat.niveau,
            titre=constat.titre,
            texte=constat.description,
            limite=constat.limites,
        )
        for niveau in ORDRE_NIVEAUX
        for constat in groupes[niveau]
    ]


def _points_a_verifier(analyse: Analyse) -> list[str]:
    """Points de vérification humaine, dérivés des constats établis."""
    points: list[str] = []
    for source in analyse.sources:
        if source.messages_fail > 0:
            origine = (
                source.contexte.identifiant_rapport
                if source.contexte.identifiant_rapport is not None
                else "report without a declared identifier"
            )
            points.append(
                f"Review with the business owner the origin of the "
                f"{formuler_compte(source.messages_fail, 'message', 'messages')} "
                f"associated with DMARC failures for source {source.adresse_ip} "
                f"({origine})."
            )
    for rapport in analyse.rapports:
        if rapport.contexte.domaine_publie is None:
            points.append(
                "Request the published domain: it is absent from the analyzed report "
                "and conclusions cannot be attached to it."
            )
        if rapport.politique_sous_domaines_publiee is None:
            points.append(
                f"Check the DMARC record of "
                f"{rapport.contexte.domaine_publie or 'this domain'}: no sp tag is "
                "published, so the p value applies to subdomains."
            )
        if rapport.erreur_declaree is not None:
            points.append(
                "The reporting server signals a generation error: request a complete "
                "report before drawing conclusions from it."
            )
    if not analyse.metriques.taux_pass.disponible:
        points.append(
            "Obtain a report covering a period that contains messages before "
            "computing any rate."
        )
    if len(analyse.metriques.domaines_publies) > 1:
        points.append(
            "Attach every conclusion to its domain: this import covers several "
            "published domains."
        )
    return points


def _a_retenir(analyse: Analyse) -> list[str]:
    """Faits établis uniquement, sans interprétation supplémentaire."""
    metriques = analyse.metriques
    avec_echecs = [source for source in analyse.sources if source.messages_fail > 0]
    faits = [
        f"{formuler_compte(metriques.total_messages, 'message was', 'messages were')} "
        f"analyzed over the period {_periode(analyse)}.",
    ]
    if metriques.taux_pass.disponible:
        faits.append(
            f"The DMARC pass rate measured on this data is {metriques.taux_pass.affichage}."
        )
    else:
        faits.append("No rate can be calculated: no message is counted.")
    faits.append(
        f"{formuler_compte(len(avec_echecs), 'source is', 'sources are')} associated "
        "with DMARC failures in this scope."
        if avec_echecs
        else "No source is associated with a DMARC failure in this scope."
    )
    faits.append(
        f"The dispositions declared by the reporting server are: "
        f"{metriques.dispositions.affichage}."
    )
    return faits


__all__ = [
    "Briefing",
    "ChiffreCle",
    "LIMITES_ANALYSE",
    "NON_DISPONIBLE",
    "Observation",
    "construire_briefing",
]