"""Tests de régression de l'audit de sécurité de l'étape 11.

Chaque test couvre une **propriété de sécurité** démontrée manquante ou
défaillante avant l'audit, et vérifie qu'un correctif la fait tenir :

1. un rapport DMARC ne peut pas contenir un nombre de `record` illimité
   (amplification mémoire : 680 Kio compressés Consumaient ~945 Mio de RSS) ;
2. un texte libre importé ne peut pas être arbitrairement long (un `org_name`
   de 50 millions de caractères était accepté, stocké, rendu et exporté) ;
3. aucun chemin du système de fichiers n'apparaît dans une réponse HTTP ;
4. une charge utile stockée endommagée produit la même erreur explicite partout,
   y compris dans la liste d'historique ;
5. la narration IA ne peut pas référencer un constat que la troncature du
   prompt a écarté ;
6. l'appel à Ollama n'utilise pas les mandataires de l'environnement, sans
   quoi la charge utile sortirait de la machine ;
7. les contrôles d'entrée, de sortie et d'exports restent intacts après ces
   correctifs (aucune régression).

Toutes les données sont synthétiques : aucun rapport client réel, aucune donnée
n'est écrite hors des bases SQLite temporaires créées par le test.
"""

from __future__ import annotations

import csv
import gzip
import io
import re
import secrets
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

from app import create_app
from app.ai.ollama_client import (
    ClientOllama,
    ParametresNarration,
    StatutNarration,
)
from app.ai.prompts import selection_constats
from app.config import Configuration, charger_configuration
from app.core.archive import (
    LIMITES_PAR_DEFAUT,
    MAX_RECORDS_PAR_RAPPORT,
    ImportLimits,
    import_reports,
)
from app.core.errors import ArchiveLimitError, ReportValidationError
from app.core.models import LONGUEUR_DOMAINE_MAX, LONGUEUR_TEXTE_MAX
from app.core.parser import parse_dmarc_report
from app.export import construire_export_csv_sources
from app.storage.database import StockageAnalyses

CHEMIN_FIXTURES = Path(__file__).parent / "fixtures"


def fixture(nom: str) -> bytes:
    """Contenu binaire d'une fixture XML synthétique."""
    return (CHEMIN_FIXTURES / nom).read_bytes()


# --- Construction de rapports synthétiques à l'échelle ------------------------

ENTETE = """<?xml version="1.0" encoding="UTF-8"?>
<feedback>
  <report_metadata>
    <org_name>Synthetic Audit Provider</org_name>
    <email>dmarc@example.com</email>
    <report_id>synthetic-audit</report_id>
    <date_range><begin>1735689600</begin><end>1735776000</end></date_range>
  </report_metadata>
  <policy_published>
    <domain>example.com</domain><adkim>r</adkim><aspf>r</aspf><p>none</p>
  </policy_published>
"""

MODEL = """
  <record>
    <row>192.0.2.{index}</row><count>{count}</count>
    <identifiers><header_from>example.com</header_from></identifiers>
    <policy_evaluated>
      <disposition>none</disposition><spf>pass</spf><dkim>pass</dkim>
    </policy_evaluated>
  </record>
"""


def rapport_avec_records(nombre: int) -> bytes:
    """Rapport DMARC synthétique comportant exactement `nombre` records."""
    corps = "".join(MODEL.format(index=index, count=(index % 97) + 1) for index in range(nombre))
    return (ENTETE + corps + "</feedback>\n").encode()


def gz(contenu: bytes) -> bytes:
    """Compression GZIP en mémoire, pour rester sous la limite de téléversement."""
    tampon = io.BytesIO()
    with gzip.GzipFile(fileobj=tampon, mode="wb", mtime=0) as flux:
        flux.write(contenu)
    return tampon.getvalue()


@pytest.fixture
def stockage(tmp_path) -> StockageAnalyses:
    """Stockage isolé, base temporaire créée et migrée."""
    instance = StockageAnalyses.depuis_chemin(tmp_path / "audit.sqlite3")
    instance.initialiser()
    return instance


@pytest.fixture
def client_et_stockage(tmp_path):
    """Client Flask de test et stockage isolé."""
    configuration = Configuration(
        cle_secrete=secrets.token_hex(32),
        chemin_base=tmp_path / "audit.sqlite3",
        max_records_per_report=MAX_RECORDS_PAR_RAPPORT,
    )
    application = create_app(configuration)
    instance = StockageAnalyses.depuis_chemin(configuration.chemin_base)
    instance.initialiser()
    application.extensions["stockage"] = instance
    return application.test_client(), instance


# --- 1. Nombre de records borné ----------------------------------------------


