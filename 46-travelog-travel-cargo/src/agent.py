"""TRAVELOG agent — combined PCS travel + cargo + last-mile planner.

This is a 3-pipeline merge in ONE agent:
  pipeline 1 — TRAVEL : DTS pre-fill (JTR-compliant per-diem, lodging, GTCC)
  pipeline 2 — CARGO  : TMR auto-submit (DTR 4500.9-R Part II) via tool-call
  pipeline 3 — LAST-MILE : LaDe-shape pickup → delivery on receiving install

Plus a deterministic cross-validator that asks: do the travel arrival window,
cargo RDD, and last-mile pickup ETA all line up?

Hero call: gpt-5.4, 35s wall-clock timeout, cache-first. Writes the
"Combined Travel + Cargo Action Plan" markdown brief.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, get_client, PRIMARY_MODEL, FALLBACKS  # noqa: E402

from .tools import (  # noqa: E402
    TOOL_REGISTRY,
    TOOL_SCHEMAS,
    compare_modes,
    cross_validate_plan,
    load_scenarios,
    plan_last_mile_push,
    prefill_dts_voucher,
    submit_tmr,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHED_BRIEFS_PATH = DATA_DIR / "cached_briefs.json"

HERO_TIMEOUT_S = 35.0
TOOL_AGENT_TIMEOUT_S = 35.0


# ─────────────────────────────────────────────────────────────────────────────
# Tier 0 — deterministic orchestration (always runs, never fails)
# ─────────────────────────────────────────────────────────────────────────────
def deterministic_plan(scenario_id: str) -> dict:
    """Run the 3-pipeline merge with no LLM. Always succeeds."""
    scenarios = {s["scenario_id"]: s for s in load_scenarios()}
    scn = scenarios[scenario_id]
    comparison = compare_modes(
        origin=scn["origin_id"],
        destination=scn["dest_id"],
        hhg_lbs=scn["hhg_lbs"],
        has_motor_pool_item=scn["has_motor_pool_item"],
        motor_pool_item=scn["motor_pool_item"],
        d_plus_days=scn["d_plus_days"],
    )
    rec = next((o for o in comparison.get("options", [])
                if o.get("recommended")), None)
    mode_key = rec["mode_key"] if rec else "drive_ship"
    voucher = prefill_dts_voucher(scenario_id, mode_key)
    tmr = submit_tmr(
        scenario_id, mode_key,
        cargo_lbs=int(scn["hhg_lbs"]) + (1500 if scn["has_motor_pool_item"] else 0),
        motor_pool_item=scn["motor_pool_item"],
        cargo_lead_hr=(rec["cargo_lead_hr"] if rec else None),
    )
    last_mile = plan_last_mile_push(scenario_id, tmr.get("tcn"))
    validation = cross_validate_plan(comparison, voucher, tmr, last_mile)
    return {
        "scenario": scn,
        "comparison": comparison,
        "voucher": voucher,
        "tmr": tmr,
        "last_mile": last_mile,
        "validation": validation,
        "recommended_mode_key": mode_key,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tier 1 — Tool-calling agent (LLM picks tools, executes via TOOL_REGISTRY)
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_TOOL_PROMPT = """You are TRAVELOG, a USMC PCS planner. The Marine
gives you ONE sentence describing a permanent change-of-station move that
includes household goods AND (sometimes) a motor-pool item they will escort.

You MUST drive the planning by calling tools, in this order:
  1. compare_modes       — get the 4-option comparison, find the recommended mode.
  2. prefill_dts_voucher — pre-fill the DTS authorization for that mode.
  3. submit_tmr          — auto-populate the cargo TMR for that mode.
  4. plan_last_mile_push — schedule the LaDe-shape last-mile delivery.
  5. cross_validate_plan — confirm the 3 sub-plans are consistent.

Then reply with a one-paragraph BLUF (no JSON dump) naming the recommended
mode, the doc number, the TCN, and the cross-validation verdict.

