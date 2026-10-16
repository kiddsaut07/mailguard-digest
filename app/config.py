"""Configuration centrale de l'application, lue dans l'environnement.

Les noms de variables sont ceux de `.env.example`. Chaque valeur numérique est
convertie et validée explicitement : une variable absente reçoit la valeur
documentée, une variable illisible ou incohérente provoque une erreur de
configuration au démarrage. Aucune limite n'est jamais désactivée.

Valeurs par défaut, alignées sur `03_SECURITY_PRIVACY.md` :

| Variable                              | Défaut      |
| -------------------------------------- | ----------- |
| `MAILGUARD_MAX_COMPRESSED_BYTES`       | 10 MiB      |
| `MAILGUARD_MAX_DECOMPRESSED_BYTES`     | 50 MiB      |
| `MAILGUARD_MAX_ARCHIVE_MEMBERS`        | 100         |
| `MAILGUARD_MAX_REPORTS_PER_IMPORT`     | 20          |
| `MAILGUARD_MAX_RECORDS_PER_REPORT`    | 10 000      |
| `MAILGUARD_MAX_CONTENT_LENGTH`         | 12 MiB      |
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app.core.archive import ImportLimits, MAX_RECORDS_PAR_RAPPORT
from app.core.errors import ConfigurationErreur

TAILLE_CLE_SECRETE_MINIMALE = 32
"""Longueur minimale d'une clé secrète acceptée hors tests."""

LONGUEUR_KB = 1024
"""Unité utilisée pour rendre les tailles lisibles dans les messages."""

ADRESSES_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})
"""Hôtes Ollama acceptés sans activation advanced."""

VRAIS = {"1", "true", "oui", "yes", "on"}
FAUX = {"0", "false", "non", "no", "off", ""}
"""Valeurs acceptées pour un indicateur booléen d'environnement."""


@dataclass(frozen=True)
class Configuration:
    """Configuration effective de l'application, validée à la construction."""

    cle_secrete: str
    hote: str = "127.0.0.1"
    port: int = 5000
    chemin_base: Path = Path("data/mailguard.sqlite3")
    max_upload_bytes: int = 10 * 1024 * 1024
    max_decompressed_bytes: int = 50 * 1024 * 1024
    max_archive_members: int = 100
    max_reports_per_import: int = 20
    max_records_per_report: int = MAX_RECORDS_PAR_RAPPORT
    max_content_length: int = 12 * 1024 * 1024
    debug: bool = False
    ai_active: bool = False
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    ollama_timeout_secondes: float = 10.0
    ollama_max_input_chars: int = 4000
    ollama_max_output_tokens: int = 300
    ollama_allow_remote: bool = False
    """Par défaut, seule une adresse de boucle locale est autorisée."""

    @property
    def limites_import(self) -> ImportLimits:
        """Limites transmises à l'importateur sécurisé."""
        return ImportLimits(
            max_upload_bytes=self.max_upload_bytes,
            max_decompressed_bytes=self.max_decompressed_bytes,
            max_archive_members=self.max_archive_members,
            max_reports=self.max_reports_per_import,
            max_records_per_report=self.max_records_per_report,
        )

    @property
    def limites_affichees(self) -> dict[str, str]:
        """Limites lisibles, affichées sur la page d'import."""
        return {
            "Uploaded file": _poids(self.max_upload_bytes),
            "Decompressed data": _poids(self.max_decompressed_bytes),
            "Entries per archive": str(self.max_archive_members),
            "Reports per import": str(self.max_reports_per_import),
            "Records per report": str(self.max_records_per_report),
            "HTTP request": _poids(self.max_content_length),
        }

    @classmethod
    def pour_tests(cls, chemin_base: str | Path) -> Configuration:
        """Configuration isolée pour les tests : secret jetable, base temporaire.

        La clé est générée à la volée et n'est jamais écrite dans le dépôt.
        """
        return cls(
            cle_secrete=secrets.token_hex(32),
            chemin_base=Path(chemin_base),
            max_upload_bytes=64 * LONGUEUR_KB,
            max_decompressed_bytes=256 * LONGUEUR_KB,
            max_archive_members=5,
            max_reports_per_import=2,
            max_records_per_report=50,
            max_content_length=96 * LONGUEUR_KB,
        )


