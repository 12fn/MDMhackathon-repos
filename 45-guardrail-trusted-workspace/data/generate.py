"""GUARDRAIL — synthetic data generator.

Produces:
  - data/per_doc_markings.json   (per-paragraph CUI marks for every sample doc)
  - data/browser_events.jsonl    (100 synthetic browser-intercept events)
  - data/cached_briefs.json      (3 cached governance posture briefs)

Reproducible (seed=1776). Re-run any time:

    python data/generate.py

The Streamlit app reads everything from the cached files so the demo never
sits on a spinner. Live regenerate paths are exposed in src/app.py.
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(APP_DIR))

DATA_DIR = APP_DIR / "data"
SAMPLES_DIR = APP_DIR / "sample_docs"
DATA_DIR.mkdir(parents=True, exist_ok=True)

R = random.Random(1776)


# ---------------------------------------------------------------------------
# Per-paragraph CUI marking (deterministic baseline used for cache).
# Mirrors the rule set from REDLINE so the markings look identical to the
# trusted exemplar. The Streamlit app calls the same rule logic at runtime
# for "live" pastes; this file lets us pre-warm the four sample docs.
# ---------------------------------------------------------------------------

MARK_RULES: list[tuple[str, str, list[str], str, list[str]]] = [
    ("ts//sci", "TOP SECRET//SCI",
     ["TS//SCI", "TS/SCI", "compartmented", "SCIF only"],
     "Compartmented intelligence — TS/SCI handling required.",
     ["NOFORN"]),
    ("ts/sci", "TOP SECRET//SCI",
     ["TS/SCI", "compartmented"],
     "Compartmented intelligence — TS/SCI handling required.",
     ["NOFORN"]),
    ("s//nf", "SECRET",
     ["S//NF", "SECRET//NOFORN"],
     "Collateral SECRET//NOFORN finished intelligence present.",
     ["NOFORN"]),
    ("secret//noforn", "SECRET",
     ["SECRET//NOFORN"],
     "Collateral SECRET//NOFORN finished intelligence present.",
     ["NOFORN"]),
    ("source selection", "CUI//SP-PROCURE",
     ["source selection", "BAFO", "competitive", "evaluation", "SSEB", "tradeoff analysis"],
     "FAR 3.104 source-selection sensitive content present.",
     ["FED ONLY"]),
    ("itar", "CUI//SP-EXPT",
     ["ITAR", "USML", "deemed-export", "TDP", "DoDD 5230.24"],
     "ITAR / USML export-control language present (DoDD 5230.24).",
     ["NOFORN"]),
    ("noforn", "CUI//SP-NF",
     ["NOFORN", "U.S. only", "no foreign disclosure"],
     "Author explicitly invokes NOFORN handling.",
     ["NOFORN"]),
    ("u.s. only", "CUI//SP-NF",
     ["U.S. only"],
     "Document marks U.S.-only handling.",
     ["NOFORN"]),
    ("force protection", "CUI//SP-OPSEC",
     ["FPCON", "vulnerability", "manning roster", "rotation schedule"],
     "OPSEC indicators referenced (FPCON, vulnerability, manning).",
     ["NOFORN"]),
    ("manning roster", "CUI//SP-OPSEC",
     ["manning roster", "rotation schedule"],
     "OPSEC indicators referenced.",
     ["NOFORN"]),
    ("vulnerability assessment", "CUI//SP-OPSEC",
     ["vulnerability assessment"],
     "OPSEC indicator — vulnerability assessment language.",
     []),
    ("vendor", "CUI//SP-PROPIN",
     ["vendor", "rate card", "labor rate", "BAFO", "ODC", "vendor-proprietary"],
     "Vendor-proprietary cost / pricing data present.",
     ["FED ONLY"]),
    ("proprietary", "CUI//SP-PROPIN",
     ["proprietary", "trade secret"],
     "Proprietary business information present.", []),
    ("ssn", "CUI//SP-PRVCY",
     ["SSN", "DOB", "EDIPI", "home address"],
     "PII triggers present under DoD 5400.11-R.", ["FED ONLY"]),
    ("edipi", "CUI//SP-PRVCY",
     ["EDIPI", "DOB", "home-of-record", "Privacy-Act"],
     "PII / Privacy Act triggers present.", ["FED ONLY"]),
    ("privacy-act", "CUI//SP-PRVCY",
     ["Privacy Act", "Privacy-Act", "DoD 5400.11-R"],
     "Privacy Act protected fields present.", ["FED ONLY"]),
    ("public release", "UNCLASSIFIED",
     ["public release", "unrestricted"],
     "Author requests public / unrestricted release.", []),
    ("unrestricted", "UNCLASSIFIED",
     ["unrestricted distribution"],
     "Unrestricted distribution explicitly requested.", []),
    ("pre-decisional", "CUI//FOUO",
     ["pre-decisional", "draft", "working paper"],
     "Pre-decisional / working-paper status warrants FOUO.", []),
    ("internal use", "CUI//FOUO",
     ["internal use", "do not release"],
     "Internal-use-only language.", []),
]

CONFIDENCE_BASE = 0.78


def _rule_paragraph(paragraph: str) -> dict:
    p = paragraph.lower()
    for trigger, marking, phrases, rationale, caveats in MARK_RULES:
        if trigger in p:
            present = [ph for ph in phrases if ph.lower() in p]
            return {
                "recommended_marking": marking,
                "rationale": rationale,
                "trigger_phrases": present or [trigger],
                "caveats_recommended": caveats,
                "confidence": CONFIDENCE_BASE,
            }
    return {
        "recommended_marking": "UNCLASSIFIED",
        "rationale": "No CUI category triggers detected; routine administrative content.",
        "trigger_phrases": [],
        "caveats_recommended": [],
        "confidence": 0.62,
    }


def _split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n")]
    return [p for p in parts if p]


def _doc_brief(paragraph_results: list[dict]) -> dict:
    order = [
        "UNCLASSIFIED", "CUI//FOUO", "CUI//SP-PROCURE", "CUI//SP-PROPIN",
        "CUI//SP-PRVCY", "CUI//SP-OPSEC", "CUI//SP-EXPT", "CUI//SP-NF",
        "SECRET", "TOP SECRET//SCI",
    ]
    rank = {m: i for i, m in enumerate(order)}
    best = max(paragraph_results,
               key=lambda r: rank.get(r.get("recommended_marking", "UNCLASSIFIED"), 0))
    overall = best.get("recommended_marking", "CUI//FOUO")
    has_noforn = any(
        "NOFORN" in (cv or "") for r in paragraph_results
        for cv in r.get("caveats_recommended", []) or []
    )
    rel = "NOFORN" if has_noforn or "NF" in overall or overall.startswith("SECRET") else "REL TO USA, FVEY"
    return {
        "overall_marking": overall,
        "releasability": rel,
        "paragraph_count": len(paragraph_results),
        "exec_summary": (
            f"Document spans UNCLASSIFIED through {overall}. Most-restrictive "
            f"paragraph drives the banner-line marking under DoDM 5200.01 Vol 2. "
            f"Recommended releasability: {rel}."
        ),
    }


def _build_per_doc_markings() -> dict:
    out: dict = {}
    for f in sorted(SAMPLES_DIR.glob("*.txt")):
        text = f.read_text()
        paras = _split_paragraphs(text)
        results = []
        for i, p in enumerate(paras):
            r = _rule_paragraph(p)
            r["paragraph_index"] = i
            r["paragraph_text"] = p
            results.append(r)
        brief = _doc_brief(results)
        out[f.stem] = {
            "doc_id": f.stem,
            "title": f.stem.replace("_", " ").upper(),
            "paragraphs": results,
            "doc_brief": brief,
        }
    return out


# ---------------------------------------------------------------------------
# Browser intercept events — mix of human + Comet + manus.im + extension
# ---------------------------------------------------------------------------

INTERNAL_APPS = [
    {"app": "GUARDRAIL Workspace", "endpoint": "/workspace/doc/01_operations_brief", "data_class": "CUI"},
    {"app": "GUARDRAIL Workspace", "endpoint": "/workspace/doc/02_intel_summary", "data_class": "CUI"},
    {"app": "GUARDRAIL Workspace", "endpoint": "/workspace/doc/03_training_memo", "data_class": "UNCLASS"},
    {"app": "GUARDRAIL Workspace", "endpoint": "/workspace/doc/04_contractor_sow", "data_class": "CUI"},
    {"app": "GUARDRAIL AI Asst", "endpoint": "/ai/query", "data_class": "CUI"},
    {"app": "GUARDRAIL Workspace", "endpoint": "/workspace/audit/export", "data_class": "CUI"},
    {"app": "GUARDRAIL Workspace", "endpoint": "/auth/totp/verify", "data_class": "AUTH"},
]

PROFILES = {
    "human_marine": {
        "kind": "human", "ua_pool": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        ],
        "entropy_range": (0.62, 0.94),
        "screenshot_calls_range": (0, 0),
        "ai_headers": [],
        "dom_markers": [],
        "webdriver": False,
    },
    "perplexity_comet": {
        "kind": "perplexity_comet", "ua_pool": [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Comet/1.4 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Comet-Browser/1.5 Chrome/126.0.0.0 Safari/537.36",
        ],
        "entropy_range": (0.04, 0.18),
        "screenshot_calls_range": (3, 14),
        "ai_headers": ["X-Sec-Comet", "X-Comet-Agent-Run-Id", "X-Perplexity-Assist"],
        "dom_markers": ["#comet-sidebar-root"],
        "webdriver": False,
    },
    "manus_im": {
        "kind": "manus_im", "ua_pool": [
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/127.0.0.0 manus-agent/0.7",
            "manus.im/0.8 (autonomous-browser; +https://manus.im) Chrome/126.0.0.0",
        ],
        "entropy_range": (0.0, 0.05),
        "screenshot_calls_range": (8, 22),
        "ai_headers": ["X-Manus-Run", "X-Manus-Task-Id"],
        "dom_markers": ["[data-manus-step]"],
        "webdriver": True,
    },
    "skyvern": {
        "kind": "unknown_browser_ai", "ua_pool": [
            "Mozilla/5.0 (Windows NT 10.0) Chrome/127.0.0.0 Skyvern-Agent/0.4 Safari/537.36",
        ],
        "entropy_range": (0.05, 0.20),
        "screenshot_calls_range": (5, 18),
        "ai_headers": ["X-AI-Assistant", "X-Skyvern-Run"],
        "dom_markers": ["#skyvern-root"],
        "webdriver": True,
    },
    "extension": {
        "kind": "suspected_extension", "ua_pool": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/127.0.0.0 Safari/537.36",
        ],
        "entropy_range": (0.18, 0.40),
        "screenshot_calls_range": (0, 3),
        "ai_headers": [],
        "dom_markers": ["[data-ext-injected='monica']"],
        "webdriver": False,
    },
}

PROFILE_WEIGHTS = [
    ("human_marine", 0.42),
    ("perplexity_comet", 0.20),
    ("manus_im", 0.14),
    ("skyvern", 0.12),
    ("extension", 0.12),
]


def _weighted_choice() -> str:
    r = R.random()
    cum = 0.0
    for n, w in PROFILE_WEIGHTS:
        cum += w
        if r <= cum:
            return n
    return PROFILE_WEIGHTS[-1][0]


def _ip() -> str:
    return f"10.{R.randint(20, 80)}.{R.randint(0, 250)}.{R.randint(2, 250)}"


def _event(idx: int, t0: datetime) -> dict:
    name = _weighted_choice()
    p = PROFILES[name]
    target = R.choice(INTERNAL_APPS)
    method = "POST" if any(k in target["endpoint"] for k in ("verify", "submit", "edit", "export")) else "GET"
    ts = t0 + timedelta(seconds=idx * R.randint(2, 7))
    headers = list(p["ai_headers"])
    if name == "human_marine" and R.random() < 0.06:
        headers.append("X-Grammarly-Extension")
    entropy = round(R.uniform(*p["entropy_range"]), 3)
    screenshots = R.randint(*p["screenshot_calls_range"])
    return {
        "event_id": f"evt-{idx:04d}",
        "timestamp_utc": ts.isoformat(),
        "client_ip": _ip(),
        "internal_app": target["app"],
        "endpoint": target["endpoint"],
        "method": method,
        "data_class": target["data_class"],
        "ground_truth_kind": p["kind"],
        "signals": {
            "user_agent": R.choice(p["ua_pool"]),
            "ai_headers_present": headers,
            "dom_markers": list(p["dom_markers"]),
            "navigator_webdriver": p["webdriver"],
            "mouse_movement_entropy": entropy,
            "screenshot_api_calls_30s": screenshots,
        },
    }


def _build_events(n: int = 100) -> list[dict]:
    t0 = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=n * 3)
    return [_event(i, t0) for i in range(n)]


# ---------------------------------------------------------------------------
# Cached governance posture briefs (cache-first hero output)
# ---------------------------------------------------------------------------

SCENARIOS = [
    {
        "id": "nominal_workspace",
        "label": "Nominal day — trusted Marine workspace",
        "stats": {
            "documents_open": 4,
            "personas_switched": 4,
            "paragraphs_marked": 24,
            "abac_redactions": 11,
            "browser_ai_blocks": 8,
            "audit_chain_entries": 31,
            "top_threat": "perplexity_comet",
        },
    },
    {
        "id": "active_comet_probe",
        "label": "Active Comet probe against intel summary",
        "stats": {
            "documents_open": 4,
            "personas_switched": 4,
            "paragraphs_marked": 24,
            "abac_redactions": 18,
            "browser_ai_blocks": 21,
            "audit_chain_entries": 47,
            "top_threat": "perplexity_comet",
        },
    },
    {
        "id": "manus_foothold",
        "label": "manus.im autonomous foothold suspected",
        "stats": {
            "documents_open": 4,
            "personas_switched": 4,
            "paragraphs_marked": 24,
            "abac_redactions": 22,
            "browser_ai_blocks": 29,
            "audit_chain_entries": 58,
            "top_threat": "manus_im",
        },
    },
]


def _baseline_brief(scenario: dict) -> str:
    s = scenario["stats"]
    return f"""# Workspace Governance Posture Brief — {scenario['label']}

