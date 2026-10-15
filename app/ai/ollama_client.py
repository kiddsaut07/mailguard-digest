"""Adaptateur Ollama : seule frontière réseau de la narration locale.

Contrat respecté :

- aucune requête n'est émise si la narration est désactivée ou mal configurée ;
- l'endpoint doit être une URL HTTP(S) loopback, sauf activation explicite de
  l'accès distant ; les redirections ne sont jamais suivies ;
- la requête est bornée (timeout de connexion et de lecture, taille de réponse
  plafonnée, génération limitée) et n'est jamais réessayée ;
- la réponse est traitée comme un texte non fiable : JSON strict, schéma strict,
  identifiants de constats vérifiés, contenu interdit détecté ;
- le moindre échec produit un `ResultatNarration` de statut non disponible ou
  rejeté, jamais une exception, et jamais de modification du briefing
  déterministe.

Le client HTTP `requests` n'est importé qu'au moment de l'appel, afin que le
chemin déterministe n'ai aucune dépendance à l'IA.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from app.ai.prompts import construire_prompt, constats_a_expliquer, identifiants_transmis
from app.core.rules import Analyse

MAX_REPONSE_OCTETS = 32 * 1024
"""Taille maximale de la réponse HTTP lue avant refus."""

MAX_EXPLICATIONS = 6
"""Nombre maximal d'explications acceptées."""

MAX_LIMITES = 6
"""Nombre maximal de limites acceptées."""

LONGUEUR_MAX_TEXTE = 1200
"""Longueur maximale d'un champ texte de la narration."""

LONGUEUR_MAX_PHRASE = 400
"""Longueur maximale d'une limitation."""

MOTIFS_INTERDITS = re.compile(
    r"(p\s*=\s*(quarantine|reject))"
    r"|(you (should|must|need to) (switch|change|set|move|adopt))"
    r"|(we recommend)"
    r"|(is (malicious|compromised|safe|legitimate))"
    r"|(<\s*script)",
    re.IGNORECASE,
)
"""
Garde-fou heuristique sur le texte généré : politique DMARC proposée, jugement
d'une source, script HTML. Ce n'est pas une frontière de sécurité — la validation
stricte du JSON et le repli déterministe restent les protections réelles.
"""

CARACTERES_INTERDITS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
"""Caractères de contrôle refusés dans la réponse du modèle."""


class StatutNarration(StrEnum):
    """Statut interne, stable, de la narration facultative."""

    DESACTIVE = "desactive"
    INDISPONIBLE = "indisponible"
    REJETE = "rejete"
    OK = "ok"


class ModelNarration(BaseModel):
    """Base des objets de narration, figés et sans champ inconnu."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Explication(ModelNarration):
    """Explication rattachée à un constat existant."""

    finding_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=LONGUEUR_MAX_TEXTE)


class Narration(ModelNarration):
    """Schéma strict attendu du modèle."""

    summary: str = Field(min_length=1, max_length=LONGUEUR_MAX_TEXTE)
    explanations: list[Explication] = Field(max_length=MAX_EXPLICATIONS)
    limitations: list[str] = Field(max_length=MAX_LIMITES)


class ResultatNarration(ModelNarration):
    """Résultat présenté à l'interface, jamais utilisé comme source de vérité."""

    statut: StatutNarration
    message: str = ""
    resume: str = ""
    explications: list[Explication] = Field(default_factory=list)
    limites: list[str] = Field(default_factory=list)
    modele: str = ""
    duree_ms: int | None = None

    @property
    def disponible(self) -> bool:
        """Vrai uniquement si une narration validée est disponible."""
        return self.statut is StatutNarration.OK


@dataclass(frozen=True)
class ParametresNarration:
    """Paramètres de l'adaptateur, tous explicites et bornés."""

    actif: bool = False
    url: str = "http://127.0.0.1:11434"
    modele: str = ""
    timeout_secondes: float = 10.0
    max_input_chars: int = 4000
    max_output_tokens: int = 300
    autorise_distant: bool = False


Transport = Callable[[str, dict, float, int], bytes]
"""Signature du transport : url, charge utile, timeout, taille maximale lue."""


