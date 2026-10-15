"""Historique local SQLite des analyses DMARC.

Ce que la base conserve, et rien d'autre
----------------------------------------

Le principe est la minimisation : aucun XML, aucun contenu d'archive et aucune
donnée brute n'est écrit. Seuls l'empreinte du fichier reçu, son nom nettoyé, la
date d'import et les **résultats déterministes** déjà calculés par
`app/core/rules.py` et `app/core/briefing.py` sont enregistrés.

Trois notions restent séparées, conformément à `02_ARCHITECTURE.md` :

1. l'empreinte SHA-256 du contenu binaire reçu à l'entrée de l'import ;
2. l'identité de l'analyse enregistrée, qui est un entier local (`identifiant`) ;
3. les informations déclarées dans le rapport DMARC (`domaine`, `organisation`,
   `identifiant_rapport`), conservées telles quelles dans la charge utile.

L'identifiant de rapport DMARC n'est **pas** utilisé comme clé : un même
identifiant peut être émis par plusieurs organisations. La clé d'unicité est
l'empreinte du fichier, et la clé primaire est un entier local.

Schéma
------

Une seule table, `analyses`, créée par la migration 1 :

| Colonne          | Rôle                                                            |
| ---------------- | --------------------------------------------------------------- |
| `identifiant`    | clé primaire locale, `AUTOINCREMENT`                            |
| `empreinte`      | SHA-256 du fichier importé, contrainte `UNIQUE`                 |
| `nom_fichier`    | nom nettoyé fourni par l'importeur, traité comme donnée non fiable |
| `date_import`    | horodatage UTC de l'import (ISO 8601)                           |
| `version_schema` | version du schéma au moment de l'écriture                        |
| `version_moteur` | version du code de calcul ayant produit les résultats            |
| `domaine_publie` | domaine publié du premier rapport, `NULL` s'il est absent        |
| `nombre_rapports`| nombre de rapports de l'analyse                                 |
| `total_messages` | total de messages calculé par le moteur                          |
| `analyse_json`   | charge utile versionnée de `Analyse`                            |
| `briefing_json`  | charge utile versionnée de `Briefing`                           |

`domaine_publie`, `nombre_rapports` et `total_messages` sont des colonnes
dénormalisées, destinées à l'affichage de l'historique et au tri sans désérialiser
la charge utile. Elles ne remplacent jamais les résultats : la lecture renvoie
toujours les objets `Analyse` et `Briefing` revalidés, et toute incohérence entre
colonnes et charge utile est un défaut à corriger, pas une source de vérité
alternative.

Sérialisation
-------------

Les résultats sont enregistrés dans une enveloppe versionnée :

```json
{"version": 1, "analyse": {...}}
{"version": 1, "briefing": {...}}
```

Chaque colonne contient sa propre enveloppe versionnée, de sorte qu'aucune donnée
n'est dupliquée et qu'un format inconnu est refusé colonne par colonne.

La version est vérifiée à la lecture, puis les deux charges utiles sont
revalidées par Pydantic (`Analyse`, `Briefing`). Un taux dont la valeur est
`None` reste `None` : il n'est jamais converti en 0. Le texte du briefing n'est
jamais utilisé pour reconstruire une métrique.

Versionnement du schéma
-----------------------

`PRAGMA user_version` porte le numéro de schéma ; `MIGRATIONS` associe chaque
version à ses instructions SQL. `initialiser()` applique les migrations
manquantes dans l'ordre, chacune dans une transaction, et échoue explicitement si
la base est plus récente que le logiciel. Une future migration s'ajoute donc dans
`MIGRATIONS` sans modifier le code existant, et ne doit jamais effacer les
données historiques.

Empreinte et doublons
---------------------

L'empreinte est calculée sur les octets exacts reçus, avant toute décompression
ou normalisation : deux fichiers identiques donnent la même empreinte, deux
fichiers différents peuvent donner des empreintes différentes même si leur XML
est sémantiquement équivalent. Elle identifie donc un contenu binaire importé,
pas l'identité sémantique d'un rapport.

Un second import du même contenu ne crée pas de ligne supplémentaire : la
contrainte `UNIQUE` de SQLite fait autorité, y compris en cas d'appels
concurrents, et l'appelant reçoit un résultat typé indiquant l'identifiant de
l'analyse existante et `cree=False`. Une réanalyse volontaire n'est pas prévue à
ce stade : elle devra être une opération explicite et distincte.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app import __version__ as VERSION_MOTEUR
from app.core.archive import ImportResult
from app.core.briefing import Briefing
from app.core.errors import StorageError
from app.core.rules import Analyse

VERSION_SCHEMA = 1
"""Version du schéma gérée par ce code."""

VERSION_ANALYSE = 1
"""Format de la charge utile sérialisée dans `analyse_json` et `briefing_json`."""

LIMITE_LISTE_DEFAUT = 20
"""Nombre d'analyses renvoyées par défaut par `lister()`."""

