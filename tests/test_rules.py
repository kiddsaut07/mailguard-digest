"""Tests du moteur de règles DMARC (étape 4).

Tous les rapports proviennent des fixtures synthétiques de `tests/fixtures/`,
analysées par le parseur de production : aucun objet de démonstration n'est
fabriqué pour l'interface, et aucun rapport client réel n'est utilisé.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.models import (
    AlignmentMode,
    DateRange,
    DmarcPolicy,
    DmarcReport,
    PolicyEvaluated,
    PublishedPolicy,
    Record,
    ReportMetadata,
)
from app.core.parser import parse_dmarc_report
from app.core.rules import (
    CategorieIncoherence,
    NiveauConstat,
    RepartitionDispositions,
    Taux,
    analyser,
    analyser_rapport,
    detecter_incoherences,
    verifier_coherence_dispositions,
)

CHEMIN_FIXTURES = Path(__file__).parent / "fixtures"
DEBUT = datetime(2025, 10, 1, tzinfo=timezone.utc)
FIN = datetime(2025, 10, 2, tzinfo=timezone.utc)


def rapport(nom: str) -> DmarcReport:
    """Analyse une fixture synthétique avec le parseur de production."""
    return parse_dmarc_report((CHEMIN_FIXTURES / nom).read_bytes())


def identifiants_constats(analyse) -> list[str]:
    """Identifiants des constats, dans leur ordre de production."""
    return [constat.identifiant for constat in analyse.constats]


# --- Vue globale ------------------------------------------------------------


def test_rapport_valide_sans_echecs_fournit_les_metriques_de_base():
    analyse = analyser_rapport(rapport("rapport_valide_sans_namespace.xml"))
    metriques = analyse.metriques

    assert metriques.total_messages == 42
    assert metriques.nombre_records == 1
    assert metriques.nombre_rapports == 1
    assert metriques.messages_pass == 42
    assert metriques.messages_fail == 0
    assert metriques.taux_pass.valeur == 100.0
    assert metriques.taux_fail.valeur == 0.0
    assert metriques.domaines_publies == ["example.com"]
    assert analyse.total_messages == 42


def test_metriques_par_rapport_conserver_identifiant_et_politique():
    analyse = analyser_rapport(rapport("rapport_valide_sans_namespace.xml"))
    rapport_analyse = analyse.rapports[0]

    assert rapport_analyse.contexte.identifiant_rapport == "1800000000-aaaa1111"
    assert rapport_analyse.contexte.organisation == "Example Mail Provider"
    assert rapport_analyse.politique_publiee is DmarcPolicy.NONE
    assert rapport_analyse.politique_sous_domaines_publiee is DmarcPolicy.QUARANTINE
    assert rapport_analyse.politique_sous_domaines_effective is DmarcPolicy.QUARANTINE
    assert rapport_analyse.alignement_dkim is AlignmentMode.RELAXED
    assert rapport_analyse.pourcentage_politique == 100
    assert rapport_analyse.date_debut == DEBUT
    assert rapport_analyse.date_fin == FIN
    assert rapport_analyse.duree_secondes == 86400


def test_absence_de_sp_est_consignee_comme_absente_et_non_inventee():
    analyse = analyser_rapport(rapport("rapport_valide_avec_namespace.xml"))
    rapport_analyse = analyse.rapports[0]

    assert rapport_analyse.politique_sous_domaines_publiee is None
    assert rapport_analyse.politique_sous_domaines_effective is DmarcPolicy.NONE


def test_taux_sont_ponderes_par_les_compteurs_et_non_moyennes():
    analyse = analyser_rapport(rapport("rapport_plusieurs_records.xml"))
    metriques = analyse.metriques

    assert metriques.total_messages == 125
    assert metriques.messages_pass == 100
    assert metriques.messages_fail == 25
    assert metriques.taux_pass.numerateur == 100
    assert metriques.taux_pass.denominateur == 125
    assert metriques.taux_pass.valeur == pytest.approx(80.0)


def test_dispositions_sont_agregees_sans_confusion_avec_la_politique_publiee():
    analyse = analyser_rapport(rapport("rapport_plusieurs_records.xml"))

    assert analyse.metriques.dispositions.none == 0
    assert analyse.metriques.dispositions.quarantine == 100
    assert analyse.metriques.dispositions.reject == 25
    assert analyse.metriques.dispositions.total == 125
    assert analyse.rapports[0].politique_publiee is DmarcPolicy.QUARANTINE


def test_disposition_differe_de_la_politique_publiee_est_comptee_telle_quelle():
    """Le rapport p=none déclare un enregistrement en reject : les deux sont conservés."""
    analyse = analyser_rapport(rapport("rapport_valide_avec_namespace.xml"))
    source = analyse.sources[0]

    assert analyse.rapports[0].politique_publiee is DmarcPolicy.NONE
    assert analyse.metriques.dispositions.total == 7
    assert analyse.metriques.dispositions.affichage.startswith("none : ")


# --- Sources -----------------------------------------------------------------


def test_plusieurs_records_meme_ip_sont_agreges_sans_perte():
    analyse = analyser_rapport(rapport("rapport_plusieurs_records.xml"))
    source = analyse.sources[0]

    assert source.adresse_ip == "192.0.2.20"
    assert source.total_messages == 100
    assert source.messages_pass == 100
    assert source.messages_fail == 0
    assert source.taux_pass.valeur == 100.0
    assert source.indices_records == [0]


def test_source_avec_plusieurs_records_conserve_le_detail_de_chaque_record():
    modele = rapport("rapport_plusieurs_records.xml")
    fusion = DmarcReport(
        version=1.0,
        metadata=modele.metadata,
        policy_published=modele.policy_published,
        records=[
            Record(
                source_ip="192.0.2.99",
                message_count=10,
                policy_evaluated=PolicyEvaluated(disposition="none", spf="pass", dkim="fail"),
            ),
            Record(
                source_ip="192.0.2.99",
                message_count=5,
                policy_evaluated=PolicyEvaluated(disposition="reject", spf="fail", dkim="fail"),
            ),
        ],
    )

    analyse = analyser_rapport(fusion)

    assert analyse.total_messages == 15
    source = analyse.sources[0]
    assert source.adresse_ip == "192.0.2.99"
    assert source.nombre_records == 2
    assert source.total_messages == 15
    assert source.messages_pass == 10
    assert source.messages_fail == 5
    assert source.dispositions.reject == 5
    assert source.indices_records == [0, 1]


def test_sources_triees_par_volume_decroissant_puis_adresse():
    analyse = analyser_rapport(rapport("rapport_plusieurs_records.xml"))

    assert [source.adresse_ip for source in analyse.sources] == [
        "192.0.2.20",
        "198.51.100.30",
        "2001:db8::5",
    ]


def test_verdis_evalues_sont_repartis_en_messages_par_mecanisme():
    analyse = analyser_rapport(rapport("rapport_plusieurs_records.xml"))
    source = next(s for s in analyse.sources if s.adresse_ip == "192.0.2.20")

    assert source.verdis_spf_evalues.reussite == 100
    assert source.verdis_spf_evalues.echec == 0
    assert source.verdis_dkim_evalues.reussite == 0
    assert source.verdis_dkim_evalues.echec == 100


def test_resultats_bruts_sont_conserves_a_part_des_verdicts_evalues():
    analyse = analyser_rapport(rapport("rapport_dkim_multiples.xml"))
    source = analyse.sources[0]

    assert [(r.mecanisme, r.resultat, r.occurrences) for r in source.resultats_bruts] == [
        ("dkim", "fail", 1),
        ("dkim", "pass", 1),
        ("dkim", "temperror", 1),
    ]
    assert source.verdis_dkim_evalues.reussite == 0
    assert source.verdis_dkim_evalues.echec == 9
    assert source.messages_pass == 0
    assert source.messages_fail == 9


def test_domaine_en_tete_conserve_sans_fusionner_les_contextes():
    analyse = analyser_rapport(rapport("rapport_dkim_multiples.xml"))

    assert analyse.sources[0].domaines_en_tete == []


# --- Cas limites -------------------------------------------------------------


def test_volume_total_nul_laisse_les_taux_indisponibles():
    analyse = analyser_rapport(rapport("rapport_volume_nul.xml"))

    assert analyse.metriques.total_messages == 0
    assert analyse.metriques.taux_pass.valeur is None
    assert analyse.metriques.taux_pass.disponible is False
    assert analyse.metriques.taux_pass.affichage == "Not calculable (no messages counted)"
    assert analyse.metriques.taux_fail.valeur is None


def test_taux_non_arrondi_en_interne_mais_arrondi_a_l_affichage():
    rapport_tiers = DmarcReport(
        metadata=ReportMetadata(
            org_name="Exemple",
            date_range=DateRange(begin=DEBUT, end=FIN),
        ),
        policy_published=PublishedPolicy(p="none"),
        records=[
            Record(
                source_ip="192.0.2.77",
                message_count=1,
                policy_evaluated=PolicyEvaluated(disposition="none", spf="pass", dkim="pass"),
            ),
            Record(
                source_ip="192.0.2.78",
                message_count=2,
                policy_evaluated=PolicyEvaluated(disposition="none", spf="fail", dkim="fail"),
            ),
        ],
    )

    analyse = analyser_rapport(rapport_tiers)

    assert analyse.metriques.taux_pass.valeur == pytest.approx(100 / 3)
    assert analyse.metriques.taux_pass.affichage == "33.3 %"


def test_valeurs_optionnelles_absentes_sont_conservees_comme_absentes():
    analyse = analyser_rapport(rapport("rapport_sans_identifiants.xml"))

    assert analyse.metriques.domaines_publies == []
    assert analyse.rapports[0].contexte.identifiant_rapport is None
    assert analyse.rapports[0].contexte.organisation == "Test provider without identifier"


def test_plusieurs_rapports_de_domaines_differents_ne_sont_pas_fusionnes():
    analyse = analyser([rapport("rapport_plusieurs_records.xml"), rapport("rapport_autre_domaine.xml")])

    assert analyse.metriques.nombre_rapports == 2
    assert analyse.metriques.total_messages == 136
    assert analyse.metriques.messages_pass == 111
    assert analyse.metriques.messages_fail == 25
    assert analyse.metriques.domaines_publies == ["example.com", "example.net"]
    assert len(analyse.sources) == 4


def test_meme_adresse_dans_deux_rapports_conserve_deux_vues():
    analyse = analyser([rapport("rapport_plusieurs_records.xml"), rapport("rapport_autre_domaine.xml")])
    memes_adresses = [s for s in analyse.sources if s.adresse_ip == "192.0.2.20"]

    assert len(memes_adresses) == 2
    assert {source.contexte.domaine_publie for source in memes_adresses} == {
        "example.com",
        "example.net",
    }


def test_taux_refuse_un_denominateur_negatif():
    with pytest.raises(ValueError):
        Taux.calculer(1, -1)


def test_repartition_dispositions_refuse_un_champ_inconnu():
    with pytest.raises(ValidationError):
        RepartitionDispositions(none=1, quarantine=1, reject=1, total=99)


# --- Constats ----------------------------------------------------------------


def test_rapport_sans_echec_produit_un_constat_neutre():
    analyse = analyser_rapport(rapport("rapport_valide_sans_namespace.xml"))

    assert "echec-dmarc-non-observe" in identifiants_constats(analyse)
    constat = next(c for c in analyse.constats if c.identifiant == "echec-dmarc-non-observe")
    assert constat.niveau is NiveauConstat.INFO
    assert constat.mesures["messages_pass"] == 42
    assert "does not prove" in constat.limites


def test_rapport_avec_echecs_produit_un_constat_d_attention():
    analyse = analyser_rapport(rapport("rapport_plusieurs_records.xml"))

    constat = next(c for c in analyse.constats if c.identifiant == "echecs-dmarc-observez")
    assert constat.niveau is NiveauConstat.ATTENTION
    assert constat.mesures["messages_fail"] == 25
    assert constat.mesures["taux_fail"] == pytest.approx(20.0)


def test_source_avec_echecs_est_citee_sans_etre_qualifiee():
    analyse = analyser_rapport(rapport("rapport_plusieurs_records.xml"))

    constat = next(c for c in analyse.constats if c.identifiant == "sources-avec-echecs-dmarc")
    assert constat.sources == ["198.51.100.30"]
    assert constat.mesures["nombre_sources"] == 1
    assert "is not proof" in constat.limites
    assert "malveillante" not in constat.description


def test_politique_en_mode_surveillance_est_decrite_sans_recommandation():
    analyse = analyser_rapport(rapport("rapport_valide_sans_namespace.xml"))

    constat = next(
        c for c in analyse.constats if c.identifiant == "politique-en-mode-surveillance"
    )
    assert constat.niveau is NiveauConstat.INFO
    assert "p=none" in constat.description
    assert "no recommendation" in constat.limites


def test_politique_publiee_sans_p_none_ne_produit_pas_le_constat_de_surveillance():
    analyse = analyser_rapport(rapport("rapport_plusieurs_records.xml"))

    assert "politique-en-mode-surveillance" not in identifiants_constats(analyse)


def test_volume_nul_produit_un_constat_de_donnees_indisponibles():
    analyse = analyser_rapport(rapport("rapport_volume_nul.xml"))

    assert "volume-total-nul" in [inco.identifiant for inco in analyse.incoherences]
    assert "taux-indisponible" in identifiants_constats(analyse)
    constat = next(c for c in analyse.constats if c.identifiant == "taux-indisponible")
    assert constat.niveau is NiveauConstat.INFORMATION_INDISPONIBLE


def test_donnees_absentes_produisent_des_constats_dedies():
    analyse = analyser_rapport(rapport("rapport_sans_identifiants.xml"))
    identifiants = identifiants_constats(analyse)

    assert "donnee-absente:domaine-publie-absent" in identifiants
    assert "donnee-absente:identifiant-rapport-absent" in identifiants
    constat = next(
        c for c in analyse.constats if c.identifiant == "donnee-absente:domaine-publie-absent"
    )
    assert constat.niveau is NiveauConstat.INFORMATION_INDISPONIBLE


def test_identifiants_et_ordre_des_constats_sont_stables():
    analyse = analyser_rapport(rapport("rapport_plusieurs_records.xml"))

    assert identifiants_constats(analyse) == [
        "volume-observe",
        "echecs-dmarc-observez",
        "sources-avec-echecs-dmarc",
        "dispositions-observees",
        "politique-sous-domaines-declaree",
        "donnee-absente:identifiant-rapport-absent",
        "donnee-inhabituelle:record-sans-volume",
    ]


def test_constats_par_niveau_regroupent_sans_perte():
    analyse = analyser_rapport(rapport("rapport_plusieurs_records.xml"))
    groupes = analyse.constats_par_niveau

    assert sum(len(valeurs) for valeurs in groupes.values()) == len(analyse.constats)
    assert len(groupes[NiveauConstat.ATTENTION]) == 2


# --- Incohérences ------------------------------------------------------------


def test_incoherence_de_dispositions_est_detectee_par_la_fonction_du_controle():
    """Le contrôle est structurellement inatteignable après validation des modèles.

    Il est donc exercé directement sur des valeurs incohérentes, sans affaiblir
    les modèles ni la validation de production.
    """
    incoherent = verifier_coherence_dispositions(
        total_messages=100,
        dispositions=RepartitionDispositions(none=10, quarantine=0, reject=0),
        contexte="rapport de test",
    )

    assert incoherent is not None
    assert incoherent.identifiant == "dispositions-incoherentes"
    assert incoherent.categorie is CategorieIncoherence.INCOHERENCE
    assert "10" in incoherent.description and "100" in incoherent.description


def test_controle_dispositions_satisfait_ne_releve_rien():
    coherent = verifier_coherence_dispositions(
        total_messages=10, dispositions=RepartitionDispositions(none=4, quarantine=6, reject=0)
    )

    assert coherent is None


def test_les_contradictions_ne_survivent_pas_a_la_validation_des_modeles():
    rapport_valide = rapport("rapport_valide_sans_namespace.xml")

    releves = detecter_incoherences([rapport_valide])

    assert not [inco for inco in releves if inco.categorie is CategorieIncoherence.INCOHERENCE]


def test_donnees_inhabituelles_sont_signalees_sans_rejet():
    analyse = analyser_rapport(rapport("rapport_plusieurs_records.xml"))
    inhabituelles = [
        inco
        for inco in analyse.incoherences
        if inco.categorie is CategorieIncoherence.DONNEE_INHABITUELLE
    ]

    assert [inco.identifiant for inco in inhabituelles] == ["record-sans-volume"]
    assert "2001:db8::5" in inhabituelles[0].description
    assert analyse.total_messages == 125


def test_echec_massif_n_est_pas_qualifie_d_attaque():
    analyse = analyser_rapport(rapport("rapport_plusieurs_records.xml"))
    descriptions = " ".join(constat.description for constat in analyse.constats)

    assert "25 messages" in descriptions
    for mot in ("attaque", "malveillant", "frauduleux", "compromis"):
        assert mot not in descriptions.lower()

    sources = next(c for c in analyse.constats if c.identifiant == "sources-avec-echecs-dmarc")
    assert "is not proof" in sources.limites


def test_contextes_policiels_multiples_signales_a_l_import():
    analyse = analyser([rapport("rapport_valide_sans_namespace.xml"), rapport("rapport_autre_domaine.xml")])
    incoherences = [inco.identifiant for inco in analyse.incoherences]

    assert "contextes-policiels-multiples" in incoherences


def test_analyse_unique_ne_signale_pas_de_contexte_multiples():
    analyse = analyser_rapport(rapport("rapport_valide_sans_namespace.xml"))

    assert "contextes-policiels-multiples" not in [inco.identifiant for inco in analyse.incoherences]
    assert analyse.a_des_incoherences is False


def test_resultats_immuables():
    analyse = analyser_rapport(rapport("rapport_valide_sans_namespace.xml"))

    with pytest.raises(ValidationError):
        analyse.metriques.total_messages = 999