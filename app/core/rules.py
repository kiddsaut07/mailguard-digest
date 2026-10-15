"""Moteur de règles DMARC : métriques, constats et contrôle des invariants.

Source de vérité
----------------

Ce module est l'unique endroit où des chiffres sont calculés à partir d'un
rapport importé. Le briefing (`app/core/briefing.py`) ne fait que reformuler ces
résultats structurés, et l'IA optionnelle ne pourra que reformuler ce texte.

Le moteur travaille exclusivement sur des objets `DmarcReport` déjà validés par
`app/core/parser.py`. Il n'accède ni à Flask, ni à SQLite, ni au réseau, et ne
qualifie jamais une adresse IP.

Formules, toutes vérifiables sur les objets d'entrée
----------------------------------------------------

- `total_messages` = somme de `record.message_count`, c'est-à-dire la somme des
  éléments `count` du rapport.
- `messages_pass` = somme de `message_count` pour les records dont le **verdict
  DMARC évalué** vaut `pass` pour au moins un mécanisme, c'est-à-dire
  `record.dmarc_pass`, qui lit `policy_evaluated` et jamais `auth_results`.
- `messages_fail` = `total_messages - messages_pass`.
- `taux_pass` = `messages_pass / total_messages * 100`, ou `None` si
  `total_messages == 0` : un taux indisponible n'est jamais remplacé par 0.
- `dispositions` = somme des compteurs groupée par `policy_evaluated.disposition`.
- `verdis evalués` = somme des compteurs selon `policy_evaluated.spf` et
  `policy_evaluated.dkim`, exprimés en messages et non en nombre de records.
- `résultats bruts` = nombre d'occurrences de `auth_results`, regroupées par
  mécanisme, résultat et domaine. Ce ne sont pas des verdicts DMARC : ils sont
  conservés à part et ne participent à aucun taux de conformité.

Aucun taux n'est obtenu par moyenne de taux par record : tous sont pondérés par
le nombre de messages. La précision flottante est conservée en interne, l'arrondi
n'intervient que dans l'affichage (`Taux.affichage`).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.models import (
    AlignmentMode,
    DmarcEvaluation,
    DmarcPolicy,
    DmarcReport,
    Disposition,
    Record,
)

DECIMALES_AFFICHAGE = 1
"""Décimales utilisées uniquement pour l'affichage d'un taux."""

Mecanisme = Literal["spf", "dkim"]
"""Mécanismes d'authentification utilisés pour les verdicts évalués."""


def formuler_compte(nombre: int, singulier: str, pluriel: str) -> str:
    """Formule accordé et déterministe : « 1 source », « 3 sources ».

    Partagée avec `app/core/briefing.py` pour éviter deux règles d'accord
    divergentes dans le texte affiché.
    """
    return f"{nombre} {singulier if nombre <= 1 else pluriel}"


class ModelCalcule(BaseModel):
    """Base des résultats : objets figés, sans champ inconnu accepté."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class NiveauConstat(StrEnum):
    """Niveau d'un constat.

    `ATTENTION` signale une situation à regarder, jamais une faute prouvée.
    `INFO` décrit un fait neutre. `INFORMATION_INDISPONIBLE` signale une donnée
    absente qui empêche une conclusion. Aucun niveau plus grave n'existe : les
    documents de référence ne définissent aucune base de gravité supérieure.
    """

    ATTENTION = "attention"
    INFO = "info"
    INFORMATION_INDISPONIBLE = "indisponible"


class CategorieIncoherence(StrEnum):
    """Nature d'une anomalie relevée sur un rapport."""

    INCOHERENCE = "incoherence"
    DONNEE_INHABITUELLE = "donnee_inhabituelle"
    DONNEE_MANQUANTE = "donnee_manquante"


