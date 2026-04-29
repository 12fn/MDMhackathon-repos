"""LLM agent: turn the deterministic 5-stage chain trace into a Closed-Loop
Maintenance Action Brief. Cache-first; live hero call has a 35s wall-clock
timeout with a deterministic fallback.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(REPO_ROOT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import chat  # noqa: E402

DATA = ROOT / "data"
CACHE_FILE = DATA / "cached_briefs.json"


SYSTEM_PROMPT = (
    "You are PREDICT-MAINT, a USMC Marine Corps Logistics Command "
    "(MARCORLOGCOM) closed-loop predictive-maintenance analyst. You write a "
    "*Closed-Loop Maintenance Action Brief* for an O-3 commander and an "
    "E-5 maintenance chief. Required structure (markdown):\n\n"
    "Open with **BLUF** (one bold paragraph, 2-3 sentences) naming the "
    "asset, the failure mode, the named bottleneck NSN, and the recommended "
    "commander action with action-due date.\n\n"
    "Then EXACTLY these sections, in order:\n"
    "  ## SENSOR-TO-SHELF CHAIN  (5 numbered stages)\n"
    "  ## NAMED BOTTLENECK\n"
    "  ## RECOMMENDED COMMANDER ACTION\n"
    "  ## CLASSIFICATION\n\n"
    "In SENSOR-TO-SHELF CHAIN: number 1-5 corresponding to "
    "Sensor / Forecast / Auto-reorder / Depot induction / Ledger. Cite "
    "specific NSN, depot codes (ALB / BAR / BIC), real platforms "
    "(MTVR / JLTV / LAV / AAV-7A1 / MV-22B), and the SHA-256 ledger hash "
    "prefix. Use real PMCS codes (B/D/A/W/M/Q/S/AN); do NOT invent codes.\n"
    "Close CLASSIFICATION with: UNCLASSIFIED // FOR OFFICIAL USE ONLY.\n\n"
    "Keep total output under ~480 words. Be specific and quantified."
)


def load_cached_briefs() -> dict[str, Any]:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text())
    except Exception:
        return {}


def get_cached_brief(scenario_id: str) -> dict | None:
    cache = load_cached_briefs()
    return cache.get(scenario_id)


def _chain_to_user_msg(asset: dict, chain_payload: dict) -> str:
    return (
        f"ASSET: {asset['asset_id']} ({asset['type']}) — {asset['unit']}\n"
        f"  hub: {asset['hub_position']}; op_hours: {asset['operating_hours']}\n"
        f"  classifier: {chain_payload['fault_class']} (RUL {chain_payload['rul_hours']} hr)\n\n"
        f"DEMAND FORECAST (30-day, NSN {asset['nsn']}):\n"
        f"  on hand at {chain_payload['source_depot']}: "
        f"{chain_payload['on_hand']} ea\n"
        f"  projected 30-day demand: "
        f"{chain_payload['projected_demand_30d']} ea\n"
        f"  shortfall: {chain_payload['shortfall']} ea\n"
        f"  recommended reorder: "
        f"{chain_payload['recommended_reorder_qty']} ea\n"
        f"  lead time: {chain_payload['lead_time_days']} days\n"
        f"  action due by: {chain_payload['action_due_by']}\n\n"
        f"DEPOT INDUCTION:\n"
        f"  reslotted at {chain_payload['induction_depot']}\n"
        f"  window: {chain_payload['induction_window']}\n\n"
        f"LEDGER ROW HASH: {chain_payload.get('hash', '')[:32]}...\n\n"
        f"Compose the Closed-Loop Maintenance Action Brief now."
    )


def generate_brief(*, asset: dict, chain_payload: dict, scenario_id: str | None = None,
                   use_cache: bool = True, hero_mode: bool = False,
                   timeout_s: float = 35.0) -> dict:
    """Cache-first: prefer the precomputed brief for the matched scenario.
    On `hero_mode=True` (or use_cache=False), call the hero model live with a
    wall-clock watchdog and fall back to a deterministic brief on any failure.
    """
    if use_cache and not hero_mode and scenario_id:
        cached = get_cached_brief(scenario_id)
        if cached and cached.get("brief"):
            return {
                "brief": cached["brief"],
                "source": "cache",
                "model_label": "Kamiwaza-deployed (cached)",
            }

    user_msg = _chain_to_user_msg(asset, chain_payload)
    msgs = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    model = "gpt-5.4" if hero_mode else None

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            text = ex.submit(
                lambda: chat(msgs, model=model, temperature=0.4)
            ).result(timeout=timeout_s)
        if text and "BLUF" in text:
            return {
                "brief": text,
                "source": "hero" if hero_mode else "live",
                "model_label": "Kamiwaza-deployed hero" if hero_mode
                else "Kamiwaza-deployed",
            }
    except (FutTimeout, Exception):
        pass

    # Deterministic fallback — always produces a brief
    return {
        "brief": _deterministic_brief(asset, chain_payload),
        "source": "fallback",
        "model_label": "deterministic fallback",
    }


def _deterministic_brief(asset: dict, ch: dict) -> str:
    """Same shape as the LLM output. Used when the LLM is unreachable."""
    return (
        f"**BLUF.** {asset['asset_id']} ({asset['type']}) shows a "
        f"**{ch['fault_class'].replace('_', ' ').upper()}** signature at the "
        f"{asset['hub_position'].lower()} hub. The 5-stage closed loop has "
        f"fired: sensor -> classifier -> 30-day forecast spike "
        f"({ch['projected_demand_30d']} ea projected vs trailing baseline) -> "
        f"GCSS-MC stock check ({ch['on_hand']} ea at {ch['source_depot']}) -> "
        f"depot induction reslot ({ch['induction_depot']} bay, "
        f"{ch['induction_window']}) -> ledger entry hash "
        f"`{ch.get('hash','')[:16]}...`. Recommended commander action: "
        f"reorder **{ch['recommended_reorder_qty']} ea NSN {asset['nsn']}** "
        f"by **{ch['action_due_by']}**.\n\n"
        f"## SENSOR-TO-SHELF CHAIN\n"
        f"1. **Sensor** — CWRU drive-end accelerometer trace (12 kHz, 1 s window). "
        f"Hand-crafted features fed into RandomForest; predicted "
        f"**{ch['fault_class']}**. RUL estimate: {ch['rul_hours']} operating hours.\n"
        f"2. **Forecast** — Holt-Winters projection on NSN {asset['nsn']} jumps "
        f"to **{ch['projected_demand_30d']} ea** over the next 30 days, RUL-shocked "
        f"by the {asset['type'].split()[0]} fleet feedback loop.\n"
        f"3. **Auto-reorder** — Validation against GCSS-MC stock + ICM ledger: "
        f"{ch['on_hand']} ea on hand at {ch['source_depot']}, shortfall "
        f"**{ch['shortfall']} ea**. Recommended reorder qty: "
        f"**{ch['recommended_reorder_qty']} ea**, action due by "
        f"**{ch['action_due_by']}** (lead time {ch['lead_time_days']} d).\n"
        f"4. **Depot induction** — Greedy scheduler reslots `{asset['asset_id']}` "
        f"at **{ch['induction_depot']}**, window **{ch['induction_window']}** "
        f"(rebuild-not-buy enforced).\n"
        f"5. **Ledger** — Append-only audit row written to "
        f"`data/ledger.jsonl`. SHA-256 chain hash "
        f"`{ch.get('hash','')[:32]}...` — tampering detectable on next read.\n\n"
        f"## NAMED BOTTLENECK\n"
        f"NSN {asset['nsn']} ({asset['part_name']}) — {ch['on_hand']} ea on hand "
        f"at {ch['source_depot']}; {ch['lead_time_days']} d lead time from DLA Land. "
        f"This is the rate-limiter on closing the loop within the 30-day window.\n\n"
        f"## RECOMMENDED COMMANDER ACTION\n"
        f"Order **{ch['recommended_reorder_qty']} ea NSN {asset['nsn']}** for "
        f"delivery to {ch['source_depot']} not-later-than **{ch['action_due_by']}**. "
        f"Confirm depot induction window **{ch['induction_window']}** at "
        f"{ch['induction_depot']}. Notify maintenance chief; sign brief into "
        f"the SHA-256 ledger.\n\n"
        f"## CLASSIFICATION\n"
        f"UNCLASSIFIED // FOR OFFICIAL USE ONLY."
    )
