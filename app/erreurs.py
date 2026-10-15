"""Correspondance entre erreurs métier et réponses HTTP.

Ce module est séparé de `app/__init__.py` pour éviter un cycle d'import : il ne
dépend que de `app.core.errors` et ne connaît ni Flask ni le stockage.
"""

from __future__ import annotations

from app.core.errors import (
    ArchiveError,
    ArchiveLimitError,
    ConfigurationErreur,
    MailGuardError,
    ReportParseError,
    ReportValidationError,
    StorageError,
    UnsafeArchiveError,
)

CODES_ERREUR: tuple[tuple[type[MailGuardError], int], ...] = (
    (ArchiveLimitError, 413),
    (UnsafeArchiveError, 400),
    (ArchiveError, 400),
    (ReportParseError, 400),
    (ReportValidationError, 400),
    (StorageError, 503),
    (ConfigurationErreur, 500),
)
"""Association entre famille d'erreur métier et code HTTP renvoyé au navigateur."""

MESSAGES_HTTP = {
    404: "This page does not exist.",
    405: "This action is not allowed on this address.",
    413: "The uploaded file is too large for this request.",
}
"""Messages français des erreurs HTTP courantes de Werkzeug."""

ENTETES_SECURITE = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'self'; script-src 'self'; "
        "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    ),
}
"""En-têtes appliqués à toutes les réponses."""


def code_http_pour(erreur: MailGuardError) -> int:
    """Code HTTP adapté à la famille d'erreur métier."""
    for famille, code in CODES_ERREUR:
        if isinstance(erreur, famille):
            return code
    return 500


def message_erreur_metier(erreur: MailGuardError) -> str:
    """Message affichable : le message métier, sans trace technique."""
    return str(erreur)


def message_http(erreur) -> str:
    """Message français pour une erreur HTTP de Werkzeug."""
    return MESSAGES_HTTP.get(erreur.code, "The request could not be processed.")


def entetes_securite(reponse):
    """Ajoute les en-têtes de sécurité à une réponse."""
    for nom, valeur in ENTETES_SECURITE.items():
        reponse.headers[nom] = valeur
    return reponse


__all__ = [
    "CODES_ERREUR",
    "ENTETES_SECURITE",
    "code_http_pour",
    "entetes_securite",
    "message_erreur_metier",
    "message_http",
]