class Taux(ModelCalcule):
    """Ratio pondéré par le nombre de messages, jamais arrondi en interne."""

    numerateur: int
    denominateur: int
    valeur: float | None

    @classmethod
    def calculer(cls, numerateur: int, denominateur: int) -> Taux:
        """Construit un taux ; `valeur` vaut `None` si le dénominateur est nul."""
        if denominateur < 0:
            raise ValueError("a rate denominator cannot be negative")
        valeur = None if denominateur == 0 else (numerateur / denominateur) * 100
        return cls(numerateur=numerateur, denominateur=denominateur, valeur=valeur)

    @property
    def disponible(self) -> bool:
        """Vrai si le taux a pu être calculé."""
        return self.valeur is not None

    @property
    def affichage(self) -> str:
        """Texte de présentation, arrondi à l'affichage uniquement."""
        if self.valeur is None:
            return "Not calculable (no messages counted)"
        return f"{self.valeur:.{DECIMALES_AFFICHAGE}f}" + " %"


class RepartitionDispositions(ModelCalcule):
    """Messages comptés par disposition évaluée."""

    none: int = 0
    quarantine: int = 0
    reject: int = 0

    @classmethod
    def depuis_records(cls, records: Sequence[Record]) -> RepartitionDispositions:
        """Somme les compteurs par `policy_evaluated.disposition`."""
        compteurs = {valeur: 0 for valeur in Disposition}
        for record in records:
            compteurs[record.policy_evaluated.disposition] += record.message_count
        return cls(
            none=compteurs[Disposition.NONE],
            quarantine=compteurs[Disposition.QUARANTINE],
            reject=compteurs[Disposition.REJECT],
        )

    @property
    def total(self) -> int:
        """Total des messages répartis par disposition."""
        return self.none + self.quarantine + self.reject

    @property
    def affichage(self) -> str:
        """Readable breakdown, keeping the RFC 7489 order."""
        return f"none : {self.none}, quarantine : {self.quarantine}, reject : {self.reject}"


class RepartitionVerdicts(ModelCalcule):
    """Messages répartis entre verdict DMARC évalué `pass` et `fail`."""

    reussite: int = 0
    echec: int = 0

    @property
    def total(self) -> int:
        """Total des messages classifiés par ce mécanisme évalué."""
        return self.reussite + self.echec


class ResultatBrutAuthentification(ModelCalcule):
    """Occurrences d'un résultat brut déclaré par le serveur.

    Ce n'est pas un verdict DMARC : aucun taux de conformité n'est calculé à
    partir de cette structure.
    """

    mecanisme: str
    resultat: str
    domaine: str
    occurrences: int


class ContexteRapport(ModelCalcule):
    """Origine d'un rapport : indispensable pour rattacher chaque chiffre."""

    index_rapport: int
    organisation: str
    domaine_publie: str | None
    identifiant_rapport: str | None


class SourceDmarc(ModelCalcule):
    """Vue par adresse IP source, à l'intérieur d'un contexte de rapport.

    Deux rapports différents donnent deux vues distinctes, même pour une même
    adresse : aucune mesure n'est fusionnée entre contextes de politique.
    """

    adresse_ip: str
    contexte: ContexteRapport
    total_messages: int
    nombre_records: int
    messages_pass: int
    messages_fail: int
    taux_pass: Taux
    taux_fail: Taux
    verdis_spf_evalues: RepartitionVerdicts
    verdis_dkim_evalues: RepartitionVerdicts
    dispositions: RepartitionDispositions
    domaines_en_tete: list[str]
    resultats_bruts: list[ResultatBrutAuthentification]
    indices_records: list[int]


class RapportAnalyse(ModelCalcule):
    """Métriques d'un rapport importé, sans aucune interprétation."""

    contexte: ContexteRapport
    date_debut: datetime
    date_fin: datetime
    duree_secondes: int
    politique_publiee: DmarcPolicy
    politique_sous_domaines_publiee: DmarcPolicy | None
    politique_sous_domaines_effective: DmarcPolicy
    alignement_dkim: AlignmentMode
    alignement_spf: AlignmentMode
    pourcentage_politique: int
    total_messages: int
    nombre_records: int
    messages_pass: int
    messages_fail: int
    taux_pass: Taux
    taux_fail: Taux
    dispositions: RepartitionDispositions
    sources: list[SourceDmarc]
    erreur_declaree: str | None


class Metriques(ModelCalcule):
    """Métriques agrégées, tous rapports confondus."""

    nombre_rapports: int
    nombre_records: int
    total_messages: int
    messages_pass: int
    messages_fail: int
    taux_pass: Taux
    taux_fail: Taux
    dispositions: RepartitionDispositions
    domaines_publies: list[str]
    periodes: list[tuple[datetime, datetime]]