## BLUF
Over the last shift the GUARDRAIL workspace screened {s['documents_open']} active
drafts across {s['personas_switched']} Marine personas and 4 simultaneous governance
layers (CUI marking, ABAC enforcement, browser-AI gov, hash-chained audit).
{s['paragraphs_marked']} paragraphs received CUI marking recommendations under
DoDM 5200.01 Vol 2; {s['abac_redactions']} were redacted at view time by ABAC
(NIST SP 800-162); {s['browser_ai_blocks']} browser-resident AI agents were
blocked at the workspace boundary; the SHA-256 audit chain wrote
{s['audit_chain_entries']} verifiable entries.

## Top exfil vectors blocked
1. **{s['top_threat']}** screen-reading the intel summary with mouse entropy
   below the 0.10 human floor and ≥3 screenshot-API calls in 30 s.
2. **manus.im autonomous browser** asserting `navigator.webdriver=true`
   against the AI assistant endpoint to harvest CUI in batch.
3. **Skyvern-class agents** sending `X-AI-Assistant` headers from a
   contractor-scoped persona — caught by the BLOCK_KNOWN_AI_UA policy.

## CUI exposure surface
- Per-paragraph SP-OPSEC marks on the operations brief correctly redact
  the FPCON / vulnerability paragraphs from the Pvt persona view.
