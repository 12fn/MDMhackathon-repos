"""HUB agent — multimodal corridor analyzer.

Two-step LLM pipeline behind a deterministic feasibility engine:

  Step 0  (deterministic):  compute_corridor(origin, destination, end_item)
                           Per-mode (road/rail/waterway/air) k-shortest paths,
                           filtered against the end-item's clearance / weight
                           / dim constraints. Returns a structured plan dict.

  Step 1  (LLM, hero JSON):   chat_json -> {recommended_mode, transit_days_estimate,
                              bottleneck_named, alternate_corridors[], cost_relative}

  Step 2  (LLM, hero narrative): chat -> "POE Movement Plan" — BLUF-style markdown
                              brief naming bottlenecks and recommended COA.

Both LLM calls are wrapped in wall-clock timeouts and fall back to deterministic
"baseline_*" outputs so the UI never freezes on a spinner. The Streamlit app
prefers cached_briefs.json when present (cache-first hero pattern).
"""
from __future__ import annotations

import concurrent.futures as _cf
import csv
import heapq
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make `shared` and the app root importable from any cwd.
APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

DATA_DIR = APP_ROOT / "data"

# Hero-call timeouts. Mini chain: 15 s. Hero model: 35 s. (Per AGENT_BRIEF_V2 §B.)
HERO_JSON_TIMEOUT_S = 18.0
HERO_TEXT_TIMEOUT_S = 35.0


# ─────────────────────────────────────────────────────────────────────────────
# Loaders
# ─────────────────────────────────────────────────────────────────────────────
def load_nodes() -> list[dict]:
    return json.loads((DATA_DIR / "nodes.json").read_text())


def load_edges() -> list[dict]:
    rows: list[dict] = []
    with (DATA_DIR / "edges.csv").open() as f:
        for r in csv.DictReader(f):
            r["miles"] = int(r["miles"])
            r["capacity_tpd"] = int(r["capacity_tpd"])
            r["clearance_in"] = int(r["clearance_in"])
            r["weight_limit_lbs"] = int(r["weight_limit_lbs"])
            rows.append(r)
    return rows


def load_end_items() -> list[dict]:
    return json.loads((DATA_DIR / "end_items.json").read_text())


def load_cached_briefs() -> dict:
    p = DATA_DIR / "cached_briefs.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def find_node(node_id: str, nodes: list[dict] | None = None) -> dict | None:
    nodes = nodes or load_nodes()
    return next((n for n in nodes if n["id"] == node_id), None)


def find_end_item(item_id: str) -> dict | None:
    return next((i for i in load_end_items() if i["id"] == item_id), None)


# ─────────────────────────────────────────────────────────────────────────────
# Per-mode graph + k-shortest paths
# ─────────────────────────────────────────────────────────────────────────────
def _adj_by_mode(edges: list[dict], mode: str) -> dict[str, list[tuple[str, dict]]]:
    """Undirected adjacency for a single mode."""
    g: dict[str, list[tuple[str, dict]]] = {}
    for e in edges:
        if e["mode"] != mode:
            continue
        g.setdefault(e["a"], []).append((e["b"], e))
        g.setdefault(e["b"], []).append((e["a"], e))
    return g


def _shortest_path(
    g: dict[str, list[tuple[str, dict]]],
    start: str,
    goal: str,
) -> tuple[list[str], list[dict]] | None:
    """Dijkstra on `miles`. Returns (node_path, edge_path) or None."""
    if start not in g or goal not in g:
        return None
    if start == goal:
        return ([start], [])
    pq: list[tuple[float, str, list[str], list[dict]]] = [(0.0, start, [start], [])]
    seen: set[str] = set()
    while pq:
        cost, node, npath, epath = heapq.heappop(pq)
        if node in seen:
            continue
        seen.add(node)
        if node == goal:
            return (npath, epath)
        for nbr, edge in g.get(node, []):
            if nbr in seen:
                continue
            heapq.heappush(pq, (cost + edge["miles"], nbr, npath + [nbr], epath + [edge]))
    return None


# Average per-mode planning speed in miles/day (CONUS realistic, includes loads).
MODE_SPEED_MPD = {
    "road":     420,   # convoy / HET pace day moves
    "rail":     500,   # intermodal manifest
    "waterway": 240,   # towboat + barge
    "air":      4500,  # outsize lift
}

# Relative cost index per ton-mile (rough planning factor; lower = cheaper).
MODE_COST_REL = {
    "road":     1.00,
    "rail":     0.35,
    "waterway": 0.18,
    "air":      8.40,
}