LONGUEUR_NOM_MAX = 255
"""Longueur maximale du nom de fichier conservé, pour ne pas stocker un abus."""

MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        """
        CREATE TABLE IF NOT EXISTS analyses (
            identifiant     INTEGER PRIMARY KEY AUTOINCREMENT,
            empreinte       TEXT    NOT NULL UNIQUE,
            nom_fichier     TEXT    NOT NULL,
            date_import     TEXT    NOT NULL,
            version_schema  INTEGER NOT NULL,
            version_moteur  TEXT    NOT NULL,
            domaine_publie  TEXT,
            nombre_rapports INTEGER NOT NULL,
            total_messages  INTEGER NOT NULL,
            analyse_json    TEXT    NOT NULL,
            briefing_json   TEXT    NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_analyses_date_import
            ON analyses (date_import DESC, identifiant DESC)
        """,
    ),
}
"""Schéma versionné : version du schéma -> instructions SQL de création."""


@dataclass(frozen=True)
class ParametresStockage:
    """Paramètres du stockage, fournis explicitement par l'appelant.

    `chemin` ne dépend jamais du nom du fichier importé. La création du répertoire
    parent est optionnelle et explicite : par défaut elle est autorisée, car la
    configuration prévue (`data/mailguard.sqlite3`) vise un dossier créé pour
    l'application.
    """

    chemin: Path
    timeout_secondes: float = 5.0
    creer_repertoire: bool = True


class ModelStockage(BaseModel):
    """Base des objets renvoyés par la couche de stockage."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Enregistrement(ModelStockage):
    """Analyse enregistrée, relue depuis la base et revalidée."""

    identifiant: int
    empreinte: str
    nom_fichier: str
    date_import: datetime
    version_moteur: str
    domaine_publie: str | None
    analyse: Analyse
    briefing: Briefing
    cree: bool = False
    """Vrai si cette écriture a créé la ligne, faux si l'import était un doublon."""


class ResumeAnalyse(ModelStockage):
    """Ligne d'historique.

    Les compteurs pass/fail et la fenêtre de couverture sont relus dans la charge
    utile stockée, sans recalcul ni réexécution du moteur. `date_debut` et
    `date_fin` délimitent l'ensemble des rapports enregistrés dans cette analyse :
    pour une analyse à un seul rapport, ils correspondent exactement à sa période.
    """

    identifiant: int
    nom_fichier: str
    date_import: datetime
    domaine_publie: str | None
    nombre_rapports: int
    total_messages: int
    messages_pass: int
    messages_fail: int
    date_debut: datetime | None
    date_fin: datetime | None
    version_moteur: str


def calculer_empreinte(contenu: bytes) -> str:
    """Empreinte SHA-256 des octets exacts reçus, en hexadécimal minuscule."""
    return hashlib.sha256(contenu).hexdigest()