def charger_configuration(
    environ: Mapping[str, str] | None = None,
    charger_fichier_env: bool = True,
) -> Configuration:
    """Construit la configuration depuis l'environnement, fichier `.env` compris.

    `environ` permet de tester une configuration sans dépendre de
    l'environnement du poste. `charger_fichier_env` vaut `False` dans les tests.
    """
    if charger_fichier_env:
        _charger_fichier_env()
    source = os.environ if environ is None else environ
    configuration = Configuration(
        cle_secrete=_lire_cle_secrete(source),
        hote=_lire_texte(source, "MAILGUARD_HOST", "127.0.0.1"),
        port=_lire_entier(source, "MAILGUARD_PORT", 5000, minimum=1, maximum=65535),
        chemin_base=Path(_lire_texte(source, "MAILGUARD_DATABASE_PATH", "data/mailguard.sqlite3")),
        max_upload_bytes=_lire_entier(
            source, "MAILGUARD_MAX_COMPRESSED_BYTES", 10 * 1024 * 1024, minimum=1
        ),
        max_decompressed_bytes=_lire_entier(
            source, "MAILGUARD_MAX_DECOMPRESSED_BYTES", 50 * 1024 * 1024, minimum=1
        ),
        max_archive_members=_lire_entier(
            source, "MAILGUARD_MAX_ARCHIVE_MEMBERS", 100, minimum=1
        ),
        max_reports_per_import=_lire_entier(
            source, "MAILGUARD_MAX_REPORTS_PER_IMPORT", 20, minimum=1
        ),
        max_records_per_report=_lire_entier(
            source,
            "MAILGUARD_MAX_RECORDS_PER_REPORT",
            MAX_RECORDS_PAR_RAPPORT,
            minimum=1,
        ),
        max_content_length=_lire_entier(
            source, "MAILGUARD_MAX_CONTENT_LENGTH", 12 * 1024 * 1024, minimum=1
        ),
        debug=_lire_booleen(source, "FLASK_DEBUG", False),
        ai_active=_lire_booleen(source, "MAILGUARD_AI_ENABLED", False),
        ollama_url=_lire_texte(source, "MAILGUARD_OLLAMA_URL", "http://127.0.0.1:11434"),
        ollama_model=_lire_texte(source, "MAILGUARD_OLLAMA_MODEL", "").strip(),
        ollama_timeout_secondes=_lire_nombre(
            source, "MAILGUARD_OLLAMA_TIMEOUT_SECONDS", 10.0, minimum=0.5, maximum=120.0
        ),
        ollama_max_input_chars=_lire_entier(
            source, "MAILGUARD_OLLAMA_MAX_INPUT_CHARS", 4000, minimum=200, maximum=20000
        ),
        ollama_max_output_tokens=_lire_entier(
            source, "MAILGUARD_OLLAMA_MAX_OUTPUT_TOKENS", 300, minimum=32, maximum=2000
        ),
        ollama_allow_remote=_lire_booleen(source, "MAILGUARD_OLLAMA_ALLOW_REMOTE", False),
    )
    return valider_configuration(configuration)


def valider_configuration(configuration: Configuration) -> Configuration:
    """Vérifie la cohérence globale, en particulier les limites HTTP et d'import."""
    if configuration.max_content_length < configuration.max_upload_bytes:
        raise ConfigurationErreur(
            "MAILGUARD_MAX_CONTENT_LENGTH must be greater than or equal to "
            "MAILGUARD_MAX_COMPRESSED_BYTES: otherwise Flask would refuse a file "
            "the importer accepts."
        )
    if configuration.max_decompressed_bytes < configuration.max_upload_bytes:
        raise ConfigurationErreur(
            "MAILGUARD_MAX_DECOMPRESSED_BYTES must be greater than or equal to "
            "MAILGUARD_MAX_COMPRESSED_BYTES: an archive cannot produce more "
            "decompressed data than its own size."
        )
    if configuration.max_upload_bytes < TAILLE_CLE_SECRETE_MINIMALE:
        raise ConfigurationErreur("A tiny import limit would make the application unusable.")
    if configuration.ai_active:
        _valider_ollama(configuration)
    return configuration


