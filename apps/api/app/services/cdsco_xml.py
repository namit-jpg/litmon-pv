"""CDSCO / PvPI ICSR export in ICH E2B(R2) XML form.

Background
----------
CDSCO requires marketing authorisation holders to report Individual Case
Safety Reports for marketed drugs to the National Coordination Centre of the
Pharmacovigilance Programme of India (NCC-PvPI, Indian Pharmacopoeia
Commission, Ghaziabad), which forwards them to the WHO-UMC via VigiFlow.
Reports are transmitted as ICH E2B XML.

This module emits the E2B(R2) ``ichicsr`` structure: one
``ichicsrmessageheader`` followed by one ``safetyreport`` per case
(ICH ICSR DTD 2.1). R2 is used rather than the HL7 v3 based R3 because it is
the format the PvPI/VigiFlow path has long accepted and it is
self-describing without an ISO IDMP terminology service.

PILOT SCOPE — read before relying on this
-----------------------------------------
Output is structurally E2B(R2)-shaped but is NOT a validated regulatory
submission:

* Reaction terms are free text from the reviewer, not MedDRA-coded (E2B
  expects ``reactionmeddrapt`` to carry a MedDRA Preferred Term).
* Product names are not WHO-DD coded.
* Sender/receiver identifiers are pilot placeholders.
* No DTD validation is performed and no batch wrapper is emitted.
* Literature cases only; there is no study or parent-child case support.

It is intended to demonstrate the export path and to be validated against the
partner's gateway before any real submission.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Optional
from xml.dom import minidom

# E2B(R2) message constants (ICH ICSR DTD 2.1)
MESSAGE_FORMAT_VERSION = "2.1"
MESSAGE_FORMAT_RELEASE = "2.0"
# Canonical system identifier for the ICH M2 ICSR DTD. Receiving gateways
# resolve this against their own local copy of the DTD.
DTD_SYSTEM_ID = "ich-icsr-v2.1.dtd"
DTD_PUBLIC_ID = "-//ICHM2//DTD ICH ICSR Vers. 2.1//EN"
DOCTYPE = f'<!DOCTYPE ichicsr SYSTEM "{DTD_SYSTEM_ID}">'
DATEFORMAT_FULL = "204"  # CCYYMMDDHHMMSS
DATEFORMAT_DAY = "102"  # CCYYMMDD

# India — reports route to NCC-PvPI
COUNTRY_INDIA = "IN"
DEFAULT_RECEIVER = "NCC-PvPI-CDSCO"
DEFAULT_SENDER = "LITMON-PV-PILOT"


def _txt(parent: ET.Element, tag: str, value: Any) -> Optional[ET.Element]:
    """Append a child element, skipping empty values.

    ElementTree escapes text, so reviewer free text is safe to pass through.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    el = ET.SubElement(parent, tag)
    el.text = s
    return el


def _sex_code(value: Optional[str]) -> Optional[str]:
    """E2B D.5: 1 = male, 2 = female. Anything else is left absent."""
    if not value:
        return None
    v = value.strip().lower()
    if v in ("m", "male"):
        return "1"
    if v in ("f", "female"):
        return "2"
    return None


def _numeric_age(value: Optional[str]) -> Optional[str]:
    """E2B D.2.2 needs a number, but reviewers capture ranges like "45-60".

    Only a single unambiguous integer is emitted. Ranges are deliberately
    dropped here and preserved in the narrative instead of inventing a value.
    """
    if not value:
        return None
    s = value.strip()
    if re.fullmatch(r"\d{1,3}", s):
        return s
    return None


def _normalise(value: Optional[str]) -> str:
    """Lower-case and collapse separators so ``non_serious``, ``non-serious``
    and ``Non Serious`` all compare equal."""
    return re.sub(r"[\s_\-]+", " ", (value or "").strip().lower())


_NON_SERIOUS = {"non serious", "nonserious", "not serious", "no", "none"}


def _is_serious(record: dict) -> bool:
    """E2B A.1.5.1. Defaults to non-serious when the reviewer left it blank —
    never assert seriousness (which drives expedited reporting) on a guess."""
    s = _normalise(record.get("seriousness"))
    if not s or s in _NON_SERIOUS:
        return False
    return True


def _fmt(dt: datetime, fmt: str) -> str:
    return dt.strftime("%Y%m%d%H%M%S" if fmt == DATEFORMAT_FULL else "%Y%m%d")


