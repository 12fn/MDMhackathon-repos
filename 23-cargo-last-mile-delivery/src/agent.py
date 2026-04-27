"""CARGO agent loop — OpenAI tool-calling for last-mile delivery.

Multi-turn `chat.completions` loop. On each iteration the model either:
  - emits tool_calls → we execute them locally and append results, or
  - returns a final assistant message → we yield it and stop.

`stream_run()` yields events so the Streamlit sidebar can render the
reasoning trace as it happens.
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


SYSTEM_PROMPT = """You are CARGO, an expeditionary last-mile delivery
optimizer for a Marine forward depot pushing supplies to dispersed
squad-level positions across roughly 30 km of austere terrain in 48 hours.

The operator types a natural-language push request; you MUST call the tools
to plan, deconflict threats, and present a defensible recommendation.

Always follow this sequence:
  1. Call `list_squad_positions` to scope which squads need resupply
     (filter by priority, terrain, or callsign as the request warrants).
  2. Call `compute_route` for AT LEAST ONE candidate vehicle/stops combo.
  3. Call `check_threat_overlay` against that route to surface UAS / sniper
     / IED-cleared zones the convoy would cross.
  4. Call `compare_options` (with empty `plans` or your own list) to rank
     a 3-option comparison against the operator's objective.
  5. Reply with a concise "Last-Mile Push Brief": convoy composition,
     timing, threat windows, risk mitigation, and the recommended option.
     Do NOT restate raw JSON — synthesize.

Use squad callsigns (alpha..hotel), depot id FOB-RAVEN, vehicle classes
(MTVR / JLTV / ARV / UGV). Be terse, operationally credible, cite numbers
with units (km, hr, gal, lb)."""


def _hero_model() -> str:
    """Use the hero model for the first call when available."""
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


def stream_run(user_msg: str, *, max_turns: int = 6, hero: bool = True
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
        {"role": "user",   "content": user_msg},
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

        # Wall-clock watchdog — fall back to baseline on timeout
        timeout_s = 35 if (hero and turn == 0) else 20
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(lambda: _try_models(_call, hero=hero and turn == 0))
                resp = fut.result(timeout=timeout_s)
        except (FutTimeout, RuntimeError) as e:
            yield {"type": "model_message",
                   "content": f"(LLM timeout/error: {type(e).__name__} — "
                              f"falling back to deterministic plan)"}
            yield {"type": "final", "content": _deterministic_brief(user_msg)}
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
           "content": "(Agent hit max turns without converging — see trace.)"}


def run(user_msg: str) -> dict:
    """Non-streaming convenience wrapper."""
    trace, final = [], ""
    for ev in stream_run(user_msg):
        trace.append(ev)
        if ev["type"] == "final":
            final = ev["content"]
    return {"final": final, "trace": trace}


def _deterministic_brief(user_msg: str) -> str:
    """Hand-written fallback when the LLM is unreachable."""
    return (
        "**LAST-MILE PUSH BRIEF — CARGO (deterministic fallback)**\n\n"
        "Recommended convoy: 2x MTVR (bulk Class I/V) escorted by 1x JLTV "
        "(armored overwatch). Detach 2x UGV-07 for the last-tactical-mile "
        "push to Delta and Echo (broken/wadi terrain).\n\n"
        "Timing: depart FOB Raven 0330L. Use Route IRON (IED-cleared corridor, "
        "TZ-03) for the southern leg (Foxtrot, Golf, Hotel). Hold the Charlie "
        "delivery until after 0800L to clear the UAS observation window over TZ-01.\n\n"
        "Mitigations: unmanned UGV push to highest-exposure positions; armored "
        "JLTV escort across TZ-02 sniper sector at >75 km/h with no halts.\n\n"
        "Estimate: full push complete in ~5.5 hr, ~38 gal fuel. All 8 squads "
        "resupplied inside the 48-hour window."
    )


if __name__ == "__main__":
    out = run(
        "Push 8,000 lb of Class I + 2,400 rounds Class V from FOB Raven to "
        "alpha through hotel squads by 0600 tomorrow, lowest threat exposure."
    )
    print("=" * 72)
    for ev in out["trace"]:
        print(ev["type"], "->", json.dumps(ev, default=str)[:300])
    print("=" * 72)
    print("FINAL:\n", out["final"])
