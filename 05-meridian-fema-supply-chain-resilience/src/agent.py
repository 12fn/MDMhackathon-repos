# MERIDIAN — MARFORPAC sustainment node OPORD-style climate brief
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""MERIDIAN agent — two-step LLM pipeline.

Step 1 (chat_json):  Score every node 0-10 with structured JSON output.
Step 2 (chat):       Render a USMC OPORD-style PARA 1-5 brief naming the
                     top-3 named threats and recommended actions per CCDR.

The hero call (step 2) prefers gpt-5.4 (no -mini) for narrative polish;
falls back to the standard mini chain on error.

A deterministic heuristic baseline (`baseline_scores`) is also exposed so the
UI / topology graph never depends on LLM completion to render colored nodes
or the `nodes_at_critical_risk` counter.
"""
from __future__ import annotations

import concurrent.futures
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Make `shared` importable when this file is run from anywhere.
ROOT = Path(__file__).resolve().parents[3]  # repo root: hackathonMDM/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHE_DIR = DATA_DIR
CACHED_BRIEF_PATH = CACHE_DIR / "cached_brief.json"
CACHED_SCORES_PATH = CACHE_DIR / "cached_scores.json"

# Hero LLM call timeout (seconds). gpt-5.4 occasionally hangs >90s; we cap it
# so the demo's 90 s window is never blocked.
HERO_CALL_TIMEOUT_S = 35.0
SCORING_CALL_TIMEOUT_S = 25.0


# ---------- I/O helpers ------------------------------------------------------

def load_nodes() -> list[dict]:
    return json.loads((DATA_DIR / "nodes.json").read_text())


def load_edges() -> list[dict]:
    return json.loads((DATA_DIR / "edges.json").read_text())


def load_reports() -> list[dict]:
    """Return list of {file, kind, target, body} for every md report on disk."""
    out = []
    for p in sorted((DATA_DIR / "reports").glob("*.md")):
        # filename pattern: NN_kind_TARGET.md
        stem_parts = p.stem.split("_", 2)
        kind = stem_parts[1] if len(stem_parts) >= 2 else "unknown"
        target = stem_parts[2] if len(stem_parts) >= 3 else ""
        out.append({
            "file": p.name,
            "kind": kind,
            "target": target,
            "body": p.read_text(),
        })
    return out


def inject_incident(report: dict) -> Path:
    """Persist an injected incident to data/reports/. Returns path."""
    DATA_DIR.joinpath("reports").mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    fname = f"99_inject_{report.get('target_id', 'XXX')}_{ts}.md"
    p = DATA_DIR / "reports" / fname
    p.write_text(report["body"])
    return p


# ---------- Heuristic baseline scoring (no LLM dependency) -------------------
#
# The graph + the "Nodes at critical risk" counter must render the moment the
# user lands on the page (or the moment the GENERATE button is clicked). They
# can NOT be gated on the hero gpt-5.4 call which may take 30-90s. Below is a
# deterministic, fully offline scoring function that maps the seeded synthetic
# corpus -> a stable risk index per node. The LLM scorer (`score_nodes`) layers
# its richer rationale on top when it returns; if it doesn't, this baseline
# stands in directly.

# Per-report-kind weight contributing to a node's risk index. Tuned so the
# seeded 30-report corpus produces 2-4 nodes >= 8.0 (the "critical" band).
KIND_WEIGHT = {
    "typhoon": 2.4,
    "swell":   1.1,
    "geo":     1.3,
    "equip":   1.4,
    "climate": 0.8,
    "inject":  3.0,  # injected FLASH always pushes its node into the critical band
    "unknown": 0.6,
}

# Short human-readable threat label per kind (shown as `top_threat` in baseline).
KIND_THREAT_LABEL = {
    "typhoon": "Tropical cyclone CPA <72h (JTWC)",
    "swell":   "Long-period swell ramp closure (NOAA)",
    "geo":     "Geopolitical incident (J2)",
    "equip":   "Equipment outage (G-4)",
    "climate": "Cumulative climate stress (FEMA)",
    "inject":  "FLASH incident (injected)",
    "unknown": "Mixed indicators",
}


def baseline_scores(nodes: list[dict], reports: list[dict]) -> list[dict]:
    """Deterministic heuristic risk scoring — no LLM, never hangs, never zero.

    Combines:
      - count + kind of recent reports targeting each node
      - node criticality (10 = APRA / AAFB / KADENA / YOKO)
      - small lift for downstream-blast-radius (high throughput nodes)

    Output schema matches `score_nodes`.
    """
    by_id = {n["id"]: n for n in nodes}
    # Tally reports per node by kind (most recent kind wins for the threat label).
    per_node: dict[str, dict] = {n["id"]: {"weight": 0.0, "kinds": [], "count": 0}
                                 for n in nodes}
    for r in reports:
        tgt = r.get("target")
        kind = (r.get("kind") or "unknown").lower()
        if tgt not in per_node:
            continue
        per_node[tgt]["weight"] += KIND_WEIGHT.get(kind, KIND_WEIGHT["unknown"])
        per_node[tgt]["kinds"].append(kind)
        per_node[tgt]["count"] += 1

    out = []
    for n in nodes:
        agg = per_node[n["id"]]
        # Base risk: criticality scaled (3.0..6.0) + report weight.
        base = 2.5 + (n["criticality"] / 10.0) * 3.0
        risk = base + agg["weight"]
        # Throughput cascade lift — top-throughput nodes carry the chain.
        if n["throughput_tpd"] >= 6000:
            risk += 0.4
        risk = max(0.0, min(10.0, risk))

        # Pick the dominant kind for the top_threat label.
        if agg["kinds"]:
            # "typhoon" / "inject" trump everything else.
            for priority in ("inject", "typhoon", "geo", "equip", "swell", "climate"):
                if priority in agg["kinds"]:
                    label_kind = priority
                    break
            else:
                label_kind = agg["kinds"][-1]
        else:
            label_kind = "unknown"

        confidence = "HIGH" if agg["count"] >= 3 else ("MODERATE" if agg["count"] >= 1 else "LOW")
        rationale = (
            f"Heuristic baseline: {agg['count']} report(s) on file, "
            f"node criticality {n['criticality']}/10, throughput {n['throughput_tpd']:,} tpd."
        )
        out.append({
            "node_id": n["id"],
            "risk_index": round(risk, 2),
            "top_threat": KIND_THREAT_LABEL[label_kind],
            "confidence": confidence,
            "rationale": rationale,
            "_source": "baseline",
        })
    return out


def nodes_at_critical_risk(scores: list[dict], threshold: float = 7.5) -> int:
    """Count of nodes with risk_index >= threshold. Deterministic from baseline."""
    return sum(1 for s in scores if float(s.get("risk_index", 0.0)) >= threshold)


# ---------- Step 1: node scoring (chat_json) ---------------------------------

NODE_SCORE_SYSTEM = """You are MERIDIAN, an agentic supply-chain climate-resilience analyst
for the United States Marine Corps' MARFORPAC sustainment enterprise.

