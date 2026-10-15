"""MailGuard Digest — application locale d'analyse des rapports DMARC agrégés.

Ce module expose la version du logiciel et la fabrique `create_app()`. Les
imports de Flask et des couches métier sont faits à l'intérieur des fonctions :
`app.storage` utilise `__version__`, et un import au niveau du module créerait
un cycle d'import.

`create_app()` ne produit aucun effet de bord : ni base créée, ni serveur lancé.
Le point d'entrée `app/main.py` charge la configuration, initialise la base puis
lance le serveur.
"""

from __future__ import annotations

__all__ = ["__version__", "create_app", "stockage_de"]

__version__ = "0.1.0"

TITRE_ERREUR_INCONNUE = "An unexpected error occurred."
"""Message générique : aucun détail technique n'est renvoyé au navigateur."""


def create_app(configuration=None):
    """Crée l'application Flask configurée, sans toucher à la base.

    `configuration` permet d'injecter une configuration de test ; par défaut la
    configuration est lue dans l'environnement et dans le fichier `.env`.
    """
    from flask import Flask, render_template
    from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

    from app.api.routes import routes
    from app.config import charger_configuration
    from app.core.errors import MailGuardError
    from app.erreurs import (
        code_http_pour,
        entetes_securite,
        message_erreur_metier,
        message_http,
    )
    from app.securite import generer_jeton
    from app.storage.database import StockageAnalyses

    configuration = configuration or charger_configuration()
    application = Flask(__name__)
    application.config.update(
        SECRET_KEY=configuration.cle_secrete,
        MAX_CONTENT_LENGTH=configuration.max_content_length,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # L'application reste sur une interface locale : le cookie n'a pas à être
        # marqué `Secure`. Une exposition en HTTPS imposerait de passer à True.
        SESSION_COOKIE_SECURE=False,
        MAILGUARD_CONFIG=configuration,
    )
    application.register_blueprint(routes)
    application.extensions["stockage"] = StockageAnalyses.depuis_chemin(
        configuration.chemin_base
    )
    _enregistrer_contexte(application, generer_jeton)
    _enregistrer_gestionnaires(
        application,
        render_template=render_template,
        exception_metier=MailGuardError,
        trop_gros=RequestEntityTooLarge,
        exception_http=HTTPException,
    )
    application.after_request(entetes_securite)
    return application


def stockage_de(application):
    """Instance de stockage attachée à l'application."""
    return application.extensions["stockage"]


def _enregistrer_contexte(application, generer_jeton) -> None:
    """Valeurs disponibles dans tous les gabarits."""

    @application.context_processor
    def _contexte() -> dict[str, str]:
        return {"jeton_csrf": generer_jeton(), "version_application": __version__}


def _enregistrer_gestionnaires(application, **composants) -> None:
    """Gestionnaires d'erreur : message français, code adapté, journalisation interne."""
    render_template = composants["render_template"]
    exception_metier = composants["exception_metier"]
    trop_gros = composants["trop_gros"]
    exception_http = composants["exception_http"]

    from app.erreurs import code_http_pour, message_erreur_metier, message_http

    @application.errorhandler(exception_metier)
    def _erreur_metier(erreur):
        code = code_http_pour(erreur)
        application.logger.warning("Business error: %s", erreur)
        return (
            render_template("erreur.html", message=message_erreur_metier(erreur), code=code),
            code,
        )

    @application.errorhandler(trop_gros)
    def _requete_trop_grosse(erreur):
        application.logger.info("Request refused: body larger than the HTTP limit.")
        return (
            render_template(
                "erreur.html",
                message=(
                    "The uploaded file exceeds the maximum size accepted by the "
                    "application. See the limits listed on the upload page."
                ),
                code=413,
            ),
            413,
        )

    @application.errorhandler(exception_http)
    def _erreur_http(erreur):
        code = erreur.code or 500
        return render_template("erreur.html", message=message_http(erreur), code=code), code

    @application.errorhandler(Exception)
    def _erreur_inattendue(erreur):
        application.logger.exception("Erreur inattendue : %s", type(erreur).__name__)
        return render_template("erreur.html", message=TITRE_ERREUR_INCONNUE, code=500), 500