class Constat(ModelCalcule):
    """Fait vérifiable, rattaché aux mesures et aux sources qui le justifient."""

    identifiant: str
    niveau: NiveauConstat
    titre: str
    description: str
    mesures: dict[str, int | float | str | None]
    sources: list[str]
    limites: str


class Incoherence(ModelCalcule):
    """Anomalie relevée sur les données, distincte d'une valeur refusée."""

    identifiant: str
    categorie: CategorieIncoherence
    description: str
    contexte: str | None


class Analyse(ModelCalcule):
    """Résultat complet du moteur de règles pour un ou plusieurs rapports."""

    rapports: list[RapportAnalyse]
    metriques: Metriques
    sources: list[SourceDmarc]
    constats: list[Constat]
    incoherences: list[Incoherence]

    @property
    def a_des_incoherences(self) -> bool:
        """Vrai si au moins une incohérence a été relevée."""
        return bool(self.incoherences)

    @property
    def total_messages(self) -> int:
        """Total des messages représentés par l'ensemble des rapports."""
        return self.metriques.total_messages

    @property
    def constats_par_niveau(self) -> dict[NiveauConstat, list[Constat]]:
        """Constats regroupés par niveau, dans l'ordre de production."""
        groupes = {niveau: [] for niveau in NiveauConstat}
        for constat in self.constats:
            groupes[constat.niveau].append(constat)
        return groupes


# --- API publique ------------------------------------------------------------


def analyser_rapport(rapport: DmarcReport) -> Analyse:
    """Analyse un rapport unique."""
    return analyser([rapport])


def analyser(rapports: Sequence[DmarcReport]) -> Analyse:
    """Analyse des rapports validés et renvoie métriques, sources, constats.

    Les rapports de domaines différents restent distingués : chaque source est
    rattachée à son contexte et aucune conformité n'est fusionnée entre
    contextes de politique.
    """
    analyses = [
        _analyser_un_rapport(rapport, index) for index, rapport in enumerate(rapports)
    ]
    tous_records = [record for rapport in rapports for record in rapport.records]
    metriques = _metriques_globales(rapports, tous_records)
    sources = _sources_globales(analyses)
    incoherences = detecter_incoherences(rapports)
    constats = _construire_constats(analyses, metriques, sources, incoherences)
    return Analyse(
        rapports=analyses,
        metriques=metriques,
        sources=sources,
        constats=constats,
        incoherences=incoherences,
    )


def detecter_incoherences(rapports: Sequence[DmarcReport]) -> list[Incoherence]:
    """Relève les anomalies déductibles des données, sans rien corriger.

    Trois familles sont distinguées : incohérence, donnée inhabituelle mais
    valide, donnée manquante. Un rapport valide n'est jamais rejeté parce que
    ses résultats sont inhabituels.
    """
    releves: list[Incoherence] = []
    for rapport in rapports:
        releves += _incoherences_dun_rapport(rapport)
    releves += _incoherences_transversales(rapports)
    return releves


# --- Analyse d'un rapport ----------------------------------------------------


def _analyser_un_rapport(rapport: DmarcReport, index: int) -> RapportAnalyse:
    """Calcule les métriques d'un rapport et les vues par source."""
    records = rapport.records
    total = rapport.total_messages
    reussite = sum(record.message_count for record in records if record.dmarc_pass)
    return RapportAnalyse(
        contexte=_contexte(rapport, index),
        date_debut=rapport.metadata.date_range.begin,
        date_fin=rapport.metadata.date_range.end,
        duree_secondes=rapport.metadata.date_range.duration_seconds,
        politique_publiee=rapport.policy_published.p,
        politique_sous_domaines_publiee=rapport.policy_published.sp,
        politique_sous_domaines_effective=rapport.policy_published.effective_subdomain_policy,
        alignement_dkim=rapport.policy_published.adkim,
        alignement_spf=rapport.policy_published.aspf,
        pourcentage_politique=rapport.policy_published.pct,
        total_messages=total,
        nombre_records=len(records),
        messages_pass=reussite,
        messages_fail=total - reussite,
        taux_pass=Taux.calculer(reussite, total),
        taux_fail=Taux.calculer(total - reussite, total),
        dispositions=RepartitionDispositions.depuis_records(records),
        sources=_sources_dun_rapport(rapport, index),
        erreur_declaree=rapport.metadata.error,
    )