class StockageAnalyses:
    """Historique local des analyses DMARC.

    Chaque appel ouvre une connexion courte livedurée de l'appel puis la ferme :
    aucune connexion n'est conservée. Les écritures passent par une transaction
    implicite (`with`), donc validées à la sortie du bloc et annulées sur erreur.
    """

    def __init__(self, parametres: ParametresStockage) -> None:
        self._parametres = parametres

    @classmethod
    def depuis_chemin(
        cls,
        chemin: str | Path,
        timeout_secondes: float = 5.0,
        creer_repertoire: bool = True,
    ) -> StockageAnalyses:
        """Construit un stockage à partir d'un chemin de fichier de base."""
        return cls(
            ParametresStockage(
                chemin=Path(chemin),
                timeout_secondes=timeout_secondes,
                creer_repertoire=creer_repertoire,
            )
        )

    @property
    def chemin(self) -> Path:
        """Chemin du fichier SQLite utilisé."""
        return self._parametres.chemin

    # --- Initialisation -------------------------------------------------------

    def initialiser(self) -> int:
        """Crée ou met à niveau le schéma et renvoie la version du schéma.

        L'appel est répétable : les tables utilisent `IF NOT EXISTS` et aucune
        donnée existante n'est supprimée.
        """
        self._preparer_repertoire()
        with self._connexion() as connexion:
            version = self._lire_version(connexion)
            if version > VERSION_SCHEMA:
                raise StorageError(
                    f"The history database is at version {version}, while this "
                    f"software supports version {VERSION_SCHEMA}. Please update the software."
                )
            for cible in range(version + 1, VERSION_SCHEMA + 1):
                self._appliquer_migration(connexion, cible)
        return VERSION_SCHEMA

    def version_schema(self) -> int:
        """Version de schéma actuellement enregistrée dans la base."""
        with self._connexion() as connexion:
            return self._lire_version(connexion)

    def _lire_version(self, connexion: sqlite3.Connection) -> int:
        """Valeur de `PRAGMA user_version`."""
        ligne = connexion.execute("PRAGMA user_version").fetchone()
        return int(ligne[0]) if ligne else 0

    def _appliquer_migration(self, connexion: sqlite3.Connection, cible: int) -> None:
        """Applique une migration dans une transaction, puis versionne la base."""
        instructions = MIGRATIONS.get(cible)
        if instructions is None:
            raise StorageError(f"No migration is defined towards version {cible}.")
        try:
            with connexion:
                for instruction in instructions:
                    connexion.execute(instruction)
                connexion.execute(f"PRAGMA user_version = {int(cible)}")
        except sqlite3.Error as erreur:
            raise StorageError(
                f"Migration to version {cible} failed; no data was changed."
            ) from erreur

    # --- Écriture -------------------------------------------------------------

    def enregistrer(
        self,
        contenu: bytes,
        resultat: ImportResult,
        analyse: Analyse,
        briefing: Briefing,
    ) -> Enregistrement:
        """Enregistre une analyse et renvoie la ligne créée ou déjà présente.

        `contenu` doit être exactement les octets reçus à l'entrée de l'import :
        l'empreinte est calculée dessus, avant toute décompression. `resultat`
        fournit le nom de fichier déjà nettoyé par l'importeur.
        """
        empreinte = calculer_empreinte(contenu)
        charge = _serialiser(analyse, briefing)
        nom_fichier = _nettoyer_nom(resultat.file_name)
        domaine = analyse.metriques.domaines_publies[0] if analyse.metriques.domaines_publies else None
        horodatage = datetime.now(timezone.utc)

        try:
            with self._connexion(schema_requis=True) as connexion:
                identifiant = self._ecrire(
                    connexion,
                    empreinte=empreinte,
                    nom_fichier=nom_fichier,
                    horodatage=horodatage,
                    domaine=domaine,
                    analyse=analyse,
                    charge=charge,
                )
        except sqlite3.IntegrityError as erreur:
            return self._doublon(empreinte, erreur)
        except sqlite3.Error as erreur:
            raise StorageError("The analysis could not be saved.") from erreur

        return Enregistrement(
            identifiant=identifiant,
            empreinte=empreinte,
            nom_fichier=nom_fichier,
            date_import=horodatage,
            version_moteur=VERSION_MOTEUR,
            domaine_publie=domaine,
            analyse=analyse,
            briefing=briefing,
            cree=True,
        )

    def _ecrire(
        self,
        connexion: sqlite3.Connection,
        empreinte: str,
        nom_fichier: str,
        horodatage: datetime,
        domaine: str | None,
        analyse: Analyse,
        charge: dict[str, str],
    ) -> int:
        """Insère la ligne et renvoie l'identifiant attribué par SQLite.

        Toute erreur levée ici annule la transaction entière : aucune ligne
        partielle n'est conservée.
        """
        curseur = connexion.execute(
            """
            INSERT INTO analyses (
                empreinte, nom_fichier, date_import, version_schema, version_moteur,
                domaine_publie, nombre_rapports, total_messages, analyse_json, briefing_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                empreinte,
                nom_fichier,
                horodatage.isoformat(),
                VERSION_SCHEMA,
                VERSION_MOTEUR,
                domaine,
                analyse.metriques.nombre_rapports,
                analyse.metriques.total_messages,
                charge["analyse"],
                charge["briefing"],
            ),
        )
        return int(curseur.lastrowid)

    def _doublon(self, empreinte: str, erreur: sqlite3.IntegrityError) -> Enregistrement:
        """Traduit une violation d'unicité en doublon explicite, jamais en panne.

        La contrainte `UNIQUE` de SQLite reste l'arbitre : le `SELECT` ne sert
        qu'à identifier la ligne existante après le refus de l'écriture.
        """
        existant = self.rechercher_par_empreinte(empreinte)
        if existant is None:
            raise StorageError("The database refused the insert.") from erreur
        return existant.model_copy(update={"cree": False})

    def supprimer(self, identifiant: int) -> bool:
        """Supprime une analyse et renvoie `True` si une ligne a été retirée.

        L'interface web devra protéger cette action par CSRF (voir
        `06_UI_AND_REPORTING.md`) ; aucune route n'existe à ce stade.
        """
        with self._connexion(schema_requis=True) as connexion:
            curseur = connexion.execute(
                "DELETE FROM analyses WHERE identifiant = ?", (int(identifiant),)
            )
        return curseur.rowcount > 0

    # --- Lecture --------------------------------------------------------------

    def obtenir(self, identifiant: int) -> Enregistrement | None:
        """Relit une analyse par identifiant, ou `None` si elle n'existe pas."""
        with self._connexion(schema_requis=True) as connexion:
            ligne = connexion.execute(
                "SELECT * FROM analyses WHERE identifiant = ?", (int(identifiant),)
            ).fetchone()
        return None if ligne is None else _ligne_vers_enregistrement(ligne)

    def rechercher_par_empreinte(self, empreinte: str) -> Enregistrement | None:
        """Relit l'analyse correspondant à une empreinte, ou `None`."""
        with self._connexion(schema_requis=True) as connexion:
            ligne = connexion.execute(
                "SELECT * FROM analyses WHERE empreinte = ?", (str(empreinte),)
            ).fetchone()
        return None if ligne is None else _ligne_vers_enregistrement(ligne)

    def lister(self, limite: int = LIMITE_LISTE_DEFAUT) -> list[ResumeAnalyse]:
        """Analyses récentes, de la plus récente à la plus ancienne.

        Le tri est déterministe : `date_import` décroissante, puis identifiant
        décroissant. La limite est explicite et bornée.
        """
        if int(limite) <= 0:
            raise StorageError("The history limit must be greater than zero.")
        borne = min(int(limite), 1000)
        with self._connexion(schema_requis=True) as connexion:
            lignes = connexion.execute(
                """
                SELECT identifiant, nom_fichier, date_import, domaine_publie,
                       nombre_rapports, total_messages, version_moteur, analyse_json
                FROM analyses
                ORDER BY date_import DESC, identifiant DESC
                LIMIT ?
                """,
                (borne,),
            ).fetchall()
        return [_ligne_vers_resume(ligne) for ligne in lignes]

    def compter(self) -> int:
        """Nombre d'analyses enregistrées."""
        with self._connexion(schema_requis=True) as connexion:
            return int(connexion.execute("SELECT COUNT(*) FROM analyses").fetchone()[0])

    # --- Connexions -----------------------------------------------------------

    def _preparer_repertoire(self) -> None:
        """Vérifie, et au besoin crée, le répertoire parent du fichier de base."""
        parent = self._parametres.chemin.parent
        try:
            if parent.is_dir():
                return
            if parent.exists():
                raise StorageError(
                    f"The path « {parent} » exists but is not a directory."
                )
            if not self._parametres.creer_repertoire:
                raise StorageError(
                    f"The directory « {parent} » is missing and its creation is not allowed."
                )
            parent.mkdir(parents=True, exist_ok=True)
        except StorageError:
            raise
        except OSError as erreur:
            raise StorageError(
                f"Le dossier « {parent} » n'a pas pu être préparé pour la base locale."
            ) from erreur

    @contextmanager
    def _connexion(self, schema_requis: bool = False) -> Iterator[sqlite3.Connection]:
        """Connexion courte : ouverte pour l'appel, fermée à la sortie du bloc.

        `PRAGMA foreign_keys` est activé par précaution pour les futurs schémas ;
        le journal reste celui par défaut de SQLite, sans mode WAL, afin de ne pas
        multiplier les fichiers annexes de la base.
        """
        chemin = self._parametres.chemin
        if chemin.is_dir():
            raise StorageError(
                f"The path « {chemin} » is a directory, not a database file."
            )
        self._preparer_repertoire()
        try:
            connexion = sqlite3.connect(
                chemin, timeout=self._parametres.timeout_secondes
            )
        except sqlite3.Error as erreur:
            raise StorageError(
                f"The local database « {chemin} » could not be opened."
            ) from erreur
        try:
            connexion.row_factory = sqlite3.Row
            connexion.execute("PRAGMA foreign_keys = ON")
            if schema_requis:
                self._exiger_schema(connexion)
            yield connexion
            connexion.commit()
        except sqlite3.IntegrityError:
            connexion.rollback()
            raise
        except sqlite3.DatabaseError as erreur:
            connexion.rollback()
            raise StorageError(
                f"The file « {chemin} » is not a usable SQLite database."
            ) from erreur
        except Exception:
            connexion.rollback()
            raise
        finally:
            connexion.close()

    def _exiger_schema(self, connexion: sqlite3.Connection) -> None:
        """Message clair si la base n'a pas encore été initialisée."""
        tables = connexion.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'analyses'"
        ).fetchone()
        if tables is None:
            raise StorageError(
                "The history database is not initialized: call initialiser() at startup."
            )