- SP-PROPIN + SP-EXPT marks on the contractor SOW correctly hide pricing
  and ITAR-controlled technical data from the contractor's own session.
- SP-NF + SECRET//NOFORN marks on the intel summary keep the foreign-
  disclosure paragraphs out of any persona without the NOFORN caveat held.

## Recommended policy tightening
- Promote `BLOCK_SCREENSHOT_API` from MEDIUM to HIGH severity for any
  endpoint serving CUI (DoDM 5200.01 Vol 2 paragraph-marked content).
- Add a deny rule for User-Agents containing `manus`, `Comet`,
  `Skyvern`, `ArcSearchAssistant`. Review the known-AI-UA list weekly.
- Require step-up auth (CAC + TOTP) before any Comet- or manus-detected
  session may even render the workspace shell.

## Authority anchors
DoDM 5200.01 Vol 2; 32 CFR Part 2002 (CUI); NIST SP 800-162 (ABAC);
DoDD 5230.24 (CTI); FAR 3.104 (procurement-sensitive); Privacy Act
of 1974. Multi-provider model surface served behind
`KAMIWAZA_BASE_URL` keeps every byte inside the SCIF.

_(Deterministic baseline rendering. The hero call substitutes a narrative
draft from the Kamiwaza-deployed model on demand.)_
"""


def _precompute_briefs() -> None:
    out: dict = {}
    chat = None
    try:
        from shared.kamiwaza_client import chat as _chat
        chat = _chat
    except Exception as e:  # noqa: BLE001
        print(f"[generate] shared client unavailable ({e}); writing baseline briefs.")

    for sc in SCENARIOS:
        body = _baseline_brief(sc)
        if chat is not None and (os.getenv("OPENAI_API_KEY") or os.getenv("KAMIWAZA_BASE_URL")):
            try:
                prompt = (
                    "You are a USMC LOGCOM cyber-governance analyst. Draft a "
                    "Workspace Governance Posture Brief for the scenario below. "
                    "Use H1 'Workspace Governance Posture Brief — <label>', then sections: "
                    "BLUF, Top exfil vectors blocked (numbered), CUI exposure surface "
                    "(bulleted), Recommended policy tightening (bulleted), Authority anchors. "
                    "~280 words. Cite DoDM 5200.01 Vol 2, 32 CFR Part 2002, NIST SP 800-162.\n\n"
                    f"Scenario: {sc['label']}\n"
                    f"Stats: {json.dumps(sc['stats'])}\n"
                )
                body = chat(
                    [
                        {"role": "system", "content": "You are precise, defense-grade, no fluff."},
                        {"role": "user", "content": prompt},
                    ],
                    model=os.getenv("LLM_HERO_MODEL", os.getenv("LLM_PRIMARY_MODEL", "gpt-5.4")),
                    temperature=0.3,
                )
            except Exception as e:  # noqa: BLE001
                print(f"[generate] hero call failed for {sc['id']}: {e}; using baseline.")

        out[sc["id"]] = {
            "label": sc["label"],
            "stats": sc["stats"],
            "brief_markdown": body,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    (DATA_DIR / "cached_briefs.json").write_text(json.dumps(out, indent=2))
    print(f"[generate] wrote cached_briefs.json ({len(out)} scenarios).")


def main() -> None:
    per_doc = _build_per_doc_markings()
    (DATA_DIR / "per_doc_markings.json").write_text(json.dumps(per_doc, indent=2))
    print(f"[generate] wrote per_doc_markings.json ({len(per_doc)} docs).")

    events = _build_events(100)
    with (DATA_DIR / "browser_events.jsonl").open("w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    print(f"[generate] wrote browser_events.jsonl ({len(events)} events).")

    _precompute_briefs()


if __name__ == "__main__":
    main()
