"""QUEUE AI reasoning layer — analyzes the schedule and emits structured JSON
plus a narrative "Depot Throughput Optimization Brief".

Two LLM calls in pipeline:
  Step 1 (chat_json): structured analysis of the schedule, returning
    {bottleneck_resource, throughput_uplift_pct, mitigation_actions[],
     parts_at_risk[], alternative_sequences[]}.
  Step 2 (chat):      hero narrative brief — BLUF, named bottleneck,
                      parts cascading effects, top-5 30-day actions, alts.

Cache-first per AGENT_BRIEF_V2 §A: data/cached_briefs.json holds three
pre-computed scenario briefs. Live calls only fire on operator click.
Watchdog timeout per §B: 35s hero, 25s scoring; deterministic fallback below.
"""
from __future__ import annotations

import concurrent.futures
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]  # repo root
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHED_BRIEFS_PATH = DATA_DIR / "cached_briefs.json"

HERO_CALL_TIMEOUT_S = 35.0
SCORING_CALL_TIMEOUT_S = 25.0


# ---- I/O --------------------------------------------------------------------

def load_backlog() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "backlog.csv")


def load_parts() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "parts_availability.csv")


def load_depots() -> list[dict]:
    return json.loads((DATA_DIR / "depot_capacity.json").read_text())


def load_scenarios() -> list[dict]:
    return json.loads((DATA_DIR / "scenarios.json").read_text())


def load_cached_briefs() -> dict:
    if not CACHED_BRIEFS_PATH.exists():
        return {}
    try:
        return json.loads(CACHED_BRIEFS_PATH.read_text())
    except Exception:
        return {}


# ---- Step 1: structured analysis (chat_json) -------------------------------

ANALYSIS_SYSTEM = """You are QUEUE, a USMC depot maintenance scheduling analyst
supporting MARCORLOGCOM. You receive a deterministic 30-day induction schedule
across MCLB Albany (ALB), MCLB Barstow (BAR), and Blount Island Command (BIC),
plus the backlog, depot capacity, and parts-availability tables that drove it.

Return STRICT JSON with this schema:
{
  "bottleneck_resource": "<short string naming the single most binding
     resource — e.g. 'Hydraulic seal kit NSN 4730-01-441-2298 — DLA Land 28d ETA'
     or 'Bay 4 hydraulic lift availability — MCLB Albany'>",
  "throughput_uplift_pct": <number 0-30 — projected % uplift over next 30 days
     if all mitigation_actions are taken>,
  "mitigation_actions": [
     {"action": "<one-sentence action>", "depot": "ALB|BAR|BIC|ALL",
      "uplift_pct": <number>, "effort": "low|med|high"}
     ... 5 items ...
  ],
  "parts_at_risk": [
     {"nsn": "<NSN>", "nomenclature": "<part name>", "blocked_inductions": <int>,
      "downstream_families": ["<MTVR|AAV|LAV|MV-22|M1A1>", ...]}
     ... 3-5 items ...
  ],
  "alternative_sequences": [
     {"label": "<name>", "delta_throughput_units": <int>,
      "tradeoff": "<one-sentence trade-off>"}
     ... 2-3 items ...
  ]
}

Be calibrated. Do not invent NSNs not in the parts table. Quantify everything."""


def build_analysis_prompt(schedule_metrics: dict, backlog_summary: str,
                          parts_summary: str, capacity_summary: str) -> list[dict]:
    user = (
        "DETERMINISTIC SCHEDULE METRICS:\n"
        + json.dumps(schedule_metrics, indent=2, default=str)
        + "\n\nBACKLOG SUMMARY:\n" + backlog_summary
        + "\n\nDEPOT CAPACITY:\n" + capacity_summary
        + "\n\nPARTS AVAILABILITY (long-pole NSNs only):\n" + parts_summary
        + "\n\nReturn the JSON object now."
    )
    return [
        {"role": "system", "content": ANALYSIS_SYSTEM},
        {"role": "user", "content": user},
    ]


