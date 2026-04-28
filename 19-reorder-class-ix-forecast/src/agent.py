# REORDER — Class IX (repair parts) demand forecasting for deployed MAGTF
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""REORDER agent — two-step LLM pipeline.

Step 1 (chat_json):  per-NSN structured shortfall call with pre-positioning
                     recommendation, GREEN/AMBER/RED, and substitution.
Step 2 (chat):       Class IX Sustainment Risk Brief — BLUF, top-5 RED NSNs,
                     contested-logistics implications, pre-positioning COAs.

Both calls are wrapped in concurrent.futures with a wall-clock timeout, and
both fall back to a deterministic baseline so the UI never sits frozen.

Cache-first: if data/cached_briefs.json holds a brief for the active scenario,
the app serves it instantly.
"""
from __future__ import annotations

import concurrent.futures
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]  # repo root: hackathonMDM/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHED_BRIEFS_PATH = DATA_DIR / "cached_briefs.json"

HERO_TIMEOUT_S = 35.0
MINI_TIMEOUT_S = 25.0


# ---------- Step 1: per-NSN structured shortfall call -----------------------

NSN_JUDGE_SYSTEM = """You are REORDER, a USMC Class IX (repair parts) sustainment
analyst supporting a deployed MAGTF in a contested-logistics fight.

You will receive (a) the operator scenario (MAGTF size, OPTEMPO, environment,
forward node), (b) a list of top-N NSNs with projected 30-day demand from a
Holt-Winters forecaster, and (c) the current on-hand stock for each NSN at the
forward node.

For EVERY NSN in the input list, return a JSON entry with the schema:
  {
    "nsn": "<NSN verbatim>",
    "part_name": "<short, operator-readable>",
    "platform_consuming": "MTVR | LAV | JLTV | M88A2 | HMMWV",
    "projected_30d_demand": <int>,
    "current_stock_at_forward_node": <int>,
    "shortfall_risk": "GREEN | AMBER | RED",
    "preposition_recommendation": "<1-line action: ship N units to <node> by D-30>",
    "alt_supplier_or_substitution": "<short fallback if primary supplier is denied>"
  }

Constraints:
  - Compute shortfall_risk from cover_ratio = stock / projected_demand:
      >= 1.5 -> GREEN, >= 0.75 -> AMBER, else RED.
  - preposition_recommendation must name a real CONUS depot (MCLB Pendleton /
    MCLB Albany / Blount Island Command) or the forward node itself.
  - alt_supplier_or_substitution should be one short, plausible action:
    a substitute NSN, an OEM alt-source, or a 3D-printable workaround when
    realistic.
  - Return a single JSON object: {"items": [ {...}, ... ]}.
