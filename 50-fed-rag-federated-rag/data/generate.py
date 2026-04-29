"""FED-RAG — Synthetic federated-silo corpora generator.

Three locked silos, each with its OWN local corpus + OWN local embedding index.
The whole point is to PROVE federation: there are 3 separate numpy index files
on disk (silos/<name>/embeddings.npy), not one merged index.

Real-world references this stands in for:
  - Silo A: GCSS-MC depot inventory at MCLB Albany (DLA-controlled, CUI)
  - Silo B: 31st MEU LCE Technical Manual library at Camp Pendleton (CUI/FOUO)
  - Silo C: DLA Troop Support Class VIII medical at Philadelphia (DLA HQ)

Compliance authorities driving the no-data-movement constraint:
  - DLA Manual 4140.27 — distribution + custody of materiel records
  - DoDM 5200.01 Vol 2 — data spillage prevention across enclaves
  - DDIL / EMCON — disconnected, intermittent, low-bandwidth ops

Two-pass generation:
  pass 1 (`python data/generate.py`)         — emit per-silo corpus.jsonl
  pass 2 (`python data/generate.py --embed`) — embed every chunk per silo,
                                                cache silos/<name>/embeddings.npy,
                                                pre-compute cached_briefs.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

OUT_DIR = Path(__file__).parent
APP_ROOT = OUT_DIR.parent
SILO_DIR = APP_ROOT / "silos"
AUDIT_DIR = APP_ROOT / "audit"
SEED = 1776
CHUNKS_PER_SILO = 30

ROOT = APP_ROOT.parent.parent
sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Silo profiles — each represents a real, locked enclave
# ─────────────────────────────────────────────────────────────────────────────
SILOS = [
    {
        "id": "albany",
        "display": "MCLB Albany — GCSS-MC Depot",
        "owner": "DLA / MCLB Albany Maintenance Center",
        "classification": "CUI // Distribution D",
        "authority": "DLA Manual 4140.27",
        "physical_loc": "Albany, GA",
        "raw_data_size_gb": 50.0,
        "data_class": "GCSS-MC depot inventory + parts availability",
        "url_env": "KAMIWAZA_SILO_ALBANY_URL",
    },
    {
        "id": "pendleton",
        "display": "Camp Pendleton — 31st MEU LCE TM Library",
        "owner": "31st MEU Logistics Combat Element",
        "classification": "CUI // FOUO",
        "authority": "DoDM 5200.01 Vol 2",
        "physical_loc": "Camp Pendleton, CA",
        "raw_data_size_gb": 12.0,
        "data_class": "Technical Manuals + maintenance procedures",
        "url_env": "KAMIWAZA_SILO_PENDLETON_URL",
    },
    {
        "id": "philly",
        "display": "DLA Troop Support — Philadelphia",
        "owner": "DLA Troop Support Medical",
        "classification": "CUI // Distribution C",
        "authority": "DLA Manual 4140.27",
        "physical_loc": "Philadelphia, PA",
        "raw_data_size_gb": 30.0,
        "data_class": "Class VIII medical + global purchasing",
        "url_env": "KAMIWAZA_SILO_PHILLY_URL",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Per-silo synthesis templates — chunk-shape varies per data class
# ─────────────────────────────────────────────────────────────────────────────
ALBANY_NSNS = [
    ("5340-01-501-3829", "Bracket, mounting, AAV-7A1 hull stiffener", "AAV-7A1"),
    ("2530-01-345-7711", "Brake disc, front, MTVR LVS", "MTVR"),
    ("2920-01-468-0912", "Alternator, 200A, JLTV", "JLTV"),
    ("2540-01-512-3401", "Seat assembly, gunner, M-ATV", "M-ATV"),
    ("4720-01-099-4421", "Hose assembly, hydraulic, AAV-7A1 ramp actuator", "AAV-7A1"),
    ("2815-01-560-7720", "Cylinder head, 6.7L diesel, MTVR", "MTVR"),
    ("5995-01-477-6634", "Cable assembly, CAN bus, JLTV", "JLTV"),
    ("3120-01-330-2298", "Bushing, sleeve, suspension arm, MTVR", "MTVR"),
    ("2590-01-588-1102", "Kit, ECP up-armor, JLTV", "JLTV"),
    ("4310-01-219-9043", "Compressor, air, LVSR PLS", "LVSR"),
    ("2540-01-601-2284", "Window assembly, transparent armor, M-ATV", "M-ATV"),
    ("2920-01-555-3018", "Starter, 24V, MTVR", "MTVR"),
]
ALBANY_LOCATIONS = ["Albany Bldg 5300 Bin A-22", "Albany Bldg 5300 Bin C-04",
                    "Albany Bldg 5102 Annex B-19", "Albany Cold Storage CS-44",
                    "Albany SecureRoom SR-08"]

PENDLETON_TMS = [
    ("TM 9-2320-387-23", "MTVR Family Unit and Direct Support Maintenance"),
    ("TM 9-2320-387-23P", "MTVR Repair Parts and Special Tools List"),
    ("TM 9-2320-280-10", "HMMWV Operator Manual"),
    ("TM 9-2350-294-10", "AAV-7A1 Crew Operator Manual"),
    ("TM 9-2350-294-23", "AAV-7A1 Unit and DS Maintenance"),
    ("TM 11-5820-890-10-8", "AN/PRC-117G Operator Manual"),
    ("TM 9-1005-319-10", "M4A1 Carbine Operator Manual"),
    ("TM 10-1670-300-20/12", "T-11 Personnel Parachute Maintenance"),
    ("TM 9-4940-568-13", "Field Maintenance Shop Set Common No. 1"),
    ("TM 4790-14/3D", "MIMMS Field Maintenance SOP — 31st MEU"),
    ("TM 9-2320-377-10", "JLTV Operator Manual"),
    ("TM 9-2320-377-23", "JLTV Field Maintenance"),
]
PENDLETON_PROCEDURES = [
    "alternator R&R", "starter R&R", "fuel filter service",
    "hydraulic ramp actuator inspection", "track tension adjustment",
    "transparent armor seal R&R", "ECP up-armor kit installation",
    "battery box inspection", "CAN bus diagnostic", "preventive maintenance checks (PMCS)",
    "torque sequence — head bolts", "cooling system bleed procedure",
]

PHILLY_CLASSVIII = [
    ("6505-01-432-7821", "Insulin, Regular U-100, 10 mL vial", "REFRIG 2-8°C", "12 months"),
    ("6515-01-559-3340", "Tourniquet, CAT Gen 7, NSN-supplied", "Ambient", "120 months"),
    ("6505-01-477-9981", "TXA Tranexamic Acid 1g/10 mL injection", "Ambient", "36 months"),
    ("6505-01-602-1198", "Ketamine 50 mg/mL, 10 mL vial", "Ambient, controlled", "24 months"),
    ("6515-01-580-2210", "HemCon ChitoGauze XR, hemostatic dressing", "Ambient", "60 months"),
    ("6505-01-396-5212", "Doxycycline 100 mg tablet, 100 ct", "Ambient", "36 months"),
    ("6505-01-541-0021", "Epinephrine 1:1000 1 mL ampule", "Ambient, light-protect", "18 months"),
    ("6515-01-561-7790", "Junctional tourniquet, JETT", "Ambient", "120 months"),
    ("6505-01-447-1132", "Morphine sulfate 10 mg/mL ampule", "Ambient, controlled", "24 months"),
    ("6505-01-588-0078", "Hextend 6% HES 500 mL", "Ambient", "24 months"),
    ("6505-01-345-2208", "Atropine 0.4 mg/mL injection", "Ambient", "36 months"),
    ("6505-01-499-7733", "Naloxone 4 mg nasal spray", "Ambient", "24 months"),
]
PHILLY_DEPOTS = ["DLA Philly DC-A", "DLA Philly DC-B Cold Vault",
                 "DLA Philly Controlled Substance Vault CSV-1",
                 "DLA San Joaquin Forward Stock", "DLA Susquehanna Buffer"]


def _albany_chunks(rng: random.Random) -> list[dict]:
    out = []
    for i in range(CHUNKS_PER_SILO):
        nsn, nomen, platform = rng.choice(ALBANY_NSNS)
        loc = rng.choice(ALBANY_LOCATIONS)
        on_hand = rng.randint(0, 240)
        due_in = rng.randint(0, 80)
        unit_price = round(rng.uniform(38.0, 8800.0), 2)
        d_pdt = rng.randint(2, 21)
        last_iss = (date.today() - timedelta(days=rng.randint(2, 380))).isoformat()
        out.append({
            "chunk_id": f"ALB-{i+1:03d}",
            "silo": "albany",
            "doc_type": "GCSS-MC inventory record",
            "platform": platform,
            "text": (
                f"NSN {nsn} ({nomen}) — Platform: {platform}. "
                f"On-hand: {on_hand} ea at {loc}. Due-in: {due_in} ea, "
                f"production lead time {d_pdt} days. Unit price ${unit_price:,.2f}. "
                f"Last issued {last_iss}. Held under DLA Manual 4140.27 "
                f"distribution control; record is Distribution D, never "
                f"replicated outside MCLB Albany ADP boundary."
            ),
            "metadata": {
                "nsn": nsn, "on_hand": on_hand, "due_in": due_in,
                "unit_price": unit_price, "lead_time_days": d_pdt,
                "location": loc, "last_issued": last_iss,
            },
        })
    return out


def _pendleton_chunks(rng: random.Random) -> list[dict]:
    out = []
    for i in range(CHUNKS_PER_SILO):
        tm_num, tm_title = rng.choice(PENDLETON_TMS)
        proc = rng.choice(PENDLETON_PROCEDURES)
        section = f"{rng.randint(2, 8)}.{rng.randint(1, 12)}"
        time_min = rng.randint(20, 480)
        mos_required = rng.choice(["3521", "3522", "0411", "1345", "2147"])
        tools = rng.choice([
            "SL-3 mechanic tool kit", "shop set common no. 1",
            "torque wrench cal-2024", "diagnostic laptop w/ STE-ICE-R",
            "hydraulic test stand HTS-2",
        ])
        out.append({
            "chunk_id": f"PEN-{i+1:03d}",
            "silo": "pendleton",
            "doc_type": "Technical Manual procedure",
            "tm_number": tm_num,
            "text": (
                f"{tm_num} ({tm_title}) §{section}: {proc}. "
                f"Estimated time {time_min} min, MOS {mos_required} required. "
                f"Tools: {tools}. Reference safety summary §1.3. "
                f"Document carries CUI//FOUO marking under DoDM 5200.01 Vol 2 "
                f"and is mirrored only on the 31st MEU LCE TM repository at "
                f"Camp Pendleton; copies do not leave the Pendleton enclave."
            ),
            "metadata": {
                "tm_number": tm_num, "section": section,
                "estimated_minutes": time_min, "mos": mos_required,
                "tools": tools,
            },
        })
    return out


def _philly_chunks(rng: random.Random) -> list[dict]:
    out = []
    for i in range(CHUNKS_PER_SILO):
        nsn, nomen, storage, shelf_life = rng.choice(PHILLY_CLASSVIII)
        depot = rng.choice(PHILLY_DEPOTS)
        on_hand = rng.randint(0, 4200)
        unit_cost = round(rng.uniform(1.10, 480.0), 2)
        lot = f"L{rng.randint(20240, 20251)}-{rng.randint(100, 999)}"
        expiry = (date.today() + timedelta(days=rng.randint(30, 720))).isoformat()
        vendor = rng.choice([
            "Cardinal Health (DAPA SP0200-22-D-0014)",
            "McKesson (DAPA SP0200-21-D-0098)",
            "Henry Schein (DAPA SP0200-23-D-0033)",
            "North American Rescue (NSN-direct)",
        ])
        out.append({
            "chunk_id": f"PHL-{i+1:03d}",
            "silo": "philly",
            "doc_type": "DLA Class VIII medical record",
            "text": (
                f"NSN {nsn} ({nomen}) — Storage: {storage}. "
                f"Shelf life {shelf_life} from manufacture. "
                f"On-hand at {depot}: {on_hand} ea, unit cost ${unit_cost:.2f}. "
                f"Lot {lot}, expiry {expiry}. Vendor: {vendor}. "
                f"Held under DLA Troop Support custody at Philadelphia HQ; "
                f"FDA-traceable Class VIII material — never leaves DLA "
                f"Philly accredited enclave per DLA Manual 4140.27."
            ),
            "metadata": {
                "nsn": nsn, "on_hand": on_hand, "unit_cost": unit_cost,
                "lot": lot, "expiry": expiry, "depot": depot, "vendor": vendor,
                "storage": storage, "shelf_life": shelf_life,
            },
        })
    return out


SILO_GENERATORS = {
    "albany": _albany_chunks,
    "pendleton": _pendleton_chunks,
    "philly": _philly_chunks,
}


# ─────────────────────────────────────────────────────────────────────────────
# Demo queries — all four naturally pull from all three silos
# ─────────────────────────────────────────────────────────────────────────────
DEMO_QUERIES = [
    {
        "id": "meu_31_itbayat_d30",
        "label": "Sustain 31st MEU at Itbayat through D+30",
        "prompt": (
            "How should I sustain the 31st MEU at Itbayat through D+30? "
            "I need depot Class IX availability for AAV-7A1 and MTVR, the "
            "applicable maintenance procedures my LCE will execute forward, "
            "and Class VIII medical resupply with shelf-life and cold-chain "
            "constraints for a 30-day distributed STOM operation."
        ),
    },
    {
        "id": "jltv_jungle_sustain",
        "label": "JLTV jungle sustainment package — Philippines",
        "prompt": (
            "Build a 21-day JLTV sustainment package for a platoon-sized "
            "stand-in force in the Philippines. Include Class IX parts "
            "availability, the JLTV field maintenance procedures the platoon "
            "mechanic will need, and a Class VIII trauma resupply tailored to "
            "junctional-hemorrhage casualty profile."
        ),
    },
    {
        "id": "haadr_typhoon_response",
        "label": "Western Pacific typhoon HA/DR cell",
        "prompt": (
            "Stand up a 14-day HA/DR cell in the Western Pacific typhoon "
            "corridor. I need MTVR and LVSR readiness parts at depot, the "
            "HMMWV and MTVR maintenance procedures the support battalion "
            "will rely on, and Class VIII trauma + tropical-disease "
            "prophylaxis stocks held by DLA."
        ),
    },
    {
        "id": "aav7a1_ramp_failure",
        "label": "AAV-7A1 ramp actuator failure cluster",
        "prompt": (
            "We have a ramp-actuator failure cluster across three AAV-7A1 "
            "hulls afloat with 31st MEU. Pull depot stock on the affected "
            "hydraulic hose assembly, the AAV-7A1 maintenance procedures "
            "covering the ramp actuator R&R, and any Class VIII items "
            "needed for embarked-medical contingency during repair."
        ),
    },
]


def write_corpora() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    rng = random.Random(SEED)
    for silo in SILOS:
        sid = silo["id"]
        chunks = SILO_GENERATORS[sid](rng)
        sdir = SILO_DIR / sid
        sdir.mkdir(parents=True, exist_ok=True)
        with (sdir / "corpus.jsonl").open("w") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")
        # Silo manifest — used by app/audit
        (sdir / "manifest.json").write_text(json.dumps({
            **silo,
            "chunk_count": len(chunks),
        }, indent=2))
        out[sid] = chunks
        print(f"  wrote {len(chunks)} chunks -> silos/{sid}/corpus.jsonl")
    # Demo queries
    (OUT_DIR / "demo_queries.json").write_text(json.dumps(DEMO_QUERIES, indent=2))
    print(f"  wrote {len(DEMO_QUERIES)} demo queries -> data/demo_queries.json")
    # Initialize empty audit log if missing
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit_log = AUDIT_DIR / "network_traffic.jsonl"
    if not audit_log.exists():
        audit_log.write_text("")
        print(f"  initialized empty audit log -> audit/network_traffic.jsonl")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Per-silo embedding cache — proves federation: 3 separate .npy files
# ─────────────────────────────────────────────────────────────────────────────
def _embed_silo(sid: str, chunks: list[dict]) -> None:
    import numpy as np
    from shared.kamiwaza_client import embed  # noqa: WPS433

    texts = [c["text"] for c in chunks]
    print(f"\n[{sid}] embedding {len(texts)} local chunks...")
    vecs: list[list[float]] = []
    batch = 32
    for i in range(0, len(texts), batch):
        vecs.extend(embed(texts[i:i + batch]))
    mat = np.array(vecs, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12
    mat = mat / norms
    sdir = SILO_DIR / sid
    np.save(sdir / "embeddings.npy", mat)
    (sdir / "chunk_ids.json").write_text(json.dumps([c["chunk_id"] for c in chunks]))
    print(f"[{sid}] wrote embeddings.npy shape={mat.shape}")


def _precompute_briefs(corpora: dict[str, list[dict]]) -> None:
    """Run the federated pipeline against all demo queries; cache outputs."""
    sys.path.insert(0, str(APP_ROOT / "src"))
    from federation import federated_query, hero_brief  # noqa: WPS433

    briefs = {}
    for q in DEMO_QUERIES:
        print(f"\nPre-computing federated brief: {q['id']}")
        try:
            fed = federated_query(q["prompt"], k_per_silo=3)
            brief_text = hero_brief(q["prompt"], fed, use_hero_model=False)
            briefs[q["id"]] = {
                "label": q["label"],
                "prompt": q["prompt"],
                "per_silo": [
                    {
                        "silo": r["silo"],
                        "display": r["display"],
                        "chunk_count": len(r["chunks"]),
                        "chunk_ids": [c["chunk_id"] for c in r["chunks"]],
                        "snippet_bytes": r["snippet_bytes"],
                    }
                    for r in fed["per_silo"]
                ],
                "brief": brief_text,
                "total_snippet_bytes": fed["total_snippet_bytes"],
                "naive_central_bytes": fed["naive_central_bytes"],
            }
        except Exception as e:  # noqa: BLE001
            print(f"  brief {q['id']} failed: {e}")
            briefs[q["id"]] = {
                "label": q["label"],
                "prompt": q["prompt"],
                "error": str(e),
            }
    (OUT_DIR / "cached_briefs.json").write_text(json.dumps(briefs, indent=2))
    print(f"\nWrote {len(briefs)} cached federated briefs -> data/cached_briefs.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--embed", action="store_true",
                        help="Also embed every silo's chunks + precompute briefs.")
    parser.add_argument("--briefs-only", action="store_true",
                        help="Skip data + embedding regen; only precompute briefs.")
    args = parser.parse_args()

    if args.briefs_only:
        corpora = {}
        for silo in SILOS:
            sid = silo["id"]
            with (SILO_DIR / sid / "corpus.jsonl").open() as f:
                corpora[sid] = [json.loads(line) for line in f if line.strip()]
    else:
        corpora = write_corpora()
        if args.embed:
            for sid, chunks in corpora.items():
                _embed_silo(sid, chunks)

    if args.embed or args.briefs_only:
        _precompute_briefs(corpora)


if __name__ == "__main__":
    main()
