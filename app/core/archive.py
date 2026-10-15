"""Importation sécurisée d'un rapport DMARC : `.xml`, `.xml.gz` et `.zip`.

Contrat public
--------------

`import_reports(nom, contenu, limites)` reçoit un nom de fichier et son contenu
binaire, puis renvoie un `ImportResult` contenant les objets `DmarcReport`
réellement produits par `app.core.parser.parse_dmarc_report()`.

Garanties :

- tout se passe en mémoire, aucun fichier temporaire, aucun `extractall()`, aucun
  chemin d'archive n'est écrit sur le disque ;
- la taille téléversée, la taille décompressée cumulée, le nombre de membres et
  le nombre de rapports importés sont contrôlés, **avant et pendant** la lecture,
  sans jamais faire confiance aux seules métadonnées déclarées par l'archive ;
- une limite atteinte interrompt l'import : elle n'est jamais désactivée ;
- les rapports sont renvoyés dans un ordre déterministe : ordre alphabétique des
  noms de membres pour une archive, ordre du document pour un fichier simple ;
- un seul membre en échec fait échouer l'import entier : aucune importation
  partielle n'est présentée comme un succès.

Politique des entrées ZIP, explicite et testée :

| Entrée                                             | Traitement                          |
| -------------------------------------------------- | ----------------------------------- |
| Répertoire (`nom/`)                                | validé puis ignoré                  |
| Fichier `.xml`                                     | lu et analysé comme rapport DMARC   |
| Archive imbriquée (`.zip`, `.gz`, `.tar`, ...)     | refus : `UnsafeArchiveError`        |
| Autre fichier ordinaire (`.txt`, `.DS_Store`, ...) | ignoré et listé dans `ignored_entries` |

Aucun fichier ordinaire non pris en charge n'est jamais interprété comme un
rapport DMARC, et aucun n'est silentlye ignoré : il est retourné dans
`ignored_entries` pour affichage.

Exceptions : `ArchiveError`, `ArchiveLimitError`, `UnsafeArchiveError` (voir
`app.core/errors.py`) ainsi que `ReportParseError` et `ReportValidationError`
relayées du parseur avec le nom du membre fautif en préfixe.
"""

from __future__ import annotations

import codecs
import gzip
import io
import re
import stat
import zipfile
import zlib
from dataclasses import dataclass, field

from app.core.errors import (
    ArchiveError,
    ArchiveLimitError,
    MailGuardError,
    UnsafeArchiveError,
)
from app.core.models import DmarcReport
from app.core.parser import parse_dmarc_report

EXTENSIONS_RAPPORT = (".xml", ".xml.gz")
"""Extensions acceptées pour un rapport DMARC unique."""

EXTENSIONS_ARCHIVE = (".zip",)
"""Extensions acceptées pour une archive contenant plusieurs rapports."""

EXTENSIONS_ARCHIVES_NIMBUEES = (
    ".zip",
    ".gz",
    ".xml.gz",
    ".tar",
    ".tgz",
    ".tbz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
)
"""Extensions considérées comme archive : un membre portant l'une d'elles est refusé."""

TAILLE_BLOC = 64 * 1024
"""Taille des blocs de lecture : la mémoire reste bornée pendant la décompression."""

TAILLE_APERCU = 4096
"""Octets inspectés pour vérifier qu'un contenu est bien du XML."""

LONGUEUR_NOM_MAX = 200
"""Longueur maximale du nom de fichier affiché, après nettoyage."""

MOTIF_UNITE_WINDOWS = re.compile(r"^[A-Za-z]:")
"""Détecte une racine de lecteur Windows, par exemple `C:` suivi d'un séparateur."""

BIT_CHIFFREMENT = 0x1
"""Indicateur ZIP « membre chiffré », position 0 de l'indicateur général."""

TYPE_REPERTOIRE = 0o170000
"""Masque `S_IFMT` d'un mode de fichier UNIX stocké dans l'attribut externe."""


@dataclass(frozen=True)
class ImportLimits:
    """Limites de sécurité, configurables par l'appelant.

    Les valeurs par défaut reprennent celles de `03_SECURITY_PRIVACY.md` et de
    `.env.example`. `max_upload_bytes` porte sur le fichier téléversé (compressé),
    `max_decompressed_bytes` sur le volume total réellement décompressé.
    """

    max_upload_bytes: int = 10 * 1024 * 1024
    max_decompressed_bytes: int = 50 * 1024 * 1024
    max_archive_members: int = 100
    max_reports: int = 20


LIMITES_PAR_DEFAUT = ImportLimits()
"""Limites utilisées si l'appelant n'en fournit pas."""