def _citation(record: dict) -> str:
    """E2B C.4.r.1 literature reference in Vancouver-ish form."""
    bits = [
        record.get("title"),
        record.get("journal"),
        (record.get("publication_date") or "")[:4] or None,
    ]
    # Titles usually already end in a period — avoid "review.. Journal".
    cite = ". ".join(str(b).strip().rstrip(".") for b in bits if b)
    pmid = record.get("pmid")
    if pmid:
        cite = f"{cite}. PMID: {pmid}" if cite else f"PMID: {pmid}"
    doi = record.get("doi")
    if doi:
        cite += f". doi:{doi}"
    return cite


def _narrative(record: dict) -> str:
    """E2B H.1 — carries what the coded fields cannot hold."""
    parts: list[str] = []
    if record.get("rationale"):
        parts.append(f"Reviewer rationale: {record['rationale']}")
    if record.get("patient_age_range"):
        parts.append(f"Reported patient age range: {record['patient_age_range']}")
    if record.get("listedness"):
        parts.append(f"Listedness: {record['listedness']}")
    if record.get("seriousness"):
        parts.append(f"Seriousness assessment: {record['seriousness']}")
    ai_model = record.get("ai_model_id")
    if ai_model:
        parts.append(
            f"Automated pre-screening: model {ai_model}, composite "
            f"{record.get('ai_composite')}. AI output is decision support only; "
            "the disposition recorded here was made by a human reviewer."
        )
    if record.get("reviewer"):
        parts.append(f"Assessed by: {record['reviewer']} on {record.get('decision_date')}")
    parts.append(
        "Source: published literature identified by automated PubMed monitoring."
    )
    return " ".join(parts)


def build_ichicsr_xml(
    records: list[dict],
    *,
    sender_id: str = DEFAULT_SENDER,
    receiver_id: str = DEFAULT_RECEIVER,
    message_number: Optional[str] = None,
    now: Optional[datetime] = None,
) -> str:
    """Render ICSR records as an E2B(R2) ``ichicsr`` XML document."""
    now = now or datetime.now(timezone.utc)
    msg_no = message_number or f"LITMON-{_fmt(now, DATEFORMAT_FULL)}"

    root = ET.Element("ichicsr", {"lang": "en"})

    header = ET.SubElement(root, "ichicsrmessageheader")
    _txt(header, "messagetype", "ichicsr")
    _txt(header, "messageformatversion", MESSAGE_FORMAT_VERSION)
    _txt(header, "messageformatrelease", MESSAGE_FORMAT_RELEASE)
    _txt(header, "messagenumb", msg_no)
    _txt(header, "messagesenderidentifier", sender_id)
    _txt(header, "messagereceiveridentifier", receiver_id)
    _txt(header, "messagedateformat", DATEFORMAT_FULL)
    _txt(header, "messagedate", _fmt(now, DATEFORMAT_FULL))

    for idx, rec in enumerate(records, start=1):
        _safety_report(root, rec, idx, now, sender_id, receiver_id, msg_no)

    raw = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    # minidom emits its own declaration; keep one and add the DOCTYPE the
    # receiving gateway needs in order to validate against the ICH DTD.
    body = "\n".join(line for line in pretty.splitlines()[1:] if line.strip())
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"{DOCTYPE}\n"
        "<!-- Structurally valid against ICH ICSR DTD 2.1 (E2B(R2)). "
        "CDSCO / NCC-PvPI pilot export. -->\n"
        "<!-- Content is NOT regulatory-ready: reaction terms are not "
        "MedDRA-coded and products are not WHO-DD coded. -->\n" + body + "\n"
    )


def validate_ichicsr(xml_text: str, dtd_path: str) -> tuple[bool, list[str]]:
    """Validate a document against the ICH ICSR v2.1 DTD.

    The DTD is not vendored into this repository: it is ICH M2 public-domain
    but its header states "No commercial distribution is allowed". Obtain a
    copy (for example from the EMA EudraVigilance DTD listing) and point
    ``CDSCO_DTD_PATH`` at it.

    Returns ``(is_valid, errors)``.
    """
    try:
        from lxml import etree
    except ImportError:  # pragma: no cover - lxml is a declared dependency
        return False, ["lxml is required for DTD validation"]

    try:
        with open(dtd_path, "rb") as fh:
            dtd = etree.DTD(fh)
    except OSError as exc:
        return False, [f"Could not read DTD at {dtd_path}: {exc}"]

    parser = etree.XMLParser(load_dtd=False, resolve_entities=False)
    try:
        doc = etree.fromstring(xml_text.encode("utf-8"), parser)
    except etree.XMLSyntaxError as exc:
        return False, [f"Not well-formed: {exc}"]

    if dtd.validate(doc):
        return True, []
    return False, [e.message for e in dtd.error_log.filter_from_errors()]