def _contexte(rapport: DmarcReport, index: int) -> ContexteRapport:
    """Origine du rapport, utilisée pour rattacher chaque source à son domaine."""
    return ContexteRapport(
        index_rapport=index,
        organisation=rapport.metadata.org_name,
        domaine_publie=rapport.policy_published.domain,
        identifiant_rapport=rapport.metadata.report_id,
    )


def _sources_dun_rapport(rapport: DmarcReport, index: int) -> list[SourceDmarc]:
    """Construit une vue par adresse IP source du rapport."""
    groupes: dict[str, list[tuple[int, Record]]] = {}
    for position, record in enumerate(rapport.records):
        groupes.setdefault(record.source_ip, []).append((position, record))

    sources = [
        _construire_source(adresse, elements, _contexte(rapport, index))
        for adresse, elements in groupes.items()
    ]
    return _trier_sources(sources)


def _construire_source(
    adresse: str,
    elements: Sequence[tuple[int, Record]],
    contexte: ContexteRapport,
) -> SourceDmarc:
    """Agrège les records d'une même adresse IP sans perdre les nuances."""
    records = [record for _, record in elements]
    total = sum(record.message_count for record in records)
    reussite = sum(record.message_count for record in records if record.dmarc_pass)
    return SourceDmarc(
        adresse_ip=adresse,
        contexte=contexte,
        total_messages=total,
        nombre_records=len(records),
        messages_pass=reussite,
        messages_fail=total - reussite,
        taux_pass=Taux.calculer(reussite, total),
        taux_fail=Taux.calculer(total - reussite, total),
        verdis_spf_evalues=_repartir_verdicts(records, "spf"),
        verdis_dkim_evalues=_repartir_verdicts(records, "dkim"),
        dispositions=RepartitionDispositions.depuis_records(records),
        domaines_en_tete=sorted(
            {
                record.identifiers.header_from
                for record in records
                if record.identifiers.header_from is not None
            }
        ),
        resultats_bruts=_resultats_bruts(records),
        indices_records=sorted(position for position, _ in elements),
    )


def _repartir_verdicts(records: Sequence[Record], mecanisme: Mecanisme) -> RepartitionVerdicts:
    """Répartit les messages selon un verdict DMARC évalué (`spf` ou `dkim`)."""
    reussite = 0
    echec = 0
    for record in records:
        verdict = (
            record.policy_evaluated.spf
            if mecanisme == "spf"
            else record.policy_evaluated.dkim
        )
        if verdict is DmarcEvaluation.PASS:
            reussite += record.message_count
        else:
            echec += record.message_count
    return RepartitionVerdicts(reussite=reussite, echec=echec)


def _resultats_bruts(records: Sequence[Record]) -> list[ResultatBrutAuthentification]:
    """Compte les résultats bruts déclarés par le serveur, sans les interpréter."""
    occurrences: dict[tuple[str, str, str], int] = {}
    for record in records:
        for resultat in record.auth_results.spf:
            _compter(occurrences, ("spf", resultat.result, resultat.domain))
        for resultat in record.auth_results.dkim:
            _compter(occurrences, ("dkim", resultat.result, resultat.domain))
    return [
        ResultatBrutAuthentification(
            mecanisme=mecanisme, resultat=resultat, domaine=domaine, occurrences=nombre
        )
        for (mecanisme, resultat, domaine), nombre in sorted(occurrences.items())
    ]


def _compter(compteur: dict[tuple[str, str, str], int], cle: tuple[str, str, str]) -> None:
    """Incrémente un compteur d'occurrences."""
    compteur[cle] = compteur.get(cle, 0) + 1


def _sources_globales(analyses: Sequence[RapportAnalyse]) -> list[SourceDmarc]:
    """Réunit les vues par source de tous les rapports, sans les fusionner."""
    return _trier_sources([source for analyse in analyses for source in analyse.sources])