@dataclass(frozen=True)
class ImportResult:
    """Résultat d'un import réussi.

    `reports` contient au moins un rapport DMARC validé. `ignored_entries`
    liste les entrées ZIP ignorées après validation, jamais des rapports.
    """

    file_name: str
    reports: list[DmarcReport]
    ignored_entries: list[str] = field(default_factory=list)

    @property
    def total_messages(self) -> int:
        """Somme des messages comptés par les rapports importés."""
        return sum(rapport.total_messages for rapport in self.reports)


def import_reports(
    nom: str,
    contenu: bytes,
    limites: ImportLimits = LIMITES_PAR_DEFAUT,
) -> ImportResult:
    """Importe un rapport DMARC depuis un fichier XML, GZIP ou ZIP.

    Lève `ArchiveError` si le format, l'archive ou son contenu sont inexploitables,
    `ArchiveLimitError` si une limite est atteinte, et les erreurs du parseur
    (`ReportParseError`, `ReportValidationError`) si un rapport est invalide.
    """
    nom_affiche = _nom_affiche(nom)
    extension = _extension(nom_affiche)

    if extension not in EXTENSIONS_RAPPORT + EXTENSIONS_ARCHIVE:
        raise ArchiveError(
            f"« {nom_affiche} » : unsupported file format. Accepted formats: "
            + ", ".join(EXTENSIONS_RAPPORT + EXTENSIONS_ARCHIVE)
            + "."
        )
    _verifier_taille_televersee(nom_affiche, contenu, limites)

    if extension == ".xml":
        return _importer_xml(nom_affiche, contenu, limites)
    if extension == ".xml.gz":
        return _importer_xml_gz(nom_affiche, contenu, limites)
    return _importer_zip(nom_affiche, contenu, limites)


# --- Contrôles communs -------------------------------------------------------


def _nom_affiche(nom: str) -> str:
    """Nom de fichier nettoyé, sans répertoire ni caractère de contrôle.

    Ce nom sert uniquement à l'affichage : il ne sert jamais à ouvrir un fichier
    et n'est jamais utilisé pour construire un chemin sur le disque.
    """
    brut = str(nom).replace("\\", "/").split("/")[-1]
    nettoyé = "".join(caractere for caractere in brut if ord(caractere) >= 32)
    nettoyé = nettoyé.strip()
    if not nettoyé:
        return "rapport_importe"
    return nettoyé[:LONGUEUR_NOM_MAX]


def _extension(nom: str) -> str:
    """Extension reconnue du fichier, les suffixes composés étant privilégiés."""
    minuscule = nom.lower()
    for extension in sorted(EXTENSIONS_RAPPORT + EXTENSIONS_ARCHIVE, key=len, reverse=True):
        if minuscule.endswith(extension):
            return extension
    return ""


def _verifier_taille_televersee(nom: str, contenu: bytes, limites: ImportLimits) -> None:
    """Refuse un fichier absent, du mauvais type ou trop volumineux."""
    if not isinstance(contenu, (bytes, bytearray)):
        raise ArchiveError(f"« {nom} » : unreadable content, raw bytes expected.")
    if len(contenu) == 0:
        raise ArchiveError(f"« {nom} » : the file is empty.")
    if len(contenu) > limites.max_upload_bytes:
        raise ArchiveLimitError(
            f"« {nom} » : the uploaded file exceeds the "
            f"{limites.max_upload_bytes} byte limit."
        )


class _Budget:
    """Compteur cumulé des octets réellement décompressés.

    Le budget est partagé par tous les membres d'une archive : un membre ne peut
    pas contourner la limite grâce aux octets consommés par les autres.
    """

    def __init__(self, limite: int) -> None:
        self._limite = limite
        self._consommes = 0

    def consommer(self, taille: int, origine: str) -> None:
        """Ajoute des octets décompressés et interrompt dès que la limite dépasse."""
        if self._consommes + taille > self._limite:
            raise ArchiveLimitError(
                f"Import stopped: decompressed data from « {origine} » "
                f"exceeds the {self._limite} byte limit."
            )
        self._consommes += taille

    @property
    def consommes(self) -> int:
        """Octets décompressés consommés jusqu'ici."""
        return self._consommes


# --- Fichiers XML et GZIP ----------------------------------------------------


def _importer_xml(nom: str, contenu: bytes, limites: ImportLimits) -> ImportResult:
    """Rapport XML unique, transmis tel quel au parseur sécurisé."""
    _Budget(limites.max_decompressed_bytes).consommer(len(contenu), nom)
    return ImportResult(nom, [_analyser(contenu, nom)])


def _importer_xml_gz(nom: str, contenu: bytes, limites: ImportLimits) -> ImportResult:
    """Rapport XML compressé en GZIP, décompressé en mémoire par blocs bornés."""
    rapport_xml = _decompresser_gz(nom, contenu, limites)
    return ImportResult(nom, [_analyser(rapport_xml, nom)])