def _valider_ollama(configuration: Configuration) -> None:
    """Valide l'endpoint et le modèle **uniquement si** la narration est activée.

    Une configuration IA invalide n'empêche jamais l'analyse déterministe de
    démarrer : elle est refusée ici pour que l'utilisateur corrige, et ignorée
    silencieusement par l'adaptateur si elle survit au démarrage.
    """
    from urllib.parse import urlparse

    analyse = urlparse(configuration.ollama_url)
    if analyse.scheme not in ("http", "https"):
        raise ConfigurationErreur(
            "MAILGUARD_OLLAMA_URL must use the http or https scheme."
        )
    if not analyse.netloc:
        raise ConfigurationErreur("MAILGUARD_OLLAMA_URL must include a host.")
    if not configuration.ollama_model:
        raise ConfigurationErreur(
            "MAILGUARD_OLLAMA_MODEL must name a model already available locally when "
            "MAILGUARD_AI_ENABLED is 1."
        )
    if not configuration.ollama_allow_remote and analyse.hostname not in ADRESSES_LOOPBACK:
        raise ConfigurationErreur(
            "MAILGUARD_OLLAMA_URL must point to a loopback address unless "
            "MAILGUARD_OLLAMA_ALLOW_REMOTE is explicitly set to 1."
        )


def _charger_fichier_env() -> None:
    """Charge le fichier `.env` local s'il existe, sans modifier l'environnement global."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dépendance déclarée dans requirements.txt
        return
    load_dotenv(override=False)


def _lire_cle_secrete(source: Mapping[str, str]) -> str:
    """Clé secrète Flask, obligatoire et suffisamment longue hors tests."""
    cle = (source.get("FLASK_SECRET_KEY") or "").strip()
    if not cle:
        raise ConfigurationErreur(
            "FLASK_SECRET_KEY is missing. Generate one with: "
            "python -c \"import secrets; print(secrets.token_hex(32))\" then "
            "store it in the .env file."
        )
    if len(cle) < TAILLE_CLE_SECRETE_MINIMALE:
        raise ConfigurationErreur(
            f"FLASK_SECRET_KEY must contain at least {TAILLE_CLE_SECRETE_MINIMALE} "
            "characters; a short or predictable key is refused."
        )
    return cle


def _lire_texte(source: Mapping[str, str], nom: str, defaut: str) -> str:
    """Valeur textuelle non vide, ou la valeur par défaut."""
    valeur = (source.get(nom) or "").strip()
    return valeur or defaut


def _lire_entier(
    source: Mapping[str, str], nom: str, defaut: int, minimum: int, maximum: int | None = None
) -> int:
    """Entier d'environnement strictement validé, jamais désactivé."""
    brut = (source.get(nom) or "").strip()
    if not brut:
        return defaut
    try:
        valeur = int(brut)
    except ValueError as erreur:
        raise ConfigurationErreur(
            f"{nom} must be an integer, received « {brut} »."
        ) from erreur
    if valeur < minimum or (maximum is not None and valeur > maximum):
        borne = f"between {minimum} and {maximum}" if maximum is not None else f"at least {minimum}"
        raise ConfigurationErreur(f"{nom} must be {borne}, received « {brut} ».")
    return valeur


def _lire_nombre(
    source: Mapping[str, str], nom: str, defaut: float, minimum: float, maximum: float
) -> float:
    """Nombre flottant d'environnement strictement validé."""
    brut = (source.get(nom) or "").strip()
    if not brut:
        return defaut
    try:
        valeur = float(brut)
    except ValueError as erreur:
        raise ConfigurationErreur(f"{nom} must be a number, received « {brut} ».") from erreur
    if not minimum <= valeur <= maximum:
        raise ConfigurationErreur(
            f"{nom} must be between {minimum} and {maximum}, received « {brut} »."
        )
    return valeur


def _lire_booleen(source: Mapping[str, str], nom: str, defaut: bool) -> bool:
    """Indicateur booléen explicite ; une valeur illisible est refusée."""
    brut = (source.get(nom) or "").strip().lower()
    if not brut:
        return defaut
    if brut in VRAIS:
        return True
    if brut in FAUX:
        return False
    raise ConfigurationErreur(
        f"{nom} must be 0 or 1 (or true/false), received « {brut} »."
    )


def _poids(octets: int) -> str:
    """Taille lisible en Mio ou Kio pour l'affichage des limites."""
    if octets % (1024 * 1024) == 0:
        return f"{octets // (1024 * 1024)} Mio"
    if octets % LONGUEUR_KB == 0:
        return f"{octets // LONGUEUR_KB} Kio"
    return f"{octets} octets"


__all__ = [
    "Configuration",
    "ConfigurationErreur",
    "charger_configuration",
    "valider_configuration",
]