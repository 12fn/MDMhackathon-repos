"""CHAIN-OF-COMMAND — ReBAC graph-walk authorization engine.

Inspired by Google Zanzibar (relation tuples + check) and OpenFGA. The engine
loads the synthetic ORBAT graph as a NetworkX DiGraph, then computes a
relationship-based authorization decision for (subject, object) pairs by
walking the relationship graph.

Authorization decision = AND of three checks:
    1. CLEARANCE      — subject's HAS_CLEARANCE rank ≥ doc classification rank.
    2. RELEASABILITY  — subject's nationality satisfies the doc's REL_TO set.
    3. NEED-TO-KNOW   — there exists an authorizing path from the subject
                        through the ORBAT (via MEMBER_OF / ATTACHED_TO /
                        DETACHED_TO / OPCON_TO / TACON_TO edges) that reaches
                        an org with HAS_NEED_TO_KNOW for this document.

The engine returns the actual edge sequence so the UI can light up the
authorizing path on the ORBAT graph (the visual hero move).
"""
from __future__ import annotations

import json
from collections import deque
from functools import lru_cache
from pathlib import Path
from typing import Any

import networkx as nx

DATA = Path(__file__).resolve().parent.parent / "data"

# ─────────────────────────────────────────────────────────────────────────────
# Rankings (per DoDM 5200.02 — clearances)
# ─────────────────────────────────────────────────────────────────────────────
CLEARANCE_RANK: dict[str, int] = {
    "UNCLASS": 0,
    "FOUO": 1,
    "CUI": 2,
    "NATO_RESTRICTED": 2,
    "CONFIDENTIAL": 3,
    "NATO_SECRET": 4,
    "SECRET": 4,
    "TS": 5,
    "TS//SCI": 6,
}

# Releasability buckets — what nationality satisfies what bucket
REL_BUCKETS: dict[str, set[str]] = {
    "ALL": {"USA", "GBR", "DEU", "FRA", "AUS", "CAN", "NZL", "JPN", "KOR", "ANY"},
    "USA": {"USA"},
    "FVEY": {"USA", "GBR", "AUS", "CAN", "NZL"},
    "NATO": {"USA", "GBR", "DEU", "FRA", "CAN", "ITA", "ESP", "POL", "TUR", "NLD"},
}

# Edges that form the ORBAT chain-of-command for need-to-know inheritance
COMMAND_EDGE_TYPES = {"MEMBER_OF", "ATTACHED_TO", "DETACHED_TO", "OPCON_TO", "TACON_TO"}


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def load_orbat() -> dict:
    return json.loads((DATA / "orbat.json").read_text())


@lru_cache(maxsize=1)
def load_personnel() -> list[dict]:
    return json.loads((DATA / "personnel.json").read_text())


@lru_cache(maxsize=1)
def load_documents() -> list[dict]:
    return json.loads((DATA / "documents.json").read_text())


@lru_cache(maxsize=1)
def load_relationship_types() -> list[dict]:
    return json.loads((DATA / "relationship_types.json").read_text())


@lru_cache(maxsize=1)
def load_demo_queries() -> list[dict]:
    return json.loads((DATA / "demo_queries.json").read_text())


@lru_cache(maxsize=1)
def load_cached_briefs() -> dict:
    p = DATA / "cached_briefs.json"
    if not p.exists():
        return {"queries": {}}
    return json.loads(p.read_text())