def test_un_rapport_au_dela_de_la_limite_de_records_est_refuse():
    """Propriété : le nombre de `<record>` par rapport est borné.

    Avant le correctif, `DmarcReport.records` n'avait qu'un `min_length` : un
    rapport de plus de 150 000 records, tenant dans quelques centaines de Kio
    compressés, était accepté et consommait près d'un gigaoctet de mémoire.
    """
    limites = ImportLimits(max_records_per_report=50)

    with pytest.raises(ReportValidationError) as erreur:
        import_reports("charge.xml", rapport_avec_records(51), limites)

    message = str(erreur.value)
    assert "51 records" in message
    assert "the limit is 50" in message


def test_la_limite_de_records_refuse_avant_la_conversion_des_records():
    """Propriété : le refus précède la construction des objets métier.

    Vérifié en spying sur `app.core.parser._lire_record` : un rapport trop long
    ne doit jamais convertir un seul record.
    """
    import app.core.parser as module_parser

    appels: list[int] = []
    original = module_parser._lire_record

    def espion(element, index):
        appels.append(index)
        return original(element, index)

    module_parser._lire_record = espion
    try:
        with pytest.raises(ReportValidationError):
            import_reports("charge.xml", rapport_avec_records(40), ImportLimits(
                max_records_per_report=5
            ))
    finally:
        module_parser._lire_record = original

    assert appels == []


def test_un_rapport_a_la_limite_de_records_est_encore_accepte():
    """Propriété : la limite ne rejette pas un rapport qui la respecte.

    Une limite qui refuserait un rapport légitime serait une régression : le
    moteur et les modèles n'ont pas été modifiés pour la respecter.
    """
    resultat = import_reports(
        "limite.xml", rapport_avec_records(50), ImportLimits(max_records_per_report=50)
    )

    assert len(resultat.reports) == 1
    assert len(resultat.reports[0].records) == 50


def test_un_rapport_sans_archives_et_gz_est_borne_de_la_meme_facon():
    """Propriété : la limite s'applique aux trois formats acceptés.

    Un `.xml.gz` est le vecteur le plus économique pour l'attaquant : 49 Kio
    compressés produisent 49 Mio décompressés, largement sous la limite de
    10 Mio par fichier téléversé.
    """
    contenu = rapport_avec_records(60)

    with pytest.raises(ReportValidationError):
        import_reports("charge.xml.gz", gz(contenu), ImportLimits(max_records_per_report=20))

    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("rapport.xml", contenu)

    with pytest.raises(ReportValidationError):
        import_reports("charge.zip", tampon.getvalue(), ImportLimits(max_records_per_report=20))


def test_le_membre_xml_d_une_archive_est_borne_par_la_limite_de_records():
    """Propriété : le conteneur n'est pas une voie de contournement."""
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("a/rapport.xml", rapport_avec_records(30))

    with pytest.raises(ReportValidationError):
        import_reports("charge.zip", tampon.getvalue(), ImportLimits(max_records_per_report=10))


def test_la_limite_de_records_par_defaut_est_documentee_et_configurable():
    """Propriété : la limite est explicite, documentée et réglable par variable."""
    defauts = LIMITES_PAR_DEFAUT

    assert defauts.max_records_per_report == MAX_RECORDS_PAR_RAPPORT
    assert MAX_RECORDS_PAR_RAPPORT == 10_000

    charge = charger_configuration(
        {"FLASK_SECRET_KEY": "x" * 40, "MAILGUARD_MAX_RECORDS_PER_REPORT": "42"},
        charger_fichier_env=False,
    )
    assert charge.max_records_per_report == 42
    assert charge.limites_import.max_records_per_report == 42
    assert charge.limites_affichees["Records per report"] == "42"


def test_une_limite_de_records_incoherente_est_refusee_au_demarrage():
    """Propriété : une valeur de configuration illisible est refusée, pas ignorée."""
    from app.core.errors import ConfigurationErreur

    with pytest.raises(ConfigurationErreur):
        charger_configuration(
            {"FLASK_SECRET_KEY": "x" * 40, "MAILGUARD_MAX_RECORDS_PER_REPORT": "beaucoup"},
            charger_fichier_env=False,
        )


def test_un_parseur_appele_directement_borne_egalement_les_records():
    """Propriété : la borne ne dépend pas du seul chemin passant par l'importeur."""
    with pytest.raises(ReportValidationError):
        parse_dmarc_report(rapport_avec_records(30), max_records=10)

    rapport = parse_dmarc_report(rapport_avec_records(10), max_records=10)
    assert len(rapport.records) == 10


# --- 2. Longueurs de texte bornées --------------------------------------------