"""


def _ensure_loop_safe_chat_json(msgs: list[dict], timeout: float,
                                schema_hint: str) -> dict | None:
    def _go():
        return chat_json(msgs, schema_hint=schema_hint, temperature=0.2)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_go).result(timeout=timeout)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def _ensure_loop_safe_chat(msgs: list[dict], timeout: float, **kw) -> str | None:
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: chat(msgs, **kw)).result(timeout=timeout)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def baseline_judge_one(nsn_meta: dict, projected_30d: float,
                      stock: int, forward_node_name: str) -> dict:
    """Deterministic per-NSN call when LLM is unavailable. Same schema as LLM."""
    cover = stock / max(1.0, projected_30d)
    if cover >= 1.5:
        risk = "GREEN"
        rec = (f"Maintain current posture: {stock} on hand at {forward_node_name} "
               f"covers projected 30-day demand.")
    elif cover >= 0.75:
        risk = "AMBER"
        gap = max(1, int(projected_30d - stock))
        rec = (f"Ship {gap} units of {nsn_meta['nsn']} from MCLB Albany to "
               f"{forward_node_name} by D-30.")
    else:
        risk = "RED"
        gap = max(1, int(projected_30d * 1.5 - stock))
        rec = (f"PRIORITY: airlift {gap} units of {nsn_meta['nsn']} from MCLB "
               f"Pendleton to {forward_node_name} by D-15 — projected demand "
               f"exceeds 30-day cover.")
    alt = (f"Substitute via OEM alt-source through Blount Island Command or "
           f"3D-print fixture if subsystem is {nsn_meta['subsystem']}.")
    return {
        "nsn": nsn_meta["nsn"],
        "part_name": nsn_meta["part_name"],
        "platform_consuming": nsn_meta["primary_platform"],
        "projected_30d_demand": int(round(projected_30d)),
        "current_stock_at_forward_node": int(stock),
        "shortfall_risk": risk,
        "preposition_recommendation": rec,
        "alt_supplier_or_substitution": alt,
    }


def judge_top_nsns(forecasts: dict, catalog_by_nsn: dict, forward_node: dict,
                   *, scenario: dict) -> list[dict]:
    """Step 1 — produce one structured-output JSON entry per NSN."""
    on_hand = forward_node.get("on_hand_by_nsn", {})
    items_input = []
    for nsn, fc in forecasts.items():
        meta = catalog_by_nsn.get(nsn, {"nsn": nsn, "part_name": nsn,
                                        "primary_platform": "?", "subsystem": "?"})
        items_input.append({
            "nsn": nsn,
            "part_name": meta["part_name"],
            "primary_platform": meta["primary_platform"],
            "subsystem": meta["subsystem"],
            "projected_30d_demand": int(round(fc["demand_30d"])),
            "current_stock_at_forward_node": int(on_hand.get(nsn, 0)),
        })

    user = (
        f"SCENARIO:\n  MAGTF: {scenario['magtf_size']}\n  OPTEMPO: {scenario['optempo']}\n"
        f"  Environment: {scenario['environment']}\n  Forward node: {forward_node['name']}\n\n"
        f"TOP-N NSNs (forecast input):\n{json.dumps(items_input, indent=2)}\n\n"
        "Return JSON: {\"items\":[{...one per NSN...}]}"
    )
    msgs = [
        {"role": "system", "content": NSN_JUDGE_SYSTEM},
        {"role": "user", "content": user},
    ]
    schema_hint = ('{"items":[{"nsn":str,"part_name":str,"platform_consuming":str,'
                   '"projected_30d_demand":int,"current_stock_at_forward_node":int,'
                   '"shortfall_risk":"GREEN|AMBER|RED",'
                   '"preposition_recommendation":str,"alt_supplier_or_substitution":str}]}')
    raw = _ensure_loop_safe_chat_json(msgs, MINI_TIMEOUT_S, schema_hint) or {}
    llm_items = raw.get("items") or raw.get("nsns") or []
    by_nsn = {it.get("nsn"): it for it in llm_items if isinstance(it, dict)}

    # Always start from baseline; overlay LLM result by nsn when present.
    out = []
    for nsn, fc in forecasts.items():
        meta = catalog_by_nsn.get(nsn, {"nsn": nsn, "part_name": nsn,
                                        "primary_platform": "?", "subsystem": "?"})
        base = baseline_judge_one(meta, fc["demand_30d"], on_hand.get(nsn, 0),
                                  forward_node["name"])
        llm = by_nsn.get(nsn)
        if llm:
            for k in ("part_name", "platform_consuming", "shortfall_risk",
                      "preposition_recommendation", "alt_supplier_or_substitution"):
                if llm.get(k):
                    base[k] = llm[k]
        out.append(base)
    return out


# ---------- Step 2: Class IX Sustainment Risk Brief --------------------------

BRIEF_SYSTEM = """You are REORDER, the Class IX (repair parts) sustainment
analyst supporting a deployed MAGTF in a contested-logistics fight.

Compose a polished one-page **Class IX Sustainment Risk Brief** in markdown
with these EXACT four section headers, in order:

  ## BLUF
  ## TOP 5 RED NSNs
  ## CONTESTED-LOGISTICS IMPLICATIONS
  ## PRE-POSITIONING COURSES OF ACTION

Constraints:
  - Open with one bold one-line headline ABOVE the section headers.
  - BLUF: one sentence stating how many NSNs are RED, the dominant platform
    consuming them, and the assessed risk to MAGTF mobility/lethality if
    resupply is denied for 30 days.
  - TOP 5 RED NSNs: bulleted list, one line each: NSN -> short part name ->
    projected 30d demand vs forward stock -> recommended pre-position action.
    If fewer than 5 are RED, fill with the highest-shortfall AMBER items.
  - CONTESTED-LOGISTICS IMPLICATIONS: 2-3 sentences naming the specific risk
    (narrow resupply window, contested SLOC/ALOC, single-source fragility).
    Reference the operator's environment (desert / jungle / maritime / cold)
    and OPTEMPO band.
  - PRE-POSITIONING COURSES OF ACTION: exactly THREE numbered COAs, each one
    sentence, naming a depot (MCLB Pendleton / Albany / Blount Island) and a
    forward node + a hard date offset (D-15, D-30, D-45).
  - Close with the line: "Originator: REORDER / G-4 Class IX cell.
    Classification: UNCLASSIFIED // FOR OFFICIAL USE."
  - Total length: under ~400 words. No invented unit names or personnel.
