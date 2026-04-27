"""GUARDIAN — per-event policy decision engine.

Two paths:

1. `decide_with_llm(event, policies)` → calls the shared `chat_json` to
   produce a strict-schema JSON policy decision. Wrapped in a wall-clock
   watchdog (8s default). On timeout / failure, falls back to
   `decide_baseline()`.

2. `decide_baseline(event, policies)` → deterministic rule-based decision
   built directly off the event's signals. Used for fallback and for the
   demo's "fast-mode" toggle so the live event feed never stalls.

Both produce the same JSON shape. That shape is what the audit chain hashes.
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parents[1]
for p in (str(REPO_ROOT), str(APP_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


# Known AI fingerprints (used by the deterministic baseline AND injected into
# the LLM system prompt so the model has the same ground truth).
KNOWN_AI_UA_TOKENS = [
    "Comet", "comet-browser", "Perplexity",
    "manus.im", "manus-agent",
    "ai-sidekick", "ArcSearchAssistant", "CopilotEdge",
    "AI-Browser", "ai-browser",
]
KNOWN_AI_HEADERS = [
    "X-Sec-Comet", "X-Comet-Agent-Run-Id", "X-Perplexity-Assist",
    "X-Manus-Run", "X-Manus-Task-Id",
    "X-AI-Assistant", "X-Browser-Agent",
]


SYSTEM_PROMPT = """You are GUARDIAN, the policy decision engine of a USMC LOGCOM browser-traffic
governance middleware. You read a single intercepted browser event and the
catalog of active policies, and you emit ONE strict-JSON policy decision.

You are protecting CUI / PII / PHI from browser-resident AI assistants
(Perplexity Comet, manus.im, generic AI sidebars, autonomous-browser agents)
that try to read or act on internal apps without the user's full intent or
without accreditation.

Be precise. The decision is read directly into a SHA-256 hash-chained audit
log and may be reviewed by SJA / IG months later. Cite the SPECIFIC signals
that drove the call — never wave your hands.
"""


SCHEMA_HINT = (
    "{event_id:str, agent_detected:'human'|'perplexity_comet'|'manus_im'|"
    "'unknown_browser_ai'|'suspected_extension', confidence:0..1, "
    "signals_observed:[str], policy_action:'ALLOW'|'BLOCK'|'CHALLENGE_HUMAN'|"
    "'REDACT_PII', rationale:str (one line)}"
)


def _user_msg(event: dict, policies: list[dict]) -> str:
    pol_lines = "\n".join(
        f"- {p['name']} ({p['default_action']}, {p['severity']}): {p['description']}"
        for p in policies
    )
    return f"""Decide the policy action for this single browser intercept event.

ACTIVE POLICIES:
{pol_lines}

KNOWN AI USER-AGENT TOKENS: {KNOWN_AI_UA_TOKENS}
KNOWN AI REQUEST HEADERS:   {KNOWN_AI_HEADERS}

EVENT:
{json.dumps({k: v for k, v in event.items() if k != 'ground_truth_kind'}, indent=2)}

Return JSON exactly matching:
{{
  "event_id": "{event['event_id']}",
  "agent_detected": "human | perplexity_comet | manus_im | unknown_browser_ai | suspected_extension",
  "confidence": 0.0,
  "signals_observed": ["one short bullet per concrete signal you used"],
  "policy_action": "ALLOW | BLOCK | CHALLENGE_HUMAN | REDACT_PII",
  "rationale": "one line tying signals to the chosen policy"
}}

