"""Routes HTTP de MailGuard Digest.

Les routes ne contiennent aucun calcul métier : elles valident la requête HTTP,
appellent `app.services.executer_import()` — qui enchaîne l'importateur sécurisé,
le moteur déterministe, le briefing et le stockage — puis choisissent le
gabarit de réponse. Toutes les valeurs affichées proviennent des objets réels
renvoyés par ces couches ; aucune donnée d'exemple n'est produite ici.

L'historique (`GET /history`), la consultation d'un rapport enregistré
(`GET /history/<identifiant>`) et sa suppression (`POST /history/<identifiant>/delete`)
réutilisent la couche de stockage existante : aucune requête SQL n'est écrite ici,
et le moteur de règles n'est jamais réexécuté pour relire un rapport.
"""

from __future__ import annotations

import json

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app import stockage_de
from app.core.archive import EXTENSIONS_ARCHIVE, EXTENSIONS_RAPPORT
from app.core.errors import ArchiveLimitError
from app.export import (
    construire_export_csv_sources,
    construire_export_json,
    nom_fichier_export,
)
from app.securite import verifier_jeton
from app.services import ResultatImport, executer_import, narrer_import, narration_stockee

TAILLE_BLOC = 64 * 1024
"""Taille de lecture du fichier reçu : la mémoire reste bornée."""

FORMATS_ACCEPTES = EXTENSIONS_RAPPORT + EXTENSIONS_ARCHIVE
"""Formats acceptés, repris des constantes de l'importateur."""

LIMITE_HISTORIQUE = 20
"""Nombre d'analyses listées par la page d'historique, borne de la couche de stockage."""


routes = Blueprint("racine", __name__)


@routes.get("/")
def accueil():
    """Page d'accueil : présentation, formats, limites et traitement local."""
    configuration = current_app.config["MAILGUARD_CONFIG"]
    return render_template(
        "index.html",
        formats=FORMATS_ACCEPTES,
        limites=configuration.limites_affichees,
    )


@routes.route("/upload", methods=["GET", "POST"])
def import_de_rapport():
    """Formulaire d'import et traitement du fichier téléversé."""
    configuration = current_app.config["MAILGUARD_CONFIG"]

    if request.method == "GET":
        return render_template(
            "upload.html", formats=FORMATS_ACCEPTES, limites=configuration.limites_affichees
        )

    if not verifier_jeton(request.form.get("jeton_csrf")):
        return _refus("The form session is invalid or has expired. Reload the page.")
    if request.content_length and request.content_length > configuration.max_content_length:
        return _refus("The uploaded file exceeds the maximum accepted size.", code=413)

    fichier = request.files.get("rapport")
    if fichier is None or not fichier.filename:
        return _refus("No file was selected.")

    nom_fichier = fichier.filename
    if not _extension_acceptee(nom_fichier):
        return _refus(
            f"The format of « {nom_fichier} » is not supported. Accepted formats: "
            + ", ".join(FORMATS_ACCEPTES)
            + "."
        )

    contenu = _lire_contenu(fichier, configuration.max_upload_bytes)

    stockage = stockage_de(current_app)
    resultat = executer_import(stockage, nom_fichier, contenu, configuration.limites_import)
    return render_template(
        "resultat.html",
        resultat=resultat,
        stockage=stockage,
        reconsulte=False,
        narration=narrer_import(resultat, configuration),
    )


@routes.get("/history")
def historique():
    """Historique réel des analyses enregistrées, sans jamais recalculer quoi que ce soit.

    La lecture est bornée par la limite du stockage (20 analyses par défaut) ; le
    nombre total réellement stocké est affiché à côté afin de ne pas laisser croire
    que la liste est exhaustive.
    """
    stockage = stockage_de(current_app)
    analyses = stockage.lister(limite=LIMITE_HISTORIQUE)
    return render_template(
        "history.html",
        analyses=analyses,
        limite=LIMITE_HISTORIQUE,
        total=stockage.compter(),
    )


