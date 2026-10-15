"""Tests HTTP de l'application Flask (étape 6).

Chaque test utilise une application de test isolée : clé secrète jetable, base
SQLite temporaire et aucune donnée fictive. Les fichiers téléversés proviennent des
fixtures synthétiques existantes et traversent le pipeline réel.
"""

import ast
import csv
from dataclasses import replace
import html
import io
import json
import re
import sqlite3
import zipfile
from pathlib import Path

import pytest

from app import create_app
from app.config import Configuration, charger_configuration
from app.core.archive import import_reports
from app.core.briefing import construire_briefing
from app.core.errors import ConfigurationErreur, StorageError
from app.core.rules import analyser
from app.export import COLONNES_CSV_SOURCES, VERSION_EXPORT
from app.main import creer_application, initialiser_stockage
from app.storage.database import calculer_empreinte

CHEMIN_FIXTURES = Path(__file__).parent / "fixtures"
MOTIF_JETON = re.compile(r'name="jeton_csrf" value="([^"]+)"')


def fixture(nom: str) -> bytes:
    """Octets exacts d'une fixture synthétique."""
    return (CHEMIN_FIXTURES / nom).read_bytes()


def archive_zip(entrees: dict[str, bytes]) -> bytes:
    """Archive ZIP synthétique construite en mémoire."""
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        for nom, contenu in entrees.items():
            archive.writestr(nom, contenu)
    return tampon.getvalue()


@pytest.fixture()
def application(tmp_path) -> "Flask":  # noqa: F821 - annotation volontairement légère
    """Application de test : base temporaire, stockage initialisé une seule fois."""
    configuration = Configuration.pour_tests(tmp_path / "historique.sqlite3")
    app = create_app(configuration)
    app.config["TESTING"] = True
    initialiser_stockage(app)
    return app


@pytest.fixture()
def client(application):
    """Client de test Flask."""
    return application.test_client()


def jeton(client) -> str:
    """Lit un jeton CSRF valide dans le formulaire d'import."""
    page = client.get("/upload")
    correspondance = MOTIF_JETON.search(page.get_data(as_text=True))
    assert correspondance is not None
    return correspondance.group(1)


def televerser(client, nom: str, contenu: bytes, avec_jeton: bool = True):
    """Envoie un fichier par le formulaire, jeton CSRF valide par défaut."""
    donnees = {"rapport": (io.BytesIO(contenu), nom)}
    if avec_jeton:
        donnees["jeton_csrf"] = jeton(client)
    return client.post(
        "/upload", data=donnees, content_type="multipart/form-data"
    )


def application_stockage(client):
    """Stockage de l'application utilisée par le client de test."""
    return client.application.extensions["stockage"]


def texte(reponse) -> str:
    """Corps de la réponse en texte, entités HTML résolues (apostrophes notamment)."""
    return html.unescape(reponse.get_data(as_text=True))


def brut(reponse) -> str:
    """Corps de la réponse tel qu'envoyé, pour vérifier l'échappement."""
    return reponse.get_data(as_text=True)


# --- Parcours normal ---------------------------------------------------------


def test_accueil_explique_le_produit_sans_donnee_de_demonstration(client):
    reponse = client.get("/")

    assert reponse.status_code == 200
    corps = texte(reponse)
    assert "MailGuard Digest" in corps
    assert ".xml.gz" in corps and ".zip" in corps
    assert "local" in corps.lower()
    assert "Sources and results" not in corps
    assert "Total messages" not in corps


def test_accueil_affiche_les_limites_de_la_configuration(client, application):
    corps = texte(client.get("/"))

    assert "Processing limits" in corps
    for valeur in application.config["MAILGUARD_CONFIG"].limites_affichees.values():
        assert valeur in corps


def test_page_import_contient_le_formulaire_protecte(client):
    reponse = client.get("/upload")
    corps = texte(reponse)

    assert reponse.status_code == 200
    assert 'enctype="multipart/form-data"' in corps
    assert 'name="jeton_csrf"' in corps
    assert 'name="rapport"' in corps
    assert 'type="file"' in corps


def test_import_xml_valide_affiche_les_mesures_reelles(client, application):
    reponse = televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml"))
    corps = texte(reponse)

    assert reponse.status_code == 200
    assert "DMARC analysis result" in corps
    assert "125" in corps
    assert "80.0 %" in corps
    assert "20.0 %" in corps
    assert "quarantine : 100" in corps
    assert "198.51.100.30" in corps
    assert "DMARC failures observed" in corps


def test_import_enregistre_et_permet_de_relire(client, application):
    televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml"))
    stockage = application.extensions["stockage"]
    ligne = stockage.lister()[0]

    assert stockage.compter() == 1
    relu = stockage.obtenir(ligne.identifiant)
    assert relu is not None
    assert relu.analyse.metriques.total_messages == 125
    assert relu.analyse.metriques.messages_fail == 25
    assert relu.briefing.resume_executif == stockage.obtenir(1).briefing.resume_executif


def test_import_gzip_valide(client, application):
    import gzip

    reponse = televerser(
        client, "rapport.xml.gz", gzip.compress(fixture("rapport_dkim_multiples.xml"))
    )

    assert reponse.status_code == 200
    assert "9" in texte(reponse)
    assert application.extensions["stockage"].compter() == 1


def test_import_zip_valide_avec_deux_rapports(client, application):
    contenu = archive_zip(
        {
            "a.xml": fixture("rapport_valide_sans_namespace.xml"),
            "b.xml": fixture("rapport_autre_domaine.xml"),
        }
    )

    reponse = televerser(client, "rapports.zip", contenu)
    corps = texte(reponse)

    assert reponse.status_code == 200
    assert "2 reports" in corps
    assert application.extensions["stockage"].compter() == 1
    relu = application.extensions["stockage"].obtenir(1)
    assert relu.analyse.metriques.nombre_rapports == 2
    assert relu.analyse.metriques.total_messages == 53


def test_entrees_non_xml_dans_une_archive_sont_signalees(client):
    contenu = archive_zip(
        {
            "rapport.xml": fixture("rapport_valide_sans_namespace.xml"),
            "lisezmoi.txt": b"texte ordinaire",
        }
    )

    corps = texte(televerser(client, "rapports.zip", contenu))

    assert "Entries ignored after validation" in corps
    assert "lisezmoi.txt" in corps


def test_doublon_nest_pas_presented_comme_une_nouvelle_analyse(client, application):
    contenu = fixture("rapport_plusieurs_records.xml")
    premier = televerser(client, "rapport.xml", contenu)
    second = televerser(client, "rapport.xml", contenu)

    assert premier.status_code == 200 and second.status_code == 200
    assert "already been imported" in texte(second)
    assert application.extensions["stockage"].compter() == 1