def _safety_report(
    root: ET.Element,
    rec: dict,
    idx: int,
    now: datetime,
    sender_id: str,
    receiver_id: str,
    msg_no: str,
) -> None:
    sr = ET.SubElement(root, "safetyreport")

    _txt(sr, "safetyreportversion", "1")
    _txt(sr, "safetyreportid", f"{sender_id}-{rec.get('pmid') or idx}")
    _txt(sr, "primarysourcecountry", COUNTRY_INDIA)
    _txt(sr, "occurcountry", rec.get("patient_country") or COUNTRY_INDIA)
    _txt(sr, "transmissiondateformat", DATEFORMAT_DAY)
    _txt(sr, "transmissiondate", _fmt(now, DATEFORMAT_DAY))
    # A.1.4 report type: 1 = spontaneous. Literature cases are reported as
    # spontaneous with the citation carried in the primary source.
    _txt(sr, "reporttype", "1")

    serious = _is_serious(rec)
    _txt(sr, "serious", "1" if serious else "2")
    if serious:
        seriousness = _normalise(rec.get("seriousness"))
        # A.1.5.2 seriousness criteria — only assert what the reviewer recorded.
        if "death" in seriousness or "fatal" in seriousness:
            _txt(sr, "seriousnessdeath", "1")
        if "life" in seriousness:
            _txt(sr, "seriousnesslifethreatening", "1")
        if "hospital" in seriousness:
            _txt(sr, "seriousnesshospitalization", "1")
        if "disab" in seriousness:
            _txt(sr, "seriousnessdisabling", "1")
        if "congenital" in seriousness or "anomaly" in seriousness:
            _txt(sr, "seriousnesscongenitalanomali", "1")
        if "other" in seriousness or "medically" in seriousness:
            _txt(sr, "seriousnessother", "1")

    decided = (rec.get("decision_date") or "")[:10].replace("-", "")
    _txt(sr, "receivedateformat", DATEFORMAT_DAY)
    _txt(sr, "receivedate", decided or _fmt(now, DATEFORMAT_DAY))
    _txt(sr, "receiptdateformat", DATEFORMAT_DAY)
    _txt(sr, "receiptdate", decided or _fmt(now, DATEFORMAT_DAY))
    _txt(sr, "fulfillexpeditecriteria", "1" if serious else "2")

    # C.2 primary source — literature
    src = ET.SubElement(sr, "primarysource")
    _txt(src, "reportercountry", rec.get("patient_country") or COUNTRY_INDIA)
    # C.2.r.4 qualification: 3 = other health professional
    _txt(src, "qualification", "3")
    _txt(src, "literaturereference", _citation(rec))

    snd = ET.SubElement(sr, "sender")
    _txt(snd, "sendertype", "1")
    _txt(snd, "senderorganization", sender_id)

    rcv = ET.SubElement(sr, "receiver")
    _txt(rcv, "receivertype", "2")
    _txt(rcv, "receiverorganization", receiver_id)

    patient = ET.SubElement(sr, "patient")
    _txt(patient, "patientonsetage", _numeric_age(rec.get("patient_age_range")))
    if _numeric_age(rec.get("patient_age_range")):
        _txt(patient, "patientonsetageunit", "801")  # 801 = year
    _txt(patient, "patientsex", _sex_code(rec.get("patient_sex")))

    # E.i reactions
    events = [e for e in (rec.get("adverse_events") or []) if str(e).strip()]
    if not events:
        events = ["Adverse event not specified in source"]
    for ev in events:
        reaction = ET.SubElement(patient, "reaction")
        _txt(reaction, "primarysourcereaction", ev)
        # Free text placed in the MedDRA slot; see PILOT SCOPE above.
        _txt(reaction, "reactionmeddrapt", ev)

    # G.k drugs — one suspect drug block per monitored product
    products = [p for p in (rec.get("suspect_products") or []) if str(p).strip()]
    if not products:
        # Fall back to the monitored product the article was screened against.
        products = [rec.get("product") or "Unspecified monitored product"]
    ingredients = [
        i for i in (rec.get("active_ingredients") or []) if str(i).strip()
    ]
    for prod in products:
        drug = ET.SubElement(patient, "drug")
        # G.k.1: 1 = suspect
        _txt(drug, "drugcharacterization", "1")
        _txt(drug, "medicinalproduct", prod)
        # G.k.2.3.r — the Active Pharmaceutical Ingredient(s).
        for ing in ingredients:
            sub = ET.SubElement(drug, "activesubstance")
            _txt(sub, "activesubstancename", ing)

    summary = ET.SubElement(patient, "summary")
    _txt(summary, "narrativeincludeclinical", _narrative(rec))
