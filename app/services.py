"""Pipeline d'import partagé par les routes et les tests.

Cette couche existe pour que l'interface HTTP et les autres appelants exécutent
exactement la même chaîne :

`fichier reçu → importateur sécurisé → rapports validés → moteur déterministe
→ briefing → stockage SQLite`

Elle ne contient aucun calcul métier : elle ordonne les appels et laisse remonter
telles quelles les exceptions métier des couches appelées.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing import TYPE_CHECKING

from app.core.archive import ImportLimits, import_reports
from app.core.briefing import Briefing, construire_briefing
from app.core.rules import Analyse, analyser
from app.storage.database import Enregistrement, StockageAnalyses

if TYPE_CHECKING:
    from app.ai.ollama_client import ClientOllama, ResultatNarration


@dataclass(frozen=True)
class ResultatImport:
    """Issue d'un import traité jusqu'à la persistance."""

    enregistrement: Enregistrement
    deja_importe: bool
    entrees_ignorees: tuple[str, ...] = ()
    """Entrées ZIP ignorées après validation, jamais interprétées comme rapports."""

    @property
    def analyse(self) -> Analyse:
        """Résultats déterminists, relus depuis la base lorsqu'il s'agit d'un doublon."""
        return self.enregistrement.analyse

    @property
    def briefing(self) -> Briefing:
        """Briefing déterministe correspondant aux résultats."""
        return self.enregistrement.briefing


def executer_import(
    stockage: StockageAnalyses,
    nom_fichier: str,
    contenu: bytes,
    limites: ImportLimits,
) -> ResultatImport:
    """Exécute le pipeline complet sur un fichier déjà reçu en mémoire.

    L'empreinte est calculée par la couche de stockage sur ces octets exacts :
    le XML n'est jamais conservé, seuls les résultats le sont. Un contenu déjà
    enregistré n'ajoute aucune ligne et renvoie l'analyse existante.
    """
    resultat = import_reports(nom_fichier, contenu, limites)
    analyse = analyser(resultat.reports)
    briefing = construire_briefing(analyse)
    enregistrement = stockage.enregistrer(contenu, resultat, analyse, briefing)
    return ResultatImport(
        enregistrement=enregistrement,
        deja_importe=not enregistrement.cree,
        entrees_ignorees=tuple(resultat.ignored_entries),
    )


__all__ = [
    "ResultatImport",
    "client_narration_de",
    "executer_import",
    "narration_stockee",
    "narrer_import",
]

# --- Narration locale facultative (étape 10) ---------------------------------

def client_narration_de(configuration) -> ClientOllama | None:
    """Construit l'adaptateur local, ou `None` si la narration est désactivée.

    Aucun appel réseau n'est effectué ici : la simple création du client est sans
    effet de bord. Le module d'IA n'est importé que lorsque la configuration
    l'exige, ce qui garde le chemin déterministe totalement indépendant.
    """
    if not configuration.ai_active:
        return None
    from app.ai.ollama_client import ClientOllama, ParametresNarration

    return ClientOllama(
        ParametresNarration(
            actif=True,
            url=configuration.ollama_url,
            modele=configuration.ollama_model,
            timeout_secondes=configuration.ollama_timeout_secondes,
            max_input_chars=configuration.ollama_max_input_chars,
            max_output_tokens=configuration.ollama_max_output_tokens,
            autorise_distant=configuration.ollama_allow_remote,
        )
    )


def narrer_import(resultat: ResultatImport, configuration) -> ResultatNarration:
    """Tente une narration locale après un import réussi.

    La narration est un complément affiché : elle n'est ni enregistrée, ni
    réinjectée dans l'analyse, et son échec ne modifie jamais le résultat
    déterministe. Elle est calculée une seule fois, à l'import, jamais au
    rechargement d'un rapport stocké.
    """
    from app.ai.ollama_client import ResultatNarration, StatutNarration

    client = client_narration_de(configuration)
    if client is None:
        return ResultatNarration(
            statut=StatutNarration.DESACTIVE, message="AI narration is disabled."
        )
    return client.narrer(resultat.analyse)


def narration_stockee() -> ResultatNarration:
    """Narration neutre pour un rapport rouvert depuis l'historique.

    Aucun appel au modèle n'est déclenché à la relecture : les rapports stockés
    n'ont pas de narration enregistrée, ce qui évite tout appel répété et reste
    cohérent avec l'absence de migration de base.
    """
    from app.ai.ollama_client import ResultatNarration, StatutNarration

    return ResultatNarration(
        statut=StatutNarration.INDISPONIBLE,
        message="AI narration is generated at import time only; stored reports are not re-narrated.",
    )
