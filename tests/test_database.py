"""Tests de la persistance SQLite (étape 5).

Chaque test utilise une base temporaire isolée : aucune donnée ne touche la base
réelle de l'utilisateur. Les analyses sont produites par les fonctions réelles
d'import, de règles et de briefing à partir des fixtures synthétiques.
"""

import gzip
import io
import sqlite3
import threading
import zipfile
from pathlib import Path

import pytest

from app.core.archive import import_reports
from app.core.briefing import construire_briefing
from app.core.errors import StorageError
from app.core.rules import analyser
from app.storage.database import (
    MIGRATIONS,
    VERSION_ANALYSE,
    VERSION_SCHEMA,
    Enregistrement,
    ResumeAnalyse,
    StockageAnalyses,
    calculer_empreinte,
)

CHEMIN_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def stockage(tmp_path) -> StockageAnalyses:
    """Stockage initialisé sur une base temporaire, un répertoire par test."""
    base = StockageAnalyses.depuis_chemin(tmp_path / "data" / "mailguard.sqlite3")
    base.initialiser()
    return base


def contenu_fixture(nom: str) -> bytes:
    """Octets exacts d'une fixture synthétique."""
    return (CHEMIN_FIXTURES / nom).read_bytes()


def analyse_depuis(contenu: bytes, nom_fichier: str = "rapport.xml"):
    """Pipeline réel : import, règles, briefing."""
    resultat = import_reports(nom_fichier, contenu)
    analyse = analyser(resultat.reports)
    return contenu, resultat, analyse, construire_briefing(analyse)


def archive_zip(contenus: dict[str, bytes]) -> bytes:
    """Archive ZIP synthétique construite en mémoire."""
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        for nom, contenu in contenus.items():
            archive.writestr(nom, contenu)
    return tampon.getvalue()


# --- Initialisation ----------------------------------------------------------


def test_initialisation_cree_une_base_neuve(tmp_path):
    base = StockageAnalyses.depuis_chemin(tmp_path / "data" / "mailguard.sqlite3")

    version = base.initialiser()

    assert version == VERSION_SCHEMA
    assert base.chemin.exists()
    assert base.version_schema() == VERSION_SCHEMA


def test_initialisation_repetee_est_idempotente(tmp_path):
    base = StockageAnalyses.depuis_chemin(tmp_path / "mailguard.sqlite3")
    base.initialiser()
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_valide_sans_namespace.xml"))
    reference = base.enregistrer(contenu, resultat, analyse, briefing)

    base.initialiser()
    base.initialiser()

    assert base.version_schema() == VERSION_SCHEMA
    assert base.compter() == 1
    assert base.obtenir(reference.identifiant) is not None


def test_initialisation_ne_duplique_pas_la_table(tmp_path):
    base = StockageAnalyses.depuis_chemin(tmp_path / "mailguard.sqlite3")
    base.initialiser()
    base.initialiser()

    with sqlite3.connect(base.chemin) as connexion:
        tables = connexion.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'analyses'"
        ).fetchall()

    assert len(tables) == 1


def test_migration_depuis_une_version_anterieure_conserve_les_donnees(tmp_path):
    base = StockageAnalyses.depuis_chemin(tmp_path / "mailguard.sqlite3")
    base.initialiser()
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_valide_sans_namespace.xml"))
    reference = base.enregistrer(contenu, resultat, analyse, briefing)

    with sqlite3.connect(base.chemin) as connexion:
        connexion.execute("PRAGMA user_version = 0")

    version = base.initialiser()

    assert version == VERSION_SCHEMA
    assert base.compter() == 1
    relu = base.obtenir(reference.identifiant)
    assert relu is not None and relu.empreinte == reference.empreinte


def test_repertoire_parent_non_cree_si_refuse(tmp_path):
    base = StockageAnalyses.depuis_chemin(
        tmp_path / "absent" / "mailguard.sqlite3", creer_repertoire=False
    )

    with pytest.raises(StorageError) as erreur:
        base.initialiser()

    assert "its creation is not allowed" in str(erreur.value)
    assert not (tmp_path / "absent").exists()


