"""STORM-SHIFT — Polycrisis Readiness Brief agent.

Hero call wraps the projection rollup in a prompt → narrative one-pager.
Cache-first: pre-computed briefs in data/cached_briefs.json render instantly.
Live regenerate uses gpt-5.4 with a 35s wall-clock watchdog and falls back to
a deterministic projection-shaped brief if the call hangs.
"""
from __future__ import annotations

import concurrent.futures
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from shared.kamiwaza_client import chat  # noqa: E402
from src import projections  # noqa: E402

DATA_DIR = APP_ROOT / "data"
CACHED_BRIEFS_PATH = DATA_DIR / "cached_briefs.json"

HERO_TIMEOUT_S = 35.0

SYSTEM = """You are STORM-SHIFT, the polycrisis readiness analyst supporting
USMC LOGCOM (MARFORCOM, MARFORPAC, and base-G4 staffs) for climate-driven
storm scenarios.

Compose a polished one-page **Polycrisis Readiness Brief** in markdown with
these EXACT section headers in order:

  ## BLUF
  ## Top 3 cascading effects
  ## Recommended pre-landfall actions
  ## Recommended post-landfall actions
  ## Dollar exposure summary
  ## Days-to-MC

Constraints:
  - Open with a single bold one-line headline ABOVE the sections.
  - BLUF: one paragraph naming the storm scenario, installation, total $ exposure,
    and days-to-MC.
  - Top 3 cascading effects: numbered list of 3 named cross-domain cascades
    (storm → flood → supply → inventory).
  - Pre-landfall: 3-5 bullets, each with a hard number (gallons, cases, miles).
  - Post-landfall: 3-5 bullets.
  - Dollar exposure summary: bullet each component with $ value, then TOTAL.
  - Days-to-MC: state the number, optionally a "with pre-positioning" range.
  - Close with: Originator: STORM-SHIFT polycrisis readiness cell. Classification line.
  - Total length: under 450 words. Do NOT invent unit names or personnel.
"""


def _build_prompt(rollup: dict) -> list[dict]:
    inst = projections.installation_by_id(rollup["installation_id"])
    scn = projections.scenario_by_id(rollup["scenario_id"])
    co = projections.scenario_by_id(rollup["co_scenario_id"]) if rollup.get("co_scenario_id") else None

    lines = [
        f"Installation: {inst['name']} ({inst['state']}) — {inst['personnel']:,} personnel",
        f"Notable history: {inst['notable_history']}",
        f"Scenario: {scn['label']} — {scn['narrative']}",
    ]
    if co:
        lines.append(f"Co-scenario (polycrisis): {co['label']} — {co['narrative']}")
    poly = rollup["polycrisis"]
    if poly["multiplier"] > 1.0:
        lines.append(f"Polycrisis multiplier: {poly['multiplier']}x — {poly['rationale']}")

    fl, su, inv, cons, fi, bi = (rollup["flood"], rollup["supply"], rollup["inventory"],
                                  rollup["consumption"], rollup["fire"], rollup["base_impact"])

    lines += [
        "",
        f"Projection 1 (flood damage): ${fl['total_usd']:,.0f}, {fl['nfip_claims_in_radius']} NFIP claims in 30-mi radius.",
        f"  Asset breakdown: {json.dumps({k: f'${v:,.0f}' for k,v in fl['asset_class_breakdown'].items()})}",
        f"Projection 2 (supply chain): {su['suppliers_affected']} suppliers, lead-time {su['lead_time_baseline_days']}d → {su['lead_time_disrupted_days']}d ({su['lead_time_surge_factor']}x), ${su['estimated_disruption_cost_usd']:,.0f}.",
        f"  Top categories: {[(c['category'], c['suppliers']) for c in su['top_affected_categories'][:3]]}",
        f"Projection 3 (inventory cascade): {inv['items_red']} RED items, {inv['items_amber']} AMBER, headcount in shelter {inv['headcount_in_shelter']:,}, {inv['shelter_days']}-day shelter.",
        f"  Critical reds: {[r['class'] for r in inv['rows'] if r['status']=='RED'][:5]}",
        f"Projection 4 (consumption surge): over {cons['shelter_days']} days, totals: " +
        ", ".join(f"{c['class']}: {c['total_over_shelter']:,}" for c in cons['classes'][:4]),
        f"Projection 5 (base impact): TOTAL ${bi['total_dollar_exposure_usd']:,.0f}, days-to-MC {bi['days_to_mission_capable']}.",
        f"Projection 6 (fire-secondary): score {fi['ignition_risk_score']}, {fi['firms_pixels_within_60mi']} FIRMS pixels, ${fi['estimated_damage_usd']:,.0f} potential, lag {fi['time_lag_days']}d.",
    ]

    user = "STORM-SHIFT projection rollup:\n" + "\n".join(lines) + "\n\nCompose the Polycrisis Readiness Brief now."
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
    ]