def _decompresser_gz(nom: str, contenu: bytes, limites: ImportLimits) -> bytes:
    """Décompresse un flux GZIP en s'arrêtant dès que la limite est dépassée."""
    budget = _Budget(limites.max_decompressed_bytes)
    morceaux: list[bytes] = []
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(contenu)) as flux:
            while True:
                bloc = flux.read(TAILLE_BLOC)
                if not bloc:
                    break
                budget.consommer(len(bloc), nom)
                morceaux.append(bloc)
    except ArchiveLimitError:
        raise
    except (OSError, EOFError, zlib.error) as erreur:
        raise ArchiveError(
            f"« {nom} » : the GZIP file is corrupted or truncated."
        ) from erreur
    return b"".join(morceaux)


# --- Archives ZIP ------------------------------------------------------------


def _importer_zip(nom: str, contenu: bytes, limites: ImportLimits) -> ImportResult:
    """Archive ZIP lue entièrement en mémoire, membre par membre."""
    budget = _Budget(limites.max_decompressed_bytes)
    try:
        archive = zipfile.ZipFile(io.BytesIO(contenu))
    except (zipfile.BadZipFile, OSError, EOFError) as erreur:
        raise ArchiveError(
            f"« {nom} » : the file is not a valid ZIP archive, or it is truncated."
        ) from erreur

    with archive:
        entrees = archive.infolist()
        if not entrees:
            raise ArchiveError(f"« {nom} » : the ZIP archive is empty.")
        _verifier_volume(nom, entrees, limites)
        _verifier_noms(nom, entrees)
        _verifier_types(nom, entrees)
        _verifier_nombre_rapports(nom, entrees, limites)

        rapports: list[DmarcReport] = []
        ignores: list[str] = []
        for entree in sorted(entrees, key=lambda element: element.filename):
            if entree.is_dir():
                ignores.append(entree.filename)
                continue
            _refuser_archive_nimbee(nom, entree)
            if not _est_rapport(entree):
                ignores.append(entree.filename)
                continue
            rapports.append(_analyser(_lire_membre(archive, entree, budget), entree.filename))

    if not rapports:
        raise ArchiveError(f"« {nom} » : the archive contains no usable DMARC report.")
    return ImportResult(nom, rapports, ignores)


def _verifier_volume(nom: str, entrees: list[zipfile.ZipInfo], limites: ImportLimits) -> None:
    """Contrôle le nombre de membres et le volume annoncé, avant toute lecture.

    Ce contrôle est un refus rapide : il ne remplace pas le comptage réel des
    octets décompressés effectué pendant la lecture.
    """
    if len(entrees) > limites.max_archive_members:
        raise ArchiveLimitError(
            f"« {nom} » : the archive contains {len(entrees)} entries, the limit "
            f"is {limites.max_archive_members}."
        )
    volume_annonce = sum(entree.file_size for entree in entrees if not entree.is_dir())
    if volume_annonce > limites.max_decompressed_bytes:
        raise ArchiveLimitError(
            f"« {nom} » : the declared archive volume exceeds the "
            f"{limites.max_decompressed_bytes} byte limit for decompressed data."
        )


def _verifier_noms(nom: str, entrees: list[zipfile.ZipInfo]) -> None:
    """Valide chaque nom de membre et refuse les doublons après normalisation."""
    vus: set[str] = set()
    for entree in entrees:
        _verifier_nom_membre(nom, entree.filename)
        cle = entree.filename.replace("\\", "/").lower()
        if cle in vus:
            raise UnsafeArchiveError(
                f"« {nom} » : entry « {entree.filename} » appears twice in the archive."
            )
        vus.add(cle)


def _verifier_nom_membre(nom: str, nom_membre: str) -> None:
    """Refuse les noms de membres trompeurs, même si aucune extraction n'a lieu.

    Aucun chemin n'est utilisé pour écrire sur le disque : ces refus garantissent
    qu'un rapport importé ne provient pas d'un nom maquillé, et évitent de
    conserver un chemin dangereux dans l'historique.
    """
    origine = f"« {nom} »"
    if "\x00" in nom_membre:
        raise UnsafeArchiveError(f"{origine} : the entry name contains a NUL character.")
    if nom_membre != nom_membre.strip():
        raise UnsafeArchiveError(
            f"{origine} : the entry name « {nom_membre} » is ambiguous (leading or trailing spaces)."
        )
    if any(ord(caractere) < 32 for caractere in nom_membre):
        raise UnsafeArchiveError(
            f"{origine} : the entry name contains a control character."
        )
    if nom_membre.startswith("/") or nom_membre.startswith("\\"):
        raise UnsafeArchiveError(
            f"{origine} : entry « {nom_membre} » uses an absolute path."
        )
    if MOTIF_UNITE_WINDOWS.match(nom_membre):
        raise UnsafeArchiveError(
            f"{origine} : entry « {nom_membre} » uses an absolute Windows path."
        )
    segments = nom_membre.replace("\\", "/").split("/")
    if ".." in segments:
        raise UnsafeArchiveError(
            f"{origine} : entry « {nom_membre} » escapes the archive root."
        )
    if any(segment == "" for segment in segments[:-1]):
        raise UnsafeArchiveError(
            f"{origine} : the entry name « {nom_membre} » contains an ambiguous path."
        )


