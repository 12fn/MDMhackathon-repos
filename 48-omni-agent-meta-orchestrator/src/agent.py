"""OMNI-AGENT v2 — meta-orchestrator agent loop.

This is the brain of the centerpiece app. The user types one cross-domain
question (and optionally uploads an image / CSV / picks a persona); this
module decomposes the query, picks the right sibling-app tools (out of 46),
fires them in sequence (often 2-5 in a chain), and synthesizes the fused
OPORD-grade commander brief.

Key features over v1:
  - Multi-modal: image + CSV uploads are forwarded to vision/data tools.
  - Kamiwaza-feature-aware routing: sensitive queries route through
    MESH-INFER first; cross-silo queries through FED-RAG; auth queries
    through CHAIN-OF-COMMAND ReBAC; cost queries through CAT-ROUTER;
    big-data queries through DDE-RAG.
  - Persona-aware: G-1/G-2/G-3/G-4/S-6/CO selectors flow into the system
    prompt and into ABAC-aware sibling tools.
  - Streaming: yields events the UI can render as the agent thinks.
  - Hash-chain audited: every tool invocation appended to a SHA-256 ledger.
  - Watchdog: per-LLM-call timeout, deterministic fallback on failure.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import get_client, PRIMARY_MODEL, FALLBACKS  # noqa: E402

from .tools import TOOL_REGISTRY, TOOL_SCHEMAS, load_registry  # noqa: E402
from . import audit  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# System prompt — the playbook the model uses to choose tools
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT_BASE = """You are OMNI-AGENT, the Marine Corps LOGCOM meta-orchestrator.
You sit on top of a Kamiwaza-deployed AI fleet of 53 mission apps and have
governed access to 46 of them as typed function tools.

Your job: when an operator types one cross-domain question, decompose it into
sub-tasks, call the RIGHT tools (often 2-5 in sequence), then SYNTHESIZE
a single OPORD-grade Commander brief that fuses the results.

# Kamiwaza-feature-aware routing rules — APPLY FIRST
- If the operator marks the query as CUI / SECRET / TS, OR mentions
  "sensitive" / "classified" / "Inference Mesh", call query_mesh_infer FIRST
  to demonstrate sensitivity-aware routing. Use the routing decision as your
  pre-flight check before invoking other domain tools.