# --- Sérialisation -----------------------------------------------------------


def _serialiser(analyse: Analyse, briefing: Briefing) -> dict[str, str]:
    """Deux enveloppes versionnées : une par colonne, sans donnée dupliquée."""
    return {
        "analyse": json.dumps(
            {"version": VERSION_ANALYSE, "analyse": analyse.model_dump(mode="json")},
            ensure_ascii=False,
        ),
        "briefing": json.dumps(
            {"version": VERSION_ANALYSE, "briefing": briefing.model_dump(mode="json")},
            ensure_ascii=False,
        ),
    }


def _deserialiser(ligne: sqlite3.Row) -> tuple[Analyse, Briefing]:
    """Relit et revalide les résultats, en refusant une version inconnue."""
    enveloppe = _lire_enveloppe(ligne["analyse_json"], "analyse")
    enveloppe_briefing = _lire_enveloppe(ligne["briefing_json"], "briefing")
    try:
        analyse = Analyse.model_validate(enveloppe["analyse"])
        briefing = Briefing.model_validate(enveloppe_briefing["briefing"])
    except (KeyError, TypeError, ValueError) as erreur:
        raise StorageError(
            "The stored results are incomplete or invalid; no value was filled in."
        ) from erreur
    return analyse, briefing


def _lire_enveloppe(valeur: str, nom: str) -> dict:
    """Charge une enveloppe JSON et vérifie sa version de format."""
    try:
        enveloppe = json.loads(valeur)
    except (TypeError, json.JSONDecodeError) as erreur:
        raise StorageError(
            f"The stored « {nom} » results cannot be read: the payload is damaged."
        ) from erreur
    if not isinstance(enveloppe, dict):
        raise StorageError(f"The stored « {nom} » payload has an unexpected format.")
    version = enveloppe.get("version")
    if version != VERSION_ANALYSE:
        raise StorageError(
            f"This analysis was stored with format {version}, which this software "
            f"cannot read (expected format: {VERSION_ANALYSE})."
        )
    return enveloppe


