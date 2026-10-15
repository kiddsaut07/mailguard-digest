"""Tests de l'importation sécurisée des rapports DMARC (étape 3).

Toutes les données sont synthétiques : les rapports XML viennent des fixtures de
`tests/fixtures/`, les archives sont construites en mémoire et aucun rapport
client réel n'est utilisé. Aucun test n'écrit de fichier sur le disque.
"""

import gzip
import io
import os
import struct
import warnings
import zipfile
from pathlib import Path

import pytest

from app.core import archive as module_archive
from app.core.archive import (
    LIMITES_PAR_DEFAUT,
    ImportLimits,
    import_reports,
)
from app.core.errors import (
    ArchiveError,
    ArchiveLimitError,
    MailGuardError,
    ReportParseError,
    ReportValidationError,
    UnsafeArchiveError,
)

CHEMIN_FIXTURES = Path(__file__).parent / "fixtures"
PETITES_LIMITES = ImportLimits(
    max_upload_bytes=64 * 1024,
    max_decompressed_bytes=256 * 1024,
    max_archive_members=5,
    max_reports=2,
)


def fixture(nom: str) -> bytes:
    """Contenu binaire d'une fixture XML synthétique."""
    return (CHEMIN_FIXTURES / nom).read_bytes()


RAPPORT_A = fixture("rapport_valide_sans_namespace.xml")
RAPPORT_B = fixture("rapport_valide_avec_namespace.xml")
RAPPORT_C = fixture("rapport_dkim_multiples.xml")
RAPPORT_TRONQUE = fixture("rapport_tronque.xml")
RAPPORT_AVEC_DTD = fixture("rapport_avec_dtd.xml")
RAPPORT_IP_INVALIDE = fixture("rapport_ip_invalide.xml")


# --- Construction d'archives synthétiques -----------------------------------


def construire_zip(entrees: list[tuple[str, bytes]]) -> bytes:
    """Archive ZIP décompressée construite entièrement en mémoire."""
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        for nom, contenu in entrees:
            archive.writestr(nom, contenu)
    return tampon.getvalue()


def construire_zip_attributs(entrees: list[tuple[zipfile.ZipInfo, bytes]]) -> bytes:
    """Archive ZIP dont les entrées ont des attributs externes forcés."""
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        for entree, contenu in entrees:
            archive.writestr(entree, contenu)
    return tampon.getvalue()


def entree(nom: str, mode: int) -> zipfile.ZipInfo:
    """Entrée ZIP avec un mode UNIX imposé (lien symbolique, FIFO...)."""
    info = zipfile.ZipInfo(filename=nom, date_time=(2026, 10, 1, 0, 0, 0))
    info.external_attr = mode << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def position_central(contenu: bytes) -> int:
    """Position du premier en-tête de répertoire central."""
    return contenu.index(b"PK\x01\x02")


def marquer_membre_chiffre(contenu: bytes) -> bytes:
    """Positionne l'indicateur « chiffré » dans le répertoire central."""
    modifie = bytearray(contenu)
    position = position_central(modifie)
    struct.pack_into("<H", modifie, position + 8, 0x1)
    return bytes(modifie)


def falsifier_taille_annoncee(contenu: bytes, taille: int = 0) -> bytes:
    """Annonce une taille décompressée fausse dans le répertoire central."""
    modifie = bytearray(contenu)
    position = position_central(modifie)
    struct.pack_into("<I", modifie, position + 24, taille)
    return bytes(modifie)


def corrompre_entete_local(contenu: bytes) -> bytes:
    """Rend l'en-tête local du premier membre illisible."""
    modifie = bytearray(contenu)
    position = modifie.index(b"PK\x03\x04")
    modifie[position : position + 4] = b"PK\x03\x09"
    return bytes(modifie)


# --- Formats valides ---------------------------------------------------------


def test_limites_par_defaut_conformes_a_la_documentation():
    assert LIMITES_PAR_DEFAUT.max_upload_bytes == 10 * 1024 * 1024
    assert LIMITES_PAR_DEFAUT.max_decompressed_bytes == 50 * 1024 * 1024
    assert LIMITES_PAR_DEFAUT.max_archive_members == 100
    assert LIMITES_PAR_DEFAUT.max_reports == 20