def _verifier_types(nom: str, entrees: list[zipfile.ZipInfo]) -> None:
    """Refuse les membres chiffrés, liens symboliques et entrées spéciales."""
    for entree in entrees:
        if entree.flag_bits & BIT_CHIFFREMENT:
            raise UnsafeArchiveError(
                f"« {nom} » : entry « {entree.filename} » is encrypted, which is refused."
            )
        mode = entree.external_attr >> 16
        if mode & TYPE_REPERTOIRE == 0:
            continue
        if stat.S_ISLNK(mode):
            raise UnsafeArchiveError(
                f"« {nom} » : entry « {entree.filename} » is a symbolic link."
            )
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise UnsafeArchiveError(
                f"« {nom} » : entry « {entree.filename} » is not a regular file."
            )


def _verifier_nombre_rapports(
    nom: str, entrees: list[zipfile.ZipInfo], limites: ImportLimits
) -> None:
    """Refuse une archive annoncant plus de rapports que la limite autorisée."""
    candidats = [entree for entree in entrees if _est_rapport(entree)]
    if len(candidats) > limites.max_reports:
        raise ArchiveLimitError(
            f"« {nom} » : the archive contains {len(candidats)} XML reports, the limit "
            f"is {limites.max_reports} per import."
        )


def _refuser_archive_nimbee(nom: str, entree: zipfile.ZipInfo) -> None:
    """Refuse tout membre qui serait lui-même une archive."""
    if _est_archive(entree):
        raise UnsafeArchiveError(
            f"« {nom} » : nested archive refused, entry « {entree.filename} »."
        )


def _est_archive(entree: zipfile.ZipInfo) -> bool:
    """Vrai si le membre porte une extension d'archive."""
    minuscule = entree.filename.lower()
    return any(minuscule.endswith(extension) for extension in EXTENSIONS_ARCHIVES_NIMBUEES)


def _est_rapport(entree: zipfile.ZipInfo) -> bool:
    """Vrai si le membre est un fichier XML ordinaire candidat à un rapport DMARC."""
    return not entree.is_dir() and entree.filename.lower().endswith(".xml")


def _lire_membre(
    archive: zipfile.ZipFile, entree: zipfile.ZipInfo, budget: _Budget
) -> bytes:
    """Lit un membre par blocs, en comptant réellement les octets décompressés."""
    morceaux: list[bytes] = []
    try:
        with archive.open(entree) as flux:
            while True:
                bloc = flux.read(TAILLE_BLOC)
                if not bloc:
                    break
                budget.consommer(len(bloc), entree.filename)
                morceaux.append(bloc)
    except (zipfile.BadZipFile, OSError, EOFError, zlib.error) as erreur:
        raise ArchiveError(
            f"Entry « {entree.filename} » : corrupted or unreadable archive."
        ) from erreur
    return b"".join(morceaux)


# --- Analyse des rapports ----------------------------------------------------


def _analyser(contenu: bytes, origine: str) -> DmarcReport:
    """Vérifie le contenu puis délègue au parseur, sans jamais le dupliquer."""
    _exiger_contenu_xml(contenu, origine)
    try:
        return parse_dmarc_report(contenu)
    except MailGuardError as erreur:
        raise type(erreur)(f"Entry « {origine} »: {erreur}") from erreur


def _exiger_contenu_xml(contenu: bytes, origine: str) -> None:
    """Refuse un contenu qui n'est pas du XML malgré une extension favorable.

    Un fichier renommé `.xml`, `.gz` ou stocké dans une archive n'est jamais
    interprété comme un rapport : seul le parseur décide ensuite de sa validité.
    """
    apercu = contenu[:TAILLE_APERCU].lstrip()
    if apercu.startswith(codecs.BOM_UTF8):
        apercu = apercu[3:].lstrip()
    if not apercu.startswith(b"<"):
        raise ArchiveError(
            f"« {origine} » : the content is not XML although the file format announces it."
        )


__all__ = [
    "EXTENSIONS_ARCHIVE",
    "EXTENSIONS_RAPPORT",
    "ImportLimits",
    "ImportResult",
    "LIMITES_PAR_DEFAUT",
    "import_reports",
]