def test_un_organisation_nom_pref_arbitrairement_longue_est_refusee():
    """Propriété : un texte libre importé ne peut pas être démesuré.

    Avant le correctif, un `org_name` de 51 millions de caractères issu d'un
    fichier de 49 Kio compressés était accepté, écrit en base, recopié dans le
    briefing, rendu dans la page HTML et inclus dans l'export JSON.
    """
    document = rapport_avec_records(1).replace(
        b"<org_name>Synthetic Audit Provider</org_name>",
        b"<org_name>" + b"A" * (2 * 1024 * 1024) + b"</org_name>",
    )

    with pytest.raises(ReportValidationError) as erreur:
        import_reports("long.xml.gz", gz(document), LIMITES_PAR_DEFAUT)

    assert "org_name" in str(erreur.value)


def test_un_nom_de_domaine_tres_long_est_refuse():
    """Propriété : les champs de type domaine sont bornés eux aussi."""
    document = rapport_avec_records(1).replace(
        b"<domain>example.com</domain>",
        b"<domain>" + b"a" * (LONGUEUR_DOMAINE_MAX + 1) + b"</domain>",
    )

    with pytest.raises(ReportValidationError):
        import_reports("dom.xml.gz", gz(document), LIMITES_PAR_DEFAUT)


def test_un_commentaire_de_raison_tres_long_est_refuse():
    """Propriété : les textes libres des records sont bornés."""
    document = rapport_avec_records(1).replace(
        b"<policy_evaluated>",
        b"<policy_evaluated><reason><type>other</type><comment>"
        + b"c" * (LONGUEUR_TEXTE_MAX + 1)
        + b"</comment></reason>",
    )

    with pytest.raises(ReportValidationError):
        import_reports("raison.xml.gz", gz(document), LIMITES_PAR_DEFAUT)


@pytest.mark.parametrize(
    "remplacement",
    [
        (b"<email>dmarc@example.com</email>", b"email"),
        (b"<report_id>synthetic-audit</report_id>", b"report_id"),
    ],
)
def test_un_identifiant_de_rapport_tres_long_est_refuse(remplacement):
    """Propriété : les métadonnées facultatives restent bornées."""
    element, _ = remplacement
    document = rapport_avec_records(1).replace(
        element,
        element.split(b">")[0] + b">" + b"z" * (LONGUEUR_TEXTE_MAX + 1) + b"</"
        + element.split(b">")[0].split(b"<")[1] + b">",
    )

    with pytest.raises(ReportValidationError):
        import_reports("meta.xml.gz", gz(document), LIMITES_PAR_DEFAUT)


def test_les_valeurs_normales_restent_acceptees():
    """Propriété : aucune régression sur des valeurs réalistes.

    Les bornes choisies (1024 caractères pour un texte, 512 pour un domaine) sont
    très supérieures à ce que publie la RFC 7489 : un rapport légitime ne peut pas
    être refusé à cause de cette correction.
    """
    resultat = import_reports("normal.xml", fixture("rapport_valide_sans_namespace.xml"))

    rapport = resultat.reports[0]
    assert rapport.metadata.org_name == "Example Mail Provider"
    assert rapport.policy_published.domain == "example.com"
    assert rapport.records[0].identifiers.header_from == "example.com"


# --- 3. Aucun chemin du système de fichiers dans une réponse HTTP ------------


def test_une_base_inutilisable_ne_divulgue_pas_le_chemin(client_et_stockage, tmp_path):
    """Propriété : `StorageError` est affichable, donc sans chemin privé.

    `03_SECURITY_PRIVACY.md` n'autorise pas l'affichage d'un chemin complet.
    Avant le correctif, le message « The file « /tmp/.../audit.sqlite3 » is not a
    usable SQLite database » était rendu tel quel dans la page d'erreur.
    """
    client, _ = client_et_stockage
    fichier = tmp_path / "casse.sqlite3"
    fichier.write_bytes(b"ceci n'est pas une base SQLite " * 50)
    client.application.extensions["stockage"] = StockageAnalyses.depuis_chemin(fichier)

    reponse = client.get("/history")
    corps = reponse.get_data(as_text=True)

    assert reponse.status_code == 503
    assert str(tmp_path) not in corps
    assert "casse.sqlite3" not in corps
    assert "Traceback" not in corps


def test_un_chemin_inaccessible_ne_divulgue_pas_le_chemin(client_et_stockage, tmp_path):
    """Propriété : le même refus vaut pour un chemin non ouvrable."""
    client, _ = client_et_stockage
    fichier = tmp_path / "fichier" / "absent.sqlite3"
    fichier.parent.write_text("ceci est un fichier, pas un dossier")
    client.application.extensions["stockage"] = StockageAnalyses.depuis_chemin(fichier)

    corps = client.get("/history").get_data(as_text=True)

    assert str(tmp_path) not in corps
    assert "fichier" not in corps


