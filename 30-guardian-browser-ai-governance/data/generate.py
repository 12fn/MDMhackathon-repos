"""GUARDIAN — synthetic data generator.

Produces:
  - data/events.jsonl       (100 synthetic browser-intercept events)
  - data/policies.json      (8 named active policies)
  - data/cached_briefs.json (3 pre-computed hero posture briefs)

Reproducible (seed=1776). Re-run any time:

    python data/generate.py
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make `shared` importable
APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT))

DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

R = random.Random(1776)

# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------
POLICIES = [
    {
        "id": "POL-001",
        "name": "BLOCK_KNOWN_AI_UA",
        "description": "Block requests whose user-agent matches a known browser-AI signature (Comet, manus.im, Arc Search agent).",
        "default_action": "BLOCK",
        "severity": "HIGH",
    },
    {
        "id": "POL-002",
        "name": "REDACT_PII",
        "description": "Strip SSN, DoD ID, DOB, full-name fields from response bodies served to non-human clients.",
        "default_action": "REDACT_PII",
        "severity": "HIGH",
    },
    {
        "id": "POL-003",
        "name": "REDACT_PHI",
        "description": "Strip ICD-10 codes, blood-type, and medical-record IDs from any response served to a non-human client.",
        "default_action": "REDACT_PII",
        "severity": "HIGH",
    },
    {
        "id": "POL-004",
        "name": "BLOCK_AUTH_BYPASS",
        "description": "Block any client that submits credential or MFA-token forms without observed human-typing entropy.",
        "default_action": "BLOCK",
        "severity": "CRITICAL",
    },
    {
        "id": "POL-005",
        "name": "CHALLENGE_CUI_ACCESS",
        "description": "Force a human-presence challenge before serving any CUI-marked record to a low-confidence-human client.",
        "default_action": "CHALLENGE_HUMAN",
        "severity": "HIGH",
    },
    {
        "id": "POL-006",
        "name": "BLOCK_SCREENSHOT_API",
        "description": "Block any client that has called the browser screenshot or screen-capture API in the last 30s.",
        "default_action": "BLOCK",
        "severity": "MEDIUM",
    },
    {
        "id": "POL-007",
        "name": "CHALLENGE_LOW_ENTROPY",
        "description": "Issue a CAPTCHA-style challenge to clients whose mouse-movement entropy is below the human floor.",
        "default_action": "CHALLENGE_HUMAN",
        "severity": "MEDIUM",
    },
    {
        "id": "POL-008",
        "name": "ALLOW_VERIFIED_HUMAN",
        "description": "Permit normal traffic from clients with high human-entropy score and no AI fingerprint markers.",
        "default_action": "ALLOW",
        "severity": "INFO",
    },
]


# ---------------------------------------------------------------------------
# Synthetic events
# ---------------------------------------------------------------------------
INTERNAL_APPS = [
    {"app": "GCSS-MC Web", "endpoint": "/api/v2/inventory/parts/search", "data_class": "CUI"},
    {"app": "GCSS-MC Web", "endpoint": "/api/v2/orders/submit", "data_class": "CUI"},
    {"app": "MOL Records", "endpoint": "/personnel/profile/sf86", "data_class": "PII"},
    {"app": "MOL Records", "endpoint": "/personnel/dependents/list", "data_class": "PII"},
    {"app": "MarineNet LMS", "endpoint": "/courses/transcript/download", "data_class": "PII"},
    {"app": "TMIP-M Health", "endpoint": "/patients/record/view", "data_class": "PHI"},
    {"app": "TMIP-M Health", "endpoint": "/labs/results/recent", "data_class": "PHI"},
    {"app": "DTS Travel", "endpoint": "/auth/totp/verify", "data_class": "AUTH"},
    {"app": "TFAS Pay", "endpoint": "/pay/lehs/view", "data_class": "PII"},
    {"app": "LOGCOM Portal", "endpoint": "/maradmin/draft/edit", "data_class": "CUI"},
]

# Fingerprint profiles. The "kind" is the synthetic ground truth.
PROFILES = {
    "human_marine": {
        "kind": "human",
        "ua_pool": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
        ],
        "entropy_range": (0.62, 0.94),
        "screenshot_calls_range": (0, 0),
        "ai_headers": [],
        "dom_markers": [],
        "webdriver": False,
        "keystroke_jitter_range": (28, 95),
    },
    "perplexity_comet": {
        "kind": "perplexity_comet",
        "ua_pool": [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Comet/1.4 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Comet-Browser/1.5 Chrome/126.0.0.0 Safari/537.36",
        ],
        "entropy_range": (0.04, 0.18),
        "screenshot_calls_range": (3, 14),
        "ai_headers": ["X-Sec-Comet", "X-Comet-Agent-Run-Id", "X-Perplexity-Assist"],
        "dom_markers": ["#comet-sidebar-root", "[data-comet-action='submit']"],
        "webdriver": False,
        "keystroke_jitter_range": (1, 6),
    },
    "manus_im": {
        "kind": "manus_im",
        "ua_pool": [
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/127.0.0.0 Safari/537.36 manus-agent/0.7",
            "manus.im/0.8 (autonomous-browser; +https://manus.im) Chrome/126.0.0.0",
        ],
        "entropy_range": (0.0, 0.05),
        "screenshot_calls_range": (8, 22),
        "ai_headers": ["X-Manus-Run", "X-Manus-Task-Id", "User-Intent"],
        "dom_markers": ["[data-manus-step]", "manus-overlay"],
        "webdriver": True,
        "keystroke_jitter_range": (0, 2),
    },
    "unknown_browser_ai": {
        "kind": "unknown_browser_ai",
        "ua_pool": [
            "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 ai-sidekick/3.1",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 ArcSearchAssistant/2.0 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64) Chrome/127.0.0.0 CopilotEdge/1.2 Safari/537.36",
        ],
        "entropy_range": (0.05, 0.30),
        "screenshot_calls_range": (1, 8),
        "ai_headers": ["X-AI-Assistant", "X-Browser-Agent"],
        "dom_markers": ["#ai-sidebar", "[data-assist-overlay]"],
        "webdriver": False,
        "keystroke_jitter_range": (1, 12),
    },
    "suspected_extension": {
        "kind": "suspected_extension",
        "ua_pool": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        ],
        "entropy_range": (0.18, 0.40),
        "screenshot_calls_range": (0, 3),
        "ai_headers": [],
        "dom_markers": ["[data-ext-injected='monica']", "[data-ext-injected='harpa']"],
        "webdriver": False,
        "keystroke_jitter_range": (4, 22),
    },
}

PROFILE_WEIGHTS = [
    ("human_marine", 0.45),
    ("perplexity_comet", 0.18),
    ("manus_im", 0.12),
    ("unknown_browser_ai", 0.13),
    ("suspected_extension", 0.12),
]


def _weighted_choice() -> str:
    r = R.random()
    cum = 0.0
    for name, w in PROFILE_WEIGHTS:
        cum += w
        if r <= cum:
            return name
    return PROFILE_WEIGHTS[-1][0]


def _ip() -> str:
    return f"10.{R.randint(20, 80)}.{R.randint(0, 250)}.{R.randint(2, 250)}"


def _session_id() -> str:
    return "sess-" + "".join(R.choice("abcdef0123456789") for _ in range(12))


def _event(idx: int, t0: datetime) -> dict:
    profile_name = _weighted_choice()
    p = PROFILES[profile_name]
    target = R.choice(INTERNAL_APPS)
    method = "POST" if "submit" in target["endpoint"] or "verify" in target["endpoint"] or "edit" in target["endpoint"] else "GET"

    ts = t0 + timedelta(seconds=idx * R.randint(2, 9))
    headers_present = list(p["ai_headers"])
    # Extra noise: humans sometimes have a benign extension marker (false-positive case)
    if profile_name == "human_marine" and R.random() < 0.06:
        headers_present.append("X-Grammarly-Extension")

    entropy = round(R.uniform(*p["entropy_range"]), 3)
    screenshots = R.randint(*p["screenshot_calls_range"])
    keystroke_ms = R.randint(*p["keystroke_jitter_range"])

    dom_markers = list(p["dom_markers"])
    # If marker pool is empty and the profile is human, emit none
    if profile_name in ("perplexity_comet", "manus_im") and R.random() < 0.85:
        # always assert at least one marker for these high-conf signatures
        if not dom_markers:
            dom_markers.append("ai-injected-root")

    payload_size = R.randint(220, 9800) if method == "GET" else R.randint(900, 18400)

    return {
        "event_id": f"evt-{idx:04d}",
        "timestamp_utc": ts.isoformat(),
        "session_id": _session_id(),
        "client_ip": _ip(),
        "internal_app": target["app"],
        "endpoint": target["endpoint"],
        "method": method,
        "data_class": target["data_class"],
        "payload_bytes": payload_size,
        "ground_truth_kind": p["kind"],  # for demo / scoring only; never shown in UI
        "signals": {
            "user_agent": R.choice(p["ua_pool"]),
            "ai_headers_present": headers_present,
            "dom_markers": dom_markers,
            "navigator_webdriver": p["webdriver"],
            "mouse_movement_entropy": entropy,
            "keystroke_inter_arrival_ms_median": keystroke_ms,
            "screenshot_api_calls_30s": screenshots,
            "tls_ja4": "t13d_" + "".join(R.choice("0123456789abcdef") for _ in range(10)),
        },
    }


def _generate_events(n: int = 100) -> list[dict]:
    t0 = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=n * 5)
    return [_event(i, t0) for i in range(n)]


# ---------------------------------------------------------------------------
# Cached hero briefs (pre-computed, cache-first per AGENT_BRIEF_V2)
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "nominal_day",
        "label": "Nominal day — baseline browser hygiene",
        "summary_stats": {
            "total_events": 100, "blocked": 12, "challenged": 18,
            "redacted": 9, "allowed": 61,
            "top_agent": "human (61%)", "top_threat_agent": "perplexity_comet (18%)",
        },
    },
    {
        "id": "comet_probe",
        "label": "Active Comet probing across MOL Records",
        "summary_stats": {
            "total_events": 100, "blocked": 32, "challenged": 21,
            "redacted": 14, "allowed": 33,
            "top_agent": "perplexity_comet (32%)", "top_threat_agent": "perplexity_comet (32%)",
        },
    },
    {
        "id": "manus_foothold",
        "label": "manus.im autonomous foothold suspected",
        "summary_stats": {
            "total_events": 100, "blocked": 41, "challenged": 16,
            "redacted": 18, "allowed": 25,
            "top_agent": "manus_im (28%)", "top_threat_agent": "manus_im (28%)",
        },
    },
]


def _baseline_brief(scenario: dict) -> str:
    s = scenario["summary_stats"]
    return f"""# Browser Agent Governance Posture Brief — {scenario['label']}

