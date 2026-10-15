"""Tests du parseur XML DMARC (étape 2).

Les fixtures de `tests/fixtures/` sont synthétiques : domaines `example.*`,
adresses des plages de documentation RFC 5737 et RFC 3849, aucun rapport client.
Les tests vérifient les valeurs obtenues dans les modèles, pas seulement
l'absence d'exception.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.errors import MailGuardError, ReportParseError, ReportValidationError
from app.core.models import (
    AlignmentMode,
    DkimResult,
    Disposition,
    DmarcEvaluation,
    DmarcPolicy,
    SpfResult,
)
from app.core.parser import parse_dmarc_report

CHEMIN_FIXTURES = Path(__file__).parent / "fixtures"
DEBUT_UTC = datetime(2025, 10, 1, tzinfo=timezone.utc)
FIN_UTC = datetime(2025, 10, 2, tzinfo=timezone.utc)


def charger(nom: str) -> str:
    """Contenu texte d'une fixture XML synthétique."""
    return (CHEMIN_FIXTURES / nom).read_text(encoding="utf-8")


def analyser(nom: str):
    """Analyse une fixture et renvoie le modèle validé."""
    return parse_dmarc_report(charger(nom))


def echouer(nom: str, type_erreur):
    """Analyse une fixture invalide et renvoie l'erreur métier levée."""
    with pytest.raises(type_erreur) as erreur:
        analyser(nom)
    return erreur.value


# --- Documents acceptés ------------------------------------------------------


def test_rapport_valide_sans_namespace():
    rapport = analyser("rapport_valide_sans_namespace.xml")

    assert rapport.version == 1.0
    assert rapport.metadata.org_name == "Example Mail Provider"
    assert rapport.metadata.report_id == "1800000000-aaaa1111"
    assert rapport.metadata.email == "rapports@example.net"
    assert rapport.metadata.extra_contact_info == "https://example.net/rapports"


def test_rapport_valide_sans_namespace_conserve_la_periode_en_utc():
    rapport = analyser("rapport_valide_sans_namespace.xml")

    assert rapport.metadata.date_range.begin == DEBUT_UTC
    assert rapport.metadata.date_range.end == FIN_UTC
    assert rapport.metadata.date_range.duration_seconds == 86400
    assert rapport.metadata.date_range.begin_timestamp == 1759276800


def test_rapport_valide_sans_namespace_conserve_la_politique_publiee():
    rapport = analyser("rapport_valide_sans_namespace.xml")

    assert rapport.policy_published.domain == "example.com"
    assert rapport.policy_published.p is DmarcPolicy.NONE
    assert rapport.policy_published.sp is DmarcPolicy.QUARANTINE
    assert rapport.policy_published.adkim is AlignmentMode.RELAXED
    assert rapport.policy_published.aspf is AlignmentMode.RELAXED
    assert rapport.policy_published.pct == 100


def test_rapport_valide_sans_namespace_detaille_le_record():
    rapport = analyser("rapport_valide_sans_namespace.xml")

    assert len(rapport.records) == 1
    record = rapport.records[0]
    assert record.source_ip == "192.0.2.10"
    assert record.message_count == 42
    assert record.policy_evaluated.disposition is Disposition.NONE
    assert record.policy_evaluated.spf is DmarcEvaluation.PASS
    assert record.policy_evaluated.dkim is DmarcEvaluation.PASS
    assert record.identifiers.header_from == "example.com"
    assert record.policy_evaluated.reason[0].comment == "relais de test"
    assert record.policy_evaluated.reason[0].type == "forwarded"


def test_rapport_valide_sans_namespace_detaille_les_resultats_bruts():
    rapport = analyser("rapport_valide_sans_namespace.xml")

    record = rapport.records[0]
    assert record.auth_results.spf[0].domain == "example.com"
    assert record.auth_results.spf[0].result is SpfResult.PASS
    assert record.auth_results.dkim[0].selector == "sel1"
    assert record.auth_results.dkim[0].result is DkimResult.PASS
    assert rapport.total_messages == 42


