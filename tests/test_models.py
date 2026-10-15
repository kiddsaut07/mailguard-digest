"""Tests unitaires des modèles de données (étape 1).

Toutes les données sont synthétiques : domaines `example.*` et adresses de la
plage de documentation RFC 5737 / RFC 3849. Aucun rapport client réel.
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.core.models import (
    AlignmentMode,
    DkimResult,
    Disposition,
    DmarcEvaluation,
    DmarcPolicy,
    DmarcReport,
    PolicyEvaluated,
    PublishedPolicy,
    Record,
    SpfResult,
)

DEBUT = datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)
FIN = DEBUT + timedelta(days=1)


def donnees_metadata(**changements) -> dict:
    """Métadonnées synthétiques valides, surchargeables."""
    donnees = {
        "org_name": "Example Mail Provider",
        "report_id": "1234567890abcdef",
        "email": "rapports@example.net",
        "date_range": {"begin": DEBUT, "end": FIN},
    }
    donnees.update(changements)
    return donnees


def donnees_policy_evaluated(**changements) -> dict:
    """Bloc `policy_evaluated` synthétique valide, surchargeable."""
    donnees = {
        "disposition": "none",
        "spf": "pass",
        "dkim": "pass",
    }
    donnees.update(changements)
    return donnees


def donnees_record(**changements) -> dict:
    """Record synthétique valide, surchargeable."""
    donnees = {
        "source_ip": "192.0.2.10",
        "message_count": 100,
        "policy_evaluated": donnees_policy_evaluated(),
    }
    donnees.update(changements)
    return donnees


def donnees_rapport(**changements) -> dict:
    """Rapport synthétique valide minimal, surchargeable."""
    donnees = {
        "version": 1.0,
        "metadata": donnees_metadata(),
        "policy_published": {"p": "none"},
        "records": [donnees_record()],
    }
    donnees.update(changements)
    return donnees


# --- Objets valides ----------------------------------------------------------


def test_rapport_complet_est_valide():
    rapport = DmarcReport(**donnees_rapport())

    assert rapport.metadata.org_name == "Example Mail Provider"
    assert rapport.policy_published.p is DmarcPolicy.NONE
    assert len(rapport.records) == 1
    assert rapport.records[0].message_count == 100
    assert rapport.total_messages == 100
    assert rapport.version == 1.0


def test_rapport_multiples_records_avec_ipv4_et_ipv6():
    rapport = DmarcReport(
        **donnees_rapport(
            records=[
                donnees_record(source_ip="192.0.2.10", message_count=7),
                donnees_record(source_ip="198.51.100.20", message_count=3),
                donnees_record(source_ip="2001:db8::1", message_count=0),
            ]
        )
    )

    assert rapport.total_messages == 10
    assert rapport.records[2].source_ip == "2001:db8::1"
    assert rapport.records[2].message_count == 0


def test_adresse_ipv6_est_normalisee_en_forme_canonique():
    rapport = DmarcReport(**donnees_rapport(records=[donnees_record(source_ip="2001:0DB8:0000:0000:0000:0000:0000:0001")]))

    assert rapport.records[0].source_ip == "2001:db8::1"


def test_resultats_bruts_spf_et_dkim_sont_conserves_separement():
    rapport = DmarcReport(
        **donnees_rapport(
            records=[
                donnees_record(
                    policy_evaluated=donnees_policy_evaluated(spf="fail", dkim="pass"),
                    auth_results={
                        "spf": [{"domain": "example.com", "result": "softfail"}],
                        "dkim": [
                            {
                                "domain": "example.com",
                                "selector": "s1",
                                "result": "temperror",
                                "human_result": "erreur temporaire",
                            }
                        ],
                    },
                )
            ]
        )
    )

    record = rapport.records[0]
    assert record.auth_results.spf[0].result is SpfResult.SOFTFAIL
    assert record.auth_results.dkim[0].result is DkimResult.TEMPERROR
    assert record.auth_results.dkim[0].human_result == "erreur temporaire"
    assert record.policy_evaluated.dkim is DmarcEvaluation.PASS


def test_raisons_et_identifiants_sont_acceptes():
    rapport = DmarcReport(
        **donnees_rapport(
            records=[
                donnees_record(
                    policy_evaluated={
                        "disposition": "quarantine",
                        "spf": "fail",
                        "dkim": "fail",
                        "reason": [
                            {"type": "forwarded", "comment": "relais connu"},
                            {"type": "other"},
                        ],
                    },
                    identifiers={
                        "header_from": "example.com",
                        "envelope_from": "example.com",
                        "envelope_to": None,
                    },
                )
            ]
        )
    )

    record = rapport.records[0]
    assert len(record.policy_evaluated.reason) == 2
    assert record.policy_evaluated.reason[0].comment == "relais connu"
    assert record.identifiers.header_from == "example.com"


def test_valeurs_par_defaut_du_standard_pour_la_politique():
    politique = PublishedPolicy(p="reject")

    assert politique.adkim is AlignmentMode.RELAXED
    assert politique.aspf is AlignmentMode.RELAXED
    assert politique.pct == 100
    assert politique.domain is None
    assert politique.sp is None


def test_politique_sous_domaine_absente_reprend_la_politique_publiee():
    sans_sp = PublishedPolicy(p="quarantine")
    avec_sp = PublishedPolicy(p="none", sp="reject")

    assert sans_sp.effective_subdomain_policy is DmarcPolicy.QUARANTINE
    assert avec_sp.effective_subdomain_policy is DmarcPolicy.REJECT


def test_identifiant_de_rapport_absent_reste_absent():
    rapport = DmarcReport(**donnees_rapport(metadata=donnees_metadata(report_id=None)))

    assert rapport.metadata.report_id is None


def test_timestamps_unix_de_la_periode_sont_reconstitues():
    rapport = DmarcReport(**donnees_rapport())

    assert rapport.metadata.date_range.begin == DEBUT
    assert rapport.metadata.date_range.end == FIN
    assert rapport.metadata.date_range.duration_seconds == 86400
    assert rapport.metadata.date_range.begin_timestamp == int(DEBUT.timestamp())
    assert rapport.metadata.date_range.end_timestamp == int(FIN.timestamp())


def test_datetime_non_utc_est_converti_en_utc():
    rapport = DmarcReport(
        **donnees_rapport(
            metadata={
                "org_name": "Exemple",
                "date_range": {
                    "begin": datetime(2026, 10, 1, 2, 0, 0, tzinfo=timezone(timedelta(hours=2))),
                    "end": datetime(2026, 10, 2, 0, 0, 0, tzinfo=timezone.utc),
                },
            }
        )
    )

    assert rapport.metadata.date_range.begin == DEBUT
    assert rapport.metadata.date_range.begin.tzinfo is timezone.utc


# --- Séparation résultats bruts / résultats évalués -------------------------


def test_dmarc_passe_si_le_spf_evalue_passe_meme_avec_dkim_echoue():
    record = Record(
        **donnees_record(
            policy_evaluated=donnees_policy_evaluated(spf="pass", dkim="fail"),
            auth_results={"spf": [{"domain": "example.com", "result": "pass"}]},
        )
    )

    assert record.dmarc_pass is True


def test_dmarc_echoue_si_les_deux_resultats_evalues_echouent():
    record = Record(
        **donnees_record(policy_evaluated=donnees_policy_evaluated(spf="fail", dkim="fail"))
    )

    assert record.dmarc_pass is False


def test_resultat_brut_pass_n_est_pas_un_dmarc_pass():
    """Un alignement absent donne un résultat évalué `fail` malgré un brut `pass`."""
    record = Record(
        **donnees_record(
            policy_evaluated=donnees_policy_evaluated(spf="fail", dkim="fail"),
            auth_results={
                "spf": [{"domain": "example.org", "result": "pass"}],
                "dkim": [{"domain": "example.org", "result": "pass", "selector": "s1"}],
            },
        )
    )

    assert record.auth_results.spf[0].result is SpfResult.PASS
    assert record.policy_evaluated.spf is DmarcEvaluation.FAIL
    assert record.dmarc_pass is False


# --- Valeurs refusées --------------------------------------------------------


def test_organisation_absente_refusee():
    with pytest.raises(ValidationError):
        DmarcReport(**donnees_rapport(metadata=donnees_metadata(org_name=None)))


def test_politique_publiee_absente_refusee():
    with pytest.raises(ValidationError):
        DmarcReport(**donnees_rapport(policy_published={}))


def test_politique_hors_nomenclature_refusee():
    with pytest.raises(ValidationError):
        PublishedPolicy(p="block")


def test_disposition_hors_nomenclature_refusee():
    with pytest.raises(ValidationError):
        PolicyEvaluated(disposition="drop", spf="pass", dkim="pass")


def test_resultat_evalue_hors_pass_fail_refuse():
    with pytest.raises(ValidationError):
        PolicyEvaluated(disposition="none", spf="softfail", dkim="pass")


def test_resultat_dkim_evalue_neutral_refuse():
    with pytest.raises(ValidationError):
        PolicyEvaluated(disposition="none", spf="pass", dkim="neutral")


def test_raison_hors_nomenclature_refusee():
    with pytest.raises(ValidationError):
        PolicyEvaluated(
            disposition="none", spf="pass", dkim="pass", reason=[{"type": "pirate"}]
        )


def test_pourcentage_hors_bornes_refuse():
    with pytest.raises(ValidationError):
        PublishedPolicy(p="none", pct=101)


def test_pourcentage_negatif_refuse():
    with pytest.raises(ValidationError):
        PublishedPolicy(p="none", pct=-1)


def test_alignement_inconnu_refuse():
    with pytest.raises(ValidationError):
        PublishedPolicy(p="none", adkim="lax")


# --- Compteurs ---------------------------------------------------------------


def test_compteur_negatif_refuse():
    with pytest.raises(ValidationError):
        Record(**donnees_record(message_count=-1))


def test_compteur_texte_refuse():
    with pytest.raises(ValidationError):
        Record(**donnees_record(message_count="100"))


def test_compteur_flottant_refuse():
    with pytest.raises(ValidationError):
        Record(**donnees_record(message_count=100.5))


def test_compteur_booleen_refuse():
    with pytest.raises(ValidationError):
        Record(**donnees_record(message_count=True))


def test_compteur_zero_accepte():
    record = Record(**donnees_record(message_count=0))

    assert record.message_count == 0
    assert record.dmarc_pass is True


# --- Adresses IP -------------------------------------------------------------


def test_adresse_ip_invalide_refusee():
    with pytest.raises(ValidationError):
        Record(**donnees_record(source_ip="192.0.2.300"))


def test_adresse_ip_non_numerique_refusee():
    with pytest.raises(ValidationError):
        Record(**donnees_record(source_ip="inconnu.example.com"))


# --- Cohérence du rapport ----------------------------------------------------


def test_periode_inversee_refusee():
    with pytest.raises(ValidationError):
        DmarcReport(
            **donnees_rapport(
                metadata=donnees_metadata(date_range={"begin": FIN, "end": DEBUT})
            )
        )


def test_date_sans_fuseau_horaire_refusee():
    with pytest.raises(ValidationError):
        DmarcReport(
            **donnees_rapport(
                metadata=donnees_metadata(
                    date_range={
                        "begin": datetime(2026, 10, 1),
                        "end": datetime(2026, 10, 2),
                    }
                )
            )
        )


def test_rapport_sans_record_refuse():
    with pytest.raises(ValidationError):
        DmarcReport(**donnees_rapport(records=[]))


def test_record_sans_resultats_evalues_refuse():
    with pytest.raises(ValidationError):
        Record(source_ip="192.0.2.10", message_count=5)


def test_champ_inconnu_refuse_dans_un_record():
    with pytest.raises(ValidationError) as erreur:
        Record(**donnees_record(spf_evalue="pass"))

    assert "spf_evalue" in str(erreur.value)


def test_champ_inconnu_refuse_dans_les_metadonnees():
    with pytest.raises(ValidationError) as erreur:
        DmarcReport(**donnees_rapport(metadata=donnees_metadata(contact="a@example.net")))

    assert "contact" in str(erreur.value)


def test_disposition_est_un_type_different_de_la_politique_publiee():
    assert Disposition.REJECT == "reject"
    assert Disposition.REJECT is not DmarcPolicy.REJECT