def _trier_sources(sources: Sequence[SourceDmarc]) -> list[SourceDmarc]:
    """Ordre déterministe : volume décroissant, puis adresse IP."""
    return sorted(sources, key=lambda source: (-source.total_messages, source.adresse_ip))


def _metriques_globales(
    rapports: Sequence[DmarcReport], records: Sequence[Record]
) -> Metriques:
    """Agrège les compteurs de tous les rapports fournis."""
    total = sum(record.message_count for record in records)
    reussite = sum(record.message_count for record in records if record.dmarc_pass)
    domaines = sorted(
        {
            rapport.policy_published.domain
            for rapport in rapports
            if rapport.policy_published.domain is not None
        }
    )
    periodes = sorted(
        {
            (rapport.metadata.date_range.begin, rapport.metadata.date_range.end)
            for rapport in rapports
        }
    )
    return Metriques(
        nombre_rapports=len(rapports),
        nombre_records=len(records),
        total_messages=total,
        messages_pass=reussite,
        messages_fail=total - reussite,
        taux_pass=Taux.calculer(reussite, total),
        taux_fail=Taux.calculer(total - reussite, total),
        dispositions=RepartitionDispositions.depuis_records(records),
        domaines_publies=domaines,
        periodes=periodes,
    )


# --- Détection des incohérences ---------------------------------------------


def verifier_coherence_dispositions(
    total_messages: int, dispositions: RepartitionDispositions, contexte: str | None = None
) -> Incoherence | None:
    """Vérifie que la somme des dispositions égale le nombre de messages.

    Contrôle exposé séparément car, après validation des modèles, l'incohérence
    est structurellement impossible : la fonction est testée directement sur des
    valeurs incohérentes, sans affaiblir les modèles ni la validation.
    """
    if dispositions.total == total_messages:
        return None
    return Incoherence(
        identifiant="dispositions-incoherentes",
        categorie=CategorieIncoherence.INCOHERENCE,
        description=(
            f"the sum of dispositions is {dispositions.total} while the "
            f"records account for {total_messages} messages"
        ),
        contexte=contexte,
    )


def _incoherences_dun_rapport(rapport: DmarcReport) -> list[Incoherence]:
    """Contrôles appliqués à un rapport."""
    releves: list[Incoherence] = []
    total = rapport.total_messages
    ecart_dispositions = verifier_coherence_dispositions(
        total,
        RepartitionDispositions.depuis_records(rapport.records),
        contexte=rapport.metadata.report_id,
    )
    if ecart_dispositions is not None:
        releves.append(ecart_dispositions)
    releves += _incoherences_volumes_nuls(rapport)
    if total == 0:
        releves.append(
            Incoherence(
                identifiant="volume-total-nul",
                categorie=CategorieIncoherence.DONNEE_INHABITUELLE,
                description=(
                    "no messages are counted in this report: rates cannot be calculated"
                ),
                contexte=rapport.metadata.report_id,
            )
        )
    releves += _donnees_manquantes(rapport)
    return releves


def _incoherences_volumes_nuls(rapport: DmarcReport) -> list[Incoherence]:
    """Signale les records sans volume : donnée valide, mais inhabituelle."""
    return [
        Incoherence(
            identifiant="record-sans-volume",
            categorie=CategorieIncoherence.DONNEE_INHABITUELLE,
            description=(
                f"record #{index + 1} ({record.source_ip}) counts zero messages"
            ),
            contexte=f"record {index + 1}",
        )
        for index, record in enumerate(rapport.records)
        if record.message_count == 0
    ]


def _donnees_manquantes(rapport: DmarcReport) -> list[Incoherence]:
    """Signale les champs facultatifs absents qui limitent l'interprétation."""
    manquants: list[Incoherence] = []
    if rapport.policy_published.domain is None:
        manquants.append(
            Incoherence(
                identifiant="domaine-publie-absent",
                categorie=CategorieIncoherence.DONNEE_MANQUANTE,
                description="the published domain is absent from the report",
                contexte=rapport.metadata.org_name,
            )
        )
    if rapport.metadata.report_id is None:
        manquants.append(
            Incoherence(
                identifiant="identifiant-rapport-absent",
                categorie=CategorieIncoherence.DONNEE_MANQUANTE,
                description="the report identifier is absent",
                contexte=rapport.metadata.org_name,
            )
        )
    if rapport.metadata.error is not None:
        manquants.append(
            Incoherence(
                identifiant="erreur-declaree-par-le-rapport",
                categorie=CategorieIncoherence.DONNEE_MANQUANTE,
                description=(
                    "the reporting server declares a generation error: "
                    f"{rapport.metadata.error}"
                ),
                contexte=rapport.metadata.org_name,
            )
        )
    return manquants