"""


def baseline_brief(judged: list[dict], scenario: dict, forward_node: dict) -> str:
    """Deterministic brief used when the LLM hero call times out and there is
    no cached brief on disk."""
    reds = [j for j in judged if j["shortfall_risk"] == "RED"]
    ambers = [j for j in judged if j["shortfall_risk"] == "AMBER"]
    top5 = (reds + ambers)[:5]
    dominant_plat = max(
        {j["platform_consuming"] for j in judged} or {"MTVR"},
        key=lambda p: sum(1 for j in judged if j["platform_consuming"] == p),
    )
    dtg = datetime.now(timezone.utc).strftime("%d%H%MZ %b %Y").upper()
    bullets = "\n".join(
        f"- **{j['nsn']}** — {j['part_name']} — projected 30d demand "
        f"{j['projected_30d_demand']} vs on-hand {j['current_stock_at_forward_node']} at "
        f"{forward_node['name']}. {j['preposition_recommendation']}"
        for j in top5
    ) or "- No RED/AMBER NSNs at current scenario settings."

    return (
        f"**REORDER CLASS IX SUSTAINMENT RISK BRIEF — DTG {dtg} — "
        f"{scenario['magtf_size']} / {scenario['optempo'].upper()} / "
        f"{scenario['environment'].upper()}**\n\n"
        f"## BLUF\n"
        f"{len(reds)} of {len(judged)} forecasted Class IX NSNs are RED — "
        f"projected 30-day demand exceeds forward-node cover. Dominant consuming "
        f"platform: {dominant_plat}. If resupply is denied for 30 days under the "
        f"assessed {scenario['environment']} OPTEMPO, MAGTF mobility and crew-served "
        f"weapons availability degrade non-linearly past D+15.\n\n"
        f"## TOP 5 RED NSNs\n{bullets}\n\n"
        f"## CONTESTED-LOGISTICS IMPLICATIONS\n"
        f"The {scenario['environment']} environment compounds {dominant_plat} subsystem "
        f"wear at the assessed {scenario['optempo']} OPTEMPO. Forward node "
        f"{forward_node['name']} sits inside the adversary's first-strike envelope; "
        f"sea LOC reconstitution exceeds the 30-day window for the listed RED NSNs. "
        f"Single-source OEM dependence on the top-3 RED parts is the dominant fragility.\n\n"
        f"## PRE-POSITIONING COURSES OF ACTION\n"
        f"1. By D-15: airlift the top-3 RED NSNs from MCLB Pendleton to "
        f"{forward_node['name']} via C-17 surge contract.\n"
        f"2. By D-30: pre-position the next five AMBER NSNs from MCLB Albany to "
        f"Blount Island Command for MPF afloat reconstitution.\n"
        f"3. By D-45: stand up an additive-manufacturing workaround for two "
        f"low-tolerance NSNs at the forward node, freeing 30% of airlift tonnage.\n\n"
        f"Originator: REORDER / G-4 Class IX cell. "
        f"Classification: UNCLASSIFIED // FOR OFFICIAL USE.\n"
    )


def write_brief(judged: list[dict], scenario: dict, forward_node: dict,
                *, hero: bool = True, use_cache: bool = True) -> str:
    """Step 2 — narrative Class IX Sustainment Risk Brief.

    Strategy (so the demo never hangs on a spinner):
      1. If a cached brief exists for the scenario, serve it instantly.
      2. Otherwise call the hero gpt-5.4 model under timeout.
      3. On hero timeout/err, try the standard chain under timeout.
      4. Last resort: deterministic baseline brief.
    """
    if use_cache and CACHED_BRIEFS_PATH.exists():
        try:
            cache = json.loads(CACHED_BRIEFS_PATH.read_text())
            entry = cache.get(scenario["id"])
            if entry and entry.get("brief"):
                return entry["brief"]
        except Exception:
            pass  # fall through to live call

    user = (
        f"SCENARIO: {scenario['label']}\n"
        f"FORWARD NODE: {forward_node['name']} ({forward_node['id']})\n"
        f"NARRATIVE HINT: {scenario.get('narrative_hint','')}\n\n"
        f"NSN JUDGEMENTS (top {len(judged)} by projected demand):\n"
        f"{json.dumps(judged, indent=2)}\n\n"
        "Compose the Class IX Sustainment Risk Brief now."
    )
    msgs = [
        {"role": "system", "content": BRIEF_SYSTEM},
        {"role": "user", "content": user},
    ]

    if hero:
        text = _ensure_loop_safe_chat(msgs, HERO_TIMEOUT_S,
                                      model="gpt-5.4", temperature=0.45)
        if text and "BLUF" in text:
            return text

    text = _ensure_loop_safe_chat(msgs, MINI_TIMEOUT_S, temperature=0.45)
    if text and "BLUF" in text:
        return text

    return baseline_brief(judged, scenario, forward_node)


def save_cached_brief(scenario_id: str, brief: str, source: str = "warm-cache") -> None:
    """Persist a brief into data/cached_briefs.json keyed by scenario id."""
    cache = {}
    if CACHED_BRIEFS_PATH.exists():
        try:
            cache = json.loads(CACHED_BRIEFS_PATH.read_text())
        except Exception:
            cache = {}
    cache[scenario_id] = {
        "brief": brief,
        "source": source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    CACHED_BRIEFS_PATH.write_text(json.dumps(cache, indent=2))