You will receive (a) a list of 12 critical nodes with attributes and (b) a corpus of
recent NOAA marine forecasts, JTWC tropical cyclone warnings, FEMA Supply Chain
Climate Resilience entries, INDOPACOM J2 incident reports, and MARFORPAC G-4
equipment outage notices.

For EVERY node in the input list, produce a structured JSON entry with:
  - "node_id":     the 3-6 char node id verbatim from the node list
  - "risk_index":  float 0.0-10.0 (10 = imminent severance), reflect cumulative
                   threats observed in the reports plus node criticality and
                   downstream cascade exposure
  - "top_threat":  one short string naming the single most pressing hazard
                   (e.g. "Typhoon DOKSURI-26E CPA <72h", "Swell ramp closure",
                   "Pier crane outage", "PRC harassment", "Cable cut")
  - "confidence":  one of "HIGH" / "MODERATE" / "LOW"
  - "rationale":   one sentence (<= 240 chars) explaining the score, citing
                   report evidence by kind (typhoon/swell/equip/geo/climate)

Return a single JSON object: {"scores": [ {...}, ... 12 entries ... ]}.
Score every node, even ones with no recent reports (use criticality + topology).
Be calibrated: do not assign 9+ to multiple nodes unless reports clearly justify.
"""


def build_node_score_prompt(nodes: list[dict], reports: list[dict]) -> list[dict]:
    nodes_brief = [
        {
            "id": n["id"], "name": n["name"], "kind": n["kind"],
            "ccdr": n["ccdr"], "criticality": n["criticality"],
            "throughput_tpd": n["throughput_tpd"],
            "fuel_storage_kgal": n["fuel_storage_kgal"],
            "runway_ft": n["runway_ft"],
        }
        for n in nodes
    ]
    # Pack reports compactly; keep first ~600 chars of each so prompt stays small.
    report_lines = []
    for r in reports:
        body = r["body"].strip()
        if len(body) > 700:
            body = body[:700] + " …(truncated)"
        report_lines.append(f"--- {r['file']} ({r['kind']} -> {r['target']}) ---\n{body}")
    corpus = "\n\n".join(report_lines)

    user = (
        "NODES (JSON):\n"
        + json.dumps(nodes_brief, indent=2)
        + "\n\nREPORTS (markdown corpus, last 60 days):\n"
        + corpus
        + "\n\nReturn JSON: {\"scores\":[{node_id,risk_index,top_threat,confidence,rationale}, ...]}"
    )
    return [
        {"role": "system", "content": NODE_SCORE_SYSTEM},
        {"role": "user", "content": user},
    ]


def _call_chat_json_with_timeout(msgs: list[dict], timeout_s: float) -> dict | None:
    """Run chat_json under a hard wall-clock timeout. Returns None on timeout/err."""
    def _go() -> dict:
        return chat_json(
            msgs,
            schema_hint='{"scores":[{"node_id":str,"risk_index":float,"top_threat":str,"confidence":str,"rationale":str}]}',
            temperature=0.2,
        )
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_go).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def score_nodes(nodes: list[dict], reports: list[dict]) -> list[dict]:
    """Step 1: structured-output JSON node scoring with deterministic baseline.

    Always starts from `baseline_scores(...)` so every node has a non-zero risk
    even when the LLM returns nothing or hangs. The LLM result, when available,
    overrides the baseline entry for matching node_ids.
    """
    base = {b["node_id"]: b for b in baseline_scores(nodes, reports)}

    msgs = build_node_score_prompt(nodes, reports)
    raw = _call_chat_json_with_timeout(msgs, SCORING_CALL_TIMEOUT_S) or {}
    llm_scores = raw.get("scores") or raw.get("nodes") or []
    by_id = {s.get("node_id"): s for s in llm_scores if isinstance(s, dict)}

    out = []
    for n in nodes:
        b = dict(base[n["id"]])  # baseline copy (always present, non-zero)
        s = by_id.get(n["id"])
        if s:
            # Overlay LLM result on baseline; clamp risk_index.
            try:
                b["risk_index"] = max(0.0, min(10.0, float(s.get("risk_index", b["risk_index"]))))
            except (TypeError, ValueError):
                pass  # keep baseline value
            for key in ("top_threat", "confidence", "rationale"):
                if s.get(key):
                    b[key] = s[key]
            b["_source"] = "llm"
        out.append(b)
    return out


# ---------- Step 2: OPORD-style brief (chat) --------------------------------

OPORD_SYSTEM = """You are MERIDIAN, the climate-resilience analyst supporting the
MARFORPAC G-4 (Logistics) staff.