def _incoherences_transversales(rapports: Sequence[DmarcReport]) -> list[Incoherence]:
    """Contrôles portant sur l'ensemble des rapports importés ensemble."""
    if len(rapports) < 2:
        return []
    domaines = sorted(
        {
            rapport.policy_published.domain
            for rapport in rapports
            if rapport.policy_published.domain is not None
        }
    )
    if len(domaines) > 1:
        return [
            Incoherence(
                identifiant="contextes-policiels-multiples",
                categorie=CategorieIncoherence.INCOHERENCE,
                description=(
                    "the imported reports cover several published domains: "
                    "every conclusion must stay attached to its own context"
                ),
                contexte=", ".join(domaines),
            )
        ]
    return []


# --- Constats déterministes --------------------------------------------------


def _construire_constats(
    analyses: Sequence[RapportAnalyse],
    metriques: Metriques,
    sources: Sequence[SourceDmarc],
    incoherences: Sequence[Incoherence],
) -> list[Constat]:
    """Applique les règles de constat dans un ordre fixe, donc reproductible.

    Aucun seuil de volume n'est inventé : une règle s'applique dès qu'un fait est
    établi, et toute valeur citée provient des mesures calculées.
    """
    constats: list[Constat] = [
        _constat_volume(metriques),
        _constat_echecs(metriques),
        _constat_sources_en_echec(sources),
        _constat_dispositions(metriques),
        _constat_taux_indisponible(metriques),
    ]
    constats = [constat for constat in constats if constat is not None]
    constats += _constats_politiques(analyses)
    constats += [
        _constat_donnee_manquante(incoherence)
        for incoherence in incoherences
        if incoherence.categorie is CategorieIncoherence.DONNEE_MANQUANTE
    ]
    constats += [
        _constat_anomalie(incoherence)
        for incoherence in incoherences
        if incoherence.categorie is not CategorieIncoherence.DONNEE_MANQUANTE
    ]
    return constats


def _constat_volume(metriques: Metriques) -> Constat:
    """Volume total observé, toujours présent."""
    return Constat(
        identifiant="volume-observe",
        niveau=NiveauConstat.INFO,
        titre="Observed volume",
        description=(
            f"{formuler_compte(metriques.total_messages, 'message spread', 'messages spread')} "
            f"across {formuler_compte(metriques.nombre_records, 'record', 'records')}, "
            f"from {formuler_compte(metriques.nombre_rapports, 'report', 'reports')}."
        ),
        mesures={
            "total_messages": metriques.total_messages,
            "nombre_records": metriques.nombre_records,
            "nombre_rapports": metriques.nombre_rapports,
        },
        sources=[],
        limites="The volume is the sum of the counters declared by the reporting server.",
    )