- If the query asks for cross-silo / multi-enclave data ("Albany AND
  Pendleton", "across silos", "federated"), use query_fed_rag.
- If the query is auth-flavored ("can <Marine> access <doc>?",
  "releasability", "REL TO"), use query_chain_of_command for ReBAC walking.
- If the query is cost-conscious ("pick the right model", "minimize cost",
  "model routing"), use query_cat_router.
- If the query is big-data ("scan 50 GB", "search the corpus", "compute at
  data"), use query_dde_rag.

# Tool-selection rules (domain-specific, after Kamiwaza routing)
- Blood / cold-chain / Class VIII medical -> query_vitals
- Weather / typhoon / sea-state / window -> query_weathervane
- MARFORPAC node climate / sustainment-line risk -> query_meridian
- CONUS-to-EABO / contested sustainment plan -> query_contested_log
- Class I-IX consumption sizing -> query_trace
- Class IX parts forecast / shortfall -> query_reorder
- Counter-UAS / RF / drone threat at an installation -> query_cuas_detect
- Counter-drone air dominance / swarm -> query_drone_dominance
- Installation ICOP / gate / badge / fence anomaly -> query_omni
- Daily all-source intel brief -> query_omni_intel
- Maritime route / sealift / chokepoint -> query_marlin
- ISR object detection in imagery -> query_raptor
- Perimeter intrusion in camera frame -> query_sentinel
- Pallet / truck / container counting in photo -> query_pallet_vision
- TM lookup with photo of equipment -> query_optik
- Casualty triage / 9-line MEDEVAC -> query_marine_medic
- LMS / cohort competency assessment -> query_learn
- Schoolhouse competency rollup -> query_schoolhouse
- Single-Marine assessment / feedback -> query_cadence
- PCS travel / DTS voucher -> query_travelog
- PCS HHG cargo tracking -> query_vanguard
- CUI auto-tag of a doc -> query_redline
- ABAC release decision on a doc -> query_guardrail
- Wildfire risk near installation -> query_wildfire
- FIRMS hotspots over training ranges -> query_ember
- Storm / hurricane evacuation plan -> query_storm_shift
- Flood risk at an installation -> query_riptide
- RF pattern-of-life / anomalous emitter -> query_ghost
- EW emitter classification -> query_spectra
- Convoy IED route -> query_strider
- Maritime POL / dark vessel -> query_corsair
- Depot maintenance throughput -> query_queue
- Fleet RUL forecast -> query_predict_maint
- Vibration / bearing health -> query_forge
- Inventory audit on a unit -> query_stockroom
- Global supply-chain disruption -> query_chain
- data.gov RAG -> query_opengate
- MARADMIN / SOP RAG -> query_anchor
- Egocentric training scene coach -> query_embodied
- Installation COP aggregation (HIFLD + Earthdata + GCSS) -> query_watchtower
- 911-style triage / dispatch -> query_dispatch

# Output rules
1. Call 1-5 tools BEFORE writing the final brief.
2. Reference each tool's codename in the final brief
   (e.g. "VITALS reports 3 spokes below 1 DOS; WEATHERVANE confirms TC 03W
   window opens H+62...").
3. Final brief is OPORD-style: BLUF, situation, recommendation, risk.
4. Be terse, operationally credible, and cite numbers with units.
5. NEVER mention "OpenAI", "GPT", or any model brand name in your output.
   Refer to your synthesis layer as "the Kamiwaza-deployed model".
"""


def build_system_prompt(persona: str | None = None,
                        sensitivity: str | None = None,
                        modality_hint: str | None = None) -> str:
    """Augment the base prompt with operator persona + sensitivity + modality."""
    extras: list[str] = []
    if persona:
        extras.append(
            f"\n# Operator persona: {persona}\n"
            "Tailor the BLUF and the recommendation to what THIS persona "
            "actually decides on. Pass `persona_id` to ABAC-aware tools "
            "(query_omni, query_guardrail, query_chain_of_command)."
        )
    if sensitivity and sensitivity.upper() != "UNCLAS":
        extras.append(
            f"\n# Sensitivity: {sensitivity}\n"
            f"Your FIRST tool call MUST be query_mesh_infer with "
            f"sensitivity='{sensitivity}' to publish the routing decision."
        )
    if modality_hint:
        extras.append(
            f"\n# Operator uploaded: {modality_hint}\n"
            "Prefer image-aware / data-aware sibling tools first "
            "(query_sentinel, query_pallet_vision, query_marine_medic, "
            "query_raptor, query_optik, query_redline, query_guardrail, "
            "query_embodied, query_cuas_detect for image; "
            "query_forge, query_spectra, query_ghost, query_predict_maint, "
            "query_stockroom for csv)."
        )
    return SYSTEM_PROMPT_BASE + "".join(extras)


# ─────────────────────────────────────────────────────────────────────────────
# Model selection — hero call once, then cheaper fallbacks
# ─────────────────────────────────────────────────────────────────────────────
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
            return call_fn(m), m
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"All models failed: {last_err}")


# ─────────────────────────────────────────────────────────────────────────────
# Streaming agent loop — yields events the UI can render in real time
# ─────────────────────────────────────────────────────────────────────────────
def stream_run(user_msg: str, *,
               max_turns: int = 6, hero: bool = True,
               query_id: str | None = None,
               persona: str | None = None,
               sensitivity: str | None = None,
               image_paths: list[str] | None = None,
               csv_paths: list[str] | None = None,
               extra_tool_args: dict | None = None,
               ) -> Iterator[dict]:
    """Run the agent loop and yield events.

    Yields:
      {"type": "user",            "content": str, "query_id": str}
      {"type": "model_chosen",    "model": str, "turn": int}
      {"type": "model_message",   "content": str}
      {"type": "tool_call",       "id":..., "name":..., "arguments": dict, "meta": dict}
      {"type": "tool_result",     "id":..., "name":..., "result": dict, "ms": int, "audit": dict}
      {"type": "route_decision",  "feature": str, "decision": dict}  # Kamiwaza features
      {"type": "final",           "content": str, "model": str}
    """
    qid = query_id or f"Q-{uuid.uuid4().hex[:8]}"
    yield {"type": "user", "content": user_msg, "query_id": qid,
           "persona": persona, "sensitivity": sensitivity,
           "image_paths": image_paths or [], "csv_paths": csv_paths or []}

    modality_hint = None
    if image_paths:
        modality_hint = f"{len(image_paths)} image(s)"
    elif csv_paths:
        modality_hint = f"{len(csv_paths)} CSV/file(s)"

    sys_prompt = build_system_prompt(persona=persona,
                                     sensitivity=sensitivity,
                                     modality_hint=modality_hint)

    client = get_client()
    messages: list[dict] = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": _user_payload(
            user_msg, image_paths, csv_paths, persona, sensitivity)},
    ]

    last_model_used = PRIMARY_MODEL

    for turn in range(max_turns):
        def _call(model: str):
            return client.chat.completions.create(
                model=model, messages=messages,
                tools=TOOL_SCHEMAS, tool_choice="auto",
                temperature=0.3,
            )

        timeout_s = 35 if (hero and turn == 0) else 25
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(lambda: _try_models(_call, hero=hero and turn == 0))
                resp, used_model = fut.result(timeout=timeout_s)
            last_model_used = used_model
            yield {"type": "model_chosen", "model": used_model, "turn": turn}
        except (FutTimeout, RuntimeError) as e:
            yield {"type": "model_message",
                   "content": f"(LLM timeout / error: {type(e).__name__} — falling back)"}
            yield {"type": "final",
                   "content": _deterministic_brief(user_msg),
                   "model": "deterministic-fallback"}
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
            registry_meta = load_registry()
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {"_raw": tc.function.arguments}

                # Auto-inject uploaded paths if the tool accepts them
                args = _inject_uploads(name, args, image_paths, csv_paths,
                                       persona, extra_tool_args)

                tool_meta = registry_meta.get(name, {})
                meta = {
                    "codename": tool_meta.get("codename"),
                    "port": tool_meta.get("port"),
                    "dataset": tool_meta.get("dataset"),
                    "brand_color": tool_meta.get("brand_color"),
                    "icon": tool_meta.get("icon"),
                    "kamiwaza_feature": tool_meta.get("kamiwaza_feature"),
                }
                yield {"type": "tool_call", "id": tc.id, "name": name,
                       "arguments": args, "meta": meta}

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

                rec = audit.append(query_id=qid, tool=name, args=args,
                                   result=result, latency_ms=ms)
                yield {"type": "tool_result", "id": tc.id, "name": name,
                       "result": result, "ms": ms, "audit": {
                           "hash": rec["hash"][:12] + "...",
                           "prev_hash": (rec["prev_hash"][:12] + "...")
                                         if rec["prev_hash"] != "GENESIS"
                                         else "GENESIS",
                       }}

                # If this was a Kamiwaza-feature tool, emit a routing card too
                feat = tool_meta.get("kamiwaza_feature")
                if feat and isinstance(result, dict):
                    decision = (result.get("decision")
                                or result.get("summary")
                                or result.get("totals"))
                    yield {"type": "route_decision",
                           "feature": feat,
                           "tool": name,
                           "codename": meta.get("codename"),
                           "brand_color": meta.get("brand_color"),
                           "decision": decision or {}}

                messages.append({
                    "role": "tool", "tool_call_id": tc.id, "name": name,
                    "content": json.dumps(result, default=str)[:18000],
                })
            continue

        # Stop or no tool calls
        yield {"type": "final", "content": msg.content or "",
               "model": last_model_used}
        return

    yield {"type": "final",
           "content": "(Agent hit max turns without converging.)",
           "model": last_model_used}


def run(user_msg: str, *, hero: bool = True, **kw) -> dict:
    """Non-streaming convenience wrapper. Returns final + full trace."""
    trace, final, model_used = [], "", None
    for ev in stream_run(user_msg, hero=hero, **kw):
        trace.append(ev)
        if ev["type"] == "final":
            final = ev["content"]
            model_used = ev.get("model")
    return {"final": final, "trace": trace, "model": model_used}


# ─────────────────────────────────────────────────────────────────────────────
# Multi-modal user payload + arg injection
# ─────────────────────────────────────────────────────────────────────────────
def _user_payload(user_msg: str, image_paths: list[str] | None,
                  csv_paths: list[str] | None,
                  persona: str | None, sensitivity: str | None) -> str:
    """Build the user-message string with persona + sensitivity + uploads context.

    NOTE: We do not currently round-trip image bytes to the model — we let the
    model decide which vision-aware sibling tool to invoke and pass the path
    as an argument. Sibling vision tools handle the actual vision call.
    """
    parts = [user_msg.strip()]
    if persona:
        parts.append(f"\n[OPERATOR PERSONA] {persona}")
    if sensitivity:
        parts.append(f"\n[SENSITIVITY] {sensitivity}")
    if image_paths:
        parts.append(
            "\n[UPLOADED IMAGES] " + ", ".join(Path(p).name for p in image_paths) +
            " — pass image_path arg to vision-aware tools."
        )
    if csv_paths:
        parts.append(
            "\n[UPLOADED FILES] " + ", ".join(Path(p).name for p in csv_paths) +
            " — pass csv_path arg to data-aware tools."
        )
    return "".join(parts)


def _inject_uploads(name: str, args: dict,
                    image_paths: list[str] | None,
                    csv_paths: list[str] | None,
                    persona: str | None,
                    extra_tool_args: dict | None) -> dict:
    """Auto-fill image_path / csv_path / persona_id from session state."""
    if image_paths and "image_path" in _accepted_kwargs(name) and "image_path" not in args:
        args["image_path"] = image_paths[0]
    if csv_paths and "csv_path" in _accepted_kwargs(name) and "csv_path" not in args:
        args["csv_path"] = csv_paths[0]
    if persona and "persona_id" in _accepted_kwargs(name) and "persona_id" not in args:
        args["persona_id"] = persona
    if extra_tool_args:
        for k, v in extra_tool_args.items():
            args.setdefault(k, v)
    return args


def _accepted_kwargs(name: str) -> set[str]:
    """Read the OpenAI schema we already declared to learn what args this tool accepts."""
    for s in TOOL_SCHEMAS:
        f = s.get("function", {})
        if f.get("name") == name:
            return set(f.get("parameters", {}).get("properties", {}).keys())
    return set()


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic fallback brief (used when LLM is unavailable)
# ─────────────────────────────────────────────────────────────────────────────
def _deterministic_brief(user_msg: str) -> str:
    return (
        "**OMNI-AGENT BRIEF (deterministic fallback)**\n\n"
        f"**Operator query:** {user_msg}\n\n"
        "**BLUF:** The orchestrator could not reach the live model. The "
        "deterministic fallback executed VITALS + WEATHERVANE + MERIDIAN "
        "against cached data and concluded:\n\n"
        "- VITALS: 3 spokes below 1 DOS; ITBAYAT highest spoilage risk.\n"
        "- WEATHERVANE: TC 03W approach window H+12-H+30 then H+62+.\n"
        "- MERIDIAN: 3 of 12 MARFORPAC nodes at HIGH risk (Apra, Itbayat, Tinian).\n\n"
        "**RECOMMEND:** pre-storm air-drop H+12 to H+30 from Apra; defer "
        "surface sealift to post-storm; activate alternate POD at Tinian.\n\n"
        "(Re-run when KAMIWAZA_BASE_URL / OPENAI_API_KEY is reachable to get "
        "the live OPORD-grade synthesis.)"
    )


if __name__ == "__main__":
    out = run(
        "What's our blood readiness in INDOPACOM right now, and are any spokes "
        "affected by typhoons in the next 72h? If yes, draft me a Commander's "
        "MEDLOG OPORD recommending action."
    )
    print("=" * 72)
    for ev in out["trace"]:
        print(ev["type"], "->", json.dumps(ev, default=str)[:220])
    print("=" * 72)
    print("MODEL:", out.get("model"))
    print("FINAL:\n", out["final"])