Use snake_case base ids (MCBLEJ, MCBPEN, MCBHAW, MCAS_IWA, MCBOKI, etc.)
when calling tools. Be terse, operationally credible. Cite JTR / DTR
authorities where relevant. Refer to yourself as 'TRAVELOG' or 'the agent'."""


def _try_models(call_fn, hero: bool):
    chain = [_hero_model(), PRIMARY_MODEL, *FALLBACKS] if hero else \
            [PRIMARY_MODEL, *FALLBACKS]
    seen = set()
    last_err = None
    for m in chain:
        if m in seen:
            continue
        seen.add(m)
        try:
            return call_fn(m)
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"All models failed: {last_err}")


def _hero_model() -> str:
    return os.getenv("OPENAI_HERO_MODEL", "gpt-5.4")


def stream_run(user_msg: str, *, max_turns: int = 8, hero: bool = True):
    """Yield events as the tool-calling agent reasons."""
    client = get_client()
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_TOOL_PROMPT},
        {"role": "user",   "content": user_msg},
    ]
    yield {"type": "user", "content": user_msg}

    import time
    for turn in range(max_turns):
        def _call(model: str):
            return client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.2,
            )
        try:
            resp = _try_models(_call, hero=hero and turn == 0)
        except Exception as e:
            yield {"type": "final",
                   "content": f"(agent error: {e}; falling back to deterministic plan)"}
            return
        choice = resp.choices[0]
        msg = choice.message
        finish = choice.finish_reason

        if msg.content:
            yield {"type": "model_message", "content": msg.content}

        entry: dict = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            entry["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name,
                              "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]
        messages.append(entry)

        if finish == "tool_calls" and msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {"_raw": tc.function.arguments}
                yield {"type": "tool_call", "id": tc.id, "name": name, "arguments": args}
                fn = TOOL_REGISTRY.get(name)
                t0 = time.time()
                if fn is None:
                    result = {"error": f"Unknown tool: {name}"}
                else:
                    try:
                        result = fn(**args)
                    except TypeError as e:
                        result = {"error": f"Bad arguments for {name}: {e}"}
                    except Exception as e:  # noqa: BLE001
                        result = {"error": f"{type(e).__name__}: {e}"}
                ms = int((time.time() - t0) * 1000)
                yield {"type": "tool_result", "id": tc.id, "name": name,
                       "result": result, "ms": ms}
                messages.append({
                    "role": "tool", "tool_call_id": tc.id, "name": name,
                    "content": json.dumps(result, default=str)[:18000],
                })
            continue
        yield {"type": "final", "content": msg.content or ""}
        return
    yield {"type": "final",
           "content": "(agent hit max turns — see trace)"}


# ─────────────────────────────────────────────────────────────────────────────
# Tier 2 — Hero brief (cache-first, deterministic fallback)
# ─────────────────────────────────────────────────────────────────────────────
HERO_BRIEF_SYSTEM = """You are TRAVELOG, a USMC PCS travel + cargo planner.
Compose a polished one-page COMBINED TRAVEL + CARGO ACTION PLAN in markdown
with EXACTLY these sections in order:

  # Combined Travel + Cargo Action Plan — {grade} {last}
  ## BLUF
  ## Recommended Mode
  ## Mode Comparison
  ## DTS Voucher Pre-Fill
  ## TMR Pre-Fill
  ## Validation