def _constat_echecs(metriques: Metriques) -> Constat:
    """Verdict d'ensemble sur les échecs DMARC observés."""
    if metriques.messages_fail > 0:
        return Constat(
            identifiant="echecs-dmarc-observez",
            niveau=NiveauConstat.ATTENTION,
            titre="DMARC failures observed",
            description=(
                f"{formuler_compte(metriques.messages_fail, 'message is', 'messages are')} "
                f"associated with a DMARC verdict of fail, a failure rate of "
                f"{metriques.taux_fail.affichage}."
            ),
            mesures={
                "messages_fail": metriques.messages_fail,
                "taux_fail": metriques.taux_fail.valeur,
                "messages_pass": metriques.messages_pass,
            },
            sources=[],
            limites=(
                "A DMARC failure indicates no successful alignment according to the "
                "report; it does not qualify the origin of the messages."
            ),
        )
    if metriques.total_messages == 0:
        return Constat(
            identifiant="volume-nul",
            niveau=NiveauConstat.INFO,
            titre="No messages counted",
            description="This set of reports counts no messages: no rate can be calculated.",
            mesures={"total_messages": 0},
            sources=[],
            limites="The absence of messages says nothing about the domain configuration.",
        )
    return Constat(
        identifiant="echec-dmarc-non-observe",
        niveau=NiveauConstat.INFO,
        titre="No DMARC failure observed",
        description=(
            f"The {formuler_compte(metriques.total_messages, 'counted message', 'counted messages')} "
            f"all carry a DMARC verdict of pass, a pass rate of "
            f"{metriques.taux_pass.affichage}."
        ),
        mesures={
            "messages_pass": metriques.messages_pass,
            "taux_pass": metriques.taux_pass.valeur,
        },
        sources=[],
        limites=(
            "The absence of failures in a report does not prove that the "
            "configuration is complete or that every send was legitimate."
        ),
    )


def _constat_sources_en_echec(sources: Sequence[SourceDmarc]) -> Constat | None:
    """Sources associées à des échecs DMARC, sans qualification de leur nature."""
    concernees = [source for source in sources if source.messages_fail > 0]
    if not concernees:
        return None
    return Constat(
        identifiant="sources-avec-echecs-dmarc",
        niveau=NiveauConstat.ATTENTION,
        titre="Sources associated with failures",
        description=(
            f"{formuler_compte(len(concernees), 'source is', 'sources are')} "
            f"associated with DMARC failures, covering "
            f"{formuler_compte(sum(source.messages_fail for source in concernees), 'message', 'messages')} "
            "in total."
        ),
        mesures={
            "nombre_sources": len(concernees),
            "messages_fail_sources": sum(source.messages_fail for source in concernees),
            "messages_fail_max": max(source.messages_fail for source in concernees),
        },
        sources=[source.adresse_ip for source in concernees],
        limites=(
            "These addresses are those declared by the reporting server; their "
            "presence is not proof of malicious activity."
        ),
    )


def _constat_dispositions(metriques: Metriques) -> Constat:
    """Dispositions déclarées par le serveur, constat toujours présent."""
    return Constat(
        identifiant="dispositions-observees",
        niveau=NiveauConstat.INFO,
        titre="Observed dispositions",
        description=(
            f"Dispositions declared by the reporting server: {metriques.dispositions.affichage}."
        ),
        mesures={
            "none": metriques.dispositions.none,
            "quarantine": metriques.dispositions.quarantine,
            "reject": metriques.dispositions.reject,
        },
        sources=[],
        limites=(
            "An aggregate disposition describes a receiver request; it does not "
            "prove what happened to any individual message."
        ),
    )


def _constat_taux_indisponible(metriques: Metriques) -> Constat | None:
    """Signale honnêtement un taux impossible à calculer."""
    if metriques.taux_pass.disponible:
        return None
    return Constat(
        identifiant="taux-indisponible",
        niveau=NiveauConstat.INFORMATION_INDISPONIBLE,
        titre="Rate not calculable",
        description=(
            "Since no messages are counted, pass and failure rates cannot be "
            "calculated for this set of reports."
        ),
        mesures={"total_messages": metriques.total_messages},
        sources=[],
        limites="An unavailable rate is never replaced by a zero value.",
    )


def _constats_politiques(analyses: Sequence[RapportAnalyse]) -> list[Constat]:
    """Décrit la politique publiée de chaque contexte distinct, sans commenter."""
    constats: list[Constat] = []
    vus: set[tuple] = set()
    for analyse in analyses:
        cle = (
            analyse.contexte.domaine_publie,
            analyse.politique_publiee,
            analyse.politique_sous_domaines_publiee,
            analyse.politique_sous_domaines_effective,
            analyse.pourcentage_politique,
            analyse.alignement_dkim,
            analyse.alignement_spf,
        )
        if cle in vus:
            continue
        vus.add(cle)
        constats += _constats_politique(analyse)
    return constats