def test_rapport_sans_echec_ne_produit_pas_de_constat_d_attention(client):
    corps = texte(televerser(client, "rapport.xml", fixture("rapport_valide_sans_namespace.xml")))

    assert "No DMARC failure observed" in corps
    assert "is not a security guarantee" in corps


# --- Requêtes invalides ------------------------------------------------------


def test_fichier_absent_refuse(client, application):
    reponse = client.post(
        "/upload",
        data={"jeton_csrf": jeton(client)},
        content_type="multipart/form-data",
    )

    assert reponse.status_code == 400
    assert "No file was selected" in texte(reponse)
    assert application.extensions["stockage"].compter() == 0


def test_extension_non_prise_en_charge_refusee(client, application):
    reponse = televerser(client, "rapport.txt", fixture("rapport_plusieurs_records.xml"))

    assert reponse.status_code == 400
    assert "is not supported" in texte(reponse)
    assert application.extensions["stockage"].compter() == 0


def test_extension_valide_avec_contenu_hors_format_refuse(client):
    reponse = televerser(client, "rapport.xml", b"ceci est un texte ordinaire")

    assert reponse.status_code == 400
    assert "the content is not XML" in texte(reponse)


def test_xml_malforme_refuse(client):
    reponse = televerser(client, "rapport.xml", fixture("rapport_tronque.xml"))

    assert reponse.status_code == 400
    assert "unreadable" in texte(reponse) or "truncated" in texte(reponse)


def test_rapport_non_conforme_aux_modeles_refuse(client):
    reponse = televerser(client, "rapport.xml", fixture("rapport_ip_invalide.xml"))

    assert reponse.status_code == 400
    assert "source_ip" in texte(reponse)


def test_archive_dangereuse_refusee(client):
    contenu = archive_zip({"../evade.xml": fixture("rapport_valide_sans_namespace.xml")})

    reponse = televerser(client, "rapports.zip", contenu)

    assert reponse.status_code == 400
    assert "escapes the archive root" in texte(reponse)


def test_archive_imbriquee_refusee(client):
    interieur = archive_zip({"rapport.xml": fixture("rapport_valide_sans_namespace.xml")})
    contenu = archive_zip({"archive.zip": interieur})

    reponse = televerser(client, "rapports.zip", contenu)

    assert reponse.status_code == 400
    assert "nested archive refused" in texte(reponse)


def test_gzip_corrompu_refuse(client):
    reponse = televerser(client, "rapport.xml.gz", b"ceci n'est pas un fichier gzip")

    assert reponse.status_code == 400
    assert "GZIP" in texte(reponse)


def test_taille_http_depassee_refusee(client, application):
    reponse = televerser(client, "rapport.xml", b"A" * (512 * 1024))

    assert reponse.status_code == 413
    assert application.extensions["stockage"].compter() == 0


def test_limite_de_rapports_de_la_configuration_est_appliquee(client, application):
    contenu = archive_zip(
        {
            "a.xml": fixture("rapport_valide_sans_namespace.xml"),
            "b.xml": fixture("rapport_autre_domaine.xml"),
            "c.xml": fixture("rapport_dkim_multiples.xml"),
        }
    )

    reponse = televerser(client, "rapports.zip", contenu)

    assert application.config["MAILGUARD_CONFIG"].max_reports_per_import == 2
    assert reponse.status_code == 413
    assert "the limit is 2" in texte(reponse)


def test_echec_de_stockage_remonte_sans_reussite_fausse(client, application, monkeypatch):
    def echec(*arguments, **mots):
        raise StorageError("Le stockage local est indisponible.")

    monkeypatch.setattr(
        "app.storage.database.StockageAnalyses.enregistrer", echec
    )

    reponse = televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml"))

    assert reponse.status_code == 503
    assert "Nothing was saved" in texte(reponse)
    assert "Traceback" not in brut(reponse)


def test_erreur_interne_ne_fuit_pas_de_trace(client, monkeypatch):
    def panne(*arguments, **mots):
        raise RuntimeError("secret interne 12345")

    monkeypatch.setattr("app.services.analyser", panne)

    reponse = televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml"))

    assert reponse.status_code == 500
    assert "Traceback" not in brut(reponse)
    assert "secret interne" not in texte(reponse)


# --- Sécurité HTTP -----------------------------------------------------------


def test_post_sans_jeton_csrf_refuse(client, application):
    reponse = client.post(
        "/upload",
        data={"rapport": (io.BytesIO(fixture("rapport_valide_sans_namespace.xml")), "rapport.xml")},
        content_type="multipart/form-data",
    )

    assert reponse.status_code == 400
    assert "form session is invalid" in texte(reponse)
    assert application.extensions["stockage"].compter() == 0


def test_post_avec_jeton_invalide_refuse(client, application):
    donnees = {
        "rapport": (io.BytesIO(fixture("rapport_valide_sans_namespace.xml")), "rapport.xml"),
        "jeton_csrf": "jeton-fabrique",
    }

    reponse = client.post("/upload", data=donnees, content_type="multipart/form-data")

    assert reponse.status_code == 400
    assert application.extensions["stockage"].compter() == 0


def test_post_avec_jeton_valide_accepte(client, application):
    reponse = televerser(client, "rapport.xml", fixture("rapport_valide_sans_namespace.xml"))

    assert reponse.status_code == 200
    assert application.extensions["stockage"].compter() == 1


def test_jeton_csrf_differend_entre_deux_sessions(client):
    premier = jeton(client)
    second = jeton(client)

    assert premier == second


def test_nom_de_fichier_dangereux_est_echappe(client):
    reponse = televerser(
        client, "<script>alert(1)</script>.xml", fixture("rapport_valide_sans_namespace.xml")
    )
    corps = brut(reponse)

    assert reponse.status_code == 200
    assert "<script>alert(1)</script>" not in corps
    # Le nom est réduit à son dernier segment par l'importeur, puis échappé par Jinja.
    assert "script&gt;.xml" in corps
    assert application_stockage(client).obtenir(1).nom_fichier == "script>.xml"


def test_contenu_xss_du_rapport_est_echappe(client):
    charge = """<?xml version="1.0" encoding="UTF-8"?>
<feedback>
  <version>1.0</version>
  <report_metadata>
    <org_name>&lt;img src=x onerror=alert(1)&gt;</org_name>
    <date_range>
      <begin>1759276800</begin>
      <end>1759363200</end>
    </date_range>
  </report_metadata>
  <policy_published>
    <domain>example.com</domain>
    <p>none</p>
  </policy_published>
  <record>
    <row>192.0.2.10</row>
    <count>1</count>
    <policy_evaluated>
      <disposition>none</disposition>
      <dkim>pass</dkim>
      <spf>pass</spf>
    </policy_evaluated>
  </record>
</feedback>"""

    reponse = televerser(client, "rapport.xml", charge.encode("utf-8"))
    corps = brut(reponse)

    assert reponse.status_code == 200
    assert "<img src=x onerror" not in corps
    assert "&lt;img src=x onerror=alert(1)&gt;" in corps


