"""Exports d'une analyse enregistrée : JSON structuré et CSV des sources.

Les deux exports sont construits **en mémoire** à partir des objets déjà
persistés (`Enregistrement.analyse` et `Enregistrement.briefing`) : ni le
parseur, ni l'importateur, ni le moteur de règles ne sont exécutés, et aucune
valeur n'est recalculée. Les fichiers temporaires sur disque sont inutiles et
absents.

Sécurité :

- aucun champ importé n'entre dans un en-tête HTTP : le nom de fichier proposé
  est construit à partir du seul identifiant numérique de l'analyse ;
- le contenu XML d'origine n'est jamais exporté, il n'est d'ailleurs pas stocké ;
- les valeurs CSV sont neutralisées contre l'injection de formule, car un nom de
  domaine ou un identifiant provient d'un rapport importé, donc non fiable ;
- aucune donnée n'est modifiée en base : ces fonctions sont en lecture seule.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from app.storage.database import Enregistrement

VERSION_EXPORT = 1
"""Version du format d'export, à faire évoluer de façon explicite."""

PREFIXES_DANGEREUX = ("=", "+", "-", "@", "\t", "\r")
"""Préfixes de formule neutralisés dans les cellules CSV."""

MARQUEUR_FORMULE = "'"
"""Caractère préposé à une valeur texte qui commence par un préfixe dangereux."""

COLONNES_CSV_SOURCES = (
    "source_ip",
    "total_messages",
    "messages_pass",
    "messages_fail",
    "failure_rate_percent",
    "evaluated_spf_pass",
    "evaluated_spf_fail",
    "evaluated_dkim_pass",
    "evaluated_dkim_fail",
    "disposition_none",
    "disposition_quarantine",
    "disposition_reject",
    "header_from_domains",
)
"""Colonnes du CSV, dans l'ordre, en anglais et stables."""


def nom_fichier_export(identifiant: int, extension: str) -> str:
    """Nom de fichier sûr, dérivé du seul identifiant numérique de l'analyse."""
    return f"mailguard-analysis-{int(identifiant)}.{extension}"


def construire_export_json(enregistrement: Enregistrement) -> dict:
    """Enveloppe JSON stable de l'analyse enregistrée.

    Les sections `analysis` et `briefing` reprennent exactement les objets
    validés au moment de l'import. Les types sont préservés : les nombres restent
    des nombres, les booléens des booléens, et une valeur absente reste `null`.
    """
    return {
        "schema_version": VERSION_EXPORT,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "analysis_identifier": enregistrement.identifiant,
        "stored_at": enregistrement.date_import.isoformat(),
        "stored_by_version": enregistrement.version_moteur,
        "uploaded_file_name": enregistrement.nom_fichier,
        "content_sha256": enregistrement.empreinte,
        "analysis": enregistrement.analyse.model_dump(mode="json"),
        "briefing": enregistrement.briefing.model_dump(mode="json"),
    }


def construire_export_csv_sources(enregistrement: Enregistrement) -> str:
    """CSV des sources, une ligne par adresse IP déclarée par le rapport.

    Les colonnes `total_messages` à `disposition_reject` sont numériques et le
    restent. `failure_rate_percent` est vide lorsque le taux n'est pas calculable,
    afin de ne jamais fabriquer un 0. `header_from_domains` regroupe les domaines
    `header_from` de la source, séparés par des espaces.
    """
    tampon = io.StringIO(newline="")
    redacteur = csv.writer(tampon, lineterminator="\n")
    redacteur.writerow(COLONNES_CSV_SOURCES)
    for source in enregistrement.analyse.sources:
        redacteur.writerow(
            [
                _cellule(source.adresse_ip),
                source.total_messages,
                source.messages_pass,
                source.messages_fail,
                "" if source.taux_fail.valeur is None else source.taux_fail.valeur,
                source.verdis_spf_evalues.reussite,
                source.verdis_spf_evalues.echec,
                source.verdis_dkim_evalues.reussite,
                source.verdis_dkim_evalues.echec,
                source.dispositions.none,
                source.dispositions.quarantine,
                source.dispositions.reject,
                _cellule(" ".join(source.domaines_en_tete)),
            ]
        )
    return tampon.getvalue()


def _cellule(valeur: str) -> str:
    """Neutralise une valeur texte pouvant être interprétée comme une formule.

    Le module `csv` gère déjà les séparateurs, les guillemets et les retours à la
    ligne ; seule l'injection de formule est traitée ici, de façon homogène.
    """
    texte = str(valeur)
    if not texte:
        return texte
    candidat = texte.lstrip(" \t\r\n")
    if candidat.startswith(PREFIXES_DANGEREUX):
        return MARQUEUR_FORMULE + texte
    return texte


__all__ = [
    "COLONNES_CSV_SOURCES",
    "VERSION_EXPORT",
    "construire_export_csv_sources",
    "construire_export_json",
    "nom_fichier_export",
]