class ClientOllama:
    """Client de narration locale, sans effet de bord tant qu'il n'est pas appelé."""

    _verrou = threading.Lock()
    """Garde simple : une seule narration à la fois, pour ne pas peser sur la mémoire."""

    def __init__(
        self,
        parametres: ParametresNarration,
        transport: Transport | None = None,
    ) -> None:
        self._parametres = parametres
        self._transport = transport or _transport_requests

    @property
    def actif(self) -> bool:
        """Vrai si la narration est activée dans la configuration."""
        return bool(self._parametres.actif)

    def narrer(self, analyse: Analyse) -> ResultatNarration:
        """Demande une narration, sans jamais lever d'exception."""
        if not self.actif:
            return ResultatNarration(
                statut=StatutNarration.DESACTIVE,
                message="AI narration is disabled.",
            )
        erreur_configuration = self._verifier_configuration()
        if erreur_configuration:
            return ResultatNarration(
                statut=StatutNarration.DESACTIVE,
                message=erreur_configuration,
                modele=self._parametres.modele,
            )

        constats = constats_a_expliquer(analyse)
        if not constats:
            return ResultatNarration(
                statut=StatutNarration.INDISPONIBLE,
                message="There is no finding to explain.",
                modele=self._parametres.modele,
            )
        prompt = construire_prompt(analyse, self._parametres.max_input_chars)
        if prompt is None:
            return ResultatNarration(
                statut=StatutNarration.REJETE,
                message="The configured input limit is too small for this report.",
                modele=self._parametres.modele,
            )

        return self._appeler(analyse, prompt, identifiants_transmis(constats))

    # --- Interne -------------------------------------------------------------

    def _verifier_configuration(self) -> str:
        """Message d'erreur si la configuration locale est inutilisable, sinon vide."""
        analyse_url = urlparse(self._parametres.url)
        if analyse_url.scheme not in ("http", "https") or not analyse_url.netloc:
            return "The local model endpoint is not a valid HTTP(S) URL."
        if not self._parametres.modele:
            return "No local model name is configured."
        if not self._parametres.autorise_distant and analyse_url.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            return "The local model endpoint is not a loopback address."
        return ""

    def _appeler(
        self, analyse: Analyse, prompt: tuple[str, str], ids: set[str]
    ) -> ResultatNarration:
        """Émet une requête unique et valide strictement la réponse."""
        systeme, utilisateur = prompt
        charge = {
            "model": self._parametres.modele,
            "stream": False,
            "messages": [
                {"role": "system", "content": systeme},
                {"role": "user", "content": utilisateur},
            ],
            "options": {
                "temperature": 0,
                "num_predict": self._parametres.max_output_tokens,
            },
        }
        depart = time.monotonic()
        if not ClientOllama._verrou.acquire(blocking=False):
            return ResultatNarration(
                statut=StatutNarration.INDISPONIBLE,
                message="A local narration is already running.",
                modele=self._parametres.modele,
            )
        try:
            brut = self._transport(
                self._parametres.url.rstrip("/") + "/api/chat",
                charge,
                self._parametres.timeout_secondes,
                MAX_REPONSE_OCTETS,
            )
        except Exception as erreur:  # échec ordinaire d'une fonction optionnelle
            return ResultatNarration(
                statut=StatutNarration.INDISPONIBLE,
                message=f"The local model could not be reached ({type(erreur).__name__}).",
                modele=self._parametres.modele,
                duree_ms=_duree_ms(depart),
            )
        finally:
            ClientOllama._verrou.release()

        return self._valider(brut, ids, depart)

    def _valider(self, brut: bytes, ids: set[str], depart: float) -> ResultatNarration:
        """Valide strictement la réponse du modèle ; à défaut, repli déterministe."""
        modele = self._parametres.modele
        try:
            enveloppe = json.loads(brut.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._refuse("The local model returned a response that is not JSON.")
        if not isinstance(enveloppe, dict):
            return self._refuse("The local model returned an unexpected structure.")
        message = enveloppe.get("message")
        contenu = message.get("content") if isinstance(message, dict) else None
        if not isinstance(contenu, str):
            return self._refuse("The local model response has no usable text field.")

        charge = _extraire_json(contenu)
        if charge is None:
            return self._refuse("The local model did not return the requested JSON object.")
        try:
            narration = Narration.model_validate(charge)
        except ValueError:
            return self._refuse("The local model output does not match the expected schema.")

        inconnus = [
            explication.finding_id
            for explication in narration.explanations
            if explication.finding_id not in ids
        ]
        if inconnus:
            return self._refuse("The local model referenced a finding that does not exist.")
        textes = [narration.summary, *(e.text for e in narration.explanations), *narration.limitations]
        if any(len(texte) > LONGUEUR_MAX_TEXTE for texte in textes):
            return self._refuse("The local model output is too long.")
        if any(CARACTERES_INTERDITS.search(texte) for texte in textes):
            return self._refuse("The local model output contains unsupported characters.")
        if any(MOTIFS_INTERDITS.search(texte) for texte in textes):
            return self._refuse("The local model output contains prohibited statements.")

        return ResultatNarration(
            statut=StatutNarration.OK,
            message="Narration generated by the local model.",
            resume=narration.summary,
            explications=list(narration.explanations),
            limites=list(narration.limitations),
            modele=modele,
            duree_ms=_duree_ms(depart),
        )

    def _refuse(self, message: str) -> ResultatNarration:
        """Construit un résultat rejeté, avec le même repli que l'indisponibilité."""
        return ResultatNarration(
            statut=StatutNarration.REJETE,
            message=message,
            modele=self._parametres.modele,
        )


def _extraire_json(contenu: str) -> dict | None:
    """Extrait l'objet JSON attendu, en tolérant un éventuel bloc de code Markdown."""
    charge = _essayer_json(contenu)
    if charge is not None:
        return charge
    premier = contenu.find("{")
    dernier = contenu.rfind("}")
    if premier == -1 or dernier <= premier:
        return None
    return _essayer_json(contenu[premier : dernier + 1])


def _essayer_json(texte: str) -> dict | None:
    """Charge un objet JSON, ou renvoie `None` silencieusement."""
    try:
        charge = json.loads(texte)
    except json.JSONDecodeError:
        return None
    return charge if isinstance(charge, dict) else None


def _duree_ms(depart: float) -> int:
    """Durée écoulée en millisecondes."""
    return int((time.monotonic() - depart) * 1000)


def _transport_requests(url: str, charge: dict, timeout: float, taille_max: int) -> bytes:
    """Transport HTTP par défaut : `requests`, sans redirection ni corps illimité."""
    import requests

    delai = (min(3.0, timeout), timeout)
    reponse = requests.post(
        url,
        json=charge,
        timeout=delai,
        allow_redirects=False,
        stream=True,
        headers={"Content-Type": "application/json"},
    )
    try:
        reponse.raise_for_status()
        return reponse.raw.read(taille_max + 1, decode_content=False)[:taille_max + 1]
    finally:
        reponse.close()


__all__ = [
    "ClientOllama",
    "Explication",
    "MAX_EXPLICATIONS",
    "MAX_LIMITES",
    "MAX_REPONSE_OCTETS",
    "Narration",
    "ParametresNarration",
    "ResultatNarration",
    "StatutNarration",
]