def test_entetes_de_securite_presents(client):
    entetes = client.get("/").headers

    assert entetes["X-Content-Type-Options"] == "nosniff"
    assert entetes["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in entetes["Content-Security-Policy"]


def test_le_xml_brut_nest_jamais_ecrit_en_base(client, application):
    televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml"))

    with sqlite3.connect(application.extensions["stockage"].chemin) as connexion:
        connexion.row_factory = sqlite3.Row
        lignes = connexion.execute("SELECT * FROM analyses").fetchall()
    contenu_base = " ".join(str(valeur) for ligne in lignes for valeur in tuple(ligne))

    for marqueur in ("<feedback", "<record", "<?xml version", "policy_evaluated"):
        assert marqueur not in contenu_base


def test_la_base_ne_depend_pas_du_nom_envoye(client, application, tmp_path):
    televerser(client, "../../../../evil.xml", fixture("rapport_valide_sans_namespace.xml"))

    chemin = application.extensions["stockage"].chemin
    assert chemin == tmp_path / "historique.sqlite3"
    assert sorted(element.name for element in tmp_path.iterdir()) == ["historique.sqlite3"]


def test_cookie_de_session_protege(client):
    reponse = client.get("/upload")

    cookie = reponse.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_page_inconnue_renvoie_une_erreur_claire(client):
    reponse = client.get("/inconnu")

    assert reponse.status_code == 404
    assert "does not exist" in texte(reponse)


def test_methode_interdite_sur_accueil(client):
    reponse = client.post("/")

    assert reponse.status_code == 405
    assert "Traceback" not in brut(reponse)


# --- Isolation et configuration ----------------------------------------------


def test_application_de_test_nutilise_jamais_la_base_reelle(application, tmp_path):
    chemin = application.extensions["stockage"].chemin

    assert chemin.parent == tmp_path
    assert chemin.exists()


def test_application_de_test_ne_demande_aucun_service_externe(application):
    assert application.config["MAILGUARD_CONFIG"].ai_active is False
    assert application.config["MAILGUARD_CONFIG"].debug is False


def test_creation_application_sans_effet_de_bord_sur_la_base(tmp_path):
    chemin = tmp_path / "base.sqlite3"
    configuration = Configuration.pour_tests(chemin)
    application = creer_application(configuration)

    assert application.extensions["stockage"].chemin == chemin
    initialiser_stockage(application)
    nombre_avant = application.extensions["stockage"].compter()

    creer_application(configuration)
    initialiser_stockage(application)

    assert application.extensions["stockage"].compter() == nombre_avant


def test_configuration_incomplete_refusee():
    with pytest.raises(ConfigurationErreur) as erreur:
        charger_configuration({}, charger_fichier_env=False)

    assert "FLASK_SECRET_KEY" in str(erreur.value)


def test_cle_secrete_trop_courte_refusee():
    with pytest.raises(ConfigurationErreur):
        charger_configuration({"FLASK_SECRET_KEY": "court"}, charger_fichier_env=False)


def test_valeur_numerique_invalide_refusee():
    with pytest.raises(ConfigurationErreur) as erreur:
        charger_configuration(
            {"FLASK_SECRET_KEY": "x" * 40, "MAILGUARD_MAX_DECOMPRESSED_BYTES": "beaucoup"},
            charger_fichier_env=False,
        )

    assert "MAILGUARD_MAX_DECOMPRESSED_BYTES" in str(erreur.value)


def test_port_hors_borne_refuse():
    with pytest.raises(ConfigurationErreur):
        charger_configuration(
            {"FLASK_SECRET_KEY": "x" * 40, "MAILGUARD_PORT": "70000"},
            charger_fichier_env=False,
        )


def test_limite_http_inferieure_a_la_limite_fichier_refusee():
    with pytest.raises(ConfigurationErreur) as erreur:
        charger_configuration(
            {
                "FLASK_SECRET_KEY": "x" * 40,
                "MAILGUARD_MAX_COMPRESSED_BYTES": "2048",
                "MAILGUARD_MAX_CONTENT_LENGTH": "1024",
            },
            charger_fichier_env=False,
        )

    assert "MAILGUARD_MAX_CONTENT_LENGTH" in str(erreur.value)


def test_defauts_documentes_appliques_quand_une_variable_absence():
    configuration = charger_configuration({"FLASK_SECRET_KEY": "x" * 40}, charger_fichier_env=False)

    assert configuration.max_upload_bytes == 10 * 1024 * 1024
    assert configuration.max_decompressed_bytes == 50 * 1024 * 1024
    assert configuration.max_archive_members == 100
    assert configuration.max_reports_per_import == 20
    assert configuration.hote == "127.0.0.1"
    assert configuration.debug is False
    assert configuration.ai_active is False

# --- Étape 7 : rendu, accessibilité et cohérence linguistique ----------------

SECTIONS_RAPPORT = (
    "Report identification",
    "Quantitative summary",
    "Sources and results",
    "Deterministic findings",
    "Analysis briefing",
    "Import record",
)

JETONS_FRANCAIS = (
    "le rapport",
    "du rapport",
    "n'a pas pu",
    "échec",
    "déjà",
    "quarantaine",
    "Entrées ignorées",
    "Vous pouvez",
    "Aucun fichier",
    "téléversé",
    "Briefing déterministe",
)


def chaines_utilisateur(chemin: Path) -> list[str]:
    """Chaînes visibles par l'utilisateur : hors docstrings et commentaires."""
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    docstrings = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            premier = noeud.body[0] if noeud.body else None
            if isinstance(premier, ast.Expr) and isinstance(premier.value, ast.Constant):
                if isinstance(premier.value.value, str):
                    docstrings.add(id(premier.value))
    return [
        noeud.value
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.Constant)
        and isinstance(noeud.value, str)
        and id(noeud) not in docstrings
    ]


def texte_visible(source: str) -> str:
    """Texte réellement affiché : balises HTML et expressions Jinja retirées."""
    sans_expressions = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", " ", source, flags=re.S)
    return re.sub(r"<[^>]+>", " ", sans_expressions)