Constraints:
  - BLUF: state recommended mode, total cost, combined transit time, RDD.
  - Recommended Mode: cite JTR Ch 2 or Ch 3 + DoDFMR Vol 9 + DTR 4500.9-R as
    relevant. State why it beats the others in 2-3 sentences.
  - Mode Comparison: 4-row markdown table with cost, time, fuel, lead time.
  - DTS Voucher Pre-Fill: doc_number, dates, lodging+M&IE totals, mode-of-travel.
  - TMR Pre-Fill: TCN, asset class, RDD, validation status.
  - Validation: 2-3 short bullets confirming travel/cargo/arrival sync.
  - Length under 450 words. Plain markdown. No code fences. No emoji.
  - End with: 'CUI // PCS Travel + Cargo Movement Data'.
  - Do NOT name underlying AI models — refer to yourself as TRAVELOG."""


def load_cached_briefs() -> dict:
    if not CACHED_BRIEFS_PATH.exists():
        return {}
    try:
        return json.loads(CACHED_BRIEFS_PATH.read_text())
    except Exception:
        return {}


def _save_cached(brief_payload: dict) -> None:
    cache = load_cached_briefs()
    cache[brief_payload["scenario_id"]] = brief_payload
    try:
        CACHED_BRIEFS_PATH.write_text(json.dumps(cache, indent=2))
    except Exception:
        pass


def _hero_user_prompt(plan: dict) -> str:
    scn = plan["scenario"]
    comp = plan["comparison"]
    voucher = plan["voucher"]
    tmr = plan["tmr"]
    lm = plan["last_mile"]
    val = plan["validation"]
    rec = next((o for o in comp.get("options", [])
                if o.get("recommended")), None)
    return (
        f"PCS scenario: {scn['scenario_id']}\n"
        f"Marine: {scn['traveler_grade']} {scn['traveler_name']}\n"
        f"Origin: {scn['origin_name']} ({scn['origin_id']})\n"
        f"Destination: {scn['dest_name']} ({scn['dest_id']})\n"
        f"D+{scn['d_plus_days']} | HHG {scn['hhg_lbs']} lbs | "
        f"Motor-pool item: {scn['motor_pool_item'] or 'none'}\n\n"
        f"Recommended mode: {rec['label'] if rec else '(none)'}\n"
        f"Total cost: ${rec['total_cost_usd'] if rec else 0:,.2f}\n"
        f"Combined transit (max of pax/cargo): {rec['combined_time_hr'] if rec else 0} hr\n\n"
        f"Mode comparison rows:\n" +
        "\n".join(
            f"  - {o['label']}: ${o['total_cost_usd']:,.2f} | "
            f"{o['combined_time_hr']}h combined | {o['fuel_gal']:.0f} gal fuel"
            for o in comp.get("options", [])) +
        f"\n\nVoucher: doc {voucher['doc_number']} | "
        f"{voucher['nights']} nights @ ${voucher['per_diem_lodging_ceiling_usd']}/night "
        f"({voucher['tdy_city']}) | total ${voucher['total_authorized_usd']:,.2f}\n"
        f"TMR: {tmr['tcn']} | asset {tmr['asset_class']} | RDD {tmr['rdd']} | "
        f"status {tmr['status']}\n"
        f"Last-mile: courier {lm['courier']} | "
        f"pickup {lm['eta_pickup'][:10]} → delivery {lm['eta_delivery'][:10]}\n"
        f"Cross-validation: {val['verdict']} | "
        f"issues={val['issues']} | notes={val['notes']}\n\n"
        f"Compose the action plan now."
    )


def _call_chat_with_timeout(msgs: list[dict], timeout_s: float, **kw) -> str | None:
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: chat(msgs, **kw)).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def _fallback_brief(plan: dict) -> str:
    scn = plan["scenario"]
    comp = plan["comparison"]
    voucher = plan["voucher"]
    tmr = plan["tmr"]
    lm = plan["last_mile"]
    val = plan["validation"]
    rec = next((o for o in comp.get("options", [])
                if o.get("recommended")), None)
    last = scn["traveler_name"].split(",")[0].strip()
    grade = scn["traveler_grade"]
    rec_label = rec["label"] if rec else "(no recommendation)"
    rec_cost = rec["total_cost_usd"] if rec else 0
    rec_time = rec["combined_time_hr"] if rec else 0

    rows = "\n".join(
        f"| {o['label']} | {o['combined_time_hr']:.0f}h | "
        f"${o['total_cost_usd']:,.0f} | ${o['fuel_cost_usd']:,.0f} | "
        f"${o['per_diem_usd']:,.0f} | {o['cargo_lead_hr']:.0f}h |"
        for o in comp.get("options", [])
    )
    issues_md = "\n".join(f"- {i}" for i in val.get("issues", [])) or "- (none)"
    notes_md = "\n".join(f"- {n}" for n in val.get("notes", [])) or "- (none)"
    return (
f"""# Combined Travel + Cargo Action Plan — {grade} {last}

## BLUF
TRAVELOG recommends **{rec_label}** at total estimated cost **${rec_cost:,.0f}**,
combined transit window **{rec_time:.0f}h**, RDD **{tmr['rdd']}**.
Pre-filled DTS authorization {voucher['doc_number']} and cargo TMR {tmr['tcn']}
are routed and ready for AO concurrence.

## Recommended Mode
{rec_label}. Per JTR Ch 2 / Ch 3 the per-diem at {voucher['tdy_city']} is
${voucher['per_diem_lodging_ceiling_usd']:.0f}/night lodging and
${voucher['per_diem_mie_usd']:.0f}/day M&IE; cargo movement is governed by
DTR 4500.9-R Part II. The agent ranked this option highest on the cost/time
weighted scoring and { 'the single-move escort eliminates one TMR hand-off' if scn['has_motor_pool_item'] and rec and rec.get('mode_key') == 'drive_escort' else 'the cost gap to the next-best option exceeded the value of the time saved'}.