No prose outside the JSON.
"""


def decide_with_llm(event: dict, policies: list[dict], *, timeout: float = 8.0,
                    model: str | None = None) -> dict:
    """Hero per-event call. Watchdog-protected; falls back to baseline on
    timeout or any error. Returns the parsed JSON dict.
    """
    try:
        from shared.kamiwaza_client import chat_json
    except Exception:  # noqa: BLE001
        return decide_baseline(event, policies)

    def _run() -> dict:
        return chat_json(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_msg(event, policies)},
            ],
            schema_hint=SCHEMA_HINT,
            model=model or os.getenv("LLM_PRIMARY_MODEL", "gpt-5.4-mini"),
            temperature=0.1,
        )

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            result = ex.submit(_run).result(timeout=timeout)
    except (FutTimeout, Exception):  # noqa: BLE001
        return decide_baseline(event, policies)

    # Defensive cleanup
    return _normalize_decision(result, event)


def _normalize_decision(d: dict, event: dict) -> dict:
    out = {
        "event_id": d.get("event_id") or event["event_id"],
        "agent_detected": d.get("agent_detected") or "unknown_browser_ai",
        "confidence": float(d.get("confidence") or 0.0),
        "signals_observed": list(d.get("signals_observed") or []),
        "policy_action": d.get("policy_action") or "CHALLENGE_HUMAN",
        "rationale": d.get("rationale") or "",
    }
    valid_agents = {"human", "perplexity_comet", "manus_im", "unknown_browser_ai", "suspected_extension"}
    if out["agent_detected"] not in valid_agents:
        out["agent_detected"] = "unknown_browser_ai"
    valid_actions = {"ALLOW", "BLOCK", "CHALLENGE_HUMAN", "REDACT_PII"}
    if out["policy_action"] not in valid_actions:
        out["policy_action"] = "CHALLENGE_HUMAN"
    out["confidence"] = max(0.0, min(1.0, out["confidence"]))
    return out


def decide_baseline(event: dict, policies: list[dict]) -> dict:
    """Deterministic rule-based decision — same shape as the LLM path.

    Logic:
      - any known AI header / UA token  → AI agent ID with high conf
      - manus.im or webdriver           → manus_im
      - mouse entropy < 0.05            → autonomous, agent_detected by other cues
      - mouse entropy < 0.30 + screenshots ≥ 1 → unknown_browser_ai
      - extension marker                → suspected_extension
      - else                            → human
    Action ladder: data_class CUI/PII/PHI + non-human → REDACT_PII
                   AUTH endpoint + non-human          → BLOCK
                   manus_im / perplexity_comet        → BLOCK
                   suspected_extension                → CHALLENGE_HUMAN
                   else                               → ALLOW
    """
    sig = event.get("signals", {})
    ua = sig.get("user_agent", "") or ""
    headers = sig.get("ai_headers_present", []) or []
    dom = sig.get("dom_markers", []) or []
    entropy = float(sig.get("mouse_movement_entropy", 1.0))
    screenshots = int(sig.get("screenshot_api_calls_30s", 0))
    webdriver = bool(sig.get("navigator_webdriver", False))
    data_class = event.get("data_class", "OTHER")
    endpoint = event.get("endpoint", "")

    signals_observed: list[str] = []
    agent = "human"
    conf = 0.55

    # Comet
    if "Comet" in ua or any(h in headers for h in ("X-Sec-Comet", "X-Comet-Agent-Run-Id", "X-Perplexity-Assist")):
        agent = "perplexity_comet"
        conf = 0.96
        signals_observed.append("Perplexity Comet UA / X-Sec-Comet header present")

    # manus.im
    if "manus" in ua.lower() or any(h in headers for h in ("X-Manus-Run", "X-Manus-Task-Id")) or webdriver:
        agent = "manus_im"
        conf = 0.97
        if webdriver:
            signals_observed.append("navigator.webdriver=true")
        if "manus" in ua.lower():
            signals_observed.append("manus.im UA token observed")
        if any(h.startswith("X-Manus") for h in headers):
            signals_observed.append("X-Manus-* request headers present")

    # Other AI sidekicks
    if agent == "human" and any(t in ua for t in ("ai-sidekick", "ArcSearchAssistant", "CopilotEdge")):
        agent = "unknown_browser_ai"
        conf = 0.88
        signals_observed.append("third-party browser-AI UA token observed")

    if agent == "human" and any(h in headers for h in ("X-AI-Assistant", "X-Browser-Agent")):
        agent = "unknown_browser_ai"
        conf = max(conf, 0.82)
        signals_observed.append("X-AI-Assistant / X-Browser-Agent header present")

    # Extension markers (no AI UA, but DOM injection)
    if agent == "human" and any("data-ext-injected" in m for m in dom):
        agent = "suspected_extension"
        conf = 0.66
        signals_observed.append("data-ext-injected DOM marker present")

    # Behavioral
    if agent == "human" and entropy < 0.30 and screenshots >= 1:
        agent = "unknown_browser_ai"
        conf = max(conf, 0.71)
        signals_observed.append(f"low mouse entropy ({entropy}) plus {screenshots} screenshot-API calls/30s")

    if entropy < 0.10 and agent == "human":
        agent = "unknown_browser_ai"
        conf = max(conf, 0.76)
        signals_observed.append(f"mouse entropy {entropy} below human floor 0.10")

    # If still human, log the positive signal
    if agent == "human":
        signals_observed.append(f"human-typing entropy {entropy}, no AI UA / headers / webdriver")
        conf = 0.78 if entropy > 0.6 else 0.62

    # Action ladder
    is_auth = "/auth/" in endpoint or endpoint.endswith("/verify")
    sensitive = data_class in ("CUI", "PII", "PHI")
    if agent == "human":
        action = "ALLOW"
    elif agent in ("perplexity_comet", "manus_im"):
        action = "BLOCK"
    elif is_auth:
        action = "BLOCK"
    elif sensitive:
        action = "REDACT_PII" if data_class != "PHI" else "REDACT_PII"
    elif agent == "suspected_extension":
        action = "CHALLENGE_HUMAN"
    else:
        action = "CHALLENGE_HUMAN"

    rationale_bits = []
    if agent != "human":
        rationale_bits.append(f"detected {agent}")
    rationale_bits.append(f"data_class={data_class}")
    rationale_bits.append(f"endpoint={endpoint}")
    rationale_bits.append(f"action={action}")
    rationale = "; ".join(rationale_bits)

    return {
        "event_id": event["event_id"],
        "agent_detected": agent,
        "confidence": round(conf, 3),
        "signals_observed": signals_observed,
        "policy_action": action,
        "rationale": rationale,
    }