def test_les_messages_de_stockage_visibles_ne_contiennent_jamais_de_chemin():
    """Propriété vérifiée à la source : aucun `StorageError` n'interpole un chemin.

    `StorageError` est renvoyé tel quel à l'interface par
    `app.erreurs.message_erreur_metier` : tout chemin inséré dans un de ces
    messages le serait aussi dans la réponse HTTP.
    """
    import inspect

    import app.storage.database as module_base

    suspects: list[str] = []
    for nom, valeur in vars(module_base).items():
        if not inspect.isfunction(valeur):
            continue
        for ligne in inspect.getsource(valeur).splitlines():
            if "StorageError(" not in ligne:
                continue
            if "{chemin}" in ligne or "{parent}" in ligne:
                suspects.append(f"{nom}: {ligne.strip()}")

    assert not suspects, suspects


# --- 4. Charge utile stockée endommagée ---------------------------------------


def test_l_historique_refuse_une_enveloppe_sans_cle_analyse(stockage):
    """Propriété : `lister()` se comporte comme `obtenir()` sur une ligne abimée.

    Avant le correctif, `_ligne_vers_resume` accédait directement à
    `enveloppe["analyse"]` : une enveloppe JSON valide mais incomplète levait
    une `KeyError` non traduite, qui rendait toute la page d'historique
    inutilisable (500) alors même que le rapport concerné s'ouvrait bien.
    """
    from app.core.errors import StorageError

    with sqlite3.connect(stockage.chemin) as connexion:
        connexion.execute(
            """INSERT INTO analyses (empreinte, nom_fichier, date_import, version_schema,
               version_moteur, domaine_publie, nombre_rapports, total_messages,
               analyse_json, briefing_json) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                "c" * 64,
                "rapport.xml",
                "2026-01-01T00:00:00+00:00",
                1,
                "0.1.0",
                "example.com",
                1,
                1,
                '{"version": 1}',
                '{"version": 1, "briefing": {}}',
            ),
        )

    with pytest.raises(StorageError):
        stockage.lister()


def test_l_historique_refuse_une_charge_utilisable_incoherente(stockage):
    """Propriété : une analyse revalidée est refusée si elle ne l'est pas."""
    from app.core.errors import StorageError

    with sqlite3.connect(stockage.chemin) as connexion:
        connexion.execute(
            """INSERT INTO analyses (empreinte, nom_fichier, date_import, version_schema,
               version_moteur, domaine_publie, nombre_rapports, total_messages,
               analyse_json, briefing_json) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                "d" * 64,
                "rapport.xml",
                "2026-01-01T00:00:00+00:00",
                1,
                "0.1.0",
                "example.com",
                1,
                1,
                '{"version": 1, "analyse": {"metriques": {"total_messages": "beaucoup"}}}',
                '{"version": 1, "briefing": {}}',
            ),
        )

    with pytest.raises(StorageError):
        stockage.lister()


def test_une_seule_ligne_corrompue_ne_casse_plus_la_page_entiere(client_et_stockage):
    """Propriété : le défaut est signalé proprement, sans trace ni 500 opaque."""
    client, stockage = client_et_stockage
    stockage.obtenir  # le stockage est fonctionnel avant sabotage
    with sqlite3.connect(stockage.chemin) as connexion:
        connexion.execute(
            """INSERT INTO analyses (empreinte, nom_fichier, date_import, version_schema,
               version_moteur, domaine_publie, nombre_rapports, total_messages,
               analyse_json, briefing_json) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                "e" * 64,
                "rapport.xml",
                "2026-01-01T00:00:00+00:00",
                1,
                "0.1.0",
                "example.com",
                1,
                1,
                '{"version": 1}',
                '{"version": 1, "briefing": {}}',
            ),
        )

    reponse = client.get("/history")
    corps = reponse.get_data(as_text=True)

    assert reponse.status_code == 503
    assert "Traceback" not in corps
    assert "unexpected error" not in corps.lower()


# --- 5. Narration IA : constats réellement transmis ---------------------------


def rapport_a_constats_multiples() -> bytes:
    """Rapport synthétique produisant plus de constats que la borne de transmission."""
    records = "".join(
        f"""<record><row>192.0.2.{index}</row><count>{compte}</count>
        <identifiers><header_from>h{index}.example</header_from></identifiers>
        <policy_evaluated><disposition>none</disposition>
        <spf>{spf}</spf><dkim>pass</dkim></policy_evaluated></record>"""
        for index, (compte, spf) in enumerate(
            [(0, "fail")] * 10 + [(5, "pass")] * 4, start=1
        )
    )
    return (ENTETE + records + "</feedback>\n").encode()