def _call_with_timeout(msgs: list[dict], timeout_s: float, **kw) -> str | None:
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: chat(msgs, **kw)).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def _fallback_brief(rollup: dict) -> str:
    inst = projections.installation_by_id(rollup["installation_id"])
    scn = projections.scenario_by_id(rollup["scenario_id"])
    bi = rollup["base_impact"]
    fl, su, inv, cons, fi = (rollup["flood"], rollup["supply"], rollup["inventory"],
                              rollup["consumption"], rollup["fire"])

    red_items = [r["class"] for r in inv["rows"] if r["status"] == "RED"][:3]
    red_str = ", ".join(red_items) if red_items else "no items in red"

    return (
        f"**STORM-SHIFT POLYCRISIS READINESS BRIEF — {inst['name'].upper()} / {scn['label'].upper()}**\n\n"
        f"## BLUF\n"
        f"A {scn['label']} on {inst['name']} ({inst['personnel']:,} personnel) projects "
        f"**${bi['total_dollar_exposure_usd']/1e9:.2f}B** total exposure, "
        f"days-to-MC **{bi['days_to_mission_capable']}**. {scn['narrative']}\n\n"
        f"## Top 3 cascading effects\n"
        f"1. **Flood envelope** — ${fl['total_usd']/1e6:,.0f}M projected damage, "
        f"{fl['nfip_claims_in_radius']} NFIP claims in 30-mi radius.\n"
        f"2. **Supplier collapse** — {su['suppliers_affected']} suppliers affected, lead-time "
        f"surge {su['lead_time_surge_factor']}x ({su['lead_time_baseline_days']}d → {su['lead_time_disrupted_days']}d).\n"
        f"3. **Inventory red cascade** — {inv['items_red']} class(es) go red within shelter window: {red_str}.\n\n"
        f"## Recommended pre-landfall actions\n"
        f"- Surge JP-8 to 95% storage capacity from nearest sister installation.\n"
        f"- Pre-position MRE cases ({cons['classes'][0]['total_over_shelter']:,.0f}-case shelter requirement).\n"
        f"- Relocate 30% of Class IX repair-parts inventory inland.\n"
        f"- Activate DSCA stand-by MOA for stevedore augmentation.\n\n"
        f"## Recommended post-landfall actions\n"
        f"- Air-bridge plasma resupply from nearest sister installation.\n"
        f"- Prioritize generator-diesel resupply.\n"
        f"- Engage alternate supplier corridor to bypass disrupted FEMA-SC events.\n\n"
        f"## Dollar exposure summary\n"
        f"- Flood damage: **${bi['components_usd']['flood_damage']/1e6:,.0f}M**\n"
        f"- Supply chain: **${bi['components_usd']['supply_chain']/1e6:,.0f}M**\n"
        f"- Inventory red premium: **${bi['components_usd']['inventory_red_premium']/1e6:,.0f}M**\n"
        f"- Fire-secondary: **${bi['components_usd']['fire_secondary']/1e6:,.0f}M**\n"
        f"- **TOTAL: ${bi['total_dollar_exposure_usd']/1e9:.2f}B**\n\n"
        f"## Days-to-MC: **{bi['days_to_mission_capable']} days** (with pre-positioning: ~{max(1.0, bi['days_to_mission_capable']*0.4):.1f} days)\n\n"
        f"Originator: STORM-SHIFT polycrisis readiness cell. Classification: UNCLASSIFIED // FOR OFFICIAL USE."
    )


def get_cached_brief_key(installation_id: str, scenario_id: str) -> str:
    return f"{scenario_id}_{installation_id}"


def get_brief(rollup: dict, *, hero: bool = True, force_live: bool = False) -> dict:
    """Cache-first + watchdog. Returns {brief, source}.

    Lookup order:
      1. cached_briefs.json — instant
      2. live hero call (gpt-5.4) under 35s timeout
      3. live default chain under 35s timeout
      4. deterministic fallback
    """
    inst_id = rollup["installation_id"]
    scn_id = rollup["scenario_id"]
    key = get_cached_brief_key(inst_id, scn_id)

    # 1. cache
    if not force_live and CACHED_BRIEFS_PATH.exists():
        try:
            cache = json.loads(CACHED_BRIEFS_PATH.read_text())
            if key in cache:
                return {"brief": cache[key], "source": "cached"}
        except Exception:
            pass

    msgs = _build_prompt(rollup)

    # 2. hero call
    if hero:
        text = _call_with_timeout(msgs, HERO_TIMEOUT_S, model="gpt-5.4", temperature=0.45)
        if text and "BLUF" in text:
            _persist_to_cache(key, text)
            return {"brief": text, "source": "hero-live"}

    # 3. mini chain
    text = _call_with_timeout(msgs, HERO_TIMEOUT_S, temperature=0.45)
    if text and "BLUF" in text:
        _persist_to_cache(key, text)
        return {"brief": text, "source": "default-chain"}

    # 4. deterministic fallback
    return {"brief": _fallback_brief(rollup), "source": "deterministic-fallback"}


def _persist_to_cache(key: str, brief: str) -> None:
    try:
        cache = {}
        if CACHED_BRIEFS_PATH.exists():
            cache = json.loads(CACHED_BRIEFS_PATH.read_text())
        cache[key] = brief
        CACHED_BRIEFS_PATH.write_text(json.dumps(cache, indent=2))
    except Exception:
        pass


if __name__ == "__main__":
    import sys
    inst_id = sys.argv[1] if len(sys.argv) > 1 else "lejeune"
    scn_id = sys.argv[2] if len(sys.argv) > 2 else "cat3"
    rollup = projections.run_all_projections(inst_id, scn_id)
    out = get_brief(rollup, hero=False)
    print(f"--- source: {out['source']} ---")
    print(out["brief"])