# ─────────────────────────────────────────────────────────────────────────────
# Graph construction
# ─────────────────────────────────────────────────────────────────────────────
def _build_graph(overrides: dict | None = None) -> nx.MultiDiGraph:
    """Build a NetworkX MultiDiGraph from the ORBAT JSON.

    `overrides` lets the UI mutate specific edges live (e.g. flip 24MEU's
    OPCON_TO edge to a different CCMD) without touching the source data.
    Shape: {"add": [{src,dst,rel,...}], "remove": [{src,dst,rel}]}
    """
    orbat = load_orbat()
    personnel = load_personnel()
    docs = load_documents()

    g = nx.MultiDiGraph()

    # Unit nodes
    for u in orbat["units"]:
        g.add_node(
            u["id"], kind=u["kind"], label=u["label"],
            echelon=u.get("echelon", "UNIT"),
            lat=u.get("lat"), lon=u.get("lon"),
        )

    # Personnel nodes
    for p in personnel:
        g.add_node(
            p["id"], kind="person", label=p["name"],
            rank=p["rank"], clearance=p["clearance"],
            nationality=p["nationality"], current_unit=p["current_unit"],
            mos=p["mos"], edipi=p["edipi"],
        )
        # Clearance pseudo-nodes
        clr_id = f"CLR_{p['clearance']}"
        if clr_id not in g:
            g.add_node(clr_id, kind="clearance", label=f"Clearance: {p['clearance']}")

    # Document nodes
    for d in docs:
        g.add_node(
            d["id"], kind="document", label=d["title"],
            classification=d["classification"], topic=d["topic"],
            classified_by=d["classified_by"], rel_to=d["rel_to"],
        )

    # OCA / REL pseudo-nodes
    for d in docs:
        oca = d["classified_by"]
        if oca not in g:
            g.add_node(oca, kind="oca", label=f"OCA: {oca}")
        for rel in d["rel_to"]:
            rel_id = f"REL_{rel}"
            if rel_id not in g:
                g.add_node(rel_id, kind="releasability", label=f"REL_TO: {rel}")

    # Edges
    for e in orbat["edges"]:
        # Apply removes
        if overrides and "remove" in overrides:
            if any(
                r["src"] == e["src"] and r["dst"] == e["dst"] and r["rel"] == e["rel"]
                for r in overrides["remove"]
            ):
                continue
        g.add_edge(e["src"], e["dst"], key=e["rel"], rel=e["rel"], **{
            k: v for k, v in e.items() if k not in ("src", "dst", "rel")
        })

    # Apply additions
    if overrides and "add" in overrides:
        for e in overrides["add"]:
            g.add_edge(e["src"], e["dst"], key=e["rel"], rel=e["rel"], **{
                k: v for k, v in e.items() if k not in ("src", "dst", "rel")
            })

    return g


def get_graph(overrides: dict | None = None) -> nx.MultiDiGraph:
    """Public accessor — returns a fresh graph honoring runtime overrides."""
    return _build_graph(overrides)


# ─────────────────────────────────────────────────────────────────────────────
# Path-finding — BFS over command edges
# ─────────────────────────────────────────────────────────────────────────────
def find_command_paths(g: nx.MultiDiGraph, src: str, dst_set: set[str], max_depth: int = 8) -> list[dict]:
    """BFS from src over COMMAND_EDGE_TYPES, returning every minimal path that
    lands in any node in `dst_set`. Returns list of {path, edges} dicts.
    """
    if src not in g or not dst_set:
        return []
    found: list[dict] = []
    queue = deque([(src, [src], [])])
    visited_at_depth: dict[str, int] = {src: 0}
    while queue:
        node, path_nodes, path_edges = queue.popleft()
        if node in dst_set and node != src:
            found.append({"nodes": path_nodes, "edges": path_edges})
            continue
        if len(path_nodes) - 1 >= max_depth:
            continue
        for _, neighbor, key, data in g.out_edges(node, keys=True, data=True):
            rel = data.get("rel", key)
            if rel not in COMMAND_EDGE_TYPES:
                continue
            depth = len(path_nodes)
            if neighbor in visited_at_depth and visited_at_depth[neighbor] < depth:
                # Already reached at shorter depth — skip to keep paths minimal-ish
                continue
            visited_at_depth[neighbor] = depth
            queue.append((
                neighbor,
                path_nodes + [neighbor],
                path_edges + [{"src": node, "dst": neighbor, "rel": rel, **data}],
            ))
    return found


def shortest_command_path(g: nx.MultiDiGraph, src: str, dst_set: set[str], max_depth: int = 8) -> dict | None:
    paths = find_command_paths(g, src, dst_set, max_depth=max_depth)
    if not paths:
        return None
    paths.sort(key=lambda p: len(p["nodes"]))
    return paths[0]


