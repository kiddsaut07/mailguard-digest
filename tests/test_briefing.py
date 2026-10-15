"""Tests du briefing français (étape 4).

Les briefings sont produits à partir de rapports synthétiques analysés par le
parseur de production. Les tests vérifient le contenu du texte, son cohérence avec
les métriques déterministes, son reproductibilité et ses interdits.
"""

import re
from pathlib import Path

import pytest

from app.core.briefing import (
    LIMITES_ANALYSE,
    NON_DISPONIBLE,
    construire_briefing,
)
from app.core.parser import parse_dmarc_report
from app.core.rules import analyser, analyser_rapport

CHEMIN_FIXTURES = Path(__file__).parent / "fixtures"

MOTS_INTERDITS = (
    "malveillant",
    "malveillante",
    "frauduleux",
    "frauduleuse",
    "compromission",
    "attaque",
    "nous recommandons",
    "il faut passer",
    "passez à",
    "il est recommandé",
)


def rapport(nom: str):
    """Analyse une fixture synthétique avec le parseur de production."""
    return parse_dmarc_report((CHEMIN_FIXTURES / nom).read_bytes())


def briefing(nom: str):
    """Briefing d'une fixture synthétique unique."""
    return construire_briefing(analyser_rapport(rapport(nom)))


def tout_texte(briefing_construit) -> str:
    """Texte complet d'un briefing, toutes sections confondues."""
    return briefing_construit.texte_complet


# --- Contenu et cohérence avec les métriques ---------------------------------


def test_briefing_contient_les_principales_metriques_calculees():
    construit = briefing("rapport_plusieurs_records.xml")
    texte = tout_texte(construit)

    assert "125 message" in texte
    assert "80.0 %" in texte
    assert "20.0 %" in texte
    assert "quarantine : 100" in texte
    assert "reject : 25" in texte
    assert construit.chiffres_cles[0].mesure == "total_messages"


def test_briefing_chiffres_cles_sont_coherents_avec_les_metriques():
    analyse = analyser_rapport(rapport("rapport_plusieurs_records.xml"))
    construit = construire_briefing(analyse)
    valeurs = {cle.mesure: cle.valeur for cle in construit.chiffres_cles}

    assert valeurs["total_messages"] == str(analyse.metriques.total_messages)
    assert valeurs["nombre_sources"] == str(len(analyse.sources))
    assert analyse.metriques.taux_pass.affichage in valeurs["taux_pass"]


def test_briefing_rapporte_la_periode_et_le_domaine():
    construit = briefing("rapport_valide_sans_namespace.xml")

    assert construit.domaine == "example.com"
    assert "2025-10-01" in construit.periode
    assert "2025-10-02" in construit.periode
    assert construit.organisation == "Example Mail Provider"
    assert construit.identifiant_rapport == "1800000000-aaaa1111"


def test_briefing_signale_les_dispositions_declarees():
    construit = briefing("rapport_plusieurs_records.xml")

    assert "none : 0, quarantine : 100, reject : 25" in tout_texte(construit)


def test_briefing_classe_les_constats_par_niveau():
    construit = briefing("rapport_plusieurs_records.xml")
    niveaux = [observation.niveau for observation in construit.observations]

    assert niveaux[0] == "attention"
    assert "echecs-dmarc-observez" in [obs.identifiant for obs in construit.observations]
    assert set(niveaux) <= {"attention", "info", "indisponible"}


def test_briefing_inclut_les_limites_et_les_points_a_verifier():
    construit = briefing("rapport_plusieurs_records.xml")

    assert list(construit.limites) == list(LIMITES_ANALYSE)
    assert any("198.51.100.30" in point for point in construit.points_a_verifier)


def test_section_a_retenir_ne_contient_que_des_faits_etablis():
    construit = briefing("rapport_plusieurs_records.xml")

    assert len(construit.a_retenir) == 4
    assert construit.a_retenir[0].startswith("125 message")
    assert "80.0 %" in construit.a_retenir[1]
    assert "source" in construit.a_retenir[2]


# --- Données absentes et cas limites -----------------------------------------


def test_briefing_volume_nul_ne_presente_pas_de_taux_inventes():
    analyse = analyser_rapport(rapport("rapport_volume_nul.xml"))
    construit = construire_briefing(analyse)
    texte = tout_texte(construit)

    assert analyse.metriques.taux_pass.valeur is None
    assert "Not calculable" in texte
    assert "0.0 %" not in texte
    assert "100.0 %" not in texte
    assert "cannot be calculated" in texte
    assert "No rate can be calculated" in " ".join(construit.a_retenir)