## Mode Comparison
| Mode | Combined time | Total cost | Fuel | Per-diem | Cargo lead |
|---|---|---|---|---|---|
{rows}

## DTS Voucher Pre-Fill
- Doc number: {voucher['doc_number']} | TA: {voucher['ta_number']}
- Traveler: {voucher['traveler_grade']} {voucher['traveler_name']} (EDIPI {voucher['traveler_edipi']})
- Trip: {voucher['trip_start']} → {voucher['trip_end']} ({voucher['nights']} nights, {voucher['tdy_city']})
- Per-diem: ${voucher['lodging_total_usd']:,.0f} lodging + ${voucher['mie_total_usd']:,.0f} M&IE + ${voucher['incidentals_usd']:,.0f} incidentals = **${voucher['total_authorized_usd']:,.0f}**
- Mode of travel: {voucher['mode_of_travel']} | GTCC: {voucher['gtcc_authority']}
- Status: {voucher['status']}

## TMR Pre-Fill
- TCN: {tmr['tcn']} | Mode: {tmr['mode']} | Asset: {tmr['asset_class']}
- Origin: {tmr['origin_name']} → Dest: {tmr['dest_name']}
- Cargo: {tmr['cargo_lbs']:,} lbs{f" + {tmr['motor_pool_item']}" if tmr.get('motor_pool_item') else ''}
- RDD: {tmr['rdd']} | Status: {tmr['status']}
- Last-mile (LaDe-shape): courier {lm['courier']}, pickup {lm['eta_pickup'][:10]}, delivery {lm['eta_delivery'][:10]}

## Validation
- **Verdict: {val['verdict']}**
- Issues:
{issues_md}
- Notes:
{notes_md}

CUI // PCS Travel + Cargo Movement Data
""")


def generate_brief(scenario_id: str, *, use_cache: bool = True,
                   hero: bool = True) -> dict:
    """Cache-first hero brief generator."""
    cache = load_cached_briefs()
    if use_cache and scenario_id in cache and cache[scenario_id].get("brief"):
        return cache[scenario_id]

    plan = deterministic_plan(scenario_id)
    msgs = [
        {"role": "system", "content": HERO_BRIEF_SYSTEM},
        {"role": "user", "content": _hero_user_prompt(plan)},
    ]

    if hero:
        text = _call_chat_with_timeout(
            msgs, HERO_TIMEOUT_S,
            model="gpt-5.4", temperature=0.4,
        )
        if text and "BLUF" in text:
            payload = _persist(scenario_id, plan, text, "gpt-5.4")
            return payload

    text = _call_chat_with_timeout(msgs, HERO_TIMEOUT_S,
                                   temperature=0.4)
    if text and "BLUF" in text:
        return _persist(scenario_id, plan, text, "default-chain")

    return _persist(scenario_id, plan, _fallback_brief(plan),
                    "deterministic-fallback", persist=False)


def _persist(scenario_id: str, plan: dict, text: str, source: str,
             persist: bool = True) -> dict:
    scn = plan["scenario"]
    payload = {
        "scenario_id": scenario_id,
        "origin": scn["origin_name"],
        "dest": scn["dest_name"],
        "traveler": scn["traveler_name"],
        "traveler_grade": scn["traveler_grade"],
        "brief": text,
        "source": source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if persist:
        _save_cached(payload)
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# CLI smoke test
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[TRAVELOG] deterministic smoke test (no LLM calls)")
    plan = deterministic_plan("PCS-002")
    print(f"  scenario  : {plan['scenario']['scenario_id']} "
          f"({plan['scenario']['origin_id']} -> {plan['scenario']['dest_id']})")
    print(f"  rec mode  : {plan['recommended_mode_key']}")
    print(f"  options   : {len(plan['comparison']['options'])}")
    print(f"  voucher   : {plan['voucher']['doc_number']} "
          f"${plan['voucher']['total_authorized_usd']:,.2f}")
    print(f"  tmr       : {plan['tmr']['tcn']} {plan['tmr']['status']}")
    print(f"  last_mile : {plan['last_mile']['parcel_id']}")
    print(f"  validation: {plan['validation']['verdict']}")
