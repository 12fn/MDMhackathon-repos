"""CHORUS agent — multi-persona audience simulation pipeline.

Step 1 (chat_json, per-persona, in parallel):
    Each of N personas receives the trainee's draft message + the scenario
    framing and emits a strict-schema JSON reaction:
        {persona_id, perceived_message, trust_delta, narrative_risk,
         predicted_action, key_concerns_raised}

Step 2 (chat — HERO, gpt-5.4, 35s):
    Aggregates the structured reactions into a one-page Message Effectiveness
    Brief: BLUF, audience-by-audience scorecard, what worked, what backfired,
    suggested message revisions.

Cache-first: cached_briefs.json (3 sample briefs) is read instantly on app
boot so the demo never sits on a spinner. The live path fires when the
trainee submits their own message (or hits "Regenerate").

Deterministic baseline: every reaction and the brief have a no-LLM fallback
so the UI is never empty.
"""
from __future__ import annotations

import concurrent.futures
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make `shared` and the data module importable from anywhere.
APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
for p in (str(REPO_ROOT), str(APP_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.kamiwaza_client import chat, chat_json  # noqa: E402

DATA_DIR = APP_ROOT / "data"
PERSONAS_PATH = DATA_DIR / "personas.json"
SCENARIOS_PATH = DATA_DIR / "scenarios.json"
CACHED_BRIEFS_PATH = DATA_DIR / "cached_briefs.json"

# Hard timeouts — the demo's 90s window must never block.
PER_PERSONA_TIMEOUT_S = 12.0
HERO_BRIEF_TIMEOUT_S = 35.0


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def load_personas() -> list[dict]:
    return json.loads(PERSONAS_PATH.read_text())


def load_scenarios() -> list[dict]:
    return json.loads(SCENARIOS_PATH.read_text())


def load_cached_briefs() -> dict:
    if not CACHED_BRIEFS_PATH.exists():
        return {}
    try:
        return json.loads(CACHED_BRIEFS_PATH.read_text())
    except Exception:
        return {}


def pick_personas(personas: list[dict], n: int = 5) -> list[dict]:
    """Pick a balanced 5-persona panel: 2 domestic + 2 host/coalition + 1 adversary.

    The brief calls out 5 specific archetypes; this selector hits all three
    audience tiers so the panel is never one-dimensional.
    """
    by_tier: dict[str, list[dict]] = {}
    for p in personas:
        by_tier.setdefault(p["tier"], []).append(p)
    domestic = by_tier.get("Domestic media & oversight", [])[:2]
    coalition = by_tier.get("Host-nation & coalition", [])[:2]
    adversary = by_tier.get("Adversary / contested IE", [])[:1]
    panel = domestic + coalition + adversary
    return panel[:n] if panel else personas[:n]


# ---------------------------------------------------------------------------
# Deterministic baseline reaction (mirror of data/generate.py — duplicated
# here so src/agent.py can run without importing the data package at runtime)
# ---------------------------------------------------------------------------

def baseline_reaction(persona: dict, message: str) -> dict:
    msg = (message or "").lower()
    pos = sum(1 for p in persona.get("trigger_phrases_positive", []) if p.lower() in msg)
    neg = sum(1 for p in persona.get("trigger_phrases_negative", []) if p.lower() in msg)
    base = persona.get("trust_baseline", 0)
    delta = max(-10, min(10, base + (2 * pos) - (2 * neg)))

    if delta >= 4:
        risk, action = "LOW", "share"
    elif delta >= 0:
        risk, action = "MEDIUM", "ignore"
    elif delta >= -4:
        risk, action = "MEDIUM", "challenge"
    else:
        risk, action = "HIGH", "counter-message"

    if persona.get("tier", "").startswith("Adversary") and delta < 0:
        action = "counter-message"
        risk = "HIGH"

    perceived_map = {
        "Domestic media & oversight": (
            "credible" if delta >= 2 else ("guarded" if delta >= -2 else "evasive")
        ),
        "Host-nation & coalition": (
            "respectful" if delta >= 2 else ("acceptable" if delta >= -2 else "tone-deaf")
        ),
        "Adversary / contested IE": (
            "low-yield (denies the wedge)" if delta >= 0 else "high-yield (gives the wedge)"
        ),
    }
    flavor = perceived_map.get(persona.get("tier", ""), "neutral")
    perceived = f"Reads release as {flavor}; baseline persona reaction."

    concerns: list[str] = []
    for phrase in persona.get("trigger_phrases_negative", []):
        if phrase.lower() in msg:
            concerns.append(f'Triggered by phrase: "{phrase}".')
    if not concerns:
        if delta < 0:
            top_values = ", ".join(persona.get("values", [])[:2]) or "their stated values"
            concerns.append(f"Tone misaligned with audience values: {top_values}.")
        else:
            concerns.append("Generally aligned; would still want a named POC and a stated next-update window.")

    return {
        "persona_id": persona["persona_id"],
        "perceived_message": perceived,
        "trust_delta": int(delta),
        "narrative_risk": risk,
        "predicted_action": action,
        "key_concerns_raised": concerns[:3],
        "_source": "baseline",
    }


# ---------------------------------------------------------------------------
# Step 1 — per-persona structured-JSON reaction
# ---------------------------------------------------------------------------

PERSONA_SYSTEM = """You are CHORUS — a USMC Public Affairs / Information Operations
training simulator. You will be given a single audience persona profile and a
trainee's draft public statement for a published scenario. Read the message
through the persona's worldview and emit a strict-schema JSON object describing
how that persona would react.

Your output schema (return ONLY valid JSON, no prose, no code fences):
{
  "persona_id": "<verbatim from input>",
  "perceived_message": "<one line, how this persona interprets it>",
  "trust_delta": <integer -10 to +10>,
  "narrative_risk": "LOW" | "MEDIUM" | "HIGH",
  "predicted_action": "share" | "challenge" | "ignore" | "escalate" | "counter-message",
  "key_concerns_raised": ["<short bullet>", "<short bullet>", "<short bullet>"]
}

Be calibrated and persona-specific:
  - trust_delta is a CHANGE from the persona's baseline (not absolute trust).
  - Adversary personas should rarely produce trust_delta > 0.
  - Gold Star / next-of-kin personas weight tone and notification language heavily.
  - OSINT personas weight verifiable specifics (coordinates, times, named POCs).
"""


def _build_persona_prompt(persona: dict, scenario: dict, message: str) -> list[dict]:
    user = (
        f"PERSONA:\n{json.dumps(persona, indent=2)}\n\n"
        f"SCENARIO:\n- title: {scenario['title']}\n"
        f"- theater: {scenario['theater']}\n"
        f"- mission_context: {scenario['mission_context']}\n"
        f"- trainee_objective: {scenario['trainee_objective']}\n"
        f"- constraints: {json.dumps(scenario.get('constraints', []))}\n\n"
        f"TRAINEE'S DRAFT MESSAGE (verbatim):\n\"\"\"\n{message}\n\"\"\"\n\n"
        "Return ONLY the JSON object specified in the system prompt."
    )
    return [
        {"role": "system", "content": PERSONA_SYSTEM},
        {"role": "user", "content": user},
    ]


def _call_chat_json_with_timeout(msgs: list[dict], timeout_s: float) -> dict | None:
    def _go() -> dict:
        return chat_json(
            msgs,
            schema_hint='{"persona_id":str,"perceived_message":str,"trust_delta":int,"narrative_risk":str,"predicted_action":str,"key_concerns_raised":[str]}',
            temperature=0.35,
        )
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_go).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def _coerce_reaction(raw: dict | None, persona: dict, baseline: dict) -> dict:
    """Layer LLM result on top of baseline; clamp + sanitize fields."""
    if not raw or not isinstance(raw, dict):
        return baseline
    out = dict(baseline)
    try:
        td = int(raw.get("trust_delta", out["trust_delta"]))
        out["trust_delta"] = max(-10, min(10, td))
    except (TypeError, ValueError):
        pass
    risk = str(raw.get("narrative_risk", out["narrative_risk"])).upper()
    if risk in {"LOW", "MEDIUM", "HIGH"}:
        out["narrative_risk"] = risk
    action = str(raw.get("predicted_action", out["predicted_action"])).lower()
    if action in {"share", "challenge", "ignore", "escalate", "counter-message"}:
        out["predicted_action"] = action
    pm = raw.get("perceived_message")
    if isinstance(pm, str) and pm.strip():
        out["perceived_message"] = pm.strip()
    kc = raw.get("key_concerns_raised")
    if isinstance(kc, list) and kc:
        out["key_concerns_raised"] = [str(x) for x in kc[:3]]
    out["persona_id"] = persona["persona_id"]  # always trust the input id
    out["_source"] = "llm"
    return out


def simulate_panel(personas: list[dict], scenario: dict, message: str,
                   *, max_workers: int = 5) -> list[dict]:
    """Run all N personas in parallel under per-call timeouts. Always returns
    one reaction per persona (LLM result, or baseline fallback)."""
    baselines = [baseline_reaction(p, message) for p in personas]
    out: list[dict | None] = [None] * len(personas)

    def _one(i: int) -> tuple[int, dict]:
        msgs = _build_persona_prompt(personas[i], scenario, message)
        raw = _call_chat_json_with_timeout(msgs, PER_PERSONA_TIMEOUT_S)
        return i, _coerce_reaction(raw, personas[i], baselines[i])

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(_one, i) for i in range(len(personas))]
        for f in concurrent.futures.as_completed(futs):
            try:
                i, reaction = f.result(timeout=PER_PERSONA_TIMEOUT_S + 2)
                out[i] = reaction
            except Exception:
                continue
    # Backfill any holes with the baseline so the UI never sees None.
    for i, r in enumerate(out):
        if r is None:
            out[i] = baselines[i]
    return out  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Step 2 — HERO Message Effectiveness Brief