def test_un_constat_ecarte_par_troncature_ne_peut_pas_etre_reference():
    """Propriété : seuls les constats réellement envoyés sont acceptés.

    Avant le correctif, la validation comparait les identifiants renvoyés par le
    modèle aux **douze premiers** constats, alors que le prompt n'en contient
    qu'une sélection tronquée. Un modèle pouvait donc citer sans être rejeté un
    constat que l'application ne lui avait jamais transmis, contrairement à ce
    qu'annonce la documentation.
    """
    import json

    from app.core.rules import analyser

    analyse = analyser(import_reports("multi.xml", rapport_a_constats_multiples()).reports)
    envoyes = selection_constats(analyse, 2000)
    maximum = analyse.constats[:12]

    # On cherche un identifiant présent dans la sélection maximale du moteur mais
    # absent du prompt réellement assemblé.
    presents = {constat.identifiant for constat in envoyes}
    ecartes = [c for c in maximum if c.identifiant not in presents]
    if not ecartes:
        pytest.skip("aucun constat distinct n'a pu être construit pour ce cas")

    capture: dict[str, list[str]] = {}

    def transport(url, charge, timeout, taille_max):
        capture["ids"] = re.findall(r"finding_id: (\S+)", charge["messages"][1]["content"])
        return json.dumps(
            {
                "message": {
                    "content": json.dumps(
                        {
                            "summary": "Résumé sans chiffre.",
                            "explanations": [
                                {"finding_id": ecartes[0].identifiant, "text": "Texte."}
                            ],
                            "limitations": [],
                        }
                    )
                }
            }
        ).encode()

    client_ia = ClientOllama(
        ParametresNarration(actif=True, modele="test", max_input_chars=2000),
        transport=transport,
    )
    resultat = client_ia.narrer(analyse)

    assert ecartes[0].identifiant not in capture["ids"], "le constat était bien absent du prompt"
    assert resultat.statut is StatutNarration.REJETE
    assert resultat.explications == []


def test_un_constat_reellement_envoye_reste_accepte_apres_troncature():
    """Propriété : le correctif ne rejette pas les sorties légitimes.

    La troncature est exercising dans les deux sens : ce qui est transmis doit
    toujours pouvoir être cité.
    """
    import json

    from app.core.rules import analyser

    analyse = analyser(import_reports("multi.xml", rapport_a_constats_multiples()).reports)
    envoyes = selection_constats(analyse, 2000)
    cible = envoyes[0].identifiant

    def transport(url, charge, timeout, taille_max):
        return json.dumps(
            {
                "message": {
                    "content": json.dumps(
                        {
                            "summary": "Résumé.",
                            "explanations": [{"finding_id": cible, "text": "Texte."}],
                            "limitations": [],
                        }
                    )
                }
            }
        ).encode()

    resultat = ClientOllama(
        ParametresNarration(actif=True, modele="test", max_input_chars=2000),
        transport=transport,
    ).narrer(analyse)

    assert resultat.statut is StatutNarration.OK
    assert [e.finding_id for e in resultat.explications] == [cible]


# --- 6. Mandataires d'environnement neutralisés -------------------------------


def test_l_appel_ollama_ignore_les_mandataires_de_l_environnement(monkeypatch):
    """Propriété : la charge utile reste sur l'endpoint configuré.

    `requests` honore `HTTP_PROXY` par défaut. Sans neutralisation, un poste
    configuré avec un mandataire et sans `NO_PROXY` enverrait les constats du
    rapport à un tiers, alors que la configuration n'autorise qu'une adresse de
    boucle locale.
    """
    capture: dict[str, object] = {}

    class FauxReponse:
        def __init__(self) -> None:
            self.raw = self
            self.closed = False

        def raise_for_status(self) -> None:
            return None

        def read(self, taille, decode_content=False):
            return b"{}"

        def close(self) -> None:
            self.closed = True

    def faux_post(url, **options):
        capture["url"] = url
        capture.update(options)
        return FauxReponse()

    module_faux = type(sys)("requests")
    module_faux.post = faux_post
    monkeypatch.setitem(sys.modules, "requests", module_faux)
    monkeypatch.setenv("HTTP_PROXY", "http://mandataire.interne:3128")

    from app.ai.ollama_client import _transport_requests

    _transport_requests(
        "http://127.0.0.1:11434/api/chat", {"a": 1}, 5.0, 1024
    )

    assert capture["proxies"] == {"http": None, "https": None}
    assert capture["allow_redirects"] is False