def test_xml_valide_est_importe():
    resultat = import_reports("rapport.xml", RAPPORT_A)

    assert len(resultat.reports) == 1
    rapport = resultat.reports[0]
    assert rapport.metadata.report_id == "1800000000-aaaa1111"
    assert rapport.total_messages == 42
    assert resultat.total_messages == 42
    assert resultat.ignored_entries == []


def test_xml_valide_accepte_la_majuscule_de_extension():
    resultat = import_reports("RAPPORT.XML", RAPPORT_A)

    assert resultat.reports[0].metadata.org_name == "Example Mail Provider"


def test_gzip_valide_contenant_un_xml_est_importe():
    resultat = import_reports("rapport.xml.gz", gzip.compress(RAPPORT_A))

    assert len(resultat.reports) == 1
    assert resultat.reports[0].metadata.report_id == "1800000000-aaaa1111"
    assert resultat.total_messages == 42


def test_zip_valide_avec_un_rapport_est_importe():
    resultat = import_reports("rapports.zip", construire_zip([("rapport.xml", RAPPORT_A)]))

    assert len(resultat.reports) == 1
    assert resultat.reports[0].records[0].source_ip == "192.0.2.10"


def test_zip_valide_avec_plusieurs_rapports_est_importe():
    contenu = construire_zip(
        [("a.xml", RAPPORT_A), ("b.xml", RAPPORT_B), ("c.xml", RAPPORT_C)]
    )

    resultat = import_reports("rapports.zip", contenu)

    assert [rapport.metadata.report_id for rapport in resultat.reports] == [
        "1800000000-aaaa1111",
        "1800000000-bbbb2222",
        "1800000000-cccc3333",
    ]
    assert resultat.total_messages == 42 + 7 + 9


def test_ordre_des_rapports_est_deterministe_et_independant_de_l_ordre_du_zip():
    contenu = construire_zip(
        [("zzz.xml", RAPPORT_C), ("aaa.xml", RAPPORT_A), ("mmm.xml", RAPPORT_B)]
    )

    resultat = import_reports("rapports.zip", contenu)
    autre = import_reports("rapports.zip", contenu)

    assert [rapport.metadata.report_id for rapport in resultat.reports] == [
        "1800000000-aaaa1111",
        "1800000000-bbbb2222",
        "1800000000-cccc3333",
    ]
    assert resultat.reports == autre.reports


def test_repertoire_dans_une_archive_est_valide_et_signale():
    contenu = construire_zip(
        [("repertoire/", b""), ("repertoire/rapport.xml", RAPPORT_A)]
    )

    resultat = import_reports("rapports.zip", contenu)

    assert len(resultat.reports) == 1
    assert resultat.ignored_entries == ["repertoire/"]


def test_fichier_ordinaire_non_pris_en_charge_est_ignore_et_signale():
    contenu = construire_zip(
        [("rapport.xml", RAPPORT_A), ("lisezmoi.txt", b"texte ordinaire"), (".DS_Store", b"bruit")]
    )

    resultat = import_reports("rapports.zip", contenu)

    assert len(resultat.reports) == 1
    assert resultat.ignored_entries == [".DS_Store", "lisezmoi.txt"]