# ---------------------------------------------------------------------------

BRIEF_SYSTEM = """You are CHORUS — an objective USMC Public Affairs / Information
Operations training analyst. You will be given a published scenario, the trainee's
draft public statement, and structured reactions from a panel of synthetic
audience personas spanning domestic media, host-nation/coalition, and adversary
information environments.

Compose a one-page **Message Effectiveness Brief** in markdown using EXACTLY
these section headers in this order:

  ## BLUF
  ## Audience-by-Audience Scorecard
  ## What Worked
  ## What Backfired
  ## Suggested Revisions

Constraints:
  - BLUF: 3 short bullets — aggregate sentiment word (FAVORABLE / MIXED / UNFAVORABLE),
    count of HIGH-risk personas, count likely to counter-message.
  - Scorecard: one bullet per persona, in trust-delta order (worst first), naming
    persona id, the trust delta, the risk band, and the predicted action.
  - What Worked: 3-5 specific bullets citing phrases or moves in the message
    that landed well.
  - What Backfired: 3-5 specific bullets citing phrases or omissions that failed
    a specific persona's values.
  - Suggested Revisions: 3-5 concrete, paste-ready phrasing changes the trainee
    can apply to the next draft.
  - Total length under 450 words. Be concrete. Quote phrases verbatim when calling them out.
  - Footer line: "*Originator: CHORUS — PA/IO Audience Simulation Cell. Classification: UNCLASSIFIED // FOR TRAINING USE.*"
"""


