"""Point d'entrée HTTP de MailGuard Digest.

Lancement :

```bash
.venv/bin/python -m app.main
```

Options facultatives : `--host`, `--port`, `--debug` (réservé au développement
local). Le module n'exécute rien à l'import : `tests/` peut charger `app.main`
sans démarrer de serveur ni créer de base.
"""

from __future__ import annotations

import argparse
from dataclasses import replace

from flask import Flask

from app.config import Configuration, charger_configuration, valider_configuration


def creer_application(configuration: Configuration | None = None) -> Flask:
    """Charge la configuration puis construit l'application Flask."""
    from app import create_app

    return create_app(configuration)


def initialiser_stockage(application: Flask) -> int:
    """Crée ou met à niveau la base configurée, sans jamais l'effacer."""
    stockage = application.extensions["stockage"]
    return stockage.initialiser()


def analyser_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Arguments de ligne de commande, tous facultatifs."""
    analyseur = argparse.ArgumentParser(
        prog="python -m app.main",
        description="Local analysis of aggregate DMARC reports.",
    )
    analyseur.add_argument("--host", help="Listening address (default: MAILGUARD_HOST).")
    analyseur.add_argument("--port", type=int, help="Listening port (default: MAILGUARD_PORT).")
    analyseur.add_argument(
        "--debug",
        action="store_true",
        help="Enable the Flask debugger. Development machine only.",
    )
    return analyseur.parse_args(argv)


def configuration_avec_arguments(
    configuration: Configuration, arguments: argparse.Namespace
) -> Configuration:
    """Applique les surcharges de ligne de commande à la configuration validée."""
    if not arguments.host and not arguments.port and not arguments.debug:
        return configuration
    surcharges = {"debug": True} if arguments.debug else {}
    if arguments.host:
        surcharges["hote"] = arguments.host
    if arguments.port:
        surcharges["port"] = arguments.port
    return valider_configuration(replace(configuration, **surcharges))


def main(argv: list[str] | None = None) -> int:
    """Lance l'application locale."""
    configuration = configuration_avec_arguments(charger_configuration(), analyser_arguments(argv))
    application = creer_application(configuration)
    version = initialiser_stockage(application)
    application.logger.info(
        "History database initialized (schema version %s) at %s",
        version,
        application.extensions["stockage"].chemin,
    )
    application.run(
        host=configuration.hote,
        port=configuration.port,
        debug=configuration.debug,
        use_reloader=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())