def test_aucun_fichier_n_est_ecrit_sur_le_disque(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    import_reports("rapports.zip", construire_zip([("rapport.xml", RAPPORT_A)]))

    assert list(tmp_path.iterdir()) == []


def test_resultat_expose_le_nom_nettoye_du_fichier():
    resultat = import_reports("dossiers/rapport.xml", RAPPORT_A)

    assert resultat.file_name == "rapport.xml"


# --- Fichiers invalides ------------------------------------------------------


@pytest.mark.parametrize(
    "nom", ["rapport.txt", "rapport.csv", "rapport", "rapport.xml.bz2", "rapport.xm"]
)
def test_extension_non_prise_en_charge_refusee(nom):
    with pytest.raises(ArchiveError) as erreur:
        import_reports(nom, RAPPORT_A)

    assert "unsupported file format" in str(erreur.value)


def test_fichier_vide_refuse():
    with pytest.raises(ArchiveError) as erreur:
        import_reports("rapport.xml", b"")

    assert "the file is empty" in str(erreur.value)


def test_contenu_xml_malforme_refuse_avec_le_nom_du_fichier():
    with pytest.raises(ReportParseError) as erreur:
        import_reports("rapport.xml", RAPPORT_TRONQUE)

    assert "rapport.xml" in str(erreur.value)
    assert "Entry" in str(erreur.value)


def test_donnees_invalides_relayees_par_le_parseur():
    with pytest.raises(ReportValidationError) as erreur:
        import_reports("rapport.xml", RAPPORT_IP_INVALIDE)

    assert "source_ip" in str(erreur.value)


def test_extension_xml_avec_contenu_dun_autre_format_refuse():
    with pytest.raises(ArchiveError) as erreur:
        import_reports("rapport.xml", gzip.compress(RAPPORT_A))

    assert "the content is not XML" in str(erreur.value)


def test_extension_xml_gz_avec_contenu_non_compresse_refuse():
    with pytest.raises(ArchiveError) as erreur:
        import_reports("rapport.xml.gz", RAPPORT_A)

    assert "GZIP" in str(erreur.value)


def test_gzip_tronque_refuse():
    compresse = gzip.compress(RAPPORT_A)

    with pytest.raises(ArchiveError) as erreur:
        import_reports("rapport.xml.gz", compresse[:-12])

    assert "corrupted or truncated" in str(erreur.value)


def test_gzip_corrompu_refuse():
    compresse = bytearray(gzip.compress(RAPPORT_A))
    compresse[-3] = 0xFF
    compresse[-2] = 0xFF
    compresse[-1] = 0xFF

    with pytest.raises(ArchiveError) as erreur:
        import_reports("rapport.xml.gz", bytes(compresse))

    assert "corrupted or truncated" in str(erreur.value)


def test_gzip_non_gzip_refuse():
    with pytest.raises(ArchiveError):
        import_reports("rapport.xml.gz", b"ceci n'est pas une archive gzip")


def test_zip_invalide_refuse():
    with pytest.raises(ArchiveError) as erreur:
        import_reports("rapports.zip", b"PK\x03\x04 ceci n'est pas une archive")

    assert "ZIP" in str(erreur.value)


def test_zip_tronque_refuse():
    contenu = construire_zip([("rapport.xml", RAPPORT_A)])

    with pytest.raises(ArchiveError) as erreur:
        import_reports("rapports.zip", contenu[: len(contenu) // 2])

    assert "ZIP" in str(erreur.value)


def test_zip_vide_refuse():
    with pytest.raises(ArchiveError) as erreur:
        import_reports("rapports.zip", construire_zip([]))

    assert "the ZIP archive is empty" in str(erreur.value)


def test_zip_sans_rapport_admissible_refuse():
    contenu = construire_zip([("lisezmoi.txt", b"texte ordinaire")])

    with pytest.raises(ArchiveError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "no usable DMARC report" in str(erreur.value)


def test_membre_xml_malforme_dans_un_zip_refuse():
    contenu = construire_zip([("rapport.xml", RAPPORT_TRONQUE)])

    with pytest.raises(ReportParseError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "rapport.xml" in str(erreur.value)


def test_membre_xml_avec_extension_mais_autre_contenu_refuse():
    contenu = construire_zip([("rapport.xml", "ceci est du texte".encode())])

    with pytest.raises(ArchiveError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "the content is not XML" in str(erreur.value)


def test_un_membre_en_echec_fait_echouer_l_import_entier():
    contenu = construire_zip([("bon.xml", RAPPORT_A), ("mauvais.xml", RAPPORT_TRONQUE)])

    with pytest.raises(ReportParseError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "mauvais.xml" in str(erreur.value)


# --- Limites -----------------------------------------------------------------


def test_fichier_televerse_trop_volumineux_refuse():
    limites = ImportLimits(max_upload_bytes=1024, max_decompressed_bytes=1024 * 1024)

    with pytest.raises(ArchiveLimitError) as erreur:
        import_reports("rapport.xml", RAPPORT_A, limites)

    assert "the uploaded file exceeds" in str(erreur.value)


def test_donnees_decompressees_au_dela_de_la_limite_interrompent_la_lecture():
    bombe = gzip.compress(b"A" * (200 * 1024))
    limites = ImportLimits(max_decompressed_bytes=64 * 1024)

    with pytest.raises(ArchiveLimitError) as erreur:
        import_reports("rapport.xml.gz", bombe, limites)

    assert "Import stopped" in str(erreur.value)


def test_archive_trop_compressee_interrompue_pendant_la_lecture():
    """Un membre minuscule en mémoire décompresse bien plus que sa taille annoncée."""
    bombe = construire_zip([("bomb.xml", b"A" * (300 * 1024))])
    limites = ImportLimits(max_decompressed_bytes=64 * 1024)

    with pytest.raises(ArchiveLimitError) as erreur:
        import_reports("rapports.zip", bombe, limites)

    assert "byte limit" in str(erreur.value)


def test_zip_avec_trop_de_membres_refuse():
    contenu = construire_zip(
        [(f"rapport{index}.xml", RAPPORT_A) for index in range(6)]
    )

    with pytest.raises(ArchiveLimitError) as erreur:
        import_reports("rapports.zip", contenu, PETITES_LIMITES)

    assert "entries, the limit" in str(erreur.value)


def test_zip_avec_trop_de_rapports_refuse():
    contenu = construire_zip([("a.xml", RAPPORT_A), ("b.xml", RAPPORT_B)])
    limites = ImportLimits(max_reports=1)

    with pytest.raises(ArchiveLimitError) as erreur:
        import_reports("rapports.zip", contenu, limites)

    assert "XML reports" in str(erreur.value)


def test_volume_total_des_membres_refuse_meme_pour_un_membre_ignore():
    contenu = construire_zip(
        [("rapport.xml", RAPPORT_A), ("donnees.bin", b"B" * (300 * 1024))]
    )
    limites = ImportLimits(max_decompressed_bytes=64 * 1024)

    with pytest.raises(ArchiveLimitError) as erreur:
        import_reports("rapports.zip", contenu, limites)

    assert "declared archive volume" in str(erreur.value)


def test_taille_annoncee_faussee_est_refusee_et_non_croie():
    contenu = falsifier_taille_annoncee(construire_zip([("rapport.xml", b"A" * 5000)]))

    with pytest.raises(ArchiveError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "corrupted or unreadable" in str(erreur.value)


def test_budget_de_decompression_refuse_le_depassement_reel():
    """Le comptage réel des octets lus est une barrière indépendante des métadonnées.

    Aucune archive ZIP honnête construite par la bibliothèque standard ne peut
    faire mentir sa taille déclarée : la barrière interne est donc vérifiée
    directement, en plus des scénarios de bout en bout ci-dessus.
    """
    budget = module_archive._Budget(limite=100)

    budget.consommer(60, "membre.xml")
    with pytest.raises(ArchiveLimitError):
        budget.consommer(41, "membre.xml")


def test_budget_de_decompression_accepte_le_volume_autorise():
    budget = module_archive._Budget(limite=100)

    budget.consommer(100, "membre.xml")

    assert budget.consommes == 100


# --- Sécurité ZIP ------------------------------------------------------------


def test_archive_imbriquee_refusee():
    contenu = construire_zip([("interne.zip", construire_zip([("x.xml", RAPPORT_A)]))])

    with pytest.raises(UnsafeArchiveError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "nested archive refused" in str(erreur.value)


def test_membre_xml_gz_dans_un_zip_refuse_comme_archive_imbriquee():
    contenu = construire_zip([("rapport.xml.gz", gzip.compress(RAPPORT_A))])

    with pytest.raises(UnsafeArchiveError):
        import_reports("rapports.zip", contenu)


def test_membre_chiffre_refuse():
    contenu = marquer_membre_chiffre(construire_zip([("rapport.xml", RAPPORT_A)]))

    with pytest.raises(UnsafeArchiveError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "is encrypted" in str(erreur.value)


def test_chemin_absolu_refuse():
    contenu = construire_zip([("/etc/rapport.xml", RAPPORT_A)])

    with pytest.raises(UnsafeArchiveError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "absolute path" in str(erreur.value)


def test_segment_parent_refuse():
    contenu = construire_zip([("../evade.xml", RAPPORT_A)])

    with pytest.raises(UnsafeArchiveError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "escapes the archive root" in str(erreur.value)


def test_chemin_windows_traversant_refuse():
    contenu = construire_zip([("sous\\..\\evade.xml", RAPPORT_A)])

    with pytest.raises(UnsafeArchiveError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "escapes the archive root" in str(erreur.value)


def test_chemin_absolu_windows_refuse():
    contenu = construire_zip([("C:\\evade.xml", RAPPORT_A)])

    with pytest.raises(UnsafeArchiveError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "absolute Windows path" in str(erreur.value)


def test_chemin_ambigu_avec_double_separateur_refuse():
    contenu = construire_zip([("dossier//rapport.xml", RAPPORT_A)])

    with pytest.raises(UnsafeArchiveError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "ambiguous path" in str(erreur.value)


def test_noms_de_membres_en_double_refuses():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        contenu = construire_zip([("rapport.xml", RAPPORT_A), ("rapport.xml", RAPPORT_B)])

    with pytest.raises(UnsafeArchiveError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "appears twice" in str(erreur.value)


def test_doublon_apres_normalisation_refuse():
    contenu = construire_zip([("Rapport.xml", RAPPORT_A), ("rapport.xml", RAPPORT_B)])

    with pytest.raises(UnsafeArchiveError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "appears twice" in str(erreur.value)


def test_lien_symbolique_refuse():
    contenu = construire_zip_attributs(
        [(entree("lien.xml", 0o120777), b"/etc/passwd"), (entree("rapport.xml", 0o100644), RAPPORT_A)]
    )

    with pytest.raises(UnsafeArchiveError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "symbolic link" in str(erreur.value)


def test_entree_speciale_non_ordinaire_refusee():
    contenu = construire_zip_attributs([(entree("fifo.xml", 0o010644), RAPPORT_A)])

    with pytest.raises(UnsafeArchiveError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "not a regular file" in str(erreur.value)


def test_entree_malformee_refusee():
    contenu = corrompre_entete_local(construire_zip([("rapport.xml", RAPPORT_A)]))

    with pytest.raises(ArchiveError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "corrupted or unreadable" in str(erreur.value)


def test_membre_avec_dtd_refuse():
    contenu = construire_zip([("rapport.xml", RAPPORT_AVEC_DTD)])

    with pytest.raises(ReportParseError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "DTD" in str(erreur.value)


def test_entite_non_declaree_refusee_dans_un_membre():
    contenu = construire_zip([("rapport.xml", fixture("rapport_entite_non_definie.xml"))])

    with pytest.raises(ReportParseError) as erreur:
        import_reports("rapports.zip", contenu)

    assert "undeclared entity" in str(erreur.value)


def test_carre_nul_dans_un_nom_refuse():
    """Limite de test assumée : `zipfile` tronque les noms au caractère NUL.

    À l'écriture comme à la lecture, la bibliothèque standard supprime tout ce
    qui suit le NUL : le cas n'est donc pas représentable de bout en bout. Le
    garde-fou est vérifié directement sur une entrée ZIP fabriquée.
    """
    info = zipfile.ZipInfo(filename="rapport.xml", date_time=(2026, 10, 1, 0, 0, 0))
    info.filename = "rapport\x00.xml"

    with pytest.raises(UnsafeArchiveError) as erreur:
        module_archive._verifier_nom_membre("rapports.zip", info.filename)

    assert "NUL" in str(erreur.value)


def test_les_erreurs_d_archive_sont_des_erreurs_metier():
    for nom, contenu in (
        ("rapport.txt", b"texte"),
        ("rapport.xml", RAPPORT_TRONQUE),
        ("rapports.zip", b"pas une archive"),
    ):
        with pytest.raises(MailGuardError):
            import_reports(nom, contenu)


def test_les_erreurs_conservent_leur_cause():
    with pytest.raises(ArchiveError) as erreur:
        import_reports("rapports.zip", b"pas une archive")

    assert erreur.value.__cause__ is not None
    assert "Traceback" not in str(erreur.value)


def test_l_import_ignore_le_contenu_xml_dans_son_nom_affiche():
    resultat = import_reports("rapport-\xc3\xa9t\xc3\xa9.xml", RAPPORT_A)

    assert resultat.file_name == "rapport-\xc3\xa9t\xc3\xa9.xml"
    assert os.sep not in resultat.file_name