def _constats_politique(analyse: RapportAnalyse) -> list[Constat]:
    """Constats factuels sur la politique publiée d'un rapport."""
    domaine = analyse.contexte.domaine_publie or "domain not declared in the report"
    mesures: dict[str, int | float | str | None] = {
        "p": str(analyse.politique_publiee),
        "sp_publie": (
            None if analyse.politique_sous_domaines_publiee is None
            else str(analyse.politique_sous_domaines_publiee)
        ),
        "sp_effective": str(analyse.politique_sous_domaines_effective),
        "pct": analyse.pourcentage_politique,
        "adkim": str(analyse.alignement_dkim),
        "aspf": str(analyse.alignement_spf),
    }
    constats: list[Constat] = []
    if analyse.politique_publiee is DmarcPolicy.NONE:
        constats.append(
            Constat(
                identifiant="politique-en-mode-surveillance",
                niveau=NiveauConstat.INFO,
                titre="Published policy in monitoring mode",
                description=(
                    f"The published policy for {domaine} is p=none: receivers are "
                    "asked to request neither quarantine nor rejection."
                ),
                mesures=mesures,
                sources=[],
                limites=(
                    "This finding describes the published configuration; it makes no "
                    "recommendation to change it and says nothing about the fate of any "
                    "individual message."
                ),
            )
        )
    if analyse.politique_sous_domaines_publiee is not None:
        constats.append(
            Constat(
                identifiant="politique-sous-domaines-declaree",
                niveau=NiveauConstat.INFO,
                titre="Declared subdomain policy",
                description=(
                    f"For {domaine}, sp={analyse.politique_sous_domaines_publiee} is "
                    f"declared; without sp, the p value applies "
                    f"({analyse.politique_sous_domaines_effective})."
                ),
                mesures=mesures,
                sources=[],
                limites=(
                    "This value describes the published DNS record; receivers may "
                    "apply it differently."
                ),
            )
        )
    return constats


def _constat_donnee_manquante(incoherence: Incoherence) -> Constat:
    """Constat dédié à une information absente du rapport."""
    return Constat(
        identifiant=f"donnee-absente:{incoherence.identifiant}",
        niveau=NiveauConstat.INFORMATION_INDISPONIBLE,
        titre="Data absent from the report",
        description=incoherence.description[0].upper() + incoherence.description[1:] + ".",
        mesures={
            "categorie": str(incoherence.categorie),
            "contexte": incoherence_contexte_ou_none(incoherence),
        },
        sources=[],
        limites="Missing data is never replaced by an estimated value.",
    )


def incoherence_contexte_ou_none(incoherence: Incoherence) -> str | None:
    """Contexte textuel d'une incohérence, conservé tel quel ou `None`."""
    return incoherence.contexte


def _constat_anomalie(incoherence: Incoherence) -> Constat:
    """Constat dédié à une incohérence ou à une donnée inhabituelle."""
    if incoherence.categorie is CategorieIncoherence.DONNEE_INHABITUELLE:
        return Constat(
            identifiant=f"donnee-inhabituelle:{incoherence.identifiant}",
            niveau=NiveauConstat.INFO,
            titre="Unusual data",
            description=incoherence.description[0].upper() + incoherence.description[1:] + ".",
            mesures={"categorie": str(incoherence.categorie)},
            sources=[],
            limites=(
                "This value is valid; it only flags an unusual situation that "
                "deserves a careful reading."
            ),
        )
    return Constat(
        identifiant=f"incoherence:{incoherence.identifiant}",
        niveau=NiveauConstat.ATTENTION,
        titre="Inconsistency detected",
        description=incoherence.description[0].upper() + incoherence.description[1:] + ".",
        mesures={"categorie": str(incoherence.categorie)},
        sources=[],
        limites=(
            "The inconsistency is reported as is; no value was corrected "
            "automatically."
        ),
    )


__all__ = [
    "Analyse",
    "CategorieIncoherence",
    "ContexteRapport",
    "Constat",
    "Incoherence",
    "Metriques",
    "ModelCalcule",
    "NiveauConstat",
    "RapportAnalyse",
    "RepartitionDispositions",
    "RepartitionVerdicts",
    "ResultatBrutAuthentification",
    "SourceDmarc",
    "Taux",
    "analyser",
    "analyser_rapport",
    "detecter_incoherences",
    "formuler_compte",
    "verifier_coherence_dispositions",
]