def _ligne_vers_enregistrement(ligne: sqlite3.Row) -> Enregistrement:
    """Construit un `Enregistrement` relu et revalidé."""
    analyse, briefing = _deserialiser(ligne)
    return Enregistrement(
        identifiant=int(ligne["identifiant"]),
        empreinte=str(ligne["empreinte"]),
        nom_fichier=str(ligne["nom_fichier"]),
        date_import=_lire_date(ligne["date_import"]),
        version_moteur=str(ligne["version_moteur"]),
        domaine_publie=ligne["domaine_publie"],
        analyse=analyse,
        briefing=briefing,
        cree=False,
    )


def _ligne_vers_resume(ligne: sqlite3.Row) -> ResumeAnalyse:
    """Construit un `ResumeAnalyse` depuis les colonnes et la charge utile stockée."""
    enveloppe = _lire_enveloppe(ligne["analyse_json"], "analyse")
    analyse = Analyse.model_validate(enveloppe["analyse"])
    debut, fin = _fenetre_couverture(analyse)
    return ResumeAnalyse(
        identifiant=int(ligne["identifiant"]),
        nom_fichier=str(ligne["nom_fichier"]),
        date_import=_lire_date(ligne["date_import"]),
        domaine_publie=ligne["domaine_publie"],
        nombre_rapports=int(ligne["nombre_rapports"]),
        total_messages=int(ligne["total_messages"]),
        messages_pass=analyse.metriques.messages_pass,
        messages_fail=analyse.metriques.messages_fail,
        date_debut=debut,
        date_fin=fin,
        version_moteur=str(ligne["version_moteur"]),
    )