@routes.get("/history/<int:identifiant>")
def rapport_stocke(identifiant: int):
    """Affiche un rapport déjà enregistré, relu tel quel depuis la base.

    Le parseur, l'importateur et le moteur de règles ne sont pas réexécutés : les
    résultats, constats et briefings affichés sont exactement ceux qui ont été
    enregistrés à l'époque de l'import.
    """
    stockage = stockage_de(current_app)
    enregistrement = stockage.obtenir(identifiant)
    if enregistrement is None:
        abort(404)
    return render_template(
        "resultat.html",
        resultat=ResultatImport(
            enregistrement=enregistrement, deja_importe=False, entrees_ignorees=()
        ),
        stockage=stockage,
        reconsulte=True,
        narration=narration_stockee(),
    )


@routes.post("/history/<int:identifiant>/delete")
def supprimer_analyse(identifiant: int):
    """Supprime une analyse enregistrée, uniquement par POST avec jeton CSRF valide.

    Le message de confirmation n'est émis qu'après l'appel réussi à la couche de
    stockage. Une suppression par GET est refusée par Flask (405) avant même
    d'atteindre ce gestionnaire.
    """
    if not verifier_jeton(request.form.get("jeton_csrf")):
        return _refus("The form session is invalid or has expired. Reload the page.")

    stockage = stockage_de(current_app)
    if stockage.supprimer(identifiant):
        flash("The stored analysis was deleted.", "succes")
    else:
        flash(
            "This analysis no longer exists in the local history; nothing was deleted.",
            "erreur",
        )
    return redirect(url_for("racine.historique"))


@routes.get("/history/<int:identifiant>/export.json")
def export_json(identifiant: int):
    """Télécharge l'analyse enregistrée au format JSON.

    Lecture seule : la base n'est pas modifiée, aucun moteur n'est relancé et le
    contenu XML d'origine n'est pas exporté puisqu'il n'est pas stocké.
    """
    enregistrement = _enregistrement_stocke(identifiant)
    charge = construire_export_json(enregistrement)
    reponse = current_app.response_class(
        json.dumps(charge, ensure_ascii=False, indent=2) + "\n",
        mimetype="application/json",
    )
    reponse.headers["Content-Disposition"] = (
        f'attachment; filename="{nom_fichier_export(identifiant, "json")}"'
    )
    return reponse


@routes.get("/history/<int:identifiant>/export.csv")
def export_csv(identifiant: int):
    """Télécharge le tableau des sources au format CSV.

    Les valeurs textuelles issues du rapport importé sont neutralisées contre
    l'injection de formule dans un tableur.
    """
    enregistrement = _enregistrement_stocke(identifiant)
    reponse = current_app.response_class(
        construire_export_csv_sources(enregistrement), mimetype="text/csv"
    )
    reponse.headers["Content-Disposition"] = (
        f'attachment; filename="{nom_fichier_export(identifiant, "csv")}"'
    )
    return reponse


def _enregistrement_stocke(identifiant: int):
    """Relit un enregistrement, ou interrompt la requête avec une 404 explicite."""
    enregistrement = stockage_de(current_app).obtenir(identifiant)
    if enregistrement is None:
        abort(404)
    return enregistrement


def _extension_acceptee(nom_fichier: str) -> bool:
    minuscule = nom_fichier.lower()
    return any(minuscule.endswith(extension) for extension in FORMATS_ACCEPTES)


def _lire_contenu(fichier, limite: int) -> bytes:
    """Lit le téléversement par blocs bornés, sans chemin ni fichier temporaire."""
    morceaux: list[bytes] = []
    total = 0
    while True:
        bloc = fichier.stream.read(TAILLE_BLOC)
        if not bloc:
            break
        total += len(bloc)
        if total > limite:
            raise ArchiveLimitError(
                f"The uploaded file exceeds the {limite} byte limit."
            )
        morceaux.append(bloc)
    return b"".join(morceaux)


def _refus(message: str, code: int = 400):
    """Rend la page d'accueil du formulaire avec un message d'erreur."""
    flash(message, "erreur")
    return (
        render_template(
            "upload.html",
            formats=FORMATS_ACCEPTES,
            limites=current_app.config["MAILGUARD_CONFIG"].limites_affichees,
        ),
        code,
    )


__all__ = ["routes"]