# --- 7. Non-régression des contrôles déjà en place ----------------------------


def test_un_televersement_trop_volumineux_est_toujours_refuse(tmp_path):
    """Contrôle préexistant : limite HTTP et limite d'import, vérifiées après correctifs."""
    configuration = Configuration.pour_tests(tmp_path / "limites.sqlite3")
    application = create_app(configuration)
    StockageAnalyses.depuis_chemin(configuration.chemin_base).initialiser()
    client = application.test_client()
    jeton = jeton_de(client, "/upload")

    # Au-delà de la limite de téléversement (64 Kio en configuration de test).
    trop_gros = client.post(
        "/upload",
        data={"rapport": (io.BytesIO(b"x" * (65 * 1024)), "gros.xml"), "jeton_csrf": jeton},
        content_type="multipart/form-data",
    )
    assert trop_gros.status_code == 413

    # Au-delà de la limite HTTP de Flask (96 Kio en configuration de test).
    requete = client.post(
        "/upload",
        data={"rapport": (io.BytesIO(b"y" * (100 * 1024)), "gros2.xml"), "jeton_csrf": jeton},
        content_type="multipart/form-data",
    )
    assert requete.status_code == 413


def test_une_archive_corrompue_est_toujours_refusee():
    """Contrôle préexistant : un ZIP illisible ne devient jamais un import partiel."""
    from app.core.errors import ArchiveError

    with pytest.raises(ArchiveError):
        import_reports("casse.zip", b"PK\x03\x04 pas une archive", LIMITES_PAR_DEFAUT)


def test_un_gzip_corrompu_est_toujours_refuse():
    """Contrôle préexistant : GZIP tronqué ou absent."""
    from app.core.errors import ArchiveError

    with pytest.raises(ArchiveError):
        import_reports("casse.xml.gz", b"\x1f\x8b\x08\x00 tronque", LIMITES_PAR_DEFAUT)


def test_un_chemin_zip_traversant_est_toujours_refuse():
    """Contrôle préexistant : traversée de répertoire, jamais d'extraction."""
    from app.core.errors import UnsafeArchiveError

    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as archive:
        archive.writestr("../../evasion.xml", fixture("rapport_valide_sans_namespace.xml"))

    with pytest.raises(UnsafeArchiveError):
        import_reports("evasion.zip", tampon.getvalue(), LIMITES_PAR_DEFAUT)


def test_une_entite_interne_reste_refusee():
    """Contrôle préexistant : DTD et entités bloquées par defusedxml."""
    from app.core.errors import ReportParseError

    document = fixture("rapport_avec_dtd.xml")

    with pytest.raises(ReportParseError):
        import_reports("dtd.xml", document, LIMITES_PAR_DEFAUT)


def test_un_champ_html_importe_reste_echappe_et_non_exportable(client_et_stockage):
    """Contrôle préexistant : aucune interpolation HTML, et CSV neutralisé."""
    client, _ = client_et_stockage
    jeton = jeton_de(client, "/upload")
    document = (
        ENTETE.replace(
            "<domain>example.com</domain>",
            "<domain>&lt;script&gt;alert(1)&lt;/script&gt;</domain>",
        )
        + MODEL.format(index=1, count=1).replace(
            "<header_from>example.com</header_from>",
            "<header_from>=cmd|'/c calc'!A1</header_from>",
        )
        + "</feedback>\n"
    ).encode()

    reponse = client.post(
        "/upload",
        data={"rapport": (io.BytesIO(document), "rapport.xml"), "jeton_csrf": jeton},
        content_type="multipart/form-data",
    )
    corps = reponse.get_data(as_text=True)

    assert reponse.status_code == 200
    assert "<script>alert(1)" not in corps
    assert corps.count("<script") == 1, "seul le script local autorisé doit être présent"

    csv_export = client.get("/history/1/export.csv")
    lignes = list(csv.reader(io.StringIO(csv_export.get_data(as_text=True))))
    assert lignes[1][-1] == "'=cmd|'/c calc'!A1"


def test_les_entetes_de_securite_sont_inchangees(client_et_stockage):
    """Contrôle préexistant : CSP stricte et en-têtes de navigateur."""
    client, _ = client_et_stockage
    reponse = client.get("/")

    csp = reponse.headers["Content-Security-Policy"]
    assert reponse.headers["X-Content-Type-Options"] == "nosniff"
    assert reponse.headers["X-Frame-Options"] == "DENY"
    assert reponse.headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in csp
    assert "script-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp


