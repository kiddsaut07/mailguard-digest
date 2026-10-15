"""Exceptions métier de MailGuard Digest.

Raison de ce fichier séparé : le parseur, la lecture d'archives et le moteur de
règles doivent pouvoir lever et distinguer les mêmes erreurs sans s'importer
mutuellement. Les détails techniques restent dans la cause Python
(`__cause__`) ; le message, lui, est directement affichable par l'interface.

Aucun de ces messages ne doit contenir de secret ni de chemin système.
"""


class MailGuardError(Exception):
    """Erreur métier identifiable, message compréhensible par un utilisateur."""


class ReportParseError(MailGuardError):
    """Le document XML est illisible ou ne respecte pas la structure DMARC."""


class ReportValidationError(MailGuardError):
    """Le document est bien formé mais ses données ne sont pas valides."""


class ArchiveError(MailGuardError):
    """Le fichier televersé n'est pas une archive exploitable."""


class ArchiveLimitError(ArchiveError):
    """Une limite de taille, de nombre de membres ou de rapports est atteinte.

    Une limite atteinte n'est jamais contournée ni désactivée : l'import échoue.
    """


class UnsafeArchiveError(ArchiveError):
    """L'archive contient une entrée dangereuse ou trompeuse.

    Chemins absolus, remontée de répertoire, doublons, membres chiffrés,
    liens symboliques, entrées spéciales ou archives imbriquées.
    """


class StorageError(MailGuardError):
    """La base locale d'historique est indisponible ou refuse une opération.

    Chemin inaccessible, base incompatible, schéma de version inconnu ou
    enregistrement refusé. Le détail technique reste dans `__cause__`.
    """


class ConfigurationErreur(MailGuardError):
    """La configuration de l'application est absente ou invalide.

    Aucune limite n'est désactivée pour autant : une valeur illisible ou
    incohérente est refusée au démarrage plutôt que remplacée silencieusement.
    """


__all__ = [
    "ArchiveError",
    "ArchiveLimitError",
    "ConfigurationErreur",
    "MailGuardError",
    "ReportParseError",
    "ReportValidationError",
    "StorageError",
    "UnsafeArchiveError",
]