Compose a polished one-page **USMC OPORD-style daily resilience brief** in
markdown, with these EXACT five paragraph headers, in order:

  ## PARA 1 — SITUATION
  ## PARA 2 — MISSION
  ## PARA 3 — EXECUTION
  ## PARA 4 — SUSTAINMENT
  ## PARA 5 — COMMAND & SIGNAL

Constraints:
  - Open with a single bold one-line headline ABOVE the paragraphs.
  - PARA 1: cite the 3 highest-risk nodes by name with their risk index and the
    single named threat for each (e.g. "Typhoon DOKSURI-26E", "Swell event",
    "Pier crane outage"). Reference report kinds (NOAA, JTWC, FEMA, J2, G-4).
  - PARA 2: a single 1-2 sentence mission statement framed for MARFORPAC G-4.
  - PARA 3: exactly THREE sub-bullets, one per CCDR or component (INDOPACOM /
    CENTCOM / MARFORPAC) with a recommended action tied to a specific node.
  - PARA 4: list pre-positioning, fuel, and afloat-asset recommendations
    with hard numbers (kgal, tons/day) drawn from the reports.
  - PARA 5: name the originator (MERIDIAN / G-4 climate-resilience cell) and
    next brief time. State classification line: "UNCLASSIFIED // FOR OFFICIAL USE".
  - Keep total length under ~450 words.
  - Do NOT invent specific units or personnel by name.
