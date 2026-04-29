"""CHAIN-OF-COMMAND — synthetic ORBAT graph + ReBAC relationship generator.

Real reference (would plug in if available on accredited platform):
  - DEERS / MOL personnel + unit roster (USMC ORBAT graph down to fire-team).
  - GCSS-MC unit table (UIC, parent UIC, current OPCON / TACON / attached).
  - Keycloak realm export (cleared identities + caveats + nationality).
  - DoD PKI cert chain (CAC EDIPI binds the identity to the realm subject).

We synthesize a 60-ish-node ORBAT graph (units + Marines + documents) with 7
relationship types, drawn from JP 3-0 command-relationships taxonomy
(OPCON / TACON / attached / detached) plus DoDM 5200.02 clearance edges.

Seed: 1776 — every run is deterministic.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

OUT = Path(__file__).parent
SEED = 1776

# ─────────────────────────────────────────────────────────────────────────────
# Relationship taxonomy (Google Zanzibar-style relations)
# ─────────────────────────────────────────────────────────────────────────────
RELATIONSHIP_TYPES = [
    {
        "id": "MEMBER_OF",
        "label": "Member of",
        "description": "Permanent organic membership (Marine in fire-team, fire-team in squad, squad in platoon, etc.).",
        "auth_weight": 1.0,
        "color": "#00FFA7",
    },
    {
        "id": "OPCON_TO",
        "label": "OPCON to",
        "description": "Operational Control. Per JP 3-0: authority to organize forces, assign tasks, designate objectives.",
        "auth_weight": 1.0,
        "color": "#00BB7A",
    },
    {
        "id": "TACON_TO",
        "label": "TACON to",
        "description": "Tactical Control. Local direction & control of movements/maneuvers necessary to accomplish missions.",
        "auth_weight": 0.8,
        "color": "#0DCC8A",
    },
    {
        "id": "ATTACHED_TO",
        "label": "Attached to",
        "description": "Temporary placement of units/personnel for admin/log support; gaining cdr exercises OPCON.",
        "auth_weight": 0.9,
        "color": "#3FA9FF",
    },
    {
        "id": "DETACHED_TO",
        "label": "Detached to",
        "description": "Unit physically detached from parent for a mission window; gaining cdr exercises TACON+.",
        "auth_weight": 0.85,
        "color": "#A974FF",
    },
    {
        "id": "HAS_CLEARANCE",
        "label": "Has clearance",
        "description": "Per DoDM 5200.02 — Marine holds an active clearance up to the named level.",
        "auth_weight": 1.0,
        "color": "#FFB347",
    },
    {
        "id": "REL_TO",
        "label": "Releasable to",
        "description": "Document caveat — releasable to the named coalition / partner-nation set.",
        "auth_weight": 1.0,
        "color": "#FF6B6B",
    },
    {
        "id": "HAS_NEED_TO_KNOW",
        "label": "Need-to-know",
        "description": "Originator-defined need-to-know binding (unit owns the topic; downstream units inherit via OPCON).",
        "auth_weight": 1.0,
        "color": "#FFD700",
    },
    {
        "id": "CLASSIFIED_BY",
        "label": "Classified by",
        "description": "Originator (OCA) — the organization that owns the classification decision for the document.",
        "auth_weight": 1.0,
        "color": "#E8E8E8",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# ORBAT graph — units, sub-units, Marines, documents
# ─────────────────────────────────────────────────────────────────────────────
# COCOMs / MARFORs (top of graph)
COCOMS = [
    {"id": "USINDOPACOM", "kind": "ccmd", "label": "USINDOPACOM",
     "lat": 21.3611, "lon": -157.9690, "echelon": "CCMD"},
    {"id": "USEUCOM",     "kind": "ccmd", "label": "USEUCOM",
     "lat": 48.7758, "lon": 9.1829, "echelon": "CCMD"},
    {"id": "USCENTCOM",   "kind": "ccmd", "label": "USCENTCOM",
     "lat": 27.8493, "lon": -82.5005, "echelon": "CCMD"},
]

MARFORS = [
    {"id": "MARFORPAC", "kind": "marfor", "label": "MARFORPAC", "parent": None,
     "lat": 21.3424, "lon": -157.9604, "echelon": "MARFOR"},
    {"id": "MARFOREUR", "kind": "marfor", "label": "MARFOREUR/AF", "parent": None,
     "lat": 49.4325, "lon": 7.7507, "echelon": "MARFOR"},
    {"id": "MARFORCENT","kind": "marfor","label": "MARFORCENT", "parent": None,
     "lat": 27.8462, "lon": -82.4994, "echelon": "MARFOR"},
]

# MEFs (II MEF is its own service-component-tier — kept distinct from MARFORs so
# need-to-know doesn't bleed up into MARFOREUR organically; coalition access
# only opens via explicit ATTACHED/DETACHED/OPCON edges.)
MEFS = [
    {"id": "I_MEF", "kind": "mef", "label": "I MEF", "parent": "MARFORPAC",
     "lat": 33.4145, "lon": -117.6014, "echelon": "MEF"},
    {"id": "II_MEF","kind": "mef", "label": "II MEF","parent": None,
     "lat": 34.6849, "lon": -77.3464, "echelon": "MEF"},
    {"id": "III_MEF","kind":"mef", "label": "III MEF","parent": "MARFORPAC",
     "lat": 26.3183, "lon": 127.7551, "echelon": "MEF"},
]

# Divisions / MEUs
DIVS = [
    {"id": "1MARDIV", "kind": "div", "label": "1st MARDIV", "parent": "I_MEF",
     "lat": 33.3877, "lon": -117.4877, "echelon": "DIV"},
    {"id": "2MARDIV", "kind": "div", "label": "2nd MARDIV", "parent": "II_MEF",
     "lat": 34.6849, "lon": -77.3464, "echelon": "DIV"},
    {"id": "24MEU",   "kind": "meu", "label": "24th MEU",  "parent": "II_MEF",
     "lat": 34.6849, "lon": -77.3464, "echelon": "MEU"},
    {"id": "31MEU",   "kind": "meu", "label": "31st MEU",  "parent": "III_MEF",
     "lat": 26.3183, "lon": 127.7551, "echelon": "MEU"},
]

# Regiments / Battalions
REGTS = [
    {"id": "8th_Marines", "kind": "regt", "label": "8th Marines", "parent": "2MARDIV",
     "lat": 34.6849, "lon": -77.3464, "echelon": "REGT"},
    {"id": "1st_Marines", "kind": "regt", "label": "1st Marines", "parent": "1MARDIV",
     "lat": 33.3877, "lon": -117.4877, "echelon": "REGT"},
]

BNS = [
    {"id": "1_8",  "kind": "bn", "label": "1/8",  "parent": "8th_Marines",
     "lat": 34.6849, "lon": -77.3464, "echelon": "BN"},
    {"id": "2_2",  "kind": "bn", "label": "2/2 (BLT)", "parent": "8th_Marines",
     "lat": 34.6849, "lon": -77.3464, "echelon": "BN", "blt_for": "24MEU"},
    {"id": "1_1",  "kind": "bn", "label": "1/1",  "parent": "1st_Marines",
     "lat": 33.3877, "lon": -117.4877, "echelon": "BN"},
]

COS = [
    {"id": "A_1_8", "kind": "co", "label": "A Co 1/8", "parent": "1_8",
     "lat": 34.6849, "lon": -77.3464, "echelon": "CO"},
    {"id": "B_1_8", "kind": "co", "label": "B Co 1/8", "parent": "1_8",
     "lat": 34.6849, "lon": -77.3464, "echelon": "CO"},
    {"id": "A_1_1", "kind": "co", "label": "A Co 1/1", "parent": "1_1",
     "lat": 33.3877, "lon": -117.4877, "echelon": "CO"},
]

PLTS = [
    {"id": "1stPlt_A_1_8", "kind": "plt", "label": "1st Plt / A Co 1/8", "parent": "A_1_8",
     "lat": 34.6849, "lon": -77.3464, "echelon": "PLT"},
    {"id": "2ndPlt_A_1_8", "kind": "plt", "label": "2nd Plt / A Co 1/8", "parent": "A_1_8",
     "lat": 34.6849, "lon": -77.3464, "echelon": "PLT"},
    {"id": "1stPlt_A_1_1", "kind": "plt", "label": "1st Plt / A Co 1/1", "parent": "A_1_1",
     "lat": 33.3877, "lon": -117.4877, "echelon": "PLT"},
]

SQDS = [
    {"id": "1Sqd_1Plt_A_1_8", "kind": "sqd", "label": "1st Squad / 1st Plt", "parent": "1stPlt_A_1_8",
     "lat": 34.6849, "lon": -77.3464, "echelon": "SQD"},
    {"id": "2Sqd_1Plt_A_1_8", "kind": "sqd", "label": "2nd Squad / 1st Plt", "parent": "1stPlt_A_1_8",
     "lat": 34.6849, "lon": -77.3464, "echelon": "SQD"},
    {"id": "3Sqd_1Plt_A_1_8", "kind": "sqd", "label": "3rd Squad / 1st Plt", "parent": "1stPlt_A_1_8",
     "lat": 34.6849, "lon": -77.3464, "echelon": "SQD"},
    {"id": "1Sqd_1Plt_A_1_1", "kind": "sqd", "label": "1st Squad / 1st Plt A 1/1", "parent": "1stPlt_A_1_1",
     "lat": 33.3877, "lon": -117.4877, "echelon": "SQD"},
]

UNITS = COCOMS + MARFORS + MEFS + DIVS + REGTS + BNS + COS + PLTS + SQDS

# ─────────────────────────────────────────────────────────────────────────────
# Personnel — 30 named Marines + a coalition LNO + a contractor
# ─────────────────────────────────────────────────────────────────────────────
PERSONNEL = [
    # The hero of the demo: LCpl Smith in 3rd Squad
    {"id": "P_SMITH", "name": "LCpl Smith", "rank": "LCpl", "edipi": "1000000001",
     "mos": "0311", "clearance": "SECRET", "nationality": "USA",
     "current_unit": "3Sqd_1Plt_A_1_8",
     "notes": "Demo hero. Rifleman, 3rd Squad / 1st Plt / A Co 1/8."},

    {"id": "P_JONES", "name": "Sgt Jones", "rank": "Sgt", "edipi": "1000000002",
     "mos": "0369", "clearance": "SECRET", "nationality": "USA",
     "current_unit": "1stPlt_A_1_8",
     "notes": "Squad Leader."},
    {"id": "P_GARCIA","name": "Cpl Garcia","rank": "Cpl","edipi":"1000000003",
     "mos":"0341","clearance":"SECRET","nationality":"USA",
     "current_unit":"3Sqd_1Plt_A_1_8",
     "notes":"Mortarman, Smith's fire-team."},
    {"id": "P_OBRIEN","name": "Capt O'Brien","rank":"Capt","edipi":"1000000004",
     "mos":"0302","clearance":"TS","nationality":"USA",
     "current_unit":"A_1_8",
     "notes":"Co Cdr, A 1/8."},
    {"id": "P_REYES", "name":"Maj Reyes","rank":"Maj","edipi":"1000000005",
     "mos":"0302","clearance":"TS","nationality":"USA",
     "current_unit":"1_8",
     "notes":"BN S-3."},
    {"id": "P_SOTO",  "name":"LtCol Soto","rank":"LtCol","edipi":"1000000006",
     "mos":"0302","clearance":"TS","nationality":"USA",
     "current_unit":"2_2",
     "notes":"Cdr, 2/2 BLT for 24th MEU."},
    {"id": "P_KING",  "name":"Col King","rank":"Col","edipi":"1000000007",
     "mos":"0302","clearance":"TS","nationality":"USA",
     "current_unit":"24MEU",
     "notes":"24th MEU CO."},
    {"id": "P_PATEL", "name":"GySgt Patel","rank":"GySgt","edipi":"1000000008",
     "mos":"0369","clearance":"SECRET","nationality":"USA",
     "current_unit":"A_1_1",
     "notes":"PltSgt, 1st Plt A 1/1."},
    # Coalition LNO — same MEU but UK national
    {"id": "P_HARRIS","name":"Sgt Harris (RM)","rank":"Sgt","edipi":"UK00000001",
     "mos":"LNO","clearance":"SECRET","nationality":"GBR",
     "current_unit":"24MEU",
     "notes":"Royal Marines LNO attached to 24th MEU (FVEY)."},
    # NATO partner — German LNO at MARFOREUR
    {"id": "P_WEBER", "name":"OF-2 Weber (BWHr)","rank":"OF-2","edipi":"DE00000001",
     "mos":"LNO","clearance":"NATO_SECRET","nationality":"DEU",
     "current_unit":"MARFOREUR",
     "notes":"Bundeswehr LNO, MARFOREUR/AF (NATO)."},
    # Contractor (vendor realm — no need-to-know inheritance)
    {"id": "P_VENDOR","name":"Quinn (SETA)","rank":"GS-9","edipi":"V0000001",
     "mos":"CONTRACTOR","clearance":"UNCLASS","nationality":"USA",
     "current_unit":"1_8",
     "notes":"SETA contractor co-located but vendor realm."},

    # Filler (fire-team buddies, etc.) — add some flavor at lower nodes
    {"id":"P_LEE","name":"PFC Lee","rank":"PFC","edipi":"1000000010","mos":"0311",
     "clearance":"SECRET","nationality":"USA","current_unit":"3Sqd_1Plt_A_1_8","notes":"Rifleman."},
    {"id":"P_DIAZ","name":"PFC Diaz","rank":"PFC","edipi":"1000000011","mos":"0311",
     "clearance":"UNCLASS","nationality":"USA","current_unit":"2Sqd_1Plt_A_1_8","notes":"Rifleman."},
    {"id":"P_NGUYEN","name":"LCpl Nguyen","rank":"LCpl","edipi":"1000000012","mos":"0311",
     "clearance":"SECRET","nationality":"USA","current_unit":"1Sqd_1Plt_A_1_8","notes":"Team Leader."},
    {"id":"P_BROWN","name":"Sgt Brown","rank":"Sgt","edipi":"1000000013","mos":"0369",
     "clearance":"SECRET","nationality":"USA","current_unit":"1stPlt_A_1_1","notes":"Sqd Ldr."},
]

# ─────────────────────────────────────────────────────────────────────────────
# Documents — 20 docs spanning the AOR set
# ─────────────────────────────────────────────────────────────────────────────
DOCUMENTS = [
    {"id": "DOC_001", "title": "INDOPACOM AOR Threat Assessment — 24 MEU window",
     "classification": "SECRET", "classified_by": "MARFORPAC_G3",
     "rel_to": ["USA"], "need_to_know_orgs": ["24MEU", "I_MEF", "USINDOPACOM"],
     "summary": "Assessment of PRC littoral activity in the 24 MEU's projected AOR.",
     "topic": "Threat Assessment"},
    {"id": "DOC_002", "title": "24 MEU CONOPS — Phase II amphib insertion",
     "classification": "SECRET", "classified_by": "24MEU_G3",
     "rel_to": ["USA", "FVEY"], "need_to_know_orgs": ["24MEU", "2_2"],
     "summary": "Phase II concept of operations for the BLT amphib insertion.",
     "topic": "CONOPS"},
    {"id": "DOC_003", "title": "MARFOREUR Coalition ROE — NATO Article-5 contingency",
     "classification": "NATO_SECRET", "classified_by": "MARFOREUR_G3",
     "rel_to": ["NATO"], "need_to_know_orgs": ["MARFOREUR", "USEUCOM"],
     "summary": "Rules-of-engagement annex for NATO Article-5 contingency response.",
     "topic": "ROE"},
    {"id": "DOC_004", "title": "1/8 Battalion training calendar Q3FY26",
     "classification": "UNCLASS", "classified_by": "1_8_S3",
     "rel_to": ["ALL"], "need_to_know_orgs": ["1_8"],
     "summary": "Quarterly training calendar for 1/8.",
     "topic": "Training"},
    {"id": "DOC_005", "title": "A Co 1/8 fire-team marksmanship grades — Q2",
     "classification": "CUI", "classified_by": "A_1_8_S3",
     "rel_to": ["USA"], "need_to_know_orgs": ["A_1_8", "1_8"],
     "summary": "Per-Marine marksmanship qualification scores.",
     "topic": "Training"},
    {"id": "DOC_006", "title": "MEU Composite Logistics Plan — sustainment",
     "classification": "CUI", "classified_by": "24MEU_G4",
     "rel_to": ["USA", "FVEY"], "need_to_know_orgs": ["24MEU"],
     "summary": "Sustainment plan for the BLT during the float.",
     "topic": "Logistics"},
    {"id": "DOC_007", "title": "Vendor Statement of Work — IT support",
     "classification": "UNCLASS", "classified_by": "1_8_S6",
     "rel_to": ["ALL"], "need_to_know_orgs": ["1_8", "VENDOR"],
     "summary": "Contractor SOW for unit IT support.",
     "topic": "Contracting"},
    {"id": "DOC_008", "title": "INDOPACOM Posture Brief Q3",
     "classification": "SECRET", "classified_by": "USINDOPACOM_J3",
     "rel_to": ["USA", "FVEY"],
     "need_to_know_orgs": ["USINDOPACOM"],
     "summary": (
         "Combatant Command quarterly posture brief. Need-to-know is bound "
         "tightly to USINDOPACOM; subordinates inherit only via OPCON / "
         "TACON command relationships (the demo's pivot edge)."
     ),
     "topic": "Posture"},
    {"id": "DOC_009", "title": "1st MARDIV Plans Annex C — Fires",
     "classification": "SECRET", "classified_by": "1MARDIV_G3",
     "rel_to": ["USA"], "need_to_know_orgs": ["1MARDIV", "I_MEF"],
     "summary": "Fires annex for 1st MARDIV contingency plan.",
     "topic": "Fires"},
    {"id": "DOC_010", "title": "Royal Marines Liaison Briefing Pack (FVEY)",
     "classification": "SECRET", "classified_by": "24MEU_G3",
     "rel_to": ["USA", "FVEY"], "need_to_know_orgs": ["24MEU"],
     "summary": "FVEY-releasable LNO orientation pack.",
     "topic": "Coalition"},
    {"id": "DOC_011", "title": "Enrollment SOP — MarineNet courses",
     "classification": "UNCLASS", "classified_by": "TECOM",
     "rel_to": ["ALL"], "need_to_know_orgs": ["ALL"],
     "summary": "How to enroll in MarineNet courses.",
     "topic": "Training"},
    {"id": "DOC_012", "title": "TS//SCI Targeting Folder — Pacific",
     "classification": "TS", "classified_by": "USINDOPACOM_J2",
     "rel_to": ["USA"], "need_to_know_orgs": ["USINDOPACOM", "MARFORPAC"],
     "summary": "TS-level targeting folder.",
     "topic": "Targeting"},
    {"id": "DOC_013", "title": "Coalition Bandwidth Sharing — NATO LZ",
     "classification": "NATO_SECRET", "classified_by": "MARFOREUR_G6",
     "rel_to": ["NATO"], "need_to_know_orgs": ["MARFOREUR"],
     "summary": "NATO bandwidth-sharing arrangement at the LZ.",
     "topic": "Comms"},
    {"id": "DOC_014", "title": "1/1 Sustainment Annex — MCAGCC",
     "classification": "CUI", "classified_by": "1_1_S4",
     "rel_to": ["USA"], "need_to_know_orgs": ["1_1", "1MARDIV"],
     "summary": "Sustainment plan for 1/1 at 29 Palms.",
     "topic": "Logistics"},
    {"id": "DOC_015", "title": "BN OPORD — Cobra Gold 26",
     "classification": "SECRET", "classified_by": "1_8_S3",
     "rel_to": ["USA", "FVEY"], "need_to_know_orgs": ["1_8", "8th_Marines"],
     "summary": "BN-level OPORD for Cobra Gold 26 exercise.",
     "topic": "OPORD"},
    {"id": "DOC_016", "title": "Vendor Inventory — Hangar 7",
     "classification": "UNCLASS", "classified_by": "1_8_S4",
     "rel_to": ["ALL"], "need_to_know_orgs": ["VENDOR", "1_8"],
     "summary": "Inventory of vendor-managed equipment.",
     "topic": "Logistics"},
    {"id": "DOC_017", "title": "MEU Composite Squadron ATO",
     "classification": "SECRET", "classified_by": "24MEU_ACE",
     "rel_to": ["USA", "FVEY"], "need_to_know_orgs": ["24MEU"],
     "summary": "Air Tasking Order for the MEU's composite squadron.",
     "topic": "Air"},
    {"id": "DOC_018", "title": "MARFORPAC TPFDD Slice — III MEF",
     "classification": "SECRET", "classified_by": "MARFORPAC_G3",
     "rel_to": ["USA"], "need_to_know_orgs": ["MARFORPAC", "III_MEF", "USINDOPACOM"],
     "summary": "Time-phased force deployment slice for III MEF.",
     "topic": "Deployment"},
    {"id": "DOC_019", "title": "Personnel Recovery Annex — MEU",
     "classification": "CUI", "classified_by": "24MEU_G3",
     "rel_to": ["USA", "FVEY"], "need_to_know_orgs": ["24MEU"],
     "summary": "PR annex with on-call quick-reaction force.",
     "topic": "PR"},
    {"id": "DOC_020", "title": "Joint Exercise OPORD — TALISMAN SABRE",
     "classification": "SECRET", "classified_by": "USINDOPACOM_J3",
     "rel_to": ["USA", "FVEY"], "need_to_know_orgs": ["USINDOPACOM", "MARFORPAC", "31MEU"],
     "summary": "Joint exercise OPORD for TALISMAN SABRE.",
     "topic": "OPORD"},
]

# ─────────────────────────────────────────────────────────────────────────────
# ReBAC edges — the ORBAT graph + dynamic command relationships
# ─────────────────────────────────────────────────────────────────────────────
def _build_edges() -> list[dict]:
    edges: list[dict] = []

    def add(src: str, dst: str, rel: str, **meta):
        edges.append({"src": src, "dst": dst, "rel": rel, **meta})

    # MEMBER_OF for every parent edge in the ORBAT
    for u in UNITS:
        if u.get("parent"):
            add(u["id"], u["parent"], "MEMBER_OF")

    # Personnel MEMBER_OF their current unit
    for p in PERSONNEL:
        add(p["id"], p["current_unit"], "MEMBER_OF")
        # HAS_CLEARANCE edge for visualization
        add(p["id"], f"CLR_{p['clearance']}", "HAS_CLEARANCE", clearance=p["clearance"])

    # Dynamic command relationships — the heart of ReBAC
    # The 24th MEU is currently OPCON to USINDOPACOM (the demo's pivot relationship)
    add("24MEU", "USINDOPACOM", "OPCON_TO",
        order_ref="MARFORPAC FRAGO 026-12", effective="2026-04-15")
    # 2/2 is the BLT for 24MEU — DETACHED from 8th Marines parent
    add("2_2", "24MEU", "DETACHED_TO",
        order_ref="MARFORCOM FRAGO 008-04", effective="2026-03-01")
    # A Co 1/8 attached to 2/2 for the BLT (this is the link that gives Smith access)
    add("A_1_8", "2_2", "ATTACHED_TO",
        order_ref="1/8 OPORD 26-101", effective="2026-04-10")
    # 31st MEU is OPCON to USINDOPACOM (organic)
    add("31MEU", "USINDOPACOM", "OPCON_TO",
        order_ref="organic", effective="permanent")
    # MARFOREUR TACON to USEUCOM for routine ops
    add("MARFOREUR", "USEUCOM", "TACON_TO",
        order_ref="organic", effective="permanent")
    # MARFORPAC TACON to USINDOPACOM
    add("MARFORPAC", "USINDOPACOM", "TACON_TO",
        order_ref="organic", effective="permanent")

    # Need-to-know edges (originator-defined): every doc → its OCA → that org HAS_NEED_TO_KNOW the topic
    for doc in DOCUMENTS:
        # Doc CLASSIFIED_BY its OCA org
        add(doc["id"], doc["classified_by"], "CLASSIFIED_BY",
            classification=doc["classification"], topic=doc["topic"])
        # Doc REL_TO each releasability bucket
        for rel in doc["rel_to"]:
            add(doc["id"], f"REL_{rel}", "REL_TO", releasability=rel)
        # Each NEED_TO_KNOW org HAS_NEED_TO_KNOW the doc
        for org in doc["need_to_know_orgs"]:
            add(org, doc["id"], "HAS_NEED_TO_KNOW", topic=doc["topic"])

    return edges


# ─────────────────────────────────────────────────────────────────────────────
# Demo queries — six access requests to demonstrate the graph-walk
# ─────────────────────────────────────────────────────────────────────────────
DEMO_QUERIES = [
    {
        "id": "Q1_smith_indopacom",
        "subject": "P_SMITH",
        "object": "DOC_008",
        "label": "LCpl Smith → INDOPACOM Posture Brief Q3",
        "expected": "ALLOW",
        "narrative": (
            "Smith is rifleman in 3rd Squad / 1st Plt / A Co 1/8. A Co 1/8 is "
            "ATTACHED to 2/2 (BLT for 24th MEU), 24th MEU is OPCON to USINDOPACOM. "
            "USINDOPACOM HAS_NEED_TO_KNOW the INDOPACOM Posture Brief. Smith holds "
            "SECRET clearance ≥ doc SECRET. REL_TO contains FVEY+USA → USA citizen ✓. "
            "Access granted via the OPCON path."
        ),
    },
    {
        "id": "Q2_smith_natowinter",
        "subject": "P_SMITH",
        "object": "DOC_003",
        "label": "LCpl Smith → MARFOREUR NATO Coalition ROE",
        "expected": "DENY",
        "narrative": (
            "Smith's chain reaches USINDOPACOM via OPCON. The MARFOREUR ROE is "
            "classified by MARFOREUR_G3, releasable to NATO only, and need-to-know "
            "is bound to MARFOREUR / USEUCOM. No path from Smith reaches that "
            "need-to-know set, and Smith's REL_TO bucket excludes NATO-only docs."
        ),
    },
    {
        "id": "Q3_harris_meu_logplan",
        "subject": "P_HARRIS",
        "object": "DOC_006",
        "label": "Sgt Harris (UK LNO) → MEU Composite Logistics Plan",
        "expected": "ALLOW",
        "narrative": (
            "Harris is MEMBER_OF 24th MEU. 24MEU HAS_NEED_TO_KNOW the MEU Log Plan. "
            "Harris holds SECRET clearance ≥ doc CUI. REL_TO contains FVEY → "
            "GBR ∈ FVEY ✓. Access granted via direct MEMBER_OF + FVEY release."
        ),
    },
    {
        "id": "Q4_weber_indopacom",
        "subject": "P_WEBER",
        "object": "DOC_008",
        "label": "OF-2 Weber (DEU) → INDOPACOM Posture Brief",
        "expected": "DENY",
        "narrative": (
            "Weber is MEMBER_OF MARFOREUR (NATO realm). No path from MARFOREUR "
            "reaches USINDOPACOM-bound need-to-know set, and the doc is REL_TO "
            "USA + FVEY only — DEU is NATO, not FVEY. Even if a path existed, "
            "REL_TO would deny."
        ),
    },
    {
        "id": "Q5_vendor_sow",
        "subject": "P_VENDOR",
        "object": "DOC_007",
        "label": "Quinn (SETA) → Vendor SOW",
        "expected": "ALLOW",
        "narrative": (
            "Quinn is MEMBER_OF 1/8 (vendor realm). 1/8 HAS_NEED_TO_KNOW the SOW "
            "and VENDOR is a need-to-know group. Doc is UNCLASS (≤ Quinn's UNCLASS "
            "max). REL_TO ALL ⊇ {USA}. Access granted."
        ),
    },
    {
        "id": "Q6_vendor_meu_log",
        "subject": "P_VENDOR",
        "object": "DOC_006",
        "label": "Quinn (SETA) → MEU Composite Logistics Plan",
        "expected": "DENY",
        "narrative": (
            "Quinn's CLEARANCE = UNCLASS. Doc classification = CUI. Even if a path "
            "existed, the clearance check would fail at edge[Quinn → CLR_UNCLASS]."
        ),
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Cached briefs — pre-warm 6 scenarios for the cache-first pattern
# ─────────────────────────────────────────────────────────────────────────────
def _precompute_briefs() -> dict:
    """Pre-render the LLM-narrated graph-walk for each demo query.

    Cache-first pattern (lesson from Phase 1): the live LLM call only fires
    when the operator clicks 'Refresh narration'.
    """
    try:
        # Import the engine and llm late so the data file is portable
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from src.engine import compute_access  # noqa: E402
        from src.llm import narrate_access  # noqa: E402
    except Exception as e:  # noqa: BLE001
        print(f"[chain-of-command] cannot precompute briefs ({e}); writing placeholder.")
        return {"_placeholder": True}

    out: dict = {"queries": {}}
    for q in DEMO_QUERIES:
        try:
            verdict = compute_access(q["subject"], q["object"])
            try:
                narration = narrate_access(verdict, q)
            except Exception as e:  # noqa: BLE001
                narration = (
                    f"(cache miss — live narration will run on demand. {e})"
                )
            out["queries"][q["id"]] = {
                "label": q["label"],
                "expected": q["expected"],
                "verdict": verdict,
                "narration": narration,
            }
        except Exception as e:  # noqa: BLE001
            print(f"[chain-of-command] verdict failed {q['id']}: {e}")
            out["queries"][q["id"]] = {
                "label": q["label"],
                "expected": q["expected"],
                "verdict": {"decision": "ERROR", "reason": str(e)},
                "narration": "(cache miss)",
            }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main(skip_briefs: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)  # noqa: F841 — held for future synth jitter

    # Write all data files
    (OUT / "relationship_types.json").write_text(json.dumps(RELATIONSHIP_TYPES, indent=2))
    print(f"Wrote {len(RELATIONSHIP_TYPES)} relationship types.")

    (OUT / "orbat.json").write_text(json.dumps({
        "units": UNITS,
        "edges": _build_edges(),
    }, indent=2))
    print(f"Wrote ORBAT — {len(UNITS)} units, {len(_build_edges())} edges.")

    (OUT / "personnel.json").write_text(json.dumps(PERSONNEL, indent=2))
    print(f"Wrote {len(PERSONNEL)} personnel records.")

    (OUT / "documents.json").write_text(json.dumps(DOCUMENTS, indent=2))
    print(f"Wrote {len(DOCUMENTS)} documents.")

    (OUT / "demo_queries.json").write_text(json.dumps(DEMO_QUERIES, indent=2))
    print(f"Wrote {len(DEMO_QUERIES)} demo queries.")

    if skip_briefs:
        if not (OUT / "cached_briefs.json").exists():
            (OUT / "cached_briefs.json").write_text(json.dumps({"queries": {}}, indent=2))
        print("Skipped cached briefs (--skip-briefs).")
        return

    briefs = _precompute_briefs()
    (OUT / "cached_briefs.json").write_text(json.dumps(briefs, indent=2))
    print(f"Wrote cached briefs → {OUT / 'cached_briefs.json'}")


if __name__ == "__main__":
    skip = "--skip-briefs" in sys.argv
    main(skip_briefs=skip)