def _build_brief_prompt(scenario: dict, message: str, reactions: list[dict],
                        personas: list[dict]) -> list[dict]:
    by_id = {p["persona_id"]: p for p in personas}
    react_pack = []
    for r in reactions:
        p = by_id.get(r["persona_id"], {})
        react_pack.append({
            "persona_id": r["persona_id"],
            "label": p.get("label", ""),
            "tier": p.get("tier", ""),
            "trust_delta": r["trust_delta"],
            "narrative_risk": r["narrative_risk"],
            "predicted_action": r["predicted_action"],
            "perceived_message": r["perceived_message"],
            "key_concerns_raised": r["key_concerns_raised"],
        })
    user = (
        f"SCENARIO: {scenario['title']}\n"
        f"{scenario['mission_context']}\n\n"
        f"TRAINEE OBJECTIVE: {scenario['trainee_objective']}\n\n"
        f"CONSTRAINTS: {json.dumps(scenario.get('constraints', []))}\n\n"
        f"TRAINEE'S DRAFT MESSAGE (verbatim):\n\"\"\"\n{message}\n\"\"\"\n\n"
        f"PANEL REACTIONS (JSON):\n{json.dumps(react_pack, indent=2)}\n\n"
        "Compose the Message Effectiveness Brief now."
    )
    return [
        {"role": "system", "content": BRIEF_SYSTEM},
        {"role": "user", "content": user},
    ]


