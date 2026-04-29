"""CONTESTED-LOG agent loop — OpenAI tool-calling.

Multi-turn `chat.completions` loop. The model fires up to 6 typed tools end-to-end:
  route_conus -> check_port_capacity -> forecast_pirate_risk
  -> check_supply_chain_disruption -> compute_last_mile -> compare_options

Watchdog + deterministic fallback so the UI never sits frozen on a hung LLM.
"""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path
from typing import Iterator

# Repo root for shared imports
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import get_client, PRIMARY_MODEL, FALLBACKS  # noqa: E402

from .tools import TOOL_REGISTRY, TOOL_SCHEMAS  # noqa: E402


SYSTEM_PROMPT = """You are CONTESTED-LOG, a USMC LOGCOM contested-logistics
sustainment planning agent for end-to-end CONUS-to-squad movement in a
contested INDOPACOM AOR (Force Design 2030 frame).

The operator types a natural-language sustainment request. You MUST call
the tools in this approximate order to deliver a Contested Sustainment
COA Brief:

  1. route_conus(origin, poe)               — CONUS rail/road/water leg
  2. check_port_capacity(poe_port)          — POE staging + berth
  3. forecast_pirate_risk(from, to)         — KDE risk overlay on sealift
  4. check_supply_chain_disruption(corridor)— 60-day disruption feed
  5. compute_last_mile(forward_port)        — squad-level push
  6. compare_options(origin, deadline)      — rank 3 end-to-end COAs

Then synthesize a "Contested Sustainment COA Brief" with:
  - BLUF (1 line: recommended COA + total days + risk verdict)
  - Full route narrative (named bottlenecks, risk windows, alt routes)
  - Days-of-supply impact (200 MRE pallets ≈ 6 lb/Marine/day → days for the
    31st MEU(SOC), cross-checked against MEU doctrine).
  - 2-line risk windows table
  - Final recommendation

Use named entities: MCLB Albany, BNSF, Port of Beaumont SDDC SPOE, T-AKE
Lewis-class, Apra Harbor, Itbayat, 31st MEU(SOC), Bab-el-Mandeb, Strait
of Malacca, Luzon Strait. Be terse, operationally credible. Cite numbers
with units (pallets, days, lb, nm). Do NOT restate raw JSON."""


def _hero_model() -> str:
    return os.getenv("OPENAI_HERO_MODEL", "gpt-5.4")


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


def stream_run(user_msg: str, *, max_turns: int = 8, hero: bool = True
               ) -> Iterator[dict]:
    """Yield events as the agent reasons:
        {"type": "user",          "content": str}
        {"type": "model_message", "content": str}
        {"type": "tool_call",     "id":..., "name":..., "arguments": dict}
        {"type": "tool_result",   "id":..., "name":..., "result": dict, "ms": int}
        {"type": "final",         "content": str}
    """
    client = get_client()
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    yield {"type": "user", "content": user_msg}

    for turn in range(max_turns):
        def _call(model: str):
            return client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.3,
            )

        timeout_s = 35 if (hero and turn == 0) else 20
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(lambda: _try_models(_call, hero=hero and turn == 0))
                resp = fut.result(timeout=timeout_s)
        except (FutTimeout, RuntimeError) as e:
            yield {"type": "model_message",
                   "content": f"(LLM timeout/error: {type(e).__name__} — falling back)"}
            yield {"type": "final", "content": _deterministic_brief()}
            return

        choice = resp.choices[0]
        msg = choice.message
        finish = choice.finish_reason

        if msg.content:
            yield {"type": "model_message", "content": msg.content}

        assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_entry["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name,
                              "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]
        messages.append(assistant_entry)

        if finish == "tool_calls" and msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {"_raw": tc.function.arguments}
                yield {"type": "tool_call", "id": tc.id, "name": name,
                       "arguments": args}

                fn = TOOL_REGISTRY.get(name)
                t0 = time.time()
                if fn is None:
                    result = {"error": f"Unknown tool: {name}"}
                else:
                    try:
                        result = fn(**args)
                    except TypeError as e:
                        result = {"error": f"Bad args for {name}: {e}"}
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
           "content": "(Agent hit max turns — partial COA only.)"}


def run(user_msg: str) -> dict:
    trace, final = [], ""
    for ev in stream_run(user_msg):
        trace.append(ev)
        if ev["type"] == "final":
            final = ev["content"]
    return {"final": final, "trace": trace}


def _deterministic_brief() -> str:
    return (
        "**CONTESTED SUSTAINMENT COA BRIEF — INDOPACOM (deterministic fallback)**\n\n"
        "**BLUF:** COA-1 Albany→Beaumont→Pearl→Apra (Guam)→Itbayat. "
        "ETA D+13.5. Pirate-risk verdict: ACCEPTABLE (avoids Bab-el-Mandeb + Malacca).\n\n"
        "**Route narrative:**\n"
        "1. CONUS leg: BNSF 286k-class rail Albany→Beaumont (1,180 mi, 32 hr). "
        "Bridge clearance ≥220 in across all spans — PASS.\n"
        "2. POE staging: Beaumont SDDC SPOE — 14 berths, LCAC pad on B07. "
        "200 pallets clear in 18 hr.\n"
        "3. Strategic sealift: T-AKE Lewis-class via LANE-PAC-N + LANE-PAC-MID. "
        "KDE pirate-risk along corridor: 0.05 (Open Pacific). Bab-el-Mandeb "
        "(0.92) and Strait of Malacca (0.78) hotspots fully avoided.\n"
        "4. Forward port: Apra Harbor Guam — 5 berths, LCAC pad ✓.\n"
        "5. Last-mile: C-130J Andersen → Itbayat tactical air-drop. Bashi "
        "Channel weather window opens D+13.\n\n"
        "**Days-of-supply check:** 200 MRE pallets ≈ 14,400 MREs ≈ 21 days "
        "of subsistence for 31st MEU(SOC) (~2,200 personnel). Covers the "
        "14-day combat sustainment window with a 7-day reserve.\n\n"
        "**Risk windows:** Luzon Strait NOTAM (PRC live-fire) D+10–D+12 — "
        "shift sealift arrival to D+13. Bab-el-Mandeb closed (assumed).\n\n"
        "**Alt routes:** (a) Charleston→Panama→LAX→Guam (D+18.5); "
        "(b) Tacoma→Yokosuka→Okinawa→Itbayat (D+15.5).\n\n"
        "**RECOMMEND:** EXECUTE COA-1."
    )


if __name__ == "__main__":
    out = run(
        "Push 200 pallets of MREs from MCLB Albany to 31st MEU at Itbayat "
        "by D+14, contested INDOPACOM, lowest pirate-risk."
    )
    print("=" * 72)
    for ev in out["trace"]:
        print(ev["type"], "->", json.dumps(ev, default=str)[:300])
    print("=" * 72)
    print("FINAL:\n", out["final"])