def _fenetre_couverture(analyse: Analyse) -> tuple[datetime | None, datetime | None]:
    """Début le plus ancien et fin la plus récente parmi les rapports stockés."""
    if not analyse.rapports:
        return None, None
    return (
        min(rapport.date_debut for rapport in analyse.rapports),
        max(rapport.date_fin for rapport in analyse.rapports),
    )


def _lire_date(valeur: str) -> datetime:
    """Relit un horodatage ISO 8601 aware, en UTC."""
    try:
        moment = datetime.fromisoformat(str(valeur))
    except ValueError as erreur:
        raise StorageError("The stored import date cannot be read.") from erreur
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _nettoyer_nom(nom: str) -> str:
    """Nom de fichier conservé : déjà nettoyé par l'importeur, borné ici."""
    nettoye = "".join(caractere for caractere in str(nom) if ord(caractere) >= 32).strip()
    return (nettoye or "rapport_importe")[:LONGUEUR_NOM_MAX]


__all__ = [
    "Enregistrement",
    "LIMITE_LISTE_DEFAUT",
    "MIGRATIONS",
    "ParametresStockage",
    "ResumeAnalyse",
    "StockageAnalyses",
    "VERSION_ANALYSE",
    "VERSION_SCHEMA",
    "calculer_empreinte",
]