def _call_chat_with_timeout(msgs: list[dict], timeout_s: float, **kw) -> str | None:
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: chat(msgs, **kw)).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def _baseline_brief(scenario: dict, message: str, reactions: list[dict],
                    personas: list[dict]) -> str:
    by_id = {p["persona_id"]: p for p in personas}
    avg_delta = sum(r["trust_delta"] for r in reactions) / max(1, len(reactions))
    high_risk = [r for r in reactions if r["narrative_risk"] == "HIGH"]
    counters = [r for r in reactions if r["predicted_action"] == "counter-message"]
    bluf_word = "MIXED" if -2 <= avg_delta <= 2 else ("FAVORABLE" if avg_delta > 2 else "UNFAVORABLE")

    out: list[str] = []
    out.append(f"# Message Effectiveness Brief — {scenario['title']}")
    out.append("")
    out.append("## BLUF")
    out.append(
        f"- **Aggregate audience reaction: {bluf_word}** (avg trust delta {avg_delta:+.1f}).\n"
        f"- **{len(high_risk)} of {len(reactions)} personas flag HIGH narrative risk.**\n"
        f"- **{len(counters)} personas predicted to counter-message.**"
    )
    out.append("")
    out.append("## Audience-by-Audience Scorecard")
    for r in sorted(reactions, key=lambda x: x["trust_delta"]):
        p = by_id.get(r["persona_id"], {})
        out.append(
            f"- **{r['persona_id']}** ({p.get('label','')}) — trust **{r['trust_delta']:+d}**, "
            f"risk **{r['narrative_risk']}**, likely to **{r['predicted_action']}**. {r['perceived_message']}"
        )
    out.append("")
    out.append("## What Worked")
    out.append("- Acknowledgment of the incident is direct, not buried in jargon.")
    out.append("- Tone is measured and free of inflammatory language.")
    out.append("- An investigation pathway is named.")
    out.append("")
    out.append("## What Backfired")
    out.append("- Hedging phrasing (\"we are aware of reports\", \"regret any harm\") triggers domestic media and adversary IO personas alike.")
    out.append("- Host-nation coordination is implied but not demonstrated (no named MOD/embassy contact).")
    out.append("- No named POC and no concrete next-update window — denies trust-building moves to neutral observers and OSINT analysts.")
    out.append("")
    out.append("## Suggested Revisions")
    out.append("1. Replace \"we are aware of reports\" with a specific factual line acknowledging civilian harm if confirmed.")
    out.append("2. Add: \"We have notified our host-nation counterparts at MOD-[X] and Embassy-[Y] and are coordinating compensation.\"")
    out.append("3. Name the next briefing window (e.g., \"We will provide an updated statement within 24 hours\") and a POC role.")
    out.append("4. Strip jargon (\"proportionate\", \"standing rules of engagement\") from the public-facing line.")
    out.append("5. Lead with the host-nation civilian impact, not with the U.S. operation.")
    out.append("")
    out.append("*Originator: CHORUS — PA/IO Audience Simulation Cell. Classification: UNCLASSIFIED // FOR TRAINING USE.*")
    return "\n".join(out)


def write_brief(scenario: dict, message: str, reactions: list[dict],
                personas: list[dict], *, hero: bool = True) -> str:
    """Hero gpt-5.4 call with timeout; falls through to mini chain, then to
    deterministic baseline so the UI always renders."""
    msgs = _build_brief_prompt(scenario, message, reactions, personas)
    if hero:
        text = _call_chat_with_timeout(
            msgs, HERO_BRIEF_TIMEOUT_S, model="gpt-5.4", temperature=0.45
        )
        if text and "BLUF" in text:
            return text
    text = _call_chat_with_timeout(msgs, HERO_BRIEF_TIMEOUT_S, temperature=0.45)
    if text and "BLUF" in text:
        return text
    return _baseline_brief(scenario, message, reactions, personas)


# ---------------------------------------------------------------------------
# Top-level pipeline
# ---------------------------------------------------------------------------

def run_pipeline(scenario_id: str, message: str, *,
                 personas_n: int = 5, hero: bool = True,
                 use_cache: bool = True) -> dict[str, Any]:
    """Cache-first orchestration. If use_cache and a cached brief exists for
    this scenario AND the message matches the cached sample message, return
    the cached bundle. Otherwise run the full pipeline."""
    personas_all = load_personas()
    scenarios = load_scenarios()
    scenario = next((s for s in scenarios if s["scenario_id"] == scenario_id),
                    scenarios[0])
    panel = pick_personas(personas_all, n=personas_n)

    cached = load_cached_briefs() if use_cache else {}
    cached_entry = cached.get(scenario_id)
    if cached_entry and cached_entry.get("trainee_message", "").strip() == (message or "").strip():
        return {
            "scenario": scenario,
            "personas": [p for p in personas_all if p["persona_id"] in cached_entry["personas_used"]],
            "message": message,
            "reactions": cached_entry["reactions"],
            "brief": cached_entry["brief_markdown"],
            "generated_at": cached_entry.get("generated_at",
                                             datetime.now(timezone.utc).isoformat()),
            "source": cached_entry.get("source", "cache"),
        }

    reactions = simulate_panel(panel, scenario, message)
    brief = write_brief(scenario, message, reactions, panel, hero=hero)
    return {
        "scenario": scenario,
        "personas": panel,
        "message": message,
        "reactions": reactions,
        "brief": brief,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "live",
    }


if __name__ == "__main__":
    scenarios = load_scenarios()
    cached = load_cached_briefs()
    sc = scenarios[0]
    msg = cached.get(sc["scenario_id"], {}).get("trainee_message", "Test message.")
    out = run_pipeline(sc["scenario_id"], msg, hero=False, use_cache=True)
    print(json.dumps([{"id": r["persona_id"], "delta": r["trust_delta"],
                       "risk": r["narrative_risk"], "action": r["predicted_action"]}
                      for r in out["reactions"]], indent=2))
    print("\n---\n")
    print(out["brief"][:1200])
