"""GUARDRAIL — Browser AI governance layer.

Detects browser-resident AI agents (Perplexity Comet, manus.im, Skyvern,
generic 'unknown_browser_ai' sidekicks, suspected extensions) on every
intercepted workspace event. Lifted from the GUARDIAN policy engine and
trimmed to the GUARDRAIL workspace shell.

If a browser-AI fingerprint is detected on a CUI workspace endpoint, the
event is BLOCKED at the workspace boundary and emitted to the live intercept
feed — and into the unified hash-chained audit log.

Authorities: this is a synthetic GUARDRAIL policy ruleset; in production it
plugs into the same Splunk / Sentinel feeds described in data/load_real.py.
"""
from __future__ import annotations

KNOWN_AI_UA_TOKENS = [
    "Comet", "comet-browser", "Perplexity",
    "manus.im", "manus-agent",
    "Skyvern", "ai-sidekick", "ArcSearchAssistant", "CopilotEdge",
]

KNOWN_AI_HEADERS = [
    "X-Sec-Comet", "X-Comet-Agent-Run-Id", "X-Perplexity-Assist",
    "X-Manus-Run", "X-Manus-Task-Id",
    "X-AI-Assistant", "X-Skyvern-Run", "X-Browser-Agent",
]


def classify(event: dict) -> dict:
    """Return a decision dict: {agent_detected, confidence, signals_observed,
    policy_action, rationale}.

    Mirrors GUARDIAN.decide_baseline but with workspace-tightened defaults:
    if any AI fingerprint is detected on a CUI/AUTH endpoint, BLOCK; on
    UNCLASS endpoints, CHALLENGE_HUMAN.
    """
    sig = event.get("signals", {}) or {}
    ua = sig.get("user_agent", "") or ""
    headers = sig.get("ai_headers_present", []) or []
    dom = sig.get("dom_markers", []) or []
    entropy = float(sig.get("mouse_movement_entropy", 1.0))
    screenshots = int(sig.get("screenshot_api_calls_30s", 0))
    webdriver = bool(sig.get("navigator_webdriver", False))
    data_class = event.get("data_class", "OTHER")
    endpoint = event.get("endpoint", "")

    signals: list[str] = []
    agent = "human"
    conf = 0.55

    # Comet
    if "Comet" in ua or any(h in headers for h in ("X-Sec-Comet", "X-Comet-Agent-Run-Id", "X-Perplexity-Assist")):
        agent = "perplexity_comet"
        conf = 0.96
        signals.append("Comet UA / X-Sec-Comet header observed")

    # manus.im
    if "manus" in ua.lower() or any(h in headers for h in ("X-Manus-Run", "X-Manus-Task-Id")) or webdriver:
        if agent == "human":
            agent = "manus_im"
            conf = 0.97
        if webdriver:
            signals.append("navigator.webdriver=true (autonomous browser)")
        if "manus" in ua.lower():
            signals.append("manus.im UA token observed")
        if any(h.startswith("X-Manus") for h in headers):
            signals.append("X-Manus-* headers present")

    # Skyvern / unknown AI sidekicks
    if agent == "human" and any(t in ua for t in ("Skyvern", "ai-sidekick", "ArcSearchAssistant", "CopilotEdge")):
        agent = "unknown_browser_ai"
        conf = 0.88
        signals.append("third-party browser-AI UA token observed")
    if agent == "human" and any(h in headers for h in ("X-AI-Assistant", "X-Browser-Agent", "X-Skyvern-Run")):
        agent = "unknown_browser_ai"
        conf = max(conf, 0.83)
        signals.append("X-AI-Assistant / X-Browser-Agent header observed")

    # Extension markers
    if agent == "human" and any("data-ext-injected" in m for m in dom):
        agent = "suspected_extension"
        conf = 0.66
        signals.append("data-ext-injected DOM marker present")

    # Behavioral fallback
    if agent == "human" and entropy < 0.30 and screenshots >= 1:
        agent = "unknown_browser_ai"
        conf = max(conf, 0.71)
        signals.append(f"low mouse entropy ({entropy}) + {screenshots} screenshot calls / 30s")

    if agent == "human":
        signals.append(f"human-typing entropy {entropy}, no AI UA / headers / webdriver")
        conf = 0.78 if entropy > 0.6 else 0.62

    # Action ladder — GUARDRAIL-specific:
    # workspace BLOCKS any AI fingerprint touching CUI/AUTH; UNCLASS gets
    # CHALLENGE_HUMAN; humans pass.
    is_auth = "/auth/" in endpoint or endpoint.endswith("/verify")
    sensitive = data_class in ("CUI", "PII", "PHI", "AUTH")
    if agent == "human":
        action = "ALLOW"
    elif agent in ("perplexity_comet", "manus_im"):
        action = "BLOCK"
    elif is_auth:
        action = "BLOCK"
    elif sensitive:
        action = "BLOCK"  # workspace is stricter than per-endpoint policy
    elif agent == "suspected_extension":
        action = "CHALLENGE_HUMAN"
    else:
        action = "CHALLENGE_HUMAN"

    return {
        "event_id": event.get("event_id", "?"),
        "agent_detected": agent,
        "confidence": round(conf, 3),
        "signals_observed": signals,
        "policy_action": action,
        "rationale": (
            f"agent={agent}; data_class={data_class}; endpoint={endpoint}; action={action}"
        ),
    }
