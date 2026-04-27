# VANGUARD — TMR automation with tool-calling agent loop
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""VANGUARD agent loop — OpenAI tool-calling.

Drives a chat.completions loop until finish_reason='stop'. On every iteration
we either:
  - Get a tool_call → execute it locally via TOOL_REGISTRY → append result.
  - Get the final assistant text → return.

`stream_run()` yields events in real time so the Streamlit sidebar can render
the reasoning trace as it happens.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Iterator

# Ensure repo root is importable for `shared.kamiwaza_client`
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import get_client, PRIMARY_MODEL, FALLBACKS  # noqa: E402

from .tools import TOOL_REGISTRY, TOOL_SCHEMAS  # noqa: E402


SYSTEM_PROMPT = """You are VANGUARD, a USMC LOGCOM transportation movement
request (TMR) routing agent for joint Air/Land/Sea sustainment in CENTCOM
theater. The operator types a natural-language move request; you must call
your tools to plan, verify, and present a 3-option comparison.

Always follow this sequence:
  1. Call `list_assets` to scope the inventory in theater.
  2. Call `compute_route` to pull at least one candidate route.
  3. Call `compare_options` to score 3 options against the operator's objective.
  4. Reply with a concise final answer: name the recommended option,
     cite hours, fuel cost, and key risk factors. Do NOT restate raw JSON.

Use base codes (ARIFJAN, ALUDEID, ERBIL, etc.) when calling tools. Be terse,
operationally credible, and cite numbers with units."""


def _hero_model() -> str:
    """Use gpt-5.4 (no -mini) for the hero call when available, else default chain."""
    return os.getenv("OPENAI_HERO_MODEL", "gpt-5.4")


def _try_models(call_fn, hero: bool):
    chain = [_hero_model(), PRIMARY_MODEL, *FALLBACKS] if hero else [PRIMARY_MODEL, *FALLBACKS]
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


def stream_run(user_msg: str, *, max_turns: int = 6, hero: bool = True) -> Iterator[dict]:
    """Yield events as the agent reasons:
      {"type": "model_message",  "content": str}
      {"type": "tool_call",      "id": str, "name": str, "arguments": dict}
      {"type": "tool_result",    "id": str, "name": str, "result": dict, "ms": int}
      {"type": "final",          "content": str}
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

        resp = _try_models(_call, hero=hero and turn == 0)
        choice = resp.choices[0]
        msg = choice.message
        finish = choice.finish_reason

        # Capture any interim text the model wrote alongside tool calls
        if msg.content:
            yield {"type": "model_message", "content": msg.content}

        # Append the assistant turn so the next iteration has the context
        assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_entry["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
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
                    "role": "tool", "tool_call_id": tc.id,
                    "name": name,
                    "content": json.dumps(result)[:18000],  # OpenAI ctx safety
                })
            continue  # next turn — let model see tool results

        # Either stop or no tool calls → final answer
        yield {"type": "final", "content": msg.content or ""}
        return

    yield {"type": "final",
           "content": "(Agent hit max turns without converging — see trace.)"}


def run(user_msg: str) -> dict:
    """Non-streaming convenience wrapper. Returns final + the full trace."""
    trace, final = [], ""
    for ev in stream_run(user_msg):
        trace.append(ev)
        if ev["type"] == "final":
            final = ev["content"]
    return {"final": final, "trace": trace}


if __name__ == "__main__":
    out = run("Move 40 pallets of MREs from Camp Arifjan to Erbil within 72 hours, "
              "lowest fuel burn.")
    print("=" * 72)
    for ev in out["trace"]:
        print(ev["type"], "->", json.dumps(ev, default=str)[:300])
    print("=" * 72)
    print("FINAL:\n", out["final"])