def test_rapport_avec_namespace_est_accepte():
    rapport = analyser("rapport_valide_avec_namespace.xml")

    assert rapport.metadata.report_id == "1800000000-bbbb2222"
    assert rapport.metadata.date_range.begin == DEBUT_UTC
    assert rapport.records[0].source_ip == "192.0.2.11"
    assert rapport.records[0].message_count == 7
    assert rapport.records[0].dmarc_pass is True


def test_plusieurs_records_sont_lus_dans_leur_ordre():
    rapport = analyser("rapport_plusieurs_records.xml")

    assert [record.source_ip for record in rapport.records] == [
        "192.0.2.20",
        "198.51.100.30",
        "2001:db8::5",
    ]
    assert [record.message_count for record in rapport.records] == [100, 25, 0]
    assert [record.policy_evaluated.disposition for record in rapport.records] == [
        Disposition.QUARANTINE,
        Disposition.REJECT,
        Disposition.NONE,
    ]


def test_plusieurs_records_somme_total_et_politique_alignement_strict():
    rapport = analyser("rapport_plusieurs_records.xml")

    assert rapport.total_messages == 125
    assert rapport.records[0].dmarc_pass is True
    assert rapport.records[1].dmarc_pass is False
    assert rapport.records[2].dmarc_pass is True
    assert rapport.policy_published.adkim is AlignmentMode.STRICT
    assert rapport.policy_published.aspf is AlignmentMode.STRICT
    assert rapport.policy_published.pct == 50
    assert rapport.policy_published.effective_subdomain_policy is DmarcPolicy.REJECT


def test_record_sans_auth_results_laisse_des_listes_vides():
    rapport = analyser("rapport_plusieurs_records.xml")

    record = rapport.records[1]
    assert record.auth_results.spf == []
    assert record.auth_results.dkim == []
    assert record.identifiers.header_from is None
    assert record.policy_evaluated.disposition is Disposition.REJECT


def test_plusieurs_resultats_dkim_bruts_sont_tous_conserves():
    rapport = analyser("rapport_dkim_multiples.xml")

    record = rapport.records[0]
    assert [resultat.result for resultat in record.auth_results.dkim] == [
        DkimResult.PASS,
        DkimResult.FAIL,
        DkimResult.TEMPERROR,
    ]
    assert [resultat.domain for resultat in record.auth_results.dkim] == [
        "example.com",
        "example.net",
        "example.org",
    ]
    assert record.auth_results.dkim[1].human_result == "signature non valide"
    assert record.auth_results.dkim[2].selector is None


def test_resultats_bruts_absents_ne_remplacent_pas_les_resultats_evalues():
    rapport = analyser("rapport_dkim_multiples.xml")

    record = rapport.records[0]
    assert record.auth_results.spf == []
    assert record.policy_evaluated.smtp_mailfrom == "example.org"
    assert record.policy_evaluated.spf is DmarcEvaluation.FAIL
    assert record.policy_evaluated.dkim is DmarcEvaluation.FAIL
    assert record.dmarc_pass is False


def test_rapport_accepte_les_octets_comme_le_texte():
    contenu = charger("rapport_valide_sans_namespace.xml")

    rapport = parse_dmarc_report(contenu.encode("utf-8"))

    assert rapport.metadata.org_name == "Example Mail Provider"


def test_identifiant_de_rapport_absent_reste_none():
    rapport = analyser("rapport_plusieurs_records.xml")

    assert rapport.metadata.report_id is None
    assert rapport.metadata.email is None


# --- Documents refusés -------------------------------------------------------


def test_xml_tronque_refuse():
    erreur = echouer("rapport_tronque.xml", ReportParseError)

    assert "unreadable" in str(erreur) or "truncated" in str(erreur)