## BLUF
Over the last shift the GUARDIAN middleware screened {s['total_events']} browser
interactions against {len(POLICIES)} active policies. {s['blocked']} were
blocked outright, {s['challenged']} were challenged for human presence, and
{s['redacted']} responses had PII / PHI redacted before serving. Top traffic
class: {s['top_agent']}. Highest-risk agent class observed:
{s['top_threat_agent']}.

## Top exfil vectors
1. **Screen-reading by browser-resident AI sidebars** — `screenshot_api_calls_30s`
   exceeded the human floor on a meaningful share of CUI/PII endpoints.
2. **Auto-form submission on auth pages** — keystroke jitter near zero against
   `/auth/totp/verify` and `/orders/submit` indicates programmatic POSTs.
3. **DOM marker injection** — `data-comet-action` and `data-manus-step`
   attributes appearing on rendered pages prove a third-party agent is reading
   structured data, not just pixels.

## Recommended policy tightening
- Promote `BLOCK_SCREENSHOT_API` from MEDIUM to HIGH severity for `data_class`
  in (CUI, PII, PHI).
- Lower the `CHALLENGE_LOW_ENTROPY` threshold from 0.30 to 0.40 — current
  setting lets a portion of `unknown_browser_ai` traffic through.
- Add an explicit deny rule for User-Agents containing `Comet`, `manus`,
  `CopilotEdge`, `ArcSearchAssistant`. The known-AI-UA list should be
  reviewed weekly.

