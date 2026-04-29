"""OMNI cross-domain correlator + Commander's I-COP Brief.

Hero AI move: a `chat_json` cross-domain correlator analyzes ~600 fused
events from 6 streams (gate, utility, EMS, mass-notify, weather, GCSS-MC,
RF, drone-RF, FIRMS). It returns 3-5 anomalies, each annotated with how
many domains corroborate it, the contributing streams, an explainability
trace, and a confidence.

Then a `chat` ("gpt-5.4", 35s timeout) writes a one-page Commander's I-COP
Brief — BLUF, top 3 cross-domain anomalies, predictive risk for next 12h,
recommended pre-positioning per CCDR.

Both calls are wrapped in concurrent.futures with a wall-clock timeout
and fall back to deterministic functions on any failure.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json  # noqa: E402

HERO_MODEL = "gpt-5.4"
MINI_TIMEOUT = 18
HERO_TIMEOUT = 35


SYSTEM_CORRELATOR = (
    "You are OMNI — the USMC LOGCOM cross-domain Installation Common "
    "Operating Picture correlator. You consume fused multi-source events "
    "across SIX domains: gate access (DBIDS), utility readings (DPW SCADA), "
    "fire/EMS dispatches (CAD), mass-notification (AtHoc / Giant Voice), "
    "weather (NASA Earthdata), GCSS-MC maintenance, IEEE WiFi/BT RF "
    "fingerprinting, drone RF detections (Remote-ID + non-cooperative "
    "FHSS), and NASA FIRMS thermal pings. Output strict JSON identifying "
    "anomalies that are corroborated ACROSS MULTIPLE DOMAINS in the same "
    "time window. Every anomaly includes a domains_crossed count and a "
    "one-line explainability trace. Each recommended action must be "
    "taskable by a watch officer in under 60 seconds."
)


SYSTEM_BRIEF = (
    "You are the senior watch officer's AI battle-buddy in the MCB Camp "
    "Pendleton Installation EOC. Draft a Commander's I-COP Brief in plain "
    "text. Use Marine register: BLUF, then the top 3 cross-domain "
    "anomalies (mention how many domains corroborate each), then "
    "predictive risk for the next 12 hours, then recommended pre-"
    "positioning per CCDR. End with '//SIGNED// I-COP Aggregator (OMNI)'. "
    "Do not exceed 360 words."
)


def _correlator_user_prompt(installation_name: str, as_of_iso: str,
                            anomaly_window: list[dict]) -> str:
    return (
        f"Installation: {installation_name}\n"
        f"As of: {as_of_iso}\n\n"
        f"Anomalous fused events (last 24h):\n"
        f"{json.dumps(anomaly_window, indent=2)}\n\n"
        "Return JSON: {\"anomalies\": [{\"anomaly_id\": str, "
        "\"severity\": \"LOW|MEDIUM|HIGH\", \"domains_crossed\": int, "
        "\"contributing_streams\": [str], \"hypothesis\": str, "
        "\"recommended_action\": str, \"explainability\": str, "
        "\"confidence\": 0..1}]} -- 3 to 5 anomalies, sorted by severity desc."
    )


def _brief_user_prompt(installation_name: str, as_of_iso: str,
                       correlation: dict) -> str:
    return (
        f"INSTALLATION: {installation_name}\n"
        f"AS OF: {as_of_iso}\n\n"
        f"CORRELATION JSON:\n{json.dumps(correlation, indent=2)}\n\n"
        "Draft the Commander's I-COP Brief now."
    )


def baseline_correlation(fused: list[dict]) -> dict:
    """Deterministic fallback. Mirrors the cached payload."""
    return {
        "anomalies": [
            {
                "anomaly_id": "OMNI-001",
                "severity": "HIGH",
                "domains_crossed": 5,
                "contributing_streams": ["drone_rf", "rf", "ems", "firms", "massnotify"],
                "hypothesis": (
                    "Cross-domain force-protection event at Las Pulgas Magazine 14: a "
                    "non-cooperative UAS (no Remote ID) was detected loitering 18 min "
                    "before ignition; an unknown 2.4 GHz emitter inside the magazine "
                    "perimeter persisted across 8 minutes pre-event; FIRMS thermal "
                    "anomalies coincide with multi-unit P1 EMS dispatch and the "
                    "EMERGENCY AtHoc broadcast."
                ),
                "recommended_action": (
                    "Activate Installation EOC at COG; cue G-2 to chain-of-custody "
                    "the drone-RF + 2.4 GHz spectrogram captures; tip MARFORPAC J-2 "
                    "and CDF on potential adversary triggering action."
                ),
                "explainability": (
                    "Flagged because: drone-RF sighting at T-18m + RF unknown-emitter "
                    "at T-8m + FIRMS thermal at T+4m + EMS P1 at T+2m + AtHoc EMERGENCY "
                    "at T+6m — all within a 30-minute window over the same magazine."
                ),
                "confidence": 0.93,
            },
            {
                "anomaly_id": "OMNI-002",
                "severity": "HIGH",
                "domains_crossed": 4,
                "contributing_streams": ["ems", "utility", "gate", "massnotify"],
                "hypothesis": (
                    "Cross-stream installation-services corroboration: 22 psi water "
                    "pressure dip at Mainside Water Tower, 2.6 MW load surge at 22-Area "
                    "Substation, POV ingress spike at Las Pulgas Gate, EMERGENCY AtHoc."
                ),
                "recommended_action": (
                    "Pre-position MEDIC-5 at 43-Area; coordinate PMO traffic-control "
                    "plan at Las Pulgas Gate; brief PWD on water-pressure recovery."
                ),
                "explainability": (
                    "Flagged because: water dip + power surge + gate spike + AtHoc "
                    "EMERGENCY all within the same 30-min window."
                ),
                "confidence": 0.90,
            },
            {
                "anomaly_id": "OMNI-003",
                "severity": "MEDIUM",
                "domains_crossed": 2,
                "contributing_streams": ["weather", "ems"],
                "hypothesis": (
                    "Santa Ana wind shift to ~14 m/s easterly is concurrent with the "
                    "magazine fire — pushing smoke and embers toward San Onofre housing."
                ),
                "recommended_action": (
                    "Pre-stage Engine Co 1 reserves at San Onofre; coordinate PWD "
                    "downwind air-quality monitoring; place housing on voluntary evac."
                ),
                "explainability": (
                    "Flagged because: weather wind 14 m/s easterly + structure-fire "
                    "EMS dispatch — wind vector projects ember plume on housing."
                ),
                "confidence": 0.78,
            },
            {
                "anomaly_id": "OMNI-004",
                "severity": "MEDIUM",
                "domains_crossed": 2,
                "contributing_streams": ["maintenance", "ems"],
                "hypothesis": (
                    "GCSS-MC reports MCFD GENSET-MCFD-AUX-3 NMC during the magazine "
                    "incident window — backup power resilience is degraded."
                ),
                "recommended_action": (
                    "CLB-1 expedite voltage-regulator swap; pre-stage commercial "
                    "generator from contingency contract."
                ),
                "explainability": (
                    "Flagged because: GCSS-MC NMC GENSET + concurrent EMS P1 incident."
                ),
                "confidence": 0.83,
            },
        ],
        "_source": "deterministic_baseline",
    }


def baseline_brief(installation_name: str, as_of_iso: str, correlation: dict) -> str:
    bullets = "\n".join(
        f"  - [{a['severity']}] {a['anomaly_id']} (domains crossed: {a.get('domains_crossed', '?')}): "
        f"{a['hypothesis']}"
        for a in correlation.get("anomalies", [])[:3]
    )
    actions = "\n".join(
        f"  - {a['recommended_action']}" for a in correlation.get("anomalies", [])[:3]
    )
    return (
        f"COMMANDER'S I-COP BRIEF — {installation_name}\n"
        f"AS OF: {as_of_iso}\n\n"
        f"BLUF: Active cross-domain force-protection event at Las Pulgas "
        f"Magazine 14. Five domains corroborate within a 30-minute window — "
        f"non-cooperative UAS loiter, unknown 2.4 GHz emitter inside the "
        f"perimeter, FIRMS thermal anomaly, multi-unit P1 EMS dispatch, "
        f"EMERGENCY AtHoc broadcast. EOC activation recommended.\n\n"
        f"TOP 3 CROSS-DOMAIN ANOMALIES:\n{bullets}\n\n"
        f"PREDICTIVE RISK — NEXT 12H:\n"
        f"  - Santa Ana wind shift sustains 6-8h; ember risk to San Onofre.\n"
        f"  - Mainside water pressure to recover within 90 min of suppression.\n"
        f"  - If RF spectrogram analysis confirms triggering action, expect "
        f"MARFORPAC J-2 escalation and FPCON uplift.\n\n"
        f"RECOMMENDED PRE-POSITIONING PER CCDR:\n{actions}\n\n"
        f"//SIGNED// I-COP Aggregator (OMNI)"
    )


def correlate_streams(installation_name: str, as_of_iso: str,
                      fused: list[dict]) -> dict[str, Any]:
    anomaly_window = [f for f in fused if f.get("is_anomaly")]
    messages = [
        {"role": "system", "content": SYSTEM_CORRELATOR},
        {"role": "user", "content": _correlator_user_prompt(
            installation_name, as_of_iso, anomaly_window)},
    ]
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(
                lambda: chat_json(
                    messages,
                    schema_hint=("anomalies[] with anomaly_id, severity, "
                                 "domains_crossed, contributing_streams, "
                                 "hypothesis, recommended_action, "
                                 "explainability, confidence"),
                    temperature=0.25,
                    max_tokens=1100,
                )
            )
            result = future.result(timeout=MINI_TIMEOUT)
        if isinstance(result, dict) and "anomalies" in result:
            result["_source"] = "live"
            return result
    except (FutTimeout, Exception):  # noqa: BLE001
        pass
    return baseline_correlation(fused)


def _hero_call(messages: list[dict]) -> str:
    """Hero model call. Tries hero-shape kwargs, falls back to mini chain."""
    try:
        from shared.kamiwaza_client import get_client  # noqa: WPS433
        client = get_client()
        resp = client.chat.completions.create(
            model=HERO_MODEL,
            messages=messages,
            max_completion_tokens=1100,
        )
        return resp.choices[0].message.content or ""
    except Exception:  # noqa: BLE001
        return chat(messages, temperature=0.35, max_tokens=1100)


def commander_brief(installation_name: str, as_of_iso: str,
                    correlation: dict) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_BRIEF},
        {"role": "user", "content": _brief_user_prompt(
            installation_name, as_of_iso, correlation)},
    ]
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(lambda: _hero_call(messages))
            text = future.result(timeout=HERO_TIMEOUT)
        if text and text.strip():
            return text
    except (FutTimeout, Exception):  # noqa: BLE001
        pass
    return baseline_brief(installation_name, as_of_iso, correlation)
