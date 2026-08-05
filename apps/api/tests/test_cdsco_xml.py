import os
import xml.etree.ElementTree as ET

import pytest

from app.services.cdsco_xml import DOCTYPE, build_ichicsr_xml, validate_ichicsr


def _base_record(**over):
    rec = {
        "product": "Amoxicillin",
        "active_ingredients": ["amoxicillin", "clavulanic acid"],
        "pmid": "12345678",
        "doi": "10.1000/xyz",
        "title": "Anaphylaxis after amoxicillin: a case report.",
        "journal": "Indian J Pharmacol",
        "publication_date": "2026-03-01",
        "adverse_events": ["Anaphylactic reaction"],
        "suspect_products": [],
        "seriousness": "serious_hospitalization",
        "patient_sex": "female",
        "patient_age_range": "34",
        "patient_country": "IN",
        "rationale": "Valid ICSR: identifiable patient, suspect drug, event.",
        "reviewer": "reviewer@litmon.local",
        "decision_date": "2026-03-10T08:00:00",
        "ai_model_id": "claude-haiku-4-5",
        "ai_composite": 0.91,
    }
    rec.update(over)
    return rec


def _parse(records):
    return ET.fromstring(build_ichicsr_xml(records))


def test_document_is_well_formed_e2b_r2_envelope():
    root = _parse([_base_record()])
    assert root.tag == "ichicsr"
    header = root.find("ichicsrmessageheader")
    assert header.findtext("messagetype") == "ichicsr"
    assert header.findtext("messageformatversion") == "2.1"
    assert header.findtext("messagereceiveridentifier") == "NCC-PvPI-CDSCO"
    assert len(root.findall("safetyreport")) == 1


def test_active_ingredients_become_activesubstancename():
    """The API tags are what CDSCO needs in G.k.2.3.r."""
    root = _parse([_base_record()])
    names = [e.text for e in root.iter("activesubstancename")]
    assert names == ["amoxicillin", "clavulanic acid"]
    # Falls back to the monitored product when no suspect product recorded.
    assert root.find(".//medicinalproduct").text == "Amoxicillin"


def test_seriousness_underscore_form_is_serious_and_expedited():
    root = _parse([_base_record(seriousness="serious_hospitalization")])
    sr = root.find("safetyreport")
    assert sr.findtext("serious") == "1"
    assert sr.findtext("seriousnesshospitalization") == "1"
    assert sr.findtext("fulfillexpeditecriteria") == "1"


def test_non_serious_variants_are_not_expedited():
    """Regression: `non_serious` must not be read as serious — that would
    wrongly flag a case as expedited to the regulator."""
    for value in ("non_serious", "non-serious", "Non Serious", "not serious", ""):
        root = _parse([_base_record(seriousness=value)])
        sr = root.find("safetyreport")
        assert sr.findtext("serious") == "2", value
        assert sr.findtext("fulfillexpeditecriteria") == "2", value
        assert sr.find("seriousnessdeath") is None, value


def test_sex_and_age_coding():
    root = _parse([_base_record()])
    patient = root.find(".//patient")
    assert patient.findtext("patientsex") == "2"  # female
    assert patient.findtext("patientonsetage") == "34"
    assert patient.findtext("patientonsetageunit") == "801"


def test_age_range_is_not_invented_as_a_number():
    """Reviewers record ranges like '45-60'; E2B wants a number. Emit nothing
    rather than fabricate a value."""
    root = _parse([_base_record(patient_age_range="45-60")])
    patient = root.find(".//patient")
    assert patient.find("patientonsetage") is None
    assert "45-60" in root.find(".//narrativeincludeclinical").text


def test_unknown_sex_is_omitted_not_guessed():
    root = _parse([_base_record(patient_sex="unknown")])
    assert root.find(".//patientsex") is None


def test_missing_event_does_not_produce_empty_reaction():
    root = _parse([_base_record(adverse_events=[])])
    assert root.find(".//primarysourcereaction").text


def test_special_characters_are_escaped():
    root = _parse([_base_record(title="Rash & fever <serious> in \"cases\"")])
    cite = root.find(".//literaturereference").text
    assert "&" in cite and "<serious>" in cite  # parsed back cleanly


def test_citation_has_no_double_period():
    root = _parse([_base_record()])
    assert ".." not in root.find(".//literaturereference").text


def test_multiple_records_produce_multiple_safety_reports():
    root = _parse([_base_record(pmid="1"), _base_record(pmid="2")])
    ids = [e.text for e in root.iter("safetyreportid")]
    assert ids == ["LITMON-PV-PILOT-1", "LITMON-PV-PILOT-2"]


def test_doctype_is_declared_for_the_receiving_gateway():
    doc = build_ichicsr_xml([_base_record()])
    assert DOCTYPE in doc
    assert 'lang="en"' in doc  # ATTLIST ichicsr lang CDATA #REQUIRED


def test_element_order_follows_the_dtd_sequence():
    """ICH ICSR DTD 2.1 content models are ordered sequences, so a correct
    set of elements in the wrong order is still invalid."""
    root = _parse([_base_record()])
    sr = root.find("safetyreport")
    order = [c.tag for c in sr]
    expected = [
        "safetyreportversion",
        "safetyreportid",
        "primarysourcecountry",
        "occurcountry",
        "transmissiondateformat",
        "transmissiondate",
        "reporttype",
        "serious",
        "seriousnesshospitalization",
        "receivedateformat",
        "receivedate",
        "receiptdateformat",
        "receiptdate",
        "fulfillexpeditecriteria",
        "primarysource",
        "sender",
        "receiver",
        "patient",
    ]
    assert order == expected

    patient = [c.tag for c in sr.find("patient")]
    assert patient == [
        "patientonsetage",
        "patientonsetageunit",
        "patientsex",
        "reaction",
        "drug",
        "summary",
    ]
    assert [c.tag for c in sr.find(".//drug")] == [
        "drugcharacterization",
        "medicinalproduct",
        "activesubstance",
        "activesubstance",
    ]


def test_patient_always_has_required_reaction_and_drug():
    """DTD: patient requires reaction+ and drug+ — never emit zero."""
    root = _parse([_base_record(adverse_events=[], suspect_products=[])])
    patient = root.find(".//patient")
    assert len(patient.findall("reaction")) >= 1
    assert len(patient.findall("drug")) >= 1


DTD_PATH = os.environ.get("CDSCO_DTD_PATH", "")


@pytest.mark.skipif(
    not DTD_PATH or not os.path.exists(DTD_PATH),
    reason="Set CDSCO_DTD_PATH to a local ich-icsr-v2.1.dtd to run DTD validation",
)
def test_output_is_valid_against_official_ich_icsr_dtd():
    doc = build_ichicsr_xml(
        [
            _base_record(),
            _base_record(pmid="999", seriousness="non_serious", patient_sex="male"),
            _base_record(pmid="1000", adverse_events=[], patient_age_range="45-60"),
        ]
    )
    ok, errors = validate_ichicsr(doc, DTD_PATH)
    assert ok, "DTD validation failed:\n" + "\n".join(errors)
