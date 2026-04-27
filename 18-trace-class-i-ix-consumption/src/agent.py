"""TRACE agent — agentic two-step LLM pipeline.

  Step 1 (chat_json):  Class I-IX consumption estimate as structured JSON
                       with daily + window totals + variance + sourcing.
  Step 2 (chat):       1-page Sustainment Estimate Brief (OPORD-shaped) with
                       risk callouts and contingency sourcing options.

Cache-first: the Streamlit app reads pre-computed briefs from
data/cached_briefs.json; the live call only fires when the user clicks
"Regenerate". Both calls are wrapped in a wall-clock timeout so the demo
never hangs on a stuck spinner — on timeout we fall back to the
deterministic baseline produced by data/generate.py.
"""
from __future__ import annotations

import concurrent.futures
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make `shared` and the local `data` module importable from anywhere.
APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import chat, chat_json  # noqa: E402
from data.generate import (  # noqa: E402
    DEPOTS,
    DOCTRINE_RATES,
    SCENARIOS,
    baseline_brief,
    baseline_estimate,
)


DATA_DIR = APP_ROOT / "data"
CACHED_BRIEFS_PATH = DATA_DIR / "cached_briefs.json"

# Wall-clock timeouts (seconds). gpt-5.4 occasionally hangs >90s; we cap so
# the 90s demo window is never blocked.
ESTIMATE_CALL_TIMEOUT_S = 25.0
HERO_CALL_TIMEOUT_S = 35.0


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def load_cached_briefs() -> dict:
    if not CACHED_BRIEFS_PATH.exists():
        return {}
    try:
        return json.loads(CACHED_BRIEFS_PATH.read_text())
    except Exception:
        return {}


def save_cached_brief(scenario_id: str, payload: dict) -> None:
    cache = load_cached_briefs()
    cache[scenario_id] = payload
    try:
        CACHED_BRIEFS_PATH.write_text(json.dumps(cache, indent=2))
    except Exception:
        pass


def list_scenarios() -> list[dict]:
    return list(SCENARIOS)


def list_depots() -> list[dict]:
    return list(DEPOTS)


# ---------------------------------------------------------------------------
# Step 1 — structured JSON consumption estimate (chat_json)
# ---------------------------------------------------------------------------
ESTIMATE_SYSTEM = """You are TRACE, the LogTRACE consumption-rate estimator for the
United States Marine Corps' Logistics Command (LOGCOM).

Given (a) a unit composition (unit type, personnel, days, opscale, climate) and
(b) a synthetic stand-in for MCWP 4-11 / MCRP 3-40D consumption planning rates,
produce a structured JSON estimate of Class I through IX requirements.

For EACH of the nine supply classes, return:
  - "class":                  one of "I","II","III","IV","V","VI","VII","VIII","IX"
  - "name":                   the class long-name (e.g. "Subsistence (MREs / UGRs)")
  - "daily_consumption":      number, daily total for the entire unit
  - "daily_unit":             unit string (e.g. "lbs/day", "gal/day", "ea/day")
  - "total_30day_or_window":  number, total over the requested operation window
  - "total_unit":             unit string for the total (e.g. "lbs", "gal", "ea")
  - "variance_band_pct":      integer, +/- planning variance percentage
  - "rate_basis":             short string citing the per-Marine planning rate
                              you used (e.g. "5.4 lbs/Marine/day")

For EACH class, also recommend pre-positioning sources from the supplied
synthetic GCSS-MC depot list — choose the top 3 depots by on-hand inventory
that can plausibly cover the requirement; report depot_id, name, on_hand,
unit, and the percentage of the total window requirement they cover.

Return a single JSON object exactly matching this shape:
{
  "scenario_id": str,
  "scenario_label": str,
  "personnel": int,
  "days": int,
  "climate": str,
  "opscale": str,
  "classes":   [ {class,name,daily_consumption,daily_unit,total_30day_or_window,total_unit,variance_band_pct,rate_basis}, ...9 entries... ],
  "sourcing": [ {class, sources:[{depot_id,name,on_hand,unit,covers_pct}, ...up to 3...]}, ...9 entries... ]
}

Be calibrated. Class III variance trends higher in hot climates and high opscale.
Class V variance is highest under high-tempo. Class VII is per-end-item (ea), not lbs.
"""