def test_chemin_pointant_vers_un_dossier_refuse(tmp_path):
    base = StockageAnalyses.depuis_chemin(tmp_path)

    with pytest.raises(StorageError) as erreur:
        base.initialiser()

    assert "is a directory, not a database file" in str(erreur.value)


def test_fichier_incompatible_refuse(tmp_path):
    fichier = tmp_path / "faux.sqlite3"
    fichier.write_bytes(b"ceci n'est pas une base SQLite, mais du texte")
    base = StockageAnalyses.depuis_chemin(fichier)

    with pytest.raises(StorageError):
        base.initialiser()


def test_version_de_schema_trop_recente_refusee(stockage):
    with sqlite3.connect(stockage.chemin) as connexion:
        connexion.execute(f"PRAGMA user_version = {VERSION_SCHEMA + 5}")

    with pytest.raises(StorageError) as erreur:
        stockage.initialiser()

    assert "Please update the software" in str(erreur.value)


def test_lecture_avant_initialisation_refusee(tmp_path):
    base = StockageAnalyses.depuis_chemin(tmp_path / "mailguard.sqlite3")

    with pytest.raises(StorageError) as erreur:
        base.lister()

    assert "not initialized" in str(erreur.value)


def test_migrations_declarees_pour_la_version_courante():
    assert VERSION_SCHEMA in MIGRATIONS
    assert all(instruction.strip() for instruction in MIGRATIONS[VERSION_SCHEMA])


# --- Enregistrement et lecture ----------------------------------------------