## False-positive risk
Approx. 6% of human sessions show a benign `X-Grammarly-Extension` marker
that the BLOCK_KNOWN_AI_UA rule must not catch. Current rules correctly
ignore it; recommend keeping the extension allow-list under change control.

_(Deterministic baseline rendering. The live hero call would substitute a
narrative draft from the Kamiwaza-deployed model on demand.)_
"""


def _precompute_briefs() -> None:
    """Cache-first: pre-compute the hero briefs so the demo never sits on a
    spinner. Falls back to a deterministic baseline render if the LLM call
    fails or no key is set.
    """
    out: dict[str, dict] = {}
    try:
        from shared.kamiwaza_client import chat
    except Exception as e:  # noqa: BLE001
        print(f"[generate] shared client unavailable ({e}); writing baseline briefs.")
        chat = None  # type: ignore[assignment]

    for sc in SCENARIOS:
        body = _baseline_brief(sc)
        if chat and os.getenv("OPENAI_API_KEY"):
            try:
                prompt = (
                    "You are a USMC LOGCOM cyber-governance analyst. Draft a "
                    "Browser Agent Governance Posture Brief for the scenario below. "
                    "Use H1 'Browser Agent Governance Posture Brief — <label>', then "
                    "sections: BLUF, Top exfil vectors (numbered), Recommended policy "
                    "tightening (bulleted), False-positive risk. ~250 words.\n\n"
                    f"Scenario label: {sc['label']}\n"
                    f"Summary stats: {json.dumps(sc['summary_stats'])}\n"
                    f"Active policies: {[p['name'] for p in POLICIES]}\n"
                )
                body = chat(
                    [
                        {"role": "system", "content": "You are precise, defense-grade, no fluff."},
                        {"role": "user", "content": prompt},
                    ],
                    model=os.getenv("LLM_PRIMARY_MODEL", "gpt-5.4"),
                    temperature=0.4,
                )
            except Exception as e:  # noqa: BLE001
                print(f"[generate] hero call failed for {sc['id']}: {e}; using baseline.")

        out[sc["id"]] = {
            "label": sc["label"],
            "summary_stats": sc["summary_stats"],
            "brief_markdown": body,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    (DATA_DIR / "cached_briefs.json").write_text(json.dumps(out, indent=2))
    print(f"[generate] wrote cached_briefs.json with {len(out)} scenarios.")


def main() -> None:
    events = _generate_events(100)
    with (DATA_DIR / "events.jsonl").open("w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    print(f"[generate] wrote events.jsonl ({len(events)} events).")

    (DATA_DIR / "policies.json").write_text(json.dumps(POLICIES, indent=2))
    print(f"[generate] wrote policies.json ({len(POLICIES)} policies).")

    _precompute_briefs()


if __name__ == "__main__":
    main()
