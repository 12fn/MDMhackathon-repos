"""DDE-RAG synthetic data generator.

Produces:
  data/nodes.json                            — 3 data-node profiles
  data/queries.json                          — 5 demo questions w/ DDE-favoring
                                                shape (large data, sensitive,
                                                low-bandwidth-environment)
  data/mock_corpora/{albany,lejeune,quantico}.jsonl — 30 RAG chunks per node
  data/mock_embeddings/{albany,lejeune,quantico}.npy — 384-dim local indexes
  data/audit_logs/dde_audit.jsonl            — append-only hash chain (seeded)
  data/cached_briefs.json                    — 5 query scenarios pre-warmed
                                                with full execution traces

Seeded with random.Random(1776) for reproducibility.
Real-Kamiwaza swap: see data/load_real.py — set KAMIWAZA_DDE_NODES to the
real Inference Mesh endpoints.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
APP_ROOT = ROOT.parent
REPO_ROOT = ROOT.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Node profiles — each is realistic about its bandwidth + compliance posture
# ---------------------------------------------------------------------------
NODES = [
    {
        "id": "albany",
        "label": "MCLB Albany — GCSS-MC",
        "installation": "Marine Corps Logistics Base Albany, GA",
        "system": "Global Combat Support System — Marine Corps",
        "data_kind": "work_orders",
        "data_size_gb": 50.0,
        "bandwidth_mbps": 50,
        "operating_env": "garrison-backhaul",
        "security_posture": "UNCLASSIFIED",
        "compliance_authority": "DoD IL4 / NIST 800-53",
        "compute_posture": "DDE inference container ready (vLLM, llama.cpp)",
        "node_endpoint": "albany.gcssmc.usmc.mil:8443",
        "color": "#00BB7A",
    },
    {
        "id": "lejeune",
        "label": "MCB Lejeune — ICM",
        "installation": "Marine Corps Base Camp Lejeune, NC",
        "system": "Inventory Control Management workbook (deployable cell)",
        "data_kind": "lateral_transfer_parts",
        "data_size_gb": 8.0,
        "bandwidth_mbps": 25,
        "operating_env": "DDIL/EMCON window",
        "security_posture": "UNCLASSIFIED // FOUO",
        "compliance_authority": "DoD IL5 / NIST 800-171",
        "compute_posture": "DDE inference container ready (DDIL-degraded mode)",
        "node_endpoint": "lejeune.icm.usmc.mil:8443",
        "color": "#0DCC8A",
    },
    {
        "id": "quantico",
        "label": "MCB Quantico — TM Library",
        "installation": "Marine Corps Base Quantico, VA",
        "system": "Technical Manual library (NSN-tagged maintenance corpus)",
        "data_kind": "tech_manuals",
        "data_size_gb": 12.0,
        "bandwidth_mbps": 100,
        "operating_env": "secure-enclave",
        "security_posture": "CUI / FOUO — ICD 503 enclave",
        "compliance_authority": "ICD 503 / DoD IL5 / DCSA spillage controls",
        "compute_posture": "DDE inference container ready (compute-only egress)",
        "node_endpoint": "quantico.tm.usmc.mil:8443",
        "color": "#00FFA7",
    },
]


# ---------------------------------------------------------------------------
# Demo queries — each picked because central RAG is *catastrophic* for it
# ---------------------------------------------------------------------------
QUERIES = [
    {
        "id": "m1a1_transmission",
        "title": "M1A1 transmission risk",
        "frame": "Marine at MCLB Albany asks for serial-number M1A1s at risk for "
                 "transmission failure based on the last 90 days of work orders.",
        "question": "Which serial-number M1A1s are at risk for transmission "
                    "failure based on the last 90 days of work orders?",
        "primary_node": "albany",
        "involves": ["albany", "lejeune", "quantico"],
        "stakes": "Pre-deployment readiness call; must answer in seconds, not days.",
    },
    {
        "id": "prc117_battery",
        "title": "PRC-117G BB-2590 shortage projection",
        "frame": "S-4 needs to know which units will run out of BB-2590 batteries "
                 "for AN/PRC-117G manpacks within the next 14 days.",
        "question": "Which units will run out of BB-2590 batteries for AN/PRC-117G "
                    "manpacks within the next 14 days, and which depot can lateral?",
        "primary_node": "lejeune",
        "involves": ["albany", "lejeune"],
        "stakes": "DDIL deployable cell — bandwidth too small to ship 8 GB to a "
                  "central embedder.",
    },
    {
        "id": "jltv_brake_recall",
        "title": "JLTV brake-caliper recall scope",
        "frame": "Vendor issued a recall on a brake-caliper lot; commander needs "
                 "to know which JLTVs across LOGCOM are affected.",
        "question": "Across all installations, which JLTVs (by serial) used the "
                    "recalled brake-caliper lot in the last 18 months?",
        "primary_node": "albany",
        "involves": ["albany", "quantico"],
        "stakes": "ICD 503 forbids copying the Quantico maintenance corpus into a "
                  "central index. DDE answers from inside the enclave.",
    },
    {
        "id": "m240_barrel_life",
        "title": "M240 barrel-life cross-check",
        "frame": "Armorer needs to validate barrel-life thresholds against the "
                 "TM and reconcile against round-count work orders.",
        "question": "Which M240B barrels have exceeded 80% of their TM-published "
                    "round-count threshold, and where are they now?",
        "primary_node": "quantico",
        "involves": ["albany", "lejeune", "quantico"],
        "stakes": "TM library is CUI; cannot leave Quantico. DDE composes the "
                  "answer with zero data movement.",
    },
    {
        "id": "mtvr_tire_lateral",
        "title": "MTVR 16R20 tire lateral feasibility",
        "frame": "Battalion needs 12 MTVR tires before a CONUS exercise; planner "
                 "wants the cheapest lateral-transfer plan.",
        "question": "What is the lowest-cost lateral-transfer plan to source 12 "
                    "MTVR 16R20 tires for the exercise window?",
        "primary_node": "lejeune",
        "involves": ["albany", "lejeune"],
        "stakes": "Operator workstation has no AO to host 50 GB of GCSS-MC; DDE "
                  "spawns compute at Albany, returns only the lateral plan.",
    },
]


# ---------------------------------------------------------------------------
# Per-node mock corpora — 30 chunks each, written to JSONL + .npy embeddings
# ---------------------------------------------------------------------------
M1A1_SERIALS = [f"USMC-M1A1-{i:05d}" for i in range(40000, 40080)]
JLTV_SERIALS = [f"USMC-JLTV-{i:05d}" for i in range(20000, 20060)]

UNITS = [
    "1st Bn 6th Marines", "2d Bn 8th Marines", "3d Bn 2d Marines",
    "1st LAR Bn", "2d Tank Bn (legacy)", "MWSS-271", "CLB-22",
    "CLB-2", "MAGTF Logistics Group", "8th ESB",
]


def _albany_chunks(rng: random.Random) -> list[dict]:
    """30 GCSS-MC work-order summaries — biased toward transmission + brake events."""
    out = []
    fault_codes = [
        ("TRANS-SLIP",   "Transmission slipping under load — operator reports."),
        ("TRANS-OVRH",   "Transmission overheat alarm at sustained 35 mph."),
        ("BRAKE-CALIPER","Caliper sticking; recall lot LRC-2024-3318 suspected."),
        ("ELEC-BUS",     "Intermittent CAN bus dropout; ECU reflash recommended."),
        ("HYD-LEAK",     "Hydraulic line weep at front diff coupling."),
    ]
    for i in range(30):
        if i < 10:
            ser = rng.choice(M1A1_SERIALS)
            code, desc = fault_codes[rng.choices([0, 0, 1, 3, 4],
                                                  weights=[3, 3, 2, 1, 1], k=1)[0]]
            platform = "M1A1"
        elif i < 22:
            ser = rng.choice(JLTV_SERIALS)
            code, desc = fault_codes[rng.choices([2, 3, 4, 0],
                                                  weights=[5, 2, 2, 1], k=1)[0]]
            platform = "JLTV M1278A1"
        else:
            ser = f"USMC-MTVR-{rng.randint(30000, 30040):05d}"
            code, desc = rng.choice(fault_codes)
            platform = "MTVR MK23"
        days_ago = rng.randint(0, 90)
        out.append({
            "chunk_id":   f"alb-{i:03d}",
            "node":       "albany",
            "kind":       "work_order",
            "platform":   platform,
            "serial":     ser,
            "fault_code": code,
            "summary":    f"{platform} {ser} — {desc} Reported by {rng.choice(UNITS)}, "
                          f"opened {days_ago}d ago, status OPEN.",
            "metadata":   {"days_ago": days_ago, "unit": rng.choice(UNITS)},
        })
    return out


def _lejeune_chunks(rng: random.Random) -> list[dict]:
    """30 ICM lateral-transfer + parts records."""
    out = []
    parts = [
        ("BB-2590 Battery, AN/PRC-117G",   "5945-01-553-1212"),
        ("MTVR 16R20 Tire",                "2610-01-422-7100"),
        ("M240 Barrel Assy, Quick-Change", "1005-01-440-1010"),
        ("JLTV Brake Caliper Assy",        "2530-01-680-2233"),
        ("Hydraulic Fluid OE-46",          "9150-00-687-7197"),
    ]
    for i in range(30):
        nomen, nsn = rng.choice(parts)
        unit = rng.choice(UNITS)
        qty = rng.randint(1, 18)
        days_to_zero = rng.choice([3, 5, 7, 10, 14, 21, 28, 45, 60])
        out.append({
            "chunk_id":   f"lej-{i:03d}",
            "node":       "lejeune",
            "kind":       "icm_record",
            "nsn":        nsn,
            "nomenclature": nomen,
            "unit":       unit,
            "qty_on_hand":qty,
            "summary":    f"{unit} holds {qty}x {nomen} (NSN {nsn}); projected "
                          f"days-to-zero at current burn rate: {days_to_zero}d. "
                          f"Lateral feasibility: HIGH from CLB-2 stock.",
            "metadata":   {"days_to_zero": days_to_zero, "qty": qty},
        })
    return out


def _quantico_chunks(rng: random.Random) -> list[dict]:
    """30 NSN-tagged TM chunks (CUI corpus)."""
    out = []
    tm_topics = [
        ("M1A1 Transmission Service Limits", "TM 9-2350-264-10",
         "Transmission diagnostic codes TS-2 / TS-4 indicate impending clutch "
         "pack failure; immediate Q-1 service required."),
        ("AN/PRC-117G Battery Maintenance", "TM 11-5820-1234-12",
         "BB-2590 nominal cycle life: 800 charge cycles; replace at 30% capacity."),
        ("M240B Barrel Round-Count Threshold", "TM 9-1005-313-10",
         "Quick-change barrel rated 15,000 rounds; inspect bore at 12,000 (80%)."),
        ("JLTV Brake Caliper Lot Recall", "MWO/REC 2024-3318",
         "Recall on caliper lot LRC-2024-3318 — affected production window "
         "Jul-2024 through Sep-2024."),
        ("MTVR Tire 16R20 Wear Limits", "TM 9-2320-364-10",
         "16R20 tire minimum tread depth 4/32\"; rotate every 3,000 mi."),
    ]
    for i in range(30):
        title, doc, body = rng.choice(tm_topics)
        out.append({
            "chunk_id":   f"qua-{i:03d}",
            "node":       "quantico",
            "kind":       "tech_manual",
            "doc":        doc,
            "title":      title,
            "summary":    f"{doc} ({title}) — {body}",
            "metadata":   {"classification": "CUI", "icd_503_enclave": True},
        })
    return out


def _embed_local(chunks: list[dict], rng: random.Random) -> np.ndarray:
    """Deterministic-pseudorandom 384-dim 'embeddings' (no external API)."""
    arr = np.zeros((len(chunks), 384), dtype=np.float32)
    for i, ch in enumerate(chunks):
        h = hashlib.sha256(ch["summary"].encode("utf-8")).digest()
        seed = int.from_bytes(h[:8], "big")
        local = np.random.default_rng(seed).normal(0, 1, 384).astype(np.float32)
        local /= np.linalg.norm(local) + 1e-9
        arr[i] = local
    return arr


# ---------------------------------------------------------------------------
# Hash-chained audit log seed
# ---------------------------------------------------------------------------
def _seed_audit() -> list[dict]:
    base_dt = datetime(2026, 4, 26, 8, 0, 0, tzinfo=timezone.utc)
    rows: list[dict] = []
    prev = "0" * 64
    seeds = [
        ("albany",   "registered DDE inference container", "vLLM-0.5.1"),
        ("lejeune",  "registered DDE inference container", "llama.cpp-2026.4"),
        ("quantico", "registered DDE inference container (CUI enclave)", "vLLM-0.5.1"),
    ]
    for i, (node, action, runtime) in enumerate(seeds):
        ts = (base_dt + timedelta(minutes=i * 7)).isoformat()
        rec = {
            "ts":       ts,
            "node":     node,
            "action":   action,
            "runtime":  runtime,
            "model":    "kamiwaza-deployed-mini",
            "prev_hash":prev,
        }
        payload = json.dumps(rec, sort_keys=True).encode("utf-8")
        rec["hash"] = hashlib.sha256(payload).hexdigest()
        prev = rec["hash"]
        rows.append(rec)
    return rows


# ---------------------------------------------------------------------------
# Pre-compute execution traces (cache-first; LLM optional)
# ---------------------------------------------------------------------------
def _precompute_briefs(nodes: list[dict], queries: list[dict]) -> dict[str, dict]:
    """For each query, run the DDE simulator + the answer composer and cache
    the full execution trace + composed answer markdown."""
    # Local imports so generate.py is self-sufficient if shared/ is missing
    from src.dde import simulate_execution  # noqa: E402
    from src.agent import compose_answer    # noqa: E402

    out: dict[str, dict] = {}
    for q in queries:
        trace = simulate_execution(q, nodes)
        answer_md = compose_answer(q, nodes, trace, use_cache=False)
        out[q["id"]] = {
            "query":  q,
            "trace":  trace,
            "answer": answer_md,
        }
        print(f"[generate] cached brief for {q['id']} "
              f"(naive={trace['naive']['bytes']:,}B, "
              f"dde={trace['dde']['bytes']:,}B, "
              f"answer={len(answer_md)} chars)")
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(*, with_briefs: bool = True) -> None:
    rng = random.Random(1776)
    np.random.seed(1776)

    print("[generate] nodes.json…")
    (ROOT / "nodes.json").write_text(json.dumps(NODES, indent=2))

    print("[generate] queries.json…")
    (ROOT / "queries.json").write_text(json.dumps(QUERIES, indent=2))

    print("[generate] mock_corpora/*.jsonl + mock_embeddings/*.npy…")
    corpora_dir = ROOT / "mock_corpora"
    emb_dir = ROOT / "mock_embeddings"
    corpora_dir.mkdir(parents=True, exist_ok=True)
    emb_dir.mkdir(parents=True, exist_ok=True)

    for node_id, gen in (("albany", _albany_chunks),
                         ("lejeune", _lejeune_chunks),
                         ("quantico", _quantico_chunks)):
        chunks = gen(rng)
        with open(corpora_dir / f"{node_id}.jsonl", "w") as f:
            for ch in chunks:
                f.write(json.dumps(ch) + "\n")
        emb = _embed_local(chunks, rng)
        np.save(emb_dir / f"{node_id}.npy", emb)
        print(f"  {node_id}: {len(chunks)} chunks, embeddings shape {emb.shape}")

    print("[generate] audit_logs/dde_audit.jsonl (seed)…")
    audit_dir = ROOT / "audit_logs"
    audit_dir.mkdir(parents=True, exist_ok=True)
    seed_rows = _seed_audit()
    with open(audit_dir / "dde_audit.jsonl", "w") as f:
        for r in seed_rows:
            f.write(json.dumps(r) + "\n")

    if with_briefs:
        # Make the app importable for the precompute pass
        if str(APP_ROOT) not in sys.path:
            sys.path.insert(0, str(APP_ROOT))
        print("[generate] pre-warming 5 cached briefs (cache-first pattern)…")
        briefs = _precompute_briefs(NODES, QUERIES)
        (ROOT / "cached_briefs.json").write_text(json.dumps(briefs, indent=2))

    print(f"[generate] done. wrote 3 nodes, 5 queries, 90 chunks to {ROOT}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--no-briefs", action="store_true",
                   help="Skip the LLM hero precompute (synth + JSON only).")
    args = p.parse_args()
    main(with_briefs=not args.no_briefs)