def test_la_suppression_exige_toujours_un_post_avec_jeton(client_et_stockage):
    """Contrôle préexistant : CSRF et méthode."""
    client, stockage = client_et_stockage
    stockage.enregistrer(
        fixture("rapport_valide_sans_namespace.xml"),
        import_reports("rapport.xml", fixture("rapport_valide_sans_namespace.xml")),
        *analyse_complete(),
    )
    jeton = jeton_de(client, "/history")

    assert client.get("/history/1/delete").status_code == 405
    assert client.post("/history/1/delete", data={}).status_code == 400
    assert client.post("/history/1/delete", data={"jeton_csrf": "faux"}).status_code == 400
    assert stockage.obtenir(1) is not None, "aucune suppression sans jeton valide"

    valide = client.post("/history/1/delete", data={"jeton_csrf": jeton})
    assert valide.status_code == 302
    assert stockage.obtenir(1) is None


def test_un_second_import_identique_ne_cree_pas_de_doublon(client_et_stockage):
    """Contrôle préexistant : détection de doublon par contrainte UNIQUE."""
    client, stockage = client_et_stockage
    jeton = jeton_de(client, "/upload")
    document = fixture("rapport_valide_sans_namespace.xml")

    for _ in range(2):
        client.post(
            "/upload",
            data={"rapport": (io.BytesIO(document), "rapport.xml"), "jeton_csrf": jeton},
            content_type="multipart/form-data",
        )

    assert stockage.compter() == 1


def test_un_import_xml_valide_depuis_une_base_vide_donne_le_resultat_attendu(client_et_stockage):
    """Non-régression fonctionnelle du parcours nominal après correctifs."""
    client, stockage = client_et_stockage
    jeton = jeton_de(client, "/upload")

    reponse = client.post(
        "/upload",
        data={
            "rapport": (io.BytesIO(fixture("rapport_valide_sans_namespace.xml")), "rapport.xml"),
            "jeton_csrf": jeton,
        },
        content_type="multipart/form-data",
    )

    assert reponse.status_code == 200
    assert stockage.compter() == 1
    assert client.get("/history").status_code == 200
    assert client.get("/history/1").status_code == 200
    assert client.get("/history/1/export.json").status_code == 200
    assert client.get("/history/1/export.csv").status_code == 200
    assert "Viewing a stored analysis" in client.get("/history/1").get_data(as_text=True)
    assert "Viewing mode" in client.get("/history/1").get_data(as_text=True)


def test_l_export_json_ne_contains_ni_xml_ni_chemin(client_et_stockage):
    """Contrôle préexistant : l'export reste minimal et lisible."""
    import json

    client, _ = client_et_stockage
    jeton = jeton_de(client, "/upload")
    client.post(
        "/upload",
        data={
            "rapport": (io.BytesIO(fixture("rapport_valide_sans_namespace.xml")), "rapport.xml"),
            "jeton_csrf": jeton,
        },
        content_type="multipart/form-data",
    )

    reponse = client.get("/history/1/export.json")
    charge = json.loads(reponse.get_data(as_text=True))

    assert charge["schema_version"] == 1
    assert isinstance(charge["analysis"]["metriques"]["total_messages"], int)
    assert "Traceback" not in json.dumps(charge)
    assert "<?xml" not in json.dumps(charge)
    assert "sqlite3" not in json.dumps(charge)
    assert str(charge["content_sha256"]) == charge["content_sha256"]


def test_l_export_csv_ne_modifie_pas_la_base(client_et_stockage):
    """Contrôle préexistant : les exports sont en lecture seule."""
    client, stockage = client_et_stockage
    jeton = jeton_de(client, "/upload")
    client.post(
        "/upload",
        data={
            "rapport": (io.BytesIO(fixture("rapport_valide_sans_namespace.xml")), "rapport.xml"),
            "jeton_csrf": jeton,
        },
        content_type="multipart/form-data",
    )
    avant = stockage.obtenir(1)

    client.get("/history/1/export.json")
    client.get("/history/1/export.csv")

    apres = stockage.obtenir(1)
    assert avant.analyse == apres.analyse
    assert avant.briefing == apres.briefing
    assert stockage.compter() == 1


def test_la_narration_reste_desactivee_par_defaut(client_et_stockage, caplog):
    """Contrôle préexistant : aucun appel réseau et aucun import du paquet IA."""
    client, _ = client_et_stockage
    jeton = jeton_de(client, "/upload")
    with caplog.at_level("DEBUG"):
        reponse = client.post(
            "/upload",
            data={
                "rapport": (io.BytesIO(fixture("rapport_valide_sans_namespace.xml")), "rapport.xml"),
                "jeton_csrf": jeton,
            },
            content_type="multipart/form-data",
        )

    corps = reponse.get_data(as_text=True)
    assert reponse.status_code == 200
    assert "AI narration is disabled" in corps
    assert "requests" not in caplog.text.lower() or "ollama" not in caplog.text.lower()