def test_enregistrement_et_relecture_conserve_tout(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(
        contenu_fixture("rapport_plusieurs_records.xml")
    )

    ecrit = stockage.enregistrer(contenu, resultat, analyse, briefing)
    relu = stockage.obtenir(ecrit.identifiant)

    assert isinstance(ecrit, Enregistrement)
    assert ecrit.cree is True
    assert relu is not None
    assert relu.analyse == analyse
    assert relu.briefing == briefing
    assert relu.empreinte == calculer_empreinte(contenu)
    assert relu.nom_fichier == "rapport.xml"
    assert relu.domaine_publie == "example.com"
    assert relu.date_import.tzinfo is not None


def test_identifiant_inconnu_renvoie_none(stockage):
    assert stockage.obtenir(4242) is None


def test_recherche_par_empreinte(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_dkim_multiples.xml"))
    ecrit = stockage.enregistrer(contenu, resultat, analyse, briefing)

    trouve = stockage.rechercher_par_empreinte(calculer_empreinte(contenu))
    absent = stockage.rechercher_par_empreinte("0" * 64)

    assert trouve is not None and trouve.identifiant == ecrit.identifiant
    assert absent is None


def test_liste_des_analyses_recentes_est_triee_et_limitee(stockage):
    for index, nom in enumerate(
        (
            "rapport_valide_sans_namespace.xml",
            "rapport_plusieurs_records.xml",
            "rapport_autre_domaine.xml",
        )
    ):
        contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture(nom))
        stockage.enregistrer(contenu, resultat, analyse, briefing, )

    liste = stockage.lister(limite=2)

    assert len(liste) == 2
    assert all(isinstance(resume, ResumeAnalyse) for resume in liste)
    identifiants = [resume.identifiant for resume in liste]
    assert identifiants == sorted(identifiants, reverse=True)


def test_liste_complete_expose_le_domaine_et_le_total(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_plusieurs_records.xml"))
    stockage.enregistrer(contenu, resultat, analyse, briefing)

    resume = stockage.lister()[0]

    assert resume.domaine_publie == "example.com"
    assert resume.total_messages == 125
    assert resume.nombre_rapports == 1


def test_limite_de_liste_invalide_refusee(stockage):
    with pytest.raises(StorageError) as erreur:
        stockage.lister(limite=0)

    assert "must be greater than zero" in str(erreur.value)


def test_les_valeurs_absentes_sont_preservees_telles_quelles(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_volume_nul.xml"))
    stockage.enregistrer(contenu, resultat, analyse, briefing)

    relu = stockage.obtenir(1)

    assert relu.analyse.metriques.taux_pass.valeur is None
    assert relu.analyse.metriques.taux_fail.valeur is None
    assert relu.analyse.metriques.total_messages == 0
    assert relu.analyse.metriques.dispositions.total == 0
    assert relu.analyse.sources[0].domaines_en_tete == []


def test_domaines_manquants_restent_absents_en_base(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_sans_identifiants.xml"))
    stockage.enregistrer(contenu, resultat, analyse, briefing)

    relu = stockage.obtenir(1)

    assert relu.domaine_publie is None
    assert relu.analyse.metriques.domaines_publies == []


def test_rapports_de_domaines_differents_restent_separes(stockage):
    premier = analyse_depuis(contenu_fixture("rapport_plusieurs_records.xml"))
    second = analyse_depuis(contenu_fixture("rapport_autre_domaine.xml"))

    e1 = stockage.enregistrer(*premier)
    e2 = stockage.enregistrer(*second)

    assert e1.identifiant != e2.identifiant
    assert stockage.compter() == 2
    assert {r.domaine_publie for r in stockage.lister()} == {"example.com", "example.net"}
    assert stockage.obtenir(e1.identifiant).analyse.metriques.total_messages == 125
    assert stockage.obtenir(e2.identifiant).analyse.metriques.total_messages == 11


# --- Doublons et transactions ------------------------------------------------


def test_second_import_identique_ne_cree_pas_de_ligne(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_valide_sans_namespace.xml"))

    premier = stockage.enregistrer(contenu, resultat, analyse, briefing)
    second = stockage.enregistrer(contenu, resultat, analyse, briefing)

    assert premier.cree is True
    assert second.cree is False
    assert second.identifiant == premier.identifiant
    assert stockage.compter() == 1


def test_analyse_existante_n_est_pas_modifiee_par_un_doublon(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_valide_sans_namespace.xml"))
    premier = stockage.enregistrer(contenu, resultat, analyse, briefing)
    date_initiale = stockage.obtenir(premier.identifiant).date_import

    stockage.enregistrer(contenu, resultat, analyse, briefing)

    relu = stockage.obtenir(premier.identifiant)
    assert relu.date_import == date_initiale
    assert relu.cree is False


def test_fichiers_differents_pour_le_meme_rapport_ne_sont_pas_confondus(stockage):
    xml = contenu_fixture("rapport_valide_sans_namespace.xml")
    zip_equivalant = archive_zip({"rapport.xml": xml})
    gz_equivalent = gzip.compress(xml)

    par_xml = stockage.enregistrer(*analyse_depuis(xml))
    par_zip = stockage.enregistrer(*analyse_depuis(zip_equivalant, "rapports.zip"))
    par_gz = stockage.enregistrer(*analyse_depuis(gz_equivalent, "rapport.xml.gz"))

    assert len({par_xml.empreinte, par_zip.empreinte, par_gz.empreinte}) == 3
    assert stockage.compter() == 3


def test_contrainte_d_unicite_verifiee_par_sqlite(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_valide_sans_namespace.xml"))
    stockage.enregistrer(contenu, resultat, analyse, briefing)

    with pytest.raises(sqlite3.IntegrityError):
        with sqlite3.connect(stockage.chemin) as connexion:
            connexion.execute(
                """
                INSERT INTO analyses (empreinte, nom_fichier, date_import, version_schema,
                                      version_moteur, domaine_publie, nombre_rapports,
                                      total_messages, analyse_json, briefing_json)
                VALUES (?, 'faux.xml', '2026-01-01T00:00:00+00:00', 1, 'test', NULL, 0, 0, '{}', '{}')
                """,
                (calculer_empreinte(contenu),),
            )


def test_appels_concurrents_ne_creent_qu_une_ligne(tmp_path):
    base = StockageAnalyses.depuis_chemin(tmp_path / "mailguard.sqlite3", timeout_secondes=10.0)
    base.initialiser()
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_valide_sans_namespace.xml"))

    barrier = threading.Barrier(2)
    resultats: list[Enregistrement] = []
    erreurs: list[Exception] = []

    def importer() -> None:
        try:
            barrier.wait(timeout=5)
            resultats.append(base.enregistrer(contenu, resultat, analyse, briefing))
        except Exception as erreur:  # pragma: no cover - ne doit pas se produire
            erreurs.append(erreur)

    fils = [threading.Thread(target=importer) for _ in range(2)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join(timeout=20)

    assert not erreurs
    assert len(resultats) == 2
    assert base.compter() == 1
    assert sum(1 for resultat in resultats if resultat.cree) == 1
    assert len({resultat.identifiant for resultat in resultats}) == 1


def test_erreur_d_ecriture_annule_la_ligne(stockage, monkeypatch):
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_autre_domaine.xml"))

    def ecrire_puis_paner(self, connexion, **arguments):
        connexion.execute(
            """
            INSERT INTO analyses (empreinte, nom_fichier, date_import, version_schema,
                                  version_moteur, domaine_publie, nombre_rapports,
                                  total_messages, analyse_json, briefing_json)
            VALUES (?, 'temporaire.xml', '2026-01-01T00:00:00+00:00', 1, 'test', NULL, 0, 0, '{}', '{}')
            """,
            (calculer_empreinte(contenu),),
        )
        raise RuntimeError("panne simulée pendant l'écriture")

    monkeypatch.setattr(StockageAnalyses, "_ecrire", ecrire_puis_paner)

    with pytest.raises(RuntimeError):
        stockage.enregistrer(contenu, resultat, analyse, briefing)

    assert stockage.compter() == 0


def test_erreur_de_serie_ne_cree_rien(stockage, monkeypatch):
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_autre_domaine.xml"))

    def serie_invalide(analyse_a_ecrire, briefing_a_ecrire):
        raise ValueError("sérialisation impossible")

    monkeypatch.setattr("app.storage.database._serialiser", serie_invalide)

    with pytest.raises(ValueError):
        stockage.enregistrer(contenu, resultat, analyse, briefing)

    assert stockage.compter() == 0


# --- Sécurité ----------------------------------------------------------------


def test_nom_de_fichier_malveillant_est_neutralise(stockage):
    nom = "../../evil\"; DROP TABLE analyses; --.xml"
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_valide_sans_namespace.xml"), nom)

    ecrit = stockage.enregistrer(contenu, resultat, analyse, briefing)
    relu = stockage.obtenir(ecrit.identifiant)

    assert relu.nom_fichier == "evil\"; DROP TABLE analyses; --.xml"
    assert "/" not in relu.nom_fichier
    assert stockage.compter() == 1


def test_nom_de_fichier_ne_cree_aucun_chemin(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stockage = StockageAnalyses.depuis_chemin(tmp_path / "mailguard.sqlite3")
    stockage.initialiser()
    contenu, resultat, analyse, briefing = analyse_depuis(
        contenu_fixture("rapport_valide_sans_namespace.xml"), "../../../../etc/evil.xml"
    )

    stockage.enregistrer(contenu, resultat, analyse, briefing)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["mailguard.sqlite3"]


def test_valeurs_avec_apostrophes_ne_provoquent_pas_d_injection(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(
        contenu_fixture("rapport_valide_sans_namespace.xml"),
        "rapport O'Brien'); DROP TABLE analyses; --.xml",
    )

    ecrit = stockage.enregistrer(contenu, resultat, analyse, briefing)
    relu = stockage.obtenir(ecrit.identifiant)

    assert relu.nom_fichier == "rapport O'Brien'); DROP TABLE analyses; --.xml"
    assert stockage.compter() == 1


def test_caracteres_unicode_sont_conseves(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(
        contenu_fixture("rapport_valide_sans_namespace.xml"), "rapport été-中文-🔒.xml"
    )

    ecrit = stockage.enregistrer(contenu, resultat, analyse, briefing)

    assert stockage.obtenir(ecrit.identifiant).nom_fichier == "rapport été-中文-🔒.xml"


def test_le_xml_brut_n_est_jamais_ecrit_en_base(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_plusieurs_records.xml"))

    stockage.enregistrer(contenu, resultat, analyse, briefing)

    with sqlite3.connect(stockage.chemin) as connexion:
        connexion.row_factory = sqlite3.Row
        lignes = connexion.execute("SELECT * FROM analyses").fetchall()
    texte_complet = " ".join(str(valeur) for ligne in lignes for valeur in tuple(ligne))

    for marqueur in ("<feedback", "<record", "policy_evaluated", "<?xml version"):
        assert marqueur not in texte_complet
    assert "<" not in texte_complet and ">" not in texte_complet
    assert stockage.chemin.exists()


def test_message_d_erreur_ne_fuit_pas_de_contenu_sensible(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_valide_sans_namespace.xml"))
    stockage.enregistrer(contenu, resultat, analyse, briefing)

    with sqlite3.connect(stockage.chemin) as connexion:
        connexion.execute(
            "UPDATE analyses SET analyse_json = ? WHERE identifiant = 1",
            ('{"version": 1, "analyse": {"casse": true}}',),
        )

    with pytest.raises(StorageError) as erreur:
        stockage.obtenir(1)

    message = str(erreur.value)
    assert "Traceback" not in message
    assert "casse" not in message
    assert stockage.chemin.exists()


def test_format_de_charge_utile_inconnu_refuse(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_valide_sans_namespace.xml"))
    stockage.enregistrer(contenu, resultat, analyse, briefing)

    with sqlite3.connect(stockage.chemin) as connexion:
        connexion.execute(
            "UPDATE analyses SET analyse_json = ? WHERE identifiant = 1",
            ('{"version": 99, "analyse": {}}',),
        )

    with pytest.raises(StorageError) as erreur:
        stockage.obtenir(1)

    assert "cannot read" in str(erreur.value)


def test_version_de_format_enregistree_est_celle_attendue(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_valide_sans_namespace.xml"))
    stockage.enregistrer(contenu, resultat, analyse, briefing)

    with sqlite3.connect(stockage.chemin) as connexion:
        charge = connexion.execute("SELECT analyse_json FROM analyses").fetchone()[0]

    assert f'"version": {VERSION_ANALYSE}' in charge


# --- Suppression -------------------------------------------------------------


def test_suppression_retire_la_ligne(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_autre_domaine.xml"))
    ecrit = stockage.enregistrer(contenu, resultat, analyse, briefing)

    supprime = stockage.supprimer(ecrit.identifiant)

    assert supprime is True
    assert stockage.compter() == 0
    assert stockage.obtenir(ecrit.identifiant) is None


def test_suppression_d_un_identifiant_inconnu(stockage):
    assert stockage.supprimer(999) is False


def test_apres_suppression_le_contenu_peut_etre_reimporte(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(contenu_fixture("rapport_autre_domaine.xml"))
    ecrit = stockage.enregistrer(contenu, resultat, analyse, briefing)
    stockage.supprimer(ecrit.identifiant)

    reimporte = stockage.enregistrer(contenu, resultat, analyse, briefing)

    assert reimporte.cree is True
    assert stockage.compter() == 1

# --- Étape 8 : champs d'historique relus depuis la charge utile --------------


def test_resume_expose_pass_fail_et_fenetre_de_couverture(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(
        contenu_fixture("rapport_plusieurs_records.xml")
    )
    ecrit = stockage.enregistrer(contenu, resultat, analyse, briefing)

    resume = stockage.lister()[0]

    assert resume.identifiant == ecrit.identifiant
    assert resume.messages_pass == 100
    assert resume.messages_fail == 25
    assert resume.date_debut == analyse.rapports[0].date_debut
    assert resume.date_fin == analyse.rapports[0].date_fin


def test_fenetre_couverture_couvre_tous_les_rapports(stockage):
    premier = analyse_depuis(contenu_fixture("rapport_plusieurs_records.xml"))
    second = analyse_depuis(contenu_fixture("rapport_autre_domaine.xml"))
    stockage.enregistrer(*premier)
    stockage.enregistrer(*second)

    resume = stockage.lister()[0]

    assert resume.nombre_rapports == 1
    assert resume.date_debut < second[2].rapports[0].date_fin


def test_liste_vide_renvoie_une_liste_vide(stockage):
    assert stockage.lister() == []


def test_ligne_historique_abimee_refusee_avec_une_erreur_claire(stockage):
    contenu, resultat, analyse, briefing = analyse_depuis(
        contenu_fixture("rapport_valide_sans_namespace.xml")
    )
    stockage.enregistrer(contenu, resultat, analyse, briefing)

    with sqlite3.connect(stockage.chemin) as connexion:
        connexion.execute("UPDATE analyses SET analyse_json = 'casse'")

    with pytest.raises(StorageError):
        stockage.lister()