# ─────────────────────────────────────────────────────────────────────────────
# Three checks (clearance / releasability / need-to-know)
# ─────────────────────────────────────────────────────────────────────────────
def _check_clearance(person: dict, doc: dict) -> tuple[bool, str]:
    p_clr = person["clearance"]
    d_cls = doc["classification"]
    p_rank = CLEARANCE_RANK.get(p_clr, -1)
    d_rank = CLEARANCE_RANK.get(d_cls, -1)
    if p_rank < 0:
        return False, f"Unknown clearance '{p_clr}' on subject."
    if d_rank < 0:
        return False, f"Unknown classification '{d_cls}' on document."
    # NATO clearances are a separate rail — a US SECRET does not grant access
    # to NATO_SECRET-marked material without an explicit NATO caveat held by
    # the Marine. Enforced here rather than via rank arithmetic.
    nato_doc = d_cls.startswith("NATO_")
    nato_p   = p_clr.startswith("NATO_")
    if nato_doc and not nato_p:
        return False, (
            f"CLEARANCE: doc is on the NATO rail ({d_cls}); subject holds "
            f"{p_clr} (national rail). NATO caveat / equivalence brief not held."
        )
    if not nato_doc and nato_p:
        return False, (
            f"CLEARANCE: doc is on the national rail ({d_cls}); subject holds "
            f"{p_clr} (NATO rail). National-rail caveat not held."
        )
    if p_rank < d_rank:
        return False, (
            f"CLEARANCE: subject {p_clr} (rank {p_rank}) < "
            f"document {d_cls} (rank {d_rank})."
        )
    return True, (
        f"CLEARANCE: subject {p_clr} (rank {p_rank}) ≥ "
        f"document {d_cls} (rank {d_rank})."
    )


def _check_releasability(person: dict, doc: dict) -> tuple[bool, str]:
    nat = person["nationality"]
    for bucket_id in doc["rel_to"]:
        bucket = REL_BUCKETS.get(bucket_id, {bucket_id})
        if nat in bucket:
            return True, (
                f"REL_TO: subject nationality {nat} ∈ bucket {bucket_id} "
                f"({sorted(bucket)})."
            )
    return False, (
        f"REL_TO: subject nationality {nat} not in any of doc's "
        f"REL_TO buckets {doc['rel_to']}."
    )


def _check_need_to_know(g: nx.MultiDiGraph, person: dict, doc: dict) -> tuple[bool, str, dict | None]:
    """Walk the ORBAT from the subject's current unit looking for any org that
    has HAS_NEED_TO_KNOW for this document."""
    # Need-to-know orgs as the BFS target set
    nodes_needing = {
        e[0] for e in g.in_edges(doc["id"], keys=True, data=True)
        if e[2] == "HAS_NEED_TO_KNOW" or (len(e) > 3 and e[3].get("rel") == "HAS_NEED_TO_KNOW")
    }
    # NetworkX MultiDiGraph in_edges with keys+data returns 4-tuples (u, v, k, d)
    nodes_needing = set()
    for u, v, k, d in g.in_edges(doc["id"], keys=True, data=True):
        if d.get("rel", k) == "HAS_NEED_TO_KNOW":
            nodes_needing.add(u)
    if not nodes_needing:
        return False, f"NEED-TO-KNOW: no org carries HAS_NEED_TO_KNOW for {doc['id']}.", None

    # BFS from the subject through command edges
    path = shortest_command_path(g, person["id"], nodes_needing)
    if path is None:
        return False, (
            f"NEED-TO-KNOW: no path through MEMBER_OF/ATTACHED/DETACHED/OPCON/TACON "
            f"from {person['id']} reaches any of need-to-know orgs "
            f"{sorted(nodes_needing)}."
        ), None
    # Tail edge: terminal_org → doc
    terminal = path["nodes"][-1]
    final_edge = {
        "src": terminal, "dst": doc["id"], "rel": "HAS_NEED_TO_KNOW",
        "topic": doc["topic"],
    }
    full_path = {
        "nodes": path["nodes"] + [doc["id"]],
        "edges": path["edges"] + [final_edge],
    }
    rels = " → ".join(f"[{e['rel']}]" for e in full_path["edges"])
    return True, (
        f"NEED-TO-KNOW: authorizing path "
        f"{' → '.join(full_path['nodes'])}  via  {rels}."
    ), full_path