def _feasibility(edge: dict, item: dict) -> tuple[bool, str]:
    """Check a single edge against an end-item's constraints. Returns (ok, reason)."""
    mode = edge["mode"]
    if mode in ("road", "rail"):
        if edge["clearance_in"] and item.get("height_in") and item["height_in"] > edge["clearance_in"]:
            return False, (
                f"clearance {edge['clearance_in']}\" < item height {item['height_in']}\""
            )
        if edge["weight_limit_lbs"] and item["weight_lbs"] > edge["weight_limit_lbs"]:
            return False, (
                f"weight class {edge['weight_limit_lbs']:,} lb < item {item['weight_lbs']:,} lb"
            )
    if mode == "air":
        if not item.get("air_compatible_c17", False) and item["weight_lbs"] > 50000:
            return False, "platform requires C-5 (outsize) — not C-17 air-compatible"
        if edge["weight_limit_lbs"] and item["weight_lbs"] > edge["weight_limit_lbs"]:
            return False, "exceeds outsize air payload limit"
    if mode == "rail" and not item.get("rail_compatible", True):
        return False, "platform not rail-compatible (self-deploy required)"
    if mode == "waterway":
        # Inland barge generally accepts anything that fits a 35'x195' tow.
        pass
    return True, "ok"


def assess_path(
    edges_path: list[dict],
    item: dict,
) -> dict:
    """Roll up a multi-edge path into a per-mode feasibility verdict."""
    if not edges_path:
        return {
            "miles": 0,
            "min_capacity_tpd": 0,
            "min_clearance_in": 0,
            "min_weight_limit_lbs": 0,
            "named_bottlenecks": [],
            "feasible": True,
            "reasons": [],
        }
    miles = sum(e["miles"] for e in edges_path)
    cap_road_rail = [e["capacity_tpd"] for e in edges_path if e["mode"] in ("road", "rail")]
    min_cap = min((e["capacity_tpd"] for e in edges_path), default=0)
    clearances = [e["clearance_in"] for e in edges_path if e["clearance_in"]]
    weights = [e["weight_limit_lbs"] for e in edges_path if e["weight_limit_lbs"]]
    bottlenecks = [e["bottleneck_named"] for e in edges_path if e["bottleneck_named"]]
    reasons: list[str] = []
    feasible = True
    for e in edges_path:
        ok, why = _feasibility(e, item)
        if not ok:
            feasible = False
            reasons.append(f"{e['a']}→{e['b']} ({e['mode']}): {why}")
    return {
        "miles": miles,
        "min_capacity_tpd": min_cap,
        "min_clearance_in": min(clearances) if clearances else 0,
        "min_weight_limit_lbs": min(weights) if weights else 0,
        "named_bottlenecks": bottlenecks,
        "feasible": feasible,
        "reasons": reasons,
        "capacity_road_rail_min": min(cap_road_rail) if cap_road_rail else min_cap,
    }