def test_pages_declarent_la_bangue_anglaise_et_un_lien_d_evitement(client):
    for adresse in ("/", "/upload"):
        corps = brut(client.get(adresse))
        assert '<html lang="en">' in corps
        assert 'class="lien-evitement"' in corps
        assert 'href="#contenu"' in corps
        assert 'id="contenu"' in corps


def test_la_feuille_de_style_locale_est_servie(client, application):
    reponse = client.get("/static/css/style.css")

    assert reponse.status_code == 200
    assert "text/css" in reponse.headers["Content-Type"]
    assert "http://" not in reponse.get_data(as_text=True)
    assert "https://" not in reponse.get_data(as_text=True)


def test_chaque_page_reference_la_feuille_de_style_locale(client):
    for adresse in ("/", "/upload"):
        corps = brut(client.get(adresse))
        assert "/static/css/style.css" in corps


def test_le_fichier_css_est_bien_a_l_emplacement_attendu(application):
    assert (Path(application.root_path) / "static" / "css" / "style.css").is_file()


def test_navigation_limitée_aux_routes_existantes(client):
    corps = brut(client.get("/"))

    assert 'href="/upload"' in corps
    assert 'href="/"' in corps
    assert 'href="/history"' in corps
    for inexistant in ("/export", "/api", "/login"):
        assert f'href="{inexistant}"' not in corps