# ─────────────────────────────────────────────────────────────────────────────
# Top-level: compute_access — the canonical ReBAC check
# ─────────────────────────────────────────────────────────────────────────────
def compute_access(subject_id: str, object_id: str, *, overrides: dict | None = None) -> dict:
    """Compute the ReBAC verdict for (subject, object).

    Returns a verdict dict the UI consumes:
        {
          decision: ALLOW|DENY,
          reason_summary: one-line summary,
          checks: [{name, ok, reason}],
          authorizing_path: {nodes, edges} | None,
          subject, object,
        }
    """
    g = get_graph(overrides)

    # Resolve nodes
    if subject_id not in g:
        return {"decision": "ERROR", "reason_summary": f"Subject {subject_id} not in graph."}
    if object_id not in g:
        return {"decision": "ERROR", "reason_summary": f"Object {object_id} not in graph."}

    # Pull person + doc dicts
    person = next((p for p in load_personnel() if p["id"] == subject_id), None)
    doc = next((d for d in load_documents() if d["id"] == object_id), None)
    if not person:
        return {"decision": "ERROR", "reason_summary": f"{subject_id} is not a person."}
    if not doc:
        return {"decision": "ERROR", "reason_summary": f"{object_id} is not a document."}

    # Three checks
    clr_ok, clr_msg = _check_clearance(person, doc)
    rel_ok, rel_msg = _check_releasability(person, doc)
    n2k_ok, n2k_msg, path = _check_need_to_know(g, person, doc)

    decision = "ALLOW" if (clr_ok and rel_ok and n2k_ok) else "DENY"

    # Reason summary — pick the most informative line
    if decision == "ALLOW":
        # Identify the pivot relationship — prefer the most "remarkable" edge
        # type (OPCON > TACON > DETACHED > ATTACHED > MEMBER_OF) for the summary.
        priority = {"OPCON_TO": 4, "TACON_TO": 3, "DETACHED_TO": 2, "ATTACHED_TO": 1}
        candidates = [e for e in (path or {}).get("edges", []) if e["rel"] in priority]
        pivot = max(candidates, key=lambda e: priority[e["rel"]]) if candidates else None
        if pivot:
            reason_summary = (
                f"ALLOW via {pivot['rel']} path "
                f"({pivot['src']} → {pivot['dst']})"
            )
        else:
            reason_summary = "ALLOW via direct MEMBER_OF chain."
    else:
        first_fail = next(
            (m for ok, m in zip((clr_ok, rel_ok, n2k_ok), (clr_msg, rel_msg, n2k_msg))
             if not ok),
            "DENY",
        )
        reason_summary = first_fail.split(":", 1)[0] if ":" in first_fail else first_fail

    return {
        "decision": decision,
        "reason_summary": reason_summary,
        "checks": [
            {"name": "CLEARANCE", "ok": clr_ok, "reason": clr_msg},
            {"name": "RELEASABILITY", "ok": rel_ok, "reason": rel_msg},
            {"name": "NEED_TO_KNOW", "ok": n2k_ok, "reason": n2k_msg},
        ],
        "authorizing_path": path,
        "subject": person,
        "object": doc,
    }