"""


def build_brief_prompt(nodes: list[dict], scores: list[dict],
                       reports: list[dict]) -> list[dict]:
    by_id = {n["id"]: n for n in nodes}
    ranked = sorted(scores, key=lambda s: s["risk_index"], reverse=True)
    top3 = ranked[:3]
    top3_lines = [
        f"- {by_id[s['node_id']]['name']} ({s['node_id']}, {by_id[s['node_id']]['ccdr']}): "
        f"risk={s['risk_index']:.1f}/10, top_threat=\"{s['top_threat']}\", conf={s['confidence']}, "
        f"rationale={s['rationale']}"
        for s in top3 if s["node_id"] in by_id
    ]
    full_table = "\n".join(
        f"  {s['node_id']:6s} {s['risk_index']:4.1f}  {s['top_threat'][:60]}"
        for s in ranked
    )
    # Provide the model with a small evidence pack: most relevant 8 reports
    relevant_ids = {s["node_id"] for s in top3}
    evidence = [r for r in reports if r["target"] in relevant_ids][:8]
    evidence_text = "\n\n".join(f"--- {r['file']} ---\n{r['body'][:600]}" for r in evidence)

    user = (
        f"DTG: {datetime.utcnow().strftime('%d%H%MZ %b %Y').upper()}\n\n"
        "Top 3 highest-risk nodes:\n" + "\n".join(top3_lines) + "\n\n"
        "Full ranking (id risk top_threat):\n" + full_table + "\n\n"
        "EVIDENCE PACK (excerpts):\n" + evidence_text + "\n\n"
        "Compose the OPORD-style brief now."
    )
    return [
        {"role": "system", "content": OPORD_SYSTEM},
        {"role": "user", "content": user},
    ]


def _call_chat_with_timeout(msgs: list[dict], timeout_s: float, **kw) -> str | None:
    """Run chat() under a hard wall-clock timeout. Returns None on timeout/err."""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: chat(msgs, **kw)).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def _fallback_brief(nodes: list[dict], scores: list[dict]) -> str:
    """Deterministic OPORD-shaped brief used when the LLM hero call times out
    AND no cached brief is on disk. Renders the right shape so the demo always
    shows a real PARA 1-5 brief, never just a spinner."""
    by_id = {n["id"]: n for n in nodes}
    ranked = sorted(scores, key=lambda s: s["risk_index"], reverse=True)
    top3 = [s for s in ranked if s["node_id"] in by_id][:3]
    top3_lines = [
        f"- **{by_id[s['node_id']]['name']}** ({s['node_id']}, {by_id[s['node_id']]['ccdr']}) — "
        f"risk **{s['risk_index']:.1f}/10**, top threat: *{s['top_threat']}* "
        f"(confidence {s['confidence']})."
        for s in top3
    ]
    crit_count = nodes_at_critical_risk(scores)
    fuel_total = sum(by_id[s["node_id"]]["fuel_storage_kgal"] for s in top3)
    tons_total = sum(by_id[s["node_id"]]["throughput_tpd"] for s in top3)

    return (
        f"**MARFORPAC 12-NODE RESILIENCE BRIEF — DTG {datetime.utcnow().strftime('%d%H%MZ %b %Y').upper()}**\n\n"
        f"## PARA 1 — SITUATION\n"
        f"{crit_count} of 12 critical sustainment nodes currently sit in the elevated/critical risk band. "
        f"Top three exposures (NOAA / JTWC / FEMA / J2 / G-4 corpus):\n"
        + "\n".join(top3_lines) + "\n\n"
        f"## PARA 2 — MISSION\n"
        f"O/O MARFORPAC G-4 sustains First Island Chain Stand-In Forces by pre-positioning fuel, "
        f"sortying afloat assets, and coordinating alternate throughput at the three named nodes "
        f"to maintain >=72-hour logistics tail under the assessed climate / threat picture.\n\n"
        f"## PARA 3 — EXECUTION\n"
        f"- **INDOPACOM:** Re-distribute MPF afloat tonnage from the highest-risk port to the "
        f"nearest amber-band node; engage USCG Sector for joint port reconstitution.\n"
        f"- **CENTCOM:** Hold Diego Garcia surge fuel reserve at current posture; pre-coordinate "
        f"sealift relief leg via SUBIC if WESTPAC degrades further.\n"
        f"- **MARFORPAC:** Activate G-4 standing MOA for stevedore augmentation at any port that "
        f"slips into the critical band.\n\n"
        f"## PARA 4 — SUSTAINMENT\n"
        f"- Pre-position ~{fuel_total:,} kgal MOGAS / JP-8 across the top-3 named nodes.\n"
        f"- Project ~{tons_total:,} short-tons/day of throughput at risk if the top-3 nodes degrade simultaneously.\n"
        f"- Maintain barge-delivered F-76 contingency from the nearest fuel-terminal node.\n\n"
        f"## PARA 5 — COMMAND & SIGNAL\n"
        f"Originator: MERIDIAN / G-4 climate-resilience cell. Next brief: 24h. "
        f"Classification: **UNCLASSIFIED // FOR OFFICIAL USE**.\n"
    )


def write_brief(nodes: list[dict], scores: list[dict], reports: list[dict],
                *, hero: bool = True, use_cache: bool = True) -> str:
    """Step 2: narrative OPORD brief.

    Strategy (so the demo never hangs on a spinner):
      1. If a cached brief exists on disk, serve it instantly.
      2. Otherwise call the hero gpt-5.4 model under a wall-clock timeout
         (HERO_CALL_TIMEOUT_S). On success, persist to cached_brief.json so
         every subsequent recording is instant.
      3. On hero timeout/err, try the standard mini chain under timeout.
      4. Last resort: render a deterministic OPORD-shaped brief from the
         scores so the UI always shows real PARA 1-5 content.
    """
    # 1. Cache hit -> instant
    if use_cache and CACHED_BRIEF_PATH.exists():
        try:
            cached = json.loads(CACHED_BRIEF_PATH.read_text())
            brief = cached.get("brief")
            if brief:
                return brief
        except Exception:
            pass  # fall through to live call

    msgs = build_brief_prompt(nodes, scores, reports)

    # 2. Hero call under timeout
    if hero:
        text = _call_chat_with_timeout(
            msgs, HERO_CALL_TIMEOUT_S, model="gpt-5.4", temperature=0.45
        )
        if text and "PARA 1" in text:
            _save_cached_brief(text, source="gpt-5.4")
            return text

    # 3. Standard chain under timeout
    text = _call_chat_with_timeout(msgs, HERO_CALL_TIMEOUT_S, temperature=0.45)
    if text and "PARA 1" in text:
        _save_cached_brief(text, source="default-chain")
        return text

    # 4. Deterministic fallback
    return _fallback_brief(nodes, scores)


def _save_cached_brief(brief: str, *, source: str) -> None:
    try:
        CACHED_BRIEF_PATH.write_text(json.dumps({
            "brief": brief,
            "source": source,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }, indent=2))
    except Exception:
        pass


def warm_brief_cache(*, hero: bool = True, force: bool = False) -> Path | None:
    """One-shot: run the full pipeline and persist the brief to disk so the
    demo recording never has to wait on a live LLM call.
    Returns the cache path on success, None on failure."""
    if CACHED_BRIEF_PATH.exists() and not force:
        return CACHED_BRIEF_PATH
    nodes = load_nodes()
    reports = load_reports()
    scores = score_nodes(nodes, reports)
    text = write_brief(nodes, scores, reports, hero=hero, use_cache=False)
    if text and "PARA 1" in text:
        _save_cached_brief(text, source="warm-cache")
        return CACHED_BRIEF_PATH
    return None


# ---------- One-shot pipeline -----------------------------------------------

def run_pipeline(*, hero: bool = True) -> dict[str, Any]:
    nodes = load_nodes()
    edges = load_edges()
    reports = load_reports()
    scores = score_nodes(nodes, reports)
    brief = write_brief(nodes, scores, reports, hero=hero)
    return {
        "nodes": nodes,
        "edges": edges,
        "reports": reports,
        "scores": scores,
        "brief": brief,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


if __name__ == "__main__":
    out = run_pipeline(hero=False)
    print(json.dumps([{"id": s["node_id"], "risk": s["risk_index"], "threat": s["top_threat"]}
                      for s in sorted(out["scores"], key=lambda s: -s["risk_index"])], indent=2))
    print("\n---\n")
    print(out["brief"])