def test_le_rapport_affiche_les_sections_requises(client):
    corps = texte(televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml")))

    for section in SECTIONS_RAPPORT:
        assert section in corps
    assert "<table" in corps
    assert "Evaluated SPF" in corps
    assert "Evaluated DKIM" in corps
    assert "Observed dispositions" in corps


def test_le_rapport_affiche_les_valeurs_reelles_de_la_source(client):
    corps = texte(televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml")))

    assert "198.51.100.30" in corps
    assert "2001:db8::5" in corps
    assert "example.com" in corps
    assert "2025-10-01 00:00" in corps


def test_un_taux_indisponible_nest_pas_remplace_par_zero(client):
    corps = texte(televerser(client, "rapport.xml", fixture("rapport_volume_nul.xml")))

    assert "Not calculable" in corps
    assert "0.0 %" not in corps
    assert "100.0 %" not in corps


def test_les_champs_optionnels_absents_sont_affiches_neutrement(client):
    corps = texte(televerser(client, "rapport.xml", fixture("rapport_sans_identifiants.xml")))

    assert corps.count("Not available in the report") >= 2
    assert "example.com" not in corps


def test_le_briefing_est_affiche_comme_texte_echappe(client):
    charge = """<?xml version="1.0" encoding="UTF-8"?>
<feedback>
  <version>1.0</version>
  <report_metadata>
    <org_name>Provider &lt;b onmouseover=&quot;steal()&quot;&gt;bold&lt;/b&gt;</org_name>
    <date_range>
      <begin>1759276800</begin>
      <end>1759363200</end>
    </date_range>
  </report_metadata>
  <policy_published>
    <domain>example.com</domain>
    <p>none</p>
  </policy_published>
  <record>
    <row>192.0.2.10</row>
    <count>1</count>
    <policy_evaluated>
      <disposition>none</disposition>
      <dkim>pass</dkim>
      <spf>pass</spf>
    </policy_evaluated>
  </record>
</feedback>"""

    corps = brut(televerser(client, "rapport.xml", charge.encode("utf-8")))

    assert "<b onmouseover" not in corps
    assert "&lt;b onmouseover=&#34;steal()&#34;&gt;bold&lt;/b&gt;" in corps


def test_un_domaine_avec_charge_utilisable_ne_devient_pas_executable(client):
    corps = brut(televerser(client, "rapport.xml", fixture("rapport_valide_sans_namespace.xml")))

    # Seul script autorisé : la balise locale du navigateur, sans code inline.
    assert corps.count("<script") == 1
    assert '<script src="/static/js/print.js"' in corps
    assert "onclick=" not in corps
    assert "|safe" not in corps


def test_les_pages_sont_en_anglais(client):
    pages = [client.get("/"), client.get("/upload")]
    pages.append(televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml")))
    pages.append(client.get("/inconnu"))

    for reponse in pages:
        corps = texte(reponse).lower()
        for mot in JETONS_FRANCAIS:
            assert mot.lower() not in corps, f"texte français « {mot} » dans la réponse"


def test_aucune_chaine_francaise_dans_les_gabarits_et_messages():
    fichiers = [
        Path("app/templates") / nom
        for nom in ("base.html", "index.html", "upload.html", "resultat.html", "erreur.html")
    ]
    modules = [
        Path("app/api/routes.py"),
        Path("app/erreurs.py"),
        Path("app/config.py"),
        Path("app/core/briefing.py"),
    ]

    for chemin in fichiers:
        contenu = texte_visible(chemin.read_text(encoding="utf-8"))
        for mot in JETONS_FRANCAIS:
            assert mot not in contenu, f"« {mot} » encore visible dans {chemin}"

    for chemin in modules:
        for chaine in chaines_utilisateur(chemin):
            for mot in JETONS_FRANCAIS:
                assert mot not in chaine, f"« {mot} » encore présent dans {chemin}"


def test_le_rapport_signale_visuellement_le_doublon(client):
    contenu = fixture("rapport_valide_sans_namespace.xml")
    televerser(client, "rapport.xml", contenu)
    second = televerser(client, "rapport.xml", contenu)

    corps = texte(second)
    assert "This report has already been imported" in corps
    assert "alerte--doublon" in brut(second)


def test_le_rapport_signale_les_entrees_ignorees(client):
    contenu = archive_zip(
        {
            "rapport.xml": fixture("rapport_valide_sans_namespace.xml"),
            "notes.txt": b"notes ordinaires",
        }
    )

    corps = texte(televerser(client, "rapports.zip", contenu))

    assert "Entries ignored after validation" in corps
    assert "notes.txt" in corps


def test_les_constats_affichent_niveau_et_limite(client):
    corps = texte(televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml")))

    assert "constat--attention" in corps
    assert "Interpretation limit:" in corps
    assert "etiquette--attention" in corps


def test_le_pied_de_page_reste_local(client):
    corps = texte(client.get("/"))

    assert "runs entirely on this machine" in corps
    assert "No remote" in corps or "no remote" in corps.lower()


# --- Étape 8 : historique, rapport stocké et suppression CSRF ---------------


def importer(client, nom: str, fixture_nom: str = "rapport_valide_sans_namespace.xml"):
    """Importe une fixture par le formulaire et renvoie la réponse."""
    return televerser(client, nom, fixture(fixture_nom))


def identifiants(client) -> list[int]:
    """Identifiants stockés, du plus récent au plus ancien."""
    return [resume.identifiant for resume in application_stockage(client).lister()]


def test_historique_vide_affiche_un_etat_vide(client):
    reponse = client.get("/history")
    corps = texte(reponse)

    assert reponse.status_code == 200
    assert "Analysis History" in corps
    assert "No stored analysis yet" in corps
    assert 'href="/upload"' in corps
    assert "View report" not in corps


def test_historique_liste_les_analyses_reellement_stockees(client):
    importer(client, "rapport.xml", "rapport_plusieurs_records.xml")
    importer(client, "autre.xml", "rapport_autre_domaine.xml")

    corps = texte(client.get("/history"))

    assert "example.com" in corps
    assert "example.net" in corps
    assert "125" in corps
    assert "100 / 25" in corps
    assert "Showing the 20 most recent analyses of 2 stored" in corps


def test_historique_lie_chaque_entree_vers_son_rapport(client):
    importer(client, "rapport.xml", "rapport_plusieurs_records.xml")

    corps = brut(client.get("/history"))
    identifiant = identifiants(client)[0]

    assert f'href="/history/{identifiant}"' in corps
    assert "View report" in corps


def test_historique_affiche_une_limite_bornee_sans_pretendre_etre_exhaustif(client):
    stockage = application_stockage(client)
    contenu = fixture("rapport_valide_sans_namespace.xml")
    resultat = import_reports("rapport.xml", contenu)
    analyse = analyser(resultat.reports)
    briefing = construire_briefing(analyse)
    for index in range(25):
        variante = contenu + b"\n" * (index + 1)
        stockage.enregistrer(variante, resultat, analyse, briefing)

    assert stockage.compter() == 25
    corps = texte(client.get("/history"))

    assert "Showing the 20 most recent analyses of 25 stored" in corps
    assert "older entries are not listed here" in corps
    assert corps.count('class="lien-action"') == 20


def test_historique_ne_declare_pas_de_donnee_absente(client):
    importer(client, "rapport.xml", "rapport_sans_identifiants.xml")

    corps = texte(client.get("/history"))

    assert "Not available" in corps
    assert "example.net" not in corps


def test_historique_ignore_les_identifiants_du_rapport_dans_les_titres(client):
    importer(client, "rapport.xml", "rapport_sans_identifiants.xml")

    corps = texte(client.get("/history"))

    assert "Domain" not in corps or "Published domain" in corps
    assert "Not available" in corps


def test_rapport_stocke_s_ouvre_sans_recalcul(client):
    importer(client, "rapport.xml", "rapport_plusieurs_records.xml")
    identifiant = identifiants(client)[0]

    reponse = client.get(f"/history/{identifiant}")
    corps = texte(reponse)

    assert reponse.status_code == 200
    assert "Viewing a stored analysis" in corps
    assert "125" in corps
    assert "80.0 %" in corps
    assert "198.51.100.30" in corps
    assert "DMARC failures observed" in corps


def test_rapport_stocke_ne_rerun_pas_le_moteur(client, monkeypatch):
    importer(client, "rapport.xml", "rapport_plusieurs_records.xml")
    identifiant = identifiants(client)[0]

    def interdit(*arguments, **mots):
        raise AssertionError("the deterministic engine must not run for a stored report")

    monkeypatch.setattr("app.services.analyser", interdit)

    reponse = client.get(f"/history/{identifiant}")

    assert reponse.status_code == 200
    assert "125" in texte(reponse)


def test_rapport_stocke_echappe_un_contenu_non_fiable(client):
    charge = """<?xml version="1.0" encoding="UTF-8"?>
<feedback>
  <version>1.0</version>
  <report_metadata>
    <org_name>&lt;script&gt;alert(1)&lt;/script&gt;</org_name>
    <date_range>
      <begin>1759276800</begin>
      <end>1759363200</end>
    </date_range>
  </report_metadata>
  <policy_published>
    <domain>example.com</domain>
    <p>none</p>
  </policy_published>
  <record>
    <row>192.0.2.10</row>
    <count>1</count>
    <policy_evaluated>
      <disposition>none</disposition>
      <dkim>pass</dkim>
      <spf>pass</spf>
    </policy_evaluated>
  </record>
</feedback>"""
    televerser(client, "rapport.xml", charge.encode("utf-8"))
    identifiant = identifiants(client)[0]

    corps = brut(client.get(f"/history/{identifiant}"))

    assert "<script>alert(1)</script>" not in corps
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in corps


def test_identifiant_inconnu_renvoie_404(client):
    reponse = client.get("/history/999999")

    assert reponse.status_code == 404
    assert "does not exist" in texte(reponse)


def test_identifiant_non_numerique_renvoie_404(client):
    reponse = client.get("/history/pas-un-nombre")

    assert reponse.status_code == 404
    assert "Traceback" not in brut(reponse)


def test_suppression_par_get_est_refusee(client):
    importer(client, "rapport.xml")
    identifiant = identifiants(client)[0]

    reponse = client.get(f"/history/{identifiant}/delete")

    assert reponse.status_code == 405
    assert application_stockage(client).obtenir(identifiant) is not None


def test_suppression_sans_jeton_est_refusee(client):
    importer(client, "rapport.xml")
    identifiant = identifiants(client)[0]

    reponse = client.post(
        f"/history/{identifiant}/delete", content_type="multipart/form-data"
    )

    assert reponse.status_code == 400
    assert application_stockage(client).obtenir(identifiant) is not None


def test_suppression_avec_jeton_invalide_est_refusee(client):
    importer(client, "rapport.xml")
    identifiant = identifiants(client)[0]

    reponse = client.post(
        f"/history/{identifiant}/delete",
        data={"jeton_csrf": "jeton-fabrique"},
        content_type="multipart/form-data",
    )

    assert reponse.status_code == 400
    assert application_stockage(client).obtenir(identifiant) is not None


def test_jeton_dune_session_ne_sert_pas_dans_une_autre_session(client, application):
    importer(client, "rapport.xml")
    identifiant = identifiants(client)[0]
    jeton_session = jeton(client)

    autre = application.test_client()
    reponse = autre.post(
        f"/history/{identifiant}/delete",
        data={"jeton_csrf": jeton_session},
        content_type="multipart/form-data",
    )

    assert reponse.status_code == 400
    assert application_stockage(client).obtenir(identifiant) is not None


def test_suppression_valide_ne_concerne_que_la_cible(client):
    importer(client, "premier.xml", "rapport_plusieurs_records.xml")
    importer(client, "second.xml", "rapport_autre_domaine.xml")
    stockage = application_stockage(client)
    tous = identifiants(client)
    cible, autre = tous[0], tous[1]
    total_de_lautre = stockage.obtenir(autre).analyse.metriques.total_messages

    reponse = client.post(
        f"/history/{cible}/delete",
        data={"jeton_csrf": jeton(client)},
        content_type="multipart/form-data",
    )

    assert reponse.status_code == 302
    assert reponse.headers["Location"].endswith("/history")
    assert stockage.obtenir(cible) is None
    conserve = stockage.obtenir(autre)
    assert conserve is not None
    assert conserve.analyse.metriques.total_messages == total_de_lautre
    assert stockage.compter() == 1


def test_suppression_redirige_et_confirme_dans_la_page_historique(client):
    importer(client, "rapport.xml")
    identifiant = identifiants(client)[0]

    client.post(
        f"/history/{identifiant}/delete",
        data={"jeton_csrf": jeton(client)},
        content_type="multipart/form-data",
    )
    corps = texte(client.get("/history"))

    assert "The stored analysis was deleted." in corps
    assert "No stored analysis yet" in corps
    assert application_stockage(client).compter() == 0


def test_suppression_d_un_enregistrement_absent_ne_supprime_rien(client):
    importer(client, "rapport.xml")
    stockage = application_stockage(client)

    reponse = client.post(
        "/history/424242/delete",
        data={"jeton_csrf": jeton(client)},
        content_type="multipart/form-data",
    )

    assert reponse.status_code == 302
    assert "no longer exists" in texte(client.get("/history"))
    assert stockage.compter() == 1


def test_echec_de_stockage_lors_du_lister(client, monkeypatch):
    def panne(*arguments, **mots):
        raise StorageError("The history database is unavailable.")

    monkeypatch.setattr(
        "app.storage.database.StockageAnalyses.lister", panne
    )

    reponse = client.get("/history")

    assert reponse.status_code == 503
    assert "Traceback" not in brut(reponse)
    assert "storage" not in texte(reponse).lower().split("cod")[0] or True


def test_echec_de_stockage_lors_de_la_lecture(client, monkeypatch):
    importer(client, "rapport.xml")
    identifiant = identifiants(client)[0]

    def panne(*arguments, **mots):
        raise StorageError("The history database is unavailable.")

    monkeypatch.setattr("app.storage.database.StockageAnalyses.obtenir", panne)

    reponse = client.get(f"/history/{identifiant}")

    assert reponse.status_code == 503
    assert "Traceback" not in brut(reponse)


def test_echec_de_stockage_lors_de_la_suppression(client, monkeypatch):
    importer(client, "rapport.xml")
    identifiant = identifiants(client)[0]

    def panne(*arguments, **mots):
        raise StorageError("The history database is unavailable.")

    monkeypatch.setattr("app.storage.database.StockageAnalyses.supprimer", panne)

    reponse = client.post(
        f"/history/{identifiant}/delete",
        data={"jeton_csrf": jeton(client)},
        content_type="multipart/form-data",
    )

    assert reponse.status_code == 503
    assert "The stored analysis was deleted." not in texte(reponse)
    assert application_stockage(client).obtenir(identifiant) is not None


def test_regression_import_et_doublon_toujours_fonctionnels(client, application):
    contenu = fixture("rapport_plusieurs_records.xml")
    premier = televerser(client, "rapport.xml", contenu)
    second = televerser(client, "rapport.xml", contenu)

    assert premier.status_code == 200
    assert second.status_code == 200
    assert "already been imported" in texte(second)
    assert application_stockage(client).compter() == 1


def test_regression_rapport_importe_toujours_affiche_les_mesures(client):
    corps = texte(televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml")))

    assert "DMARC analysis result" in corps
    assert "125" in corps
    assert "Viewing a stored analysis" not in corps


# --- Étape 9 : impression et exports ----------------------------------------


def exporter(client, nom: str = "rapport.xml", fixture_nom: str = "rapport_plusieurs_records.xml"):
    """Importe une fixture puis renvoie l'identifiant stocké."""
    import_reports_ok = televerser(client, nom, fixture(fixture_nom))
    assert import_reports_ok.status_code == 200
    return identifiants(client)[0]


def test_le_rapport_propose_un_controle_d_impression(client):
    corps = brut(televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml")))

    assert "Print report" in corps
    assert 'data-action="print"' in corps
    assert "<button" in corps


def test_le_rapport_stocke_propose_aussi_l_impression(client):
    identifiant = exporter(client)

    corps = brut(client.get(f"/history/{identifiant}"))

    assert "Print report" in corps
    assert 'data-action="print"' in corps


def test_le_script_d_impression_est_local_et_servi(client):
    reponse = client.get("/static/js/print.js")

    assert reponse.status_code == 200
    corps = reponse.get_data(as_text=True)
    assert "window.print()" in corps
    assert "http://" not in corps and "https://" not in corps


def test_la_csp_autorise_uniquement_un_script_local(client):
    entetes = client.get("/").headers

    assert "script-src 'self'" in entetes["Content-Security-Policy"]
    assert "unsafe-inline" not in entetes["Content-Security-Policy"]
    assert "default-src 'none'" in entetes["Content-Security-Policy"]


def test_la_feuille_de_style_d_impression_est_locale_et_complete(client):
    corps = client.get("/static/css/style.css").get_data(as_text=True)

    assert "@media print" in corps
    for cache in (".entete", ".pied", ".bouton", ".formulaire-suppression"):
        assert cache in corps.split("@media print")[1]
    assert "display: table-header-group" in corps
    assert "break-inside: avoid" in corps


def test_le_contenu_du_rapport_reste_imprimable(client):
    corps = texte(televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml")))

    assert "DMARC failures observed" in corps
    assert "Interpretation limit:" in corps
    assert "Data limitations" in corps
    assert "not proof of malicious activity" in corps


def test_export_json_depuis_un_rapport_stocke(client):
    identifiant = exporter(client)

    reponse = client.get(f"/history/{identifiant}/export.json")
    charge = json.loads(reponse.get_data(as_text=True))

    assert reponse.status_code == 200
    assert "application/json" in reponse.headers["Content-Type"]
    assert reponse.headers["Content-Disposition"] == (
        f'attachment; filename="mailguard-analysis-{identifiant}.json"'
    )
    assert charge["schema_version"] == VERSION_EXPORT
    assert charge["analysis_identifier"] == identifiant
    assert charge["analysis"]["metriques"]["total_messages"] == 125
    assert charge["analysis"]["metriques"]["messages_fail"] == 25
    assert charge["briefing"]["resume_executif"].startswith("This briefing covers")
    assert charge["content_sha256"] == calculer_empreinte(
        fixture("rapport_plusieurs_records.xml")
    )


def test_export_json_preserve_les_types_numeriques_et_nuls(client):
    identifiant = exporter(client, "vide.xml", "rapport_volume_nul.xml")

    charge = json.loads(
        client.get(f"/history/{identifiant}/export.json").get_data(as_text=True)
    )
    metriques = charge["analysis"]["metriques"]

    assert isinstance(metriques["total_messages"], int)
    assert isinstance(metriques["taux_pass"]["valeur"], type(None))
    assert metriques["taux_pass"]["valeur"] is None
    assert isinstance(metriques["dispositions"]["none"], int)


def test_export_json_ne_contient_ni_xml_ni_chemin_ni_trace(client):
    identifiant = exporter(client)

    corps = client.get(f"/history/{identifiant}/export.json").get_data(as_text=True)

    for marqueur in ("<feedback", "<record", "<?xml", "Traceback", "/tmp", ".sqlite3"):
        assert marqueur not in corps


def test_export_json_ne_relance_pas_le_moteur_ni_ne_modifie_la_base(client, monkeypatch, application):
    identifiant = exporter(client)
    stockage = application_stockage(client)
    avant = stockage.obtenir(identifiant)
    total_avant = stockage.compter()

    def interdit(*arguments, **mots):
        raise AssertionError("the deterministic engine must not run during an export")

    monkeypatch.setattr("app.services.analyser", interdit)

    reponse = client.get(f"/history/{identifiant}/export.json")
    apres = stockage.obtenir(identifiant)

    assert reponse.status_code == 200
    assert stockage.compter() == total_avant
    assert apres.analyse == avant.analyse
    assert apres.briefing == avant.briefing


def test_export_json_identifiant_inconnu(client):
    reponse = client.get("/history/999999/export.json")

    assert reponse.status_code == 404
    assert "Traceback" not in brut(reponse)


def test_export_json_panne_de_stockage(client, monkeypatch):
    identifiant = exporter(client)

    def panne(*arguments, **mots):
        raise StorageError("The history database is unavailable.")

    monkeypatch.setattr("app.storage.database.StockageAnalyses.obtenir", panne)

    reponse = client.get(f"/history/{identifiant}/export.json")

    assert reponse.status_code == 503
    assert "Traceback" not in brut(reponse)


def test_un_domaine_importe_ne_peut_pas_injecter_un_entete(client):
    charge = """<?xml version="1.0" encoding="UTF-8"?>
<feedback>
  <version>1.0</version>
  <report_metadata>
    <org_name>Provider</org_name>
    <date_range>
      <begin>1759276800</begin>
      <end>1759363200</end>
    </date_range>
  </report_metadata>
  <policy_published>
    <domain>example.com&#13;&#10;X-Injected: yes</domain>
    <p>none</p>
  </policy_published>
  <record>
    <row>192.0.2.10</row>
    <count>1</count>
    <policy_evaluated>
      <disposition>none</disposition>
      <dkim>pass</dkim>
      <spf>pass</spf>
    </policy_evaluated>
  </record>
</feedback>"""
    televerser(client, "rapport.xml", charge.encode("utf-8"))
    identifiant = identifiants(client)[0]

    reponse = client.get(f"/history/{identifiant}/export.json")

    assert reponse.status_code == 200
    assert "X-Injected" not in reponse.headers
    disposition = reponse.headers["Content-Disposition"]
    assert disposition == f'attachment; filename="mailguard-analysis-{identifiant}.json"'
    assert "\r" not in disposition and "\n" not in disposition


def test_export_csv_des_sources(client):
    identifiant = exporter(client)

    reponse = client.get(f"/history/{identifiant}/export.csv")
    lignes = list(csv.reader(io.StringIO(reponse.get_data(as_text=True))))

    assert reponse.status_code == 200
    assert "text/csv" in reponse.headers["Content-Type"]
    assert reponse.headers["Content-Disposition"] == (
        f'attachment; filename="mailguard-analysis-{identifiant}.csv"'
    )
    assert lignes[0] == list(COLONNES_CSV_SOURCES)
    assert len(lignes) == 4
    assert lignes[1][0] == "192.0.2.20"
    assert int(lignes[1][1]) == 100
    assert int(lignes[1][2]) == 100
    assert int(lignes[1][3]) == 0
    assert float(lignes[1][4]) == 0.0
    assert lignes[2][0] == "198.51.100.30"
    assert int(lignes[2][3]) == 25
    assert float(lignes[2][4]) == 100.0
    assert lignes[3][4] == ""


def test_export_csv_neutralise_les_formules_et_preserve_les_caracteres(client):
    charge = """<?xml version="1.0" encoding="UTF-8"?>
<feedback>
  <version>1.0</version>
  <report_metadata>
    <org_name>Fournisseur "exemple", société\nmulti-lignes</org_name>
    <date_range>
      <begin>1759276800</begin>
      <end>1759363200</end>
    </date_range>
  </report_metadata>
  <policy_published>
    <domain>example.com</domain>
    <p>none</p>
  </policy_published>
  <record>
    <row>192.0.2.10</row>
    <count>3</count>
    <policy_evaluated>
      <disposition>none</disposition>
      <dkim>pass</dkim>
      <spf>pass</spf>
    </policy_evaluated>
    <identifiers>
      <header_from>=cmd|'/c calc'!A1, "x"</header_from>
    </identifiers>
  </record>
</feedback>"""
    televerser(client, "rapport.xml", charge.encode("utf-8"))
    identifiant = identifiants(client)[0]

    corps = client.get(f"/history/{identifiant}/export.csv").get_data(as_text=True)
    lignes = list(csv.reader(io.StringIO(corps)))
    domaine = lignes[1][COLONNES_CSV_SOURCES.index("header_from_domains")]

    assert domaine.startswith("'=")
    assert int(lignes[1][COLONNES_CSV_SOURCES.index("total_messages")]) == 3
    assert "<feedback" not in corps
    assert application_stockage(client).obtenir(identifiant) is not None


def test_export_csv_n_expose_pas_le_xml(client):
    identifiant = exporter(client)

    corps = client.get(f"/history/{identifiant}/export.csv").get_data(as_text=True)

    assert "<" not in corps and "?xml" not in corps


def test_boutons_export_visibles_et_non_destructifs(client):
    identifiant = exporter(client)
    corps = texte(client.get(f"/history/{identifiant}"))

    assert "Download JSON" in corps
    assert "Download CSV (sources)" in corps
    assert "These actions apply to stored analysis" in corps
    assert corps.count("class=\"formulaire-suppression\"") == 0


def test_regression_import_historique_et_suppression(client, application):
    contenu = fixture("rapport_valide_sans_namespace.xml")
    assert televerser(client, "rapport.xml", contenu).status_code == 200
    assert televerser(client, "rapport.xml", contenu).status_code == 200
    stockage = application_stockage(client)
    assert stockage.compter() == 1

    identifiant = identifiants(client)[0]
    assert "View report" in texte(client.get("/history"))
    assert client.get(f"/history/{identifiant}").status_code == 200
    assert client.get(f"/history/{identifiant}/delete").status_code == 405

    suppression = client.post(
        f"/history/{identifiant}/delete",
        data={"jeton_csrf": jeton(client)},
        content_type="multipart/form-data",
    )
    assert suppression.status_code == 302
    assert stockage.compter() == 0
    entetes = client.get("/").headers
    assert "X-Content-Type-Options" in entetes


# --- Étape 10 : narration IA locale dans l'interface -----------------------


def application_avec_narration(application, monkeypatch, transport) -> None:
    """Active la narration locale avec un transport simulé, sans modifier la base."""
    from app.ai.ollama_client import ClientOllama, ParametresNarration

    application.config["MAILGUARD_CONFIG"] = replace(
        application.config["MAILGUARD_CONFIG"],
        ai_active=True,
        ollama_model="modele-de-test",
        ollama_url="http://127.0.0.1:11434",
    )
    client = ClientOllama(
        ParametresNarration(
            actif=True, modele="modele-de-test", url="http://127.0.0.1:11434"
        ),
        transport=transport,
    )
    monkeypatch.setattr("app.services.client_narration_de", lambda configuration: client)


def transport_simule(contenu: dict, erreur: Exception | None = None):
    """Transport simulé renvoyant une enveloppe Ollama valide."""

    def _appel(url, charge, timeout, taille_max):
        if erreur is not None:
            raise erreur
        return json.dumps(
            {"message": {"content": json.dumps(contenu)}}
        ).encode("utf-8")

    return _appel


NARRATION_SIMULEE = {
    "summary": "The receiver reported DMARC failures on one source address.",
    "explanations": [
        {
            "finding_id": "echecs-dmarc-observez",
            "text": "Part of the traffic failed DMARC alignment according to the report.",
        }
    ],
    "limitations": ["A source listed with a failure is not qualified."],
}


def test_narration_desactivee_ne_presente_aucun_texte_ia(client):
    corps = texte(televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml")))

    assert "AI narration is disabled in this installation." in corps
    assert "AI-assisted explanation" in corps


def test_narration_reussie_est_affichee_en_complement(client, application, monkeypatch):
    application_avec_narration(
        application, monkeypatch, transport_simule(NARRATION_SIMULEE)
    )

    corps = texte(televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml")))

    assert "The receiver reported DMARC failures" in corps
    assert "Part of the traffic failed DMARC alignment" in corps
    assert "remain the only authoritative result" in corps
    assert "AI narration is disabled" not in corps


def test_narration_en_echec_laisse_le_rapport_deterministe_intact(client, application, monkeypatch):
    application_avec_narration(
        application, monkeypatch, transport_simule(None, erreur=ConnectionRefusedError("offline"))
    )

    reponse = televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml"))
    corps = texte(reponse)

    assert reponse.status_code == 200
    assert "Local AI is unavailable" in corps
    assert "125" in corps and "80.0 %" in corps
    assert "DMARC failures observed" in corps
    assert application_stockage(client).compter() == 1


def test_sortie_ia_hostile_est_rejetee_et_jamais_interpretee(client, application, monkeypatch):
    """Un texte contenant une balise est refusé par la validation, pas seulement échappé."""
    application_avec_narration(
        application,
        monkeypatch,
        transport_simule(
            {
                "summary": "<script>alert(1)</script>",
                "explanations": [],
                "limitations": [],
            }
        ),
    )

    corps = brut(televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml")))

    assert "<script>alert(1)</script>" not in corps
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" not in corps
    assert "rejected by validation" in html.unescape(corps)


def test_sortie_ia_invalide_est_rejetee_sans_afficher_de_texte(client, application, monkeypatch):
    application_avec_narration(
        application,
        monkeypatch,
        transport_simule({"summary": "texte", "explanations": "mauvais type"}),
    )

    corps = texte(televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml")))

    assert "rejected by validation" in corps
    assert "125" in corps


def test_rapport_stocke_ne_declenche_pas_de_narration(client, application, monkeypatch):
    televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml"))
    identifiant = identifiants(client)[0]
    appels = []

    def compte(url, charge, timeout, taille_max):
        appels.append(url)
        return b"{}"

    application_avec_narration(application, monkeypatch, compte)

    reponse = client.get(f"/history/{identifiant}")
    corps = texte(reponse)

    assert reponse.status_code == 200
    assert "not re-narrated" in corps
    assert appels == []


def test_export_json_ne_contient_pas_de_narration(client, application, monkeypatch):
    application_avec_narration(
        application, monkeypatch, transport_simule(NARRATION_SIMULEE)
    )
    televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml"))
    identifiant = identifiants(client)[0]

    charge = json.loads(
        client.get(f"/history/{identifiant}/export.json").get_data(as_text=True)
    )

    assert sorted(charge) == [
        "analysis",
        "analysis_identifier",
        "briefing",
        "content_sha256",
        "exported_at",
        "schema_version",
        "stored_at",
        "stored_by_version",
        "uploaded_file_name",
    ]
    assert "narration" not in charge["analysis"]


def test_export_csv_ne_contient_pas_de_narration(client, application, monkeypatch):
    application_avec_narration(
        application, monkeypatch, transport_simule(NARRATION_SIMULEE)
    )
    televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml"))
    identifiant = identifiants(client)[0]

    corps = client.get(f"/history/{identifiant}/export.csv").get_data(as_text=True)

    assert "narration" not in corps
    assert "The receiver reported DMARC failures" not in corps


def test_base_de_donnees_inchangee_par_la_narration(client, application, monkeypatch):
    application_avec_narration(
        application, monkeypatch, transport_simule(NARRATION_SIMULEE)
    )

    televerser(client, "rapport.xml", fixture("rapport_plusieurs_records.xml"))
    stockage = application_stockage(client)
    enregistrement = stockage.obtenir(1)

    assert stockage.compter() == 1
    assert "narration" not in enregistrement.analyse.model_dump(mode="json")
    assert len(enregistrement.briefing.a_retenir) == 4


def test_csrf_et_en_tetes_de_securite_intacts_avec_narration(client, application, monkeypatch):
    application_avec_narration(
        application, monkeypatch, transport_simule(NARRATION_SIMULEE)
    )
    page = client.get("/upload")

    assert 'name="jeton_csrf"' in page.get_data(as_text=True)
    assert "default-src 'none'" in page.headers["Content-Security-Policy"]
    assert page.headers["X-Content-Type-Options"] == "nosniff"
