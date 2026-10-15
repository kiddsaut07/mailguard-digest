"""Protection CSRF minimale fondée sur les primitives de session Flask.

Le jeton est tiré par `secrets`, stocké dans la session du serveur et comparé
avec `secrets.compare_digest` : une soumission sans jeton, ou avec un jeton
différent, est refusée avant tout traitement. Les cookies de session sont
`HttpOnly` et `SameSite=Lax`, ce qui empêche également qu'un site tiers envoie
la requête de formulaire.
"""

from __future__ import annotations

import secrets

from flask import session

NOM_JETON = "jeton_csrf"
"""Clé de session conservant le jeton de l'onglet courant."""

TAILLE_JETON = 32
"""Octets d'entropie du jeton, tirés par `secrets.token_urlsafe`."""


def generer_jeton() -> str:
    """Crée le jeton s'il n'existe pas encore et le renvoie."""
    jeton = session.get(NOM_JETON)
    if not isinstance(jeton, str) or not jeton:
        jeton = secrets.token_urlsafe(TAILLE_JETON)
        session[NOM_JETON] = jeton
    return jeton


def verifier_jeton(candidat: str | None) -> bool:
    """Vrai si le jeton fourni correspond à celui conservé en session."""
    attendu = session.get(NOM_JETON)
    if not isinstance(attendu, str) or not attendu:
        return False
    if not isinstance(candidat, str) or not candidat:
        return False
    return secrets.compare_digest(attendu, candidat)


__all__ = ["NOM_JETON", "generer_jeton", "verifier_jeton"]