# ─────────────────────────────────────────────────────────────────────────────
# compute_corridor — the deterministic engine the LLM reasons over
# ─────────────────────────────────────────────────────────────────────────────
def compute_corridor(origin_id: str, destination_id: str, end_item_id: str) -> dict:
    """Build a per-mode corridor plan from origin → destination for the end-item.

    Output schema (passed into the LLM as evidence):
      {
        origin: {...node...},
        destination: {...node...},
        end_item: {...item...},
        per_mode: {
          road:     { node_path, edge_path, summary, transit_days, cost_index },
          rail:     {...},
          waterway: {...},
          air:      {...},
        },
        recommended_mode_baseline: <str>,
        baseline_bottleneck: <str>,
      }
    """
    nodes = load_nodes()
    edges = load_edges()
    item = find_end_item(end_item_id)
    if item is None:
        raise ValueError(f"unknown end_item: {end_item_id}")
    o = find_node(origin_id, nodes)
    d = find_node(destination_id, nodes)
    if o is None or d is None:
        raise ValueError(f"unknown node: {origin_id} or {destination_id}")

    per_mode: dict[str, dict] = {}
    for mode in ("road", "rail", "waterway", "air"):
        g = _adj_by_mode(edges, mode)
        sp = _shortest_path(g, origin_id, destination_id)
        if sp is None:
            per_mode[mode] = {"available": False, "reason": "no path in this mode"}
            continue
        node_path, edge_path = sp
        summary = assess_path(edge_path, item)
        transit_days = round(summary["miles"] / max(1, MODE_SPEED_MPD[mode]), 1)
        cost_index = round(summary["miles"] * MODE_COST_REL[mode] / 100, 2)
        per_mode[mode] = {
            "available": True,
            "node_path": node_path,
            "edge_path": edge_path,
            "summary": summary,
            "transit_days": transit_days,
            "cost_index": cost_index,
        }

    # Baseline recommendation: lowest cost_index among feasible modes;
    # if none feasible, lowest cost_index among available modes (with a flag).
    feasible_modes = [m for m, p in per_mode.items()
                      if p.get("available") and p["summary"]["feasible"]]
    if feasible_modes:
        rec = min(feasible_modes, key=lambda m: per_mode[m]["cost_index"])
        bottleneck = ", ".join(per_mode[rec]["summary"]["named_bottlenecks"]) or "none on recommended corridor"
    else:
        # all modes blocked; recommend the closest-to-feasible (smallest # of blocking reasons)
        avail = [m for m, p in per_mode.items() if p.get("available")]
        if avail:
            rec = min(avail, key=lambda m: len(per_mode[m]["summary"]["reasons"]) or 999)
            bottleneck = "; ".join(per_mode[rec]["summary"]["reasons"][:2])
        else:
            rec = "none"
            bottleneck = "no path in any mode"

    return {
        "origin": o,
        "destination": d,
        "end_item": item,
        "per_mode": per_mode,
        "recommended_mode_baseline": rec,
        "baseline_bottleneck": bottleneck,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# LLM helpers — defer import so importing this module doesn't require an env
# ─────────────────────────────────────────────────────────────────────────────
HERO_JSON_SYSTEM = """You are HUB, a USMC LOGCOM movement-planning analyst.

You are given an evidence pack: origin / destination / end-item, plus per-mode
(road / rail / waterway / air) shortest-path summaries with capacity, clearance,
weight limit, and named bottlenecks for each leg.

Return STRICT JSON with this schema:
{
  "recommended_mode": "road" | "rail" | "waterway" | "air",
  "transit_days_estimate": <number>,
  "bottleneck_named": <string — single named choke point or "none">,
  "alternate_corridors": [
    {"mode": <string>, "transit_days": <number>, "rationale": <string ≤ 120 chars>}
  ],
  "cost_relative": <number — index where road=1.00>
}
No prose, no markdown, no code fences. Reason from the evidence pack ONLY.
"""

HERO_TEXT_SYSTEM = """You are HUB, a USMC LOGCOM movement-planning analyst.
Compose a short polished markdown brief titled exactly "POE Movement Plan".
Mandatory sections in this order:

  ## POE Movement Plan
  **BLUF:** one sentence, recommend mode + named POE + transit days.
  **Recommended Corridor:** named legs and rationale (cite capacity / clearance /
                            weight numbers from the evidence pack).
  **Named Bottlenecks:** bullet list — each named bottleneck with the platform
                         constraint that drives it (e.g. "I-10 Lake Charles
                         bridge weight class — JLTV OK, M1A1 NO-GO without
                         OS/OW permit").
  **Alternate Corridors:** 2-3 bullets, each one mode with a one-line rationale.
  **Cost & Risk Note:** one line on cost index relative to road and the single
                        biggest residual risk.

Constraints:
  - Use the structured JSON values for transit_days_estimate, recommended_mode,
    bottleneck_named, alternate_corridors, cost_relative.
  - Use the per-mode evidence pack for all named bottlenecks and constraints.
  - Total length ≤ 300 words.
  - Do NOT invent place names, units, or model names.
  - Close with a one-line classification: "UNCLASSIFIED // FOR PLANNING USE".
"""


def _build_evidence_user(plan: dict) -> str:
    """Serialize the corridor plan compactly for the LLM."""
    o, d, item = plan["origin"], plan["destination"], plan["end_item"]
    item_block = (
        f"END ITEM: {item['id']} ({item['name']})\n"
        f"  weight_lbs={item['weight_lbs']:,}, height_in={item['height_in']}, "
        f"width_in={item['width_in']}, length_in={item['length_in']}\n"
        f"  category={item['category']}, permit_required={item['permit_required']}, "
        f"rail_compatible={item['rail_compatible']}, c17_air_compatible={item['air_compatible_c17']}\n"
        f"  notes: {item['notes']}\n"
    )
    od_block = (
        f"ORIGIN:      {o['id']} {o['name']} ({o['kind']}, {o['state']})\n"
        f"DESTINATION: {d['id']} {d['name']} ({d['kind']}, {d['state']})\n"
    )
    mode_lines = []
    for mode, mp in plan["per_mode"].items():
        if not mp.get("available"):
            mode_lines.append(f"--- {mode.upper()}: NO PATH AVAILABLE ---")
            continue
        s = mp["summary"]
        path = " → ".join(mp["node_path"])
        bn = ", ".join(s["named_bottlenecks"]) or "none"
        rs = "; ".join(s["reasons"][:3]) or "ok"
        mode_lines.append(
            f"--- {mode.upper()} ---\n"
            f"  path: {path}\n"
            f"  miles: {s['miles']}, transit_days: {mp['transit_days']}, "
            f"cost_index: {mp['cost_index']}\n"
            f"  min_capacity_tpd: {s['min_capacity_tpd']:,}, "
            f"min_clearance_in: {s['min_clearance_in']}, "
            f"min_weight_limit_lbs: {s['min_weight_limit_lbs']:,}\n"
            f"  named_bottlenecks: {bn}\n"
            f"  feasible_for_item: {s['feasible']}  reasons: {rs}\n"
        )
    return (
        item_block + "\n" + od_block + "\n"
        + "PER-MODE CORRIDOR EVIDENCE:\n" + "\n".join(mode_lines) + "\n"
        + f"\nBASELINE_RECOMMENDATION: {plan['recommended_mode_baseline']}\n"
        + f"BASELINE_BOTTLENECK: {plan['baseline_bottleneck']}\n"
    )


def _run_with_timeout(fn, timeout_s: float):
    try:
        with _cf.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(fn).result(timeout=timeout_s)
    except (_cf.TimeoutError, Exception):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Hero step 1 — chat_json
# ─────────────────────────────────────────────────────────────────────────────
def baseline_chat_json(plan: dict) -> dict:
    """Deterministic structured output if the LLM is unavailable."""
    rec = plan["recommended_mode_baseline"]
    pm = plan["per_mode"]
    transit = pm.get(rec, {}).get("transit_days", 0) if rec != "none" else 0
    cost_rel = pm.get(rec, {}).get("cost_index", 1.0) if rec != "none" else 1.0
    # Normalize cost_relative to road=1.0 if road is available.
    road_cost = pm.get("road", {}).get("cost_index", cost_rel)
    if road_cost and rec != "none":
        cost_rel = round(cost_rel / road_cost, 2)
    alts = []
    for m, mp in pm.items():
        if m == rec or not mp.get("available"):
            continue
        why = "feasible" if mp["summary"]["feasible"] else "blocked"
        bn = ", ".join(mp["summary"]["named_bottlenecks"]) or "no named bottleneck"
        alts.append({
            "mode": m,
            "transit_days": mp["transit_days"],
            "rationale": f"{why}; {bn}",
        })
    return {
        "recommended_mode": rec,
        "transit_days_estimate": transit,
        "bottleneck_named": plan["baseline_bottleneck"],
        "alternate_corridors": alts,
        "cost_relative": cost_rel,
        "_source": "baseline",
    }


def hero_chat_json(plan: dict) -> dict:
    """Step 1 — structured-output JSON. Falls back to baseline on err/timeout."""
    from shared.kamiwaza_client import chat_json  # noqa: WPS433

    msgs = [
        {"role": "system", "content": HERO_JSON_SYSTEM},
        {"role": "user", "content": _build_evidence_user(plan)},
    ]

    def _go() -> dict:
        return chat_json(
            msgs,
            schema_hint=(
                '{"recommended_mode":str,"transit_days_estimate":number,'
                '"bottleneck_named":str,"alternate_corridors":[{"mode":str,'
                '"transit_days":number,"rationale":str}],"cost_relative":number}'
            ),
            temperature=0.2,
        )

    out = _run_with_timeout(_go, HERO_JSON_TIMEOUT_S)
    if not isinstance(out, dict) or "recommended_mode" not in out:
        return baseline_chat_json(plan)
    out["_source"] = "llm"
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Hero step 2 — chat narrative
# ─────────────────────────────────────────────────────────────────────────────
def baseline_narrative(plan: dict, jb: dict) -> str:
    """Deterministic markdown brief if the LLM is unavailable."""
    o, d, item = plan["origin"], plan["destination"], plan["end_item"]
    rec = jb["recommended_mode"]
    transit = jb["transit_days_estimate"]
    bn = jb["bottleneck_named"]
    cost_rel = jb["cost_relative"]
    pm = plan["per_mode"]

    # Bottleneck callouts derived from evidence
    bn_bullets = []
    for mode, mp in pm.items():
        if not mp.get("available"):
            continue
        for nb in mp["summary"]["named_bottlenecks"]:
            verdict = "OK" if mp["summary"]["feasible"] else "NO-GO"
            note = ""
            if not mp["summary"]["feasible"] and mp["summary"]["reasons"]:
                note = " — " + mp["summary"]["reasons"][0]
            bn_bullets.append(f"- **{nb}** ({mode}) — {item['id']} {verdict}{note}")
    if not bn_bullets:
        bn_bullets.append("- No named bottlenecks on the recommended corridor.")

    alts = jb.get("alternate_corridors", []) or []
    alt_lines = [f"- **{a['mode'].upper()}** — {a['transit_days']}d · {a['rationale']}"
                 for a in alts[:3]] or ["- No alternate corridors with feasibility margin."]

    rec_path = ""
    if rec in pm and pm[rec].get("available"):
        rec_path = " → ".join(pm[rec]["node_path"])
    return (
        f"## POE Movement Plan\n\n"
        f"**BLUF:** Recommend **{rec.upper()}** corridor "
        f"{o['name']} → {d['name']} for {item['id']} ({item['name']}); "
        f"transit ~{transit} days. Named choke point: *{bn}*.\n\n"
        f"**Recommended Corridor:** {rec_path or '(no path)'}.\n"
        f"  - Min capacity: {pm.get(rec,{}).get('summary',{}).get('min_capacity_tpd',0):,} tons/day\n"
        f"  - Min clearance: {pm.get(rec,{}).get('summary',{}).get('min_clearance_in',0)} in\n"
        f"  - Min weight class: {pm.get(rec,{}).get('summary',{}).get('min_weight_limit_lbs',0):,} lb\n\n"
        f"**Named Bottlenecks:**\n" + "\n".join(bn_bullets) + "\n\n"
        f"**Alternate Corridors:**\n" + "\n".join(alt_lines) + "\n\n"
        f"**Cost & Risk Note:** Cost index {cost_rel}× road baseline. "
        f"Largest residual risk: throughput contention at "
        f"{pm.get(rec,{}).get('summary',{}).get('min_capacity_tpd',0):,} tpd "
        f"shared with surge traffic on the corridor.\n\n"
        f"UNCLASSIFIED // FOR PLANNING USE\n"
    )


def hero_chat_narrative(plan: dict, jb: dict) -> str:
    """Step 2 — markdown narrative. Falls back to baseline on err/timeout."""
    from shared.kamiwaza_client import chat  # noqa: WPS433

    user = (
        _build_evidence_user(plan)
        + "\n\nSTRUCTURED JSON (from step 1):\n"
        + json.dumps({k: v for k, v in jb.items() if not k.startswith("_")}, indent=2)
        + "\n\nCompose the POE Movement Plan now."
    )
    msgs = [
        {"role": "system", "content": HERO_TEXT_SYSTEM},
        {"role": "user", "content": user},
    ]

    def _go_hero() -> str:
        return chat(msgs, model="gpt-5.4", temperature=0.45)

    text = _run_with_timeout(_go_hero, HERO_TEXT_TIMEOUT_S)
    if text and "POE Movement Plan" in text:
        return text

    def _go_default() -> str:
        return chat(msgs, temperature=0.45)

    text = _run_with_timeout(_go_default, HERO_TEXT_TIMEOUT_S)
    if text and "POE Movement Plan" in text:
        return text

    return baseline_narrative(plan, jb)


# ─────────────────────────────────────────────────────────────────────────────
# Top-level pipeline used by the Streamlit app
# ─────────────────────────────────────────────────────────────────────────────
def run_pipeline(
    origin_id: str,
    destination_id: str,
    end_item_id: str,
    *,
    use_cache: bool = True,
    scenario_id: str | None = None,
) -> dict:
    """End-to-end: returns the corridor plan + LLM JSON + LLM narrative.

    Cache-first: if scenario_id matches a key in cached_briefs.json, return it.
    """
    if use_cache and scenario_id:
        cache = load_cached_briefs()
        if scenario_id in cache:
            return cache[scenario_id]

    plan = compute_corridor(origin_id, destination_id, end_item_id)
    jb = hero_chat_json(plan)
    narrative = hero_chat_narrative(plan, jb)
    return {
        "scenario": {"origin_id": origin_id, "destination_id": destination_id,
                     "end_item_id": end_item_id},
        "plan": plan,
        "json_brief": jb,
        "narrative": narrative,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    out = compute_corridor("MCLB-ALB", "POE-BMT", "M1A1")
    print(json.dumps({
        "recommended_baseline": out["recommended_mode_baseline"],
        "bottleneck": out["baseline_bottleneck"],
        "per_mode_summary": {
            m: {
                "available": p.get("available"),
                "transit_days": p.get("transit_days"),
                "feasible": p.get("summary", {}).get("feasible"),
                "named_bottlenecks": p.get("summary", {}).get("named_bottlenecks"),
            } for m, p in out["per_mode"].items()
        },
    }, indent=2))