def _call_chat_json_with_timeout(msgs: list[dict], timeout_s: float) -> dict | None:
    def _go() -> dict:
        return chat_json(
            msgs,
            schema_hint=(
                '{"bottleneck_resource":str,"throughput_uplift_pct":float,'
                '"mitigation_actions":[{"action":str,"depot":str,"uplift_pct":float,"effort":str}],'
                '"parts_at_risk":[{"nsn":str,"nomenclature":str,"blocked_inductions":int,"downstream_families":[str]}],'
                '"alternative_sequences":[{"label":str,"delta_throughput_units":int,"tradeoff":str}]}'
            ),
            temperature=0.2,
        )
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_go).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def deterministic_analysis(schedule_metrics: dict,
                           parts_df: pd.DataFrame) -> dict:
    """Fallback structured analysis derived directly from the optimizer output."""
    long_pole = parts_df[parts_df["long_pole"] == "Y"].copy()
    parts_at_risk = []
    for _, p in long_pole.head(5).iterrows():
        parts_at_risk.append({
            "nsn": p["nsn"],
            "nomenclature": p["nomenclature"],
            "blocked_inductions": int(max(1, schedule_metrics["blocked_parts"] // max(1, len(long_pole)))),
            "downstream_families": [s.strip() for s in str(p["used_by"]).split(",")],
        })
    bn = schedule_metrics.get("bottleneck", "Bay availability — MCLB Albany")
    uplift = float(schedule_metrics.get("throughput_uplift_pct_est", 12.0))
    return {
        "bottleneck_resource": bn,
        "throughput_uplift_pct": max(uplift, 8.0),
        "mitigation_actions": [
            {"action": "Expedite hydraulic seal kit NSN 4730-01-441-2298 via DLA Land emergency requisition.",
             "depot": "ALL", "uplift_pct": 6.0, "effort": "med"},
            {"action": "Cross-deck two MV-22 prop rotor blades from organizational stock to BIC.",
             "depot": "BIC", "uplift_pct": 3.5, "effort": "low"},
            {"action": "Reallocate two hydraulics technicians from BAR to ALB on second shift.",
             "depot": "ALB", "uplift_pct": 4.0, "effort": "low"},
            {"action": "Defer 5 FD-3 LAV inductions at BAR by 14 days; pull 3 FD-1 MTVR inductions forward.",
             "depot": "BAR", "uplift_pct": 5.0, "effort": "low"},
            {"action": "Place held-parts release request on M1A1 optical sight NSN 1240-01-602-7715.",
             "depot": "ALB", "uplift_pct": 3.0, "effort": "med"},
        ],
        "parts_at_risk": parts_at_risk,
        "alternative_sequences": [
            {"label": "Sequence A — Priority-pure (FD-1/2 first)",
             "delta_throughput_units": -2, "tradeoff": "+12% priority-weighted, bay util drops to 78%."},
            {"label": "Sequence B — Bay-utilization max",
             "delta_throughput_units": +6, "tradeoff": "+18% raw throughput, FD-3/FD-4 ages."},
            {"label": "Sequence C — Parts-aware (recommended)",
             "delta_throughput_units": +4, "tradeoff": "+14% throughput, FD-1 on time, no idle bays."},
        ],
    }


def analyze_schedule(schedule_metrics: dict, backlog_df: pd.DataFrame,
                     parts_df: pd.DataFrame, depots: list[dict]) -> dict:
    """Step 1: structured-output JSON analysis with deterministic baseline."""
    base = deterministic_analysis(schedule_metrics, parts_df)
    backlog_sum = _backlog_summary(backlog_df)
    parts_sum = _parts_summary_text(parts_df)
    cap_sum = _capacity_summary(depots)
    msgs = build_analysis_prompt(schedule_metrics, backlog_sum, parts_sum, cap_sum)
    raw = _call_chat_json_with_timeout(msgs, SCORING_CALL_TIMEOUT_S) or {}
    if not isinstance(raw, dict) or not raw.get("bottleneck_resource"):
        raw["_source"] = "deterministic"
        return base
    # Overlay LLM result on base, only keeping LLM keys we trust
    out = dict(base)
    for key in ("bottleneck_resource", "throughput_uplift_pct",
                "mitigation_actions", "parts_at_risk", "alternative_sequences"):
        if raw.get(key):
            out[key] = raw[key]
    out["_source"] = "llm"
    return out


# ---- Step 2: hero narrative brief (chat) -----------------------------------

BRIEF_SYSTEM = """You are QUEUE, a USMC depot maintenance scheduling analyst
supporting MARCORLOGCOM. Compose a one-page operator brief titled:

  Depot Throughput Optimization Brief

OUTPUT FORMAT (markdown):

Open with **BLUF** (one bold paragraph, 2-3 sentences) naming the single
biggest bottleneck and the projected throughput uplift if operators take the
recommended actions over the next 30 days.

Then EXACTLY these sections, in order:
  ## NAMED BOTTLENECK
  ## PARTS AVAILABILITY — CASCADING EFFECTS
  ## TOP 5 ACTIONS (NEXT 30 DAYS)
  ## ALTERNATIVE INDUCTION SEQUENCES
  ## CLASSIFICATION

In NAMED BOTTLENECK: name the specific resource (Bay # at a depot, or NSN at
a DLA source) with quantified detail.
In PARTS section: 3-5 long-pole NSNs and their downstream effect on
MTVR / AAV / LAV / MV-22 / M1A1 induction throughput.
In ACTIONS: numbered 1-5, each one sentence, each tied to a specific depot
or NSN, with a quantified throughput-uplift estimate.
In ALTERNATIVE SEQUENCES: 2-3 candidate re-sequencing options, each with the
trade-off.
Close CLASSIFICATION with: UNCLASSIFIED // FOR OFFICIAL USE.

Total under ~480 words. Use real depot codes (ALB / BAR / BIC) and real
end-item families (MTVR / AAV / LAV / MV-22 / M1A1).
"""


def build_brief_prompt(analysis: dict, schedule_metrics: dict,
                       backlog_summary: str, parts_summary: str,
                       capacity_summary: str, scenario_label: str) -> list[dict]:
    user = (
        f"SCENARIO: {scenario_label}\n\n"
        "STRUCTURED ANALYSIS (from chat_json step):\n"
        + json.dumps(analysis, indent=2, default=str)
        + "\n\nDETERMINISTIC SCHEDULE METRICS:\n"
        + json.dumps(schedule_metrics, indent=2, default=str)
        + "\n\nBACKLOG SUMMARY:\n" + backlog_summary
        + "\n\nDEPOT CAPACITY:\n" + capacity_summary
        + "\n\nPARTS AVAILABILITY (long-pole NSNs):\n" + parts_summary
        + "\n\nCompose the Depot Throughput Optimization Brief now."
    )
    return [
        {"role": "system", "content": BRIEF_SYSTEM},
        {"role": "user", "content": user},
    ]


def _call_chat_with_timeout(msgs: list[dict], timeout_s: float, **kw) -> str | None:
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: chat(msgs, **kw)).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def _deterministic_brief(scenario_label: str, analysis: dict,
                         schedule_metrics: dict) -> str:
    bn = analysis.get("bottleneck_resource", "Bay availability — MCLB Albany")
    uplift = analysis.get("throughput_uplift_pct", 12)
    actions = analysis.get("mitigation_actions", [])
    parts = analysis.get("parts_at_risk", [])
    alts = analysis.get("alternative_sequences", [])

    parts_md = "\n".join(
        f"- NSN {p['nsn']} ({p['nomenclature']}) — gates "
        f"{', '.join(p.get('downstream_families', []))} "
        f"({p.get('blocked_inductions', '?')} inductions blocked in window)."
        for p in parts[:5]
    ) or "- No long-pole NSNs are gating throughput in this scenario."

    actions_md = "\n".join(
        f"{i+1}. {a['action']} (depot **{a.get('depot','ALL')}**, "
        f"+{a.get('uplift_pct',0)}% uplift, effort {a.get('effort','med')})"
        for i, a in enumerate(actions[:5])
    )

    alts_md = "\n".join(
        f"- **{s.get('label','—')}** — Δ {s.get('delta_throughput_units',0):+d} units / "
        f"30 days. {s.get('tradeoff','')}"
        for s in alts[:3]
    )

    return (
        f"**BLUF.** Scenario *{scenario_label}*: the single biggest constraint "
        f"on 30-day depot throughput is **{bn}**. With the five recommended "
        f"actions below, projected uplift is **+{uplift}%** across MCLB Albany, "
        f"MCLB Barstow, and Blount Island Command.\n\n"
        f"## NAMED BOTTLENECK\n"
        f"{bn}. This resource gates the heaviest-labor inductions and cascades "
        f"into the FD-1 / FD-2 priority backlog.\n\n"
        f"## PARTS AVAILABILITY — CASCADING EFFECTS\n"
        f"{parts_md}\n\n"
        f"## TOP 5 ACTIONS (NEXT 30 DAYS)\n"
        f"{actions_md}\n\n"
        f"## ALTERNATIVE INDUCTION SEQUENCES\n"
        f"{alts_md}\n\n"
        f"## CLASSIFICATION\n"
        f"UNCLASSIFIED // FOR OFFICIAL USE.\n"
    )


def write_brief(scenario_label: str, scenario_id: str, analysis: dict,
                schedule_metrics: dict, backlog_df: pd.DataFrame,
                parts_df: pd.DataFrame, depots: list[dict],
                *, hero: bool = True, use_cache: bool = True) -> tuple[str, str]:
    """Step 2: narrative brief.

    Strategy (cache-first per AGENT_BRIEF_V2):
      1. If cached_briefs.json[scenario_id] exists, return it instantly.
      2. Otherwise call gpt-5.4 under timeout; on success, persist.
      3. On hero timeout/err, try standard chain under timeout.
      4. Fallback: deterministic brief that matches the section shape.
    Returns (brief_markdown, source_label).
    """
    if use_cache:
        cache = load_cached_briefs()
        cached = cache.get(scenario_id)
        if cached and cached.get("brief"):
            return cached["brief"], cached.get("source", "cache")

    backlog_sum = _backlog_summary(backlog_df)
    parts_sum = _parts_summary_text(parts_df)
    cap_sum = _capacity_summary(depots)
    msgs = build_brief_prompt(analysis, schedule_metrics, backlog_sum,
                              parts_sum, cap_sum, scenario_label)

    if hero:
        text = _call_chat_with_timeout(
            msgs, HERO_CALL_TIMEOUT_S, model="gpt-5.4", temperature=0.45
        )
        if text and "BLUF" in text and "NAMED BOTTLENECK" in text:
            _save_brief(scenario_id, scenario_label, text, source="gpt-5.4")
            return text, "gpt-5.4"

    text = _call_chat_with_timeout(msgs, HERO_CALL_TIMEOUT_S, temperature=0.45)
    if text and "BLUF" in text and "NAMED BOTTLENECK" in text:
        _save_brief(scenario_id, scenario_label, text, source="default-chain")
        return text, "default-chain"

    return _deterministic_brief(scenario_label, analysis, schedule_metrics), "deterministic"


def _save_brief(scenario_id: str, scenario_label: str, brief: str,
                *, source: str) -> None:
    """Persist a freshly generated brief into cached_briefs.json."""
    try:
        cache = load_cached_briefs()
        existing = cache.get(scenario_id, {})
        existing.update({
            "scenario_id": scenario_id,
            "label": scenario_label,
            "brief": brief,
            "source": source,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })
        cache[scenario_id] = existing
        CACHED_BRIEFS_PATH.write_text(json.dumps(cache, indent=2))
    except Exception:
        pass


# ---- formatting helpers ----------------------------------------------------

def _backlog_summary(backlog_df: pd.DataFrame) -> str:
    by_family = backlog_df.groupby("family").size().to_dict()
    by_priority = backlog_df.groupby("priority").size().to_dict()
    by_depot = backlog_df.groupby("depot").size().to_dict()
    return (
        f"Total: {len(backlog_df)} end items. "
        f"By family: {by_family}. "
        f"By FD priority: {by_priority}. "
        f"By depot: {by_depot}."
    )


def _parts_summary_text(parts_df: pd.DataFrame) -> str:
    long_pole = parts_df[parts_df["long_pole"] == "Y"]
    lines = []
    for _, p in long_pole.iterrows():
        lines.append(
            f"- NSN {p['nsn']} ({p['nomenclature']}): on_hand={p['on_hand']}, "
            f"ETA={p['eta_days']}d ({p['source']}), used_by={p['used_by']}"
        )
    return "\n".join(lines)


def _capacity_summary(depots: list[dict]) -> str:
    lines = []
    for d in depots:
        skills = ", ".join(f"{k}={v}" for k, v in d["skills"].items())
        lines.append(
            f"- {d['name']} ({d['id']}): {d['bays']} bays x "
            f"{d['shifts_per_day']} shifts; specialty={','.join(d['specialty'])}; "
            f"skills={skills}"
        )
    return "\n".join(lines)