def test_briefing_champs_absents_signales_sans_invention():
    construit = briefing("rapport_sans_identifiants.xml")
    observations = {obs.identifiant: obs.texte for obs in construit.observations}

    assert construit.domaine == NON_DISPONIBLE
    assert construit.identifiant_rapport == NON_DISPONIBLE
    assert observations["donnee-absente:domaine-publie-absent"].startswith("The published domain is absent")
    assert observations["donnee-absente:identifiant-rapport-absent"].startswith(
        "The report identifier is absent"
    )
    assert any("published domain" in point for point in construit.points_a_verifier)
    assert "example.net" not in tout_texte(construit)


def test_briefing_plusieurs_domaines_sont_listes_et_rattaches():
    analyse = analyser([rapport("rapport_valide_sans_namespace.xml"), rapport("rapport_autre_domaine.xml")])
    construit = construire_briefing(analyse)

    assert "several domains" in construit.domaine
    assert "example.com" in construit.domaine and "example.net" in construit.domaine
    assert any("several published domains" in point for point in construit.points_a_verifier)


def test_briefing_publie_les_politiques_par_contexte():
    analyse = analyser([rapport("rapport_valide_sans_namespace.xml"), rapport("rapport_autre_domaine.xml")])
    construit = construire_briefing(analyse)
    politique = next(cle for cle in construit.chiffres_cles if cle.mesure == "politique_publiee")

    assert "example.com: p=none, sp=quarantine" in politique.valeur
    assert "example.net: p=none" in politique.valeur


def test_briefing_sans_echec_ne_promet_pas_de_securite():
    construit = briefing("rapport_valide_sans_namespace.xml")
    texte = tout_texte(construit)
    sans_echec = next(
        obs for obs in construit.observations if obs.identifiant == "echec-dmarc-non-observe"
    )

    assert "is not a security guarantee" in texte
    assert "does not prove" in sans_echec.limite
    assert "domaine sécurisé" not in texte.lower()


# --- Interdits ---------------------------------------------------------------


def test_briefing_ne_qualifie_jamais_une_adresse():
    for nom in (
        "rapport_plusieurs_records.xml",
        "rapport_dkim_multiples.xml",
        "rapport_valide_sans_namespace.xml",
    ):
        texte = tout_texte(briefing(nom)).lower()
        for mot in MOTS_INTERDITS[:6]:
            assert mot not in texte, f"{nom} contient « {mot} »"


def test_briefing_ne_recommande_pas_de_changement_de_politique():
    for nom in ("rapport_plusieurs_records.xml", "rapport_valide_sans_namespace.xml"):
        texte = tout_texte(briefing(nom)).lower()
        for mot in MOTS_INTERDITS[6:]:
            assert mot not in texte, f"{nom} contient « {mot} »"
        assert "makes no recommendation to change the dmarc policy" in texte


def test_briefing_ne_promet_pas_de_reussite_quand_il_y_a_des_echecs():
    construit = briefing("rapport_plusieurs_records.xml")
    texte = tout_texte(construit)

    assert "25 messages are associated with a DMARC verdict of fail" in texte
    assert "domaine sécurisé" not in texte.lower()


# --- Reproductibilité --------------------------------------------------------


def test_briefing_est_reproductible():
    premier = construire_briefing(analyser_rapport(rapport("rapport_plusieurs_records.xml")))
    second = construire_briefing(analyser_rapport(rapport("rapport_plusieurs_records.xml")))

    assert premier == second
    assert tout_texte(premier) == tout_texte(second)


def test_briefing_est_reproductible_avec_plusieurs_sources():
    analyse = analyser_rapport(rapport("rapport_dkim_multiples.xml"))

    assert tout_texte(construire_briefing(analyse)) == tout_texte(construire_briefing(analyse))


def test_briefing_est_un_objet_immuable():
    construit = briefing("rapport_valide_sans_namespace.xml")

    with pytest.raises(Exception):
        construit.domaine = "example.org"


def test_briefing_ignore_l_ordre_de_constat_de_la_metrique():
    analyse = analyser_rapport(rapport("rapport_plusieurs_records.xml"))
    construit = construire_briefing(analyse)
    identifiants = [observation.identifiant for observation in construit.observations]

    assert len(identifiants) == len(set(identifiants))
    assert re.match(r"^echecs-dmarc-observez$", identifiants[0])