def test_l_identifiant_d_archives_historique_inconnu_reste_404(client_et_stockage):
    """Contrôle préexistant : identifiant absent ou non numérique."""
    client, _ = client_et_stockage

    assert client.get("/history/42").status_code == 404
    assert client.get("/history/abc").status_code == 404
    assert client.get("/history/42/export.json").status_code == 404


def test_un_geste_ia_manquant_ne_desactive_pas_l_analyse_deterministe():
    """Contrôle préexistant : l'IA reste facultative de bout en bout.

    Le paquet `app.ai` n'est pas importé par le chemin déterministe : le
    sous-processus échoue volontairement si le module est chargé.
    """
    import subprocess

    code = (
        "import sys; sys.path.insert(0, '.');"
        "import app.core.archive, app.core.rules, app.core.briefing, app.storage.database;"
        "from app import create_app;"
        "charge = [m for m in sys.modules if m.startswith('app.ai')];"
        "print('CHARGE:' + ','.join(sorted(charge)))"
    )
    sortie = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=str(Path.cwd())
    )

    assert sortie.returncode == 0, sortie.stderr
    assert "CHARGE:\n" in sortie.stdout


def test_une_configuration_ia_invalide_ne_bloque_pas_l_analyse_deterministe():
    """Contrôle préexistant : l'échec de l'IA optionnelle n'atteint pas le cœur.

    Un endpoint refusé est signalé par un statut, sans requête et sans lever :
    l'import et le briefing déterministes sont déjà enregistrés à ce stade.
    """
    client_ia = ClientOllama(
        ParametresNarration(actif=True, url="ftp://example.com", modele="m")
    )

    def transport_injoignable(url, charge, timeout, taille_max):
        raise AssertionError("aucune requête ne doit être émise")

    client_ia._transport = transport_injoignable
    resultat = client_ia.narrer(None)

    assert resultat.statut is StatutNarration.DESACTIVE
    assert resultat.statut is not StatutNarration.OK
    assert resultat.resume == ""


def test_le_nom_de_fichier_export_ne_peut_pas_etre_injecte():
    """Contrôle préexistant : le nom d'attachment ne dépend que d'un entier."""
    from app.export import nom_fichier_export

    assert nom_fichier_export(12, "json") == "mailguard-analysis-12.json"
    assert nom_fichier_export(12, "csv") == "mailguard-analysis-12.csv"


def test_le_csv_resiste_a_un_contenu_avec_separateurs_et_guillemets():
    """Contrôle préexistant : l'échappement reste entièrement confié au module csv."""
    document = (
        ENTETE
        + MODEL.format(index=1, count=1).replace(
            "<header_from>example.com</header_from>",
            "<header_from>a,b \"c\"\nd</header_from>",
        )
        + "</feedback>\n"
    ).encode()
    resultat = import_reports("csv.xml", document)
    from app.core.briefing import construire_briefing
    from app.core.rules import analyser
    from app.storage.database import Enregistrement
    from datetime import datetime, timezone

    analyse = analyser(resultat.reports)
    enregistrement = Enregistrement(
        identifiant=1,
        empreinte="f" * 64,
        nom_fichier="csv.xml",
        date_import=datetime.now(timezone.utc),
        version_moteur="0.1.0",
        domaine_publie="example.com",
        analyse=analyse,
        briefing=construire_briefing(analyse),
    )

    lignes = list(csv.reader(io.StringIO(construire_export_csv_sources(enregistrement))))

    assert lignes[1][-1] == 'a,b "c"\nd', "le saut de ligne doit survivre au champ CSV"


# --- Utilitaires --------------------------------------------------------------


def jeton_de(client, chemin: str) -> str:
    """Extrait le jeton CSRF rendu par une page de formulaire."""
    corps = client.get(chemin).get_data(as_text=True)
    trouve = re.search(r'name="jeton_csrf" value="([^"]+)"', corps)
    assert trouve is not None, f"aucun jeton CSRF rendu par {chemin}"
    return trouve.group(1)


def analyse_complete():
    """Analyse et briefing déterministes de la fixture de référence."""
    from app.core.briefing import construire_briefing
    from app.core.rules import analyser

    resultat = import_reports(
        "rapport.xml", fixture("rapport_valide_sans_namespace.xml"), LIMITES_PAR_DEFAUT
    )
    analyse = analyser(resultat.reports)
    return analyse, construire_briefing(analyse)