def _build_estimate_prompt(scenario: dict) -> list[dict]:
    user = (
        "UNIT COMPOSITION:\n"
        + json.dumps({
            "scenario_id": scenario["id"],
            "scenario_label": scenario["label"],
            "unit_type": scenario["unit_type"],
            "personnel": scenario["personnel"],
            "days": scenario["days"],
            "climate": scenario["climate"],
            "opscale": scenario["opscale"],
            "supply_basis": scenario["supply_basis"],
        }, indent=2)
        + "\n\nDOCTRINE RATES (synthetic stand-in for MCWP 4-11 / MCRP 3-40D):\n"
        + json.dumps({
            "rate_units": DOCTRINE_RATES["rate_units"],
            "class_names": DOCTRINE_RATES["class_names"],
            "rates_for_this_basis": DOCTRINE_RATES["rates"][scenario["supply_basis"]][scenario["opscale"]],
        }, indent=2)
        + "\n\nSYNTHETIC GCSS-MC DEPOT INVENTORY:\n"
        + json.dumps([
            {"depot_id": d["depot_id"], "name": d["name"], "location": d["location"],
             "role": d["role"], "inventory": d["inventory"]}
            for d in DEPOTS
        ], indent=2)
        + "\n\nReturn the JSON object now."
    )
    return [
        {"role": "system", "content": ESTIMATE_SYSTEM},
        {"role": "user", "content": user},
    ]


def _call_chat_json_with_timeout(msgs: list[dict], timeout_s: float) -> dict | None:
    def _go() -> dict:
        return chat_json(
            msgs,
            schema_hint='{"scenario_id":str,"classes":[...9...],"sourcing":[...9...]}',
            temperature=0.2,
        )
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_go).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def _merge_estimate(base: dict, llm: dict) -> dict:
    """Layer LLM result on baseline; baseline guarantees non-zero values."""
    out = dict(base)
    out["_source"] = "llm"
    by_id_llm = {c.get("class"): c for c in (llm.get("classes") or []) if isinstance(c, dict)}
    by_id_src = {s.get("class"): s for s in (llm.get("sourcing") or []) if isinstance(s, dict)}
    new_classes = []
    for c in base["classes"]:
        merged = dict(c)
        l = by_id_llm.get(c["class"])
        if l:
            for k in ("daily_consumption", "total_30day_or_window", "variance_band_pct"):
                if l.get(k) is not None:
                    try:
                        merged[k] = float(l[k]) if k != "variance_band_pct" else int(l[k])
                    except (TypeError, ValueError):
                        pass
            for k in ("name", "daily_unit", "total_unit", "rate_basis"):
                if l.get(k):
                    merged[k] = l[k]
        new_classes.append(merged)
    out["classes"] = new_classes
    new_sourcing = []
    for s in base["sourcing"]:
        ll = by_id_src.get(s["class"])
        if ll and ll.get("sources"):
            new_sourcing.append({"class": s["class"], "sources": ll["sources"][:3]})
        else:
            new_sourcing.append(s)
    out["sourcing"] = new_sourcing
    return out


def estimate_consumption(scenario: dict, *, hero: bool = True) -> dict:
    """Step 1: structured JSON consumption estimate.

    Always starts from the deterministic baseline (so the chart + table render
    instantly). Layers LLM JSON on top under a wall-clock timeout. Returns a
    dict with `_source` ∈ {baseline, llm}.
    """
    base = baseline_estimate(scenario)
    if not hero:
        return base
    msgs = _build_estimate_prompt(scenario)
    llm = _call_chat_json_with_timeout(msgs, ESTIMATE_CALL_TIMEOUT_S)
    if not llm:
        return base
    try:
        return _merge_estimate(base, llm)
    except Exception:
        return base


# ---------------------------------------------------------------------------
# Step 2 — narrator brief (chat)
# ---------------------------------------------------------------------------
BRIEF_SYSTEM = """You are TRACE, the LogTRACE narrator for the USMC Logistics
Command (LOGCOM) sustainment cell.

Compose a polished one-page **Sustainment Estimate Brief** in markdown with
these EXACT five paragraph headers, in order:

  ## PARA 1 — SITUATION
  ## PARA 2 — MISSION
  ## PARA 3 — CONSUMPTION ESTIMATE (Class I-IX)
  ## PARA 4 — RISKS & CONTINGENCY
  ## PARA 5 — SOURCES & SIGNAL

Constraints:
  - Open with a single bold one-line headline ABOVE the paragraphs.
  - PARA 1: cite unit type, personnel, days, climate, opscale verbatim from inputs.
  - PARA 2: 1-2 sentence mission statement framed for LOGCOM sustainment.
  - PARA 3: ONE bullet per supply class (I through IX). For each, name the
    total over the window with units and variance (±X%), and the primary
    pre-positioning source by depot name.
  - PARA 4: 3-5 bullets on the highest-variance / highest-risk classes
    (typically Class III POL, Class V ammunition, Class IX repair parts) and
    contingency sourcing options.
  - PARA 5: name the originator (TRACE / LOGCOM sustainment cell), next
    refresh time, and end with: "Classification: UNCLASSIFIED // FOR OFFICIAL USE".
  - Total length ≤ 500 words.
  - Do NOT invent specific units or personnel by name.
  - Do NOT name any specific underlying model or vendor.
"""