# ─────────────────────────────────────────────────────────────────────────────
# RBAC + ABAC comparison (the side-by-side hero)
# ─────────────────────────────────────────────────────────────────────────────
RBAC_ROLE_ACL: dict[str, list[str]] = {
    # Static role-based ACL — only these named roles are on the doc's access list.
    "DOC_001": ["MARFORPAC_G3", "USINDOPACOM_J3"],
    "DOC_002": ["MEU_S3", "BLT_S3"],
    "DOC_003": ["MARFOREUR_G3", "USEUCOM_J3"],
    "DOC_004": ["S3_BN", "S3_CO"],
    "DOC_005": ["S3_CO"],
    "DOC_006": ["MEU_S4", "MEU_S3"],
    "DOC_007": ["S6_BN", "VENDOR_LIAISON"],
    "DOC_008": ["INDOPACOM_STAFF", "MARFORPAC_G3"],
    "DOC_009": ["MARDIV_G3"],
    "DOC_010": ["MEU_S3"],
    "DOC_011": ["ALL"],
    "DOC_012": ["INDOPACOM_J2"],
    "DOC_013": ["MARFOREUR_G6"],
    "DOC_014": ["S4_BN"],
    "DOC_015": ["BN_S3"],
    "DOC_016": ["S4_BN", "VENDOR_LIAISON"],
    "DOC_017": ["MEU_ACE_S3"],
    "DOC_018": ["MARFORPAC_G3"],
    "DOC_019": ["MEU_S3"],
    "DOC_020": ["INDOPACOM_J3"],
}


def rbac_decision(subject_id: str, object_id: str) -> dict:
    """Naive RBAC: only the named role list on the doc gets in.

    Per the demo: the LCpl rifleman is rank-rifleman, not on any of these
    role lists, so RBAC denies the OPCON-path scenarios.
    """
    person = next((p for p in load_personnel() if p["id"] == subject_id), None)
    if not person:
        return {"decision": "ERROR", "reason": "subject not found"}
    # Pretend each Marine carries one role: their MOS + echelon-of-current-unit
    persona_roles: set[str] = set()
    persona_roles.add(person["mos"])
    persona_roles.add(person["rank"])
    persona_roles.add("ALL")  # Everyone has the world-readable role
    if person["current_unit"] == "MARFOREUR":
        persona_roles.add("MARFOREUR_G3")
    if person["current_unit"] == "24MEU":
        persona_roles.add("MEU_S3")
    if person["current_unit"] == "1_8":
        persona_roles.add("VENDOR_LIAISON" if person["mos"] == "CONTRACTOR" else "BN_S3")

    acl = set(RBAC_ROLE_ACL.get(object_id, []))
    if persona_roles & acl:
        match = sorted(persona_roles & acl)[0]
        return {"decision": "ALLOW",
                "reason": f"RBAC: persona role '{match}' is on the doc ACL."}
    return {"decision": "DENY",
            "reason": (
                f"RBAC: none of persona roles {sorted(persona_roles)[:5]} are on "
                f"doc ACL {sorted(acl)}."
            )}


def abac_decision(subject_id: str, object_id: str) -> dict:
    """ABAC: classification ≤ clearance AND nationality satisfies REL_TO AND
    the persona's current_unit is one of the doc's need_to_know_orgs.

    Per the demo: ABAC has no concept of OPCON/TACON inheritance. So Smith's
    A Co 1/8 is not on the INDOPACOM Posture Brief's need-to-know list →
    ABAC denies.
    """
    person = next((p for p in load_personnel() if p["id"] == subject_id), None)
    doc = next((d for d in load_documents() if d["id"] == object_id), None)
    if not person or not doc:
        return {"decision": "ERROR", "reason": "subject or object not found"}

    clr_ok, clr_msg = _check_clearance(person, doc)
    rel_ok, rel_msg = _check_releasability(person, doc)
    if not clr_ok:
        return {"decision": "DENY", "reason": clr_msg}
    if not rel_ok:
        return {"decision": "DENY", "reason": rel_msg}
    if person["current_unit"] not in doc["need_to_know_orgs"]:
        return {"decision": "DENY",
                "reason": (
                    f"ABAC: persona current_unit '{person['current_unit']}' not in "
                    f"doc need_to_know_orgs {doc['need_to_know_orgs']} (no "
                    f"OPCON / TACON inheritance in pure ABAC)."
                )}
    return {"decision": "ALLOW",
            "reason": "ABAC: classification, releasability, and unit-attribute all match."}


def three_way_compare(subject_id: str, object_id: str, *, overrides: dict | None = None) -> dict:
    """Run all three models side-by-side."""
    return {
        "rbac": rbac_decision(subject_id, object_id),
        "abac": abac_decision(subject_id, object_id),
        "rebac": compute_access(subject_id, object_id, overrides=overrides),
    }