def test_mauvaise_racine_refusee():
    erreur = echouer("rapport_mauvaise_racine.xml", ReportParseError)

    assert "feedback" in str(erreur)
    assert "rapport_dmarc" in str(erreur)


def test_metadonnees_manquantes_refusees():
    erreur = echouer("rapport_sans_metadata.xml", ReportParseError)

    assert "report_metadata" in str(erreur)


def test_politique_manquante_refusee():
    erreur = echouer("rapport_sans_politique.xml", ReportParseError)

    assert "policy_published" in str(erreur)


def test_rapport_sans_record_refuse():
    erreur = echouer("rapport_sans_record.xml", ReportParseError)

    assert "record" in str(erreur)


def test_timestamp_non_entier_refuse():
    erreur = echouer("rapport_timestamp_non_entier.xml", ReportValidationError)

    assert "timestamp" in str(erreur)


def test_timestamp_negatif_refuse():
    erreur = echouer("rapport_timestamp_negatif.xml", ReportValidationError)

    assert "cannot be a negative timestamp" in str(erreur)


def test_periode_inversee_refusee():
    erreur = echouer("rapport_periode_inversee.xml", ReportValidationError)

    assert "inconsistent reporting period" in str(erreur)


def test_ip_invalide_refusee():
    erreur = echouer("rapport_ip_invalide.xml", ReportValidationError)

    assert "records.0.source_ip" in str(erreur)
    assert "invalid IP address" in str(erreur)


def test_compteur_absent_refuse():
    erreur = echouer("rapport_compteur_absent.xml", ReportValidationError)

    assert "count" in str(erreur)
    assert "is absent" in str(erreur)


def test_compteur_non_numerique_refuse():
    erreur = echouer("rapport_compteur_non_numerique.xml", ReportValidationError)

    assert "count" in str(erreur)
    assert "must be a positive integer" in str(erreur)


def test_compteur_negatif_refuse():
    erreur = echouer("rapport_compteur_negatif.xml", ReportValidationError)

    assert "count" in str(erreur)
    assert "cannot be negative" in str(erreur)


def test_disposition_hors_nomenclature_refusee():
    erreur = echouer("rapport_disposition_invalide.xml", ReportValidationError)

    assert "disposition" in str(erreur)
    assert "none" in str(erreur)


def test_resultat_evalue_hors_pass_fail_refuse():
    erreur = echouer("rapport_resultat_evalue_invalide.xml", ReportValidationError)

    assert "dkim" in str(erreur)
    assert "pass" in str(erreur) and "fail" in str(erreur)


def test_politique_publiee_hors_nomenclature_refusee():
    erreur = echouer("rapport_politique_invalide.xml", ReportValidationError)

    assert "p" in str(erreur)
    assert "quarantine" in str(erreur)


def test_alignement_hors_nomenclature_refuse():
    erreur = echouer("rapport_alignement_invalide.xml", ReportValidationError)

    assert "adkim" in str(erreur)


def test_pourcentage_hors_bornes_refuse():
    erreur = echouer("rapport_pourcentage_invalide.xml", ReportValidationError)

    assert "between 0 and 100" in str(erreur)


# --- Sécurité du lecteur XML -------------------------------------------------


def test_dtd_et_entite_interne_refusees():
    erreur = echouer("rapport_avec_dtd.xml", ReportParseError)

    assert "DTD" in str(erreur)


def test_entite_non_declaree_refusee():
    erreur = echouer("rapport_entite_non_definie.xml", ReportParseError)

    assert "undeclared entity" in str(erreur)


def test_les_erreurs_heritent_de_une_erreur_metier_unique():
    for nom in ("rapport_tronque.xml", "rapport_ip_invalide.xml"):
        erreur = echouer(nom, MailGuardError)
        assert str(erreur)
        assert "Traceback" not in str(erreur)


def test_les_erreurs_conservent_leur_cause_interne():
    erreur = echouer("rapport_ip_invalide.xml", ReportValidationError)

    assert erreur.__cause__ is not None