def _build_brief_prompt(scenario: dict, estimate: dict) -> list[dict]:
    classes_lines = []
    src_by_id = {s["class"]: s for s in estimate["sourcing"]}
    for c in estimate["classes"]:
        top = (src_by_id.get(c["class"]) or {}).get("sources", [{}])
        top0 = top[0] if top else {}
        classes_lines.append(
            f"- Class {c['class']} ({c['name']}): "
            f"daily {c['daily_consumption']:,} {c['daily_unit']}, "
            f"window {c['total_30day_or_window']:,} {c['total_unit']} "
            f"(±{c['variance_band_pct']}%); rate basis {c['rate_basis']}; "
            f"primary source {top0.get('name','—')} "
            f"({top0.get('on_hand', 0):,} {top0.get('unit','')} on hand)."
        )
    user = (
        f"DTG: {datetime.now(timezone.utc).strftime('%d%H%MZ %b %Y').upper()}\n\n"
        f"UNIT COMPOSITION:\n"
        f"  - Unit type: {scenario['unit_type']}\n"
        f"  - Personnel: {scenario['personnel']:,}\n"
        f"  - Window:    {scenario['days']} days\n"
        f"  - Climate:   {scenario['climate']}\n"
        f"  - Opscale:   {scenario['opscale']}\n"
        f"  - Basis:     {scenario['supply_basis']}\n\n"
        f"CONSUMPTION ESTIMATE (Class I-IX):\n"
        + "\n".join(classes_lines)
        + "\n\nCompose the Sustainment Estimate Brief now."
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


def write_brief(scenario: dict, estimate: dict, *, hero: bool = True) -> tuple[str, str]:
    """Step 2: narrative brief. Returns (brief_md, source_label)."""
    msgs = _build_brief_prompt(scenario, estimate)

    if hero:
        text = _call_chat_with_timeout(msgs, HERO_CALL_TIMEOUT_S, model="gpt-5.4",
                                       temperature=0.45)
        if text and "PARA 1" in text:
            return text, "hero"

    text = _call_chat_with_timeout(msgs, HERO_CALL_TIMEOUT_S, temperature=0.45)
    if text and "PARA 1" in text:
        return text, "default-chain"

    return baseline_brief(scenario, estimate), "baseline"


# ---------------------------------------------------------------------------
# One-shot pipeline
# ---------------------------------------------------------------------------
def run_hero_pipeline(scenario: dict, *, hero: bool = True,
                      use_cache: bool = True) -> dict[str, Any]:
    """Full Step 1 + Step 2 pipeline.

    If `use_cache` and a cached entry exists on disk for this scenario, return
    it instantly. Otherwise run the live pipeline, persist to cache, return.
    """
    if use_cache:
        cached = load_cached_briefs().get(scenario["id"])
        if cached and cached.get("brief") and cached.get("estimate"):
            return {
                "scenario": scenario,
                "estimate": cached["estimate"],
                "brief": cached["brief"],
                "source": cached.get("source", "cache"),
                "cached": True,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

    estimate = estimate_consumption(scenario, hero=hero)
    brief, brief_source = write_brief(scenario, estimate, hero=hero)
    out = {
        "scenario": scenario,
        "estimate": estimate,
        "brief": brief,
        "source": brief_source,
        "cached": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_cached_brief(scenario["id"], {
        "scenario": scenario,
        "estimate": estimate,
        "brief": brief,
        "source": brief_source,
    })
    return out


if __name__ == "__main__":
    sc = SCENARIOS[0]
    out = run_hero_pipeline(sc, hero=False, use_cache=False)
    print(json.dumps({k: v for k, v in out.items() if k != "brief"}, indent=2)[:1500])
    print("\n---\n")
    print(out["brief"])
